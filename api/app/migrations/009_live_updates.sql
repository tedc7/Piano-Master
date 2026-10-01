-- Updating a live song (v0.27, arch §10.7): the parent's "Needs improvement" on a song in the library
-- is a staged item that names the live song (`live`), with no files of its own. The fixed song,
-- resubmitted under the same id, replaces the request in the review list and keeps `live`; approving
-- it replaces the live song in place. Until then the children keep playing the live one.
ALTER TABLE staged_items ADD COLUMN live TEXT;     -- the library song this updates (its piece id), or NULL
