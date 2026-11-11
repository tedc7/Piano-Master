"""A listening page for the probe: every version of each song's vocal, with a button for each
melisma that plays from just before it, so versions can be compared at the same spot.

    tools/.venv/bin/python feasibility/melisma-probe/build_page.py

Reads out/bend/<piece>/ (bend.py), out/work-*/<piece>/final/ (render.py) and, when they are there,
the first trial's files (out/first-trial/<piece>/). Writes out/listen/ (index.html, manifest.json,
MP3s). Open out/listen/index.html in a browser on this machine, or put it on the piano server with
deploy.sh.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

import soundfile as sf

import melisma as ml

OUT = ml.HERE / "out"
SITE = OUT / "listen"
SONGS = [("the-first-noel", "christmas/the-first-noel"), ("joy-to-the-world", "christmas/joy-to-the-world"),
         ("what-child-is-this", "christmas-2/what-child-is-this")]


def mp3(src: Path, name: str) -> str:
    y, sr = sf.read(src, always_2d=True)
    sf.write(SITE / name, y, sr, format="MP3", bitrate_mode="CONSTANT", compression_level=0.5)
    return name


def versions(pid: str) -> list[dict]:
    """(label, note, file) for each version made so far."""
    out = []
    b = OUT / "bend" / pid
    rep = json.loads((b / "report.json").read_text()) if (b / "report.json").exists() else None

    def add(key: str, label: str, note: str, src: Path):
        if src.exists():
            out.append({"key": key, "label": label, "note": note, "file": mp3(src, f"{pid}-{key}.mp3")})

    def share(x):
        return f"{x[0]} of {x[1]}"
    if rep:
        add("approved", "A. As approved (melismas held on one pitch)",
            f"melisma notes on pitch: {share(rep['before']['melismaNotes'])}; whole melody: {share(rep['before']['melody'])}", b / "vocal_in.wav")
        add("first", "B. First trial (Nov 10): the bend you heard, with the tics", "Rubber Band, straight slides, a 10 ms jump back at the end",
            OUT / "first-trial" / pid / "vocal_bent2.wav")
        e = rep["engines"].get("psola")
        if e:
            add("psola", "C. Bend, smoothed: only the melismas changed",
                f"melisma notes on pitch: {share(e['melismaNotes'])}; whole melody: {share(e['melody'])}; "
                f"{e['joins']['clean']} joins where the two are the same, {e['joins']['crossfaded']} crossfaded", b / "vocal_psola.wav")
            add("psola-whole", "D. Bend, smoothed: the whole vocal through the same process (no joins)",
                "the same bends as C; listen for whether the rest of the song sounds different", b / "raw_psola.wav")
        e = rep["engines"].get("rubberband")
        if e:
            add("rubberband", "E. Bend with Rubber Band, same smooth slides",
                f"melisma notes on pitch: {share(e['melismaNotes'])}", b / "vocal_rubberband.wav")
    for w in sorted(OUT.glob("work-*")):
        f = w / pid / "final"
        if not (f / "report.json").exists():
            continue
        r = json.loads((f / "report.json").read_text())
        c = r["checks"]
        got = r.get("bent") or r["asRendered"]
        add(f"hybrid-{w.name[5:]}", f"F. New YuE2 take: melismas with a note under {r['shortS']:g} s sung on split vowels, the rest bent",
            f"{r['melismas']['split']} split, {r['melismas']['bend']} bent; split notes on pitch: {share(got['splitNotes'])}; "
            f"whole melody: {share(got['melody'])}; words off the staff {c['wordsOff']:.0%}"
            + (f", heard {c['wordsHeard']:.0%}" if c.get("wordsHeard") is not None else "")
            + ("" if r["pass"] else f"; FAILS the media checks: {'; '.join(c['reasons'])}"), f / "vocal_hybrid.wav")
    return out


def spots(pid: str, path: str) -> list[dict]:
    piece = ml.common.load(ml.ROOT / "content" / "incoming" / f"{path}.yaml")
    media = json.loads((ml.approved_dir(piece) / "media.json").read_text())
    at = ml.stem_time(piece, float(media["padBeats"]))
    return [{"t": round(max(0.0, at(m["notes"][0]["start"]) - 1.5), 2), "word": m["notes"][0]["lyric"]["text"].strip(",.;:!?"),
             "len": round(min(m["seconds"]), 2), "kind": m["kind"]} for m in ml.melismas(piece)]


def main() -> None:
    SITE.mkdir(parents=True, exist_ok=True)
    songs = []
    for pid, path in SONGS:
        v = versions(pid)
        if v:
            songs.append({"id": pid, "title": pid.replace("-", " ").title(), "versions": v, "spots": spots(pid, path)})
    (SITE / "manifest.json").write_text(json.dumps({"songs": songs}, indent=1) + "\n")
    rows = []
    for s in songs:
        rows.append(f"<h2>{html.escape(s['title'])}</h2>")
        rows.append("<p class='spots'>Jump to a melisma (every player on this song moves there; times are the same in each version, "
                    "though a new take sings them a little differently):<br>" + " ".join(
                        f"<button data-song='{s['id']}' data-t='{x['t']}' class='{x['kind']}' title='shortest note {x['len']} s'>"
                        f"{html.escape(x['word'])} {int(x['t'] // 60)}:{int(x['t'] % 60):02d}</button>" for x in s["spots"]) + "</p>")
        for v in s["versions"]:
            rows.append(f"<div class='v'><b>{html.escape(v['label'])}</b><br><span>{html.escape(v['note'])}</span><br>"
                        f"<audio controls preload='none' data-song='{s['id']}' src='{v['file']}'></audio></div>")
    page = f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Melisma probe</title>
<style>
body {{ font: 17px/1.45 system-ui, sans-serif; max-width: 900px; margin: 24px auto; padding: 0 16px; color: #222; background: #fbfaf7; }}
h2 {{ margin-top: 36px; }} .v {{ margin: 14px 0; padding: 10px 12px; background: #fff; border: 1px solid #e2dfd7; border-radius: 10px; }}
.v span {{ color: #666; font-size: 15px; }} audio {{ width: 100%; margin-top: 6px; }}
button {{ font: inherit; font-size: 14px; margin: 2px; padding: 4px 8px; border-radius: 8px; border: 1px solid #c9c5b8; background: #fff; }}
button.split {{ background: #fff4d6; }} .key span {{ padding: 2px 8px; border-radius: 6px; border: 1px solid #c9c5b8; }}
</style>
<h1>Melisma probe: listen</h1>
<p>One sung syllable over several notes. Each song's vocal alone, in several versions. Press a word to move every player of
that song to just before that melisma, then play the versions one after another.</p>
<p class="key">Buttons: <span>white</span> every note of the melisma is 0.3 s or longer &nbsp; <span style="background:#fff4d6">yellow</span> it has a shorter note</p>
{''.join(rows)}
<script>
document.querySelectorAll('button[data-t]').forEach(b => b.onclick = () => {{
  document.querySelectorAll(`audio[data-song="${{b.dataset.song}}"]`).forEach(a => {{ a.pause(); a.preload = 'auto'; a.currentTime = +b.dataset.t; }});
}});
document.querySelectorAll('audio').forEach(a => a.onplay = () => document.querySelectorAll('audio').forEach(o => {{ if (o !== a) o.pause(); }}));
</script>
"""
    (SITE / "index.html").write_text(page)
    print(f"wrote {SITE / 'index.html'}: {sum(len(s['versions']) for s in songs)} versions of {len(songs)} songs")


if __name__ == "__main__":
    main()
