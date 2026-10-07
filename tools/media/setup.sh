#!/usr/bin/env bash
# Rebuild the media skill's tools (arch §10.5; all gitignored, in tools/.media/). Needs tools/.venv
# (tools/setup.sh), ~/miniconda3 and internet. YuE2 itself is the generate-music skill's engine
# (~/engines/yue2, its own installer). Nothing is installed system-wide.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
M="$ROOT/tools/.media"
mkdir -p "$M/soundfonts"
# analysis and MIDI in the tools venv: librosa (pitch, onsets), soundfile, mido, scipy
"$ROOT/tools/.venv/bin/pip" install -q -r "$ROOT/tools/media/requirements.txt"
# FluidSynth 2.6 (renders the backing) and Rubber Band 4 (the vocal's time map and tempo versions;
# the Python bindings can't pass a time map), both from conda-forge
[ -x "$M/fluidsynth/bin/fluidsynth" ] || ~/miniconda3/bin/conda create -q -y -p "$M/fluidsynth" -c conda-forge --override-channels fluidsynth
[ -x "$M/rubberband/bin/rubberband" ] || ~/miniconda3/bin/conda create -q -y -p "$M/rubberband" -c conda-forge --override-channels rubberband
# MuseScore General 0.2 (MIT; its acknowledgements are in the app's credits)
SF="$M/soundfonts/MuseScore_General.sf3"
[ -f "$SF" ] || curl -sfL -o "$SF" https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General/MuseScore_General.sf3
[ -f "$M/soundfonts/MuseScore_General_License.md" ] || curl -sfL -o "$M/soundfonts/MuseScore_General_License.md" \
  https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General/MuseScore_General_License.md
# lyric aligner (ctc-forced-aligner, ONNX MMS model, 1.26 GB in ~/ctc_forced_aligner/model.onnx), in its own venv,
# with Whisper (faster-whisper small.en, the lesson voice's) for the words-heard check
[ -x "$M/fa/bin/python" ] || python3 -m venv "$M/fa"
"$M/fa/bin/pip" install -q --upgrade pip && "$M/fa/bin/pip" install -q ctc-forced-aligner soundfile faster-whisper
mkdir -p ~/ctc_forced_aligner
[ -f ~/ctc_forced_aligner/model.onnx ] || curl -L -C - --retry 5 -o ~/ctc_forced_aligner/model.onnx \
  https://huggingface.co/deskpai/ctc_forced_aligner/resolve/main/04ac86b67129634da93aea76e0147ef3.onnx
echo "e8bad67fd3533b3d3c145b0ca31bb15383945c13384dd8975baaa7b73f7b61ac  $HOME/ctc_forced_aligner/model.onnx" | sha256sum -c
test -f ~/engines/yue2/INSTALLED.json || echo "note: YuE2 is not installed (bash ~/.claude/skills/generate-music/scripts/install_engine.sh)"
echo "ready: $("$M/fluidsynth/bin/fluidsynth" --version | head -1); $("$M/rubberband/bin/rubberband" --version 2>&1 | head -1)"
