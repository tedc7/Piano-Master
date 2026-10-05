#!/usr/bin/env bash
# A new piano server from this repo (docs/fresh-install.md, arch §12): the app, the API and the
# approved curriculum songs. Run it on the dev box once the Server repo has set the server up
# (Caddy, the piano-api container and its /opt/piano/data volume, piano-api-redeploy).
# Safe to run again: each step checks before it acts, and the library only takes songs it doesn't
# already have (or that the parent deleted).
#   tools/fresh_install.sh            check, then deploy and seed the curriculum songs
#   tools/fresh_install.sh --check    the checks only; nothing is changed here or on the server
# Restoring the server from a backup instead? Don't run this: restore the backup (the Server repo's
# procedure), then tools/deploy.sh. The backup has the children's progress; this has only songs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# The server's address, ssh host and certificate: ~/.config/piano-master/server.env
# (copy tools/server.env.example; never commit it).
. tools/server_env.sh
HOST="$PIANO_HOST"
SERVER="$PIANO_SERVER"
CA="$CADDY_ROOT_CA"
CHECK=no
[ "${1:-}" = --check ] && CHECK=yes
step() { printf '\n== %s\n' "$*"; }
fail() { echo "fresh install stopped: $*" >&2; exit 1; }
# The server's own certificate authority, never curl -k: a rebuilt server whose Caddy data wasn't
# restored has a new one, and the dev box and every device need its root.
[ -f "$CA" ] || fail "no root certificate at $CA (CADDY_ROOT_CA): copy the server certificate authority's root there"
curl_opts=(-s --max-time 15 --cacert "$CA")

step "1. Dev tools (tools/setup.sh)"
if [ -x tools/.venv/bin/python ] && [ -x .tools/node/bin/node ] && [ -d client/node_modules ]; then
  echo "ready"
elif [ "$CHECK" = yes ]; then
  fail "the dev tools aren't built: run tools/setup.sh"
else
  tools/setup.sh
fi

step "2. The curriculum songs' stems (Git LFS)"
command -v git-lfs >/dev/null || fail "git-lfs isn't installed (it holds content/library/media)"
if [ "$CHECK" = no ]; then
  git lfs install --local >/dev/null
  git lfs pull --include "content/library/media/**"
fi
echo "$(find content/library/media -name '*.mp3' 2>/dev/null | wc -l) stem files"

step "3. The content, and the curriculum songs it needs"
tools/.venv/bin/python tools/build_content.py | tail -1
tools/.venv/bin/python tools/library_export.py --verify || fail "content/library/ is incomplete (see above)"

step "4. The server (the Server repo's part)"
# tools/deploy.sh copies the app and the API into place with sudo, not only the redeploy script:
# the deploy account and its sudo rule are part of the server's setup (docs/fresh-install.md).
# One ssh connection for all of it: the server limits how many it accepts in a row.
missing=$(ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" 'test -x /usr/local/sbin/piano-api-redeploy || echo piano-api-redeploy-not-installed
  for c in rsync rm cp chown find mv /usr/local/sbin/piano-api-redeploy; do sudo -n -l "$c" >/dev/null 2>&1 || echo "$c"; done') \
  || fail "can't reach the server over ssh as '$HOST' (PIANO_HOST)"
case "$missing" in
  *not-installed*) fail "piano-api-redeploy isn't installed on $HOST: set the server up with the Server repo first" ;;
  ?*) fail "the deploy account on $HOST can't run these with sudo and no password: $(echo $missing) (the server's setup: docs/fresh-install.md)" ;;
esac
echo "ssh and sudo: ready"
rc=0; health=$(curl "${curl_opts[@]}" "$SERVER/api/health") || rc=$?
case $rc in
  35|51|58|60|77|83|90|91) fail "$SERVER's certificate doesn't verify with $CA (curl error $rc). A rebuilt server has a new certificate authority unless its Caddy data was restored: copy the new root to the dev box and every iPad" ;;
esac
if [ -n "$health" ] && songs=$(curl "${curl_opts[@]}" "$SERVER/api/library" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['pieces']))" 2>/dev/null); then
  echo "the API answers: $health"
  [ "$songs" -gt 0 ] && echo "its library already has $songs songs: only the missing curriculum songs will be added"
else
  echo "the API isn't answering yet (a new server): the deploy starts it"
fi

if [ "$CHECK" = yes ]; then
  step "Checks passed. Without --check this deploys: tools/deploy.sh all --seed-songs"
  exit 0
fi

step "5. Deploy the app and the API, seeding the curriculum songs"
tools/deploy.sh all --seed-songs

step "6. Every song on the map is in the library"
tools/.venv/bin/python tools/library_check.py

cat <<EOF

Installed: $SERVER/app/
Next, in the app (docs/fresh-install.md):
  1. Config: set the parent PIN (asked for on the first visit), then add the children.
  2. Config > Songs and genres: allow the genres each child may see (all are blocked at first).
  3. Config > Dev box connection: make a token for the song skills, and save it on the dev box in
     ~/.config/piano-master/skill-token (never in the repo).
EOF
