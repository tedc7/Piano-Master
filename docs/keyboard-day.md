# Keyboard day: the tests that need the piano

Everything up to M6 is built and tested with a scripted keyboard in the browser check
(`tools/check_app.py`). The scripted keyboard shows the logic works; it can't show that the timing
feels right, that rewinds feel natural, or that the stars feel fair. This list is what only a real
piano and the children can check, in the order to run it. Each step names where to do it, the pass
mark, and what to send back for tuning.

Everything runs as the parent (Switch player › Parent › PIN), except where a child plays.

## 1. Before the iPad: the keyboard on a computer

- [ ] Plug the keyboard into the Linux dev box or a Chromebook with USB and open
      `https://<piano-server>/app/#/config/midi` in Chrome. It should list the keyboard by name.
      If it doesn't, the keyboard is not class-compliant USB MIDI (arch §2.3). Stop and exchange it.

## 2. Device qualification on the iPad (arch §2.6), in MIDIWeb Browser

| # | Where | Do | Pass mark | Record |
| --- | --- | --- | --- | --- |
| 1 | Config › Piano check | Connect with the USB adapter | Listed by name; virtual ports ignored | |
| 2 | Piano check | Every key low to high, then 3- and 4-note chords | Every key heard; "Most keys at once" 4 | Keys heard |
| 3 | Piano check | Soft and loud notes; the pedal; one key 10 times fast | Velocity range ≥ 30; pedal down/up; +10 notes | Fastest repeat |
| 4a | Piano check | Play for a minute | MIDI delivery median and 95% under ~10 ms | Median, 95%, worst |
| 4b | Piano check › Save results | Save | The pedal and touch sensitivity appear in Device settings | |
| 4c | Config › Device settings | Choose 61 or 88 keys; check the pedal and touch rows | Matches the keyboard | |
| 5 | Config › Latency calibration | Start, then tap one key with each of the 24 clicks. Do it twice | Spread under 20 ms; the two offsets within ~10 ms of each other | Offset, spread |
| 6 | Piano check, "Click on each key" on | Film keys and screen in slow motion (240 fps). Press a key 10 times | Key-to-screen under ~30 ms | Frames to light, frames to click |
| 7 | Any song, Listen then Play | Is the staff on the play line when a note sounds? | Notes cross the line as they sound (display offset, 80 ms on the iPad) | Any offset change |
| 8 | Echo Song, Play, "Right hand" | Play the right hand; the app plays the left hand on its piano | The app's left hand and the piano's own sound are balanced | Too loud or too soft? |
| 9 | Amazing Grace, Play with vocals | Play along | No crackling; the piano and the iPad speakers are balanced | Backing volume |
| 10 | Mid-song | Unplug and replug the piano; lock and wake; switch apps; Wi-Fi off and on | MIDI and sound come back (a reload may be needed); an attempt played during a Wi-Fi drop arrives afterwards | What needed a reload |
| 11 | Pedal unplugged | Play a song | Nothing breaks | |

Repeat steps 1–7 on the Chromebook if the children will use it.

## 3. M1 acceptance: play-along and smooth rewind (arch §3)

- [ ] A child plays **Twinkle Twinkle** at the 50% preset, start to finish.
- [ ] Rewinds: a child makes mistakes in a phrase and it glides back. Ask the child and watch.
      Does it feel like "let's take that again", or like an interruption? Too eager or too late?
- [ ] Losing their place: the child stops for a moment. It should rewind at the next bar line.
- [ ] The count-in after a glide is long enough to get the hands ready.

Send back: rewinds that felt wrong (the song and roughly where). The thresholds are 6 errors or
25% of a phrase, 2 beats of silence, and a 0.7 s glide (arch §3). They're one-line changes.

## 4. M2: scoring feels fair (arch §7.10)

- [ ] Ten plays across the pieces, by the children and by you. After each, do the stars match what
      you'd say?
- [ ] Record fixtures from real attempts. List them with
      `tools/.venv/bin/python tools/fixture_from_attempt.py`, then write one with
      `tools/.venv/bin/python tools/fixture_from_attempt.py <id> <name>`. Aim for one of each:
      perfect, one wrong note, rushed, dragging, extra notes, rolled chords, a rewind that should
      happen, one that shouldn't, and losing your place.
- [ ] Timing windows (±150 ms on time at Prep levels): does "on time" match your ear?

Send back: the fixtures, and any play where the stars felt wrong.

## 5. Lessons and practice (M3–M6)

- [ ] Each placeholder concept lesson's **Try** and **Check** cards with the piano. A key press
      should count once; a wrong key on Check goes back to Show.
- [ ] A Guided session from start to end for each child. Does it end near the target length?
- [ ] One-hand practice with the other hand played by the app (step 8 above), with a child.
- [ ] **Two devices** (M4): a child plays on the iPad, then on the Chromebook. Their progress
      and today's session follow them.
- [ ] After a week of real practice: Config › Progress reports shows any **patterns** Diagnostics
      found (M6), and the session's Practice slot has the remedy drills. Are they the right ones?

## 6. The rest of the qualification test (no piano needed, same day)

- [ ] **No internet** (2.6 #10): unplug the router's internet; the app loads, a session runs, progress saves.
- [ ] **Silent switch** on the iPad: app audio still plays, or note that it must be off.
- [ ] **Lockdown** (2.6 #11): MIDIWeb Browser full screen; the reminder appears after a relaunch.
      Decide whether Guided Access is needed.
- [ ] **Soak test** (2.6 #12): a week of daily use.

## What to send back

The offsets and spreads from step 2, the rewinds that felt wrong, the fixtures, any stars that felt
unfair, and balance notes. The numbers are tuned from these (arch §7.10). Nothing here needs code
changes to run.
