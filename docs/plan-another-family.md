# Plan: another family runs the piano app on their own home server

Status: **built in v0.51** (Nov 14, 2026): see `docs/install-guide.md` and architecture §11.7.
This was revision 3 of the plan, kept for the reasoning behind it. The parent decided:
- **The bulk import:** songs from the app are brought into the Review list, with Approve all.
- **"Waiting for a song"** for a skill whose songs aren't approved.
- **The map and lessons ship without review.** Only songs go through the Review list.
- **They follow `main`.** Release tags stay an open question, for later, if updates cause trouble.
- **Their requests come to us outside the app,** or as a GitHub issue with nothing private in it.

Still not done: a run through the guide on a fresh Ubuntu 26.04 machine by a Claude session given
only the guide, and the install with the family.

## 1. How it would work

```
Our side (unchanged)                         Their side
-------------------------------------------  ---------------------------------------------
dev box + GPU + Claude Code                  their Ubuntu server, which is also their "dev box":
  song skills -> our server's Review list      Claude Code + a clone of this repo
  our parent approves                          the server's setup, done by their Claude
  library_export.py -> content/library/        from docs/install-guide.md
  (later content/packs/<pack>/)
  commit -> PR -> merged to main               git pull -> tools/deploy.sh
                         \                       the app, the API, the map and the lessons,
                          \___ GitHub _______>   plus the curriculum songs (and any packs)
                                                 bundled as "songs from the app"
                                               Review list > Bring into review
                                                 their parent approves, one by one or all
                               issues <------- their parent's requests, filed by their Claude
                                               with nothing private in them
```

- **Only GitHub links the two families.** No server talks to the other one, and the children's
  data never leaves their server.
- **Their server runs with song tools off** (2.4): it never makes songs, and the Skill API is
  closed.
- **Every song reaches their children through their parent's Review list:** the first 108,
  every later fix, and every pack.

## 2. Your points

### 2.1 Git LFS: no change needed
0 of 10 GB used this month. A full clone pulls about 0.3–0.4 GB, and an update only the stems
that changed. Keep an eye on:
- **LFS storage**, as well as bandwidth: every re-rendered vocal adds a version that stays in the
  history;
- **packs**: `.lfsconfig` `fetchexclude = content/packs/**` so a clone doesn't download every pack.

### 2.2 Amazing Grace into the repo, on LFS
Put it in `content/library/` like a curriculum song:
- its stems in `media/amazing-grace-melody/`, which `.gitattributes` already sends to LFS
  (`content/library/media/**`);
- its 44 KB notation and details in `amazing-grace-melody.json`, as plain text like the others.

Only the one take we use comes over: 8 stems, 31 MB in LFS. Nothing large goes into git itself.
Re-encoding at the library's usual bitrate (about 3–5 MB) is optional now; it only saves LFS
space. Then:
- add a short **starter list** to `library_export.py` for songs beyond the map that every install
  gets (Amazing Grace for now);
- retire the `syncProbe` path in `build_content.py`, so a fresh clone builds;
- `check_app.py` step 6 reads it from the library.

It's a hymn, so a child sees it only once the parent allows Hymns.

### 2.3 The first install has the curriculum songs only
Yes: 107 map songs plus Amazing Grace. Now they come in through the Review list (section 3)
rather than straight into the library as approved.

### 2.4 Song tools on only for our server and dev box
Our `server.env` gets `PIANO_SONG_TOOLS=on`, and our deploys carry it as a marker in the content
they bundle. A deploy from a box without it, like theirs, leaves song tools off. A migration
turns them on where skill tokens already exist, so our server doesn't change.

| Off (their server) | Hidden or refused |
| --- | --- |
| Play screen, gear pop-up | Needs improvement |
| Review list | Send back / needs work, and the bulk "Ask for updates" |
| Config | Dev box connection |
| Skill API | Every call refused (403: song tools are off) |
| `/api/health` | `songTools: false`, for the tools and skills to check |

What stays: the Review list itself, with listening, approve and delete, and its new bulk import
(section 3). Their server needs no Skill API at all, which keeps it simple.

### 2.5 An install guide written for their Claude
`docs/install-guide.md`, public, written for Claude Code on their server.

1. **Requirements.**
   - **Server:** Ubuntu Server 26.04 LTS on x86-64. That's what ours runs; 24.04 should work but
     is untested. It needs 2 GB RAM, 10 GB free disk, and a fixed LAN IP from a DHCP reservation.
   - **Student device:** an iPad with MIDIWeb Browser.
   - **Piano:** a class-compliant USB MIDI keyboard (the specs say "USB MIDI"). The microphone
     input is the fallback (2.8).
2. **Host packages:**
   - Docker Engine with the compose plugin, from Docker's apt repo;
   - `git`, `git-lfs`, `rsync`, `sqlite3`, `curl`;
   - Node 22, and Python 3.12+ with venv.
3. **The server contract:** a public description of what our private Server repo provides.
   - **Caddy** on `<IP>:443` only, with `tls internal` and `default_sni <IP>`, and no port 80.
     `/api/*` goes to `piano-api:8000` with the prefix kept and no body limit. Everything else is
     a read-only `file_server` from `/opt/piano/www`. Keep the `caddy_data` volume.
   - **`piano-api`:** built from `/opt/piano/api`, user 10001, `init: true`,
     `PIANO_DB=/data/piano.db`, `TZ=<their time zone>`, 512 MB, no published ports.
   - **Folders:** `/opt/piano/{www,api}` root-owned. `/opt/piano/data` 0750, owned by 10001:
     never deleted, never `down -v`.
   - **`/usr/local/sbin/piano-api-redeploy`:** one at a time, rebuild only `piano-api`, wait for
     health through Caddy against the root CA, logs on failure, prune old images.
   - **A nightly backup and a restore test:** `sqlite3 .backup` plus `integrity_check`, then
     `library/` and `staging/` right after, with copies off the server's disk.
   - **PIN reset:** `docker compose exec piano-api python -m app.admin reset-pin`.
4. **Install:**
   - the clone (with LFS);
   - `~/.config/piano-master/server.env` with `PIANO_HOST=local` (change 4.4);
   - `tools/setup.sh`;
   - `tools/fresh_install.sh --check`, then `tools/fresh_install.sh`.
5. **Certificates, with the parent:**
   - copy Caddy's root (`/data/caddy/pki/authorities/local/root.crt`) to `CADDY_ROOT_CA`;
   - AirDrop or email it to each iPad, then Settings › Profile Downloaded › Install, then
     General › About › Certificate Trust Settings › full trust;
   - open the site in MIDIWeb Browser and confirm there's no warning.

   The certificate check is never skipped.
6. **First run:**
   - the PIN, then the children;
   - Review list › Bring into review › listen › approve (section 3);
   - genres to allow;
   - keyboard size, the piano check and latency calibration;
   - MIDIWeb Browser full screen, or Guided Access.
7. **Checks** with exact commands and expected answers: health 200 with `songTools: false`,
   `/app/` 200, port 8000 closed from the LAN, a restore test that passes.
8. **Updating** (2.7).
9. **Rules for their Claude.** The guide tells it to save these on their box in
   `CLAUDE.local.md`, listed in `.git/info/exclude` so it never reaches git. Claude Code loads
   that file in every session there, so the rules hold after the guide is out of mind.
   - **Don't use the repo's song skills** (`import-song`, `make-media`, `lesson-voice`,
     `generate-music`). They need our GPU pipeline and a server with song tools on. For a new
     song, a fix or a pack, file an issue.
   - **Don't change the repo:** no edits to tracked files, no commits, no pushes, no branches.
     Update only with `git pull`. Their own settings live outside the repo
     (`~/.config/piano-master/`, the server's compose and Caddy files).
   - **Nothing private goes to GitHub.** Issues are public. No children's names, ages, photos or
     recordings. No addresses, IPs or server names, no tokens, no PIN, no database contents.
     Describe the song, the bar and what's wrong, and show the parent the text before filing.
   - **Never skip a certificate check**, never `docker compose down -v`, and never delete
     `/opt/piano/data`. Back up before every update.
   - **Every song goes through the parent's Review list.** Never approve for the parent.

   As a backstop, the skills could also check `songTools` and stop with one line (4.6).

### 2.6 Later: song packs in LFS
`content/packs/<pack>/` (e.g. `christmas`, `childrens-classics`) holds `pack.yaml` (title,
description, each song's license), `<id>.json` and `media/<id>/*.mp3`, all in LFS.
- **Our side:** `library_export.py --pack <name>` copies approved songs that are public domain or
  our own arrangements, never a parent's private songs.
- **Their side:** `git lfs pull --include "content/packs/christmas/**"`, then the next deploy
  bundles it, and it appears in the Review list's bulk import (section 3) for their parent.

### 2.7 Every change goes through GitHub
- **Updates:** their Claude backs up, runs `git pull` and `tools/deploy.sh`, then tells the
  parent when the Review list has songs waiting.
- **Fixes we make** reach them the same way, as updates in their Review list.
- **Change requests:** their parent tells their Claude, which files an issue under the rules in
  2.5.9.
- **Follow `main` or release tags?** `main` has only reviewed merges. A tag after each deploy we're
  happy with costs one command and gives them a known-good point. I'd tag.

### 2.8 The microphone (corrected)
This was recorded, but in the wrong place for me to find. The changelog for v0.38 says
"MIDIWeb Browser offers microphone access", and architecture §4 has the iPad results:
- **Heard well:** C2 to B5.
- **Mostly heard:** C6 to C8, 15 of 18 keys.
- **Mostly missed:** the lowest octave. Its overtones are too close together for the 85 ms window.
- **Never:** the pedal. Velocity is only guessed, fast repeats under ~90 ms merge, and the room
  must be quiet.

§2.1 still says "whether MIDIWeb Browser offers it is not yet checked", and §4's last paragraph
says "not yet on the iPad with the JK-825". Both are stale (change 4.9).

**For them:** the curriculum's songs span C2 to D♯6, so Prep A works by microphone. The few notes
above B5 are mostly heard. The guide should say the microphone is a stand-in with limits, and
that dynamics, pedal and held-note scoring from Level 3 need MIDI.

## 3. Every song through their Review list

**Your bulk-import idea fits well.** The Review list can't read the repo, but it doesn't need to:
their deploys already carry the songs to the server. Today it has no bulk import or bulk approve.
Its one bulk feature, Ask for updates, is a song-tools request.

1. **Songs from the app.** On a server with song tools off, every deploy bundles
   `content/library/` (and any pulled packs) into the API's content as **available songs, not
   approved ones**. This replaces today's `--seed-songs` adoption on their install. Our install
   keeps `--seed-songs` for a rebuild of our own server.
2. **What's new.** The server compares the bundle with its library and review area:
   - **new:** not in the library and not waiting;
   - **updated:** a newer approved version of a song this server took from the app;
   - **skipped:** deleted by their parent, or already waiting;
   - **unchanged.**

   It reports the counts in `/api/health` and at the top of the Review list.
3. **Bulk import:** "Songs from the app: 108 new, 3 updates. **Bring into review**" (one line per
   group: the curriculum, and each pack). Tapping it runs the normal intake on each song: the
   same checks, analysis against this server's own map, and fingerprints against deleted songs.
   They're staged as one package.
   - **Updates** come in as updates to the live song, the same as a Needs-improvement fix today:
     the list shows the bars that changed, the children keep the live song meanwhile, and
     approving replaces it in place, keeping stars and progress.
   - **One intake change:** accept an update to a live song with no open request when it comes
     from the app's bundle and the live song came from the bundle too.
4. **Bulk approve:** "Approve all N in this package", with a confirm. The parent can listen to a
   few, approve those one by one, and approve the rest together. It helps us too.
5. **Their choices per song:** approve, delete (it won't be offered again; it's restorable from
   the deleted list), or leave it waiting. Send back is hidden, because no song skills would
   answer it. A note for us goes to their Claude, then to an issue.

### What this still needs a decision on

- **A map song that isn't approved, or was deleted.** The engine plans only from the library
  (`content.py`), so it's never offered, which is right. But:
  - `library_check.py` stops a deploy whose map names a song the library lacks. On their install
    that has to become a warning, or the first deploy can't run, because the songs aren't
    approved yet.
  - A skill whose practice songs are all waiting or deleted needs defined behaviour. I suggest it
    shows **"Waiting for a song"** on the Journey, is skipped by Guided sessions, and never
    blocks the skills after it. The Today's Practice screen must still work with zero
    approved songs on day one.

  This needs engine and simulator tests. It also tightens our own install, where a parent
  deleting a practice song today leaves the same gap.
- **The map and lessons still ship without review.** Only songs go through the Review list. The
  skill map, the lessons and their voice, and the app's code arrive with each deploy, the same as
  on our server. I think that's right: they're the app, not library content. But it's worth
  saying in the guide.
- **First-day load:** 108 songs. Bulk approve makes it minutes, not hours. The guide should
  suggest listening to a handful first.
- **Their analysis can differ from ours.** Intake re-analyses each song against their deployed
  map. That's the same map, so the results should match, and the Review list shows any
  "beyond the map" flags as it does for us.

**The alternative**, if you'd rather not build the bulk import: their Claude submits the songs
with a token, through the Skill API, using a new `tools/library_submit.py` and the same intake.
It would work, but the Skill API and Dev box connection would have to stay open on their server.
Their Claude would also have to run it after every pull. The Review-list import keeps the parent
in charge and needs no Claude step, so I recommend it.

## 4. Changes to build

| # | Change |
| --- | --- |
| 4.1 | **Amazing Grace** into `content/library/` (stems on LFS), the starter list in `library_export.py`, the `syncProbe` build path retired |
| 4.2 | **The song tools flag**: the marker from `deploy.sh`, the migration, `songTools` in health, the Skill API closed when off, the hidden parent features |
| 4.3 | **Review-list bulk import and bulk approve** (section 3): available songs in the bundle, the comparison, "Bring into review", updates from the bundle accepted by intake, "Approve all in this package" |
| 4.4 | **`PIANO_HOST=local`** in `deploy.sh` and `fresh_install.sh`; `library_check.py` warns instead of failing when song tools are off |
| 4.5 | **Engine: a skill waiting for a song** (section 3), with tests in `test_engine.py` and the simulator |
| 4.6 | **`setup.sh` accepts a system Node 22**; Playwright optional. Optional: the skills check `songTools` and stop |
| 4.7 | **`docs/install-guide.md`**, with the rules for their Claude (2.5.9) |
| 4.8 | **A clean-room test**: a fresh Ubuntu 26.04 VM and a Claude session given only the guide. Install, review and approve, play a session; then pull a later commit with a changed curriculum song, and check the update waits in the Review list |
| 4.9 | **Architecture**: a new section, "another family's install", in §2.5/§10.7/§11.6; fix the stale microphone lines in §2.1 and §4; version bump and changelog |
| 4.10 | Later: **song packs** (`content/packs/`, `--pack` export, `.lfsconfig` fetchexclude), appearing in the bulk import |

## 5. Still open

1. **A hand-built server can drift.** Their Claude builds the setup from a description, not our
   tested `setup.sh`. The checks catch deploy-time problems; only a restore test proves the
   backup. Backups are theirs, and without one a disk failure loses the children's progress.
2. **The rules for their Claude are instructions, not locks.** `CLAUDE.local.md` makes them stick
   across sessions. The song tools flag makes the skills fail harmlessly if they're tried anyway.
   Nothing stops a determined local edit, but a `git pull` conflict would show it quickly.
3. **Fixes take as long as our pipeline:** our GPU, our parent's approval, a PR, their pull, and
   then their parent's review.
4. **A moving target.** The app is pre-1.0 and Prep A only. Following tags, not `main`, softens it.
5. **Decisions for you:**
   - the bulk import in the Review list, or their Claude submitting with a token (section 3);
   - "Waiting for a song" as the behaviour for a skill with no approved songs;
   - `main` or tags;
   - issues only from them, or PRs from a fork too.

## 6. Order

1. **4.1 Amazing Grace and 4.6 setup**, then a clean-clone build test in a container.
2. **4.2 the song tools flag, 4.5 the engine change, 4.3 the bulk import and approve.** Tests,
   then a deploy to our server: no visible change for us except "Approve all", which we can use
   too.
3. **4.4 local deploys, 4.7 the install guide, 4.9 the architecture doc.**
4. **4.8 the clean-room VM test**, fixing the guide until a fresh Claude gets through it.
5. **Install with the other family.**
6. Later: **4.10 song packs**, starting with a Christmas pack.
