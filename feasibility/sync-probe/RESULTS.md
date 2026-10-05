# Song clock, media alignment and real notation (tests 2, 3 and 4)

Arch v0.16 §3 ("one song-clock position drives the staff, audio, lyrics and scoring"), §5 (notation format), §10.5 steps 3, 4 and 7 (alignment, pitch check, tempo versions), §12 M0-S "still open". Run 2026-09-25 on the dev box and the iPad; round 4 (YuE2 input, one note per syllable) 2026-09-26. Feasibility closed: see "Where the vocal problems come from" for the decision and known issues.

**Page:** <https://<piano-server>/sync/> (round-4 takes deployed 2026-09-27) ([site/index.html](site/index.html)). Pipeline: see "Reproduce" at the end.

## Songs (real public-domain sources, no hand edits)

| Song | Source | What it exercises |
| --- | --- | --- |
| Amazing Grace | Open Hymnal ABC Plus, SATB | 3/4, pickup, 5 verses, slow hymn |
| What Child Is This? | Open Hymnal ABC Plus, SATB | 3/4, E minor (written with 2 sharps), pickup, dotted and sixteenth figures, 3 verses |
| It Came Upon a Midnight Clear | Open Hymnal ABC Plus, SATB | 6/8, pickup, 5 verses |
| Jeanie with the Light Brown Hair | music21 corpus, MusicXML lead sheet | 4/4, repeat with first and second endings, 2 verses, 40 chord symbols, treble staff only |
| Was mein Gott will (Bach BWV 103.6) | music21 corpus, MusicXML, 4 vocal staves | Four staves reduced to a grand staff, repeat with 2 verses, fermatas; staff only (German words) |

Excluded: the corpus's *Alexander's Ragtime Band*. The song (1911) is public domain, but the file says "All Rights Reserved", so the edition isn't openly licensed (§10.4). Hymnary.org and CPDL refuse scripted downloads (HTTP 403), so they weren't used.

## Test 4: real notation → §5 format → staff

**Result: pass in headless Chromium at iPad size; confirm on the iPad.** All 5 sources convert and render with 0 problems: 20–85 measures in playback order, 13–68 ms to render, 4,500–18,700 px wide, every lyric syllable placed. Screenshots show correct pickups, ties, dots, beaming (including 6/8), accidentals, two voices per staff, fermatas and chord symbols.

Findings:
- **music21 can't read Open Hymnal's ABC Plus.** It merges the four voices into one part (68 bars instead of 17) and drops every lyric. [abc2xml](https://wim.vree.org/svgParse/abc2xml.html) → MusicXML → music21 works. The import skill needs this step for ABC sources.
- **§5 needs a pitch spelling on each note.** A MIDI number alone can't draw F♯ vs G♭, or name a chord (B major came out as "Cb" until spelling was used). The converter adds `spelled {step, alter, octave}`. §5 also stores no rests; the renderer fills the gaps, which worked.
- **The moving staff renders the playback order unrolled.** Repeats, endings and verses become one long line with the right verse's words under each pass. No repeat signs are drawn, which suits the moving staff.
- **YuE2's `K:` field needs the key the song is in, not the written signature.** What Child Is This is written with two sharps but is in E minor. The converter takes the tonic from the final bass note.
- Pickups can be written as a short first bar or as a full bar starting with rests (Jeanie). Phrase detection handles both. Phrases come from the metric grid, moved back to include pickup notes at a word start. Verse 2 of What Child Is This gets one odd phrase start ("for you."), because its words sit differently on the same notes.
- **Hymn chord symbols can be derived** from the four voices on each beat (G, D7/C, Am/C, B …) for YuE2's `plan full` and later the §10.5 harmony check.

## Test 3: alignment, 50% quality, realistic songs

**Round 1** (first takes, no lead-in; superseded by round 2 below). Renders: YuE2 through the `generate-music` skill (piano-master profile), 43–77 s per song, peak VRAM about 8 GB, nothing truncated. Measurements are from [align.py](align.py). "Windows" are 3-second stretches of the song, measured every 0.5 s, in which the sung pitch curve is lined up against the score's.

| Song (length) | YuE2 timing before alignment | After, 100% (median / p95) | Held-out (median / p95) | After, 50% (median / p95) | Pitch on target (before → 100% / 50%) |
| --- | --- | --- | --- | --- | --- |
| Amazing Grace (142 s) | starts 1.1 s early, drifts 3.0 s (2% fast) | 7.7 / 38.5 ms | 16 / 100 ms | 19 / 84 ms | 98% → 98% / 98% |
| What Child Is This (109 s) | 1.2 s early, drifts 1.3 s | 3.7 / 17.4 ms | 9 / 21 ms | 13 / 51 ms | 97% → 96% / 96% |
| Midnight Clear (173 s) | 1.2 s early, no drift | 5.5 / 18.4 ms | 9 / 25 ms | 34 / 67 ms | 98% → 98% / 96% |
| Jeanie (203 s) | 1.7 s early, no drift | 9.0 / 70.2 ms | 14 / 88 ms | 24 / 126 ms | 99% → 98% / 98% |

50% figures are in stretched time (what the child hears); halve them for score time. Estimator accuracy (the ruler: a known ±100 ms wobble applied and measured back): 13–16 ms median, 42–49 ms p95.

**Alignment precision:** works, with a caveat about the 50 ms rule.
- On 3 of 4 songs, 95% of windows land within 40 ms at 100%. Jeanie reaches 70 ms at p95, with 6% of windows over 50 ms.
- The ruler's own p95 (about 45 ms) is close to the §10.5 bar of "drift over about 50 ms fails". So this method can certify a *median* comfortably, but not a strict 50 ms p95.
- Suggested rule for §10.5: fail a take on a sustained offset (median over a phrase) above 50 ms, not on single windows.

**What had to change to get there:**
- **Picking single note onsets fails.** Vibrato and breaths fool it: the ruler's p95 was 265 ms. Lining up pitch curves in windows works.
- **Rubber Band's time map needs a second pass.** A time map with points every 0.5 s leaves the output about 25 ms late. Measuring once and correcting the map removes this (Amazing Grace: 25 → 8 ms median).
- **Rubber Band's Python bindings can't pass a time map.** The Rubber Band 4.0 command line from conda-forge does.
- **YuE2 ignores leading rests.** Every take starts singing at once, 1.1–1.7 s before the score's pickup, so alignment is required (as M0-S found).

**50% tempo quality:**
- **YuE2 can't render a slow take.** Asked for 50 BPM it sang at about 73; asked for 40, about 70. Its "slow takes" still need a 1.5–1.8× stretch, so a native slow render is not a real alternative to Rubber Band.
- Both 50% versions keep 91–98% of notes on pitch.
- **iPad listening:** stretched 50% is fine. The slow take only sounded better at the start, which was the start problem fixed in round 2. **Decision: 50% comes from Rubber Band**, and the slow-take option has been removed from the page.

**Accompaniment:** the onset check is weak on soft, sparse backings (clear onsets on only 15–85% of beats), so it can't confirm the backing timing well. Jeanie's guitar backing went from 92 ms to 35 ms median off the grid. For the other songs the measure sat at about 50 ms both before and after alignment, which is within its noise. The vocal and backing are warped with the same map, so they stay together.

**Download sizes** (128 kbps MP3, vocal + backing): 4.5–8.2 MB at 100% and 8.9–16.4 MB at 50%. At the server's measured 0.93 MB/s, that is 5–9 s to load at 100% and 10–18 s at 50%.

### Round 2: the song starts (after the iPad listening)

**Cause:** YuE2 ignores the rests before the pickup: every round-1 take started singing 1.1–1.7 s early. The aligner then squeezed everything before its first reliable window into the score's start (a 2× stretch on Amazing Grace, the wobble heard at every speed). Twice YuE2 also dropped the pickup word itself ("What", "It").

**Changes:**
- **Lead-in before the song:** two variants, same seed.
  - *intro*: 2 instrumental bars, tonic then dominant seventh.
  - *fake*: an extra bar with a throwaway sung "Oh" on the first melody pitch. It's muted after alignment, since the song's start is known. The fake note was the user's idea.
- **Aligner:**
  - The offset is held constant before the first anchor: the input is padded or trimmed, with no stretch there.
  - The vocal is muted before the song's first note.
  - A new check reports melody notes that weren't sung, and whether the first one was.
  - The anchor filter now drops only isolated spikes. It used to also drop real steps where YuE2 holds a long note longer.
- **Takes selected with a quality rule:** first note sung, at least 90% on pitch, then lowest p95. The page's **Take** menu lists the selected take first.

| Song | Take used | Start before alignment | 100% (median / p95) | Held-out p95 | 50% (median / p95) | Pitch | First note sung, notes not sung |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Amazing Grace | intro | +0.17 s | 6.7 / 33.7 ms | 44 ms | 29 / 94 ms | 98% | yes, 0 |
| What Child Is This | fake | +0.05 s | 4.2 / 19.0 ms | 17 ms | 16 / 57 ms | 99.5% | yes, 0 |
| Midnight Clear | fake | +0.04 s | 8.1 / 33.0 ms | 69 ms | 23 / 76 ms | **89%** | yes, 4 (a D5 in verses 2–4) |
| Jeanie | intro | +0.35 s | 10.7 / 53.9 ms | 141 ms | 35 / 134 ms | 92% | yes, 0 |

The other takes: the intro takes of What Child Is This and Amazing Grace are as good. The intro take of **Midnight Clear dropped "It" again**, while its fake-note take sang it, so the fake note was more reliable for the first word (4 of 4 songs, against 3 of 4). Jeanie's fake-note take was worse (p95 108 ms). Take lengths now match the score within about 1% (round 1: up to 2.5% fast).

**Takeaways for §10.5:**
- Always add a lead-in. The fake note protects the first word better; the intro gives a natural start.
- Midnight Clear still misses the 90% pitch bar, so it would get a third take with another seed. This is the "retry up to 3 takes" step, driven by these checks.
- Jeanie (slow ballad, long notes) is the hardest to align: fewer reliable windows, and the timing varies between takes.

### Round 3: lyric alignment as the backbone (2026-09-25)

**Round 2 iPad listening:**
- Amazing Grace: both takes in sync.
- What Child Is This: the fake-note take was off for the first ~8 words; the intro take was badly off from word 4 until "lies He in".
- Midnight Clear: the intro take lost "It", then corrected after ~8 words.
- Jeanie: the fake-note take's lyrics led by several words for half the song, then lagged by about a word.
- The backing was inaudible on the iPad. **Cause:** 84–99% of YuE2's backing energy is below 250 Hz, which tablet speakers barely play, and the level had been set from that bass. **Fix:** a gentle cut below 120 Hz, then the backing is set 10 dB under the vocal as measured above 250 Hz. The page also gained a backing volume control (0–300%).

**Lyric alignment works and matched every problem heard on the iPad.**
- **Method:** [lyric_align.py](lyric_align.py) uses `ctc-forced-aligner`'s ONNX aligner model (1.26 GB, in its own venv `.fa`) to find where each known word starts. It takes about 30 s per song on the CPU. Its own helper rounds the frame stride to a whole millisecond (seconds of drift over a song), and it crashes on accented letters; both are worked around.
- **Test:** each word was placed two ways, by lyric alignment and by the round-2 melody-based map. Where the two disagreed, the stretches matched every report above:
  - What Child fake-note take: words 2–8, +0.5 s.
  - What Child intro take: words 4–53, "who" … "mean", +4.4 s.
  - Midnight Clear intro take: words 0–7.
  - Jeanie fake-note take: words 0–66 at −4.7 s, then words 72–99 at +0.9 to +1.8 s.

  In each, the melody-only aligner had matched a repeated melody, or the held "Oh" on the first word's pitch, to the wrong place.
- **Extra stretches:** the comparison also flagged stretches nobody reported (Amazing Grace verse 3, one line of every Midnight Clear verse). A rough transcription from the aligner's model confirms Amazing Grace's: at 80–86 s YuE2 sings "…thus far / and grace will lead / me home" 1–3 bars before the notes those words belong to.

**Aligner, round 3** ([align.py](align.py)):
1. Word anchors are the coarse map.
2. Pitch windows refine it, searching only ±0.35 s around the word map.
3. Word anchors fill any gap without a pitch anchor.
4. **Two-sided check** on the aligned 100% vocal:
   - words: lyric alignment again, flagging any stretch of words more than 0.3 s off;
   - melody: runs of 4 or more notes sung on the wrong pitch;
   - also pitch at least 90% and the first note sung.

   Stretches are reported by word or time.
- The fake note now sits on a different pitch from the first word (tonic, or dominant when the song starts on the tonic).
- Two more seeds per song were rendered.

**Result: 0 of 16 takes pass** (4 songs; intro and fake-note takes; 3 seeds for the fake note). With words as the backbone the words land on the staff, but only 17–83% of notes are then on pitch (96–99% when the melody drives the warp). The key is not the problem: every take is in the written key, sung an octave lower. In every take, over stretches of several words, YuE2 sings the words on different notes than the score puts them, so no single time warp can line up both.

**Conclusion (round 3):** with the inputs as written, YuE2 can't be relied on for sung vocals whose words land on the right notes. Better alignment can't fix a take whose words and melody disagree. Round 4 found the main input-side cause.

### Round 4: one Vocal note per sung syllable (2026-09-26)

**Why:** a review of YuE2's inputs ([YuE2 Lyrics & Melody Input — Agent Instructions](../../YuE2%20Lyrics%20%26%20Melody%20Input%20—%20Agent%20Instructions.md), repo root) proposed one Vocal attack per sung syllable. Our converter had sent every hymnal note. Wherever a syllable is held over two or more notes (a melisma, e.g. "A-ma-**zing**" on B–G), YuE2 got more notes than syllables:

| Song | Notes sent | Syllables | Extra notes |
| --- | --- | --- | --- |
| Amazing Grace | 175 | 140 | 35 (20%) |
| What Child Is This | 213 | 171 | 42 (20%) |
| Midnight Clear | 330 | 283 | 47 (14%) |
| Jeanie | 180 | 172 | 8 (4%) |

**What YuE2 does itself:** asked to write its own melody for these lyrics ([plan_test.py](plan_test.py), no ABC supplied), it uses 1.01–1.10 attacks per syllable, i.e. almost one note per syllable. The spike's Autumn Road plan is exactly one per syllable. Nothing in YuE2 splits the lyrics into syllables or checks the count: the lyrics go into the prompt as plain text, and the pairing is learned.

**Two new input styles**, both with the fake-note lead-in and the same 3 seeds as the earlier fake-note takes ([convert.py](convert.py) `syllabic_melody`):
- **`syl`:**
  - each note without a syllable of its own is merged into the syllable's note, held on its first pitch (B–G on "zing" becomes one B);
  - the converter checks, with YuE2's own ABC parser, that the Vocal attacks equal the syllables, one per syllable beat;
  - `L:1/32` (YuE2's own grid);
  - chords kept, so `cot=full`.
- **`mel`:** the same, but chord-free, so `cot=melody` (the document's recommended mode).

The staff and the piano part are unchanged. Only the sung line loses the melismas, and the pitch check measures against the line actually sent.

**Result ([compare_styles.py](compare_styles.py), 12 takes per style):**

| Input style | Words >0.3 s off, melody-aligned | Notes on pitch, words-aligned | Takes passing the strict QA | Backing plays the written chord ([harmony.py](harmony.py)) |
| --- | --- | --- | --- | --- |
| As written (rounds 2–3) | 39% | 60% | 0 of 12 | 56% |
| **`syl`** | **12%** | **85%** | **3 of 12** | 57% |
| `mel` | 11% | 77% | 2 of 12 | 40% |

- **Words vs melody:** the two methods now agree far more often. The melody-aligned measure counts words sung on other notes than the score gives them. Per song, the best-scoring take's score rose from +0.70 to +0.93 on average.
- **First passes:** these are the first takes to pass the strict two-sided QA (Amazing Grace seeds 1 and 2; What Child seed 3).
- **Remaining misses:** misplaced stretches still occur, but fewer and shorter (0.8–1.6 per take, against 2.2–5.7).
- **Seeds still matter:** one Jeanie `syl` seed has 25% of words off.
- **Chord-free (`mel`):** no better for the vocal, and the backing strays from the written chords (40% of chord spans against 56–57%). The child's piano plays those chords, so `mel` isn't used.
- **Section counts:** "attacks = syllables in every section" can't hold exactly, because a pickup syllable sits in the previous section's last bar. YuE2's own plans place pickups the same way. The converter checks the whole song and every syllable's beat instead.
- **Split-vowel lyrics:** the document's third melisma option ("Amazi-ing") wasn't tried. It puts non-words into the lyrics, which the word check can't align.

**Decision:** the app's YuE2 input follows `syl` (one Vocal attack per syllable, chords kept). The trade-off: the singer holds one pitch where the staff shows a slurred pair. That's audible but small, and far less distracting than words on the wrong notes.

**Does one note per syllable remove the need for alignment? No.** The time maps of the 12 `syl` takes, against the 12 earlier fake-note takes, show:

| | As written | `syl` |
| --- | --- | --- |
| Take length vs score | 0.99–1.11× | 0.98–1.06× |
| Overall tempo error (median / worst) | 0.3–0.6% / 8.8% | 0.7% / 3.1% |
| Off the grid with only a start offset (median / p95) | 109 ms / 399 ms | 121 ms / 696 ms |
| Off the grid with a start offset plus one tempo correction (median / p95) | 27 ms / 113 ms | 42 ms / 162 ms |
| Word map vs melody map (median gap / share over 0.3 s) | 178 ms / 34% | 100 ms / 11% |

The last three rows use the melody map.

- **The pace is still YuE2's own:** a 0.7% error is about 1.3 s over a 3-minute song, and it adds rubato on held notes. Even with the best single tempo correction, 5% of the song is still more than 160 ms off, against the ~50 ms needed. So the time warp stays.
- **What changed:** the words and the melody now agree (the word map and the melody map sit 100 ms apart instead of 178 ms), so the alignment methods agree more often.
  - The "melody only" map won 7 of 12 takes, "words" 5, and "words + melody" none. That mode can be dropped.
  - The lyric aligner stays: for the word check, and as the fallback where a repeated melody or the lead-in fools the melody map.
- **The syllables file isn't an alignment.** It records where each syllable *should* be; the aligners measure where YuE2 *actually* sang it.

**Skill:** the rule and its check are now in the `generate-music` skill. The piano-master profile requires a syllables file. The script rejects a score unless it has one `Vocal` attack per syllable, each on its syllable's beat, and the syllables spell the lyrics. It names the first extra note. [convert.py](convert.py) writes the syllables file (`syllables-<take>.json`).

**iPad listening (2026-09-27):**
- Words are well aligned to the notes and the staff: the best-sounding set so far.
- **Display offset: 80 ms** lines the notes up with the play line. It's now the page default.
- **Backing volume: 200%** was about right in general, and is now the page default. In pipeline terms, the backing sits 4 dB under the vocal above 250 Hz instead of 10 dB. The backing still varied in volume, and maybe instruments, within and between songs (see "Backing" below).

**Known limitations (accepted for the family app):**
- **Melismas are lost.** YuE2 has no way to sing one syllable over several notes it's given, so the singer holds the first pitch. This matters most for songs with many slurs (What Child, Amazing Grace).
- **The first word is sometimes soft or unclear**, even with the fake-note lead-in.
- **Some seeds still misplace a stretch of words.** Render 2–3 seeds and let the check pick; the Vocals button covers the rest.
- **The backing varies** in level and instrumentation within a song and between songs (next section).

**Backing ([backing_stats.py](backing_stats.py), raw stems, above 250 Hz = what the iPad plays):**

| Takes | Backing vs vocal | Swing within the song (p90 − p10) | Energy below 250 Hz |
| --- | --- | --- | --- |
| These songs, `syl`, 12 takes | −10 to −32 dB | 11–37 dB | 87–100% |
| Earlier spike (Autumn Road, Garden Morning) | −3 to +0.4 dB | 4–11 dB | 43–78% |

- **The style text sent was the piano-master profile's genre defaults:**
  - Hymns: "warm solo voice or small choir … soft organ and strings";
  - Holiday: "warm and festive voice, choir optional, bells, strings, light percussion";
  - Folk: "acoustic guitar and light bass".

  Each ended with "soft, sparse, background, no lead melody". That's vaguer than Autumn Road's "fingerpicked acoustic guitar, soft cello, light brushed percussion", and it offers either/or voices.
- **Prompt test:** Amazing Grace and What Child were rendered again with the same score, lyrics and seeds, changing only the style.
  - "Specific": a genre word, named instruments with how they play, one solo voice, no "soft, sparse".
  - "Folk trio": Autumn Road's instruments.

  The backing level barely moved (−13 to −21 dB against −10 to −22 dB). **The quiet backing isn't the prompt: YuE2 mixes these songs that way.** Above 250 Hz the mix itself is almost all vocal (mix −20.4 dB, vocal stem −20.5 dB, backing −41 dB on Amazing Grace), so the stem separation isn't losing the backing. The likely driver is the material: long verse-only hymns with a continuous sung line and no instrumental sections, against the spike's short verse–chorus songs.
- **The prompt does change how well the backing follows the chords** ([harmony.py](harmony.py): share of chord spans where the written chord is the backing's strongest):

  | Prompt | Amazing Grace, seeds 1 / 3 | What Child, seeds 1 / 3 | Mean |
  | --- | --- | --- | --- |
  | Profile default | 68% / 67% | 42% / 56% | 58% |
  | **Specific** | **85% / 86%** | **68% / 86%** | **81%** |
  | Folk trio | 54% / 73% | 52% / 60% | 60% |

  The prompt had no consistent effect on the words: which takes put a stretch of words on the wrong notes depends on the seed. 6 of the 12 takes pass the strict QA, spread over all three prompts.
- **Consequences:**
  - **Level:** a per-song level (already done) plus a fixed boost (the 200% default) covers most of it. The swings within a song would need a slow automatic backing level, still to build.
  - **Prompt:** iPad listening (2026-09-27) preferred the "specific instruments" takes. **Decision:** the piano-master genre defaults now name the backing instruments and how they play: a genre word, one solo voice, no "or choir" alternatives, and no piano (the child plays it). The prompt-test takes stay on the page (Amazing Grace seed 1, What Child seed 3).

## Where the vocal problems come from (summary for the architecture)

Decision (2026-09-25, updated 2026-09-26 after round 4): keep YuE2 for vocals as they are, with one Vocal note per sung syllable in its input. They sound good and help a lot; this is a family teaching aid, not a product. Document the flaws, give the app a **Vocals on/off** button for badly affected songs, and swap the engine when a better one arrives (YuE3, Suno, …). Measured over 16 takes (4 songs; intro and fake-note lead-ins; 3 seeds for the fake note), plus round 4's 24 takes.

**1. YuE2 doesn't keep the score's pace exactly.**
- **Overall:** most takes land within 1% of the score's length (median 0.5%). Two ran 4.5% and 10.7% long.
- **Within a take:** the offset against the score drifts. Median drift over a song is 1.1 s. The worst takes drift 9–10 s, where YuE2 slowed down partway through.
- **Local rubato:** ±0.1–0.25 s, larger on long held notes (Jeanie).
- **Can the aligner fix it?** Yes. This is what the time warp is for, and after it the melody sits within about 10 ms (median) of the grid where the take is consistent.

**2. YuE2 follows the notes well, and it sings the words in order, but not always on the notes the score gives them.**
- **Notes:** with the melody driving the warp, 96–99% of notes are sung on the right pitch. Every take is in the written key, sung an octave lower (a male voice).
- **Words:**
  - YuE2 sings the right words in the right order. A rough transcription matches the lyrics, and the lyric aligner places 91–98% of words confidently. The other 2–9% (3–20 words per song) are slurred, swallowed or occasionally dropped.
  - **But it decides for itself which note each word goes on.** Over stretches of several words, it sings words half a bar to 3 bars before or after the notes the score gives them. Example: Amazing Grace verse 3, "…thus far / and grace will lead / me home" at 80–86 s, 1–3 bars early.
  - With the hymnal's notes as written, this happened in every take (0 of 16 passed a strict check of both melody and words). **The main cause was our input:** 4–20% of the notes had no syllable of their own (melismas), and YuE2 pairs syllables with notes by itself. With one note per syllable (round 4), words off the staff fell from 39% to 12%, and 3 of 12 takes pass. It still happens in some stretches of most takes: YuE2 has no syllable-to-note channel.
- **Can the aligner fix it?** No. One warp can put either the melody or the words on the staff, not both. The final pipeline keeps the melody on the notes (the student plays along with it) and reports the stretches where the words are off.

**3. YuE2 starts songs its own way.**
- **Without a lead-in:** it ignores the rests before the pickup and starts singing at once, 1.1–1.7 s early. Twice it also dropped the first word ("What", "It").
- **With a lead-in:** starts land close to the score.
  - **2-bar instrumental intro:** starts within +0.04 to +0.4 s; the first word was sung in 3 of 4 songs (Midnight Clear lost "It" again).
  - **Throwaway sung "Oh" before the song:** the "Oh" itself lands anywhere from 2.4 s early to 1.1 s late, and it's muted after alignment. The first real word was sung in 12 of 12 takes. The "Oh" must be on a different pitch from the first word: on the same pitch, the aligner took it for the first word.

**4. Yes, the aligner made mistakes of its own. Most are fixed; one limit remains.**

| Aligner problem | Effect heard | Status |
| --- | --- | --- |
| Everything before the first anchor was squeezed into the score's start | Wobble at the start at every speed (Amazing Grace) | **Fixed:** constant offset before the first anchor |
| A pitch-only map took a held note on the same pitch (the "Oh") for the first word, or matched a repeat of the melody | Words shifted for the first ~8 words (What Child), or for half the song (Jeanie) | **Fixed where it matters:** the word map now sets the rough position (modes "words" and "words + melody"). Each take is also scored with the pitch-only map, which wins only where it scores better |
| Rubber Band lags about 25 ms behind a time map with points every 0.5 s | Vocal about 25 ms late | **Fixed:** a second, correcting pass |
| Picking single note onsets (the first method) was fooled by vibrato and breaths | Would have given a wrong warp | **Replaced** by 3-second pitch windows |
| The accuracy measure has its own limit | Can't certify a strict 50 ms bar | **Remains:** 13–16 ms median, 42–56 ms p95 (ruler test) |
| The lyric aligner places a few words poorly | A few words per song | **Remains:** those words are skipped when measuring |
| Backing level was set from bass the iPad can't play | Backing inaudible | **Fixed:** level measured above 250 Hz, gentle bass cut, volume control |

**What the final pipeline does:**
1. Convert the song with one Vocal note per sung syllable (melismas merged, chords kept), and check the count. Render with the fake-note lead-in (one fixed seed, plus retries).
2. Align every take three ways:
   - "words" (the word map with ±0.35 s pitch adjustment);
   - "words + melody" (±1.2 s);
   - "melody only" (a pitch-only map).
3. Check each result for notes on pitch, words off the staff, the first word sung, and whether the backing plays the written chords. Score = share of notes on pitch − share of words off − 0.1 if the first word is missing − 0.1 if words are off in the first 15 s.
4. Keep the best-scoring take. The page shows its check results, including the stretches where the words are off.

**Final takes on the page** ([select_takes.py](select_takes.py)). Each song defaults to its best one-note-per-syllable take, and offers its best earlier take for A/B listening:

| Song | Default take (round 4) | Notes on pitch | Words >0.3 s off | Strict QA | Earlier best (compare) |
| --- | --- | --- | --- | --- | --- |
| Amazing Grace | `syl` seed 1, melody only | 99% | 2% | **pass** | fake note, seed 1: 99% / 19% |
| What Child Is This | `syl` seed 3, melody only | 95% | 2% | **pass** | fake note, seed 1, words: 83% / 6% |
| Midnight Clear | `syl` seed 3, melody only | 97% | 3% | 1 short stretch | fake note, seed 3, words + melody: 93% / 12% |
| Jeanie | `syl` seed 1, melody only | 98% | 10% | 2 stretches | intro, seed 1: 92% / 18% |

**Which method wins:**
- Melody only wins when the take's words sit roughly where the score puts them (the melody is then near-exact).
- The words-based modes win where a pitch-only map would be fooled (What Child's "Oh" on the first word's pitch).
- Scoring every take in every mode and keeping the best beats any single method.
- Across all 48 round-3 take-and-mode combinations, the best one per song had 83–99% of notes on pitch and 6–19% of words off the staff. With round 4's input, the best has 95–99% and 2–10%.

**For the app (architecture):**
- A **Vocals** on/off button on the Play screen.
- Store each song's check results with its media, and show them in the parent's review list, so a badly affected song can be re-rendered or left with vocals off.
- The alignment and check steps don't depend on the engine, so they carry over when YuE2 is replaced.

## Test 2: one song clock (to run on the iPad)

Staff position, lyric highlight, key light and the flash square all come from one song clock. It reads the audio clock through `getOutputTimestamp()` (falling back to `currentTime` minus the reported latencies). Clicks are scheduled on the audio clock. Headless Chromium on the dev box ran at 60 fps with rewinds and tempo switches and no errors; that says nothing about the iPad.

**On the iPad (MIDIWeb Browser, full screen, silent mode off):**

1. Open <https://<piano-server>/sync/>. Check each song's staff with **Staff check** (drag to scroll): are the notes, words and chords readable?
2. **Clock sync:** choose Amazing Grace at 100%. Leave **Click** and **Flash** on, turn **Vocal** and **Backing** off. Film the screen at 240 fps slow motion for about 20 s while it plays. Count frames between each flash and its click (each frame is about 4 ms). The flash should be within about 30 ms of the click. If it's consistently off, the **−10 / +10 ms** buttons find the display offset.
3. **Drift and rewinds:** turn Vocal and Backing on and **Auto-rewind 20 s** on, and play one full song (about 3 minutes). Watch whether the lit syllable stays with the sung word to the end and after each rewind. Tap **Results** and copy the text: fps, clock method, drift in ppm, and load times.
4. **Tempo switch:** while playing, switch between 100% and 50%. It should carry on at the same place with no gap.
5. **50% listening:** on Amazing Grace and What Child Is This, play "50% (stretched)" and then "50% (YuE2 slow take)". Is the stretched vocal acceptable to sing along with? Which is better?

| # | Check | Result (2026-09-25, iPad A16, MIDIWeb Browser) | Notes |
| --- | --- | --- | --- |
| 1 | Staves readable (5 songs) | **Pass** | Amazing Grace "looks great"; Bach also good. A musician still needs to review them |
| 2 | Flash vs click (frames at 240 fps) | **Not measured**; looks right | Slow-motion counting wasn't practical. The flash visibly lines up with the notes on the staff. The Results numbers below back this up |
| 3 | 3-minute run with auto-rewind | **Pass** | Amazing Grace, 197 s, 9 rewinds: **60.0 fps, p95 17 ms, worst 23 ms, 0 of 11,847 frames over 25 ms**. The clock used `getOutputTimestamp` (baseLatency 2.7 ms, outputLatency 8.0 ms). **Audio clock vs display clock: 8–32 ppm** over four runs, about 2–6 ms per 3 minutes, so no drift correction is needed. The latency formula (`currentTime` − latencies) differs from `getOutputTimestamp` by about −12 ms, so use the timestamp. Auto-rewind is "smooth and clear for the user" |
| 4 | Tempo switch without a gap | **Pass** | "Works well and smoothly" |
| 5 | 50% stretched vs YuE2 slow take | **Stretched is fine** | The slow take sounded better near the start, but that was the start problem below, not the stretch. Decision: 50% comes from Rubber Band |

Other iPad findings:
- **The vocals drift at the start of some songs.** What Child Is This lost the first word "What" and ran about one note off until roughly 15% of the way in. Midnight Clear lost "It" ("came" is stretched over "It came"). Jeanie's "I dream" starts about half a beat early and settles by "of". Amazing Grace wobbles in the first seconds at every speed. Cause and fix: see "Round 2" below.
- **Play waits about 5 s** while the stems download (4.5–6 MB at the server's 0.93 MB/s). The Play button now shows a spinner and a download percentage, and ignores taps until ready.
- **The backing was too quiet** (8 dB under the vocal). It is now 4.5 dB under, about 50% louder.
- **The flash square was too big.** It's now 70% of the size (50 px).
- **Clock bug:** one run ended at once with "end of song, played 0 s". After the iPad sleeps, `getOutputTimestamp()` can return a stale time stamp; extrapolating from it jumped the clock minutes ahead. The page now only uses a time stamp under 250 ms old from a running context, and otherwise falls back to the latency formula.

## Reproduce

```bash
./setup.sh                       # venvs (.venv, .fa), Rubber Band CLI, abc2xml, aligner model, headless Chromium (all gitignored)
.venv/bin/python convert.py      # sources -> build/<id>/notation.json and YuE2 inputs (intro, fake note, syl, mel, extra seeds)
./render_all.sh                  # YuE2 on the GPU -> renders/<take>/ (about 1 min per take)
for m in dtw melody words; do .venv/bin/python align.py --mode $m; done   # -> renders/<take>/aligned-<mode>/, alignment-<mode>.json
.venv/bin/python harmony.py      # backing vs the written chords -> build/harmony.json
.venv/bin/python compare_styles.py   # round 4: as written vs syl vs mel -> build/compare_styles.json
.venv/bin/python select_takes.py # best syl take + earlier best per song -> build/final_takes.json
.venv/bin/python build_site.py && .venv/bin/python check_page.py --play && ./deploy.sh
.venv/bin/python spike_lyrics.py <take>   # optional: words vs melody-map comparison for one take
HF_HOME=~/engines/yue2/hf-home HF_HUB_OFFLINE=1 ~/engines/yue2/.venv/bin/python plan_test.py   # optional: YuE2's own attacks per syllable
```
