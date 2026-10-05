# Server brief: piano App API container and data directory

Written for the Server repo session. Context: the Piano-Master app (architecture §2.5, §4, §11) now has a web client served from `/opt/piano/www/app/` (https://<piano-server>/app/). Its next part is the **App API**: a small Python (FastAPI) service with a SQLite database. The Piano-Master session writes and deploys the API code; this brief covers only the server setup it runs in.

**Goal:** run the App API as a container behind the existing Caddy at `https://<piano-server>/api/`, with its SQLite database in a persistent host directory that is backed up. The site, the KB and every existing guarantee stay unchanged.

**Contract with the app** (the Piano-Master session builds to this):
- **Code:** in `/opt/piano/api` on the host, including its own `Dockerfile` and pinned `requirements.txt`. App deploys replace this folder's contents.
- **Port and health:** the container listens on port 8000 inside the Docker network. `GET /api/health` returns 200 with `{"ok": true, ...}`.
- **Data:** the database is `/data/piano.db` inside the container, from the environment variable `PIANO_DB`. `/data` is where the app keeps all its state; later milestones add `/data/media` (audio stems and videos uploaded by the Skill API).
- **Paths:** the API serves everything under `/api/`. Caddy passes the path through unchanged; don't strip the prefix.

**Requirements**
1. **Service** `piano-api` in `setup/templates/docker-compose.yml.tmpl`:
   - `build: /opt/piano/api`, `restart: unless-stopped`;
   - volume `/opt/piano/data:/data` (read-write);
   - environment `PIANO_DB=/data/piano.db`, `TZ=<the home's time zone>`, since practice days are local calendar days;
   - **no published host ports**: it is reached only by Caddy over the compose network;
   - log rotation the same as the other services.
2. **Caddy:** in the `${SERVER_IP}` site block, `handle /api/*` → `reverse_proxy piano-api:8000`, placed before the existing `file_server`. Keep the same security headers. The static site at `/srv/piano` is unchanged.
3. **Host directories:**
   - `/opt/piano/api`: create it if missing. If it's empty, drop in a placeholder (a minimal `Dockerfile` plus a health endpoint returning `{"ok": true, "placeholder": true}`) so the stack can start before the first app deploy. Like `/opt/piano/www`, setup creates it but doesn't manage its contents after that.
   - `/opt/piano/data`: persistent and writable by the container's user, never touched by setup reruns. Never delete it, and never `docker compose down -v`.
4. **Redeploy helper for app deploys:** a root-owned script, for example `/usr/local/sbin/piano-api-redeploy`. It rebuilds and restarts only `piano-api` (`docker compose … up -d --build piano-api`), waits for `/api/health` (timeout about 60 s), and exits non-zero on failure with the last container log lines. The Piano-Master session calls it with `sudo -n` over ssh after syncing `/opt/piano/api`, so allow that non-interactively for the deploy user. It must not restart Caddy or the KB.
5. **Backup** (arch §11.2):
   - take a consistent copy of `/opt/piano/data/piano.db` just before the file backup runs, using SQLite's online backup (`sqlite3 … ".backup …"`) or `VACUUM INTO`, never a plain file copy of a live database;
   - include the rest of `/opt/piano/data` in the backup.
   - Add a restore note to the docs; a restore test comes after M4.
6. **Keep all existing guarantees:**
   - Caddy stays bound to `${SERVER_IP}:443` only; no port 80;
   - `verify-lan.sh` P01 still reports exactly ports 22, 443 and 445;
   - `caddy_data` is never removed;
   - the family knowledge base's site is unaffected.
7. **Tests** in `verify.sh` / `verify-lan.sh`:
   - `curl --cacert caddy-root-ca.crt https://${SERVER_IP}/api/health` returns 200;
   - `https://${SERVER_IP}/app/` still returns 200;
   - port 8000 is not reachable from the LAN;
   - existing H01–H05 still pass.
8. **Rollout:**
   - `sudo ./setup.sh --dry-run`, `sudo ./setup.sh`, then a second run must report **0 changed**;
   - then `sudo ./verify.sh`, then `./verify-lan.sh` from the workstation;
   - expect a few seconds of KB downtime while Caddy reloads;
   - work on a branch and open a PR as usual.

**Not needed now** (later briefs): the parent-PIN and Skill API secrets in the environment file (M4, M7); a larger request-body limit for media uploads (M7, M8); the optional AI proxy (M9).

**Report back:**
- the service name and compose file path;
- the exact redeploy command and which user may run it with `sudo -n`;
- the container user's uid and gid (for `/opt/piano/data` ownership);
- where the backup copy of the database lands;
- the verify results.
