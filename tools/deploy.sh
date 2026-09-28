#!/usr/bin/env bash
# Build the content and the client, then deploy to the piano server as https://192.168.2.128/app/
# Touches only /opt/piano/www/app (swapped in whole); everything else on the server is left alone.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${PIANO_HOST:-kb}"
URL="https://192.168.2.128/app/"
CA="${CADDY_ROOT_CA:-$HOME/repos/Server/caddy-root-ca.crt}"
export PATH="$ROOT/.tools/node/bin:$PATH"

"$ROOT/tools/.venv/bin/python" "$ROOT/tools/build_content.py"
(cd "$ROOT/client" && npm run --silent check && npm run --silent test && npm run --silent build)
SRC="$ROOT/client/dist"

rsync -a --delete "$SRC/" "$HOST:/tmp/piano-app/"
ssh "$HOST" 'set -e
  sudo rm -rf /opt/piano/www/app.new
  sudo cp -r /tmp/piano-app /opt/piano/www/app.new
  sudo chown -R root:root /opt/piano/www/app.new
  sudo find /opt/piano/www/app.new -type d -exec chmod 755 {} +
  sudo find /opt/piano/www/app.new -type f -exec chmod 644 {} +
  sudo rm -rf /opt/piano/www/app.old
  if [ -d /opt/piano/www/app ]; then sudo mv /opt/piano/www/app /opt/piano/www/app.old; fi
  sudo mv /opt/piano/www/app.new /opt/piano/www/app
  sudo rm -rf /opt/piano/www/app.old /tmp/piano-app'

# Checks: the page, the content index and one stem load (audio needs range requests on iOS: 206)
curl_opts=(-s -o /dev/null -w "%{http_code}")
if [ -f "$CA" ]; then curl_opts+=(--cacert "$CA"); else curl_opts+=(-k); fi
page=$(curl "${curl_opts[@]}" "$URL")
index=$(curl "${curl_opts[@]}" "${URL}content/index.json")
stem=$(cd "$SRC" && ls media/*/vocals_100.* 2>/dev/null | head -1 || true)
range=$([ -n "$stem" ] && curl "${curl_opts[@]}" -r 0-1023 "${URL}${stem}" || echo "no stems")
echo "page $page, content $index, range request $range"
[ "$page" = 200 ] && [ "$index" = 200 ] && echo "deployed: $URL"
