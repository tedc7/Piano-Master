-- M2: devices, attempts with raw events, and client logs. Shaped for M4, which adds students
-- and progress: attempts.student_id is filled from then on.

CREATE TABLE devices (
  id             TEXT PRIMARY KEY,
  created_at     TEXT NOT NULL,
  last_seen      TEXT NOT NULL,
  user_agent     TEXT,
  client_version TEXT,
  profile        TEXT NOT NULL DEFAULT '{}'   -- DeviceProfile fields (JSON) until M4 gives them columns
);

CREATE TABLE attempts (
  id                TEXT PRIMARY KEY,          -- made by the client, so outbox resends are harmless
  device_id         TEXT NOT NULL REFERENCES devices(id),
  student_id        TEXT,                      -- M4
  piece_id          TEXT NOT NULL,
  arrangement_id    TEXT NOT NULL,
  content_version   TEXT,
  context           TEXT NOT NULL,             -- guided or free
  mode              TEXT NOT NULL,             -- play or loop
  completed         INTEGER NOT NULL,
  started_at        TEXT NOT NULL,
  received_at       TEXT NOT NULL,
  duration_sec      REAL,
  tempo_preset      TEXT NOT NULL,
  conditions        TEXT NOT NULL,             -- JSON: mode, preset, hands, section, hints, rewinds
  conditions_factor REAL NOT NULL,
  raw_accuracy      REAL NOT NULL,
  raw_timing        REAL,
  accuracy          REAL NOT NULL,
  timing_score      REAL,
  accuracy_stars    REAL NOT NULL,
  timing_stars      REAL,
  latency_offset_ms REAL,
  display_offset_ms REAL,
  section           TEXT,                      -- JSON {fromBeat, toBeat} for a loop
  per_phrase_errors TEXT NOT NULL,             -- JSON
  note_errors       TEXT NOT NULL,             -- JSON: expected vs played, with bars
  tricky            TEXT,                      -- JSON {phrase, bars}
  evaluation        TEXT NOT NULL,             -- JSON: the client's full evaluation
  raw_events        TEXT NOT NULL,             -- JSON: every key, pedal and pass (for Diagnostics and fixtures)
  passes            TEXT NOT NULL,             -- JSON
  client_version    TEXT
);
CREATE INDEX attempts_piece ON attempts (piece_id, started_at);
CREATE INDEX attempts_device ON attempts (device_id, started_at);

CREATE TABLE client_logs (
  id          INTEGER PRIMARY KEY,
  time        TEXT NOT NULL,                   -- on the client
  received_at TEXT NOT NULL,
  device_id   TEXT,
  student_id  TEXT,
  level       TEXT NOT NULL,
  message     TEXT NOT NULL,
  context     TEXT
);
CREATE INDEX client_logs_received ON client_logs (received_at);
