#!/usr/bin/env bash
# Rebuild the lesson voice's tools (arch §10.5, v0.34; gitignored, in tools/.voice/): Kokoro-82M
# (Apache-2.0) and its voice, and Whisper small.en for the check. Runs on the CPU. Needs python3.12
# and internet once; nothing is installed system-wide. The models go to the Hugging Face cache.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
V="$ROOT/tools/.voice"
[ -x "$V/bin/python" ] || python3.12 -m venv "$V"
"$V/bin/pip" install -q --upgrade pip
"$V/bin/pip" install -q torch==2.10.0 --index-url https://download.pytorch.org/whl/cpu
"$V/bin/pip" install -q -r "$ROOT/tools/voice/requirements.txt"
"$V/bin/python" "$ROOT/tools/voice/lesson_voice.py" fetch
echo "ready: $("$V/bin/python" -c 'import kokoro, torch; print("kokoro", kokoro.__version__, "torch", torch.__version__)')"
