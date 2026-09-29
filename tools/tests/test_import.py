"""The song import skill's tools (arch §10.4): convert, check, compare, promote."""
import shutil
from pathlib import Path

import pytest
import yaml

import import_song as imp

ROOT = Path(__file__).resolve().parents[2]

GOOD = {
    "title": "Test Tune", "composer": "Trad.", "kind": "library", "genre": "folk", "level": "Prep A", "hands": "R",
    "source": {"site": "test", "url": "https://example.org/tune"}, "license": {"composition": "public-domain", "edition": "public-domain"},
    "abc": "X:1\nM:4/4\nL:1/4\nQ:1/4=90\nK:C\nC D E C | E F G2 | G F E D | E C D2 |\nC E D F | E G F D | E D C D | C4 |]\n",
}


def write(folder: Path, pid: str, **over) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / f"{pid}.yaml"
    f.write_text(yaml.safe_dump({**GOOD, **over}, sort_keys=False))
    return f


@pytest.fixture()
def content(tmp_path, monkeypatch):
    """A copy of the library to promote into; the skill map is the real one."""
    c = tmp_path / "content"
    shutil.copytree(ROOT / "content" / "pieces", c / "pieces")
    monkeypatch.setattr(imp, "CONTENT", c)
    monkeypatch.setattr(imp, "DELETED", c / "deleted.yaml")
    return c


def by_id(results):
    return {r["id"]: r for r in results}


def test_a_good_piece_checks_clean_and_is_analysed(content):
    r = by_id(imp.check_files([write(content / "incoming" / "b", "tune")]))["tune"]
    assert r["errors"] == [] and r["summary"]["keyboardSize"] == 61 and r["summary"]["bars"] == 8
    assert r["summary"]["featured"] == ["placeholder.rh-c-position"]


def test_the_checks_catch_fields_licenses_bars_duplicates_and_deleted_songs(content):
    b = content / "incoming" / "b"
    files = [
        write(b, "nolicense", license={"composition": "public-domain", "edition": "CC BY-NC-SA"}),
        write(b, "shortbar", abc=GOOD["abc"].replace("E F G2 |", "E F G |")),
        write(b, "twinkle-copy", abc="X:1\nM:4/4\nL:1/4\nK:C\nC C G G | A A G2 | F F E E | D D C2 |]\n"),
        write(b, "todo", level="TODO"),
    ]
    (content / "deleted.yaml").write_text(yaml.safe_dump([{"title": "Test Tune", "composer": "Trad.", "reason": "too long"}]))
    rs = by_id(imp.check_files(files))
    assert any("not an accepted license" in e for e in rs["nolicense"]["errors"])
    assert any("bar 2 lasts 3 beats" in e for e in rs["shortbar"]["errors"])
    assert any("same song as twinkle-twinkle" in e for e in rs["twinkle-copy"]["errors"])
    assert "`level` is missing" in rs["todo"]["errors"]
    assert all(any("deleted list" in e for e in r["errors"]) for k, r in rs.items() if k != "twinkle-copy")


def test_promote_moves_only_clean_approved_pieces(content):
    b = content / "incoming" / "b"
    write(b, "tune")
    write(b, "broken", level="TODO")
    assert imp.main(["promote", str(b), "broken"]) == 1 and not (content / "pieces" / "broken.yaml").exists()
    assert imp.main(["promote", str(b), "tune"]) == 0
    assert (content / "pieces" / "tune.yaml").exists() and not (b / "tune.yaml").exists()


def test_convert_and_compare_a_musicxml_score(content, tmp_path, monkeypatch, capsys):
    from music21 import corpus
    monkeypatch.setattr(imp, "INCOMING", content / "incoming")
    src = Path(corpus.getWork("mozart/k545/movement1_exposition"))
    assert imp.main(["convert", str(src), "--id", "k545", "--batch", "t", "--title", "K. 545"]) == 0
    draft = content / "incoming" / "t" / "k545.yaml"
    assert yaml.safe_load(draft.read_text())["hands"] == "RL"
    capsys.readouterr()
    assert imp.main(["compare", str(draft), str(src), "--line", "all"]) == 0
    assert "191 of the piece's 191 notes line up" in capsys.readouterr().out
