"""Find where each known lyric word starts in a vocal stem (forced alignment, not transcription).

Runs in its own venv (tools/.media/fa: ctc-forced-aligner's ONNX MMS aligner, no PyTorch needed):
    tools/.media/fa/bin/python tools/media/lyric_align.py vocals.flac words.json out.json

words.json: [{"word": ...}, ...] in sung order. out.json: the same list with start/end (seconds)
and "conf", the word's mean log-probability per frame (near 0 = confident, very negative = the
aligner had to force it, e.g. a word YuE2 didn't sing).

Or {"segments": [{"start": s, "end": s, "words": [...]}, ...]}: each segment's words are aligned
in that stretch of audio only, with the model loaded once; times are still from the file's start.
Over a whole song, heavily repeated lyrics (a refrain sung nine times) made one alignment lose its
place by seconds; phrase by phrase it can't drift.

The package's own helpers round the frame stride up to a whole millisecond (21 ms instead of
20.00x ms), which drifts by seconds over a song, so the stride is computed here exactly.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata

import numpy as np
from ctc_forced_aligner import (SAMPLING_FREQ, AlignmentSingleton, generate_emissions, get_alignments, get_spans,
                                load_audio, preprocess_text)


STARS = "segment"


def clean(word):
    """Letters and apostrophes only (the aligner's alphabet has no accents: 'è' crashed it)."""
    w = unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode()
    w = re.sub(r"[^A-Za-z']", "", w).lower()
    return w or "a"


def align_words(audio_path, words, wave=None, offset=0.0):
    model = AlignmentSingleton()
    wave = load_audio(audio_path) if wave is None else wave          # 16 kHz mono float32
    emissions, _ = generate_emissions(model.alignment_model, wave, batch_size=4)
    stride = len(wave) / SAMPLING_FREQ / emissions.shape[0]   # seconds per frame, exact
    text = " ".join(clean(w["word"]) for w in words)
    tokens, text_starred = preprocess_text(text, romanize=False, language="eng", star_frequency=STARS)
    segments, scores, blank = get_alignments(emissions, tokens, model.alignment_tokenizer)
    spans = get_spans(tokens, segments, blank)
    out, k = [], 0
    for i, t in enumerate(text_starred):
        if t == "<star>":
            continue
        span = spans[i]
        a, b = span[0].start, span[-1].end
        frames = scores[0][a:b] if np.ndim(scores) == 2 else scores[a:b]
        out.append({**words[k], "start": round(offset + a * stride, 3), "end": round(offset + b * stride, 3),
                    "conf": round(float(np.mean(frames)) if len(frames) else -99.0, 3)})
        k += 1
    return out


if __name__ == "__main__":
    audio, words_file, out_file = sys.argv[1:4]
    words = json.loads(open(words_file).read())
    if isinstance(words, dict):
        wave = load_audio(audio)
        result = []
        for seg in words["segments"]:
            a, b = max(0, int(seg["start"] * SAMPLING_FREQ)), min(len(wave), int(seg["end"] * SAMPLING_FREQ))
            if seg["words"] and b - a > SAMPLING_FREQ // 2:
                result += align_words(audio, seg["words"], wave[a:b], a / SAMPLING_FREQ)
    else:
        result = align_words(audio, words)
    open(out_file, "w").write(json.dumps(result, indent=1) + "\n")
    print(f"{len(result)} words aligned")
