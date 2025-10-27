-- +brant Up
ALTER TABLE source_repo
ALTER COLUMN webhook_id SET NOT NULL,
ALTER COLUMN webhook_version SET NOT NULL;

ALTER TABLE tracker
ALTER COLUMN webhook_id SET NOT NULL,
ALTER COLUMN webhook_version SET NOT NULL;

-- +brant Down
ALTER TABLE source_repo
ALTER COLUMN webhook_id DROP NOT NULL,
ALTER COLUMN webhook_version DROP NOT NULL;

ALTER TABLE tracker
ALTER COLUMN webhook_id DROP NOT NULL,
ALTER COLUMN webhook_version DROP NOT NULL;
