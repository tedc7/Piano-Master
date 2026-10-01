# Server brief: the song library's files (M7)

Written for the Server repo session. Context: Piano-Master milestone M7 (architecture v0.23 §10.7,
§10.9) moves imported songs onto the piano server. The App API now keeps files beside its database,
in `/opt/piano/data` (the container's `/data`, the same volume as `piano.db`):

| Folder | What | Size |
| --- | --- | --- |
| `library/` | Approved songs: `library/<id>/piece.json` and its stems (`media/*.mp3`), plus `library/index.json` | About 5–25 MB a song with stems; a few hundred songs is a few GB |
| `staging/` | Every song not in the library: waiting for the parent's review, sent back for changes, or deleted (kept so it can be restored or corrected) | Emptied as songs are approved or forgotten |

Nothing to change for these to work: the API writes them itself, as the container's user, under the
existing volume. Please check:

1. **Backup:** the existing file backup of `/opt/piano/data` now includes these folders. Both should
   be backed up: the notation and stems can be rebuilt on the dev box, but only with its GPU and
   some hours of work, and `staging/` also holds the parent's deleted songs. Since architecture
   v0.27, `library/` holds **every** song the app plays, including the 108 lesson songs that used to
   ship with the app, so without it the app has no songs until they're restored.
2. **Disk:** there's room for a few GB more under `/opt/piano/data`.
3. **Uploads through Caddy:** the dev box uploads each stem with `PUT /api/skill/packages/.../media/<file>`
   (up to 64 MB a file). If Caddy limits request bodies on the `/api` route, allow at least 64 MB there.
4. **Range requests:** the app's audio is served by the API (`GET /api/library/media/<id>/<file>`) with
   range support (206), which iOS needs. Check that Caddy passes `Range` through (it does by default).

The dev box's token for the Skill API is made in the app (Config › Dev box connection) or in
the container: `docker exec docmost-piano-api-1 python -m app.admin skill-token "dev box"`.
