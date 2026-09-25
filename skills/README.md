# Skills (snapshot)

These are **copies** of Claude Code skills that live in `~/.claude/skills/` on the dev box. Claude loads the live copies, not these. They are general-purpose (not tied to this repo) and are kept here as a backup.

| Skill | What it does |
| --- | --- |
| `generate-music` | Songs, vocals and accompaniment from lyrics + a style description (or an ABC score) with the local YuE2 engine; optional vocal/accompaniment stems. Piano-Master media renders use its `piano-master` profile |

Make changes to the live skills, then copy them here to back them up:

```bash
rsync -a --delete --exclude __pycache__ ~/.claude/skills/generate-music/ skills/generate-music/
```

To restore on a new machine:

```bash
cp -a skills/generate-music ~/.claude/skills/
bash ~/.claude/skills/generate-music/scripts/install_engine.sh   # engine + weights into ~/engines/yue2 (~15 GB download)
```

The engine itself (venv, model weights) is not in git; the install script rebuilds it at pinned versions.
