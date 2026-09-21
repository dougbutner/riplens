export type RatioId = "1x1" | "16x9" | "9x16";

export type EffectId =
  | "kaleidoscope"
  | "chromatic"
  | "scanline"
  | "pixel_sort"
  | "block_corrupt"
  | "fractal"
  | "hsv_geometry"
  | "blend"
  | "lens_peel"
  | "feedback"
  | "vortex"
  | "slice_scramble"
  | "vhs"
  | "wave_warp"
  | "neon_edge"
  | "fisheye"
  | "zoom_streak"
  | "mosaic"
  | "solids"
  | "flower"
  | "metatron"
  | "merkaba"
  | "rgb_prism";

export interface RatioSpec {
  id: RatioId;
  label: string;
  w: number;
  h: number;
  use: string;
}

export const RATIOS: RatioSpec[] = [
  { id: "1x1", label: "1 × 1", w: 1080, h: 1080, use: "Feed" },
  { id: "16x9", label: "16 × 9", w: 1920, h: 1080, use: "YouTube" },
  { id: "9x16", label: "9 × 16", w: 1080, h: 1920, use: "Reels" },
];

export const EFFECT_ORDER: { id: EffectId; name: string; note: string }[] = [
  { id: "kaleidoscope", name: "Kaleidoscope", note: "Polar fold, 6–16 wedges" },
  { id: "chromatic", name: "Chromatic split", note: "RGB channel offset" },
  { id: "scanline", name: "Scanline tear", note: "Horizontal slice drag" },
  { id: "pixel_sort", name: "Pixel sort", note: "Luminance interval sort" },
  { id: "block_corrupt", name: "Block corrupt", note: "Copied macroblocks" },
  { id: "fractal", name: "Fractal overlay", note: "Julia set, difference blend" },
  { id: "hsv_geometry", name: "HSV lattice", note: "N-gon grid keyed to HSV" },
  { id: "blend", name: "Blend rotate", note: "Screen / difference / overlay" },
  { id: "lens_peel", name: "Lens peel", note: "Plate rips off the gate" },
  { id: "feedback", name: "Feedback trail", note: "Scaled ghost recursion" },
  { id: "vortex", name: "Vortex", note: "Polar swirl remap" },
  { id: "slice_scramble", name: "Slice scramble", note: "Vertical strip shuffle" },
  { id: "vhs", name: "VHS tracking", note: "Chroma noise + tear" },
  { id: "wave_warp", name: "Wave warp", note: "Sinusoidal displacement" },
  { id: "neon_edge", name: "Neon edge", note: "Sobel glow on the plate" },
  { id: "fisheye", name: "Fisheye", note: "Barrel lens warp" },
  { id: "zoom_streak", name: "Zoom streak", note: "Radial copies toward center" },
  { id: "mosaic", name: "Mosaic", note: "Crystal block quantize" },
  { id: "solids", name: "Platonic solids", note: "3D wireframe tetra → dodeca" },
  { id: "flower", name: "Flower of Life", note: "Nineteen stroked circles" },
  { id: "metatron", name: "Metatron", note: "Fruit of Life + all lines" },
  { id: "merkaba", name: "Merkaba", note: "Star tetrahedron, no fill" },
  { id: "rgb_prism", name: "RGB prism", note: "Cyan left, red right, green mid, drifting" },
];

export interface AudioFeatures {
  rms: number;
  bass: number;
  mid: number;
  treble: number;
  centroid: number;
  peak: boolean;
}

export interface Hsv {
  h: number;
  s: number;
  v: number;
}

export function featuresToHsv(f: AudioFeatures): Hsv {
  return {
    h: (f.centroid * 360 + f.bass * 80) % 360,
    s: 0.35 + f.mid * 0.65,
    v: 0.28 + f.rms * 0.72,
  };
}

export const DEFAULT_THRESHOLD = 0.62;
export const DEFAULT_COOLDOWN = 1.2;
