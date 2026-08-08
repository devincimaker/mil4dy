# mil4dy 0.2 — Offline Professional DJ Mix Engine

Turns folders of MP3s into an analyzed, planned, professionally rendered DJ mix.

```bash
uv run mil4dy doctor                              # check ffmpeg / rubberband / ML deps
uv run mil4dy analyze DIR [DIR ...]               # pre-warm the analysis cache
uv run mil4dy plan DIR [...] --minutes 30 --json output/plan.json
uv run mil4dy mix  DIR [...] --minutes 30 --output output/mix.mp3
uv run mil4dy mix  ... --debug-transition 6       # one transition ±8 beats as WAV
```

System deps: `brew install ffmpeg rubberband` (rubberband ≥ 3 for the R3 engine).
Python 3.12 via uv; first analyze run downloads beat_this model weights (~80 MB).

## How it works

1. **Analysis** (cached per content fingerprint in `<first_dir>/.mil4dy/cache/v2/`):
   beat_this beats + downbeats, essentia EDMA key → Camelot code, SSM/Foote
   structure segmentation labeled intro/build/drop/breakdown/verse/outro,
   LUFS, per-segment energy + vocal likelihood, per-bar bass profile.
   Byte-identical files in different folders are deduplicated automatically.
2. **Planner**: beam search orders tracks along an energy arc (warm-up → peak →
   cooldown) and a gradual tempo journey, scoring harmonic compatibility
   (confidence-weighted Camelot). Cues come from structure: mix out of
   outros/breakdowns, into intros, with the incoming track's first drop landing
   exactly at the transition end. A decision table picks the transition type:
   `long_blend_bass_swap`, `filter_sweep`, `breakdown_blend`, or `quick_cut`
   (with echo-out) when both overlap windows carry vocals.
3. **Renderer**: an OutputClock assigns every set beat an exact output sample;
   tracks are stretched with piecewise constant-ratio Rubberband R3 pinned to
   that grid (<1 ms beat alignment, verified by click-track tests). Transitions
   run automation lanes: LR4 120 Hz crossover bass swap, time-varying SVF
   filter sweeps, dB-domain gain ramps, tempo-synced echo tails. Master chain:
   per-track −16 LUFS pregain → −10 LUFS target (or `--loudness streaming` for
   −14) → true-peak lookahead limiter at −1 dBTP.

Tests: `uv run pytest` — synthetic click tracks assert sub-millisecond beat
alignment through tempo ramps; Goertzel/FFT assertions cover bass swap depth,
crossover flatness, sweep attenuation, LUFS targets, and the limiter ceiling.
