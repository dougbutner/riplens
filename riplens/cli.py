"""RipLens CLI — doctor, analyze, render."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from riplens import EFFECT_ORDER, RATIOS, __version__
from riplens.audio import TrackFeatures
from riplens.ffmpeg import encoder_name, ffmpeg_bin
from riplens.io import ensure_layout, list_audio, list_images, list_videos, load_config
from riplens.render import render_all


def _root() -> Path:
    return Path.cwd()


def _cfg(root: Path) -> Path:
    p = root / "config.yaml"
    if not p.exists():
        raise SystemExit("config.yaml not found. Run from the repo root.")
    return p


def cmd_doctor(root: Path) -> int:
    ensure_layout(root)
    cfg = load_config(_cfg(root))
    music = list_audio(root / cfg["sources"]["music"])
    images = list_images(root / cfg["sources"]["images"])
    videos = list_videos(root / cfg["sources"]["videos"])
    enc = encoder_name(cfg.get("codec", {}).get("video", "auto"))
    print(f"RipLens {__version__}")
    print(f"ffmpeg     {ffmpeg_bin()}")
    print(f"encoder    {enc}")
    print(f"songs      {len(music)}")
    print(f"images     {len(images)}")
    print(f"videos     {len(videos)}")
    print("effects    " + ", ".join(EFFECT_ORDER))
    print("ratios     " + ", ".join(f"{k}={v[0]}x{v[1]}" for k, v in RATIOS.items()))
    print("layout     sources/{{music,images,videos}} → output/{{1x1,16x9,9x16}}")
    if not music:
        print("\nDrop audio into sources/music")
    if not images:
        print("Drop art into sources/images")
    return 0


def cmd_analyze(root: Path) -> int:
    cfg = load_config(_cfg(root))
    songs = list_audio(root / cfg["sources"]["music"])
    if not songs:
        print("No audio in sources/music")
        return 1
    rows = []
    for s in songs:
        feat = TrackFeatures(str(s))
        info = feat.summary()
        info["file"] = s.name
        rows.append(info)
        print(
            f"{s.name:40}  {info['duration']:7.1f}s  {info['tempo']:6.1f} BPM  "
            f"peaks={info['peak_count']:<4}  rms={info['rms_mean']:.2f}/{info['rms_max']:.2f}"
        )
    print(json.dumps(rows, indent=2))
    return 0


def cmd_render(args: argparse.Namespace, root: Path) -> int:
    ensure_layout(root)
    song = Path(args.song).expanduser() if args.song else None
    try:
        written = render_all(
            root,
            _cfg(root),
            ratio=args.ratio,
            song=song,
            threshold=args.threshold,
        )
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    print("wrote:")
    for p in written:
        print(f"  {p}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="riplens",
        description="Local glitch music videos from your songs and your art. No AI. No APIs.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="Check ffmpeg, GPU encoder, source folders")
    sub.add_parser("analyze", help="Print BPM, RMS, peak counts for every song")
    r = sub.add_parser("render", help="Write 1x1, then 16x9, then 9x16 H.264 MP4s")
    r.add_argument("--ratio", choices=list(RATIOS), help="Render one ratio only")
    r.add_argument("--song", help="Path to one audio file")
    r.add_argument("--threshold", type=float, help="Override peak threshold (default 0.62)")
    sub.add_parser("init", help="Create sources/ and output/ folders")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = _root()
    if args.cmd == "doctor":
        return cmd_doctor(root)
    if args.cmd == "analyze":
        return cmd_analyze(root)
    if args.cmd == "init":
        ensure_layout(root)
        print("ready: sources/{music,images,videos}  output/{1x1,16x9,9x16}")
        return 0
    if args.cmd == "render":
        return cmd_render(args, root)
    return 1
