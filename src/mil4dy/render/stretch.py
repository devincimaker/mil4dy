"""Sample-accurate time-stretching via piecewise constant-ratio Rubberband R3.

Rubberband's --timemap mode has a variable internal offset (~600+ samples,
measured), so it cannot pin beats to the output grid. Constant-ratio R3 is
accurate to ~±5 samples, so instead we:

- split the track into segments between "anchor" beats (short segments inside
  tempo ramps, whole phrases elsewhere),
- stretch each segment at the constant ratio that maps its anchors exactly onto
  the OutputClock grid,
- splice consecutive segments with short equal-power crossfades centered on the
  anchors. Adjacent segments differ in ratio by <0.5%, so the overlapping
  material is phase-coherent within the crossfade window (<1 sample drift).

Segments whose input and output spans already agree to within a couple of
samples are copied directly (no rubberband) — the common case outside
transitions, where playback BPM equals the track's native BPM.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from ..analysis.decode import RENDER_SAMPLE_RATE

XFADE = 512  # samples, total crossfade window at each splice
PAD_IN = 4096  # input-domain context handed to rubberband beyond segment edges
DIRECT_COPY_TOLERANCE = 2  # samples


class StretchError(RuntimeError):
    pass


def stretch_constant(audio: np.ndarray, ratio: float,
                     sample_rate: int = RENDER_SAMPLE_RATE,
                     pitch_semitones: float = 0.0) -> np.ndarray:
    """One constant-ratio R3 stretch. audio (n, 2) float32 -> (~n*ratio, 2)."""
    with tempfile.TemporaryDirectory(prefix="mil4dy-rb-") as td:
        tdir = Path(td)
        in_wav, out_wav = tdir / "in.wav", tdir / "out.wav"
        sf.write(in_wav, audio.astype(np.float32), sample_rate, subtype="FLOAT")
        cmd = ["rubberband", "--fine", "--time", f"{ratio:.10f}"]
        if pitch_semitones:
            cmd += ["--pitch", f"{pitch_semitones:.4f}"]
        cmd += [str(in_wav), str(out_wav)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise StretchError(f"rubberband failed: {proc.stderr.strip()}")
        out, _ = sf.read(out_wav, dtype="float32", always_2d=True)
    return out


def _slice_padded(audio: np.ndarray, start: int, end: int) -> np.ndarray:
    """audio[start:end] with zero padding for out-of-range indices."""
    n = len(audio)
    out = np.zeros((end - start, audio.shape[1]), np.float32)
    lo, hi = max(start, 0), min(end, n)
    if hi > lo:
        out[lo - start : hi - start] = audio[lo:hi]
    return out


def piecewise_stretch(
    audio: np.ndarray,
    anchors_in: np.ndarray,
    anchors_out: np.ndarray,
    sample_rate: int = RENDER_SAMPLE_RATE,
    pitch_semitones: float = 0.0,
) -> np.ndarray:
    """Stretch so that input sample anchors_in[j] lands exactly at output sample
    anchors_out[j] - anchors_out[0] of the returned buffer.

    anchors_*: strictly increasing int arrays of equal length >= 2.
    Returns float32 (anchors_out[-1] - anchors_out[0], 2).
    """
    anchors_in = np.asarray(anchors_in, dtype=np.int64)
    anchors_out = np.asarray(anchors_out, dtype=np.int64)
    if len(anchors_in) != len(anchors_out) or len(anchors_in) < 2:
        raise ValueError("need matching anchor arrays of length >= 2")
    if np.any(np.diff(anchors_in) <= 0) or np.any(np.diff(anchors_out) <= 0):
        raise ValueError("anchors must be strictly increasing")

    n_seg = len(anchors_in) - 1
    base = int(anchors_out[0])
    total = int(anchors_out[-1] - base)
    out = np.zeros((total, 2), np.float32)
    half = XFADE // 2

    # Equal-power crossfade ramps for splice windows
    x = (np.arange(XFADE) + 0.5) / XFADE
    w_in = np.sin(0.5 * np.pi * x).astype(np.float32)[:, None]
    w_out = np.cos(0.5 * np.pi * x).astype(np.float32)[:, None]

    prev_tail: np.ndarray | None = None  # segment material extending past its right anchor

    for j in range(n_seg):
        in_a, in_b = int(anchors_in[j]), int(anchors_in[j + 1])
        out_a, out_b = int(anchors_out[j] - base), int(anchors_out[j + 1] - base)
        in_len, out_len = in_b - in_a, out_b - out_a
        left = half if j > 0 else 0
        right = half if j < n_seg - 1 else 0

        if abs(in_len - out_len) <= DIRECT_COPY_TOLERANCE:
            seg = _slice_padded(audio, in_a - left, in_a + out_len + right)
        else:
            ratio = out_len / in_len
            in_lo = max(0, in_a - PAD_IN)
            in_hi = min(len(audio), in_b + PAD_IN)
            stretched = stretch_constant(audio[in_lo:in_hi], ratio, sample_rate,
                                         pitch_semitones)
            s0 = int(round((in_a - in_lo) * ratio))
            seg = _slice_padded(stretched, s0 - left, s0 + out_len + right)

        # seg covers [out_a - left, out_b + right); body write skips splice zones
        body_start = out_a + (half if j > 0 else 0)
        body_end = out_b - (half if j < n_seg - 1 else 0)
        out[body_start:body_end] = seg[body_start - (out_a - left) : body_end - (out_a - left)]

        if j > 0 and prev_tail is not None:
            # Splice window [out_a - half, out_a + half)
            head = seg[:XFADE]
            window = prev_tail * w_out + head * w_in
            out[out_a - half : out_a + half] = window[: min(XFADE, total - (out_a - half))]

        # Tail for the next splice: material covering [out_b - half, out_b + half)
        prev_tail = seg[-XFADE:] if right else None

    return out


def plan_anchors(
    in_samples: np.ndarray,
    out_samples: np.ndarray,
    dense_ranges: list[tuple[int, int]],
    dense_step: int = 2,
    sparse_step: int = 32,
    max_interior_error: int = 132,  # samples (~3 ms)
) -> np.ndarray:
    """Choose anchor beat indices for piecewise_stretch.

    in_samples/out_samples: per-beat sample positions (input domain / output
    domain), same length. dense_ranges: [start_beat, end_beat) intervals (tempo
    ramps) that get an anchor every `dense_step` beats; elsewhere every
    `sparse_step` beats. Sparse intervals whose interior beats would deviate
    from the linear mapping by more than max_interior_error are split
    recursively (handles source tracks with drifting internal grids).
    """
    n = len(in_samples)
    last = n - 1
    dense = np.zeros(n, dtype=bool)
    for a, b in dense_ranges:
        dense[max(a, 0) : min(b, n)] = True

    anchors: set[int] = {0, last}
    k = 0
    while k < last:
        step = dense_step if dense[k] else sparse_step
        # Do not let a sparse interval cross into a dense range
        nxt = min(k + step, last)
        if not dense[k]:
            crossing = np.flatnonzero(dense[k + 1 : nxt])
            if len(crossing):
                nxt = k + 1 + int(crossing[0])
        anchors.add(nxt)
        k = nxt

    def split(a: int, b: int) -> None:
        if b - a < 2:
            return
        ideal = in_samples[a] + (in_samples[b] - in_samples[a]) * (
            (out_samples[a + 1 : b] - out_samples[a]) / (out_samples[b] - out_samples[a])
        )
        err = np.abs(in_samples[a + 1 : b] - ideal)
        if err.max() > max_interior_error:
            mid = (a + b) // 2
            anchors.add(mid)
            split(a, mid)
            split(mid, b)

    for a, b in zip(sorted(anchors)[:-1], sorted(anchors)[1:]):
        split(a, b)

    return np.array(sorted(anchors), dtype=np.int64)
