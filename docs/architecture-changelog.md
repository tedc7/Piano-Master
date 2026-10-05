# Architecture change log

What changed in each version of [architecture.md](architecture.md), newest first. Numbers in brackets, like (6.3), are sections of architecture.md at that version. Each version's full text is in the file's git history; versions up to v0.25 were saved as separate files named `Family Piano Tutor - Architecture v0.NN.md`.

## All versions

| Version | Date | Summary |
| --- | --- | --- |
| v0.32 | Oct 5, 2026 | The Server session's report: the library in the nightly backup and its restore test passed; a new server also needs the deploy account's sudo and, without Caddy's data, a new certificate root; the install scripts check both; the server's details moved out of the repo into a local config file |
| v0.31 | Oct 3, 2026 | A fresh install: the approved curriculum songs kept in the repo (`content/library/`, stems in Git LFS) by `tools/library_export.py`, seeded on a new server by `tools/fresh_install.sh`; the library in the backup and its restore test |
| v0.30 | Oct 3, 2026 | Vocals for curriculum songs: a vocal alone, with no backing (a `none` backing style, the default for the map's own songs), and the app playing songs whose stems have no backing; YuE2's input in the song's real key and a singable range; repeated-note songs placed by their words |
| v0.29 | Oct 1, 2026 | Daily-use fixes: Back returns to the screen as it was left; one bubble per Journey skill (no lightbulb); pop-ups close on a tap outside; a locked song names the one skill that unlocks it; the metronome one choice per student; finger numbers and letter names switched per song by the parent |
| v0.28 | Oct 1, 2026 | Two of our own studies are never duplicates of each other (the melody check is for imports); words for ten wordless warm-ups through the live-song update flow |
| v0.27 | Sep 30, 2026 | One song library: every song in the server's library through the review list, the map naming only approved songs, the 108 built-in songs seeded once; updating a live song (Needs improvement, the fix as an update, approved in place; Diagnostics on current notes only); library re-analysis after a map change built; letter names under the note heads |
| v0.26 | Sep 30, 2026 | From a review of the code against this document: the file moved to `docs/architecture.md` with this change log; the keyboard decided (88 velocity-sensitive keys, sustain pedal); work requests, vocal-style changes, wait mode, the dark theme, the AI advisor (M9), concept videos and the Level 1 and 2 maps moved to potential features; content loading, library re-analysis, the coverage report and Home's stars described as built |
| v0.25 | Sep 30, 2026 | No method-book links in the repository (book pages in a private file); one concept per Journey bubble: 46 Prep A skills with one Explain each and their own practice songs (2 to 4, 108 core pieces); concept type labels; skills for ideas the notes can't show; dynamic marks drawn and played |
| v0.24 | Sep 30, 2026 | From the family's four first-level method books: the real Prep A map (16 skills, lessons, 68 core pieces with 14 warm-ups); chords counted by size; pre-staff letter-named pieces; the method spine's staff order; intervals, chords, held notes, ties, rests and black-key groups in the song analysis; the tune passing between the hands; Journey units and book pages |
| v0.23 | Sep 29, 2026 | From building M8's media skill v1 and M7's approval pipeline on a batch of kids' songs: `make-media` skill and `tools/media/`; the library on the server, the Skill API, intake, the review list, genre and song rules, deletion; `kids` and `round` styles, four-part hymns with `play: melody`; the word and bleed check rules; the tempo rule |
| v0.22 | Sep 28, 2026 | From the FluidSynth probe: backing rendered from notation with FluidSynth and MuseScore General; YuE2 for vocals, its backing only as the fallback; accompaniment-only stems |
| v0.21 | Sep 28, 2026 | From building M6 and preparing for the keyboard: Diagnostics with five detectors and Focus remedies; the drill generator and scale and arpeggio fingering tables; Check and Echo scoring; the app's sampled piano for the other hand; tap-along latency calibration; the song import skill v1 and the melody fingerprint |
| v0.20 | Sep 28, 2026 | From building M3 without the books and a first hand import of classical pieces: song analysis and beyond-the-map pieces; analysis in every content build; the concept-lesson format; finger-number generator v1; grace notes, tuplets, clef changes, per-note hands, passes vs verses; songs with several arrangements; keyboard size per arrangement; backing for wordless pieces is an open question |
| v0.19 | Sep 28, 2026 | From building M4 and M5 and the practice simulator: students and parent login on the server; content bundled into the App API; a concept lesson for every skill and a Ready-to-learn state; stuck contact alternates section and slower whole piece; bounded New-slot replacement; implicit review after half an interval; sessions fill their time |
| v0.18 | Sep 28, 2026 | From building M1 and M2 and the layout review: display offset is behind the audio clock; plain Web Audio instead of Tone.js; rewind threshold 6 because a wrong key counts twice; built stack recorded; M0, M1 and M2 status; parent as a player and tab-bar navigation; Play and Listen modes with a bars picker and a Rewind button; per-student settings flagged for M4 |
| v0.17 | Sep 27, 2026 | From feasibility tests 2–4 and YuE2 listening: one song clock with a per-device display offset; pitch spelling in the notation; ABC Plus via abc2xml; YuE2 input with one note per syllable, chords and an "Oh" lead-in; named backing instruments; pitch-window alignment with lyric forced alignment; backing level for tablet speakers; Vocals on/off button; YuE2 limitations documented |
| v0.16 | Sep 24, 2026 | From the feasibility tests: HTTPS by IP address with the internal certificate authority; iPad client checks passed (storage, wake lock, audio, speech, video, 60 fps staff); keyboard without MIDI, new keyboard needed; full-screen reminder; status-only top strip; M0-S decision: proceed with YuE2 |
| v0.15 | Sep 23, 2026 | From the v0.14 review: branching skill map; Guided-ready (passed + 1) and library-ready unlocking; stacked aids do not pass; gentle "Try it another way" options and stuck-skill support practice; rhythm skills need timing stars; no minimum practice or daily cap; running mastery with best-so-far; content-change handling deferred |
| v0.14 | Sep 23, 2026 | Skill API for the dev box and parent work requests; tempo presets; smooth automatic rewind as the main practice mode; wait mode optional |
| v0.13 | Sep 23, 2026 | Review changes: server database and home-network model, evaluator spec, practice-aid factor, map-point unlocking, media and video skills with single approval, parent mode, security, backup, logging, testing, later-phase milestones, future enhancements |
| v0.12 | Sep 20, 2026 | Baseline reviewed in "Architecture v0.12 — Review Findings" |

## v0.32 (Oct 5, 2026)

From the Server session's report on `docs/server-brief-backup-restore.md` (it also answers the M4 backup brief and item 1 of the M7 library brief):
- **Backup (11.2):** the database's consistent copy, `library/` and `staging/` are in the nightly backup (30 daily and 12 monthly copies). The restore test, extended to the library, passed: integrity ok, schema 10, 113 songs in both copies, a stem's range request, the same students. M4's restore test is done.
- **A new server (11.6):** the list in the brief was incomplete. The deploy account needs sudo with no password for the commands `tools/deploy.sh` uses (`rsync`, `rm`, `cp`, `chown`, `find`, `mv`), not only `piano-api-redeploy`; and a rebuilt server has a new certificate authority unless Caddy's data is restored. `tools/fresh_install.sh` now checks the sudo in one ssh connection (the server limits connections in a row), and it, `tools/deploy.sh` and `tools/library_export.py` stop with an explanation instead of skipping the certificate check (`curl -k`).
- **No install's details in the public repo:** the dev box's scripts (deploy, fresh install, the song and library tools, the feasibility probes) read the server's address, ssh host and certificate from `~/.config/piano-master/server.env` (`tools/server.env.example`) instead of having them written in; the docs say `<piano-server>` and `<piano-api container>`, and no longer name the server's other services, its domain or the router. `content/incoming/` (song batches, some for private family use only) is in `.gitignore`.

## v0.31 (Oct 3, 2026)

From the review of next steps (the core working well):
- **A fresh install (11.6):** restoring the backup stays the first way back. Without one, `tools/fresh_install.sh` (safe to run again) checks the dev tools, the stems, the content and the server, then deploys with `--seed-songs`; the API adopts the curriculum songs as approved on its first start, with the parent's helper choices.
- **The curriculum songs in the repo (11.2, 11.6):** `content/library/`, exactly as approved, kept by `tools/library_export.py` from a new Skill API call (`GET /api/skill/library/{id}`: the piece, its details and the helper choices). Only songs on the map whose source is our own or public domain. Stems in Git LFS (`.gitattributes`). The seed now comes from here instead of `build/songs/` (the v0.27 one-time seed).
- **Backup (11.2):** the library and staging folders listed with what they hold; a new Server brief asks for them in the backup and a restore test that brings the library back (`docs/server-brief-backup-restore.md`).

## v0.30 (Oct 3, 2026)

From the parent's Needs improvement notes on 43 live Prep A songs ("Add vocals to this song"):
- **Curriculum songs get a vocal alone (10.5):** a backing style `none`, the default for `genre: studies` (the map's own songs) and set in the files of the four curriculum songs in other genres (By the Moonlight, Hot Cross Buns for the Left Hand, Merrily We Roll Along, Joyful, Joyful (letter names)). The media tool would otherwise have built a strings pad and cello from the song's own hands; whether these songs get backings is still an open Next steps item. The app plays its own piano with the stems, so a vocal-only song still has its music.
- **Vocal-only stems (M8):** the client loads a tempo version with vocals and no accompaniment; the backing volume shows only for songs that have a backing.
- **YuE2's input (10.5):** the song's real key when the signature names neither its major nor its minor (the black-key songs, written in C with sharps, had been sung toward C), and each phrase moved by whole octaves into A3–F5 (a left hand written down to C♯2 had been unsingable). Of the first 13 songs, 1 passed before these fixes.
- **Repeated-note songs (10.5):** a melody with too few pitch changes for the alignment windows is placed by its words, and flagged for the listen.
- **Checks from the parent's listen (10.5):** a word the aligner can't place with confidence counts as off (a garbled word had counted for nothing); a held note sung in another octave from the rest of the take fails it; the octave move is made for each run of one hand's notes, not a whole phrase; up to 12 takes.
- **Words for Two-Key Hops,** the one song asked for that had none.

## v0.29 (Oct 1, 2026)

From the family's first weeks of use (the Next steps list):
- **Back from a song (3):** Back on the Play screen returns to the screen that opened the song as it was left: the same scroll position, the same Journey pop-up open, the library's filter. The tab bar still opens every screen fresh.
- **Journey map (3):** one bubble per skill. The lightbulb bubble before each skill is gone; the concept lesson opens from the bubble's sheet, as it already could. A tap anywhere outside the sheet closes it.
- **Song library (3, 10.1):** a locked song shows "Coming soon" with the one skill that unlocks it (the last still to reach), not the whole list.
- **Metronome (3, 5):** one choice per student for every song (`Student.settings.metronome`, replacing the per-song `click`). Until the student first chooses, songs with singing play without it.
- **Song helpers (3):** finger numbers and letter names on or off for each song, in Song and settings (parent mode), for every child (`song_display`, migration 010; `PUT /api/library/pieces/{id}/display`). By default finger numbers show in Prep A songs and not in later levels; letter names show on the pre-staff songs, as before, on white keys only. Letter names switched on by the parent name the black keys too (C♯), so the switch works on the 23 early songs played only on black keys, which start with it off. The song analysis still reads `letters` from the song's file, not this switch.
- **Song and settings (3):** a tap outside closes it without starting anything. The Needs improvement note starts with a bar only once the song has moved past its start.

## v0.28 (Oct 1, 2026)

From the first use of Needs improvement on live songs:
- **Melody fingerprint (10.8):** two of our own songs (`license.composition: original`) are never checked against each other, at intake or in `import_song.py check`. With words on both hands, Bubble Hands' melody became the same two-black-key alternation as Sit Tall's, and intake would have refused its update as "the same song". The check stays for every import.
- **Words for ten songs:** the parent asked for words on ten wordless warm-ups and studies; they went through the update flow (Needs improvement, fixed and resubmitted under the same ids, waiting as updates in the review list).

## v0.27 (Sep 30, 2026)

From building the review's first items, and the family's experience that songs in use keep showing things to fix:
- **One song library (5, 6.8, 6.9, 6.10, 10.1, 10.7):** every song is in the server's library and reaches it through the review list, whatever made it. The skill map and lessons still deploy with the app; the map names each skill's practice songs by id and may name only approved songs (`tools/library_check.py` stops a deploy otherwise), so a new level is added by approving its songs first, then deploying its map. "Core pieces" and the "Lesson pieces" genre are gone: a skill's practice songs are allowed for every child whatever their genre, and each song has its real genre (our own music is `studies`, with the `original` license). Every song's source is kept in git in `content/pieces/` (`promote` moves an approved import's source there). The 108 songs built into the app before came into the library once, as approved, through `deploy.sh --seed-songs`. Each song's version is now a hash of its notes.
- **Updating a live song (10.7):** Needs improvement in the Play screen's gear pop-up (renamed Song and settings) asks for a fix, with the bar the staff is at. The skills read it as a live song; intake takes the fix under the same id; the review list shows it as an update with what changed and the live version to compare; approving replaces the song in place (same id and approval date, so progress carries on), and Discard update keeps the live one. Diagnostics reads only attempts on a song's current notes.
- **Re-analysis after a map change (6.10):** built. When the API starts with a changed map, every library song is analysed again, for the skill it's a practice song of, and Content and analysis lists the songs whose required skills changed.
- **Letter names (6.7):** printed just under the note heads, which stay the usual size (they were inside enlarged heads).
- **Melody fingerprint (10.8):** a run of one repeated note no longer counts, and too short a melody gets no verdict: beginner studies on Middle C matched each other as "the same song".

## v0.26 (Sep 30, 2026)

From a review of the built app against this document:
- **Version control by git:** the document is now `docs/architecture.md`, with its version and date at the top, and this change log beside it. It is edited in place; the file is no longer copied or renamed for each version.
- **The keyboard (2.3, 2.7):** the family's new keyboard has 88 velocity-sensitive keys and a sustain pedal. The "if missing" handling for other pianos (2.4) is not built and moves to potential features, with 61-key support.
- **Potential features (14, was "Future enhancements"):** work requests (with the parent's file uploads), vocal-style changes, wait mode, the dark theme, the AI advisor (M9, removed from the milestones; the other numbers are kept), concept videos (the skill and the Concept videos page, from M8; the Watch card stays), the Level 1 and 2 maps, other pianos and a per-child coverage report. M3 now covers the Prep A and Prep B maps; Prep B needs the next level's books (6.2).
- **Content loading (6.10):** described as built: core content is validated and analysed in the content build and loaded by deploying it, with no Load content or Re-run analysis button. Library songs are analysed at intake; **re-analysing them when a deploy changes the map is still to build**, and replaces the "Automatic re-analysis" enhancement.
- **Coverage report (6.8):** each skill's core pieces and library songs; the build needs at least 2 core practice pieces per skill (the page said 3).
- **Home (3):** shows the stars earned today, as built (was "this week").
- **Repeat signs (5):** repeats and first and second endings are built; D.C., D.S., segno, coda and Fine come with the level map that first teaches them, and until then the song import skill writes them out.

## v0.25 (Sep 30, 2026)

From the family's first look at the Prep A Journey map:
- **One concept per bubble (3 "Journey maps", 6.3, 6.8).** v0.24's 16 skills followed the method book's sections, so a bubble held several ideas (sitting, hand shape, finger numbers and the black keys in the first one; bar lines with the C 5-finger scale) and up to 10 songs. Nothing in the app needed that grouping. The Prep A map now has **46 skills**, one idea each (sitting at the piano, finger numbers, the quarter note, Middle C, the octave...). Each concept lesson has **one Explain card**, and each bubble has its own **practice songs** (2 to 4), so bubbles are checked off sooner and their stars describe one or two songs.
- **The kind of idea is shown (3):** each bubble, its sheet and its Explain card are labelled Notes, Rhythm, Technique, Theory or Musicianship (the skill's track, 6.6).
- **Practice pieces (6.8, 6.10):** a skill's `pieces` list is now its practice pieces, what its bubble shows: the core pieces written for it, at least 2 (was 3 featuring it), each in one list only. The loader checks that each features the skill and needs only it and the skills before it on the map, so it is Guided-ready as soon as the skill is Current.
- **Ideas the notes can't show (6.8):** sitting, a round hand, finger numbers, the measure, a dynamic mark, allegro, question and answer. Such a skill has no constraints of its own (at most a hand position for the finger-number generator); the pieces written for it require and feature it. Everything else is still decided by song analysis alone, and library songs never need these skills.
- **Dynamic marks:** a piece can carry `dynamics` (bar: f, mf, p...). The staff draws them and Listen plays them louder or softer; a lesson's Hear card can set how hard the app's piano plays (`level`). Dynamics are still not scored (7.7).
- **No method-book links in the repository (6.1, 6.2):** the repository is public, so the map, lessons, pieces, code and this document name no method book, its units, titles or pages. The units are our own groupings (9 in Prep A), each lesson is labelled only with its general type, and three pieces whose titles came close to a book's were renamed. The family's page references moved to `content/private/book-refs.yaml` (never committed), which the build merges for parent mode.
- **Map shape:** it forks where ideas don't depend on each other (the technique ideas beside the keyboard ones in Unit 1, rhythm beside reading, Unit 5's treble notes beside Unit 6's bass notes) and joins at the start of the unit that needs them. 40 new core pieces (108 in all), several moved to the concept they practise best; the Unit 4 landmarks and Unit 5 to 8 skills keep the usual five-finger positions for fingering.

## v0.24 (Sep 30, 2026)

From the family's four first-level method books, photographed page by page: lesson, theory, technique and performance:
- **The real Prep A skill map replaces the placeholder (6.3, M3).** 16 skills in 10 units, from two black keys to the quarter rest, each with its pages in the four books (moved to a private file in v0.25). The map forks where units don't depend on each other: the rhythm skills run alongside the reading skills, and Unit 5 (treble notes) alongside Unit 6 (bass notes), which join at Unit 7 (skips).
- **Content for every skill:** a concept lesson in our own words, and 3 to 5 core pieces: our own music, or our own arrangements of public-domain tunes that the method also uses (Hot Cross Buns, Ode to Joy, When the Saints, Frère Jacques, Rain Rain, Twinkle). Every piece analyses to the skill it was written for.
- **Warm-ups (6.2):** 14 warm-up pieces in our own music, one or two per unit, using common kinds of beginner technique exercise: a finger pattern moved to the next key or octave, repeated notes with firm fingertips, 1-3 and 1-3-5 skip patterns, a thumb walking down the keys, landmark notes dropped together with arm weight, the octave leap, and a tied pattern. The first lesson teaches sitting at the piano and the daily warm-ups (heavy arms, firm fingertips, a curved hand, the thumb on its side tip). 68 pieces in all.
- **What the lesson and technique books changed:** three black keys belong to Unit 1; the musical alphabet opens Unit 3; C and G played together (a 5th) start at the landmarks, a 3rd together at the skips, so the analysis now counts a chord by its size; the octave (Middle C to Bass C) and musical question and answer belong to Unit 8; the hand shift to Unit 5.
- **Pre-staff reading (6.7):** Units 1 to 3 are read by letter names, as in the books. Their pieces are marked `letters`: every white-key note head is drawn larger with its letter inside. Staff reading starts in Unit 4 with three landmarks (Middle C, Treble G, Bass F) on the grand staff.
- **Staff order follows the method spine (6.7):** the grand staff from the start, hands taking turns in Middle C position, instead of v0.9's treble-only, then bass-only steps.
- **Song analysis learned the first level's ideas (6.8):** melodic intervals (steps, skips), two notes at once in one hand, hands together over a held note, ties, rests, black-key groups, and pre-staff skills. A map uses them only if a skill names them, so older maps analyse as before. Prep A has no eighth notes and no intervals wider than a skip except the landmark jumps, so most library songs stay beyond the map until Level 1, or need an easy arrangement.
- **The tune can pass between the hands:** a left-hand note with words, played while the right hand is silent, is the melody there. Its words are shown and sung, and the melody fingerprint follows the whole tune.
- **Journey map:** each bubble shows its unit, rows follow their prerequisites so paths cross less, and parent mode shows each skill's book pages.

## v0.23 (Sep 29, 2026)

From building the media skill (M8) and the approval pipeline (M7), and testing both on a batch of kids' songs:
- **M7's approval pipeline built (10.1, 10.7, 10.9):** songs now reach the library through the piano server, not a deploy.
  - **The library lives on the server:** approved songs (notation and stems) are in the server's data folder beside the database. The app and the lesson engine merge them with the pieces deployed with the app. The content version becomes `<deployed>+<library>`.
  - **Skill API** (`/api/skill/...`, a token per skill): the import skill's `submit` sends a batch with its stems. The server's intake checks each song again (license, id, melody fingerprint against the library and the deleted list, song analysis against the deployed map) and stages the ones that pass.
  - **Config › Review list:** one list of every song waiting, in the order they arrived, each with its source, license, tempo source, level, lyrics, media checks and flags, and three buttons: **Approve**, **Needs improvement** and **Never allow**. A song opens in the Play screen with its vocal and backing, from staging, and stays on the list until the parent decides on it. **Needs improvement** asks what should change; the note is kept on the server for the skills (`import_song.py feedback`), and the fixed song, resubmitted under the same id, returns to the list with the note beside it. Approved songs get a New badge.
  - **Config › Dev box connection** (under Settings): the tokens that let the dev box's skills submit songs and read the notes.
  - **Config › Songs and genres:** each child's genre rules (lesson pieces always allowed, other genres blocked until allowed) and song rules, and deleting a song.
  - **The library holds only approved songs.** Every other song lives in the review area: waiting, sent back for changes, or deleted. "Never allow" (Review list) and "Delete" (Songs and genres) both make a song deleted. It shows under **Deleted songs** at the bottom of the Review list, where it can go back to review, be sent for improvement (to be corrected), or be forgotten (then the skills may offer it again).
  - Still to come: work requests (and the parent's file uploads through them), vocal-style change requests, and media updates in the review list.
- **Tempo (10.4):** the 100% preset is the song's natural performance tempo, taken from a metronome mark or recordings and written in the piece's `tempoSource`. The first kids' batch came out at half speed, because the teaching sheets' note values are twice the sung beat (cut time) and the tempo was guessed. Songs sung in two are written in cut time; YuE2 is given them on the felt beat.
- **Media skill v1 built (10.5):** the project skill `.claude/skills/make-media/` with `tools/media/`. It takes a piece file or an import batch and does every step: YuE2 inputs from the arrangement, 2 takes (a third if neither passes), alignment in two ways per take, the checks, the best take kept, the FluidSynth backing at each tempo, levels, MP3s and `media.json`.
- **Where media lives:** each piece's stems in `content/media/<id>/` (gitignored), or with its import batch until it's promoted. The content build copies them into the client, and refuses stems made for a different playback length.
- **New backing sources and styles:** a hymn is typed with all four parts and `play: melody` (the child plays the melody, the other voices are the backing); a round plays its own later entries (`round`); children's songs get soft strings, a pizzicato bass and glockenspiel chimes from the chords (`kids`).
- **Check rules settled:**
  - words off the staff fail a take only above 10% or in the first 15 s; shorter stretches are flagged for the listen;
  - the new bleed check (YuE2 backing left in the vocal) is measured from the spectrograms, first threshold −25 dB;
  - the tuning check (10 cents) and the per-phrase timing check (50 ms) are as planned.
- **Alignment fixes:** a Rubber Band map point at the very start made the whole output about 90 ms late (now dropped); the correcting second pass is kept only when it measures better.
- **Test batch** (`content/incoming/kids-songs/`): Five Little Ducks, The Itsy Bitsy Spider, London Bridge, Row, Row, Row Your Boat (a round), and Jesus Loves Me (a children's hymn, in four parts). It went through the whole pipeline: the import skill, the media skill, `submit`, and the server's intake, and it waits in the review list.
  - **At the real tempos all five pass every vocal check**, with 1 to 4 takes each: 91–99% of notes on pitch, the vocal a median 6–10 ms from the beat at 100% and 21–32 ms at 50% (in the stretched time the child hears), tuning within 4 cents.
  - **YuE2 misses more at a song's real speed:** three songs needed a fourth take, so the skill can now render up to six.
  - **The backings** kept every part within 9 ms of the beat, except Jesus Loves Me's cello (24 ms, flagged).
  - **The bleed check caught a real case:** a London Bridge take had YuE2's backing audible in its vocal (−22.7 dB) and was set aside.
  - The problems met on the way are in `docs/media-pipeline-notes.md`.

## v0.22 (Sep 28, 2026)

From the FluidSynth backing probe, `feasibility/fluid-probe/RESULTS.md`:
- **Backing is rendered from notation (10.5, decided):**
  - The accompaniment stem is rendered with **FluidSynth** and the **MuseScore General** SoundFont (MIT) from the arrangement's own notes: ensemble parts in the score, a hymn's four-part harmony, or chord symbols.
  - **YuE2 now makes the vocal.** Its backing is used only for a song with words that has no backing notes.
  - **Solo piano pieces** keep the app's own piano for the other hand (v0.21).
  - The parent's listening test: MuseScore General sounded less synthetic than GeneralUser GS. For Amazing Grace, both FluidSynth backings (organ, and strings with cello) sounded better than YuE2's, and the strings sounded best.
- **Why it works:**
  - FluidSynth plays exactly on the beat and renders each tempo preset natively, so there is no stretching and no alignment for the backing.
  - It plays the written harmony by construction.
  - It renders in under a second per preset on the dev box's CPU.
  - Slow-attack instruments (bowed strings, organ) start early by their measured attack time; every part then sounds within 17 ms of its beat.
- **The YuE2 vocal fits it:** on Amazing Grace, the aligned vocal is 1.5 cents from A440, and its syllables land a median 17 ms before the beat (84% within 100 ms). That's as close to the beat as YuE2's own backing was.
- **Stems without vocals:** a stem set may now have only an accompaniment (instrumental pieces). The Vocals button shows only when there is a vocal.

## v0.21 (Sep 28, 2026)

From building M6, the app's piano for the other hand, keyboard-day preparation and the song import skill v1:
- **Diagnostics built (8.8):** the five detectors use the table's thresholds. They read per-note results, which every attempt now stores: the notation index and timing of each written note in the scored pass. A wrong key is paired with the missed written note within half a beat. Diagnostics runs when each day's session is built, and for the parent's report. First-version choices:
  - accuracy is taken before the practice-aid factor;
  - rushing or dragging on every note is one "steady beat" pattern, and a single rhythm figure counts only when it is further off than the rest;
  - a pattern is resolved after 2 days, after it was found, on which its notes score 4 stars;
  - it is stuck after 3 remedies or 2 weeks without such a day;
  - it is set aside after 14 days without being seen.

  One known limit: the matcher counts a wrong key that matches the next note's pitch as that note played early. So a stepwise confusion (F played for G, just before a G) can stay hidden.
- **Remedies lead the Practice slot (8.5, 8.8):** they appear in the session as **Focus** items:
  - note confusion: a generated reading drill;
  - rhythm: a rhythm tap drill (any key counts, and only timing is scored), then the bars with the metronome;
  - hands together: the weaker hand alone, then hands together one preset slower;
  - position shift: the bars around the shift, looped;
  - tempo ceiling: the slower preset, then the faster one.

  A test simulator (`api/tests/test_planted.py`) plants each pattern in a simulated student: each is found within 2 days and gets its remedy the same day. It resolves once the remedy works, and a pattern that never improves is marked stuck.
- **Drill generator (8.9):** drills are §5 notation served per student and built only from passed skills' material: reading, rhythm, scale, arpeggio and five-finger drills. There are standard fingering tables for all 12 major and harmonic minor scales and for arpeggios on white-key roots. A scale run of an octave or more in a piece takes the table's fingers.
- **Theory and ear-training scoring (7.8):**
  - Check questions score 1 point right the first time and 0.5 the second.
  - A question may be answered with buttons, for an identify question after listening.
  - A new **Echo** card plays a 2–8 note phrase for the student to play back. It is scored by edit distance, with 10% off for each replay.
  - A lesson's score is stored, and a theory skill passes on it.
- **The app plays the other hand (3, 4):** Listen mode, concept lessons and one-hand practice use a sampled piano, the Salamander Grand Piano (CC BY 3.0, 2 MB), served by the piano server. When a child practises one hand, the app plays the other. This is a per-student setting, on by default, and it is the backing for solo piano pieces.
- **Keyboard day (2.6):** Config > Latency calibration (the tap-along, 2.6.1) is built. The piano check saves the pedal and touch sensitivity it detects to the DeviceProfile, and the parent can also set them. `docs/keyboard-day.md` lists the tests that need the keyboard.
- **Song import skill v1 (10.4):** a project skill in `.claude/skills/import-song/`, with `tools/import_song.py` to convert, check, compare, report and promote.
  - Batches wait in `content/incoming/` for the parent's approval. Until staging exists (M7), approved pieces are promoted into `content/pieces/` (superseded in v0.23: batches are submitted to the server's review list).
  - The melody fingerprint (10.8) is built, and the checks use it.
  - The edition licence whitelist matches exactly: CC BY-NC and ND editions are used for checking only.

## v0.20 (Sep 28, 2026)

From building M3 without the method books, and from a first hand import of 20 classical arrangements, `content/incoming/classical/NOTES.md`:
- **Song analysis built (6.8):** each thing an arrangement uses (a pitch in a hand, a note length, a time or key signature, the hands taking turns or playing together) is credited to the earliest skill whose constraints allow it. Those skills are its required skills. The featured skills are the newest one, plus the next newest when its notes or hands are in at least half the bars; a time signature, key or note length alone never makes a skill featured. Anything no skill allows is **beyond the map**, and that arrangement never unlocks until the map covers it. A skill map's `pieces` list now only says which skill a core piece was written for, and the build warns when the analysis disagrees. The analysis also records each bar's note count, so implicit review can score a required skill's own bars (8.4).
- **Analysis runs in the content build, not by a button (6.10):** content ships with each deploy (v0.19), so every deploy is analysed against the skill map it carries. Config > Content and analysis shows the coverage report and each piece's analysis. A Load content button and Re-run analysis wait until content is loaded without a deploy.
- **Concept lessons have a format (6.9):** one YAML file per skill in `content/lessons/`, with explain, show, hear, try, check and watch cards; notes are written `C4 D4:2 [C4,E4,G4]`. The build checks every skill has one (a warning on the placeholder map). Try is confirmed on the piano; Check takes a tapped or played key; a wrong answer goes back to Show (3).
- **Finger-number generator v1 (8.9):** fixed positions come from a skill's `position` constraint, and everything else from a lowest-effort search using Parncutt's finger-pair spans. The thumb passing under is cheap; a finger over the thumb costs more than a hand shift, as beginner fingerings prefer. It gives the standard C major scale fingering in both hands and agrees with Twinkle's printed fingering.
- **Notation (5):** grace notes are kept apart in `graces` (drawn, never scored); tuplet notes carry `tuplet: [3, 2]`; a clef change at the start of a bar is recorded per staff; `"_L"` or `"_R"` below a note in ABC sets its hand when it differs from its staff's; each playback entry has its `pass` through a repeat, and `verse` stays 1 in a piece without words. The tempo uses the metronome mark's beat unit (`Q:1/2=60` is 120 quarters), and a tie on one note of a chord ties only that note.
- **Songs and arrangements (5, 10.3):** a piece may name its `song` and `version` ("Beginner"); the library shows one card per song, placed where its easiest version opens, with a button per version.
- **Keyboard size (2.3, 5):** the build records 61 or 88 keys per arrangement from its range (C2–C7 fits 61) and warns when it needs 88.
- **Backing for wordless pieces (10.5, open; decided in v0.22: FluidSynth from notation):** YuE2 always sings, so it can't make backing tracks for piano pieces. Most classical piano pieces are accompanied by the pianist's other hand, so the first step is the app playing the other hand when a child practises one. For ensemble originals, a candidate is rendering accompaniment parts written in notation (from the original score, or arranged from the chords) with a sampled-instrument synthesizer such as FluidSynth: exact timing and any tempo, so no alignment step. To be evaluated before importing more songs.

## v0.19 (Sep 28, 2026)

From building M4 and M5, `api/app/engine.py`, and the practice simulator, `api/tests/simulator.py`:
- **Students and parent login built (M4):** the parent adds the students under Config; the first PIN is chosen in the app on a new piano server, and a forgotten PIN is cleared on the server (`python -m app.admin reset-pin`, 11.1). Per-student settings live on the server; device settings stay in the browser where they are measured and are copied to the DeviceProfile (5). The parent's own plays are stored with no student (3).
- **Content on the server:** until the content loader (M3), each deploy bundles the built skill map and piece index into the App API, so the lesson engine plans from the same content version the client shows (6.10). A piece's required and featured skills are its assigned skill until song analysis (6.8).
- **Every skill has a concept lesson** unless the skill map says `conceptLesson: false`. A skill whose prerequisites are passed but whose lesson is not done is shown as **Ready to learn** (its lightbulb glows); its songs open once the lesson is done (3, 8.1).
- **Stuck contact alternates (8.1):** the stuck skill's one short item is the tricky section one day and the whole piece one preset slower the next. The simulator showed that a section alone never passes the skill (only whole-item attempts pass), so a stuck skill stayed stuck for good.
- **The New slot's replacement is bounded (8.5):** when a skill passes mid-session, its remaining New items are replaced by the next skill's, taking no more time than they did. Without the bound a quick learner's session grew with every pass and was never completed, so the target never stepped up.
- **Implicit review needs half an interval (8.4):** a strong play counts as a review only once at least half the current review interval has passed, so a run of good plays on one day cannot climb the whole ladder.
- **Sessions fill their time (8.5, 8.6):** a longer target adds more of the new skills' pieces, and time still unplanned becomes extra "Your pick" items (up to 4). With nothing new to learn (end of content, or everything else waiting on a stuck skill), polish is no longer capped at 2.

## v0.18 (Sep 28, 2026)

From building M1 and M2, `client/`, `api/`:
- **Display offset direction:** the staff is drawn a per-device offset **behind** the estimated audio clock, not ahead of it (3, 5). v0.17 said "ahead"; the code and the iPad test hold it behind.
- **Plain Web Audio instead of Tone.js:** stems, clicks, count-in and the Listen tone need only a few Web Audio nodes, and the song clock reads the `AudioContext` directly, so Tone.js is dropped (2.7, 4).
- **Rewind threshold 6:** a phrase rewinds when its missed plus wrong notes reach **6**, or 25% of its notes, whichever is larger (3). A **wrong key counts twice**: the written note it replaced is missed, and the key itself is a wrong note, so 2 errors per wrong key made the first threshold of 2 rewind on a single slip. To be tightened after the MIDI tests if needed.
- **Built stack:** Svelte 5, TypeScript and Vite on the client; FastAPI with SQLite (numbered migrations) for the App API; the client outbox and client log are in place (2.7, 12).
- **Navigation (from the layout review):** the player picker lists each child and **Parent** (behind the PIN) as players; a bottom tab bar replaces Home (students: Today's Practice, Journey, Songs, My Progress; the parent: Journey, Songs, Config). Today's Practice shows the whole session as a path of items, checked off with their stars as soon as each is finished. The status strip leaves its left 110 px empty for MIDIWeb Browser's floating full-screen button (3).
- **Play screen controls:** two modes, **Play** (play-along) and **Listen**, each button starting and pausing its own mode, with a bars picker (**All bars** or one section, which then repeats: the old Section loop). A **Rewind** button goes back a set number of bars (2 by default) and counts as a rewind in Play mode; after the end it returns to the start. The Click button is now **Metro** (3).
- **Settings owners (flagged for M4):** everything is kept per device for now; in M4 the per-student settings (auto-rewind, backing volume, rewind bars, and per song the vocals, metronome and tempo preset) move to each student, set by the parent in Config, and the device settings (offsets, piano input) stay in Config > Device settings. The Play screen's settings sheet then shows only test readouts, to the parent (5, 12).

## v0.17 (Sep 27, 2026)

From feasibility tests 2–4 and four rounds of YuE2 listening, `feasibility/sync-probe/RESULTS.md`:
- **Song clock and notation:**
  - One song clock drives the staff, lyrics and audio. It reads the audio clock through `getOutputTimestamp()`, ignoring stale time stamps. On the iPad it ran at 60 fps, and the audio and display clocks agreed within 8–32 ppm, so no drift correction is needed. A per-device **display offset** (80 ms on the iPad A16) lines the notes up with the play line (3, 5).
  - Real public-domain hymns and songs convert to the §5 notation and render with no hand edits. Notes need a **pitch spelling** (5), and ABC Plus sources go through abc2xml first (10.4).
- **YuE2 input:** the melody sent to YuE2 has **one note per sung syllable** (melismas merged onto their first pitch). This cut the words sung on the wrong notes from 39% to 12%. Scores also keep their chords and start with a throwaway sung "Oh" bar.
- **Backing prompts:** they **name the backing instruments and how they play**, which made the backing follow the chords in 81% of spans instead of 58% (10.5).
- **Timing:** YuE2 still keeps its own pace (0.7% off, plus rubato), so every take is time-warped. The alignment uses pitch windows, with lyric forced alignment as the word check and fallback. 50% versions come from Rubber Band (10.5).
- **Accepted limitations:** YuE2 sings melismas as one held pitch, sometimes blurs the first word, puts an occasional stretch of words on other notes, and varies its backing. The Play screen gets a **Vocals on/off** button, and each song's check results are stored (3, 5, 10.5).

## v0.16 (Sep 24, 2026)

From the feasibility tests, `feasibility/RESULTS.md`.

The piano site is served at the server's fixed IP address with the server's own certificate authority, because the router cannot hold local DNS names and no public issuer certifies an `.internal` name (2.5). On the iPad A16, MIDIWeb Browser trusts that certificate authority and offers Web MIDI, and saved data, Wake Lock, audio, speech, video and 60 fps staff scrolling all passed. **MIDI itself is untested:** the Jikada JK-825 has no MIDI, so a new keyboard is needed (2.3). MIDIWeb Browser's full-screen mode is lost when the app relaunches, and a page cannot turn it on, but the page can detect it and show a reminder (2.2). In full-screen mode the top of the screen ignores taps, so the top strip of every screen shows status only (3). The YuE2 media spike passed and YuE2 is confirmed as the media engine: it sings a supplied melody (92-98% of notes on pitch) within 8 GB of GPU memory, but its timing only roughly follows the score, so the alignment step is essential (10.5, 12).

## v0.15 (Sep 23, 2026)

From the v0.14 review.

The skill map is a **branching map** (prerequisites create forks and joins), not a single line, so several skills can be in progress at once. A skill passes at 3 stars; **Guided sessions may use pieces that need one Current skill beyond the passed skills**, while Free Play and the library unlock only from passed skills (6.8, 8.1). **Stacked practice aids are for practice and do not pass a skill**; only whole-item attempts pass (7.5). A student who has trouble gets gentle **"Try it another way"** options after 3 tries, and a **stuck** skill gets more support practice in the session, never a "failed" message and never a free pass (8.1). **Rhythm skills also need timing stars to pass.** There is no minimum practice to pass and no daily cap on new skills. **Mastery is a stored running value** updated after every attempt, with the best-so-far kept (8.2). Handling of content changes behind a student's progress moves to future enhancements (section 14).

## v0.14 (Sep 23, 2026)

The dev box (Claude Code, the three skills, and YuE2) reaches the piano server only through a new Skill API, and parents queue content requests in Parental Controls; the server runs no Claude or GPU work. Tempo uses four presets (50%, 75%, 90%, 100%). Practice now centres on normal play-along with a smooth automatic rewind (section 3, "Play and smooth rewind"); wait mode becomes an optional aid built later, with no vocals or accompaniment.

## v0.13 (Sep 23, 2026)

From the v0.12 review.

All data now lives in one server database on the home network, so any device a child signs into picks up their progress; the Lesson Engine moves to the server; the performance evaluator is fully specified, including a practice-aid factor so 5 stars are only possible at full conditions; songs unlock by their place on the skill map; song media (vocals, accompaniment) and concept videos are produced by Claude skills before the parent's single approval; a parent mode (PIN login/logout) replaces a separate preview page; new sections cover security, backup, logging and testing; Bluetooth MIDI, headphones, placement and notifications move to a future enhancements list. See section 15 of architecture.md for the full decisions log.
