-- The helpers on a song's staff (v0.29, arch §3): finger numbers and letter names, switched on or off
-- for each song by the parent (the Play screen's Song and settings), for every child. A missing row,
-- or a NULL, keeps the default: finger numbers on in Prep A songs and off in later levels, letter
-- names as the song's file has them (Prep A Units 1 to 3).
CREATE TABLE song_display (
  piece_id   TEXT PRIMARY KEY,
  fingers    INTEGER,
  letters    INTEGER,
  updated_at TEXT NOT NULL
);
