"""Folder layout: sources/{music,images,videos} → output/{1x1,16x9,9x16}."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import yaml

AUDIO_EXT = {".wav", ".mp3", ".flac", ".aiff", ".aif", ".ogg", ".m4a"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


def load_config(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def list_audio(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXT)


def list_images(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXT)


def list_videos(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXT)


def read_image(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"Could not read image: {path}")
    return img


def sample_video_plates(path: Path, every_s: float = 4.0, cap_n: int = 12) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, int(fps * every_s))
    plates: list[np.ndarray] = []
    for i in range(0, n, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = cap.read()
        if ok and frame is not None:
            plates.append(frame)
        if len(plates) >= cap_n:
            break
    cap.release()
    return plates


def ensure_layout(root: Path) -> None:
    for p in [
        root / "sources" / "music",
        root / "sources" / "images",
        root / "sources" / "videos",
        root / "output" / "1x1",
        root / "output" / "16x9",
        root / "output" / "9x16",
    ]:
        p.mkdir(parents=True, exist_ok=True)
        keep = p / ".gitkeep"
        if not keep.exists():
            keep.write_text("")
