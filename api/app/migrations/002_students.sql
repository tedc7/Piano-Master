-- M4: students, the parent PIN and its sessions, favorites. Attempts now name the student, the
-- skill the session item was for, and the session item, so progress follows each child.

CREATE TABLE students (
  id           TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  avatar       TEXT NOT NULL,
  start_date   TEXT NOT NULL,                  -- local calendar day
  status       TEXT NOT NULL DEFAULT 'active', -- active or archived
  settings     TEXT NOT NULL DEFAULT '{}',     -- JSON: autoRewind, rewindBars, backingVolume, vocalsOff, click, presets
  sort         INTEGER NOT NULL DEFAULT 0,
  created_at   TEXT NOT NULL
);

CREATE TABLE parent (
  id                  INTEGER PRIMARY KEY CHECK (id = 1),
  pin_hash            TEXT,                    -- scrypt; NULL until the parent chooses a PIN
  failed_attempts     INTEGER NOT NULL DEFAULT 0,
  locked_until        TEXT,
  lockouts            INTEGER NOT NULL DEFAULT 0,  -- each further lockout doubles its length
  auto_logout_minutes INTEGER NOT NULL DEFAULT 10
);
INSERT INTO parent (id) VALUES (1);

CREATE TABLE parent_sessions (
  token_hash TEXT PRIMARY KEY,                 -- sha256 of the token the client holds
  created_at TEXT NOT NULL,
  last_used  TEXT NOT NULL
);

CREATE TABLE favorites (
  student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  piece_id   TEXT NOT NULL,
  added_at   TEXT NOT NULL,
  PRIMARY KEY (student_id, piece_id)
);

ALTER TABLE attempts ADD COLUMN skill_id TEXT;
ALTER TABLE attempts ADD COLUMN item_id TEXT;
CREATE INDEX attempts_student ON attempts (student_id, started_at);
