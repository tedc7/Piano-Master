# Sources and licenses (arch §10.2)

## What may be added

A piece needs **both** of these:

1. **The composition** is public domain in the US: first published in 1930 or earlier (as of 2026;
   the year moves forward each January 1). Folk songs, nursery rhymes, hymns, and Bach to Debussy
   all qualify. A modern song qualifies only when **the parent supplied the file** for private
   family use (`license.composition: parent-supplied`). It is never shared.
2. **The edition** (the engraving or file) is openly licensed: public domain, CC0, CC BY or CC BY-SA
   (any version). Non-commercial (NC), no-derivatives (ND) and unlicensed editions can't be used as
   the source. Retype the notes from the public-domain composition and use that edition only to
   check them. Write `edition: "retyped from <site> (<license>), checked only"`.

Say how you know, in `license.evidence`: the page that states the license or the publication date.

## Candidate sources

| Source | Formats | Notes |
| --- | --- | --- |
| Mutopia Project (mutopiaproject.org) | LilyPond, MIDI, PDF | Licenses vary per piece (PD, CC BY, CC BY-SA). The LilyPond source can't be converted here. Use the MIDI to check pitches with `compare`, and retype or take the notes from another format |
| OpenScore public-domain collections (MuseScore, musescore.com/openscore) | MusicXML | CC0. The best MusicXML source for classical songs and lieder |
| Humdrum / KernScores (github.com/craigsapp, kern.humdrum.org) | kern | Often CC BY-NC-SA: check only, don't copy. kern keeps spelling and voices |
| music21's corpus (in `tools/.venv`) | MusicXML, kern | Mostly public domain. Good for checking. `corpus.getWork("mozart/k545/movement1_exposition")` |
| Hymnary.org, Open Hymnal | ABC, MusicXML | Open Hymnal ABC is ABC Plus: convert with abc2xml first (the build already does this for `abc:`) |
| Folk collections in ABC (thesession.org, abcnotation.com) | ABC | Tunes are traditional. Check each transcription's own terms |
| IMSLP | PDF, sometimes MusicXML or MIDI | Use only files marked public domain or CC. Most are PDFs, to retype from |
| MuseScore.com general uploads | MuseScore, MusicXML | **Not collected automatically** (site terms). The parent can hand you a file they downloaded |

## Source fields in the piece file

```yaml
source:
  site: OpenScore
  url: https://musescore.com/openscore/scores/…
  id: "…"                   # the site's own id, for duplicate checks
  file: song.mxl            # what you converted
license:
  composition: public-domain          # or parent-supplied
  edition: CC0                        # or public-domain, CC BY 4.0, CC BY-SA 3.0, parent-supplied, "retyped from …"
  evidence: "composer died 1849; edition page states CC0"
```

## Lyrics

The lyrics must be public domain too, or parent-supplied. First-pass check for family-friendliness:
flag anything questionable in the review for the parent. Don't reword it yourself.
