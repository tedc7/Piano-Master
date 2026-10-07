"""What Whisper hears in a vocal take, against the words it should sing (the words-heard check).

Runs in the aligner's venv (tools/.media/fa, with faster-whisper):
    tools/.media/fa/bin/python tools/media/hear.py vocals.flac out.json

out.json: {"heard": the transcript}. The media tool scores it against the words (align.heard_share),
so a change to the scoring needs no new transcription.

The lyric aligner finds where each known word sits, so it can't tell a garbled word from one it
couldn't place: it misses short words ("a", "the") and same-pitch neighbours ("lit-tle lamb") in
takes that sing them clearly (Mary Had a Little Lamb, Oct 7, 2026: 30% "off", every word heard).
Whisper doesn't know the words, so what it hears is what a listener would. Same model as the
lesson voice's check (small.en, on the CPU).
"""
from __future__ import annotations

import json
import sys

import numpy as np
import soundfile as sf

WHISPER = "small.en"


def main(audio_path: str, out_path: str) -> None:
    from faster_whisper import WhisperModel
    a, sr = sf.read(audio_path, dtype="float32")
    if a.ndim > 1:
        a = a.mean(axis=1)
    # to Whisper's 16 kHz in the frequency domain: a plain interpolation aliases (the lesson voice's finding)
    n = round(len(a) * 16000 / sr)
    x = np.fft.irfft(np.fft.rfft(a)[: n // 2 + 1], n) * (n / len(a))
    segs, _ = WhisperModel(WHISPER, device="cpu", compute_type="int8").transcribe(
        x.astype(np.float32), language="en", beam_size=5)
    json.dump({"heard": " ".join(s.text.strip() for s in segs)}, open(out_path, "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:3])
