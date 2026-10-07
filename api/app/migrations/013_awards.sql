-- M10: medals a student has earned (arch §5 Award, §3 "Rewards"). A medal is never taken back.
-- The star collection is not stored: it is each song's best accuracy stars, from the attempts.

CREATE TABLE IF NOT EXISTS awards (
  student_id  TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  id          TEXT NOT NULL,          -- "stars:100", "streak:7", "unit:<level>|<unit>:complete", "level:<level>:mastered"
  kind        TEXT NOT NULL,          -- stars, streak, mastered, fivestar, songs, hours, unit, level
  tier        TEXT NOT NULL,          -- bronze, silver, gold, platinum
  title       TEXT NOT NULL,          -- as shown when it was earned ("Unit 4 · Reading the Staff")
  detail      TEXT NOT NULL,          -- "Complete", "250 stars"
  earned_date TEXT NOT NULL,          -- local calendar day
  seen        INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (student_id, id)
);
