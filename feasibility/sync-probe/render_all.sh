#!/usr/bin/env bash
# Render every YuE2 request under build/*/yue2/ into renders/<id>/, one at a time (one GPU).
# A folder that already has report.json is skipped, so this can be re-run after a failure.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
GEN="$HOME/.claude/skills/generate-music/scripts/generate_music.py"
mkdir -p "$HERE/renders"
for req in "$HERE"/build/*/yue2/request*.json; do
  id=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['id'])" "$req")
  if [ -f "$HERE/renders/$id/report.json" ]; then echo "skip $id"; continue; fi
  rm -rf "$HERE/renders/$id"
  echo "=== $id $(date +%T)"
  python3 "$GEN" --request "$req" --out "$HERE/renders" 2>"$HERE/renders/$id.log" | tail -1 | python3 -c "
import json,sys; d=json.loads(sys.stdin.read() or '{}')
print(' ', d.get('status'), d.get('audio_seconds'), 'score', d.get('score_nominal_seconds'), 'truncated', d.get('truncated'), 'time', (d.get('timing_seconds') or {}).get('yue2_total'), 'vram', d.get('peak_vram_gib'), d.get('error') or d.get('reason') or '')"
done
echo "done $(date +%T)"
