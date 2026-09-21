"""Parse editable SRT/VTT and burn captions onto a frame.

White fill + dark outline + dim pill so lyrics survive bright plates
(Olympus, paper-white peels). PIL FreeType, no libass required at render.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

TIME_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")


def parse_time(ts: str) -> float:
    m = TIME_RE.match(ts.strip())
    if not m:
        return 0.0
    h, mn, s, ms = (int(x) for x in m.groups())
    return h * 3600 + mn * 60 + s + ms / 1000.0


def fmt_time(t: float) -> str:
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    mn = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms == 1000:
        s += 1
        ms = 0
    return f"{h:02d}:{mn:02d}:{s:02d},{ms:03d}"


@dataclass
class Cue:
    start: float
    end: float
    text: str


def parse_srt_text(raw: str) -> list[Cue]:
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    if raw.lstrip().upper().startswith("WEBVTT"):
        raw = re.sub(r"^WEBVTT.*?\n", "", raw)
    cues: list[Cue] = []
    blocks = re.split(r"\n\s*\n", raw.strip())
    time_line = re.compile(
        r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})"
    )
    for block in blocks:
        lines = [ln for ln in block.split("\n") if ln.strip() != ""]
        if not lines:
            continue
        idx = 0
        if re.fullmatch(r"\d+", lines[0].strip()):
            idx = 1
        if idx >= len(lines):
            continue
        m = time_line.search(lines[idx])
        if not m:
            continue
        text = "\n".join(lines[idx + 1 :]).strip()
        text = re.sub(r"<[^>]+>", "", text)
        if not text:
            continue
        cues.append(Cue(parse_time(m.group(1)), parse_time(m.group(2)), text))
    return cues


def parse_srt(path: Path) -> list[Cue]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    return parse_srt_text(raw)


def write_srt(cues: list[Cue], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for i, c in enumerate(cues, 1):
        blocks.append(f"{i}\n{fmt_time(c.start)} --> {fmt_time(c.end)}\n{c.text}\n")
    path.write_text("\n".join(blocks) + "\n", encoding="utf-8")


def write_txt(cues: list[Cue], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [c.text.replace("\n", " ") for c in cues]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cue_at(cues: list[Cue], t: float) -> Cue | None:
    for c in cues:
        if c.start <= t < c.end:
            return c
    return None


def resolve_font(root: Path, name: str | None) -> Path | None:
    fonts = root / "fonts"
    if name:
        p = Path(name)
        if p.is_file():
            return p
        for cand in (
            fonts / name,
            fonts / f"{name}.ttf",
            fonts / f"{name}.otf",
        ):
            if cand.is_file():
                return cand
        lowered = name.lower().replace(" ", "")
        if fonts.is_dir():
            for f in fonts.rglob("*"):
                if f.suffix.lower() in {".ttf", ".otf"} and lowered in f.stem.lower().replace(" ", ""):
                    return f
    preferred = [
        "Montserrat-ExtraBold.ttf",
        "Montserrat-Bold.ttf",
        "Satoshi-Bold.ttf",
        "Inter-Bold.ttf",
        "Poppins-Bold.ttf",
        "ClashDisplay-Bold.ttf",
        "GeneralSans-Bold.ttf",
    ]
    for n in preferred:
        p = fonts / n
        if p.is_file():
            return p
        hits = list(fonts.rglob(n)) if fonts.is_dir() else []
        if hits:
            return hits[0]
    if fonts.is_dir():
        any_font = next(fonts.rglob("*.ttf"), None) or next(fonts.rglob("*.otf"), None)
        if any_font:
            return any_font
    for sysf in (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/Library/Fonts/Arial Bold.ttf"),
    ):
        if sysf.is_file():
            return sysf
    return None


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> str:
    paragraphs = [ln.strip() for ln in text.split("\n") if ln.strip()] or [text]
    out: list[str] = []
    for para in paragraphs:
        words = para.split()
        line = ""
        for w in words:
            trial = (line + " " + w).strip()
            if draw.textlength(trial, font=font) <= max_w or not line:
                line = trial
            else:
                out.append(line)
                line = w
        if line:
            out.append(line)
    return "\n".join(out[:3])


class SubtitleRenderer:
    def __init__(
        self,
        cues: list[Cue],
        font_path: Path | None,
        frame_h: int,
        size_frac: float = 0.052,
        margin_frac: float = 0.09,
        position: str = "bottom",
        uppercase: bool = False,
    ) -> None:
        self.cues = cues
        self.position = position
        self.margin_frac = margin_frac
        self.uppercase = uppercase
        self.size = max(18, int(frame_h * size_frac))
        self.stroke = max(3, int(self.size * 0.12))
        self.font: ImageFont.FreeTypeFont | None = None
        if font_path and font_path.is_file():
            try:
                self.font = ImageFont.truetype(str(font_path), self.size)
            except OSError:
                self.font = None
        if self.font is None:
            self.font = ImageFont.load_default()
        self._key: str | None = None
        self._layer: Image.Image | None = None

    def apply(self, frame: np.ndarray, t: float) -> np.ndarray:
        cue = cue_at(self.cues, t)
        if cue is None:
            return frame
        h, w = frame.shape[:2]
        key = cue.text
        if key != self._key or self._layer is None or self._layer.size != (w, h):
            self._layer = self._raster(w, h, cue.text)
            self._key = key
        overlay = np.array(self._layer)
        rgb = overlay[:, :, :3][:, :, ::-1]
        a = overlay[:, :, 3:4].astype(np.float32) / 255.0
        out = frame.astype(np.float32) * (1.0 - a) + rgb.astype(np.float32) * a
        return np.clip(out, 0, 255).astype(np.uint8)

    def _raster(self, w: int, h: int, text: str) -> Image.Image:
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        font = self.font
        max_w = int(w * 0.86)
        wrapped = _wrap(draw, text.upper() if self.uppercase else text, font, max_w)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, align="center", spacing=int(self.size * 0.18))
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad_x = int(self.size * 0.55)
        pad_y = int(self.size * 0.32)
        if self.position == "top":
            y = int(h * self.margin_frac)
        elif self.position == "center":
            y = (h - th) // 2
        else:
            y = h - int(h * self.margin_frac) - th
        x = (w - tw) // 2
        pill = [
            x - pad_x,
            y - pad_y,
            x + tw + pad_x,
            y + th + pad_y,
        ]
        pill_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        pdraw = ImageDraw.Draw(pill_layer)
        pdraw.rounded_rectangle(pill, radius=int(self.size * 0.35), fill=(8, 7, 6, 150))
        pill_layer = pill_layer.filter(ImageFilter.GaussianBlur(radius=1.2))
        img = Image.alpha_composite(img, pill_layer)
        draw = ImageDraw.Draw(img)
        draw.multiline_text(
            (x, y),
            wrapped,
            font=font,
            fill=(255, 252, 245, 255),
            align="center",
            spacing=int(self.size * 0.18),
            stroke_width=self.stroke,
            stroke_fill=(12, 10, 8, 230),
        )
        return img


def find_lyrics_file(root: Path, song: Path, cfg: dict | None = None) -> Path | None:
    subs = (cfg or {}).get("subtitles") or {}
    explicit = subs.get("file") or subs.get("path")
    if explicit and explicit not in ("auto", True, False):
        p = Path(explicit)
        if not p.is_absolute():
            p = root / p
        if p.is_file():
            return p
    stem = song.stem
    for folder in (root / "sources" / "lyrics", song.parent, root / "sources" / "music"):
        for ext in (".srt", ".vtt"):
            p = folder / f"{stem}{ext}"
            if p.is_file():
                return p
    return None
