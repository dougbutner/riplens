from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FrameFeat:
    rms: float
    bass: float
    mid: float
    treble: float
    centroid: float
    h: float
    s: float
    v: float
