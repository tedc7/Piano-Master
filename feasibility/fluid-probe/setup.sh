#!/usr/bin/env bash
# Rebuild the probe's tools (all gitignored): FluidSynth (conda-forge, local), a Python venv, and
# the SoundFonts under test. Needs ~/miniconda3 and internet. Nothing is installed system-wide.
set -euo pipefail
cd "$(dirname "$0")"
[ -x .fluidsynth/bin/fluidsynth ] || ~/miniconda3/bin/conda create -q -y -p "$PWD/.fluidsynth" -c conda-forge --override-channels fluidsynth
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q music21 mido soundfile numpy pyyaml librosa
echo "ready: .fluidsynth/bin/fluidsynth $(.fluidsynth/bin/fluidsynth --version | head -1)"
