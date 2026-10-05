# Server brief: the song library in the backup, and a restore test that brings it back

Written for the Server repo session.

**Context:** Piano-Master architecture v0.31 (§11.2, §11.6). Since v0.27, every song the app plays
is in `/opt/piano/data/library/`, beside the database. The library holds 113 approved songs today,
each with its notation and its stems, and new vocals arrive every week. `/opt/piano/data/staging/`
holds the songs waiting for the parent's review, the songs sent back, and the songs the parent
deleted. If both are lost, the app has no songs.

Earlier briefs asked for parts of this:
- `server-brief-m4-backup.md`: the database backup and a restore test;
- `server-brief-m7-library.md`, item 1: the library folders in the backup.

Neither has a report back yet in the Piano-Master repo. This brief replaces item 1 of the M7 brief
and extends the M4 restore test to the library.

**What's in `/opt/piano/data`**

| Path | What | Can it be rebuilt? |
| --- | --- | --- |
| `piano.db` (+ `-wal`, `-shm`) | Children, progress, attempts, the parent's rules and choices, the library's records, the review list | No |
| `library/<id>/piece.json`, `library/<id>/media/*.mp3`, `library/index.json` | Every approved song and its stems: 5–25 MB a song with stems | Only partly: since v0.31 the curriculum songs (107) are also in the Piano-Master repo. The imported songs aren't, and re-rendering them takes hours of GPU time and a new review |
| `staging/` | Songs waiting for review, sent back, or deleted, with their files | Partly, by re-running the skills; the parent's deleted songs only from here |

The database and the folders must come from the **same moment**. The library's records are in
`piano.db`, so a database newer than its folders names songs whose files are missing.

**Requirements**
1. **Backup:** the backup job includes `/opt/piano/data/library/` and `/opt/piano/data/staging/`,
   taken right after the consistent SQLite copy (`.backup` or `VACUUM INTO`, as in the M4 brief).
   - The files are written once and replaced whole, never edited in place, so a plain file copy
     after the database copy is consistent enough.
   - Expect 1–3 GB, growing by about 2.5 MB for each song with a vocal.
   - Report the backup's current size and how often it runs.
2. **Restore test**, without touching the live data. Extend the M4 test:
   - Restore the newest backup (the database and both folders) into one scratch directory, from
     the backup store, not from `/opt/piano/data`.
   - Run `PRAGMA integrity_check;` (expect `ok`) and `PRAGMA user_version;` (expect 10 or higher).
   - Start a throwaway API container from the live image with the scratch directory as its data
     volume (`PIANO_DB=<scratch>/piano.db`, and the same layout as the live volume, so `library/`
     and `staging/` sit beside the database). Use no published ports, and reach it with
     `docker exec`.
   - Check:
     - `GET /api/health` reports `ok` and a schema of 10 or higher.
     - `GET /api/library` lists as many songs as the live API, give or take approvals since the
       backup.
     - `GET /api/library/pieces/canyon-echo` returns a piece whose `media.presets["100"].vocals.url`
       is a stem.
     - That stem, fetched with `Range: bytes=0-99`, returns 206 and 100 bytes.
     - `GET /api/students` lists the same students as the live API.
   - Then stop the container and delete the scratch copy.
3. **Restore procedure in the docs:** add the library to the written procedure. Restore
   `piano.db`, `library/` and `staging/` together, owned by the container user, with no stale
   `-wal` or `-shm` files. Then start `piano-api` and check `/api/health` and `/api/library`.
4. **A new server without a backup** (for the docs, and nothing to do now): the Piano-Master repo's
   `tools/fresh_install.sh`, run from the dev box once the server is set up, deploys the app and
   seeds the library with the curriculum songs (`docs/fresh-install.md` in that repo). It needs
   only what the Server repo already provides:
   - ssh as the deploy account with non-interactive sudo for `/usr/local/sbin/piano-api-redeploy`;
   - the `piano-api` container and its `/opt/piano/data` volume;
   - `/opt/piano/www`;
   - Caddy allowing 64 MB request bodies on `/api`.
   Please confirm that list is complete for a server built from scratch by the Server repo's setup.
5. **Keep all existing guarantees:**
   - Caddy stays on `${SERVER_IP}:443` only;
   - `verify-lan.sh` P01 still reports ports 22, 443 and 445;
   - `/opt/piano/data` is never deleted and never `docker compose down -v`;
   - the KB is unaffected.

**Report back:**
- where the library and staging folders land in the backup, how often the backup runs, and its size;
- the restore test's results: the integrity check, the schema, the song counts from both copies, the
  stem's range request, and the students check;
- where the restore procedure is documented;
- whether item 4's list is complete for a new server.

## Report back (Oct 5, 2026): done

From the Server session, in short (the details stay with the server's own docs). This also answers
`server-brief-m4-backup.md` and item 1 of `server-brief-m7-library.md`.

1. **Backup:** the consistent database copy, `library/` and `staging/` are all in the nightly
   backup, and have been since the App API brief. It keeps 30 daily and 12 monthly copies, and is a
   few GB with plenty of room.
2. **Restore test** (the server's `piano-restore-test`, against the newest backup): **passed**.
   - The integrity check is ok; the schema is 10, as `/api/health` reports.
   - The restored API and the live one list the same songs, and a stem's range request returns 206
     with 100 bytes.
   - The students and their progress match, except songs staged after the backup.
   - It runs in a throwaway container with no network, removed afterwards. A deliberately broken
     restore fails the test.
3. **The procedure** is in the server's backup docs: the database, `library/` and `staging/`
   together from one backup, owned by the container's user, with no `-wal` or `-shm` files, and the
   current set moved aside first. The PIN reset is beside it.
4. **A new server: item 4's list wasn't complete.** Confirmed: the server's setup makes Caddy, the
   container and its volume, `/opt/piano/www` and `piano-api-redeploy`, and Caddy has no limit on
   request size. Missing:
   - **The deploy account:** `tools/deploy.sh` needs sudo with no password for `rsync`, `rm`, `cp`,
     `chown`, `find` and `mv`, not only `piano-api-redeploy`. It had been set up by hand; the
     server's bootstrap docs now include it.
   - **The certificate:** unless Caddy's data is restored, a rebuilt server has a new certificate
     authority, and the dev box and every device need its root.

   Fixed here: `tools/fresh_install.sh` checks that sudo (in one ssh connection: the server limits
   how many it accepts in a row). It, `tools/deploy.sh` and the song tools stop with an explanation
   instead of skipping the certificate check. `docs/fresh-install.md` lists both steps.
