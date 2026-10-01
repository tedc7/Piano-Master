-- Library songs are analysed again when a deploy changes the skill map (v0.26, arch §6.10). One row:
-- the skill map the library was last analysed against, and the songs whose analysis changed then.
CREATE TABLE library_analysis (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  map_hash TEXT NOT NULL,              -- the deployed skill map (ids, sequences, prerequisites, constraints)
  content_version TEXT,                -- the deployed content version it came with
  analysed_at TEXT NOT NULL,
  songs INTEGER NOT NULL,              -- library songs analysed
  changes TEXT NOT NULL DEFAULT '[]'   -- [{pieceId, title, before: {requiredSkills, beyondMap}, after: {...}}]
)
