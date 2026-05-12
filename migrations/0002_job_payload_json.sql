BEGIN;

SET search_path TO open_swe;

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS payload_json TEXT;

COMMIT;
