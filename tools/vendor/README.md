# Vendored converters

Two ABC and MusicXML converters by Willem G. Vree, kept here at the versions the content build and
the song import were made and checked with. The author's site offers only the newest version, and
a newer one can change the built notation, which the songs' vocal and backing stems are aligned to.

| Folder | What | Used by |
| --- | --- | --- |
| `abc2xml_268/abc2xml.py` | abc2xml 268: ABC with several voices to MusicXML (music21's ABC reader merges voices) | `tools/notation.py` (the content build) |
| `xml2abc_177/xml2abc.py` | xml2abc 177: MusicXML to ABC | `tools/import_song.py convert` |

Both are free software under the GNU Lesser General Public License, as each file's header says,
copyright Willem G. Vree and contributors; the license text is in `COPYING.LESSER`. They are
unchanged copies of the files from https://wim.vree.org/svgParse/ (abc2xml.py-268.zip,
xml2abc.py-177.zip). To move to a newer version, rebuild the content and check that no song's
notation changes before replacing them.
