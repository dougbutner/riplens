"""Frame loop: crop art → effect → HSV geometry → H.264."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tqdm import tqdm

from riplens import EFFECT_ORDER
from riplens.audio import TrackFeatures
from riplens.effects import (
    REGISTRY,
    EffectState,
    cover,
    grain,
)
from riplens.glyphs import overlay_glyphs, overlay_solids
from riplens.ffmpeg import encoder_name, write_cmd
from riplens.io import (
    list_audio,
    list_images,
    list_videos,
    load_config,
    read_image,
    sample_video_plates,
)
from riplens.subtitles import SubtitleRenderer, find_lyrics_file, parse_srt, resolve_font


def render_song(
    song: Path,
    plates: list,
    dest: Path,
    width: int,
    height: int,
    cfg: dict,
    encoder: str,
    root: Path | None = None,
) -> None:
    fps = int(cfg.get("fps", 30))
    threshold = float(cfg.get("threshold", 0.62))
    cooldown = float(cfg.get("cooldown", 1.2))
    ken = float(cfg.get("ken_burns", 0.08))
    names: list[str] = cfg.get("effects") or EFFECT_ORDER
    overlays = cfg.get("overlays") or {}
    solids_on = bool(overlays.get("solids", False))
    glyphs_on = bool(overlays.get("glyphs", True))
    codec = cfg.get("codec") or {}
    crf = int(codec.get("crf", 18))
    preset = str(codec.get("preset", "fast"))
    abit = str(codec.get("audio_bitrate", "192k"))

    sub_cfg = cfg.get("subtitles") or {}
    burner: SubtitleRenderer | None = None
    if sub_cfg.get("enabled") and root is not None:
        srt = find_lyrics_file(root, song, cfg)
        font = resolve_font(root, sub_cfg.get("font"))
        if srt:
            cues = parse_srt(srt)
            if cues:
                burner = SubtitleRenderer(
                    cues,
                    font,
                    height,
                    size_frac=float(sub_cfg.get("size", 0.052)),
                    margin_frac=float(sub_cfg.get("margin", 0.09)),
                    position=str(sub_cfg.get("position", "bottom")),
                )
                print(f"  subs  {srt.name}  {len(cues)} cues  font={font.name if font else 'default'}")
        else:
            print(f"  subs  on, but no SRT for {song.stem} (run riplens lyrics)")

    feat_track = TrackFeatures(str(song))
    n_frames = int(feat_track.duration * fps)
    state = EffectState()
    state.plates = plates
    effect_idx = 0
    last_switch = -99.0

    cmd = write_cmd(width, height, fps, str(song), dest, encoder, crf, preset, abit)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None

    try:
        for i in tqdm(range(n_frames), desc=dest.name, unit="f"):
            t = i / fps
            feat = feat_track.at(t)
            if feat.rms >= threshold and (t - last_switch) > cooldown:
                effect_idx = (effect_idx + 1) % len(names)
                last_switch = t
                if names[effect_idx] == "lens_peel":
                    state.peel = 0.0

            if names[effect_idx % len(names)] == "lens_peel":
                state.peel = min(1.0, state.peel + 0.018 + feat.rms * 0.01)
                if state.peel >= 1.0:
                    state.plate_index = (state.plate_index + 1) % len(state.plates)
                    state.peel = 0.0

            zoom = 1.0 + ken * feat.rms
            frame = cover(state.plate, width, height, zoom)
            name = names[effect_idx % len(names)]
            fn = REGISTRY[name]
            frame = fn(frame, feat, t, state)
            if solids_on and name not in ("solids", "flower", "metatron", "merkaba"):
                frame = overlay_solids(frame, feat, t)
            if glyphs_on:
                frame = overlay_glyphs(frame, feat, t, solids_on)
            frame = grain(frame, 8.0)
            if burner is not None:
                frame = burner.apply(frame, t)
            if frame.dtype != "uint8":
                frame = frame.clip(0, 255).astype("uint8")
            if frame.shape[1] != width or frame.shape[0] != height:
                import cv2

                frame = cv2.resize(frame, (width, height))
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
        code = proc.wait()
    if code != 0:
        raise RuntimeError(f"ffmpeg exited {code} writing {dest}")


def load_plates(root: Path, cfg: dict) -> list:
    img_dir = root / cfg["sources"]["images"]
    vid_dir = root / cfg["sources"]["videos"]
    plates = [read_image(p) for p in list_images(img_dir)]
    for v in list_videos(vid_dir):
        plates.extend(sample_video_plates(v))
    if not plates:
        raise RuntimeError(
            f"No images in {img_dir}. Drop png/jpg into sources/images and run again."
        )
    return plates


def render_all(
    root: Path,
    cfg_path: Path,
    ratio: str | None = None,
    song: Path | None = None,
    threshold: float | None = None,
    subs: bool | None = None,
) -> list[Path]:
    cfg = load_config(cfg_path)
    if threshold is not None:
        cfg["threshold"] = threshold
    if subs is not None:
        cfg.setdefault("subtitles", {})["enabled"] = bool(subs)
    music_dir = root / cfg["sources"]["music"]
    songs = [song] if song else list_audio(music_dir)
    if not songs:
        raise RuntimeError(f"No audio in {music_dir}. Drop wav/mp3/flac into sources/music.")
    plates = load_plates(root, cfg)
    ratios = cfg["output"]["ratios"]
    order = [ratio] if ratio else ["1x1", "16x9", "9x16"]
    encoder = encoder_name(cfg.get("codec", {}).get("video", "auto"))
    written: list[Path] = []
    out_root = root / cfg["output"]["root"]
    for s in songs:
        for r in order:
            spec = ratios[r]
            w, h = int(spec["width"]), int(spec["height"])
            dest = out_root / r / f"{s.stem}.mp4"
            print(f"→ {r}  {w}x{h}  {s.name}  encoder={encoder}")
            render_song(s, plates, dest, w, h, cfg, encoder, root=root)
            written.append(dest)
    return written
