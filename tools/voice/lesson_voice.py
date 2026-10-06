"""Record the lessons' spoken lines with the lesson voice, and check each recording (arch §10.5, v0.34).

    tools/.voice/bin/python tools/voice/lesson_voice.py plan     # lines with no recording, or one of other words
    tools/.voice/bin/python tools/voice/lesson_voice.py make     # record them, check them, drop unused files
    tools/.voice/bin/python tools/voice/lesson_voice.py check    # check every recording again
    tools/.voice/bin/python tools/voice/lesson_voice.py fetch    # download the pinned models (setup.sh)

The voice is Kokoro-82M's Heart at 80% speed (spoken.VOICE). Recordings are MP3s named by a hash of
the spoken words and the voice, in content/lessons/voice/ (Git LFS), with voice.json: for each line
shown, its file, the words spoken, its length, and the check. The check transcribes the recording with
Whisper (small.en) and compares the letters heard with the letters written (numbers as words, the
lexicon's respellings applied); more than 10% different is flagged for a listen. build_content.py
copies the recordings into the app; a line without one is read by the device's own voice.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent))
import spoken  # noqa: E402

SR = 24000
FLAG = 0.10                 # letters heard that differ from those written
TARGET_DB = -20.0           # loudness of the voiced parts, so every line plays at one level
WHISPER = "small.en"
# Whisper's spelling of a word the lexicon respells for the voice
HEARD_AS = {"bass": "base"}


def model_files() -> str:
    """The pinned Kokoro model and the one voice, from the Hugging Face cache (downloaded once)."""
    from huggingface_hub import snapshot_download
    return snapshot_download(spoken.VOICE["model"], revision=spoken.VOICE["revision"],
                             allow_patterns=["config.json", "kokoro-v1_0.pth", f"voices/{spoken.VOICE['voice']}.pt"])


def fetch() -> None:
    model_files()
    from faster_whisper import WhisperModel
    WhisperModel(WHISPER, device="cpu", compute_type="int8")


def letters(text: str) -> str:
    """For comparing what was said with what was written: lower case, numbers and fractions as words,
    no spaces or punctuation ("E, D, C" and Whisper's "EDC" are the same; "4/4" is "four four")."""
    from num2words import num2words
    t = re.sub(r"\[([^\]]+)\]\(/[^/]+/\)", r"\1", text).lower()
    t = re.sub(r"[/\-]", " ", t)
    t = re.sub(r"\d+", lambda m: " " + num2words(int(m.group())) + " ", t)
    t = " ".join(HEARD_AS.get(w, w) for w in re.findall(r"[a-z']+", t))
    return re.sub(r"[^a-z]", "", t)


def distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


class Voice:
    def __init__(self) -> None:
        from kokoro import KModel, KPipeline
        repo = model_files()
        model = KModel(repo_id=spoken.VOICE["model"], config=f"{repo}/config.json", model=f"{repo}/kokoro-v1_0.pth").eval()
        self.pipe = KPipeline(lang_code="a", repo_id=spoken.VOICE["model"], model=model)
        self.voice = f"{repo}/voices/{spoken.VOICE['voice']}.pt"

    def say(self, text: str) -> np.ndarray:
        chunks = [r.audio.cpu().numpy() for r in self.pipe(text, voice=self.voice, speed=spoken.VOICE["speed"])
                  if r.audio is not None]
        a = np.concatenate(chunks)
        frames = a[: len(a) // 480 * 480].reshape(-1, 480)
        rms = np.sqrt((frames ** 2).mean(axis=1))
        voiced = rms[rms > 10 ** (-45 / 20)]
        gain = 10 ** (TARGET_DB / 20) / max(1e-6, float(np.sqrt((voiced ** 2).mean())) if len(voiced) else 1.0)
        a = a * gain
        return a / max(1.0, float(np.abs(a).max()) / 0.95)


class Checker:
    def __init__(self) -> None:
        from faster_whisper import WhisperModel
        self.model = WhisperModel(WHISPER, device="cpu", compute_type="int8")

    def check(self, path: Path, say: str) -> dict:
        """Transcribe the recording as saved. It is resampled to Whisper's 16 kHz in the frequency
        domain: a plain interpolation aliases, and Whisper then hears words that aren't there."""
        audio, sr = sf.read(path, dtype="float32")
        n = round(len(audio) * 16000 / sr)
        x = np.fft.irfft(np.fft.rfft(audio)[: n // 2 + 1], n) * (n / len(audio))
        segs, _ = self.model.transcribe(x.astype(np.float32), language="en", beam_size=5)
        heard = " ".join(s.text.strip() for s in segs)
        want, got = letters(say), letters(heard)
        off = distance(want, got) / max(1, len(want))
        return {"heard": heard, "off": round(off, 3), "flag": off > FLAG}


def plan(lines: dict, man: dict) -> list[str]:
    return [t for t, ln in lines.items() if not spoken.recorded(t, ln, man)]


def save(man: dict, lines: dict) -> None:
    man["voice"] = spoken.VOICE
    man["lines"] = {t: man["lines"][t] for t in lines if t in man["lines"]}
    spoken.MANIFEST.write_text(json.dumps(man, indent=1, ensure_ascii=False, sort_keys=True) + "\n")


def make(lines: dict, man: dict) -> int:
    todo = plan(lines, man)
    spoken.VOICE_DIR.mkdir(parents=True, exist_ok=True)
    if todo:
        voice, checker = Voice(), Checker()
        t0 = time.time()
        for i, text in enumerate(todo, 1):
            say = lines[text]["say"]
            audio = voice.say(say)
            name = f"{spoken.line_key(say)}.mp3"
            sf.write(spoken.VOICE_DIR / name, audio, SR, format="MP3")
            man["lines"][text] = {"file": name, "say": say, "seconds": round(len(audio) / SR, 2),
                                  "where": lines[text]["where"], "check": checker.check(spoken.VOICE_DIR / name, say)}
            mark = "  FLAG" if man["lines"][text]["check"]["flag"] else ""
            print(f"[{i}/{len(todo)}] {text[:70]}{mark}", flush=True)
            if i % 20 == 0:
                save(man, lines)
        print(f"recorded {len(todo)} lines in {time.time() - t0:.0f} s")
    save(man, lines)
    used = {m["file"] for m in man["lines"].values()}
    for f in spoken.VOICE_DIR.glob("*.mp3"):
        if f.name not in used:
            f.unlink()
            print(f"removed unused {f.name}")
    return report(man)


def check(lines: dict, man: dict) -> int:
    checker = Checker()
    for text in lines:
        m = man["lines"].get(text)
        if not m or not spoken.recorded(text, lines[text], man):
            continue
        m["check"] = checker.check(spoken.VOICE_DIR / m["file"], m["say"])
    save(man, lines)
    return report(man)


def report(man: dict) -> int:
    lines = spoken.lines()
    missing = plan(lines, man)
    flagged = [(t, m) for t, m in man["lines"].items() if m["check"]["flag"]]
    total = sum(m["seconds"] for m in man["lines"].values())
    size = sum((spoken.VOICE_DIR / m["file"]).stat().st_size for m in man["lines"].values() if (spoken.VOICE_DIR / m["file"]).exists())
    print(f"{len(lines) - len(missing)} of {len(lines)} lines recorded ({total / 60:.1f} min, {size / 1e6:.1f} MB); "
          f"{len(flagged)} flagged, {len(missing)} to record")
    for t, m in flagged:
        print(f"  FLAG {m['check']['off']:.0%} off ({m['where']}): {t}\n       heard: {m['check']['heard']}")
    for t in missing:
        print(f"  to record ({lines[t]['where']}): {t}")
    return 1 if missing else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["plan", "make", "check", "fetch"])
    args = ap.parse_args()
    if args.command == "fetch":
        fetch()
        return 0
    lines, man = spoken.lines(), spoken.manifest()
    if args.command == "plan":
        return report(man)
    return make(lines, man) if args.command == "make" else check(lines, man)


if __name__ == "__main__":
    sys.exit(main())
