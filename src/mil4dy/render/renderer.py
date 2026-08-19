"""Render orchestrator: MixPlan -> mastered audio file."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from ..analysis.decode import RENDER_SAMPLE_RATE as SR
from ..schemas import MixPlan
from .audio_io import encode_mp3, write_wav
from .automation import apply_deck_automation
from .envelopes import db_to_amp
from .fx import echo_out
from .master import master_chain, measure_lufs
from .timeline import build_clock, schedule_track

PER_TRACK_LUFS = -16.0
END_FADE_S = 6.0


def _log(msg: str) -> None:
    try:
        print(msg, file=sys.stderr, flush=True)
    except BrokenPipeError:
        pass


def render_mix(plan: MixPlan, output: Path, wav: bool = False,
               debug_transition: int | None = None,
               end_fade_s: float | None = None,
               encode: bool = True) -> dict:
    clock, entries = build_clock(plan)
    n = len(plan.tracks)
    total = clock.total_samples
    master = np.zeros((total + 5 * SR, 2), np.float32)

    for i in range(n):
        t = plan.tracks[i]
        _log(f"rendering {t.id}: {t.artist} - {t.title}")
        st = schedule_track(plan, i, clock, entries)

        # Refine loudness on the actually-used region
        lufs = measure_lufs(st.audio)
        st.audio *= np.float32(db_to_amp(PER_TRACK_LUFS - lufs))

        # Capture echo material before fades (last beat before the overlap ends)
        echo_src = None
        if i < n - 1 and "echo_out" in plan.transitions[i].fx:
            a = int(st.beat_out_samples[st.n_beats - 1] - st.offset)
            b = int(st.beat_out_samples[st.n_beats] - st.offset)
            echo_src = st.audio[a : min(b, len(st.audio))].copy()

        if i > 0:
            tr = plan.transitions[i - 1]
            length = tr.length_beats
            r1 = int(st.beat_out_samples[min(length, st.n_beats)] - st.offset)
            beat_pos = np.interp(
                np.arange(st.offset, st.offset + r1),
                st.beat_out_samples[: length + 1].astype(np.float64),
                np.arange(length + 1, dtype=np.float64),
            )
            apply_deck_automation(st.audio, 0, r1, beat_pos, tr, "in")

        if i < n - 1:
            tr = plan.transitions[i]
            length = tr.length_beats
            k0 = st.n_beats - length
            r0 = int(st.beat_out_samples[k0] - st.offset)
            r1 = len(st.audio)
            beat_pos = np.interp(
                np.arange(st.offset + r0, st.offset + r1),
                st.beat_out_samples[k0 : st.n_beats + 1].astype(np.float64),
                np.arange(length + 1, dtype=np.float64),
            )
            apply_deck_automation(st.audio, r0, r1, beat_pos, tr, "out")

        end = min(st.offset + len(st.audio), len(master))
        master[st.offset : end] += st.audio[: end - st.offset]

        if echo_src is not None:
            echo_out(master, echo_src, int(st.beat_out_samples[st.n_beats]),
                     plan.transitions[i].tempo_ramp.to_bpm)
        del st

    # End-of-mix fade
    fade_s = END_FADE_S if end_fade_s is None else max(end_fade_s, 0.0)
    fade_n = int(fade_s * SR)
    if fade_n > 0:
        fade_n = min(fade_n, total)
        fade_db = np.linspace(0.0, -60.0, fade_n)
        master[total - fade_n : total] *= db_to_amp(fade_db).astype(np.float32)[:, None]
    master = master[:total]

    if debug_transition is not None:
        idx = debug_transition - 1
        if not 0 <= idx < len(plan.transitions):
            raise SystemExit(f"transition {debug_transition} out of range "
                             f"(1..{len(plan.transitions)})")
        tr = plan.transitions[idx]
        start_beat = entries[idx + 1]
        pad = 8
        a = clock.beat_samples[max(start_beat - pad, 0)]
        b_idx = min(start_beat + tr.length_beats + pad, clock.n_beats - 1)
        b = clock.beat_samples[b_idx]
        out = output.parent / f"{output.stem}.transition{debug_transition}.wav"
        seg, report = master_chain(master[a:b], plan.target_lufs)
        write_wav(seg, out)
        _log(f"wrote {out} ({tr.type}, {tr.length_beats} beats) {report}")
        return report

    _log("mastering...")
    mastered, report = master_chain(master, plan.target_lufs)
    _log(f"master: {report}")

    if encode:
        encode_mp3(mastered, output)
    if wav or not encode:
        write_wav(mastered, output.with_suffix(".wav") if encode else output)
    return report
