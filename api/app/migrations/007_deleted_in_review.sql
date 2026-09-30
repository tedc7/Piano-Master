-- Deleted songs live in the review area (v0.23): the library holds only approved songs, and every
-- song that isn't in it (waiting, sent back for changes, or deleted) is a staged item. "Never
-- allow" in the review list and "Delete" in Songs and genres both make a song `deleted`; its files
-- stay in staging, so it can go back to review, be sent for improvement, or be forgotten.
ALTER TABLE staged_items ADD COLUMN deleted_from TEXT;        -- review (never allowed) or library (deleted)
ALTER TABLE staged_items ADD COLUMN deleted_reason TEXT;
UPDATE staged_items SET status = 'deleted', deleted_from = 'review' WHERE status = 'never';
-- records from the old deleted list (no files: they can be forgotten, not listened to)
INSERT INTO packages (id, name, skill, notes, status, created_at)
  SELECT 'deleted-before', 'Deleted before v0.23', 'parent', NULL, 'done', datetime('now')
  WHERE EXISTS (SELECT 1 FROM deleted_songs);
INSERT INTO staged_items (id, package_id, piece_id, song, title, composer, genre, info, report, fingerprint, media, status,
                          decided_at, deleted_from, deleted_reason)
  SELECT id, 'deleted-before', COALESCE(song, id), COALESCE(song, id), title, composer, '',
         json_object('sourceIds', json(source_ids)), '{}', fingerprint, '[]', 'deleted', deleted_at, 'library', reason
  FROM deleted_songs;
DROP TABLE deleted_songs;
