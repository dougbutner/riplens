---
name: glitch-visualizer
description: >
  Copyable recipes for RipLens looks — kaleidoscope, chromatic split, scanline
  tear, pixel sort, block corrupt, Julia fractal, HSV hex geometry, blend-mode
  rotate, lens peel, feedback trail. Audio-reactive HSV (centroid / mid / RMS).
  Threshold-cycled effect stack. Local OpenCV + librosa + FFmpeg only; no
  generative AI. Use when adding or editing a glitch look, mapping HSV to
  geometry, or rendering 1x1 / 16x9 / 9x16 music videos from still art.
---

# RipLens glitch visualizer

Canonical implementation: `riplens/effects.py`, `riplens/audio.py`.
If those files change, this skill changes in the **same commit** (`AGENTS.md`).

## Non-negotiables

- Local pixels only. OpenCV, NumPy, librosa, FFmpeg.
- Art is **cover-cropped**, never stretched.
- HSV geometry rides on **every** frame.
- Looks advance on a **rising RMS edge** above `threshold` (default `0.62`) after `cooldown` (default `1.2s`).
- Outputs: `1080×1080`, `1920×1080`, `1080×1920`, H.264 `yuv420p` + AAC, `+faststart`.

## HSV map

From `TrackFeatures.at(t)`:

```
h = (centroid * 360 + bass * 80) % 360
s = 0.35 + mid * 0.65
v = 0.28 + rms * 0.72
```

| Channel | Source | Range |
|---|---|---|
| H | spectral centroid + bass offset | 0–360 |
| S | mid band (150–2000 Hz) | 0.35–1.0 |
| V | RMS (waveform height) | 0.28–1.0 |

Bands (librosa STFT, n_fft 2048): bass 20–150, mid 150–2000, treble 2000–8000. Each band and RMS is divided by its 95th percentile, clipped 0–1.

OpenCV HSV hue is `h/2` (0–180). Helper: `hsv_to_bgr(h, s, v)`.

## Threshold cycle

```
if rms >= threshold and (t - last_switch) > cooldown:
    effect_idx = (effect_idx + 1) % 10
    last_switch = t
```

Order (`EFFECT_ORDER`):

1. kaleidoscope
2. chromatic
3. scanline
4. pixel_sort
5. block_corrupt
6. fractal
7. hsv_geometry
8. blend
9. lens_peel
10. feedback

## Look recipes

### 1. Kaleidoscope

Polar fold. Cache `xx, yy, r` per resolution.

```
segments = 6 + round(bass * 10)   # 6–16
theta = atan2(dy, dx) + t * (0.12 + rms * 0.4)
slice = 2π / segments
folded = abs((theta mod 2*slice) - slice)
map_x = cx + r * cos(folded)
map_y = cy + r * sin(folded)
cv2.remap(..., BORDER_REFLECT)
```

### 2. Chromatic split

```
offset = 8 + bass * 28
R ← roll(R, +offset, x)
B ← roll(B, -offset, x)
G stays
then hue-rotate HSV[:,0] += h * 0.2; sat *= 1 + s * 0.4
```

### 3. Scanline tear

Per row `y`:

```
amp = 12 + rms * 48
shift = sin(y * 0.08 + t * 9) * amp     # if that sine > 0.55
      else sin(y * 0.4) * 2
row = img[y, (x + shift) % w]
every band = 6 + treble * 18 rows: subtract 28 (CRT)
```

### 4. Pixel sort (Asendorf)

Gray luminance. Threshold `90 + mid * 80`. On each row (stride 2, or 1 if rms > 0.7), find contiguous runs where `gray > thresh` and length ≥ 8. Sort pixels in the run by mean BGR.

### 5. Block corrupt

`n = 8 + rms * 18` copies. Block `bw = 16+bass*48`, `bh = 10+treble*36`. Random source → dest. If `rms > 0.8`, invert a random horizontal strip and mix 45%.

### 6. Fractal overlay

Julia set, 160×160 then scale. `c = (-0.4 + bass*0.5) + i(0.6 - mid*0.7)`. 22 iterations. Color HSV hue = `h/2 + esc*40`. Composite with **screen**, alpha `0.35 + rms*0.4`. Cache on rounded `(cx, cy, h)`.

### 7. HSV geometry

Hex grid 7×8-ish, odd rows shifted `gw/2`. Cell hue `h + col*18 + row*8`. Radius `gw * 0.42 * (0.35 + v*0.7)`. Overlay 45%. Stroke a waveform `y = h/2 + sin(x*0.02 + t*4)*amp + sin(x*0.05 + t*7)*amp*0.4` with `amp = h * 0.08 * v`.

### 8. Blend rotate

Tint a copy by adding `h/2` to HSV hue. Mode index `int(t*0.35 + rms*3) % 5`:

| mode | op |
|---|---|
| overlay | 50/50 + luma mask |
| difference | `absdiff` |
| screen | `255 - (255-a)*(255-b)/255` |
| multiply | `a*b/255` |
| color_dodge | `a / (255-b) * 255` |

Wash 22% with solid `hsv_to_bgr(h,s,v)`.

### 9. Lens peel

Progress `peel` 0→1 while this look is active (`+= 0.018 + rms*0.01`). Next plate on paper-white `(230,239,243)`. Jagged mask:

```
y_rip = h * (1 - p)
jag[x] = sin(x * 0.18 + t * 9) * 16 * min(1, p*3)
mask[y < y_rip + jag[x]] = keep current
```

Affine pull: scale `1 + p*0.12`, translate y `-p * h * 0.18`, brighten `alpha = 1 + p*0.8`. Flash `sin(p * π)` toward paper. When `p >= 1`, `plate_index += 1`.

### 10. Feedback trail

Keep last frame. `getRotationMatrix2D(center, 0.5 + bass*1.2, 1.03 + rms*0.02)`, warp, `addWeighted(ghost 0.86, live 0.55)`, wash 18% HSV.

## Always-on overlay

After the look, `geometry_overlay`: circle radius `min(w,h) * (0.18 + v*0.22)` at center, 6 spokes rotating `t * 0.2`, color `hsv_to_bgr(h, s+0.1, 1)`. Then grain σ ≈ 8.

## Cover crop

```
scale = max(W/iw, H/ih) * (1 + ken_burns * rms)   # ken_burns default 0.08
center crop
```

## Encoder

```
ffmpeg -f rawvideo -pix_fmt bgr24 -s WxH -r 30 -i pipe:0 -i song \
  -c:v libx264|h264_nvenc -pix_fmt yuv420p -c:a aac -b:a 192k \
  -shortest -movflags +faststart out.mp4
```

NVENC when `ffmpeg -encoders` lists `h264_nvenc` **and** `nvidia-smi -L` succeeds.

## Copying into another project

1. Keep `EFFECT_ORDER` and this file identical.
2. Port a look by translating the recipe above, not by calling an API.
3. Drive H/S/V from centroid / mid / RMS even if you swap the picture source.
4. Threshold-cycle; do not randomize look order unless the user asks.
5. When you invent a look, append (do not insert) and document it here.
