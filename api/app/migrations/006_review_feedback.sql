-- M7 review, one song at a time (v0.23): each staged song waits until the parent approves it,
-- sends it back with what needs to change, or never allows it. The feedback is kept for the Claude
-- skills to read (Skill API); a resubmitted song replaces the one sent back and shows its feedback.
ALTER TABLE staged_items ADD COLUMN feedback TEXT;            -- the parent's "needs improvement" note
ALTER TABLE staged_items ADD COLUMN decided_at TEXT;
ALTER TABLE staged_items ADD COLUMN replaces TEXT;            -- the item this resubmission replaces
CREATE INDEX staged_items_piece ON staged_items (piece_id, status);
