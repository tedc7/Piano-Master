# Server brief: piano database backup check and restore test (M4)

Written for the Server repo session. Context: Piano-Master milestone M4 (architecture v0.19 §11.2, §12) moved the children's data onto the piano server. `/opt/piano/data/piano.db` now holds the students, their settings, skill states, today's sessions, practice days and every attempt. Unlike the app code, this data can't be recreated. M4's acceptance test includes **a restore test that succeeds**. The earlier brief ([server-brief-app-api.md](server-brief-app-api.md), item 5) asked for the database backup; this brief confirms it and adds the restore test.

**Nothing in the app changes.** The Piano-Master session deploys the API as before (`piano-api-redeploy`). The database schema is now version 3; migrations run when the API starts.

**Requirements**
1. **Backup in place:** confirm that the backup job takes a consistent copy of `/opt/piano/data/piano.db` just before the file backup runs.
   - Use SQLite's online backup (`sqlite3 /opt/piano/data/piano.db ".backup '<dest>'"`) or `VACUUM INTO`. The database is in WAL mode, so a plain file copy of `piano.db` alone can miss recent writes.
   - The rest of `/opt/piano/data` is included too.
   - If item 5 of the earlier brief isn't done yet, do it now.
2. **Restore test** (the M4 acceptance test), without touching the live database:
   - Take the newest backup copy from the backup store (not from `/opt/piano/data`) and restore it into a scratch directory.
   - Run `PRAGMA integrity_check;` (expect `ok`) and `PRAGMA user_version;` (expect 3 or higher).
   - Compare row counts with the live database: `students`, `attempts`, `skill_states`, `sessions`, `practice_days`. They should match, or differ only by activity since the backup.
   - Start a throwaway API container from the same image against the restored copy. For example: `docker run --rm -d --name piano-api-restore-test -e PIANO_DB=/restore/piano.db -v <scratch>:/restore <piano-api image>`, with no published ports, on the compose network or reached with `docker exec`.
   - Check that `GET /api/health` returns `ok` and `GET /api/students` lists the same students as the live API. Then stop the container and delete the scratch copy.
3. **Restore procedure in the docs:** write down how to restore the live database from a backup:
   - stop `piano-api`;
   - keep the current `piano.db`, `piano.db-wal` and `piano.db-shm` aside;
   - put the restored `piano.db` in place, owned by the container user, with no stale `-wal` or `-shm` files beside it;
   - start `piano-api` and check `/api/health`.
4. **Parent PIN reset:** document the exact command for when the parent forgets the PIN `docker exec <piano-api container> python -m app.admin reset-pin`. The app then asks for a new PIN. This needs no secrets in the environment file.
5. **Keep all existing guarantees:**
   - Caddy stays on `${SERVER_IP}:443` only;
   - `verify-lan.sh` P01 still reports ports 22, 443 and 445;
   - `/opt/piano/data` is never deleted and never `docker compose down -v`;
   - the KB is unaffected.

**Report back:**
- where the backup copy of the database lands, and how often it's taken;
- the restore-test results: integrity check, schema version, the row counts from both copies, and the health and students check;
- the restore procedure's location in the docs;
- the container name for the PIN reset command.
