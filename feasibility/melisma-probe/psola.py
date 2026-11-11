"""Bend a voice's pitch along a contour with Praat's overlap-add resynthesis (PSOLA).
Run with the probe's own venv (feasibility/melisma-probe/.venv, set up by setup.sh):

    .venv/bin/python psola.py in.wav contour.json out.wav

contour.json: [[seconds, semitones], ...], linear between the points, 0 before the first and after
the last. Only the pitch tier changes; durations and unvoiced sound are kept.
"""
import json
import sys

import numpy as np
import parselmouth
from parselmouth.praat import call

FLOOR, CEILING, STEP = 90.0, 900.0, 0.005      # the voice's range (YuE2 sings A2 to about G5), 5 ms pitch points

src, contour, dst = sys.argv[1:4]
pts = json.load(open(contour))
snd = parselmouth.Sound(src)
if not pts:
    snd.save(dst, "WAV")
    sys.exit(0)
ts, ss = np.array([p[0] for p in pts]), np.array([p[1] for p in pts])


def bend(mono: parselmouth.Sound) -> tuple[parselmouth.Sound, int, int]:
    manip = call(mono, "To Manipulation", STEP, FLOOR, CEILING)
    tier = call(manip, "Extract pitch tier")
    n = call(tier, "Get number of points")
    times = np.array([call(tier, "Get time from index", i) for i in range(1, n + 1)])
    hz = np.array([call(tier, "Get value at index", i) for i in range(1, n + 1)])
    shift = np.interp(times, ts, ss, left=0.0, right=0.0)
    new = call("Create PitchTier", "bent", mono.xmin, mono.xmax)
    for t, f, s in zip(times, hz, shift):
        call(new, "Add point", float(t), float(f * 2 ** (s / 12)))
    call([new, manip], "Replace pitch tier")
    return call(manip, "Get resynthesis (overlap-add)"), int(n), int(np.sum(np.abs(shift) > 0.01))


# A stereo stem is bent as its mono sum. Bending each channel by itself was tried (Nov 10, 2026): the
# two channels' periods are laid independently, and their correlation inside the bent regions fell
# from 0.64 to 0.07 (a smeared image that cancels in mono). The caller puts the mono result on both
# channels inside the bent regions and keeps the stereo original outside them.
out, n, moved = bend(snd.convert_to_mono() if snd.n_channels > 1 else snd)
out.save(dst, "WAV")
print(json.dumps({"channelsIn": snd.n_channels, "pitchPoints": n, "moved": moved}))
