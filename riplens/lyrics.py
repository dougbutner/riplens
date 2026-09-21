"""Local lyrics: your words, timed to the vocal stem. No API.

Accurate captions for a music video come from the lyric sheet, not from
guessing sung words. Default path:

1. Read `sources/lyrics/<stem>.txt` (or `.lrc`, or an ID3 USLT tag)
2. Isolate vocals (Demucs if installed, else a mid-channel extract)
3. Force-align each line onto vocal energy (FFmpeg + NumPy)
4. Write an editable `sources/lyrics/<stem>.srt`

Whisper is opt-in (`riplens lyrics --asr whisper`) and only a draft.
Never overwrite a `.txt` the user wrote. Never overwrite an SRT unless
`--force`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from riplens.align import (
    align_lines,
    load_text_file,
    parse_lrc,
    pcm,
    read_id3_lyrics,
    split_lyric_lines,
)
from riplens.ffmpeg import ffmpeg_bin
from riplens.subtitles import Cue, write_srt, write_txt


def _run(cmd: list[str]) -> None:
    subprocess.check_call(cmd)


def isolate_vocals(song: Path, dest_dir: Path) -> tuple[Path, str]:
    """Return (wav_path, method)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    wav = dest_dir / f"{song.stem}.vocals.wav"
    if wav.is_file() and wav.stat().st_size > 1024:
        return wav, "cached"

    demucs = shutil.which("demucs")
    if demucs:
        out_root = dest_dir / "demucs"
        cmd = [
            demucs,
            "--two-stems",
            "vocals",
            "-n",
            "htdemucs",
            "-o",
            str(out_root),
            str(song),
        ]
        print("isolating vocals with Demucs htdemucs…")
        _run(cmd)
        found = list(out_root.rglob("vocals.wav"))
        if found:
            audio = found[0]
            _run(
                [
                    ffmpeg_bin(),
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(audio),
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    str(wav),
                ]
            )
            return wav, "demucs-htdemucs"

    print("Demucs not installed — mid-channel extract (center vocals).")
    print("  Mac:  pip install demucs     # uses Apple Silicon MPS")
    _run(
        [
            ffmpeg_bin(),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(song),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-af",
            "pan=mono|c0=0.5*FL+0.5*FR,highpass=f=120,lowpass=f=7000,acompressor=threshold=-18dB:ratio=4:attack=5:release=80",
            str(wav),
        ]
    )
    return wav, "center-channel"


def _transcribe(wav: Path, model_name: str) -> tuple[list[dict], str]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SystemExit(
            "faster-whisper is not installed.\n"
            "  pip install faster-whisper\n"
            "That is an optional local draft. Accurate captions use a .txt of the lyrics."
        ) from exc

    device = "cpu"
    compute = "int8"
    try:
        import torch

        if torch.cuda.is_available():
            device, compute = "cuda", "float16"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            device, compute = "cpu", "int8"
    except ImportError:
        pass

    print(f"whisper  model={model_name}  device={device}  compute={compute}  (draft only)")
    model = WhisperModel(model_name, device=device, compute_type=compute)
    segments, info = model.transcribe(
        str(wav),
        language=None,
        task="transcribe",
        beam_size=5,
        vad_filter=False,
        word_timestamps=True,
        condition_on_previous_text=True,
        temperature=0.0,
        initial_prompt="These are the lyrics of a song. Transcribe the sung words.",
    )
    lang = info.language or "und"
    words: list[dict] = []
    for seg in segments:
        if seg.words:
            for w in seg.words:
                token = (w.word or "").strip()
                if not token:
                    continue
                words.append({"start": float(w.start), "end": float(w.end), "word": token})
        elif seg.text and seg.text.strip():
            words.append(
                {
                    "start": float(seg.start),
                    "end": float(seg.end),
                    "word": seg.text.strip(),
                }
            )
    return words, lang


def _join_words(buf: list[dict]) -> str:
    out = ""
    for w in buf:
        token = w["word"]
        if out and not token.startswith(("'", ",", ".", "!", "?", ";", ":")):
            out += " "
        out += token
    return re.sub(r"\s+", " ", out).strip()


def _pack_cues(words: list[dict], max_chars: int = 42, max_dur: float = 4.4, gap: float = 0.42) -> list[Cue]:
    cues: list[Cue] = []
    buf: list[dict] = []

    def flush() -> None:
        if not buf:
            return
        text = _join_words(buf)
        start = float(buf[0]["start"])
        end = max(float(buf[-1]["end"]), start + 0.7)
        cues.append(Cue(start, end, text))
        buf.clear()

    for w in words:
        if buf:
            pause = float(w["start"]) - float(buf[-1]["end"])
            dur = float(w["end"]) - float(buf[0]["start"])
            trial = _join_words(buf + [w])
            if pause >= gap or dur > max_dur or len(trial) > max_chars:
                flush()
        buf.append(w)
    flush()
    return cues


def find_lyric_text(
    song: Path,
    root: Path,
    explicit: Path | None = None,
) -> tuple[str | None, str, Path | None]:
    """Return (text, origin, path). Text is None if we have nothing to align."""
    lyrics_dir = root / "sources" / "lyrics"
    if explicit:
        p = explicit.expanduser()
        if not p.is_file():
            raise SystemExit(f"missing lyrics file {p}")
        raw = load_text_file(p)
        return raw, f"file:{p.name}", p

    lrc = lyrics_dir / f"{song.stem}.lrc"
    if lrc.is_file():
        return load_text_file(lrc), "lrc", lrc

    txt = lyrics_dir / f"{song.stem}.txt"
    if txt.is_file() and txt.stat().st_size > 8:
        return load_text_file(txt), "txt", txt

    sidecar = song.with_suffix(".txt")
    if sidecar.is_file() and sidecar.stat().st_size > 8:
        return load_text_file(sidecar), "sidecar-txt", sidecar

    tagged = read_id3_lyrics(song)
    if tagged:
        return tagged, "id3", None

    return None, "none", None


def _missing_text_message(song: Path, root: Path) -> str:
    dest = root / "sources" / "lyrics" / f"{song.stem}.txt"
    return (
        f"No lyrics text for {song.name}.\n"
        f"Accurate captions need the words — singing is not speech, so local ASR\n"
        f"will mangle a rap or a sung line. Drop the lyric sheet here, one phrase per line:\n"
        f"  {dest}\n"
        f"Then run `riplens lyrics` again. RipLens isolates the vocal and times each\n"
        f"line locally (FFmpeg + NumPy). No Whisper. No API.\n"
        f"\n"
        f"Already have an .lrc? Put it next to the .txt. ID3 unsynced lyrics are used\n"
        f"if the file has them.\n"
        f"\n"
        f"Last resort draft from the audio (often wrong on singing):\n"
        f"  pip install faster-whisper\n"
        f"  riplens lyrics --asr whisper --force"
    )


def extract_lyrics(
    song: Path,
    root: Path,
    model: str = "small",
    force: bool = False,
    asr: str | None = None,
    text_file: Path | None = None,
) -> dict:
    lyrics_dir = root / "sources" / "lyrics"
    lyrics_dir.mkdir(parents=True, exist_ok=True)
    srt_path = lyrics_dir / f"{song.stem}.srt"
    txt_path = lyrics_dir / f"{song.stem}.txt"
    json_path = lyrics_dir / f"{song.stem}.words.json"
    stem_dir = lyrics_dir / "_stems"

    if srt_path.is_file() and not force:
        print(f"exists  {srt_path}  (edit this file, then re-render). Pass --force to redo.")
        print("Want better words? Edit the .txt (one phrase per line) then:")
        print(f"  riplens lyrics --force")
        return {"srt": str(srt_path), "skipped": True}

    asr = (asr or "").strip().lower() or None
    raw, origin, origin_path = find_lyric_text(song, root, text_file)

    if asr in {"whisper", "faster-whisper", "faster_whisper"}:
        wav, method = isolate_vocals(song, stem_dir)
        words, lang = _transcribe(wav, model)
        cues = _pack_cues(words)
        asr_txt = lyrics_dir / f"{song.stem}.asr.txt"
        write_txt(cues, asr_txt)
        write_srt(cues, srt_path)
        if not txt_path.is_file():
            write_txt(cues, txt_path)
        json_path.write_text(
            json.dumps({"language": lang, "method": method, "model": model, "asr": "whisper", "words": words}, indent=2),
            encoding="utf-8",
        )
        print(f"language {lang}")
        print(f"stem     {method}")
        print(f"cues     {len(cues)}   ← Whisper draft. Proofread {asr_txt.name} / {srt_path.name}.")
        print("Replace the .txt with the real lyrics and run `riplens lyrics --force` for accurate captions.")
        return {
            "srt": str(srt_path),
            "txt": str(txt_path),
            "language": lang,
            "method": method,
            "cues": len(cues),
            "skipped": False,
            "origin": "whisper",
        }

    if raw is None:
        raise SystemExit(_missing_text_message(song, root))

    lrc_cues = parse_lrc(raw) if origin == "lrc" or (origin_path and origin_path.suffix.lower() == ".lrc") else None
    if lrc_cues:
        write_srt(lrc_cues, srt_path)
        if not txt_path.is_file():
            write_txt(lrc_cues, txt_path)
        print(f"origin   {origin} (already timed)")
        print(f"cues     {len(lrc_cues)}")
        print(f"srt      {srt_path}")
        return {
            "srt": str(srt_path),
            "txt": str(txt_path),
            "method": "lrc",
            "cues": len(lrc_cues),
            "skipped": False,
            "origin": origin,
        }

    lines = split_lyric_lines(raw)
    if not lines:
        raise SystemExit(f"lyrics file is empty after cleanup: {origin_path or origin}")

    wav, method = isolate_vocals(song, stem_dir)
    print(f"origin   {origin}  {len(lines)} lines")
    print(f"stem     {method}  {wav.name}")
    print("aligning lines to vocal energy…")
    y = pcm(wav, 16000)
    cues = align_lines(lines, y, 16000)
    write_srt(cues, srt_path)
    if origin != "txt" and not txt_path.is_file():
        txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "origin": origin,
                "method": method,
                "aligner": "energy",
                "lines": [{"start": c.start, "end": c.end, "text": c.text} for c in cues],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"cues     {len(cues)}")
    print(f"srt      {srt_path}")
    if txt_path.is_file():
        print(f"txt      {txt_path}   ← source of truth. Edit words here, then --force.")
    print("Edit the .srt timings if a line lands late, then `riplens render --subs`.")
    return {
        "srt": str(srt_path),
        "txt": str(txt_path),
        "method": method,
        "cues": len(cues),
        "skipped": False,
        "origin": origin,
    }


def lyrics_status() -> dict:
    info = {
        "aligner": True,
        "faster_whisper": False,
        "demucs": bool(shutil.which("demucs")),
        "ffmpeg": ffmpeg_bin(),
    }
    try:
        import faster_whisper  # noqa: F401

        info["faster_whisper"] = True
        info["faster_whisper_ver"] = getattr(faster_whisper, "__version__", "yes")
    except ImportError:
        pass
    return info
