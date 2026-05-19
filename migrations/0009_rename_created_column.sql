-- +brant Up

ALTER TABLE "mailing_list" RENAME COLUMN created TO linked;
ALTER TABLE "source_repo" RENAME COLUMN created TO linked;
ALTER TABLE "tracker" RENAME COLUMN created TO linked;

-- +brant Down

ALTER TABLE "tracker" RENAME COLUMN linked TO created;
ALTER TABLE "source_repo" RENAME COLUMN linked TO created;
ALTER TABLE "mailing_list" RENAME COLUMN linked TO created;
