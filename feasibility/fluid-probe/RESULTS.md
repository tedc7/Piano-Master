# FluidSynth backing probe

**Decision (Sep 28, 2026): adopted.**
- **Vocals** come from YuE2.
- **The backing** is rendered with FluidSynth and **MuseScore General** from the arrangement's own
  notes (ensemble parts, a hymn's four-part harmony, or chord symbols). YuE2's backing is kept only
  for songs with words that have no backing notes.
- **Solo piano pieces** use the app's own piano for the other hand.

In the parent's listening test, MuseScore General sounded less synthetic than GeneralUser GS. For
Amazing Grace, **both FluidSynth backings sounded better than YuE2's**, and the strings backing
sounded best. Recorded in the architecture, v0.22 §10.5.

**Question (arch §10.5, open since v0.20):** can pieces without words get an ensemble backing by
rendering accompaniment parts from their own notation with FluidSynth and a free SoundFont? YuE2
can't: it always sings.

**Live:** https://192.168.2.128/fluid/ is the listening page. https://192.168.2.128/fluid/app/ is a
test copy of the app with the three pieces, one version per SoundFont. Tap Parent, open a song, and
use Listen at each speed.

## What was built

| Step | How |
| --- | --- |
| Tools | FluidSynth 2.6.1 from conda-forge in `.fluidsynth/` (local to the dev box; nothing on the server), a venv with music21, mido and soundfile (`setup.sh`) |
| SoundFonts | **MuseScore General** 0.2 (sf3, 40 MB, MIT, from the FluidR3 lineage) and **GeneralUser GS** 2.0.3 (sf2, 32 MB, its own permissive license: free use in music, private or commercial). Only the rendered audio is served; the SoundFonts stay on the dev box |
| Backing parts (`backing.py`) | Taken from each piece's own §5 notation, in playback order, so there is no alignment step. Three kinds, one per piece (below) |
| Rendering (`render.py`) | MIDI at each preset's tempo, FluidSynth to WAV (48 kHz, reverb on), the level matched to the YuE2 accompaniment stems (-26 dB RMS where it plays), then MP3 at 128 kbps. There is a one-beat lead-in (the app's `padBeats`) |
| App change | The client accepts an accompaniment-only stem set (`vocals` optional; the Vocals button only shows when there are vocals). Committed on this branch; the real app isn't redeployed with it yet |

### The three kinds of backing

| Piece | Backing | From |
| --- | --- | --- |
| Canon in D (Pachelbel) | Violins 2 and 3 play the right hand's variations delayed by one and by two rounds of the ground bass (Pachelbel's own canon). A cello plays the ground bass, and a harpsichord continuo plays the chords | The arrangement's own notes. This is the "backing from the original score" case |
| The Blue Danube (Strauss) | Pizzicato basses on beat 1, horns on beats 2 and 3, and sustained strings | The arrangement's left hand, orchestrated as a waltz (its chord in each bar) |
| Ode to Joy (Beethoven) | A string pad and a cello on the roots | The piece's chord symbols (it is melody only) |

Chords come from chord symbols when there are any. Otherwise they come from the left hand: one
chord per bar in 3/4, per half bar in 4/4, and a single bass note gets the key's diatonic triad.

## Measured

| | Result |
| --- | --- |
| Render time | 0.25–0.7 s per piece and preset (about a minute of music), on the CPU. All four presets for all three pieces and both SoundFonts, including the timing tests, took about a minute |
| Tempo presets | Each preset is **rendered at its own tempo**, not time-stretched, so 50% sounds as clean as 100% (YuE2's 50% needs Rubber Band). The length is the notated length plus a 2.6–3.9 s reverb tail |
| Size | About 1 MB per minute at 128 kbps. The four presets of a one-minute piece take 5–5.5 MB; the three pieces with two SoundFonts take 33 MB |
| Timing | Exact by construction for the notes. **But slow-attack instruments sound late**: at 30% of their rise, bowed violins and string pads lagged 70–190 ms behind their notated beat, and horns and pizzicato basses 25–40 ms. Cello and harpsichord were instant. Starting each part early by its measured lag (as sample-library players do) brought every part to within 17 ms of the beat, most within 4 ms |
| In the app | The headless check (`check_site.py`) passes: each piece loads its accompaniment-only stems and plays in Listen mode at 100% and 50%, with no Vocals button and no page errors |

Per-part timing, before and after starting early (ms, median; from `build/report.json`):

| Part | MuseScore General | GeneralUser GS |
| --- | --- | --- |
| Canon: violins 2 and 3 | 90 / 68 → 0 | 187 / 183 → 0–3 |
| Canon: cello, harpsichord | 0, 4 | 0, 8 |
| Danube: pizzicato basses, horns | 42, 27 → 0 | 24, 33 → 0 |
| Danube: sustained strings | 0 | 11 |
| Ode to Joy: string pad | 125 → −16 | 145 → 1 |

## Parent's first listen (Sep 28, 2026)

The two SoundFonts are close, but **MuseScore General sounded better, less synthetic**. Build around
it.

## Hybrid test: a YuE2 vocal over a FluidSynth backing (`hymn.py`)

The proposed rule is YuE2 for vocals, and FluidSynth for backing whenever there are backing notes.
So the question is whether YuE2's aligned vocal works over a backing it wasn't sung with.

**Test:** Amazing Grace's existing YuE2 vocal stems, with three backings:
- YuE2's own backing;
- a church organ playing the Open Hymnal's alto, tenor and bass, with the bass doubled an octave down;
- strings on the alto and tenor, with a cello on the bass.

The two FluidSynth backings use MuseScore General. They're laid out on the app piece's playback
order (2 verses), with the stems' own lead-in (`padBeats` 5) and tempo. Both are on the listening
page as mixes at the app's balance, and in the test app as three versions of "Amazing Grace (backing
test)", with Vocals on/off.

| Check | Result |
| --- | --- |
| Tuning | Vocal +1.5 cents from A440 (+3.0 at 50%); YuE2 backing +2.5. FluidSynth is exactly A440. About 10 cents would be audible, so **no correction is needed** (the media skill should still check it on each song) |
| Octave | The voice sings the melody an octave below the written pitch, as a male voice does. That's harmless with any backing |
| Vocal timing against the beat | Each sung syllable's onset against its notated time: a median of −17 ms, 84% within 100 ms (10th–90th percentile −78 to +61 ms). YuE2's own backing, measured the same way: +3 ms, 89% within 100 ms. **The aligned vocal sits as close to the beat as its own backing did**, and the FluidSynth backing is on the beat, so they fit together the same way |
| Attack lag | Organ 39 ms and strings 86 ms, started early by that much; cello and organ pedal instant |
| In the app | Headless: the organ version plays with the vocal at 100% and 50%, and the Vocals button shows |

Measuring a vocal's pitch arrival instead of its syllable onsets gives a wider spread (a median of
89 ms late, and ±230 ms). That's the pitch settling after each syllable starts, and melismas sung as
one held pitch, not timing: syllable onsets are what the ear hears as "on the beat".

**Result: go on the numbers**, pending the listen. A hymn's own four-part harmony is a better backing
source than chords derived from it. Every hymn from the Open Hymnal has one.

## Listening test (for the parent, on the iPad)

| # | Listen to | Question | Result |
| --- | --- | --- | --- |
| 1 | The listening page: each piece "with the piano part", in both SoundFonts | Does it sound like real instruments, good enough for a child to enjoy playing with? Which SoundFont is better? | **Close; MuseScore General sounded better, less synthetic** (Sep 28) |
| 2 | Canon in D in the test app, Listen at 100% and 50% | Is the canon (the violins answering one another) clear and pleasant? Does it stay behind the piano? | |
| 3 | The Blue Danube, Listen at 100% | Does the waltz feel right (strong 1, light 2 and 3)? | |
| 4 | Ode to Joy, Listen at 75% | Is a sustained pad a good backing for a melody-only piece, or too plain? | |
| 5 | Any piece: Rewind while listening; change the preset mid-song | Does the backing come back in cleanly and on the beat? | |
| 6 | Parent › ⚙ backing volume | Is the default level right on the iPad speakers, next to the piano's own speakers? | |
| 7 | With the keyboard (later): play along in Play mode | Is the backing on the beat with your playing? | |
| 8 | Amazing Grace: the vocal with the YuE2 backing, the organ, and the strings (listening page and test app) | Does the vocal sound together with the FluidSynth backings? Which backing do you prefer for a hymn? | **Both FluidSynth backings were better than YuE2's; the strings were best** (Sep 28) |

## What this means for the decision

**In favour:**
- FluidSynth needs no GPU and no alignment step.
- It renders every preset natively and gets pitches and harmony right by construction.
- The backing can come straight from the score: the canon voices, the other hand, or the chords.

**Against:** the sound is General MIDI sample playback, clearly less real than YuE2's recorded-sounding backing. Strings need the early start. How good it sounds is what the listening test decides.

**If it's adopted:**
1. Move the generator into the media skill as an **instrumental mode**: per-genre orchestration styles (baroque strings, waltz, hymn organ, folk guitar and bass), with parts from the score, the other hand or the chords.
2. Add the rendered stems to the song's media for the single parent approval (10.3); the check is the timing measurement above.
3. Keep the client change (accompaniment-only stems).
4. Solo piano pieces keep the app's own other-hand piano (v0.21) and need no render.

**An alternative to decide at the same time:** play the backing **live in the app**, from the notation, with a few sampled instruments. This is how the other hand is played now. There would be no files, any tempo, rewinds for free, and a volume per part. The cost is instrument samples to host (a few MB each, extracted from a SoundFont), more work for the iPad, and more code. Rendering offline is simpler and uses the existing stem path, so it's the recommended first step; the live option is worth it only if we want per-part control (for example, muting violin 2).

**Not tested yet:**
- More genres (hymns, folk);
- A higher-quality orchestral SoundFont (Sonatina Symphonic Orchestra is CC Sampling Plus, which needs a licence check);
- Real play-along with the keyboard.
