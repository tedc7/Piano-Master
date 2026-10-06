"""What the lessons say aloud, and how the voice should say it (arch §10.5, v0.34). Plain Python, no
speech engine: lesson_voice.py records the lines, build_content.py hands the recordings to the app.

Every line the lesson screen reads: each card's `text`, each Check question's `text` and a Hear
card's contrast `text`, from content/lessons/*.yaml, and the screen's own praise lines from
client/src/lib/lessonPhrases.ts. A line can carry `say:` beside its `text` when the voice should
read something other than what is shown; the lexicon (tools/voice/lexicon.yaml) fixes words the
voice gets wrong everywhere ("bass"), note letters are marked so "A" is the letter, not "a", and a
"..." is read the way the voice says it cleanly (see `blanks`).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LESSONS = ROOT / "content" / "lessons"
VOICE_DIR = LESSONS / "voice"
MANIFEST = VOICE_DIR / "voice.json"
PHRASES = ROOT / "client" / "src" / "lib" / "lessonPhrases.ts"
LEXICON = Path(__file__).with_name("lexicon.yaml")

# The voice every lesson uses (chosen by ear on Oct 6, 2026: feasibility/voice-probe). Changing any of
# it records every line again.
VOICE = {"engine": "kokoro 0.9.4", "model": "hexgrad/Kokoro-82M", "revision": "f3ff3571791e39611d31c381e3a41a3af07b4987",
         "voice": "af_heart", "speed": 0.8}

# "A" is a note letter, not the word "a", when no noun follows it: before another letter, a verb or a
# preposition, or punctuation ("A is two steps below", "A B C", "plays A in", "C, B, A").
_NOT_A_NOUN = r"(?:[A-G]\b|is|in|and|or|with|just|on|to|sits|lives|comes|goes|gets|has|was|then|at|for|by|below|above)\b"
_NOTE_A = re.compile(r"\bA\b(?=\s+" + _NOT_A_NOUN + r"|\s*[,.;:!?)]|\s*$)")


_DOTS = r"(?:\.\.\.|…)"


def blanks(text: str) -> str:
    """A "..." as the voice should read it. At the end of a line (a fill-in question, "A quarter note
    is...") it ends in a plain stop: with the dots the voice adds a sound before or after the words
    (heard as "The piano, soft", "C and E ara"). At the start ("...and mezzo forte") it is dropped. In
    the middle ("Bass C is a ... below Bass D") it is read as "blank", which the voice would skip."""
    t = re.sub(rf"^\s*{_DOTS}\s*", "", text)
    t = re.sub(rf"\s{_DOTS}\s", " blank ", t)
    return re.sub(rf"\s*{_DOTS}\s*$", ".", t)


def lexicon() -> dict[str, str]:
    """Word -> how to say it, in Kokoro's phonemes (misaki's alphabet)."""
    return yaml.safe_load(LEXICON.read_text())["words"]


def spoken(text: str, lex: dict[str, str] | None = None) -> str:
    """The text with Kokoro's pronunciation marks: `[word](/phonemes/)`."""
    lex = lexicon() if lex is None else lex
    out = _NOTE_A.sub("[A](/ˈA/)", blanks(text))
    for word, ph in lex.items():
        out = re.sub(rf"(?<![\[\w]){re.escape(word)}\b(?!\]\()", f"[{word}](/{ph}/)", out)
    return out


def line_key(say: str) -> str:
    """The recording's name: the spoken text and the voice, so a change to either records it again."""
    h = hashlib.sha256(json.dumps(VOICE, sort_keys=True).encode() + b"\0" + say.encode())
    return h.hexdigest()[:16]


def phrases() -> list[str]:
    """The lesson screen's own lines (lessonPhrases.ts: one `key: "text",` per line)."""
    return re.findall(r'^\s*\w+:\s*"((?:[^"\\]|\\.)*)",?\s*$', PHRASES.read_text(), re.M)


def lines() -> dict[str, dict]:
    """Every line read aloud -> {say, where}. `say` is what the voice reads, with the lexicon applied."""
    lex = lexicon()
    out: dict[str, dict] = {}

    def add(item: dict | None, where: str) -> None:
        if not item or not item.get("text"):
            return
        text = str(item["text"])
        say = spoken(str(item.get("say") or text), lex)
        prev = out.get(text)
        if prev and prev["say"] != say:
            raise ValueError(f"{where}: {text!r} is said two ways ({prev['where']} has another `say:`)")
        out.setdefault(text, {"say": say, "where": where})

    for path in sorted(LESSONS.glob("*.yaml")):
        for i, c in enumerate(yaml.safe_load(path.read_text()).get("cards") or []):
            where = f"{path.name} card {i + 1}"
            add(c, where)
            for q in c.get("questions") or []:
                add(q, where)
            add(c.get("contrast"), where)
    for p in phrases():
        add({"text": p}, PHRASES.name)
    return out


def manifest() -> dict:
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"voice": VOICE, "lines": {}}


def recorded(text: str, line: dict, man: dict) -> str | None:
    """The recording's file name if it is up to date for this line (same words, same voice)."""
    m = man["lines"].get(text)
    name = f"{line_key(line['say'])}.mp3"
    return name if m and m["file"] == name and (VOICE_DIR / name).exists() else None
