"""The 22 RipLens looks. OpenCV + NumPy only. No generative models.

When you change a recipe here, update skills/glitch-visualizer/SKILL.md
in the same commit. That file is the copyable pattern.
"""

from __future__ import annotations

from typing import Callable

import cv2
import numpy as np

from riplens.feat import FrameFeat

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
    segments = int(6 + (t * 0.55 + feat.bass * 8) % 11)
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
    sides = 3 + int((t * 0.4 + feat.bass * 3) % 6)
    rot = t * 0.35
    for row in range(rows):
        ox = 0 if row % 2 == 0 else gw / 2
        for col in range(cols):
            x = int(col * gw + ox)
            y = int(row * gh * 0.75 + gh * 0.2)
            hue = (feat.h + col * 18 + row * 8) % 360
            color = hsv_to_bgr(hue, feat.s, feat.v)
            r = int(gw * 0.42 * pulse)
            pts = _ngon(x, y, r, max(3, sides), rot)
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


def _ngon(x: int, y: int, r: int, n: int, rot: float) -> np.ndarray:
    pts = []
    for i in range(max(3, n)):
        a = rot + i * 2 * np.pi / max(3, n)
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
    """Deprecated no-op. The six-spoke wheel was removed."""
    return img


def grain(img: np.ndarray, amount: float = 12.0) -> np.ndarray:
    noise = np.random.default_rng(None).normal(0, amount, img.shape).astype(np.float32)
    return np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)


PHI = (1 + np.sqrt(5)) / 2
INV = 1 / PHI


def _edges(verts: np.ndarray, slack: float = 1.12) -> list[tuple[int, int]]:
    d = np.sqrt(((verts[:, None, :] - verts[None, :, :]) ** 2).sum(-1))
    np.fill_diagonal(d, np.inf)
    m = float(d.min())
    ii, jj = np.where(np.triu(d <= m * slack, 1))
    return list(zip(ii.tolist(), jj.tolist()))


def _mesh(kind: str) -> tuple[np.ndarray, list[tuple[int, int]]]:
    if kind == "tetra":
        v = np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], dtype=np.float32)
        return v, _edges(v, 1.05)
    if kind == "cube":
        v = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], dtype=np.float32)
        return v, _edges(v, 1.05)
    if kind == "octa":
        v = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], dtype=np.float32)
        return v, _edges(v, 1.05)
    if kind == "icosa":
        pts = []
        for s in (-1, 1):
            for t in (-1, 1):
                pts.append([0, s, t * PHI])
                pts.append([s, t * PHI, 0])
                pts.append([t * PHI, 0, s])
        v = np.array(pts, dtype=np.float32)
        return v, _edges(v, 1.08)
    if kind == "dodeca":
        pts = [[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
        for s in (-1, 1):
            for t in (-1, 1):
                pts.append([0, s * INV, t * PHI])
                pts.append([s * INV, t * PHI, 0])
                pts.append([t * PHI, 0, s * INV])
        v = np.array(pts, dtype=np.float32)
        return v, _edges(v, 1.08)
    a, e = _mesh("tetra")
    b = -a
    verts = np.vstack([a, b])
    edges = e + [(i + 4, j + 4) for i, j in e]
    return verts, edges


def _rotate(v: np.ndarray, ax: float, ay: float, az: float) -> np.ndarray:
    cx, sx = np.cos(ax), np.sin(ax)
    cy, sy = np.cos(ay), np.sin(ay)
    cz, sz = np.cos(az), np.sin(az)
    x, y, z = v[:, 0], v[:, 1], v[:, 2]
    y, z = y * cx - z * sx, y * sx + z * cx
    x, z = x * cy + z * sy, -x * sy + z * cy
    x, y = x * cz - y * sz, x * sz + y * cz
    return np.stack([x, y, z], axis=1)


def _project(v: np.ndarray, cx: float, cy: float, radius: float) -> np.ndarray:
    z = v[:, 2] + 3.2
    f = radius / z
    return np.stack([cx + v[:, 0] * f, cy + v[:, 1] * f], axis=1)


def _stroke_solid(
    canvas: np.ndarray, kind: str, cx: float, cy: float, radius: float, ax: float, ay: float, az: float, color: tuple[int, int, int], thick: int
) -> None:
    verts, edges = _mesh(kind)
    pts = _project(_rotate(verts, ax, ay, az), cx, cy, radius)
    for i, j in edges:
        p0 = tuple(np.round(pts[i]).astype(int))
        p1 = tuple(np.round(pts[j]).astype(int))
        cv2.line(canvas, p0, p1, color, thick, cv2.LINE_AA)


def _screen(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    return (255 - cv2.multiply(255 - base, 255 - overlay, scale=1 / 255.0)).astype(np.uint8)


SOLID_CYCLE = ("tetra", "cube", "octa", "icosa", "dodeca", "merkaba")


def vortex(img: np.ndarray, feat: FrameFeat, t: float, st: EffectState) -> np.ndarray:
    h, w = img.shape[:2]
    if st._grid is None or st._grid[0] != h or st._grid[1] != w:
        yy, xx = np.indices((h, w), dtype=np.float32)
        cy, cx = h / 2.0, w / 2.0
        dx, dy = xx - cx, yy - cy
        r = np.sqrt(dx * dx + dy * dy)
        st._grid = (h, w, yy, xx, r, cx, cy)
    _, _, yy, xx, r, cx, cy = st._grid
    rmax = float(np.hypot(cx, cy))
    twist = 1.8 + feat.rms * 3.4
    fall = (1.0 - np.clip(r / rmax, 0, 1)) ** 2
    theta = np.arctan2(yy - cy, xx - cx) + twist * fall + t * 0.25
    map_x = (cx + r * np.cos(theta)).astype(np.float32)
    map_y = (cy + r * np.sin(theta)).astype(np.float32)
    return cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def slice_scramble(img: np.ndarray, feat: FrameFeat, t: float, _st: EffectState) -> np.ndarray:
    h, w = img.shape[:2]
    strip = max(6, int(8 + feat.bass * 28))
    seed = int(t * 2.4)
    out = img.copy()
    for x in range(0, w, strip):
        dw = min(strip, w - x)
        src_x = (x * 13 + seed * 47) % max(1, w - dw)
        sl = img[:, src_x : src_x + dw]
        yoff = int(np.sin(x * 0.03 + t * 5) * h * (0.04 + feat.rms * 0.08))
        out[:, x : x + dw] = np.roll(sl, yoff, axis=0)
    return out


def vhs(img: np.ndarray, feat: FrameFeat, t: float, _st: EffectState) -> np.ndarray:
    h, w = img.shape[:2]
    ox = int(10 + feat.bass * 24)
    b, g, r = cv2.split(img)
    r = np.roll(r, ox, axis=1)
    b = np.roll(b, -ox, axis=1)
    out = cv2.merge([b, g, r])
    tear_y = int((t * 90 % 1.0) * h)
    tear_h = int(6 + feat.treble * 22)
    out[tear_y : tear_y + tear_h] = np.roll(out[tear_y : tear_y + tear_h], ox * 3, axis=1)
    noise = _st_rng_noise(out, 9)
    out = cv2.addWeighted(out, 0.92, noise, 0.08, 0)
    out[::3] = (out[::3] * 0.82).astype(np.uint8)
    return out


def _st_rng_noise(img: np.ndarray, sigma: float) -> np.ndarray:
    n = np.random.default_rng(None).normal(128, sigma, img.shape)
    return np.clip(n, 0, 255).astype(np.uint8)


def wave_warp(img: np.ndarray, feat: FrameFeat, t: float, st: EffectState) -> np.ndarray:
    h, w = img.shape[:2]
    if st._grid is None or st._grid[0] != h or st._grid[1] != w:
        yy, xx = np.indices((h, w), dtype=np.float32)
        cy, cx = h / 2.0, w / 2.0
        r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        st._grid = (h, w, yy, xx, r, cx, cy)
    _, _, yy, xx, *_rest = st._grid
    ax = 10 + feat.rms * 36
    ay = 8 + feat.mid * 28
    map_x = (xx + np.sin(yy * 0.045 + t * 6) * ax).astype(np.float32)
    map_y = (yy + np.cos(xx * 0.035 + t * 4.2) * ay).astype(np.float32)
    return cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def neon_edge(img: np.ndarray, feat: FrameFeat, _t: float, _st: EffectState) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.clip(np.hypot(gx, gy) * (0.8 + feat.rms), 0, 255).astype(np.uint8)
    color = hsv_to_bgr(feat.h, 0.85, 1.0)
    tint = np.full_like(img, color)
    mag3 = cv2.merge([mag, mag, mag])
    glow = cv2.multiply(tint, mag3, scale=1 / 255.0)
    return _screen(img, glow)


def fisheye(img: np.ndarray, feat: FrameFeat, _t: float, st: EffectState) -> np.ndarray:
    h, w = img.shape[:2]
    if st._grid is None or st._grid[0] != h or st._grid[1] != w:
        yy, xx = np.indices((h, w), dtype=np.float32)
        cy, cx = h / 2.0, w / 2.0
        r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        st._grid = (h, w, yy, xx, r, cx, cy)
    _, _, yy, xx, r, cx, cy = st._grid
    rmax = float(np.hypot(cx, cy))
    k = 0.55 + feat.bass * 0.85
    rn = r / rmax
    r2 = rmax * (rn + k * rn * rn * rn)
    ang = np.arctan2(yy - cy, xx - cx)
    map_x = (cx + np.cos(ang) * r2).astype(np.float32)
    map_y = (cy + np.sin(ang) * r2).astype(np.float32)
    return cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def zoom_streak(img: np.ndarray, feat: FrameFeat, _t: float, _st: EffectState) -> np.ndarray:
    h, w = img.shape[:2]
    out = img.astype(np.float32)
    acc = out.copy()
    n = 9
    for i in range(1, n + 1):
        s = 1 + i * (0.035 + feat.rms * 0.04)
        nw, nh = int(w * s), int(h * s)
        scaled = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        x = (nw - w) // 2
        y = (nh - h) // 2
        crop = scaled[y : y + h, x : x + w]
        if crop.shape[:2] != (h, w):
            crop = cv2.resize(crop, (w, h))
        acc += crop.astype(np.float32) * (0.08)
    return np.clip(acc, 0, 255).astype(np.uint8)


def mosaic(img: np.ndarray, feat: FrameFeat, _t: float, _st: EffectState) -> np.ndarray:
    h, w = img.shape[:2]
    cell = max(6, int(8 + feat.rms * 36))
    small = cv2.resize(img, (max(4, w // cell), max(4, h // cell)), interpolation=cv2.INTER_LINEAR)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)


def _draw_on_plate(img: np.ndarray, draw) -> np.ndarray:
    out = cv2.convertScaleAbs(img, alpha=0.72, beta=0)
    overlay = np.zeros_like(out)
    draw(overlay)
    halo = cv2.dilate(overlay, np.ones((3, 3), np.uint8))
    dark = np.clip(out.astype(np.int16) - (halo > 0).astype(np.int16) * 70, 0, 255).astype(np.uint8)
    return cv2.add(dark, overlay)


def solids(img: np.ndarray, feat: FrameFeat, t: float, _st: EffectState) -> np.ndarray:
    h, w = img.shape[:2]
    kind = SOLID_CYCLE[int(t * 0.38 + feat.bass * 2) % len(SOLID_CYCLE)]
    color = hsv_to_bgr(feat.h, min(1.0, feat.s + 0.15), 1.0)
    cx, cy = w / 2, h / 2
    R = min(w, h) * (0.28 + feat.v * 0.12)

    def draw(overlay: np.ndarray) -> None:
        _stroke_solid(overlay, kind, cx, cy, R, t * 0.7, t * 0.45, feat.bass, color, 2)
        orbit = min(w, h) * 0.34
        for i in range(3):
            a = t * 0.55 + i * 2 * np.pi / 3
            k = SOLID_CYCLE[(SOLID_CYCLE.index(kind) + i + 1) % len(SOLID_CYCLE)]
            _stroke_solid(
                overlay,
                k,
                cx + np.cos(a) * orbit,
                cy + np.sin(a) * orbit * 0.72,
                R * 0.28,
                t * 1.1 + i,
                t * 0.8,
                i,
                color,
                1,
            )

    return _draw_on_plate(img, draw)


def flower(img: np.ndarray, feat: FrameFeat, t: float, _st: EffectState) -> np.ndarray:
    h, w = img.shape[:2]
    color = hsv_to_bgr(feat.h, min(1.0, feat.s + 0.1), 1.0)
    cx, cy = w // 2, h // 2
    R = int(min(w, h) * (0.11 + feat.v * 0.04))
    centers = [(cx, cy)]
    for ring, n, off in ((1, 6, 0.0), (2, 12, np.pi / 12)):
        for i in range(n):
            a = off + i * 2 * np.pi / n
            centers.append((int(cx + np.cos(a) * ring * R), int(cy + np.sin(a) * ring * R)))

    def draw(overlay: np.ndarray) -> None:
        for x, y in centers:
            cv2.circle(overlay, (x, y), R, color, 2, cv2.LINE_AA)
        M = cv2.getRotationMatrix2D((cx, cy), np.degrees(t * 0.08), 1.0)
        rotated = cv2.warpAffine(overlay, M, (w, h), borderMode=cv2.BORDER_CONSTANT)
        overlay[:, :] = rotated

    return _draw_on_plate(img, draw)


def metatron(img: np.ndarray, feat: FrameFeat, t: float, _st: EffectState) -> np.ndarray:
    h, w = img.shape[:2]
    color = hsv_to_bgr(feat.h, min(1.0, feat.s + 0.1), 1.0)
    cx, cy = w / 2, h / 2
    R = min(w, h) * (0.12 + feat.rms * 0.03)
    pts = [(cx, cy)]
    for ring in (1, 2):
        for i in range(6):
            a = i * np.pi / 3
            pts.append((cx + np.cos(a) * ring * R, cy + np.sin(a) * ring * R))

    def draw(overlay: np.ndarray) -> None:
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                p0 = (int(pts[i][0]), int(pts[i][1]))
                p1 = (int(pts[j][0]), int(pts[j][1]))
                cv2.line(overlay, p0, p1, color, 1, cv2.LINE_AA)
        for x, y in pts:
            cv2.circle(overlay, (int(x), int(y)), int(R * 0.18), color, 1, cv2.LINE_AA)
        M = cv2.getRotationMatrix2D((w / 2, h / 2), np.degrees(t * 0.12), 1.0)
        overlay[:, :] = cv2.warpAffine(overlay, M, (w, h), borderMode=cv2.BORDER_CONSTANT)

    return _draw_on_plate(img, draw)


def merkaba(img: np.ndarray, feat: FrameFeat, t: float, _st: EffectState) -> np.ndarray:
    h, w = img.shape[:2]
    color = hsv_to_bgr(feat.h, min(1.0, feat.s + 0.15), 1.0)
    cx, cy = w / 2, h / 2
    R = min(w, h) * (0.34 + feat.v * 0.1)

    def draw(overlay: np.ndarray) -> None:
        _stroke_solid(overlay, "merkaba", cx, cy, R, t * 0.55, t * 0.8, t * 0.2, color, 2)
        _stroke_solid(overlay, "cube", cx, cy, R * 0.42, t * 0.3, -t * 0.4, 0, color, 1)

    return _draw_on_plate(img, draw)


def rgb_prism(img: np.ndarray, feat: FrameFeat, t: float, _st: EffectState) -> np.ndarray:
    b, g, r = cv2.split(img)
    lum = 0.299 * r.astype(np.float32) + 0.587 * g.astype(np.float32) + 0.114 * b.astype(np.float32)
    red = np.clip(r.astype(np.float32) * 0.35 + lum * 0.75, 0, 255).astype(np.uint8)
    green = np.clip(g.astype(np.float32) * 0.35 + lum * 0.75, 0, 255).astype(np.uint8)
    cyan_g = np.clip(g.astype(np.float32) * 0.25 + lum * 0.55, 0, 255).astype(np.uint8)
    cyan_b = np.clip(b.astype(np.float32) * 0.45 + lum * 0.7, 0, 255).astype(np.uint8)
    z = np.zeros_like(r)
    ox_r = int(10 + np.sin(t * 1.73) * 9 + feat.bass * 24)
    oy_r = int(np.sin(t * 1.11) * 4)
    ox_c = int(-(10 + np.sin(t * 1.31 + 1.1) * 9 + feat.treble * 24))
    oy_c = int(np.cos(t * 0.97) * 4)
    ox_g = int(np.sin(t * 0.83) * (3 + feat.mid * 8))
    oy_g = int(np.sin(t * 2.07) * (5 + feat.mid * 12))

    def shift(ch: np.ndarray, ox: int, oy: int) -> np.ndarray:
        return np.roll(np.roll(ch, ox, axis=1), oy, axis=0)

    red_img = cv2.merge([z, z, shift(red, ox_r, oy_r)])
    grn_img = cv2.merge([z, shift(green, ox_g, oy_g), z])
    cyn_img = cv2.merge([shift(cyan_b, ox_c, oy_c), shift(cyan_g, ox_c, oy_c), z])
    return np.clip(red_img.astype(np.int16) + grn_img.astype(np.int16) + cyn_img.astype(np.int16), 0, 255).astype(np.uint8)


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
    "vortex": vortex,
    "slice_scramble": slice_scramble,
    "vhs": vhs,
    "wave_warp": wave_warp,
    "neon_edge": neon_edge,
    "fisheye": fisheye,
    "zoom_streak": zoom_streak,
    "mosaic": mosaic,
    "solids": solids,
    "flower": flower,
    "metatron": metatron,
    "merkaba": merkaba,
    "rgb_prism": rgb_prism,
}
