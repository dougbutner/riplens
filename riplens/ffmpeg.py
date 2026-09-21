"""Pick a YouTube-safe H.264 encoder. Prefer NVENC when the GPU is present."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

def _has_libx264(ff: str) -> bool:
    try:
        out = subprocess.check_output(
            [ff, "-hide_banner", "-encoders"],
            stderr=subprocess.STDOUT,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False
    return "libx264" in out


def ffmpeg_bin() -> str:
    candidates: list[str] = []
    found = shutil.which("ffmpeg")
    if found:
        candidates.append(found)
    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled:
            candidates.append(bundled)
    except Exception:
        pass
    for ff in candidates:
        if _has_libx264(ff):
            return ff
    if candidates:
        return candidates[0]
    raise RuntimeError("ffmpeg not found")


def encoder_name(preference: str = "auto") -> str:
    if preference and preference != "auto":
        return preference
    ff = ffmpeg_bin()
    try:
        out = subprocess.check_output(
            [ff, "-hide_banner", "-encoders"],
            stderr=subprocess.STDOUT,
            text=True,
        )
    except subprocess.CalledProcessError:
        return "libx264"
    if "h264_nvenc" in out and shutil.which("nvidia-smi"):
        try:
            subprocess.check_output(["nvidia-smi", "-L"], stderr=subprocess.DEVNULL)
            return "h264_nvenc"
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    return "libx264"


def write_cmd(
    width: int,
    height: int,
    fps: int,
    audio_path: str,
    dest: Path,
    encoder: str,
    crf: int,
    preset: str,
    audio_bitrate: str,
) -> list[str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_bin()
    video = [
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
        "-i",
        audio_path,
    ]
    if encoder == "h264_nvenc":
        vcodec = [
            "-c:v",
            "h264_nvenc",
            "-preset",
            "p4",
            "-cq",
            str(max(15, crf)),
            "-b:v",
            "0",
            "-pix_fmt",
            "yuv420p",
        ]
    else:
        vcodec = [
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
        ]
    audio = ["-c:a", "aac", "-b:a", audio_bitrate, "-ac", "2"]
    tail = [
        "-shortest",
        "-movflags",
        "+faststart",
        "-y",
        str(dest),
    ]
    return [ff, "-hide_banner", "-loglevel", "error", *video, *vcodec, *audio, *tail]
