# YuE2 media engine (M0-S) — results

Arch v0.16 §10.5 and M0-S: can YuE2 sing a supplied melody and produce a usable soft accompaniment on the dev box's 16 GB GPU?

**Setup (2026-09-24):**
- **Software:** YuE2 (`yue2-infer` 0.1.6, commit `09a1e8a`; weights YuE2-3B `14fc6c6`, YuE2-Vae `9a94e1d`), PyTorch 2.10.0+cu128, Demucs 4.1.0 (htdemucs) for stems, and librosa 1.0.0 for analysis.
- **Install:** all in one venv at `~/engines/yue2`, about 15 GB; delete that folder to remove it.
- **Skill:** the installer, the front end (`generate_music.py`) and the worker are part of the user-level Claude skill `~/.claude/skills/generate-music`, which does generic text-to-music. Piano-Master is its `piano-master` profile. A backup copy is in [../../skills/](../../skills/).
- **Test material:** in this folder. All test songs use original lyrics and melodies.

**Engine settings:** default full quality (`memory_budget_gib 16`, no offload, no FP8). No out-of-memory fallback was needed.

| # | Test | Result | Numbers |
| --- | --- | --- | --- |
| 1 | Environment: GPU visible, sm_120 in the torch build, BF16, weight hashes | **Pass** | RTX 5070 Ti, sm_120, CUDA 12.8 build on driver 590 |
| 2 | Generic text-to-song ("Autumn Road", folk, YuE2 writes its own melody and chords) | **Pass** | 133 s song rendered in 55 s; **peak VRAM 7.95 GiB**; not truncated |
| 3 | Same request and seed, with stems | **Pass** | Byte-identical audio to test 2 (deterministic); Demucs 7.5 s, 0.8 GiB; stems the same length as the mix and audible |
| 4 | Piano-Master profile, **supplied melody and chords** ("Garden Morning", 16 bars, C major, 96 BPM, nursery genre); plus a variant with a 2-bar instrumental intro | **Pass** | 41.7 s song (score says 40.0 s) in 19 s + 3 s stems; peak VRAM 7.8 GiB. Intro variant: 47.8 s (score 45.0 s) |
| 5 | Input contract: bad ABC / tempo mismatch rejected before the GPU; no overwrite | **Pass** | All exit 2 with a clear message |
| 6 | Listening on the iPad (non-expert listeners): <https://192.168.2.128/listen/> | **Pass** | Garden Morning and Autumn Road: all Yes (melody followed, words clear, accompaniment soft and in time, clean split, usable). Note: in Autumn Road the vocals come in before the reference notes (see test 7) |
| 7 | Timing and pitch vs the score ([analyze_vocal.py](analyze_vocal.py): pYIN pitch + DTW alignment; a first cut of §10.5 steps 3-4) | **Pass** (pitch) | Pitch on target after alignment: **92%** Garden Morning, **98%** Garden Morning + intro, **96%** Autumn Road (§10.5 bar: 90%). Timing vs score: Garden Morning within about ±0.1 s; with intro 0.4 s late rising to 0.8 s late; Autumn Road 2.5 s early drifting to 3.7 s early |

**Findings:**
- **16 GB is enough.** YuE2 peaks at about 8 GiB at full quality, so the official 24 GB figure is conservative for songs of this length. It is also fast: about 0.4× real time (a 2-minute song renders in about a minute).
- **It sings the notes it is given.** With a supplied melody, 92-98% of notes land on the right pitch after alignment, and the listeners heard the melody followed.
- **Timing follows the score only approximately.** With a supplied score and no intro, the vocal stayed within about ±0.1 s of the score. With a 2-bar intro it settled about 0.8 s late. When YuE2 writes its own plan, the recording drifts from that plan (Autumn Road: vocals 2.5 s early at the start, 3.7 s early by the end, about 1.3% fast). This is what the listeners heard as the reference coming in after the words. So the §10.5 **alignment step (time-warp to the beat grid) is required**, not optional; the DTW alignment in `analyze_vocal.py` is a working starting point for it. The measurement resolution is about 0.1-0.2 s.
- **YuE2 outputs a single mix**; Demucs splits it in seconds and the listeners rated the split clean.
- **The accompaniment stem is louder than the vocal** (about -17 vs -20 dBFS RMS) despite "soft, sparse, background" in the prompt. The planned loudness step (§10.5 step 8) has to set the balance; the prompt alone doesn't.
- **Scores must be in YuE2's native two-voice ABC dialect.** A MusicXML → native ABC converter is needed before real arrangements can be used (a new work item for M8).
- **Measuring pitch needs an energy gate**: the separated vocal stem carries faint instrument bleed (about -75 dBFS) that a pitch tracker will otherwise follow.

**Outcome so far:** go for YuE2 as the media engine, with the alignment step built in. Listening was by non-experts, so a musician's listen is still worth getting.

**Still open (rest of M0-S):** word accuracy (Whisper), accompaniment timing and harmony checks, the 90/75/50% time-stretch versions, and trying more songs and genres (only three short renders so far).

## Reproduce

```bash
~/engines/yue2/.venv/bin/python run_tests.py                          # tests 1-5 -> results/ (gitignored)
~/engines/yue2/.venv/bin/python analyze_vocal.py results/garden-morning results/autumn-road-stems
~/engines/yue2/.venv/bin/python build_listen_site.py results/garden-morning results/garden-morning-intro results/autumn-road-stems
./deploy_listen.sh                                                    # -> https://192.168.2.128/listen/
```
