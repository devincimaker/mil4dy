# AI DJ research notes

Notes from a literature pass on **DJ mixing** (beatmatching, cue points, transitions, set generation), not studio mixing (stems → stereo).

Collected 2026-08-16. The 2025 survey’s verdict still holds: **no published automatic DJ has matched a human yet.**

- Survey: [Temporal Considerations in DJ Mix Information Retrieval and Generation](https://drops.dagstuhl.de/storage/00lipics/lipics-vol355-time2025/LIPIcs.TIME.2025.20/LIPIcs.TIME.2025.20.pdf) (Williams et al., TIME 2025)

---

## What “labeled mixes” means here

A useful training pair is:

**original tracks + a real DJ set + where each track sits in the set + (ideally) fader / EQ / filter moves**

Hundreds of thousands of DJ mixes exist on Mixcloud, MixesDB, 1001Tracklists, and SoundCloud. The scarce part is **labels**: complete tracklists, mix-in / mix-out alignment, and mixer state.

Largest published labeled collections:

| Dataset | What you get | Scale |
|---|---|---|
| KAIST DJ Mix Dataset | Real mixes + transitions; reverse-engineered fader/EQ | **5,040 mixes / 50,742 transitions** |
| Raveform (2026) | Mix links, tracklists, beat grids, mix-to-track alignment | **4,902 mixes / 56,873 tracks** |
| 1001Tracklists study (ISMIR 2020) | Mix-to-track alignment analysis | 1,557 mixes / 20,765 transitions |
| EDM-CUE | Human cue points | 4,710 tracks / **21k cues** |
| M-DJCUE | Human cue points | 134 tracks |
| UnmixDB | Synthetic beatmatched mixes with known ground truth | small, open audio |

~5k mixes / ~50k transitions is the published ceiling. Not 100k+.

Why 100k labeled mixes has not happened:

1. Complete tracklists are rare (1001Tracklists is the best source and still incomplete).
2. Alignment is hard: each original must be found inside a tempo-shifted, EQ’d, overlapping mix.
3. Mixer state is almost never logged. KAIST reverse-engineers faders/EQ.
4. Copyright: metadata and links can be published; 5,000 commercial sets cannot.

That is why most Auto-DJ products (rekordbox, Serato, djay, DJ.Studio) are still **rules + beatgrid + key**, not a net trained on 200k human sets.

---

## Analysis (measurement, not generation)

These papers do **not** build an AI DJ. They measure what DJs actually do.

### A Computational Analysis of Real-World DJ Mixes (Kim, Choi, Sacks, Yang, Nam — ISMIR 2020)

**Not an AI DJ.** Measurement paper.

Took 1,557 real 1001Tracklists sets, aligned each original track into the mix with beat-synchronous subsequence DTW (tempo- and key-invariant), then counted cue points, transition lengths, and tempo/key changes.

Findings on 1,557 mixes / 13,728 tracks / 20,765 transitions:

- 86% of plays are tempo-shifted less than 5%; almost everything stays under 10%.
- Only 2.5% of plays get a key change; of those, 94% are one semitone. Master Tempo stays on.
- Transition lengths peak every 32 beats (phrase-aligned).
- Cue points cluster: 24% of DJ pairs use the exact same cue; 74% are within 8 bars.
- Human “next track starts” annotations usually mark **cue-in**, not the start of the fade.

Later KAIST papers turn these measurements into reverse-engineered mixer state and then into an Auto-DJ demo.

- Paper: https://arxiv.org/abs/2008.10267
- Companion: https://mir-aidj.github.io/djmix-analysis/
- Code: https://github.com/mir-aidj/djmix-analysis/

### Reverse-engineering transitions (Kim, Yang, Nam — NIME 2021)

Recover DJ mixer control (sub-band / EQ) from real mixes via convex optimization.

- https://nime.org/proc/nime2021_87/

### Joint Estimation of Fader and Equalizer Gains (Kim, Yang, Nam — DAFx 2022)

Same idea at larger scale: **5,040 real-world mixes / 50,742 transitions**.

- PDF: https://mac.kaist.ac.kr/pubs/KimYangNam-dafx2022.pdf
- Dataset: https://github.com/mir-aidj/djmix-dataset
- Author page: https://taejun.kim/

### Raveform (Kim, Kim, Kim, Nam — TISMIR 2026)

Public dataset: 4,902 DJ mix links, 56,873 tracks, beat grids, mix-to-track alignment, plus 1,423 tracks with expert structure annotations. Also trains structure models for EDM.

- Paper: https://transactions.ismir.net/articles/10.5334/tismir.288
- Site: https://mir-aidj.github.io/raveform/

### UnmixDB (Schwarz & Fourer, 2018–2019)

Synthetic beat-synchronous mixes with known ground truth, for reverse-engineering methods. Not human DJ behavior.

- Dataset: https://zenodo.org/records/1422385
- Paper: https://hal.science/hal-02010431
- Methods survey: https://hal.science/hal-02172427v1/document

---

## Full Auto-DJ systems

These take a crate and output a mix. Almost all are **rule pipelines**.

| Paper | Does it mix? | Learned from DJs? |
|---|---|---|
| Ishizaki et al. 2009 | Full set | No — tempo discomfort model |
| Vande Veire 2018 | Full set | No — MIR rules |
| Spotify / Bittner 2017 | Sequence + fade | No — optimization |
| Highlight mix 2017 | Full set | No — highlight model |
| DJnet 2017 | Vision / demo | Early proposal |
| **DJtransGAN 2022** | Transitions only | **Yes — real mixes** |
| StructFreak 2023 | Full demo | Structure model + rules |
| Mosaikbox 2024 | Full set | No — stems + rules |
| DJ-AI 2025 | Sequence + fades | Embeddings / gen models |

### From raw audio to a seamless mix (Vande Veire & De Bie, 2018)

The classic complete pipeline. Beat / downbeat / structure → cue points → phrase-aligned blends. Built for drum & bass. Rules, not a trained mixer. Runnable.

- https://asmp-eurasipjournals.springeropen.com/articles/10.1186/s13636-018-0134-8
- Blog: http://lenvdv.github.io/2018-03-20-autodj/
- Code: https://github.com/lenvdv/auto-dj

### Automatic Playlist Sequencing and Transitions (Bittner et al., Spotify, ISMIR 2017)

Order the playlist (graph search), then optimize a DJ-style crossfade. Evaluated by professional curators. Ancestor of Spotify Automix.

- https://archives.ismir.net/ismir2017/paper/000086.pdf
- Spotify page: https://research.atspotify.com/publications/automatic-playlist-sequencing-and-transitions

### Automatic DJ Mix Generation Using Highlight Detection (Kim, Park, Nam et al., ISMIR 2017 LBD)

Pick the “highlight” of each track, sequence those clips, blend. Full mix from a pool.

- https://www.researchgate.net/publication/322007163_Automatic_DJ_Mix_Generation_Using_Highlight_Detection

### DJnet (Huang, Chou, Yang, ISMIR 2017 LBD)

Stated goal: a fully automatic DJ for medleys, mashups, remixes, even EDM. Early vision paper.

- https://remyhuang.github.io/files/huang17ismir-lbd.pdf

### DJ StructFreak (Kim & Nam, ISMIR 2023 LBD)

Same KAIST lab as the 1001Tracklists analysis. Actual AI DJ demo: structure embeddings pick mix points; user can override cues.

- Demo: https://taejun.kim/dj-structfreak
- Lab: https://mac.kaist.ac.kr/ai_dj.html
- Abstract: https://ismir2023program.ismir.net/lbd_328.html

### Mosaikbox (Sowula & Knees, ISMIR 2024)

Newest full-system paper. Song selection + automatic mixing, **rule-based stem edits** (mute/swap drums, etc.) + a tighter beatgrid. Beat a baseline in listening tests. Still rules.

- https://doi.org/10.5281/zenodo.14877463

### DJ-AI (Kınay et al., 2025)

Graph sequencing + generative/embedding models for transitions.

- https://dl.acm.org/doi/10.1145/3771594.3771640

### Full-Automatic DJ Mixing System (Ishizaki et al., ISMIR 2009)

Older ancestor. Tempo-adjust so the blend does not feel uncomfortable.

- https://ismir2009.ismir.net/proceedings/PS1-14.pdf

---

## The one that learns from real DJ mixes

### DJtransGAN (Chen, Hsu, Liao, Martínez-Ramírez, Mitsufuji, Yang — Sony + Academia Sinica, ICASSP 2022)

Closest published “train on human DJ transitions” result.

A GAN watches real Livetracklist mixes. The generator uses a **differentiable EQ + fader** to mix two tracks. It learns *how* to fade and EQ-kill, not just “crossfade for 32 bars.” Listening tests: it developed a style, but also did un-DJ things. Still the main learned-transition paper.

- https://arxiv.org/abs/2110.06525
- Code: https://github.com/ChenPaulYu/DJtransGAN
- Data pipeline: https://github.com/ChenPaulYu/DJtransGAN-dg-pipeline
- Sony writeup: https://www.sony.com/en/SonyInfo/technology/publications/automatic-dj-transitions-with-differentiable-audio-effects-and-generative-adversarial-networks/

---

## Cue points (one DJ job, not a full set)

- **EDM-CUE** — 21k human cue points on 4,710 tracks; object-detection model.  
  Paper: https://arxiv.org/abs/2407.06823  
  Dataset: https://huggingface.co/datasets/disco-eth/edm-cue
- **M-DJCUE** — 134 expert-annotated EDM tracks.  
  Paper: https://arxiv.org/abs/2007.08411  
  Dataset: https://github.com/MZehren/M-DJCUE
- Heuristic cue estimation: Schwarz, Schindler, Spadavecchia — “A heuristic algorithm for DJ cue point estimation” (SMC 2018).

---

## Suggested reading order

1. **Vande Veire 2018** — complete pipeline you can run.
2. **DJtransGAN 2022** — the only one that learned blend behavior from real mixes.
3. **Mosaikbox 2024** — current best full-system paper.
4. **Kim et al. 2020** (`2008.10267`) — the measurement step those systems sit on.
5. **Williams 2025** — map of the field and why end-to-end is hard.

KAIST’s public path toward a learned DJ is: measure mixes (2020) → recover fader/EQ (2021–22) → Raveform structure data (2026) → StructFreak demo (2023).

---

## Related but not DJ mixing

An earlier pass mixed this up with **studio automatic mixing** (gain, EQ, compression, stems → stereo). Different field, different datasets (MedleyDB, MoisesDB, MEGAMI). Living bibliography for that: https://csteinmetz1.github.io/AutomaticMixingPapers/

Do not treat those papers as AI DJ work.
