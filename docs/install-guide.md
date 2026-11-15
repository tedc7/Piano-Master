# Installing Piano-Master on a family's home server

**Written for Claude Code**, running on the family's own Linux server, helping a parent install
the app and keep it up to date. The parent may not know the details below: you do the work, explain
each step in plain words, and ask before anything that changes the system (packages, sudo rules,
the firewall, a restore). Architecture: `docs/architecture.md` §11.7 (v0.51).

This install has **no song tools**. The maintainers make every song, vocal, backing and lesson
recording on their own machine (a GPU and their own Claude skills), approve them, and put them in
this repository. Your family gets them with each update, and the parent approves each song in the
app's **Review list** before a child sees it. Nothing about your family ever leaves your server.

## 1. Rules for you, Claude, in this repository

Save these rules on the family's server so every later session follows them. Write them to
`CLAUDE.local.md` at the repo root, and add `CLAUDE.local.md` to `.git/info/exclude`, so they stay
out of git. Claude Code reads that file in every session in this folder.

```markdown
# Piano-Master on this family's server

This is a family install of Piano-Master (docs/install-guide.md). Follow these rules:

- **Don't use the repo's song skills** (import-song, make-media, lesson-voice, generate-music).
  They need the maintainers' GPU pipeline and a server with song tools, and this one has none. For
  a new song, a fix, or a lesson recording, tell the parent it goes to the app's maintainers.
- **Don't change the repo.** No edits to tracked files, no commits, no branches, no pushes. Update
  only with `git pull` on `main`. This family's own settings live outside the repo
  (~/.config/piano-master/, /opt/piano/stack/).
- **Nothing private goes to GitHub or to the maintainers.** That covers children's names, ages,
  photos and recordings, and the family's address. It also covers IP addresses, server names,
  tokens, the PIN and anything from the database. When the parent wants to report a problem,
  describe the song, the bar and what's wrong. Show the parent the exact text before it's sent.
  GitHub issues are public.
- **Never skip a certificate check** (no curl -k): fix the certificate instead.
- **Never delete /opt/piano/data, and never run `docker compose down -v`.** Back up before every
  update (docs/install-guide.md §9).
- **Every song goes through the parent's Review list.** Never approve songs for the parent, and
  never call the app's approve endpoints yourself.
```

## 2. What the family needs

| What | Requirement |
| --- | --- |
| **Server** | A Linux machine that stays on, on the home network: **Ubuntu Server 26.04 LTS** (x86-64), the version the maintainers run. 24.04 LTS should work, since the app runs in Docker, but it's untested. 2 GB of free memory, 10 GB of free disk (the songs take about 0.4 GB and grow with updates), wired or reliable Wi-Fi. |
| **A fixed address** | The server's IP address must never change: a **DHCP reservation** in the home router. The iPad opens the app by that address, and the certificate is for it. |
| **Student device** | An **iPad** (10 inches or larger, landscape) with **MIDIWeb Browser** (by 5of12, App Store). Safari has no Web MIDI, so a USB piano needs MIDIWeb Browser. |
| **Piano** | A **class-compliant USB MIDI keyboard**: the specifications say "USB MIDI" or "class compliant". Some budget keyboards have a USB port only for music files. Velocity-sensitive keys and a sustain pedal jack are recommended. A USB cable to the iPad (USB-C, or Apple's camera adapter). |
| **Without a MIDI piano** | The app can listen through the iPad's microphone instead (Config › Device settings), which works in MIDIWeb Browser. It's a stand-in with limits. It hears C2 to B5 well and C6 to C8 mostly, and misses most of the lowest octave. It can't hear the pedal, and it guesses how hard a key was played. Fast repeated notes can merge, and the room must be quiet. The first level's songs (C2 to D♯6) work with it. The scoring of loud and soft, held notes and the pedal, from Level 3, needs MIDI. |
| **Internet** | Only to install and update. Daily practice needs none. |

## 3. Packages on the server

Ask the parent before installing. Then:

- **Docker Engine with the compose plugin**, from Docker's own apt repository (follow
  docs.docker.com, "Install Docker Engine on Ubuntu"), not the `docker.io` package.
- `sudo apt install git git-lfs rsync sqlite3 curl unzip python3-venv python3-pip`
- **Node.js 22**, for building the app. Any packaged Node 22 works (for example NodeSource's
  `nodejs` 22.x). `tools/setup.sh` uses it when `node --version` says v22. Otherwise it needs
  Miniconda at `~/miniconda3`.
- Make sure the server's time zone is the family's (`timedatectl`): practice days are local days.

## 4. The server's setup

The maintainers' own server is set up by a private repository. This section describes what the
app needs, so you can set up the same on this server. The paths below are what the app's scripts
expect. Keep them.

### 4.1 Folders

| Path | Owner, mode | What |
| --- | --- | --- |
| `/opt/piano/www` | root, 755 | The app's files; deploys replace `/opt/piano/www/app/` |
| `/opt/piano/api` | root, 755 | The App API's code and its Dockerfile; deploys replace it |
| `/opt/piano/data` | **10001:10001, 750** | The database, the song library and the review area. **The family's data: never delete it, never `down -v`, never let a deploy touch it.** Create it once. |
| `/opt/piano/stack` | root | `compose.yml`, `Caddyfile`, `root.crt` (below) |

### 4.2 `/opt/piano/stack/compose.yml`

```yaml
# Piano-Master: Caddy (HTTPS on the home network only) and the App API.
services:
  caddy:
    image: caddy:2.10
    restart: unless-stopped
    ports:
      - "SERVER_IP:443:443"        # the server's fixed LAN address only; no port 80
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data           # holds the family's certificate authority: never remove it
      - caddy_config:/config
      - /opt/piano/www:/srv/piano:ro
    mem_limit: 256m

  piano-api:
    build: /opt/piano/api          # the app's own Dockerfile; tools/deploy.sh replaces this folder
    user: "10001:10001"            # may write only under /data
    init: true
    environment:
      PIANO_DB: /data/piano.db
      TZ: "Europe/London"          # the family's time zone: practice days are local days
    volumes:
      - /opt/piano/data:/data
    restart: unless-stopped
    mem_limit: 512m
    # no ports: only Caddy reaches it, over the compose network

volumes:
  caddy_data:
  caddy_config:
```

### 4.3 `/opt/piano/stack/Caddyfile`

```
{
	# iPads that open the site by IP address send no SNI: without this, Caddy picks the wrong certificate
	default_sni SERVER_IP
}

SERVER_IP {
	tls internal                     # Caddy's own certificate authority, no internet needed

	redir / /app/
	handle /api/* {                  # handle, not handle_path: the API serves under /api/
		reverse_proxy piano-api:8000
	}
	handle {
		root * /srv/piano
		file_server
	}

	encode zstd gzip
	header {
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options "nosniff"
		X-Frame-Options "SAMEORIGIN"
		Referrer-Policy "strict-origin-when-cross-origin"
		-Server
	}
}
```

Replace `SERVER_IP` with the fixed address. Caddy has no limit on request size, which is right.
Don't add one to `/api`.

### 4.4 Start Caddy, and keep its root certificate

```bash
cd /opt/piano/stack && sudo docker compose up -d caddy
sudo docker compose exec caddy cat /data/caddy/pki/authorities/local/root.crt | sudo tee /opt/piano/stack/root.crt >/dev/null
mkdir -p ~/.config/piano-master && cp /opt/piano/stack/root.crt ~/.config/piano-master/server-root-ca.crt
```

`piano-api` starts with the first deploy: its folder is empty until then. The root certificate is
valid for 10 years, and Caddy renews everything under it with no internet. It lives in the
`caddy_data` volume. If that volume is ever lost, there is a new authority, and every iPad needs the
new root (§6).

### 4.5 `/usr/local/sbin/piano-api-redeploy` (root, 755)

Deploys call it after replacing `/opt/piano/api`:

```bash
#!/usr/bin/env bash
# Rebuild and restart only piano-api, then wait for /api/health through Caddy.
set -Eeuo pipefail
COMPOSE=/opt/piano/stack/compose.yml
HEALTH=https://SERVER_IP/api/health
(( EUID == 0 )) || { echo "run as root" >&2; exit 2; }
[[ -f /opt/piano/api/Dockerfile ]] || { echo "no Dockerfile in /opt/piano/api" >&2; exit 2; }
exec 9>/run/lock/piano-api-redeploy.lock
flock -n 9 || { echo "another redeploy is running" >&2; exit 3; }
docker compose -f "$COMPOSE" up -d --build --no-deps piano-api || { docker compose -f "$COMPOSE" logs --tail 40 piano-api >&2; exit 1; }
for _ in $(seq 30); do
  if curl -sf --max-time 3 --cacert /opt/piano/stack/root.crt "$HEALTH" | grep -q '"ok": *true'; then
    docker image prune -f >/dev/null 2>&1 || true
    echo healthy; exit 0
  fi
  sleep 2
done
echo "not healthy after 60 s" >&2; docker compose -f "$COMPOSE" logs --tail 40 piano-api >&2; exit 1
```

### 4.6 Sudo for the deploys

`tools/deploy.sh` copies the app into place as root, and you run it non-interactively. So the
account you run as needs these commands with sudo and no password, in
`/etc/sudoers.d/piano-deploy` (edit it with `visudo -f`):

```
USER ALL=(root) NOPASSWD: /usr/bin/rsync, /usr/bin/rm, /usr/bin/cp, /usr/bin/chown, /usr/bin/find, /usr/bin/mv, /usr/local/sbin/piano-api-redeploy
```

**Tell the parent plainly what this means.** Commands like `rsync` and `cp` as root are nearly as
powerful as root. It's the same as the maintainers' setup, and it's the parent's account. If they'd
rather not, they can type `sudo -v` in a terminal before each update, which allows sudo for a few
minutes, and you run the deploy then.

### 4.7 The firewall

The site is for the home network only. Allow ssh (if used) and 443 from the local network, and
nothing from outside. **Never forward a port to it from the router.** The parent's PIN keeps
children out of parent mode. It isn't protection against strangers.

## 5. The repository and the first install

```bash
git clone https://github.com/tedc7/Piano-Master.git ~/Piano-Master
cd ~/Piano-Master
git lfs install --local && git lfs pull        # the songs' audio (about 0.4 GB)
```

Then write the rules from §1 to `CLAUDE.local.md`.

`~/.config/piano-master/server.env` (never in the repo):

```bash
PIANO_SERVER=https://SERVER_IP
PIANO_HOST=local                  # the server is this machine: no ssh
CADDY_ROOT_CA=~/.config/piano-master/server-root-ca.crt
# no PIANO_SONG_TOOLS line: this install has no song tools
```

```bash
tools/setup.sh --no-browser       # the build tools: a Python venv and the client's packages
tools/fresh_install.sh --check    # what's ready; changes nothing
tools/fresh_install.sh            # builds, tests, deploys the API and the app
```

`fresh_install.sh` checks the dev tools, the songs' audio, the content, this machine's sudo and
the certificate. Then it runs `tools/deploy.sh all`, which runs the tests, builds the app, and puts
the app and the API in place. Every curriculum song comes with the API as a **song from the app**,
waiting for the parent. It says when it's done: `Installed: https://SERVER_IP/app/`.

## 6. The certificate on the iPad (with the parent)

The site uses the family's own certificate authority (§4.4). Each device trusts it once:

1. Get `/opt/piano/stack/root.crt` to the iPad: AirDrop it from a Mac, email it to the parent's
   own address, or put it on a USB stick and open it in Files.
2. Open it on the iPad. It says "Profile Downloaded".
3. **Settings › Profile Downloaded › Install** (enter the iPad passcode).
4. **Settings › General › About › Certificate Trust Settings**: turn on full trust for it. This
   step is easy to miss, and without it the site stays untrusted.
5. Install **MIDIWeb Browser**, open `https://SERVER_IP/app/`, and confirm there's no warning.

A laptop or Chromebook for the parent needs the same root: macOS Keychain (Always Trust), Windows
"Trusted Root Certification Authorities", or ChromeOS Settings › Privacy › Manage certificates ›
Authorities.

## 7. The first day, in the app (the parent, with you explaining)

1. **Parent** on the start screen: choose a PIN (4 to 8 digits).
2. **Config › Students**: add each child.
3. **Config › Review list**: *Songs from the app* shows the songs this version brings.
   **Bring into review** puts them all in the list. The parent listens to a few (▶ Listen and
   play), then uses **Approve all…**. Until a skill's songs are approved, its Journey bubble says
   **Waiting for a song**, and Today's Practice says the songs are waiting.
4. **Config › Songs and genres**: allow the genres each child may see. All genres start blocked,
   so Amazing Grace, for example, needs Hymns. The Journey's own practice songs are always allowed.
5. **Config › Device settings**: MIDI or the microphone, and the keyboard size (61 or 88 keys).
6. **Config › Piano check** (every key lights up; chords; the pedal), then **Latency
   calibration** (tap one key along with the clicks).
7. On the iPad: MIDIWeb Browser's **full-screen mode**. The app reminds the child when it's off.
   For stricter lockdown, iPadOS **Guided Access**.

## 8. Checks

Run these after the install and after any change to the setup:

| Check | Expect |
| --- | --- |
| `curl -s --cacert /opt/piano/stack/root.crt https://SERVER_IP/api/health` | `"ok": true` and `"songTools": false` |
| `curl -s -o /dev/null -w '%{http_code}' --cacert /opt/piano/stack/root.crt https://SERVER_IP/app/` | `200` |
| From another machine on the network: `curl -sk https://SERVER_IP:8000/` | No connection: the API isn't exposed |
| `stat -c '%u:%g %a' /opt/piano/data` | `10001:10001 750` |
| `tools/fresh_install.sh --check` | `Checks passed` |
| `sudo /usr/local/sbin/piano-backup` then a restore test (§9) | A backup, and a test that passes |

## 9. Backups (the family's own)

The children's progress exists only on this server, so **without a backup, a failed disk loses
it**. Set up a nightly backup, and keep copies off the server's own disk (a USB disk or a NAS,
whichever the parent has).

`/usr/local/sbin/piano-backup` (root, 755):

```bash
#!/usr/bin/env bash
# The database (a consistent copy, never a plain copy of the live file), then the songs, from the same minute.
set -euo pipefail
DEST=/var/backups/piano KEEP=14
d="$DEST/$(date +%F)"; mkdir -p "$d"
sqlite3 /opt/piano/data/piano.db ".backup '$d/piano.db'"
[ "$(sqlite3 "$d/piano.db" 'PRAGMA integrity_check;')" = ok ] || { echo "backup copy failed its check" >&2; exit 1; }
tar -C /opt/piano/data -cf "$d/songs.tar" library staging
ls -1d "$DEST"/*/ | sort | head -n -"$KEEP" | xargs -r rm -rf
```

Run it nightly with a systemd timer (or root's crontab), then copy `/var/backups/piano` off the box.

**Restore test** (do it once after setting up, and after big updates). Restore into a scratch folder
and start a throwaway API on it, with no network:

```bash
B=/var/backups/piano/$(ls /var/backups/piano | tail -1); T=/var/tmp/piano-restore
sudo rm -rf $T && sudo mkdir -p $T && sudo cp $B/piano.db $T/ && sudo tar -C $T -xf $B/songs.tar && sudo chown -R 10001:10001 $T
IMG=$(sudo docker compose -f /opt/piano/stack/compose.yml images -q piano-api)
sudo docker run -d --rm --name piano-restore-test --network none --user 10001:10001 -v $T:/data -e PIANO_DB=/data/piano.db $IMG
sleep 5; sudo docker exec piano-restore-test python -c "import json,urllib.request as u; g=lambda p: json.load(u.urlopen('http://127.0.0.1:8000'+p)); print(g('/api/health')['ok'], len(g('/api/library')['pieces']), 'songs', len(g('/api/students')['students']), 'students')"
sudo docker stop piano-restore-test; sudo rm -rf $T
```

Expect `True`, and the same song and student counts as the live app.

**Restoring for real:**
1. `sudo docker compose -f /opt/piano/stack/compose.yml stop piano-api`.
2. Move `/opt/piano/data` aside; never delete it.
3. Make a new `/opt/piano/data` (10001:10001, 750) with the backup's `piano.db`, and unpack
   `songs.tar` into it. Leave out any `piano.db-wal` or `piano.db-shm`.
4. Start `piano-api`, and check health, the library and the students.

**A forgotten PIN:**
`sudo docker compose -f /opt/piano/stack/compose.yml exec piano-api python -m app.admin reset-pin`.
The app asks for a new PIN on the next visit.

## 10. Updating

When the parent asks for an update, or the maintainers say there's a new version:

```bash
sudo /usr/local/sbin/piano-backup                       # first, always: database changes are one-way
cd ~/Piano-Master && git pull && git lfs pull
tools/deploy.sh                                         # tests, builds, deploys the API and the app
```

- The API's database changes (migrations) run by themselves when it starts. There's no going back
  to an older version except by restoring the backup.
- Then tell the parent to open **Config › Review list**. *Songs from the app* says what's new: new
  songs, and **updates** to songs they have (a fixed vocal, corrected notes). An update shows what
  changed, the children keep the old version until the parent approves it, and approving keeps
  every child's stars. If the parent discards an update, that version isn't offered again.
- The skill map, the lessons and the app itself change with the update, without review. Only songs
  go through the Review list.
- A deploy that fails changes nothing that works. Show the parent the error. The API's log is
  `sudo docker compose -f /opt/piano/stack/compose.yml logs --tail 50 piano-api`.

**Song packs** (when the maintainers publish them, such as a Christmas pack, in `content/packs/`):
`git lfs pull --include "content/packs/<pack>/**"`, then `tools/deploy.sh`. The pack appears in
*Songs from the app* for the parent to bring in and approve.

## 11. Troubleshooting

| The parent sees | Look at |
| --- | --- |
| "Can't reach the piano server" | Is the iPad on the home Wi-Fi? Is the server's address still the reserved one? `docker compose ps`, and health (§8) |
| A certificate warning | The iPad doesn't fully trust the root yet (§6, step 4), or `caddy_data` was lost and the root changed |
| No piano | The cable or adapter, the keyboard is class-compliant, MIDIWeb Browser (not Safari), Config › Piano check |
| No sound | The iPad's volume; the silent switch; reload the page after the iPad wakes |
| "Microphone silent" | Another app (a call, Siri) has the microphone: close it, or reload |
| A song is wrong (a note, a word, the vocal) | Note the song and the bar; it goes to the maintainers (§1's rules) |
| Today's Practice says songs are waiting | Config › Review list: songs from the app to bring in and approve |

## 12. What this app is

A practice app for children learning piano at home. It's in active development: today it teaches
the first level, and later levels come with updates. It runs entirely on
your server and needs no internet to practise. The app's code is GPL-3.0. Its piano sound is the
Salamander Grand Piano (CC BY 3.0). The backings were rendered with the MuseScore General
SoundFont. Each song's source and license are in its details in the Review list.
