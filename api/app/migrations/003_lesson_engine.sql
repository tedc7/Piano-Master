-- M5: the lesson engine's state (arch §5 SkillState, PracticeDay, Session; §8).

CREATE TABLE skill_states (
  student_id            TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  skill_id              TEXT NOT NULL,
  status                TEXT NOT NULL DEFAULT 'locked',   -- locked, current, passed, mastered
  concept_done          INTEGER NOT NULL DEFAULT 0,
  capability_hold       INTEGER NOT NULL DEFAULT 0,
  mastery               REAL,                             -- running value (8.2)
  best_mastery          REAL,
  best_accuracy_stars   REAL,
  best_timing_stars     REAL,
  attempts_without_pass INTEGER NOT NULL DEFAULT 0,       -- completed attempts while Current
  first_try_day         TEXT,                             -- first of those attempts (stuck needs 2 days)
  stuck                 INTEGER NOT NULL DEFAULT 0,
  stuck_since           TEXT,
  high_days             TEXT NOT NULL DEFAULT '[]',       -- JSON: days mastery reached 0.86
  high_timing           INTEGER NOT NULL DEFAULT 0,       -- one of those attempts had 3+ timing stars
  passed_date           TEXT,
  mastered_date         TEXT,
  last_practiced        TEXT,
  last_piece_id         TEXT,
  last_preset           TEXT,
  last_tricky_phrase    INTEGER,
  review_step           INTEGER,                          -- 0..6 on the 1, 3, 7, 14, 30, 60, 120 day ladder
  next_review_date      TEXT,
  last_review_date      TEXT,
  weak_reviews          INTEGER NOT NULL DEFAULT 0,       -- weak reviews in a row
  refresher             INTEGER NOT NULL DEFAULT 0,       -- concept lesson offered again after two weak reviews
  PRIMARY KEY (student_id, skill_id)
);

CREATE TABLE practice_days (
  student_id        TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  date              TEXT NOT NULL,                        -- local calendar day
  guided_sec        REAL NOT NULL DEFAULT 0,
  free_sec          REAL NOT NULL DEFAULT 0,
  target_minutes    REAL NOT NULL,
  session_completed INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (student_id, date)
);

CREATE TABLE sessions (
  student_id     TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  date           TEXT NOT NULL,
  target_minutes REAL NOT NULL,
  queue          TEXT NOT NULL,                           -- JSON list of items
  end_of_content INTEGER NOT NULL DEFAULT 0,
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL,
  PRIMARY KEY (student_id, date)
);

ALTER TABLE students ADD COLUMN target_minutes REAL NOT NULL DEFAULT 15;
ALTER TABLE students ADD COLUMN target_checked TEXT;     -- last weekly step-up check (8.6)
