-- Migration 167: broadcast_recipients.lead_id must accept NULL
--
-- Invalid/unmatched phone numbers legitimately have no lead_id (upload.py's
-- immediate-send path already inserts lead_id=NULL for them). broadcast_executor.py's
-- scheduled/drip/retry path does the same for its excluded-lead branch. With lead_id
-- NOT NULL, any such row poisoned the WHOLE batch insert (batches of 100) — silently
-- caught and logged, so broadcast_recipients ended up empty for that broadcast even
-- though sent/failed counts (computed in-memory) still looked correct in History.
-- That's why a broadcast could show "Failed 1 of 6" in History with a completely
-- empty failed-CSV / segment-CSV download.

ALTER TABLE broadcast_recipients ALTER COLUMN lead_id DROP NOT NULL;
