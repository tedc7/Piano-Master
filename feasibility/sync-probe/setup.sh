#!/usr/bin/env bash
# Rebuild the probe's tools (all gitignored): Python venv, Rubber Band CLI, abc2xml, headless Chromium.
# Needs: python3 (3.12+), ~/miniconda3 for the conda-forge Rubber Band build, internet.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q music21 librosa soundfile pyparsing playwright
.venv/bin/python -m playwright install chromium
# Rubber Band 4.0 command line (R3 engine and --timemap); the pylibrb bindings can't pass a time map
~/miniconda3/bin/conda create -q -y -p "$PWD/.rubberband" -c conda-forge --override-channels rubberband
# abc2xml 268 by Willem Vree (LGPL): converts Open Hymnal's ABC Plus, which music21 can't read correctly
mkdir -p tools && curl -sL -o tools/abc2xml.zip https://wim.vree.org/svgParse/abc2xml.py-268.zip
(cd tools && unzip -o -q abc2xml.zip)
# Lyric aligner (ctc-forced-aligner, ONNX MMS model, 1.26 GB in ~/ctc_forced_aligner/model.onnx)
python3 -m venv .fa
.fa/bin/pip install -q --upgrade pip && .fa/bin/pip install -q ctc-forced-aligner soundfile
mkdir -p ~/ctc_forced_aligner
[ -f ~/ctc_forced_aligner/model.onnx ] || curl -L -C - --retry 5 -o ~/ctc_forced_aligner/model.onnx \
  https://huggingface.co/deskpai/ctc_forced_aligner/resolve/main/04ac86b67129634da93aea76e0147ef3.onnx
echo "e8bad67fd3533b3d3c145b0ca31bb15383945c13384dd8975baaa7b73f7b61ac  $HOME/ctc_forced_aligner/model.onnx" | sha256sum -c
echo "ready: convert.py -> render_all.sh -> align.py --mode {dtw,melody,words} -> select_takes.py -> build_site.py -> check_page.py -> deploy.sh"
