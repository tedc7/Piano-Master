#!/usr/bin/env bash
# The melisma probe's own tools (gitignored): Praat's pitch-synchronous resynthesis through
# parselmouth (GPL-3), in a venv of its own so the project's tools/.venv is left as it is.
# Everything else the probe uses is the media skill's (tools/setup.sh, tools/media/setup.sh).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
python3 -m venv "$HERE/.venv"
"$HERE/.venv/bin/pip" install -q --upgrade pip
"$HERE/.venv/bin/pip" install -q "praat-parselmouth==0.4.7" numpy soundfile
"$HERE/.venv/bin/python" -c "import parselmouth; print('ready: parselmouth', parselmouth.__version__, 'Praat', parselmouth.PRAAT_VERSION)"
