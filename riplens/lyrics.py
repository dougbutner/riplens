"""Local lyrics extraction: isolate vocals, transcribe, write editable SRT.

Best-accuracy path (all free, all local, Mac-friendly):

1. Vocal stem
   - Demucs `htdemucs` `--two-stems=vocals` when `demucs` is installed
     (Meta MIT model; MPS on Apple Silicon, CUDA on NVIDIA, CPU otherwise)
   - else FFmpeg mid-channel extract (vocals usually sit in the center)
2. Transcribe the stem with faster-whisper
   - VAD off (singing is not speech; VAD drops phrases)
   - word timestamps on, then pack into 1–2 line cues
3. Write `sources/lyrics/<stem>.srt` (edit this) plus a plain `.txt`

Never overwrite an existing SRT unless `--force`. Corrections you type
into the SRT are what the renderer burns.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

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
            "That is the local, free transcriber (CTranslate2). No API."
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

    print(f"whisper  model={model_name}  device={device}  compute={compute}")
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


def _hard_wrap(text: str, max_chars: int) -> tuple[str, str]:
    if len(text) <= max_chars:
        return text, ""
    cut = text.rfind(" ", 0, max_chars)
    if cut < 8:
        cut = max_chars
    return text[:cut].strip(), text[cut:].strip()


def _split_long_lines(cues: list[Cue], max_chars: int) -> list[Cue]:
    fixed: list[Cue] = []
    for c in cues:
        if len(c.text) <= max_chars or " " not in c.text:
            fixed.append(c)
            continue
        words = c.text.split()
        mid = max(1, len(words) // 2)
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])
        if len(line1) > max_chars or len(line2) > max_chars:
            line1, line2 = _hard_wrap(c.text, max_chars)
        fixed.append(Cue(c.start, c.end, f"{line1}\n{line2}".strip()))
    return fixed


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
    return _merge_short(_split_long_lines(cues, max_chars))


def _merge_short(cues: list[Cue], min_chars: int = 22) -> list[Cue]:
    out: list[Cue] = []
    for c in cues:
        if out:
            prev = out[-1]
            gap = c.start - prev.end
            short = len(prev.text.replace("\n", " ")) < min_chars or len(c.text.replace("\n", " ")) < 10
            if short and gap < 0.85:
                text = (prev.text.replace("\n", " ") + " " + c.text.replace("\n", " ")).strip()
                if len(text) > 42 and " " in text:
                    words = text.split()
                    mid = max(1, len(words) // 2)
                    text = " ".join(words[:mid]) + "\n" + " ".join(words[mid:])
                out[-1] = Cue(prev.start, c.end, text)
                continue
        out.append(c)
    return out


def extract_lyrics(
    song: Path,
    root: Path,
    model: str = "small",
    force: bool = False,
) -> dict:
    lyrics_dir = root / "sources" / "lyrics"
    lyrics_dir.mkdir(parents=True, exist_ok=True)
    srt_path = lyrics_dir / f"{song.stem}.srt"
    txt_path = lyrics_dir / f"{song.stem}.txt"
    json_path = lyrics_dir / f"{song.stem}.words.json"
    stem_dir = lyrics_dir / "_stems"

    if srt_path.is_file() and not force:
        print(f"exists  {srt_path}  (edit this file, then re-render). Pass --force to redo.")
        return {"srt": str(srt_path), "skipped": True}

    wav, method = isolate_vocals(song, stem_dir)
    words, lang = _transcribe(wav, model)
    cues = _pack_cues(words)
    write_srt(cues, srt_path)
    write_txt(cues, txt_path)
    json_path.write_text(
        json.dumps({"language": lang, "method": method, "model": model, "words": words}, indent=2),
        encoding="utf-8",
    )
    print(f"language {lang}")
    print(f"stem     {method}")
    print(f"cues     {len(cues)}")
    print(f"srt      {srt_path}")
    print(f"txt      {txt_path}   ← plain lyrics, easy to proofread")
    print("Edit the .srt timings/words, then `riplens render --subs`.")
    return {
        "srt": str(srt_path),
        "txt": str(txt_path),
        "language": lang,
        "method": method,
        "cues": len(cues),
        "skipped": False,
    }


def lyrics_status() -> dict:
    info = {
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
