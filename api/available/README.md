# Songs from the app

`tools/deploy.sh` fills this folder on a piano server without song tools (another family's install,
`docs/install-guide.md`): the approved curriculum songs from `content/library/` as
`curriculum/`, and any song packs pulled from `content/packs/`. The API image keeps them in a layer
of their own (`/srv/available`, `PIANO_APP_SONGS`), and the parent brings them into the Review list
(arch §10.7, v0.51). Nothing here is approved on that server until the parent approves it.

Only this file is in git.
