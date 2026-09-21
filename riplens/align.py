"""Force-align known lyrics to a vocal stem.

No ASR. No API. FFmpeg PCM + NumPy only.

Given the words (a .txt / .lrc / ID3 tag) and the isolated vocal,
map each line onto sung energy. Timing snaps to pauses so captions
land on bars instead of drifting through the beat.

This is the accurate path for music videos: the artist already has
the words. Whisper-class ASR on singing is a draft at best.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import numpy as np

from riplens.ffmpeg import ffmpeg_bin
from riplens.subtitles import Cue

LRC_LINE = re.compile(r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]\s*(.*)$")
SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


def pcm(path: Path, sr: int = 16000) -> np.ndarray:
    raw = subprocess.check_output(
        [
            ffmpeg_bin(),
            "-v",
            "error",
            "-i",
            str(path),
            "-f",
            "f32le",
            "-ac",
            "1",
            "-ar",
            str(sr),
            "pipe:1",
        ]
    )
    return np.frombuffer(raw, dtype=np.float32)


def rms_envelope(y: np.ndarray, sr: int, hop: int = 256, win: int = 1024) -> tuple[np.ndarray, np.ndarray]:
    if y.size == 0:
        return np.zeros(1, dtype=np.float32), np.zeros(1, dtype=np.float32)
    n = 1 + max(0, (len(y) - win) // hop)
    rms = np.zeros(n, dtype=np.float32)
    for i in range(n):
        sl = y[i * hop : i * hop + win]
        if sl.size < win:
            sl = np.pad(sl, (0, win - sl.size))
        rms[i] = float(np.sqrt(np.mean(sl * sl) + 1e-12))
    kernel = np.ones(5, dtype=np.float32) / 5.0
    rms = np.convolve(rms, kernel, mode="same")
    times = (np.arange(n) * hop + win / 2) / sr
    return rms, times


def vocal_mask(rms: np.ndarray) -> np.ndarray:
    if rms.size == 0:
        return np.zeros(0, dtype=bool)
    floor = float(np.percentile(rms, 20))
    peak = float(np.percentile(rms, 85))
    thr = floor + 0.22 * max(peak - floor, 1e-6)
    mask = rms >= thr
    # close holes shorter than ~180 ms (about 11 hops at 16 kHz / 256)
    closed = mask.copy()
    n = mask.size
    i = 0
    while i < n:
        if closed[i]:
            i += 1
            continue
        j = i
        while j < n and not closed[j]:
            j += 1
        if i > 0 and j < n and (j - i) <= 12:
            closed[i:j] = True
        i = j
    return closed


def split_lyric_lines(text: str, max_chars: int = 42) -> list[str]:
    raw = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return []
    if raw.lstrip().startswith("WEBVTT") or "-->" in raw:
        from riplens.subtitles import parse_srt_text

        return [c.text.replace("\n", " ").strip() for c in parse_srt_text(raw) if c.text.strip()]

    staged: list[str] = []
    for block in raw.split("\n"):
        line = block.strip()
        if not line or line.startswith("#"):
            continue
        m = LRC_LINE.match(line)
        if m:
            line = m.group(4).strip()
            if not line:
                continue
        if len(line) <= max_chars:
            staged.append(line)
            continue
        # prefer punctuation, then commas, then spaces
        parts = [p.strip() for p in SENTENCE.split(line) if p and p.strip()]
        if len(parts) == 1:
            parts = [p.strip() for p in re.split(r"\s*,\s*", line) if p.strip()]
        buf = ""
        for part in parts:
            trial = (buf + " " + part).strip() if buf else part
            if len(trial) <= max_chars:
                buf = trial
            else:
                if buf:
                    staged.append(buf)
                if len(part) <= max_chars:
                    buf = part
                else:
                    staged.extend(_wrap_words(part, max_chars))
                    buf = ""
        if buf:
            staged.append(buf)
    return staged


def _wrap_words(text: str, max_chars: int) -> list[str]:
    words = text.split()
    out: list[str] = []
    buf = ""
    for w in words:
        trial = (buf + " " + w).strip()
        if len(trial) <= max_chars or not buf:
            buf = trial
        else:
            out.append(buf)
            buf = w
    if buf:
        out.append(buf)
    return out


def parse_lrc(text: str) -> list[Cue] | None:
    rows: list[tuple[float, str]] = []
    for line in text.splitlines():
        m = LRC_LINE.match(line.strip())
        if not m:
            continue
        body = m.group(4).strip()
        if not body:
            continue
        minute = int(m.group(1))
        sec = int(m.group(2))
        frac = m.group(3) or "0"
        if len(frac) == 1:
            frac = frac + "00"
        elif len(frac) == 2:
            frac = frac + "0"
        t = minute * 60 + sec + int(frac[:3]) / 1000.0
        rows.append((t, body))
    if len(rows) < 2:
        return None
    rows.sort(key=lambda r: r[0])
    cues: list[Cue] = []
    for i, (start, body) in enumerate(rows):
        end = rows[i + 1][0] if i + 1 < len(rows) else start + 3.2
        if end <= start:
            end = start + 1.2
        cues.append(Cue(start, end, body))
    return cues


def _snap(times: np.ndarray, rms: np.ndarray, t: float, window: float = 0.28) -> float:
    if times.size == 0:
        return t
    lo, hi = t - window, t + window
    idx = np.where((times >= lo) & (times <= hi))[0]
    if idx.size == 0:
        return float(np.clip(t, times[0], times[-1]))
    # prefer a local pause (low rms) so we don't cut a word in half
    k = int(idx[int(np.argmin(rms[idx]))])
    return float(times[k])


def align_lines(
    lines: list[str],
    y: np.ndarray,
    sr: int,
    min_dur: float = 0.7,
    max_dur: float = 5.2,
) -> list[Cue]:
    lines = [ln.strip() for ln in lines if ln and ln.strip()]
    if not lines:
        return []
    rms, times = rms_envelope(y, sr)
    duration = float(len(y) / sr) if sr else 0.0
    mask = vocal_mask(rms)
    if mask.any():
        v_times = times[mask]
        v_rms = rms[mask]
        t0, t1 = float(v_times[0]), float(v_times[-1])
    else:
        v_times, v_rms = times, rms
        t0, t1 = 0.0, duration
    t1 = max(t1, t0 + min_dur * len(lines) * 0.15)

    weights = np.array([max(len(ln), 8) for ln in lines], dtype=np.float64)
    weights /= weights.sum()

    if mask.any():
        energy = np.maximum(v_rms, 1e-6)
        cum = np.cumsum(energy)
        cum /= cum[-1]
        stamps = [t0]
        acc = 0.0
        for w in weights[:-1]:
            acc += w
            i = int(np.searchsorted(cum, acc))
            i = min(max(i, 1), len(v_times) - 1)
            stamps.append(_snap(times, rms, float(v_times[i])))
        stamps.append(t1)
    else:
        span = max(t1 - t0, min_dur)
        stamps = [t0]
        acc = 0.0
        for w in weights[:-1]:
            acc += w
            stamps.append(t0 + acc * span)
        stamps.append(t1)

    # monotonic + pad
    for i in range(1, len(stamps)):
        if stamps[i] <= stamps[i - 1] + 0.12:
            stamps[i] = stamps[i - 1] + 0.12
    if stamps[-1] > duration + 0.05:
        # scale back into the vocal window
        span = max(stamps[-1] - stamps[0], 1e-3)
        room = max(duration - stamps[0] - 0.05, min_dur)
        scale = room / span
        origin = stamps[0]
        stamps = [origin + (t - origin) * scale for t in stamps]

    cues: list[Cue] = []
    n = len(lines)
    for i, line in enumerate(lines):
        start = stamps[i]
        end = stamps[i + 1] if i + 1 < len(stamps) else stamps[i] + min_dur
        # hold the last frame of a line a little past the boundary so it reads
        if i + 1 < n:
            end = min(end, stamps[i + 1])
        if end - start < min_dur:
            end = start + min_dur
        if end - start > max_dur:
            end = start + max_dur
        if i + 1 < n and end > stamps[i + 1] - 0.04:
            end = max(start + 0.45, stamps[i + 1] - 0.04)
        cues.append(Cue(float(start), float(end), line))

    # never overlap
    for i in range(len(cues) - 1):
        if cues[i].end > cues[i + 1].start:
            mid = (cues[i].start + cues[i + 1].start) / 2
            cues[i] = Cue(cues[i].start, max(cues[i].start + 0.4, mid), cues[i].text)
            cues[i + 1] = Cue(cues[i].end, max(cues[i].end + 0.4, cues[i + 1].end), cues[i + 1].text)
    return cues


def load_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def read_id3_lyrics(song: Path) -> str | None:
    """Best-effort unsynced lyrics. mutagen if present, else a tiny USLT scan."""
    try:
        from mutagen import File as MutagenFile  # type: ignore

        audio = MutagenFile(str(song))
        if audio is None:
            return None
        tags = audio.tags or {}
        for key in ("USLT::eng", "USLT::XXX", "LYRICS", "UNSYNCEDLYRICS", "©lyr"):
            val = tags.get(key)
            if val:
                text = str(getattr(val, "text", val) or "")
                if text.strip():
                    return text
        for key, val in tags.items():
            kn = str(key).upper()
            if "USLT" in kn or kn.endswith("LYR") or "LYRIC" in kn:
                text = str(getattr(val, "text", val) or "")
                if text.strip() and "iTunNORM" not in text:
                    return text
    except Exception:
        pass
    return _scan_id3_uslt(song)


def _scan_id3_uslt(song: Path) -> str | None:
    try:
        data = song.read_bytes()
    except OSError:
        return None
    if data[:3] != b"ID3":
        return None
    marker = b"USLT"
    idx = data.find(marker)
    if idx < 0:
        marker = b"USLT"
        idx = data.find(marker)
    if idx < 0 or idx + 10 >= len(data):
        return None
    size = int.from_bytes(data[idx + 4 : idx + 8], "big")
    if size <= 4 or idx + 10 + size > len(data):
        # synchsafe v2.4 fallback
        bts = data[idx + 4 : idx + 8]
        size = ((bts[0] & 0x7F) << 21) | ((bts[1] & 0x7F) << 14) | ((bts[2] & 0x7F) << 7) | (bts[3] & 0x7F)
    body = data[idx + 10 : idx + 10 + size]
    if not body:
        return None
    enc = body[0]
    rest = body[1:]
    # skip language (3) + short descriptor
    if len(rest) < 4:
        return None
    rest = rest[3:]
    if enc in (0, 3):  # latin-1 / utf-8
        nul = rest.find(b"\x00")
        payload = rest[nul + 1 :] if nul >= 0 else rest
        codec = "utf-8" if enc == 3 else "latin-1"
        return payload.decode(codec, errors="replace").strip() or None
    if enc in (1, 2):
        nul = rest.find(b"\x00\x00")
        payload = rest[nul + 2 :] if nul >= 0 else rest
        codec = "utf-16" if enc == 1 else "utf-16-be"
        return payload.decode(codec, errors="replace").strip() or None
    return None
