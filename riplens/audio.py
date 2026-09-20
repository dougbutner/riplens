"""Offline audio analysis. librosa only — no network, no models."""

from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np


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


class TrackFeatures:
    def __init__(self, path: str, hop_length: int = 512, sr: int = 22050) -> None:
        y, sr = librosa.load(path, sr=sr, mono=True)
        self.sr = sr
        self.duration = float(librosa.get_duration(y=y, sr=sr))
        self.y = y
        hop = hop_length
        rms = librosa.feature.rms(y=y, hop_length=hop)[0]
        stft = np.abs(librosa.stft(y, hop_length=hop, n_fft=2048))
        freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
        bass = _band(stft, freqs, 20, 150)
        mid = _band(stft, freqs, 150, 2000)
        treble = _band(stft, freqs, 2000, 8000)
        centroid = librosa.feature.spectral_centroid(S=stft, sr=sr)[0]
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop)
        self.tempo = float(np.atleast_1d(tempo)[0])
        self.times = librosa.times_like(rms, sr=sr, hop_length=hop)
        self.rms = _norm(rms)
        self.bass = _norm(bass)
        self.mid = _norm(mid)
        self.treble = _norm(treble)
        self.centroid = _norm(centroid)
        peak_idx = np.where((self.rms[1:] > 0.62) & (self.rms[1:] - self.rms[:-1] > 0.04))[0]
        self.peak_count = int(peak_idx.size)
        self._rms_raw = rms

    def at(self, t: float) -> FrameFeat:
        rms = float(_interp(self.times, self.rms, t))
        bass = float(_interp(self.times, self.bass, t))
        mid = float(_interp(self.times, self.mid, t))
        treble = float(_interp(self.times, self.treble, t))
        centroid = float(_interp(self.times, self.centroid, t))
        h = (centroid * 360.0 + bass * 80.0) % 360.0
        s = 0.35 + mid * 0.65
        v = 0.28 + rms * 0.72
        return FrameFeat(rms, bass, mid, treble, centroid, h, s, v)

    def summary(self) -> dict:
        return {
            "duration": round(self.duration, 2),
            "tempo": round(self.tempo, 1),
            "peak_count": self.peak_count,
            "rms_mean": round(float(self.rms.mean()), 3),
            "rms_max": round(float(self.rms.max()), 3),
        }


def _band(stft: np.ndarray, freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    mask = (freqs >= lo) & (freqs < hi)
    if not np.any(mask):
        return np.zeros(stft.shape[1], dtype=np.float32)
    return stft[mask].mean(axis=0)


def _norm(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    p = np.percentile(x, 95)
    if p <= 1e-8:
        return np.zeros_like(x)
    return np.clip(x / p, 0.0, 1.0)


def _interp(times: np.ndarray, values: np.ndarray, t: float) -> float:
    return float(np.interp(t, times, values))
