"""RipLens CLI — doctor, analyze, lyrics, render."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from riplens import EFFECT_ORDER, RATIOS, __version__
from riplens.ffmpeg import encoder_name, ffmpeg_bin
from riplens.io import ensure_layout, list_audio, list_images, list_videos, load_config
from riplens.lyrics import extract_lyrics, lyrics_status
from riplens.subtitles import resolve_font


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
    lyr = lyrics_status()
    print(f"whisper    {'yes — ' + str(lyr.get('faster_whisper_ver', 'ok')) if lyr['faster_whisper'] else 'no  (pip install faster-whisper)'}")
    print(f"demucs     {'yes' if lyr['demucs'] else 'no  (optional: pip install demucs)'}")
    font = resolve_font(root, None)
    print(f"sub font   {font if font else 'none — run python3 scripts/collect_fonts.py'}")
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
    from riplens.audio import TrackFeatures

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


def cmd_lyrics(args: argparse.Namespace, root: Path) -> int:
    ensure_layout(root)
    cfg = load_config(_cfg(root))
    music_dir = root / cfg["sources"]["music"]
    if args.song:
        songs = [Path(args.song).expanduser()]
    else:
        songs = list_audio(music_dir)
    if not songs:
        print("No audio in sources/music")
        return 1
    st = lyrics_status()
    if not st["faster_whisper"]:
        print("faster-whisper is not installed. Local, free, no API:")
        print("  pip install faster-whisper")
        return 1
    rc = 0
    for s in songs:
        if not s.is_file():
            print(f"missing {s}", file=sys.stderr)
            rc = 1
            continue
        print(f"→ lyrics  {s.name}")
        try:
            extract_lyrics(s, root, model=args.model, force=args.force)
        except Exception as exc:
            print(exc, file=sys.stderr)
            rc = 1
    return rc


def cmd_render(args: argparse.Namespace, root: Path) -> int:
    from riplens.render import render_all

    ensure_layout(root)
    song = Path(args.song).expanduser() if args.song else None
    try:
        written = render_all(
            root,
            _cfg(root),
            ratio=args.ratio,
            song=song,
            threshold=args.threshold,
            subs=args.subs,
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
    g = r.add_mutually_exclusive_group()
    g.add_argument("--subs", dest="subs", action="store_true", help="Burn sources/lyrics/<stem>.srt onto the video")
    g.add_argument("--no-subs", dest="subs", action="store_false", help="Skip subtitle burn even if config enables it")
    r.set_defaults(subs=None)
    ly = sub.add_parser(
        "lyrics",
        help="Extract vocals → transcribe → write an editable SRT next to the song",
    )
    ly.add_argument("--song", help="Path to one audio file (default: every song in sources/music)")
    ly.add_argument("--model", default="small", help="faster-whisper model: base, small, medium, large-v3")
    ly.add_argument("--force", action="store_true", help="Overwrite an existing SRT")
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
        print("ready: sources/{music,images,videos,lyrics}  output/{1x1,16x9,9x16}  fonts/")
        return 0
    if args.cmd == "lyrics":
        return cmd_lyrics(args, root)
    if args.cmd == "render":
        return cmd_render(args, root)
    return 1
