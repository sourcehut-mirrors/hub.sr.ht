CREATE TYPE visibility AS ENUM (
	'PUBLIC',
	'PRIVATE',
	'UNLISTED'
);

CREATE TYPE user_type AS ENUM (
	'PENDING',
	'USER',
	'ADMIN',
	'SUSPENDED'
);

CREATE TABLE "user" (
	id serial PRIMARY KEY,
	created timestamp without time zone NOT NULL,
	updated timestamp without time zone NOT NULL,
	username character varying(256),
	email character varying(256) NOT NULL,
	user_type user_type NOT NULL,
	url character varying(256),
	location character varying(256),
	bio character varying(4096),
	suspension_notice character varying(4096),
	oauth_token character varying(256),
	oauth_token_expires timestamp without time zone,
	oauth_token_scopes character varying
);

CREATE UNIQUE INDEX ix_user_username ON "user" USING btree (username);

CREATE TABLE project (
	id serial PRIMARY KEY,
	created timestamp without time zone NOT NULL,
	updated timestamp without time zone NOT NULL,
	owner_id integer NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
	name character varying(128) NOT NULL,
	description character varying(512) NOT NULL,
	website character varying,
	visibility visibility DEFAULT 'UNLISTED'::visibility NOT NULL,
	checklist_complete boolean DEFAULT false NOT NULL,
	summary_repo_id integer,
	tags character varying(16)[] DEFAULT '{}'::character varying[] NOT NULL
);

CREATE TABLE features (
	id serial PRIMARY KEY,
	created timestamp without time zone NOT NULL,
	project_id integer NOT NULL REFERENCES project(id) ON DELETE CASCADE,
	summary character varying NOT NULL
);

CREATE TABLE mailing_list (
	id serial PRIMARY KEY,
	remote_id integer NOT NULL,
	created timestamp without time zone NOT NULL,
	updated timestamp without time zone NOT NULL,
	project_id integer NOT NULL REFERENCES project(id) ON DELETE CASCADE,
	owner_id integer NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
	name character varying(128) NOT NULL,
	description character varying,
	visibility visibility DEFAULT 'UNLISTED'::visibility NOT NULL
);

CREATE TABLE source_repo (
	id serial PRIMARY KEY,
	remote_id integer NOT NULL,
	created timestamp without time zone NOT NULL,
	updated timestamp without time zone NOT NULL,
	project_id integer NOT NULL REFERENCES project(id) ON DELETE CASCADE,
	owner_id integer NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
	name character varying(128) NOT NULL,
	description character varying,
	repo_type character varying NOT NULL,
	visibility visibility DEFAULT 'UNLISTED'::visibility NOT NULL,
	CONSTRAINT project_source_repo_unique UNIQUE (project_id, remote_id, repo_type)
);

ALTER TABLE project
	ADD CONSTRAINT project_summary_repo_id_fkey FOREIGN KEY (summary_repo_id) REFERENCES source_repo(id) ON DELETE CASCADE;

CREATE TABLE tracker (
	id serial PRIMARY KEY,
	remote_id integer NOT NULL,
	created timestamp without time zone NOT NULL,
	updated timestamp without time zone NOT NULL,
	project_id integer NOT NULL REFERENCES project(id) ON DELETE CASCADE,
	owner_id integer NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
	name character varying(128) NOT NULL,
	description character varying,
	visibility visibility DEFAULT 'UNLISTED'::visibility NOT NULL
);

CREATE TABLE event (
	id serial PRIMARY KEY,
	created timestamp without time zone NOT NULL,
	project_id integer NOT NULL REFERENCES project(id) ON DELETE CASCADE,
	user_id integer REFERENCES "user"(id) ON DELETE CASCADE,
	event_type character varying NOT NULL,
	source_repo_id integer REFERENCES source_repo(id) ON DELETE CASCADE,
	mailing_list_id integer REFERENCES mailing_list(id) ON DELETE CASCADE,
	tracker_id integer REFERENCES tracker(id) ON DELETE CASCADE,
	external_source character varying,
	external_summary character varying,
	external_details character varying,
	external_summary_plain character varying,
	external_details_plain character varying,
	external_url character varying
);
