"""The ten RipLens looks. OpenCV + NumPy only. No generative models.

When you change a recipe here, update skills/glitch-visualizer/SKILL.md
in the same commit. That file is the copyable pattern.
"""

from __future__ import annotations

from typing import Callable

import cv2
import numpy as np

from riplens.audio import FrameFeat

BlendFn = Callable[[np.ndarray, FrameFeat, float, "EffectState"], np.ndarray]


class EffectState:
    def __init__(self) -> None:
        self.feedback: np.ndarray | None = None
        self.plates: list[np.ndarray] = []
        self.plate_index = 0
        self.peel = 0.0
        self.rng = np.random.default_rng(7)
        self._julia: np.ndarray | None = None
        self._julia_key: tuple | None = None
        self._grid: tuple | None = None

    @property
    def plate(self) -> np.ndarray:
        return self.plates[self.plate_index % len(self.plates)]

    @property
    def next_plate(self) -> np.ndarray:
        return self.plates[(self.plate_index + 1) % len(self.plates)]


def hsv_to_bgr(h: float, s: float, v: float) -> tuple[int, int, int]:
    hsv = np.uint8([[[int(h / 2) % 180, int(s * 255), int(v * 255)]]])
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0]
    return int(bgr[0]), int(bgr[1]), int(bgr[2])


def cover(img: np.ndarray, w: int, h: int, zoom: float = 1.0) -> np.ndarray:
    ih, iw = img.shape[:2]
    scale = max(w / iw, h / ih) * zoom
    nw, nh = max(w, int(iw * scale)), max(h, int(ih * scale))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    x = max(0, (nw - w) // 2)
    y = max(0, (nh - h) // 2)
    crop = resized[y : y + h, x : x + w]
    if crop.shape[0] != h or crop.shape[1] != w:
        crop = cv2.resize(crop, (w, h), interpolation=cv2.INTER_LINEAR)
    return crop


def kaleidoscope(img: np.ndarray, feat: FrameFeat, t: float, st: EffectState) -> np.ndarray:
    h, w = img.shape[:2]
    segments = int(6 + feat.bass * 10)
    segments = max(4, segments)
    if st._grid is None or st._grid[0] != h or st._grid[1] != w:
        yy, xx = np.indices((h, w), dtype=np.float32)
        cy, cx = h / 2.0, w / 2.0
        dx, dy = xx - cx, yy - cy
        r = np.sqrt(dx * dx + dy * dy)
        st._grid = (h, w, yy, xx, r, cx, cy)
    _, _, yy, xx, r, cx, cy = st._grid
    theta = np.arctan2(yy - cy, xx - cx) + t * (0.12 + feat.rms * 0.4)
    slice_ang = (2 * np.pi) / segments
    folded = np.abs(np.mod(theta, slice_ang * 2.0) - slice_ang)
    map_x = (cx + r * np.cos(folded)).astype(np.float32)
    map_y = (cy + r * np.sin(folded)).astype(np.float32)
    return cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def chromatic(img: np.ndarray, feat: FrameFeat, _t: float, _st: EffectState) -> np.ndarray:
    offset = int(8 + feat.bass * 28)
    b, g, r = cv2.split(img)
    r = np.roll(r, offset, axis=1)
    b = np.roll(b, -offset, axis=1)
    out = cv2.merge([b, g, r])
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 0] = (hsv[:, :, 0] + feat.h * 0.2) % 180
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * (1.0 + feat.s * 0.4), 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def scanline(img: np.ndarray, feat: FrameFeat, t: float, _st: EffectState) -> np.ndarray:
    h, w = img.shape[:2]
    amp = 12 + feat.rms * 48
    ys = np.arange(h, dtype=np.float32)
    shifts = (np.sin(ys * 0.08 + t * 9.0) * amp).astype(np.int32)
    tears = np.sin(ys * 0.08 + t * 9.0) > 0.55
    shifts = np.where(tears, shifts, (np.sin(ys * 0.4) * 2).astype(np.int32))
    out = np.empty_like(img)
    xs = np.arange(w)
    for y in range(h):
        out[y] = img[y, (xs + int(shifts[y])) % w]
    band = int(6 + feat.treble * 18)
    out[::band] = (out[::band].astype(np.int16) - 28).clip(0, 255).astype(np.uint8)
    return out


def pixel_sort(img: np.ndarray, feat: FrameFeat, _t: float, _st: EffectState) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = 90 + feat.mid * 80
    out = img.copy()
    h, w = gray.shape
    step = 1 if feat.rms > 0.7 else 2
    for y in range(0, h, step):
        row = gray[y]
        mask = row > thresh
        if not np.any(mask):
            continue
        padded = np.concatenate([[False], mask, [False]])
        diff = np.diff(padded.astype(np.int8))
        starts = np.where(diff == 1)[0]
        ends = np.where(diff == -1)[0]
        for a, b in zip(starts, ends):
            if b - a < 8:
                continue
            sl = out[y, a:b]
            order = np.argsort(sl.mean(axis=1))
            out[y, a:b] = sl[order]
    return out


def block_corrupt(img: np.ndarray, feat: FrameFeat, _t: float, st: EffectState) -> np.ndarray:
    out = img.copy()
    h, w = img.shape[:2]
    n = int(8 + feat.rms * 18)
    bw = int(16 + feat.bass * 48)
    bh = int(10 + feat.treble * 36)
    for _ in range(n):
        sx = int(st.rng.integers(0, max(1, w - bw)))
        sy = int(st.rng.integers(0, max(1, h - bh)))
        dx = int(st.rng.integers(0, max(1, w - bw)))
        dy = int(st.rng.integers(0, max(1, h - bh)))
        out[dy : dy + bh, dx : dx + bw] = img[sy : sy + bh, sx : sx + bw]
    if feat.rms > 0.8:
        y = int(st.rng.integers(0, h))
        hh = int(8 + feat.rms * 24)
        y2 = min(h, y + hh)
        inv = cv2.bitwise_not(out[y:y2])
        out[y:y2] = cv2.addWeighted(out[y:y2], 0.55, inv, 0.45, 0)
    return out


def _julia(w: int, h: int, cx: float, cy: float, hue: float) -> np.ndarray:
    xs = np.linspace(-1.5, 1.5, w, dtype=np.float32)
    ys = np.linspace(-1.5, 1.5, h, dtype=np.float32)
    zr, zi = np.meshgrid(xs, ys)
    zx, zy = zr.copy(), zi.copy()
    esc = np.zeros((h, w), dtype=np.float32)
    live = np.ones((h, w), dtype=bool)
    max_iter = 22
    for i in range(max_iter):
        if not live.any():
            break
        xr = zx[live]
        yi = zy[live]
        nx = xr * xr - yi * yi + cx
        ny = 2.0 * xr * yi + cy
        zx[live] = nx
        zy[live] = ny
        escaped = (zx * zx + zy * zy) > 4
        newly = escaped & live
        esc[newly] = i / max_iter
        live &= ~escaped
    esc[live] = 1.0
    hsv = np.zeros((h, w, 3), dtype=np.uint8)
    hsv[:, :, 0] = ((hue / 2) + esc * 40).astype(np.uint8) % 180
    hsv[:, :, 1] = 140
    hsv[:, :, 2] = (esc * 255).astype(np.uint8)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def fractal(img: np.ndarray, feat: FrameFeat, _t: float, st: EffectState) -> np.ndarray:
    cx = -0.4 + feat.bass * 0.5
    cy = 0.6 - feat.mid * 0.7
    key = (round(cx, 2), round(cy, 2), int(feat.h))
    if st._julia is None or st._julia_key != key:
        st._julia = _julia(160, 160, cx, cy, feat.h)
        st._julia_key = key
    layer = cv2.resize(st._julia, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_LINEAR)
    screen = 255 - cv2.multiply(255 - img, 255 - layer, scale=1 / 255.0)
    alpha = 0.35 + feat.rms * 0.4
    return cv2.addWeighted(img, 1 - alpha * 0.5, screen, alpha * 0.5, 0)


def hsv_geometry(img: np.ndarray, feat: FrameFeat, t: float, _st: EffectState) -> np.ndarray:
    out = img.copy()
    h, w = img.shape[:2]
    overlay = np.zeros_like(out)
    cols, rows = 7, 9
    gw, gh = w / cols, h / rows
    pulse = 0.35 + feat.v * 0.7
    for row in range(rows):
        ox = 0 if row % 2 == 0 else gw / 2
        for col in range(cols):
            x = int(col * gw + ox)
            y = int(row * gh * 0.75 + gh * 0.2)
            hue = (feat.h + col * 18 + row * 8) % 360
            color = hsv_to_bgr(hue, feat.s, feat.v)
            r = int(gw * 0.42 * pulse)
            pts = _hex(x, y, r)
            cv2.fillConvexPoly(overlay, pts, color)
            cv2.polylines(overlay, [pts], True, (240, 235, 220), 1, cv2.LINE_AA)
    mixed = cv2.addWeighted(out, 0.7, overlay, 0.45, 0)
    amp = int(h * 0.08 * feat.v)
    xs = np.linspace(0, w - 1, w).astype(np.int32)
    ys = (h * 0.5 + np.sin(xs * 0.02 + t * 4) * amp + np.sin(xs * 0.05 + t * 7) * amp * 0.4).astype(
        np.int32
    )
    pts = np.stack([xs, np.clip(ys, 0, h - 1)], axis=1).reshape(-1, 1, 2)
    cv2.polylines(mixed, [pts], False, hsv_to_bgr(feat.h, feat.s, 1.0), 2, cv2.LINE_AA)
    return mixed


def _hex(x: int, y: int, r: int) -> np.ndarray:
    pts = []
    for i in range(6):
        a = i * np.pi / 3
        pts.append([int(x + r * np.cos(a)), int(y + r * np.sin(a))])
    return np.array(pts, dtype=np.int32)


BLEND_MODES = ("overlay", "difference", "screen", "multiply", "color_dodge")


def blend(img: np.ndarray, feat: FrameFeat, t: float, _st: EffectState) -> np.ndarray:
    mode = BLEND_MODES[int(t * 0.35 + feat.rms * 3) % len(BLEND_MODES)]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 0] = (hsv[:, :, 0] + feat.h / 2) % 180
    tinted = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)
    if mode == "difference":
        mixed = cv2.absdiff(img, tinted)
    elif mode == "screen":
        mixed = 255 - cv2.multiply(255 - img, 255 - tinted, scale=1 / 255.0)
    elif mode == "multiply":
        mixed = cv2.multiply(img, tinted, scale=1 / 255.0)
    elif mode == "color_dodge":
        mixed = cv2.divide(img, np.clip(255 - tinted, 1, 255), scale=255)
    else:
        mixed = cv2.addWeighted(img, 0.5, tinted, 0.5, 0)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mask = gray[:, :, None] / 255.0
        mixed = (img * (1 - mask) + mixed * mask).astype(np.uint8)
    wash = np.full_like(img, hsv_to_bgr(feat.h, feat.s, feat.v))
    return cv2.addWeighted(mixed, 0.78, wash, 0.22, 0)


def lens_peel(img: np.ndarray, feat: FrameFeat, t: float, st: EffectState) -> np.ndarray:
    h, w = img.shape[:2]
    p = st.peel if st.peel > 0 else 0.45 + 0.25 * np.sin(t * 1.4)
    p = float(np.clip(p, 0.0, 1.0))
    nxt = cover(st.next_plate, w, h, 1.02)
    paper = np.full_like(img, (230, 239, 243))
    base = cv2.addWeighted(paper, 0.15, nxt, 0.85, 0)
    y_rip = int(h * (1.0 - p))
    xs = np.arange(w)
    jag = (np.sin(xs * 0.18 + t * 9) * 16 * min(1.0, p * 3)).astype(np.int32)
    mask = np.zeros((h, w), dtype=np.uint8)
    for x in range(w):
        y2 = int(np.clip(y_rip + jag[x], 0, h))
        mask[:y2, x] = 255
    M = np.float32([[1 + p * 0.12, 0, 0], [0, 1 + p * 0.12, -p * h * 0.18]])
    pulled = cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_CONSTANT, borderValue=(243, 239, 230))
    pulled = cv2.convertScaleAbs(pulled, alpha=1 + p * 0.8, beta=p * 40)
    out = base.copy()
    m3 = mask[:, :, None] / 255.0
    out = (pulled * m3 + out * (1 - m3)).astype(np.uint8)
    flash = float(np.sin(p * np.pi))
    if flash > 0.05:
        white = np.full_like(out, (230, 239, 243))
        out = cv2.addWeighted(out, 1 - flash * 0.55, white, flash * 0.55, 0)
    return out


def feedback(img: np.ndarray, feat: FrameFeat, _t: float, st: EffectState) -> np.ndarray:
    h, w = img.shape[:2]
    if st.feedback is None or st.feedback.shape[:2] != (h, w):
        st.feedback = img.copy()
    scale = 1.03 + feat.rms * 0.02
    M = cv2.getRotationMatrix2D((w / 2, h / 2), 0.5 + feat.bass * 1.2, scale)
    ghost = cv2.warpAffine(st.feedback, M, (w, h), borderMode=cv2.BORDER_REFLECT)
    out = cv2.addWeighted(ghost, 0.86, img, 0.55, 0)
    wash = np.full_like(out, hsv_to_bgr(feat.h, feat.s, feat.v))
    out = cv2.addWeighted(out, 0.82, wash, 0.18, 0)
    st.feedback = out
    return out


def geometry_overlay(img: np.ndarray, feat: FrameFeat, t: float) -> np.ndarray:
    out = img.copy()
    h, w = img.shape[:2]
    cx, cy = w // 2, h // 2
    r = int(min(w, h) * (0.18 + feat.v * 0.22))
    color = hsv_to_bgr(feat.h, min(1.0, feat.s + 0.1), 1.0)
    cv2.circle(out, (cx, cy), r, color, 1, cv2.LINE_AA)
    for i in range(6):
        a = i / 6 * np.pi * 2 + t * 0.2
        x2 = int(cx + np.cos(a) * r * 1.4)
        y2 = int(cy + np.sin(a) * r * 1.4)
        cv2.line(out, (cx, cy), (x2, y2), color, 1, cv2.LINE_AA)
    return out


def grain(img: np.ndarray, amount: float = 12.0) -> np.ndarray:
    noise = np.random.default_rng(None).normal(0, amount, img.shape).astype(np.float32)
    return np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)


REGISTRY: dict[str, BlendFn] = {
    "kaleidoscope": kaleidoscope,
    "chromatic": chromatic,
    "scanline": scanline,
    "pixel_sort": pixel_sort,
    "block_corrupt": block_corrupt,
    "fractal": fractal,
    "hsv_geometry": hsv_geometry,
    "blend": blend,
    "lens_peel": lens_peel,
    "feedback": feedback,
}
