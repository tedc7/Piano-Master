# Feasibility results

## Q1 — MIDI on the iPad

**Blocked: new keyboard needed.** The Jikada JK-825 has no MIDI. Its USB port is only for playing music files, and the manual never mentions MIDI. Neither an iOS MIDI monitor app nor MIDIWeb Browser (on a public Web MIDI monitor page) saw any events. Re-test once a class-compliant USB MIDI keyboard is bought.

## Q2 — HTTPS from the server into MIDIWeb Browser

- **Test page:** [https-probe/index.html](https-probe/index.html), deployed to `/opt/piano/www/index.html` on the server.
- **URL:** `https://192.168.2.128/`
- **Device:** iPad A16, iOS ____, MIDIWeb Browser version ____

| # | Step | Expected | Result | Notes / screenshot |
| --- | --- | --- | --- | --- |
| 1 | Install Caddy root CA; fingerprint `19A112C4…3FD7D972`; Full Trust on | Profile installed, trust enabled | **Pass** (2026-09-24) | |
| 2 | Safari opens the URL | Padlock, no warning; secure context PASS; MIDI API absent | **Pass** (2026-09-24) | |
| 3 | MIDIWeb Browser opens the URL | No warning; secure context PASS; MIDI API PASS; request resolves, 0 inputs | **Pass** (2026-09-24) | No warnings or errors; HTTPS pass; MIDI access pass. With no keyboard connected, reports 2 inputs (`MIDIWeb Out / 5of12`, `Network Session 1`) and 2 outputs (`Network Session 1`, `MIDIWeb In / 5of12`). These are virtual ports (the app's own and iPadOS network MIDI), so the app must choose the piano by name and ignore them |
| 4 | Router WAN unplugged; relaunch and reload | Same as step 3 | | |
| 5 | App switch, lock/wake, reload; full-screen mode | Still no warning; address bar stays hidden | **Partial pass** (2026-09-24) | No certificate warnings after lock/wake, app switch, or closing and relaunching the app. Full-screen mode survives lock/wake and app switches, but **is lost when MIDIWeb Browser is closed and relaunched**: the page comes back with the address bar visible. Lockdown finding, not an HTTPS one (see below) |
| 6 | Full Trust off; reload | Warning or refusal (proves the trust path) | **Pass** (2026-09-24) | Shows Apple's "Connection Not Private" warning. |
| 7 | "Try full screen" button in MIDIWeb Browser, then lock/wake, app switch, swipe | Shows whether a page can hide the address bar itself, and what exits it | **Fail** (2026-09-24) | Both Fullscreen API rows FAIL (no request function; not enabled). The buttons did nothing visible and the page couldn't tell which mode it was in. With the app's own full screen switched on by hand, "Exit full screen" had no effect. **The page can't control full screen; it has to be set by hand in MIDIWeb Browser** |
| 8 | Viewport section: note "Screen height not used" with the app's full screen off and on (by hand), in landscape and portrait; then relaunch the app and check the LOAD badge | The gap changes clearly between off and on, so the page can detect the address bar and show a reminder | **Pass** (2026-09-24) | Full screen off: gap 87 px, inner and visual 1180 x 733. Full screen on: gap 0 px, inner and visual 1180 x 820. visualViewport offset (0) and scale (1) don't change. The log records a resize with the new gap as soon as full screen is switched on or off, in both directions. Portrait works the same (off/on detected in both directions; exact portrait numbers not recorded). Relaunch: with full screen on (latest log line gap 0), closing and reopening the app brought the page back with full screen off (gap 87) and a fresh log of 2 lines, so the page was completely reloaded. The reminder would appear in exactly this case |

**Outcome (so far):** Go for HTTPS. MIDIWeb Browser trusts the user-installed Caddy root (and only because of it, per step 6) and offers Web MIDI on the server's HTTPS page. Still to confirm: step 4 (no internet).

**Lockdown finding (arch §2.2, §2.6 check 11 in v0.16):** full-screen mode alone isn't a reliable lockdown, because a relaunch (after a force-quit or an iPad restart) brings back the address bar. Options, to decide in M0:
- a parent turns full screen back on after any relaunch;
- Guided Access, which also stops the app being closed;
- Screen Time "Allowed Websites Only" limited to the piano site. Not yet tested whether it applies inside MIDIWeb Browser or accepts an IP-address URL.

**Full-screen reminder (from steps 7 and 8):** the page can't switch full screen on (step 7), but it can tell when it's off (step 8). On the iPad A16 (landscape figures shown; portrait behaves the same) the page fills the screen exactly when full screen is on (gap 0) and loses 87 px to the app's bars when it's off, and a resize event fires on every change. So the app can:
- treat a gap above about 40 px as "not full screen";
- check on load and on every resize;
- show a calm reminder on the student picker to turn full screen on, and hide it as soon as the gap returns to 0.

Keep the threshold in the DeviceProfile (arch §5) rather than hard-coding 87 px, since other devices and app versions will differ. The reminder only nudges; lockdown still needs Guided Access or a parent's check.

## Client capabilities in MIDIWeb Browser (tests 1, 2, 3, 4, 6)

Pages on the server (links at the top of `https://192.168.2.128/`):
- **Client probe** `https://192.168.2.128/client/`: [client-probe/index.html](client-probe/index.html), tests 1, 2, 3 and 6. Test media from [client-probe/make-media.py](client-probe/make-media.py), deployed to `/opt/piano/www/media/` (not committed).
- **Render test** `https://192.168.2.128/render/`: [render-probe/index.html](render-probe/index.html), test 4, with VexFlow 4.2.5 served alongside. Version 5 loads its music font from a CDN by default, so 4.2.5 is used because it works offline.

Both pages ran with no errors in headless Chromium on the workstation before deployment, and the render test held 60 fps there in both modes. The iPad is the real test.

| # | Test | How | Pass when | Result | Notes |
| --- | --- | --- | --- | --- | --- |
| 1 | Saved data after a relaunch | "Save test values", close and reopen MIDIWeb Browser, return to the page | **Pass** (2026-09-24) | Worked as described: local storage, cookie and IndexedDB survive a full relaunch. The persistent-storage request returned false, so iPadOS could still clear this data if storage runs low. That's acceptable for a device id and a small outbox, but the app should cope with losing them (re-register the device) |
| 2a | Screen stays awake: Wake Lock API | Auto-Lock 2 min; start, don't touch for 4 min | **Pass** (2026-09-24) | Stopped Auto-Lock. Use the Wake Lock API during practice |
| 2b | Screen stays awake: silent video | Same, with the silent-video method | **Fail** (2026-09-24) | Didn't stop Auto-Lock. Not needed, since 2a works |
| 3a | Audio starts, and plays with silent mode on | Start audio, metronome, toggle silent mode | **Pass (start)** (2026-09-24) | Audio context created suspended at 48000 Hz and ran after the Start tap. Silent-mode behaviour not recorded |
| 3b | Audio after lock/wake | Metronome on, lock, wake | **Pass** (2026-09-24) | On lock the audio state went to "interrupted"; on return the page resumed it straight away (interrupted -> running). The app must do the same resume on return |
| 3c | Reported output delay | Read the Audio rows | **Recorded** (2026-09-24) | baseLatency 2.7 ms, outputLatency 8.0 ms, sample rate 48000 Hz |
| 3d | Download speed from the server | "Download speed" | **Recorded** (2026-09-24) | 31.8 MB in 34.1 s, about 0.93 MB/s (single run; the first two runs overlapped by accident, 49.5 s each). The server's Wi-Fi is being upgraded, so no workaround is planned yet |
| 3e | Memory: 2 stems at 50% | "Load 2 stems, 50%"; then "Hold 2 more" until it fails or reaches about 550 MB | **Pass** (2026-09-24) | Held 691 MB of decoded audio (2 x 3 min + 4 x 6 min) and kept playing. Decoding is fast: 2 x 138 MB in 0.48 s |
| 3f | Instant start and rewind | "Play from a random point" several times, then "Rewind 10 s" | **Pass** (2026-09-24) | Start scheduled 0.0 ms after the tap; random starts and 10-s rewinds sounded good |
| 4a | Staff scroll and glide: one wide SVG | Run 60 s test | **Pass** (2026-09-24) | 60 s, 3600 frames, 60.0 fps; frame time median, p95 and p99 all 17.0 ms, worst 24.0 ms; 0 frames over 25 ms; 4 glides. Pre-render 50 ms. Staff 22189 x 451 px at scale 1.50, DPR 2. Looked and sounded good |
| 4b | Staff scroll and glide: canvas tiles | Same | **Pass** (2026-09-24) | Same figures: 60.0 fps, worst 24.0 ms, 0 frames over 25 ms, 4 glides. Pre-render 38 ms. Looked and sounded good |
| 6a | Spoken text | "Speak a sentence", with silent mode on and off | **Pass** (2026-09-24) | Works and sounds good; speech starts about 310 ms after the tap. Silent-mode behaviour not recorded |
| 6b | Video | Play the test video | **Pass** (2026-09-24) | Plays inside the page with sound; doesn't switch to a full-screen player |

**Rendering:** both ways of drawing the staff hold a steady 60 fps on the iPad A16 in MIDIWeb Browser, through rewind glides, with a lit key on every beat. The 451 px staff height is 55% of the 820 px full-screen height, so the runs were in full-screen mode. Either can be used; one wide SVG is the simpler choice (no pixel-ratio handling, stays sharp at any scale, and end-to-end tests can inspect it). Frame times are reported in whole milliseconds, which is fine for this.

**Network note:** the server's only link is its USB Wi-Fi adapter: about 0.6 MB/s to the workstation and 0.93 MB/s to the iPad. The server's Wi-Fi is being upgraded, so the app doesn't compensate for it yet. Re-measure with test 3d afterwards.

**Full-screen tap dead zone (important for UI design):** in MIDIWeb Browser's full-screen mode, taps near the top of the screen don't register. The dead zone is about one button high (roughly the height of the hidden address bar). On the render test only the very bottom edge of the top-row buttons worked, and the links there couldn't be tapped at all. **Rule for the app:** keep the top strip for status only (song progress, stars, streak); nothing a student needs to tap goes there. This changes arch §3, whose Play screen puts pause, restart, tempo presets and the mode toggle in a top bar.

**Other spikes:** YuE2 (the M0-S media spike) was built and tested separately by another agent, with generally positive results.
