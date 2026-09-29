-- M6: Diagnostics (arch §8.8), generated drills (§8.9) and theory scoring (§7.8).

-- Each expected note of the scored pass: [notation note index, timing in ms, or null when missed].
ALTER TABLE attempts ADD COLUMN note_results TEXT;

CREATE TABLE error_patterns (
  id              TEXT PRIMARY KEY,
  student_id      TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  kind            TEXT NOT NULL,                  -- note, rhythm, hands, shift, tempo
  key             TEXT NOT NULL,                  -- what makes two findings the same pattern
  details         TEXT NOT NULL,                  -- JSON: what was found, and the numbers
  skill_ids       TEXT NOT NULL DEFAULT '[]',     -- JSON
  occurrences     INTEGER NOT NULL DEFAULT 0,
  first_seen      TEXT NOT NULL,                  -- local calendar days
  last_seen       TEXT NOT NULL,
  remedies_tried  TEXT NOT NULL DEFAULT '[]',     -- JSON: days a remedy item was done
  good_days       TEXT NOT NULL DEFAULT '[]',     -- JSON: days the affected notes scored 4+ stars
  status          TEXT NOT NULL DEFAULT 'active', -- active, improving, resolved, stuck
  resolved_date   TEXT,
  UNIQUE (student_id, key)
);

CREATE TABLE drills (
  id          TEXT PRIMARY KEY,                   -- "drill-…", used as the attempt's piece id
  student_id  TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  pattern_id  TEXT,
  kind        TEXT NOT NULL,                      -- reading, rhythm, scale, …
  piece       TEXT NOT NULL,                      -- JSON: a piece in the client's format
  created     TEXT NOT NULL
);

CREATE TABLE lesson_results (
  student_id  TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  skill_id    TEXT NOT NULL,
  date        TEXT NOT NULL,
  questions   INTEGER NOT NULL,
  points      REAL NOT NULL,                      -- 1 right first time, 0.5 second time (§7.8)
  stars       REAL NOT NULL,
  created     TEXT NOT NULL
);
CREATE INDEX lesson_results_student ON lesson_results (student_id, skill_id);
