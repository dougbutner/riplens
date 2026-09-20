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
| `riplens render --threshold 0.7` | Stricter effect switching |

Cursor, CLI, and this README all call the same functions. There is no hidden GUI step.

## How a frame is built

1. **Analyze** the song once with librosa — RMS, bass / mid / treble, spectral centroid, tempo.
2. **Cover-crop** the current plate to the target ratio. Zoom breathes with RMS (Ken Burns).
3. **Pick an effect** from the ten-look stack. When RMS crosses `threshold` (default `0.62`) on a rising edge, and `cooldown` (default `1.2s`) has elapsed, advance to the next look.
4. **HSV geometry** is drawn on every frame:
   - **H** ← spectral centroid (wrapped 0–360, plus a bass offset)
   - **S** ← mid energy (0.35–1.0)
   - **V** ← RMS / waveform height (0.28–1.0)
5. **Encode** BGR frames + original audio to H.264 `yuv420p` + AAC, `+faststart`. Plays on YouTube and Instagram.

## The ten looks

They rotate in this order. Click-lock them in the live studio; here they only move on peaks.

| # | id | What you see |
|---|---|---|
| 01 | `kaleidoscope` | Polar fold, 6–16 wedges from bass, rotation from RMS |
| 02 | `chromatic` | RGB channel offset from bass, hue wash from centroid |
| 03 | `scanline` | Horizontal slice drag, CRT bands from treble |
| 04 | `pixel_sort` | Asendorf luminance-interval sort on rows |
| 05 | `block_corrupt` | Copied macroblocks, inverted tear on loud peaks |
| 06 | `fractal` | Julia set keyed to bass/mid, screen + overlay |
| 07 | `hsv_geometry` | Hex grid colored with the HSV map, waveform stroke |
| 08 | `blend` | overlay / difference / screen / multiply / color-dodge |
| 09 | `lens_peel` | Current plate rips off a jagged gate, next fades in from paper-white |
| 10 | `feedback` | Previous frame scaled 1.03, rotated, ghosted |

Exact formulas: [`skills/glitch-visualizer/SKILL.md`](skills/glitch-visualizer/SKILL.md).

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

A browser studio exists for auditioning the same ten looks against a demo beat or dropped files. It records WebM. Final Instagram / YouTube files always come from this Python renderer.

Repo: [github.com/dougbutner/riplens](https://github.com/dougbutner/riplens)
