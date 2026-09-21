# RipLens

Local glitch music-video studio. Your songs. Your art. Three frames.

No generative models. No API calls. OpenCV, librosa, FFmpeg, NumPy.

Drop files into `sources/`, run one command, collect YouTube-safe and Instagram-safe H.264 from three folders.

```
sources/music   +  sources/images  (+ sources/videos)
                    ↓
        riplens render
                    ↓
     output/1x1     1080×1080   feed
     output/16x9    1920×1080   YouTube
     output/9x16    1080×1920   Reels / Stories
```

The three ratios render **one after another**, never mixed into one folder.

## Install

Needs Python 3.10+ and FFmpeg. On a machine with NVIDIA, NVENC is picked automatically.

```bash
git clone https://github.com/dougbutner/riplens.git
cd riplens
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
riplens init
riplens doctor
```

Put songs in `sources/music` (wav, mp3, flac, aiff, ogg, m4a).
Put art in `sources/images` (png, jpg, webp, tiff).
Optional B-roll in `sources/videos` — frames are sampled as extra plates.

## Commands

| Command | What it does |
|---|---|
| `riplens init` | Create `sources/` and `output/` folders |
| `riplens doctor` | FFmpeg path, encoder (`h264_nvenc` or `libx264`), file counts |
| `riplens analyze` | Duration, BPM, peak count, RMS per song |
| `riplens render` | Every song × 1×1, then 16×9, then 9×16 |
| `riplens render --ratio 9x16` | Reels only |
| `riplens render --song path.wav` | One track, all three ratios |
| `riplens lyrics` | Isolate vocals, transcribe locally, write `sources/lyrics/<stem>.srt` |
| `riplens lyrics --force --model small` | Redo the SRT (default: never overwrite your edits) |
| `riplens render --subs` | Burn the SRT onto the three ratios |
| `riplens render --no-subs` | Skip captions even if config has them on |

Cursor, CLI, and this README all call the same functions. There is no hidden GUI step.

## How a frame is built

1. **Analyze** the song once with librosa — RMS, bass / mid / treble, spectral centroid, tempo.
2. **Cover-crop** the current plate to the target ratio. Zoom breathes with RMS (Ken Burns).
3. **Pick an effect** from the 23-look stack. When RMS crosses `threshold` (default `0.62`) on a rising edge, and `cooldown` (default `1.2s`) has elapsed, advance to the next look.
4. **Optional neon overlays** (config `overlays:`):
   - **glyphs** (default on) — stroke-only runes and temple marks, HSV-colored
   - **solids** (default off) — a platonic wireframe in the center; skipped when the current look is already a geometry look
5. **Optional captions** (`riplens render --subs`) — burn `sources/lyrics/<stem>.srt` with a font from `fonts/`. Edit the SRT in any text editor; the next render uses your words.
6. **Encode** BGR frames + original audio to H.264 `yuv420p` + AAC, `+faststart`. Plays on YouTube and Instagram.

## The 23 looks

They rotate in this order. Click-lock them in the live studio; here they only move on peaks.
The six-spoke hex wheel is gone. Sacred-geometry looks are **stroke-only wireframes** floating on the plate.
Glyphs are a **separate overlay** (default on) — not a look.

| # | id | What you see |
|---|---|---|
| 01 | `kaleidoscope` | Polar fold; wedge count wanders with time + bass |
| 02 | `chromatic` | RGB channel offset from bass, hue wash from centroid |
| 03 | `scanline` | Horizontal slice drag, CRT bands from treble |
| 04 | `pixel_sort` | Asendorf luminance-interval sort on rows |
| 05 | `block_corrupt` | Copied macroblocks, inverted tear on loud peaks |
| 06 | `fractal` | Julia set keyed to bass/mid, screen + overlay |
| 07 | `hsv_geometry` | N-gon lattice (3–8 sides) colored with the HSV map |
| 08 | `blend` | overlay / difference / screen / multiply / color-dodge |
| 09 | `lens_peel` | Current plate rips off a jagged gate, next fades in from paper-white |
| 10 | `feedback` | Previous frame scaled 1.03, rotated, ghosted |
| 11 | `vortex` | Polar swirl remap, twist from RMS |
| 12 | `slice_scramble` | Vertical strip shuffle |
| 13 | `vhs` | Tracking tear + chroma split + scanlines |
| 14 | `wave_warp` | Sinusoidal displacement mesh |
| 15 | `neon_edge` | Sobel glow screened onto the plate |
| 16 | `fisheye` | Barrel lens warp from bass |
| 17 | `zoom_streak` | Radial copies toward center |
| 18 | `mosaic` | Crystal block quantize |
| 19 | `solids` | 3D wireframe platonic solids, cycling tetra→dodeca |
| 20 | `flower` | Flower of Life — 19 stroked circles, no fill |
| 21 | `metatron` | Fruit of Life + every connecting line |
| 22 | `merkaba` | Star tetrahedron + inner cube, stroke only |
| 23 | `rgb_prism` | Cyan copy left, bright red right, green mid — independent drift |

Exact formulas: [`skills/glitch-visualizer/SKILL.md`](skills/glitch-visualizer/SKILL.md).

### Overlay layers (`config.yaml` → `overlays`)

| layer | default | what |
|---|---|---|
| `glyphs` | on | Neon stroke pack: Elder Futhark, Egyptian, Babylonian/Sumerian, Phoenician, Greek, Celtic, Norse staves (valknut, Helm of Awe, vegvísir), alchemy, hermetic/chaos, zodiac, Adinkra, Maya/Inca, DJ marks |
| `solids` | off | One platonic wireframe at center. Skipped while looks 19–22 are already drawing geometry. |

Both can be on at once. Glyphs move to an outer ring so they sit around the solid.

## Lyrics / captions (optional)

Local only. No lyric APIs.

```
pip install faster-whisper          # transcriber (CTranslate2). Mac CPU/int8 is fine.
pip install demucs                  # optional vocal stem. MPS on Apple Silicon.
riplens lyrics                      # writes sources/lyrics/<stem>.srt + .txt
# open the .srt, fix any word, save
riplens render --subs
```

Accuracy order:

1. **Demucs `htdemucs` two-stem vocals** then **faster-whisper `small`/`medium`** on the stem. VAD is off — singing is not speech and VAD drops phrases.
2. If Demucs is missing: FFmpeg **center-channel extract** (vocals usually sit in the middle of a stereo mix) then the same Whisper pass.
3. You correct the SRT. The renderer never overwrites an existing SRT unless you pass `--force`.

Subtitle type lives in [`fonts/`](fonts/) — **170 commercial-free families** (Fontshare / Indian Type Foundry + article-recommended Google Fonts + League of Moveable Type). The `.ttf` files and [`fonts/catalog.json`](fonts/catalog.json) are in this repo so a clone can burn captions without a network. Default face is **Montserrat ExtraBold**. Config:

```yaml
subtitles:
  enabled: false
  font: Montserrat-ExtraBold
  size: 0.052
  position: bottom
```

Rebuild the font folder (optional) with `python3 scripts/collect_fonts.py`.

The live canvas gate (browser) lives in [`src/lib/engine/`](src/lib/engine/). Same 23 looks, same glyph pack, same HSV map as the Python renderer.

## Config

[`config.yaml`](config.yaml) is the session file. Threshold, cooldown, fps, codec, and the effect order live there. You should not have to edit Python for a normal take.

Encoder `auto` means: use `h264_nvenc` when `nvidia-smi` sees a card, otherwise `libx264` at CRF 18.

## Skills / agents

Anyone cloning this into Cursor (or another agent) must read:

- [`AGENTS.md`](AGENTS.md) — the hard rule
- [`skills/glitch-visualizer/SKILL.md`](skills/glitch-visualizer/SKILL.md) — copyable recipes

**Rule:** if you change `riplens/effects.py` or the HSV mapping in `riplens/audio.py`, you update the skill in the **same commit**. The skill is the pattern others copy. Code and skill never diverge.

## Why these libraries

Searched GitHub, papers, and common music-video pipelines. The stack that actually ships local, open, non-AI looks:

| Job | Library | Why |
|---|---|---|
| Beats, RMS, centroid, bands | [librosa](https://github.com/librosa/librosa) | Standard offline analysis. No model download. |
| Pixels, remap, blend | OpenCV (`opencv-python-headless`) | Kaleidoscope remap, channel split, Julia overlay |
| Arrays | NumPy | Polar fold, pixel sort, Julia iteration |
| Encode | FFmpeg (`libx264` / `h264_nvenc`) | YouTube-safe yuv420p + AAC. `imageio-ffmpeg` is the fallback binary. |

Deliberately **not** used: MoviePy (heavy), Stable Diffusion / StreamDiffusion (generative), any HTTP API, ffglitch (optional later — true codec mosh is a follow-up, not required for YouTube playback).

## Live preview

A browser studio exists for auditioning the same 23 looks against a demo beat or dropped files. It records WebM. Final Instagram / YouTube files always come from this Python renderer.

Repo: [github.com/dougbutner/riplens](https://github.com/dougbutner/riplens)
