-- M7: intake, staging and the parent's review (arch §10.7), the approved song library (§10.1),
-- the deleted-songs list (§10.8), genre and song rules per child (§10.1), and the Claude skills'
-- tokens for the Skill API (§10.9). Files live beside the database: staging/<package>/<piece>/,
-- library/<piece>/ and removed/<piece>/ (a deleted song's files, kept so it can be restored).

CREATE TABLE skill_tokens (
  token_hash TEXT PRIMARY KEY,                 -- sha256 of the token the dev box holds
  name       TEXT NOT NULL,                    -- which skill or machine it's for
  created_at TEXT NOT NULL,
  last_used  TEXT
);

CREATE TABLE packages (
  id           TEXT PRIMARY KEY,
  name         TEXT NOT NULL,                  -- the batch's name
  skill        TEXT NOT NULL,                  -- the token's name
  notes        TEXT,                           -- Claude's summary for the parent
  status       TEXT NOT NULL,                  -- open (media uploading), staged (waiting for review), done
  created_at   TEXT NOT NULL,
  submitted_at TEXT,
  reviewed_at  TEXT
);

CREATE TABLE staged_items (
  id          TEXT PRIMARY KEY,
  package_id  TEXT NOT NULL REFERENCES packages(id) ON DELETE CASCADE,
  piece_id    TEXT NOT NULL,
  song        TEXT NOT NULL,                   -- arrangements of one song share this
  title       TEXT NOT NULL,
  composer    TEXT,
  genre       TEXT NOT NULL,
  info        TEXT NOT NULL,                   -- JSON: level, source, license, flags, notes, lyrics, media checks
  report      TEXT NOT NULL,                   -- JSON: intake errors and warnings
  fingerprint TEXT NOT NULL,                   -- JSON list of melody-fingerprint hashes
  media       TEXT NOT NULL DEFAULT '[]',      -- JSON: [{file, bytes}] the stems it needs
  status      TEXT NOT NULL                    -- rejected (by intake), staged, approved, discarded, never
);
CREATE INDEX staged_items_package ON staged_items (package_id);

CREATE TABLE library (
  piece_id    TEXT PRIMARY KEY,
  song        TEXT NOT NULL,
  title       TEXT NOT NULL,
  composer    TEXT,
  genre       TEXT NOT NULL,
  source_ids  TEXT NOT NULL DEFAULT '[]',
  fingerprint TEXT NOT NULL,
  info        TEXT NOT NULL,
  entry       TEXT NOT NULL,                   -- JSON: its row in the content index
  approved_at TEXT NOT NULL,
  package_id  TEXT
);

CREATE TABLE deleted_songs (
  id          TEXT PRIMARY KEY,
  song        TEXT,
  title       TEXT NOT NULL,
  composer    TEXT,
  source_ids  TEXT NOT NULL DEFAULT '[]',
  fingerprint TEXT NOT NULL DEFAULT '[]',
  reason      TEXT,
  deleted_at  TEXT NOT NULL,
  rows        TEXT NOT NULL DEFAULT '[]'       -- JSON: its library rows, to restore it ([] for "never add")
);

CREATE TABLE genre_rules (
  student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  genre      TEXT NOT NULL,
  allowed    INTEGER NOT NULL,
  PRIMARY KEY (student_id, genre)
);

CREATE TABLE song_rules (
  student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  song       TEXT NOT NULL,
  allowed    INTEGER NOT NULL,                 -- overrides the genre rule
  PRIMARY KEY (student_id, song)
);
