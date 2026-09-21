#!/usr/bin/env python3
"""Cut a short proof MP4. No librosa — ffmpeg PCM + OpenCV."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from riplens import EFFECT_ORDER  # noqa: E402
from riplens.effects import (  # noqa: E402
    REGISTRY,
    EffectState,
    cover,
    grain,
)
from riplens.feat import FrameFeat  # noqa: E402
from riplens.glyphs import overlay_glyphs  # noqa: E402
from riplens.subtitles import (  # noqa: E402
    SubtitleRenderer,
    parse_srt,
    resolve_font,
)


def pcm(path: Path, sr: int = 22050) -> np.ndarray:
    cmd = [
        "ffmpeg",
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
    raw = subprocess.check_output(cmd)
    return np.frombuffer(raw, dtype=np.float32)


def features(y: np.ndarray, sr: int, hop: int = 512) -> dict[str, np.ndarray]:
    win = 2048
    n = 1 + max(0, (len(y) - win) // hop)
    rms = np.zeros(n, dtype=np.float32)
    bass = np.zeros(n, dtype=np.float32)
    mid = np.zeros(n, dtype=np.float32)
    treble = np.zeros(n, dtype=np.float32)
    centroid = np.zeros(n, dtype=np.float32)
    freqs = np.fft.rfftfreq(win, 1 / sr)
    for i in range(n):
        sl = y[i * hop : i * hop + win]
        if sl.size < win:
            sl = np.pad(sl, (0, win - sl.size))
        windowed = sl * np.hanning(win)
        mag = np.abs(np.fft.rfft(windowed))
        rms[i] = np.sqrt(np.mean(sl * sl))
        bass[i] = mag[(freqs >= 20) & (freqs < 150)].mean() if np.any((freqs >= 20) & (freqs < 150)) else 0
        mid[i] = mag[(freqs >= 150) & (freqs < 2000)].mean() if np.any((freqs >= 150) & (freqs < 2000)) else 0
        treble[i] = mag[(freqs >= 2000) & (freqs < 8000)].mean() if np.any((freqs >= 2000) & (freqs < 8000)) else 0
        s = mag.sum()
        centroid[i] = float((freqs * mag).sum() / s) if s > 1e-8 else 0
    times = np.arange(n) * hop / sr

    def norm(a: np.ndarray) -> np.ndarray:
        p = np.percentile(a, 95) or 1.0
        return np.clip(a / p, 0, 1).astype(np.float32)

    return {
        "t": times,
        "rms": norm(rms),
        "bass": norm(bass),
        "mid": norm(mid),
        "treble": norm(treble),
        "centroid": norm(centroid),
    }


def at(bank: dict[str, np.ndarray], t: float) -> FrameFeat:
    rms = float(np.interp(t, bank["t"], bank["rms"]))
    bass = float(np.interp(t, bank["t"], bank["bass"]))
    mid = float(np.interp(t, bank["t"], bank["mid"]))
    treble = float(np.interp(t, bank["t"], bank["treble"]))
    centroid = float(np.interp(t, bank["t"], bank["centroid"]))
    h = (centroid * 360.0 + bass * 80.0) % 360.0
    s = 0.35 + mid * 0.65
    v = 0.28 + rms * 0.72
    return FrameFeat(rms, bass, mid, treble, centroid, h, s, v)


def hue_shift(img: np.ndarray, deg: float) -> np.ndarray:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.int16)
    hsv[:, :, 0] = (hsv[:, :, 0] + int(deg / 2)) % 180
    return cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)


def load_bgr(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f"missing art {path}")
    return img


def render(
    seconds: float,
    width: int,
    height: int,
    fps: int,
    dest: Path,
    song: Path | None = None,
    images: list[Path] | None = None,
    use_subs: bool = True,
) -> None:
    song = Path(song) if song else ROOT / "sources/music/guatemalan-balcony.mp3"
    if images:
        plates = [load_bgr(p) for p in images]
    else:
        img = load_bgr(ROOT / "sources/images/olympus.jpg")
        plates = [img, hue_shift(img, 32), hue_shift(img, -48), hue_shift(img, 160)]
    if len(plates) == 1:
        plates = [plates[0], hue_shift(plates[0], 32), hue_shift(plates[0], -48), hue_shift(plates[0], 160)]
    y = pcm(song)
    sr = 22050
    bank = features(y, sr)
    state = EffectState()
    state.plates = plates
    srt = ROOT / "sources/lyrics" / f"{song.stem}.srt"
    burner = None
    if use_subs and srt.is_file():
        cues = parse_srt(srt)
        font = resolve_font(ROOT, "Montserrat-ExtraBold")
        burner = SubtitleRenderer(cues, font, height)
        print(f"subs  {srt.name}  {len(cues)} cues  font={font.name if font else 'default'}")
    n = int(seconds * fps)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "pipe:0",
        "-ss",
        "0",
        "-t",
        str(seconds),
        "-i",
        str(song),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    idx = 0
    cycle = 1.2
    try:
        for i in range(n):
            t = i / fps
            feat = at(bank, t)
            nxt = int(t / cycle) % len(EFFECT_ORDER)
            if nxt != idx:
                idx = nxt
                if EFFECT_ORDER[idx] == "lens_peel":
                    state.peel = 0.0
            name = EFFECT_ORDER[idx]
            if name == "lens_peel":
                state.peel = min(1.0, state.peel + 0.018 + feat.rms * 0.01)
                if state.peel >= 1.0:
                    state.plate_index = (state.plate_index + 1) % len(state.plates)
                    state.peel = 0.0
            frame = cover(state.plate, width, height, 1.0 + 0.08 * feat.rms)
            frame = REGISTRY[name](frame, feat, t, state)
            frame = overlay_glyphs(frame, feat, t, solids_on=False)
            frame = grain(frame, 8.0)
            if burner is not None:
                frame = burner.apply(frame, t)
            proc.stdin.write(frame.tobytes())
            if i % fps == 0:
                print(f"  {i:4d}/{n}  {name}  rms={feat.rms:.2f}", flush=True)
    finally:
        proc.stdin.close()
        code = proc.wait()
    if code != 0:
        raise SystemExit(f"ffmpeg {code}")
    print(f"wrote {dest}  {dest.stat().st_size} bytes")


def main() -> None:
    ap = argparse.ArgumentParser(description="RipLens studio proof renderer")
    ap.add_argument("--seconds", type=float, default=28)
    ap.add_argument("--width", type=int, default=720)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--dest", type=Path, default=ROOT / "output/1x1/preview.mp4")
    ap.add_argument("--song", type=Path, default=None)
    ap.add_argument("--image", action="append", default=None)
    ap.add_argument("--no-subs", action="store_true")
    args = ap.parse_args()
    images = [Path(p) for p in args.image] if args.image else None
    render(
        seconds=args.seconds,
        width=args.width,
        height=args.height,
        fps=args.fps,
        dest=args.dest,
        song=args.song,
        images=images,
        use_subs=not args.no_subs,
    )


if __name__ == "__main__":
    main()
