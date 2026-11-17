"""Find the same moment in two recordings by what happens in them, not by their clocks.

Everything here reads media through ffmpeg (which must be on PATH) and works on
small numpy arrays: a region of interest (ROI) scaled down, or audio at 8 kHz.
Times are seconds from the start of each file.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass

import numpy as np

AUDIO_RATE = 8000


class EventNotFound(RuntimeError):
    """The event never happens in the searched part of the file."""


def _ffmpeg() -> str:
    exe = shutil.which('ffmpeg')
    if not exe:
        raise RuntimeError('ffmpeg is not on PATH')
    return exe


def duration(path: str) -> float:
    """Length of a media file in seconds (container duration)."""
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', path],
                         capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)['format']['duration'])


def read_audio(path: str, rate: int = AUDIO_RATE) -> np.ndarray:
    """The file's audio as mono float samples in -1..1."""
    raw = subprocess.run([_ffmpeg(), '-v', 'error', '-i', path, '-vn', '-ac', '1', '-ar', str(rate),
                          '-f', 's16le', '-'], capture_output=True, check=True).stdout
    if not raw:
        raise EventNotFound(f'{path}: no audio stream')
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


@dataclass(frozen=True)
class Roi:
    """A rectangle in the video's own pixels."""
    x: int
    y: int
    w: int
    h: int

    @staticmethod
    def parse(text: str) -> 'Roi':
        """'x,y,w,h' -> Roi."""
        x, y, w, h = (int(round(float(v))) for v in text.split(','))
        return Roi(x, y, w, h)


def read_frames(path: str, roi: Roi | None = None, fps: float = 30.0, size: tuple[int, int] | None = None) -> np.ndarray:
    """Frames (N, h, w, 3) uint8 at a steady fps, cropped to `roi` and scaled to `size` (w, h)."""
    filters = [f'fps={fps}']
    if roi:
        filters.append(f'crop={roi.w}:{roi.h}:{roi.x}:{roi.y}')
    if size is None:
        w, h = (roi.w, roi.h) if roi else _video_size(path)
        scale = min(1.0, 160.0 / max(w, h))  # small is plenty, and fast
        size = (max(2, int(w * scale) // 2 * 2), max(2, int(h * scale) // 2 * 2))
    filters.append(f'scale={size[0]}:{size[1]}:flags=area')
    raw = subprocess.run([_ffmpeg(), '-v', 'error', '-i', path, '-vf', ','.join(filters), '-an',
                          '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, np.uint8)
    return frames.reshape(-1, size[1], size[0], 3)


def _video_size(path: str) -> tuple[int, int]:
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height',
                          '-of', 'json', path], capture_output=True, text=True, check=True).stdout
    s = json.loads(out)['streams'][0]
    return int(s['width']), int(s['height'])


# MARK: - Events


def audio_onset(path: str, after: float = 0.0, threshold_db: float = -45.0, window_ms: float = 5.0) -> float:
    """Seconds into `path` when its sound first rises above `threshold_db` dBFS (peak in each window), at or after `after`."""
    x = np.abs(read_audio(path))
    win = max(1, int(AUDIO_RATE * window_ms / 1000))
    env = x[: len(x) // win * win].reshape(-1, win).max(axis=1)
    t = np.arange(len(env)) * win / AUDIO_RATE
    hit = np.where((env > 10 ** (threshold_db / 20)) & (t >= after))[0]
    if not len(hit):
        raise EventNotFound(f'{path}: no sound above {threshold_db} dBFS after {after:.2f} s')
    return float(t[hit[0]])


COLORS = {
    # name: (predicate on r, g, b arrays) - simple, robust thresholds for UI highlight colors
    'green': lambda r, g, b: (g > 140) & (g > r + 50) & (g > b + 30),
    'red': lambda r, g, b: (r > 150) & (r > g + 60) & (r > b + 60),
    'blue': lambda r, g, b: (b > 150) & (b > r + 50) & (b > g + 20),
    'yellow': lambda r, g, b: (r > 170) & (g > 150) & (b < 110),
    'white': lambda r, g, b: (r > 215) & (g > 215) & (b > 215),
    'bright': lambda r, g, b: (r.astype(int) + g + b) > 600,
    'dark': lambda r, g, b: (r.astype(int) + g + b) < 90,
}


def color_mask(frames: np.ndarray, color: str) -> np.ndarray:
    """Boolean (N, h, w): pixels matching `color` (a name in COLORS, or 'rgb:R,G,B[,tolerance]')."""
    r, g, b = (frames[..., i].astype(np.int16) for i in range(3))
    if color.startswith('rgb:'):
        parts = [int(v) for v in color[4:].split(',')]
        tol = parts[3] if len(parts) > 3 else 40
        return (abs(r - parts[0]) <= tol) & (abs(g - parts[1]) <= tol) & (abs(b - parts[2]) <= tol)
    if color not in COLORS:
        raise ValueError(f'unknown color {color!r}: use one of {sorted(COLORS)} or rgb:R,G,B[,tol]')
    return COLORS[color](r, g, b)


def color_event(path: str, roi: Roi, color: str = 'green', min_fraction: float = 0.25, after: float = 0.0,
                fps: float = 30.0, change: bool = False) -> float:
    """Seconds into `path` when at least `min_fraction` of the ROI first turns `color` (at or after `after`).

    With change=True it finds the first frame that differs from the first one instead
    (any visible change in the ROI), ignoring `color`.
    """
    frames = read_frames(path, roi, fps)
    t = np.arange(len(frames)) / fps
    if change:
        d = np.abs(frames.astype(np.int16) - frames[0].astype(np.int16)).mean(axis=(1, 2, 3))
        hit = np.where((d > 8) & (t >= after))[0]
    else:
        frac = color_mask(frames, color).mean(axis=(1, 2))
        hit = np.where((frac >= min_fraction) & (t >= after))[0]
    if not len(hit):
        raise EventNotFound(f'{path}: the ROI never turns {"different" if change else color} after {after:.2f} s')
    return float(t[hit[0]])


# MARK: - Series (one value per video frame)


def motion_series(path: str, roi: Roi, fps: float = 30.0) -> np.ndarray:
    """How much the ROI changes from frame to frame (mean absolute difference, 0..255)."""
    f = read_frames(path, roi, fps).astype(np.int16)
    d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2, 3))
    return np.concatenate([[0.0], d]).astype(np.float32)


def knob_series(path: str, roi: Roi, fps: float = 30.0, color: str = 'green', ring: float = 0.62) -> np.ndarray:
    """A rotary knob's angle per frame, in degrees clockwise from 12 o'clock (-150..150).

    `roi` is a square around the knob; its pointer must be drawn in `color`. The angle is
    where that color is strongest on a circle at `ring` x the radius.
    """
    f = read_frames(path, roi, fps, size=(120, 120)).astype(np.float32)
    n = 120
    c, r = n / 2, ring * n / 2
    a = np.radians(np.arange(-150, 151, 1.0))
    xs = np.clip((c + r * np.sin(a)).astype(int), 0, n - 1)
    ys = np.clip((c - r * np.cos(a)).astype(int), 0, n - 1)
    ringpx = f[:, ys, xs, :]
    if color == 'green':
        score = ringpx[..., 1] - (ringpx[..., 0] + ringpx[..., 2]) / 2
    else:
        score = color_mask(ringpx.astype(np.uint8), color).astype(np.float32)
    return np.degrees(a[np.argmax(score, axis=1)]).astype(np.float32)


def envelope_series(path: str, fps: float = 30.0) -> np.ndarray:
    """Audio loudness per video frame (RMS, dBFS)."""
    x = read_audio(path)
    hop = AUDIO_RATE / fps
    n = int(len(x) / hop)
    out = np.empty(n, np.float32)
    for i in range(n):
        w = x[int(i * hop): int((i + 1) * hop)]
        out[i] = 20 * np.log10(np.sqrt(np.mean(w * w)) + 1e-9)
    return out


def brightness_series(path: str, fps: float = 30.0, silence_db: float = -50.0) -> np.ndarray:
    """Audio brightness per video frame: log spectral centroid. Follows a filter sweep or an opening filter.

    Frames quieter than `silence_db` have no brightness: they're NaN, and best_lag skips them.
    """
    x = read_audio(path)
    hop, win = AUDIO_RATE / fps, 1024
    freqs = np.fft.rfftfreq(win, 1 / AUDIO_RATE)
    window = np.hanning(win)
    n = int((len(x) - win) / hop)
    out = np.full(max(n, 0), np.nan, np.float32)
    for i in range(n):
        seg = x[int(i * hop): int(i * hop) + win]
        if 20 * np.log10(np.sqrt(np.mean(seg * seg)) + 1e-9) < silence_db:
            continue
        m = np.abs(np.fft.rfft(seg * window))
        out[i] = np.log((freqs * m).sum() / (m.sum() + 1e-9) + 1)
    return out


# MARK: - Lining two series up


def best_lag(a: np.ndarray, b: np.ndarray, max_lag: int, metric: str = 'corr', min_overlap: int = 30) -> tuple[int, float]:
    """The lag L (frames) for which a[t] best matches b[t + L], and its score.

    metric 'corr': Pearson correlation (higher is better) - for series in different units,
    such as a knob angle against audio brightness. 'mae': mean absolute difference
    (lower is better) - for the same quantity in both, such as two knobs. NaN values
    (silence, in brightness_series) are left out of the comparison.
    """
    best = None
    for lag in range(-max_lag, max_lag + 1):
        i0, i1 = max(0, -lag), min(len(a), len(b) - lag)
        if i1 - i0 < min_overlap:
            continue
        x, y = a[i0:i1], b[i0 + lag:i1 + lag]
        keep = ~(np.isnan(x) | np.isnan(y))
        if keep.sum() < min_overlap:
            continue
        x, y = x[keep], y[keep]
        if metric == 'mae':
            s = float(np.mean(np.abs(x - y)))
            better = best is None or s < best[1]
        else:
            if x.std() == 0 or y.std() == 0:
                continue
            s = float(np.corrcoef(x, y)[0, 1])
            better = best is None or s > best[1]
        if better:
            best = (lag, s)
    if best is None:
        raise EventNotFound('the series are too short to compare')
    return best


SERIES = {
    'motion': lambda p, roi, fps, color: motion_series(p, roi, fps),
    'knob': lambda p, roi, fps, color: knob_series(p, roi, fps, color or 'green'),
    'envelope': lambda p, roi, fps, color: envelope_series(p, fps),
    'brightness': lambda p, roi, fps, color: brightness_series(p, fps),
}


def series(path: str, kind: str, roi: Roi | None = None, fps: float = 30.0, color: str | None = None) -> np.ndarray:
    """One of SERIES for `path` ('motion' and 'knob' need an roi)."""
    if kind in ('motion', 'knob') and roi is None:
        raise ValueError(f'{kind} needs --roi')
    return SERIES[kind](path, roi, fps, color)
