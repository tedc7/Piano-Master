"""Build the probe's site: a listening page, and a test copy of the app with the rendered backings.

    .venv/bin/python build_site.py      # after render.py and (cd client && npm run build) -> dist/

dist/index.html     each piece with both SoundFonts: backing with the piano part, backing alone at
                    100% and 50%, the parts, attack timing and sizes
dist/app/           the built client (client/dist) plus the three pieces, one version per
                    SoundFont, with their backing as accompaniment-only stems at all four presets,
                    and Amazing Grace's YuE2 vocal with three backings (hymn.py): YuE2's own, a
                    church organ and strings, both MuseScore General from the hymn's alto, tenor and bass
"""
from __future__ import annotations

import html
import json
import shutil
import sys
from pathlib import Path

import yaml

import backing as bk
import render as rd

HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"
CLIENT = bk.ROOT / "client" / "dist"
SF_NAMES = {"musescore": "MuseScore General", "generaluser": "GeneralUser GS"}
SF_LICENSE = {"musescore": "MIT (FluidR3 lineage; S. Christian Collins)", "generaluser": "GeneralUser GS License v2.0 (S. Christian Collins)"}


def pieces(report: dict) -> list[dict]:
    """Each test piece as the client reads it, one version per SoundFont."""
    import build_content as bc
    from app import analysis
    skills, errors, _ = bc.validate_skill_maps(bc.load_skill_maps(), {p.stem for p in (bc.CONTENT / "pieces").glob("*.yaml")})
    parsed = {s["id"]: analysis.Constraints(s) for s in skills}
    version = json.loads((CLIENT / "content" / "index.json").read_text())["contentVersion"]
    out = []
    for pid in bk.PIECES:
        meta = yaml.safe_load((bk.ROOT / "content" / "incoming" / "classical" / f"{pid}.yaml").read_text())
        for sfname in rd.SOUNDFONTS:
            vid = f"{pid}--{sfname}"
            piece, entry, _ = bc.make_piece(vid, {**meta, "song": pid, "songTitle": meta["title"], "version": SF_NAMES[sfname]},
                                            skills, parsed, version)
            r = report[pid]["soundfonts"][sfname]
            piece["media"] = entry_media = {
                "engine": "fluidsynth", "take": sfname, "padBeats": rd.PAD_BEATS, "bpm": piece["notation"]["header"]["tempo"],
                "presets": {k: {"ratio": v["ratio"], "accompaniment": {"url": f"media/{vid}/accompaniment_{k}.mp3", "bytes": v["bytes"]}}
                            for k, v in r["presets"].items()},
                "check": None,
            }
            entry["hasMedia"] = True
            out.append({"id": vid, "pid": pid, "sf": sfname, "piece": piece, "entry": entry, "media": entry_media})
    return out


HYMN_VERSIONS = {"yue2": "YuE2 backing", "organ": "Organ (FluidSynth)", "strings": "Strings (FluidSynth)"}


def hymn_pieces(hymn: dict) -> list[dict]:
    """Amazing Grace, one version per backing, all with the same YuE2 vocal stems."""
    orig = json.loads((bk.ROOT / "client" / "public" / "content" / "pieces" / "amazing-grace-melody.json").read_text())
    out = []
    for key, label in HYMN_VERSIONS.items():
        vid = f"amazing-grace--{key}"
        media = json.loads(json.dumps(orig["media"]))
        if key != "yue2":
            media["engine"] = "YuE2 vocal + FluidSynth backing"
            for pk, v in media["presets"].items():
                v["accompaniment"] = {"url": f"media/{vid}/accompaniment_{pk}.mp3", "bytes": hymn["styles"][key]["presets"][pk]["bytes"]}
        piece = {**orig, "id": vid, "song": "amazing-grace-test", "songTitle": "Amazing Grace (backing test)", "version": label,
                 "media": media}
        entry = {k: piece.get(k) for k in ("id", "title", "composer", "kind", "genre", "level", "hands", "skillId", "keyboardSize",
                                           "song", "songTitle", "version")}
        entry |= {"tempo": orig["notation"]["header"]["tempo"], "timeSig": orig["notation"]["header"]["timeSig"],
                  "measures": len(orig["notation"]["playbackOrder"]), "beats": float(orig["notation"]["length"]),
                  "phrases": len(orig["notation"]["phrases"]), "hasMedia": True,
                  **{k: orig.get(k) for k in ("barNotes", "requiredSkills", "featuredSkills", "mapPoint", "skillMeasures", "beyondMap")}}
        out.append({"id": vid, "key": key, "piece": piece, "entry": entry})
    return out


def hymn_section(hymn: dict) -> str:
    e = html.escape
    sy = hymn["syllableTiming"]
    cells = []
    for key, label in HYMN_VERSIONS.items():
        base = "media/amazing-grace"
        parts = "" if key == "yue2" else "<br><span class=m>" + e(", ".join(hymn["styles"][key]["parts"])) + "</span>"
        cells.append(f"""<div class=sf><h3>{e(label)}</h3>{parts}
<p>Vocal with this backing, 100%<br><audio controls preload=none src="{base}/mix_{key}_100.mp3"></audio></p>
<p>50%<br><audio controls preload=none src="{base}/mix_{key}_50.mp3"></audio></p>
<p><a href="app/#/play/amazing-grace--{key}">Open in the test app</a></p></div>""")
    v, a = sy["vocals_100.mp3"], sy["accompaniment_100.mp3"]
    return f"""<section><h2>Amazing Grace: the YuE2 vocal over a FluidSynth backing</h2>
<p>The same aligned YuE2 vocal with three backings. The FluidSynth ones play the hymn's own alto, tenor and bass
(the Open Hymnal's four-part harmony) on MuseScore General. Mixes are at the app's balance (backing at 200%).</p>
<div class=cmp>{''.join(cells)}</div>
<p class=m>Tuning from A440: vocal {hymn['tuningCents']['vocals_100.mp3']:+} cents, YuE2 backing {hymn['tuningCents']['accompaniment_100.mp3']:+}
cents (FluidSynth is exactly A440; about 10 cents would be noticeable). Syllable onsets against the beat: vocal median
{v['medianMs']} ms, {round(v['within100ms'] * 100)}% within 100 ms; the YuE2 backing, measured the same way, {a['medianMs']} ms and
{round(a['within100ms'] * 100)}%. The vocal sits as close to the beat as its own backing did, and FluidSynth is on the beat.</p></section>"""


def page(report: dict, hymn: dict | None = None) -> str:
    e = html.escape
    rows = []
    for pid, rep in report.items():
        parts = "".join(f"<li>{e(p['name'])} <span class=m>(GM program {p['program'] + 1}, {p['notes']} notes)</span></li>" for p in rep["parts"])
        cells = []
        for sfname, r in rep["soundfonts"].items():
            base = f"media/{pid}/{sfname}"
            lags = "".join(f"<tr><td>{e(k)}</td><td>{v['median']}</td><td>{r['leadMs'].get(k, 0)}</td><td>{r['lagsAfter'][k]['median']}</td></tr>"
                           for k, v in r["lags"].items())
            size = sum(v["bytes"] for v in r["presets"].values()) / 1e6
            cells.append(f"""<div class=sf><h3>{e(SF_NAMES[sfname])}</h3>
<p>With the piano part (100%)<br><audio controls preload=none src="{base}/with_piano_100.mp3"></audio></p>
<p>Backing alone, 100%<br><audio controls preload=none src="{base}/accompaniment_100.mp3"></audio></p>
<p>Backing alone, 50% (rendered at that tempo, not stretched)<br><audio controls preload=none src="{base}/accompaniment_50.mp3"></audio></p>
<p><a href="app/#/play/{pid}--{sfname}">Open in the test app</a> (Listen mode plays the app's piano with this backing)</p>
<details><summary>Timing and size</summary><table><tr><th>Part</th><th>Attack lag ms</th><th>Starts early ms</th><th>Lag after</th></tr>{lags}</table>
<p class=m>Four presets: {size:.1f} MB of MP3. Render time: {', '.join(f"{k}% {v['renderSec']} s" for k, v in r['presets'].items())}.</p></details></div>""")
        rows.append(f"<section><h2>{e(rep['title'])}</h2><ul>{parts}</ul><div class=cmp>{''.join(cells)}</div></section>")
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width, initial-scale=1">
<title>FluidSynth backing probe</title><style>
body {{ font: 17px/1.45 -apple-system, "Segoe UI", Roboto, sans-serif; margin: 20px; color: #1f1f24; background: #f7f5f0; }}
section {{ background: #fff; border: 1px solid #e2dfd7; border-radius: 14px; padding: 14px 18px; margin-bottom: 16px; }}
.cmp {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }}
.sf {{ background: #f4f2ec; border-radius: 10px; padding: 10px 14px; }} audio {{ width: 100%; }}
.m {{ color: #6c6a72; font-size: 14px; }} table {{ border-collapse: collapse; font-size: 14px; }} td, th {{ padding: 2px 8px; text-align: left; }}
</style></head><body>
<h1>FluidSynth backing probe</h1>
<p>Backing tracks rendered from each piece's own notation with FluidSynth and two free SoundFonts, for the
architecture's open question (§10.5): can wordless pieces get an ensemble backing this way? Listen for: does it
sound like real instruments, does it stay behind the piano, and is it on the beat?</p>
<p class=m>Test app: tap <b>Parent</b>, open a song, and use <b>Listen</b> at each speed (the backing is rendered at
each speed, so nothing is stretched). With the keyboard, Play works too. It shares this iPad's settings with the
real app; the parent's plays are never a child's.</p>
{hymn_section(hymn) if hymn else ""}
{''.join(rows)}
<p class=m>SoundFonts: MuseScore General ({e(SF_LICENSE['musescore'])}); GeneralUser GS ({e(SF_LICENSE['generaluser'])}).
The app's own piano: Salamander Grand Piano (CC BY 3.0).</p>
</body></html>"""


def main() -> int:
    report = json.loads((rd.BUILD / "report.json").read_text())
    if not (CLIENT / "index.html").exists():
        print("build the client first: (cd client && npm run build)", file=sys.stderr)
        return 1
    if DIST.exists():
        shutil.rmtree(DIST)
    # the listening page and its audio
    for pid, rep in report.items():
        for sfname in rep["soundfonts"]:
            src, dst = rd.BUILD / pid / sfname, DIST / "media" / pid / sfname
            dst.mkdir(parents=True)
            for f in src.glob("*.mp3"):
                shutil.copy2(f, dst / f.name)
    hymn = json.loads((rd.BUILD / "hymn.json").read_text()) if (rd.BUILD / "hymn.json").exists() else None
    if hymn:
        dst = DIST / "media" / "amazing-grace"
        dst.mkdir(parents=True)
        for f in (rd.BUILD / "amazing-grace").glob("mix_*.mp3"):
            shutil.copy2(f, dst / f.name)
    (DIST / "index.html").write_text(page(report, hymn))
    # the test app: the client, plus the three pieces in each SoundFont
    shutil.copytree(CLIENT, DIST / "app")
    index = json.loads((DIST / "app" / "content" / "index.json").read_text())
    for p in pieces(report):
        (DIST / "app" / "content" / "pieces" / f"{p['id']}.json").write_text(json.dumps(p["piece"]))
        index["pieces"].append(p["entry"])
        m = DIST / "app" / "media" / p["id"]
        m.mkdir(parents=True)
        for f in (rd.BUILD / p["pid"] / p["sf"]).glob("accompaniment_*.mp3"):
            shutil.copy2(f, m / f.name)
    for p in hymn_pieces(hymn) if hymn else []:
        (DIST / "app" / "content" / "pieces" / f"{p['id']}.json").write_text(json.dumps(p["piece"]))
        index["pieces"].append(p["entry"])
        if p["key"] != "yue2":
            m = DIST / "app" / "media" / p["id"]
            m.mkdir(parents=True)
            for f in (rd.BUILD / "amazing-grace" / p["key"]).glob("accompaniment_*.mp3"):
                shutil.copy2(f, m / f.name)
    (DIST / "app" / "content" / "index.json").write_text(json.dumps(index))
    total = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file()) / 1e6
    print(f"wrote {DIST}: {len(report)} pieces x {len(rd.SOUNDFONTS)} SoundFonts, {total:.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
