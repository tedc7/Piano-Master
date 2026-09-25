#!/usr/bin/env python3
"""Make the test media for the client probe page.

Usage: make-media.py <ffmpeg> <out_dir>

Writes into out_dir (deployed to /opt/piano/www/media/, not committed):
  stem-3min.m4a  3-minute stereo AAC, the size of a real stem at 100% tempo
  stem-6min.m4a  6-minute stereo AAC, a stem at the 50% tempo preset
  stem-3min.wav  the 3-minute stem uncompressed (about 32 MB), for the download-speed test
  test-10s.mp4   10-second 720p H.264 + AAC video, like a concept video
  silent.mp4     tiny muted loop, for the keep-awake fallback

The stems are a click every second over a tone whose pitch changes every
10 seconds, so a jump to a new position is audible.
"""
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

RATE = 44100


def stem(seconds: int) -> np.ndarray:
    t = np.arange(seconds * RATE) / RATE
    # C major scale, one step per 10-second block, looping.
    scale = [261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88, 523.25]
    freq = np.array(scale)[(t // 10).astype(int) % len(scale)]
    tone = 0.18 * np.sin(2 * np.pi * freq * t)
    # Short click at the start of every second.
    phase = t % 1.0
    click = 0.5 * np.sin(2 * np.pi * 1500 * t) * np.exp(-phase * 60) * (phase < 0.05)
    left = tone + click
    right = 0.8 * tone + click
    return np.stack([left, right], axis=1)


def write_wav(path: Path, data: np.ndarray) -> None:
    pcm = (np.clip(data, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def run(ffmpeg: str, *args: str) -> None:
    subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def main() -> None:
    ffmpeg, out = sys.argv[1], Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)

    for minutes in (3, 6):
        wav = out / f"stem-{minutes}min.wav"
        write_wav(wav, stem(minutes * 60))
        run(ffmpeg, "-i", str(wav), "-c:a", "aac", "-b:a", "128k", str(out / f"stem-{minutes}min.m4a"))
    (out / "stem-6min.wav").unlink()

    run(ffmpeg,
        "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=10",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
        "-c:v", "libx264", "-profile:v", "main", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", "-shortest",
        str(out / "test-10s.mp4"))

    run(ffmpeg,
        "-f", "lavfi", "-i", "color=c=black:size=64x64:rate=10:duration=2",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "32k",
        "-movflags", "+faststart", "-shortest",
        str(out / "silent.mp4"))


if __name__ == "__main__":
    main()
