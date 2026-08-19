"""Library analysis orchestrator.

Phase A (process pool): decode + librosa frame features per track.
Phase B (serial, main process): beat_this + essentia model inference, structure
segmentation, cache write. Torch/essentia models load once and stay resident.
Energy values are stored raw in the cache and percentile-normalized across the
current library at load time.
"""

from __future__ import annotations

import os
import sys
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

import numpy as np

from ..schemas import TrackAnalysis
from .beats import BeatEngine, phrase_grid, robust_bpm, score_intro
from .cache import AnalysisCache
from .decode import decode, discover_tracks, fingerprint, probe
from .features import FrameFeatures, integrated_lufs, normalize_energies, raw_energy
from .key import detect_key
from .structure import segment_track


def _phase_a(path_str: str):
    path = Path(path_str)
    tags = probe(path)
    y = decode(path)  # mono @22050 for features
    ff = FrameFeatures(y)
    return path_str, tags, ff


def _phase_b(path: Path, fp: str, tags, ff: FrameFeatures, beat_engine: BeatEngine
             ) -> TrackAnalysis:
    y44 = decode(path, sample_rate=44100, mono=True)
    duration = len(y44) / 44100.0

    beat_times, downbeat_times, beat_conf, intro_local, intro_ok = beat_engine.detect(y44, 44100)
    segments, novelty_bounds = segment_track(y44, 44100, ff, beat_times, downbeat_times, duration)
    phrase_starts = phrase_grid(downbeat_times, novelty_bounds)

    key, scale, camelot, key_conf, key_engine = detect_key(y44)
    stats = ff.span_stats(0, duration)
    bpm = robust_bpm(beat_times)
    intro = next((s for s in segments if s.label == "intro"), None)
    if intro is not None:
        # Refine the intro bound now that we have segments; still using the
        # stored grid (already regularized). Raw intro_ok from detect wins
        # when the detector rebuilt a uniform pulse.
        refined_bpm, refined_ok = score_intro(beat_times, duration, bpm, intro.end)
        if intro_local <= 0:
            intro_local = refined_bpm
        if intro_ok:
            intro_ok = refined_ok

    return TrackAnalysis(
        path=str(path), fingerprint=fp,
        title=tags.title, artist=tags.artist, genre=tags.genre, duration=duration,
        bpm=bpm,
        beat_times=np.round(beat_times, 5).tolist(),
        downbeat_times=np.round(downbeat_times, 5).tolist(),
        phrase_starts=np.round(phrase_starts, 5).tolist(),
        downbeat_confidence=beat_conf,
        intro_grid_ok=intro_ok, intro_bpm=intro_local,
        beats_engine=beat_engine.name,
        key=key, scale=scale, camelot=camelot, key_confidence=key_conf, key_engine=key_engine,
        lufs_integrated=integrated_lufs(y44, 44100),
        energy=raw_energy(stats),
        segments=segments,
        bass_profile=ff.bass_profile_per_bar(np.asarray(downbeat_times)),
    )


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def analyze_library(music_dirs: list[Path], workers: int | None = None,
                    force: bool = False) -> list[TrackAnalysis]:
    cache = AnalysisCache(music_dirs[0])
    paths = discover_tracks(music_dirs)
    if not paths:
        raise SystemExit(f"no audio files found under {', '.join(map(str, music_dirs))}")
    fps = {p: fingerprint(p) for p in paths}

    records: dict[Path, TrackAnalysis] = {}
    todo: list[Path] = []
    for p in paths:
        rec = None if force else cache.get(fps[p])
        if rec is not None:
            rec.path = str(p)  # cache survives moves; refresh the path
            records[p] = rec
        else:
            todo.append(p)

    if todo:
        _progress(f"analyzing {len(todo)} new tracks ({len(records)} cached)")
        beat_engine = BeatEngine()
        n_workers = workers or max((os.cpu_count() or 4) - 2, 1)
        done = 0
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            pending = set()
            queue = list(todo)
            while queue or pending:
                while queue and len(pending) < n_workers * 2:
                    pending.add(pool.submit(_phase_a, str(queue.pop(0))))
                finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                for fut in finished:
                    try:
                        path_str, tags, ff = fut.result()
                        p = Path(path_str)
                        rec = _phase_b(p, fps[p], tags, ff, beat_engine)
                    except Exception as exc:
                        done += 1
                        _progress(f"  [{done}/{len(todo)}] skip {exc}")
                        continue
                    cache.put(rec)
                    records[p] = rec
                    done += 1
                    _progress(f"  [{done}/{len(todo)}] {rec.artist} - {rec.title} "
                              f"({rec.bpm:.1f} bpm, {rec.camelot or '?'}, "
                              f"{len(rec.segments)} segments)")

    # Byte-identical files in different dirs share a fingerprint: keep one copy
    seen_fp: set[str] = set()
    ordered = []
    for p in paths:
        rec = records.get(p)
        if rec is None or fps[p] in seen_fp:
            continue
        seen_fp.add(fps[p])
        ordered.append(rec)

    # Library-wide percentile normalization of raw energies
    track_raw = [r.energy for r in ordered]
    norm = normalize_energies(track_raw)
    ref = np.sort(np.asarray(track_raw))
    for rec, e in zip(ordered, norm):
        rec.energy = e
        for seg in rec.segments:
            rank = np.searchsorted(ref, seg.energy) / max(len(ref) - 1, 1)
            seg.energy = float(np.clip(rank, 0.0, 1.0))
    return ordered
