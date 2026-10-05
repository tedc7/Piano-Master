# Sourced by the dev box's shell scripts: this install's piano server (tools/server.env.example),
# from ~/.config/piano-master/server.env or $PIANO_CONFIG. Variables already set win.
PIANO_CONFIG="${PIANO_CONFIG:-$HOME/.config/piano-master/server.env}"
_pm_set=$(declare -p PIANO_SERVER PIANO_HOST CADDY_ROOT_CA 2>/dev/null || true)
# shellcheck disable=SC1090
[ -f "$PIANO_CONFIG" ] && . "$PIANO_CONFIG"
eval "$_pm_set"
unset _pm_set
for _pm_v in PIANO_SERVER PIANO_HOST CADDY_ROOT_CA; do
  if [ -z "${!_pm_v:-}" ]; then
    echo "$_pm_v isn't set: copy tools/server.env.example to $PIANO_CONFIG and fill it in" >&2
    exit 1
  fi
done
unset _pm_v
PIANO_SERVER="${PIANO_SERVER%/}"
CADDY_ROOT_CA="${CADDY_ROOT_CA/#\~/$HOME}"
