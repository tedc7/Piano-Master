# A fresh install, and keeping the curriculum songs in the repo

How to get the piano app working on a server again, and how to keep the repo ready for that
(architecture §11.2, §11.6, v0.31).

## Which way back

| Situation | Do this | You get back |
| --- | --- | --- |
| The server lost its data, and the backup is fine | **Restore the backup** (the server's own restore procedure: the database, `library/` and `staging/` together), then `tools/deploy.sh` | Everything: the children, their progress, the parent's rules, every approved song with its stems, the review list |
| No usable backup, or a second server | **A new install from the repo**: below | The app, and the curriculum songs as approved. The children and their progress start again; imported songs that aren't on the skill map (the kids' songs batch, say) aren't in the repo and have to be submitted again |

Always prefer the backup. A new install from the repo is for when there's nothing to restore.

## A new install from the repo

1. **The server** (the Server repo's session, not this repo). Its `setup.sh` makes Caddy on the
   server's address with the internal certificate authority, the `piano-api` container with its
   `/opt/piano/data` volume, `/opt/piano/www` and the `piano-api-redeploy` script. Caddy has no
   limit on request size, so the stems' uploads get through. Two things `setup.sh` doesn't do
   (confirmed by the Server session, Oct 5, 2026):
   - **The deploy account.** The ssh host the deploys use (`PIANO_HOST`, below) needs sudo with no
     password for `rsync`, `rm`, `cp`, `chown`, `find` and `mv`, as well as `piano-api-redeploy`,
     because `tools/deploy.sh` copies the app and the API into place with them.
   - **The certificate.** Unless Caddy's data volume is restored from the backup, a rebuilt server
     has a new certificate authority. Copy its root to the dev box (`CADDY_ROOT_CA`, below) and
     install it on every iPad and Chromebook. The scripts never fall back to skipping the
     certificate check: they stop and say so.
2. **The dev box:** clone the repo (with Git LFS installed), and tell the scripts about your
   server. Copy `tools/server.env.example` to `~/.config/piano-master/server.env` and fill it in:
   the site's address (`PIANO_SERVER`), the ssh host for deploys (`PIANO_HOST`, an alias in
   `~/.ssh/config`) and the root certificate's file (`CADDY_ROOT_CA`). It stays outside the repo,
   because the repo is public. Then:

   ```bash
   tools/fresh_install.sh --check     # see what's ready; changes nothing
   tools/fresh_install.sh             # build the tools if needed, fetch the stems, deploy and seed
   ```

   The script is safe to run again. Each step checks first:
   1. the dev tools (`tools/setup.sh` if they're missing);
   2. the curriculum songs' stems (`git lfs pull`);
   3. the content build, and `tools/library_export.py --verify`: every song on the skill map is in
      `content/library/` with every stem it names;
   4. the server, in one ssh connection (the server limits how many it accepts in a row): ssh to
      `PIANO_HOST`, `piano-api-redeploy` and the sudo the deploy needs; then the certificate, and
      whether the API already has songs;
   5. `tools/deploy.sh all --seed-songs`: the API and the app, with `content/library/` as the seed;
   6. `tools/library_check.py`: every song on the map is in the library.

   On its first start, the API adopts the seed as approved (`library.adopt_seed`): only songs it
   doesn't have, isn't reviewing and wasn't told to delete. On a server that already has songs,
   it adds only the missing curriculum songs.
3. **In the app:**
   1. Config: set the parent PIN (asked for on the first visit), then add the children.
   2. Config › Songs and genres: allow the genres each child may see (all are blocked at first).
   3. Config › Dev box connection: make a token for the song skills, and save it on the dev box in
      `~/.config/piano-master/skill-token` (never in the repo).

## Keeping `content/library/` up to date

`content/library/` is the curriculum's part of the server's library, exactly as the parent approved
it:

| File | What |
| --- | --- |
| `index.json` | The library's index entry for each song (its level, skills, unlocking and when it was approved) |
| `<id>.json` | The approved piece: notation, analysis, its media list, its details (license, source) and the parent's finger-number and letter-name choices |
| `media/<id>/*.mp3` | Its stems at the four tempo presets (Git LFS, `.gitattributes`) |

**After the parent approves curriculum songs** (new songs for the map, or Needs improvement fixes
such as new vocals), copy them into the repo and commit:

```bash
tools/.venv/bin/python tools/build_content.py           # the built skill map says which songs are the curriculum
tools/.venv/bin/python tools/library_export.py --check  # what would change
tools/.venv/bin/python tools/library_export.py          # copy it
git add content/library && git commit                   # the stems go to Git LFS
```

The export needs the skill token. It leaves unchanged songs alone, replaces a changed song's files,
and removes songs that are no longer on the map. It copies only songs whose source in
`content/pieces/` is our own or public domain. A song a parent supplied for private family use is
never copied, because the repo is public.

**Sources and approved songs.** `content/pieces/` holds every song's source, which is what we edit.
`content/library/` holds what the parent approved. They differ while a change waits in the review
list: a fresh install gets the approved version.

## The seed's history

v0.27 seeded the library once from `build/songs/`, which held the songs built into the app before
then. Since v0.31, the seed is `content/library/`, and it's used only by `--seed-songs`. Ordinary
deploys never seed, so a song the parent deleted can't come back by itself.
