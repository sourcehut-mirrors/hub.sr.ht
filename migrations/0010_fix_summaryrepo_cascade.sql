-- +brant Up
ALTER TABLE project
	DROP CONSTRAINT project_summary_repo_id_fkey,
	ADD CONSTRAINT project_summary_repo_id_fkey
	FOREIGN KEY (summary_repo_id)
	REFERENCES source_repo(id) ON DELETE SET NULL;

-- +brant Down
ALTER TABLE project
	DROP CONSTRAINT project_summary_repo_id_fkey,
	ADD CONSTRAINT project_summary_repo_id_fkey
	FOREIGN KEY (summary_repo_id)
	REFERENCES source_repo(id) ON DELETE CASCADE;	
