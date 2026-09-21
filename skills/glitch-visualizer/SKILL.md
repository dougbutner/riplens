---
name: glitch-visualizer
description: >
  Copyable recipes for RipLens looks — kaleidoscope, chromatic split, scanline
  tear, pixel sort, block corrupt, Julia fractal, HSV n-gon lattice, blend-mode
  rotate, lens peel, feedback trail, vortex, slice scramble, VHS, wave warp,
  neon edge, fisheye, zoom streak, mosaic, platonic solids, Flower of Life,
  Metatron, Merkaba, RGB prism. Independent neon overlay layers: glyphs (runes
  + civilization marks) and platonic solids. Audio-reactive HSV. Local OpenCV
  + librosa + FFmpeg only.
---

# RipLens glitch visualizer

Canonical implementation: `riplens/effects.py`, `riplens/audio.py`.
If those files change, this skill changes in the **same commit** (`AGENTS.md`).

## Non-negotiables

- Local pixels only. OpenCV, NumPy, librosa, FFmpeg.
- Art is **cover-cropped**, never stretched.
- Looks advance on a **rising RMS edge** above `threshold` (default `0.62`) after `cooldown` (default `1.2s`).
- **No persistent hex wheel.** Sacred-geometry looks (19–22) are stroke-only wireframes, dim-plate + dual-stroke halo.
- **Two overlay layers**, independent toggles, both may be on: `glyphs` (default on) and `solids` (default off).
- **Captions are a third overlay**, off by default in the CLI (`subtitles.enabled: false`). Burn only when `riplens render --subs` or config enables them. Never a look in `EFFECT_ORDER`.
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
    effect_idx = (effect_idx + 1) % len(EFFECT_ORDER)
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
11. vortex
12. slice_scramble
13. vhs
14. wave_warp
15. neon_edge
16. fisheye
17. zoom_streak
18. mosaic
19. solids
20. flower
21. metatron
22. merkaba
23. rgb_prism

## Look recipes

### 1. Kaleidoscope

Polar fold. Cache `xx, yy, r` per resolution.

```
segments = 6 + round((t * 0.55 + bass * 8) % 11)   # 6–16, wanders with time
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

Hex-or-n-gon grid 7×9, odd rows shifted `gw/2`. **Sides** `3 + floor((t*0.4 + bass*3) % 6)` so the lattice is triangles through octagons, never stuck on hex. Cell hue `h + col*18 + row*8`. Radius `gw * 0.42 * (0.35 + v*0.7)`. Overlay 45%. Stroke a waveform `y = h/2 + sin(x*0.02 + t*4)*amp + sin(x*0.05 + t*7)*amp*0.4` with `amp = h * 0.08 * v`.

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

### 11. Vortex

Polar swirl. Cache `xx, yy, r`.

```
twist = 1.8 + rms * 3.4
fall = (1 - clip(r/rmax, 0, 1))^2
theta = atan2(dy, dx) + twist * fall + t * 0.25
map = (cx + r*cos(theta), cy + r*sin(theta))
cv2.remap BORDER_REFLECT
```

### 12. Slice scramble

Vertical strips `width = 8 + bass*28`. Source x `(x*13 + floor(t*2.4)*47) % (w-strip)`. Y offset `sin(x*0.03 + t*5) * h * (0.04 + rms*0.08)`.

### 13. VHS tracking

RGB roll `ox = 10 + bass*24`. Tracking band at `y = (t*90 % 1)*h`, height `6 + treble*22`, extra roll `ox*3`. 8% gaussian noise. Every 3rd row × 0.82.

### 14. Wave warp

```
map_x = x + sin(y*0.045 + t*6) * (10 + rms*36)
map_y = y + cos(x*0.035 + t*4.2) * (8 + mid*28)
remap BORDER_REFLECT
```

### 15. Neon edge

Sobel magnitude on luma × `(0.8+rms)`, tint `hsv_to_bgr(h, 0.85, 1)`, **screen** onto the plate.

### 16. Fisheye

```
k = 0.55 + bass*0.85
rn = r / rmax
r2 = rmax * (rn + k * rn^3)
```

### 17. Zoom streak

9 copies, scale `1 + i*(0.035 + rms*0.04)`, add 0.08 each (canvas: `lighter`).

### 18. Mosaic

`cell = 8 + rms*36`. Downscale then `INTER_NEAREST` back.

### 19. Platonic solids (wireframe)

Stroke only, **screen** composite, no fill. Cycle `tetra, cube, octa, icosa, dodeca, merkaba` by `floor(t*0.38 + bass*2)`. One large solid at center, three smaller on an ellipse. Rotate `ax=t*0.7, ay=t*0.45`. Perspective `z+3.2`.

Vertices: tetra `(±1,±1,±1)` subset; cube all `(±1,±1,±1)`; octa axis units; icosa cyclic `(0,±1,±φ)`; dodeca cube + even perms `(0, ±1/φ, ±φ)`; merkaba = tetra + inverted tetra.

### 20. Flower of Life

19 circles: center + 6 at `R` + 12 at `2R` offset 15°. `R = min(w,h)*(0.11 + v*0.04)`. Stroke, screen, slow rotate `t*0.08`.

### 21. Metatron

Fruit of Life: 13 centers (0 + 6 at R + 6 at 2R). Line every pair. Small circles at centers. Stroke, screen, rotate `t*0.12`.

### 22. Merkaba

Star tetrahedron wireframe + inner cube at 0.42 scale. Dim plate + halo. Rotate `ax=t*0.55, ay=t*0.8`.

### 23. RGB prism

Three luminance-tinted copies of the plate, additive (`lighter` / int16 add). Not a simple channel split — each copy shows the whole image.

```
lum = 0.299 R + 0.587 G + 0.114 B
cyan  (left)  : G = 0.25G + 0.55 lum,  B = 0.45B + 0.70 lum
green (mid)   : G = 0.35G + 0.75 lum
red   (right) : R = 0.35R + 0.75 lum

ox_cyan  = -(10 + sin(t*1.31+1.1)*9 + treble*24)
oy_cyan  = cos(t*0.97)*4
ox_green = sin(t*0.83)*(3 + mid*8)
oy_green = sin(t*2.07)*(5 + mid*12)
ox_red   = 10 + sin(t*1.73)*9 + bass*24
oy_red   = sin(t*1.11)*4
```

Canvas: `globalCompositeOperation = "lighter"`. Python: `np.roll` each plate then add.

## Overlay layers

Independent of `EFFECT_ORDER`. Config:

```yaml
overlays:
  solids: false   # platonic wireframe, skipped on looks 19–22
  glyphs: true    # rune / temple / zodiac / DJ pack
```

Studio: Layers sidebar, two buttons. Both can sit on the same look. When solids are on, glyphs move to an outer ring (`0.42 * min(w,h)`) so they orbit the solid. When solids are off, one large glyph sits near center plus two small floaters.

### Glyph pack (`riplens/glyphs.py` = `src/lib/engine/glyphs.ts`)

Stroke-only, unit box `[-1,1]`, y-up. Dual-stroke halo: dark 4.5px then HSV neon ~1.6px (Python: dilate overlay, darken plate 55, add). **167 marks.** Packs:

| pack | examples |
|---|---|
| Elder Futhark | fehu … dagaz (24) |
| Norse staves | valknut, aegishjalmur (Helm of Awe), vegvísir, mjolnir, gungnir, yggdrasil |
| Egyptian | ankh, wedjat, djed, was, ra disk, lotus, maat, scarab, tyet, shen, uraeus, pyramid, winged sun, ka, neb, neter, crook, flail |
| Babylonian / Sumerian | Ishtar star, dingir, crescent+star, cuneiform, rod-and-ring, Shamash, Sin, Marduk spade, Enki water, eight-point star, lamassu |
| Phoenician / Greek / Roman | Tanit, aleph, Baal, omega, phi, labrys, meander, bolt, alpha, delta, psi, lambda, caduceus, trident, labyrinth, thyrsus, fasces, laurel |
| Celtic | triskelion, triquetra, awen, spiral, Brigid's cross, Celtic cross, ogham ailm / beith |
| Slavic | kolovrat, hands of god |
| Alchemy | fire/water/air/earth, sun, moon, mercury, sulfur, salt, mars, venus, jupiter, saturn, squared circle |
| Hermetic / chaos | pentagram, vesica, ouroboros, chaos star, unicursal hexagram, hexagram, triple moon, horned god, eye of providence |
| India / Tibet / Levant | sri, trishula, dharmachakra, endless knot, vajra, om bindu, khatim, hamsa, nazar |
| Americas | Maya kan / fret, ollin, quincunx, serpent, chakana, Inti |
| East Asia | taiji, I Ching trigrams, bagua, tomoe, mitsudomoe, torii, seimei, taegeuk |
| Africa / Oceania | gye nyame, sankofa, dwennimmen, nsibidi star, koru, turtle, wave, medicine wheel, thunderbird |
| Zodiac | aries … pisces |
| DJ / VJ | vinyl, EQ bars, infinity, peace, anarchy, acid smiley, all-seeing eye, play triangle |

Layout: 8 glyphs on an ellipse, index `floor(t*0.72 + bass*8)`, stride 11. Pulse size with RMS.

### Solids overlay

One `SOLID_CYCLE` wireframe at center, `R = min(w,h)*(0.2 + v*0.08)`. Skip when current look ∈ `{solids, flower, metatron, merkaba}`.

### Captions overlay (`riplens/subtitles.py` = `src/lib/engine/subtitles.ts`)

Optional. Independent of glyphs/solids. Config:

```yaml
subtitles:
  enabled: false
  file: auto
  font: Montserrat-ExtraBold
  size: 0.052
  position: bottom
  margin: 0.09
```

`riplens lyrics` times `sources/lyrics/<stem>.txt` onto the vocal stem and writes an SRT (edit the .txt for words; never overwrite the SRT unless `--force`). `riplens render --subs` burns it after grain so type sits on top of neon. Fill + dark stroke + dim rounded pill. Default casing is as-written. Font resolves inside `fonts/` (170 commercial-free families). Studio toggle is Captions; timebase is `audio.currentTime()`, not wall clock.


Full extraction recipe: `skills/lyrics/SKILL.md`.

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
