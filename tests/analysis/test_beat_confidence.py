"""Beat confidence must be computed, never the literal 0.9."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from mil4dy.analysis.beats import beat_confidence, regularize_beats


BEATS_SRC = Path(__file__).resolve().parents[2] / "src" / "mil4dy" / "analysis" / "beats.py"


def test_no_hardcoded_point_nine_confidence():
    src = BEATS_SRC.read_text()
    assert "0.9" not in src.split("regularize_beats")[0] or (
        "return np.asarray(beats), np.asarray(downbeats), 0.9" not in src
    )
    assert "return np.asarray(beats), np.asarray(downbeats), 0.9" not in src
    assert ", 0.9)" not in src.replace("int(n * 0.9)", "")


def test_regular_grid_scores_high():
    bpm = 125.0
    beats = np.arange(0.0, 180.0, 60.0 / bpm)
    score = beat_confidence(beats, 180.0, bpm)
    assert score >= 0.85
    assert score != 0.9 or abs(score - 0.9) > 1e-12 or score > 0.95


def test_walk_with_me_intro_slice_scores_low():
    pattern = np.array([0.22, 0.36, 0.48, 0.72])
    rng = np.random.default_rng(3)
    iv = rng.choice(pattern, size=80)
    beats = np.concatenate([[0.0], np.cumsum(iv)])
    score = beat_confidence(beats, float(beats[-1]), 125.0)
    assert score < 0.6


def test_regularize_does_not_invent_point_nine():
    beats = np.arange(0.0, 60.0, 60.0 / 125.0)
    downs = beats[::4]
    *_, conf, _, _ = regularize_beats(beats, downs, 60.0)
    assert conf != pytest.approx(0.9)
    assert 0.0 <= conf <= 1.0


@pytest.mark.slow
def test_click_track_through_beat_engine():
    pytest.importorskip("beat_this")
    pytest.importorskip("torch")
    from mil4dy.analysis.beats import BeatEngine
    from mil4dy.planner.grid import grid_ok, window_span_s
    from tests.render.synth import click_track

    audio, _ = click_track(125.0, 64)
    mono = audio.mean(axis=1)
    engine = BeatEngine(device="cpu")
    beats, _, conf, _, _ = engine.detect(mono, 44100)
    if len(beats) < 16:
        pytest.skip("detector returned too few beats on a click track")
    mid = beats[len(beats) // 4 : 3 * len(beats) // 4]
    local = 60.0 / float(np.median(np.diff(mid))) if len(mid) > 2 else 0.0
    assert abs(local - 125.0) < 4.0
    n = min(32, len(beats) - 1)
    assert grid_ok(window_span_s(beats, 0, n), 125.0, n) or conf > 0.5
