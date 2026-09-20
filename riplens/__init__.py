"""RipLens — local glitch music-video renderer. No AI. No APIs."""

__version__ = "1.0.0"

EFFECT_ORDER = [
    "kaleidoscope",
    "chromatic",
    "scanline",
    "pixel_sort",
    "block_corrupt",
    "fractal",
    "hsv_geometry",
    "blend",
    "lens_peel",
    "feedback",
]

RATIOS = {
    "1x1": (1080, 1080),
    "16x9": (1920, 1080),
    "9x16": (1080, 1920),
}
