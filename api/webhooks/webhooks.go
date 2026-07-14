package webhooks

import (
	"context"
	"database/sql"

	"github.com/lib/pq"
)

func dedupeEvent(ctx context.Context, tx *sql.Tx, eventSource string,
	projectID int, eventURL string, eventUserID int,
) int {
	var existingEventID int
	event := tx.QueryRowContext(ctx, `
               SELECT id FROM event
               WHERE
                       event_type = $1 AND
                       external_source = $2 AND
                       external_url = $3 AND
                       (user_id IS NULL OR user_id = $4)
       `, "external_event", eventSource, eventURL, eventUserID)
	if err := event.Scan(&existingEventID); err != nil {
		existingEventID = 0
	}
	if existingEventID != 0 {
		err := addEventProjectAssociation(ctx, tx, existingEventID, projectID)
		if err != nil {
			existingEventID = 0
		}
	}
	return existingEventID
}

func addEventProjectAssociation(ctx context.Context, tx *sql.Tx,
	eventID int, projectID int,
) error {
	_, err := tx.ExecContext(ctx, `
               INSERT INTO event_project_association
               VALUES($1, $2);`, eventID, projectID)
	return err
}

func refreshProjectUpdated(ctx context.Context, tx *sql.Tx, projectID int) error {
	_, err := tx.ExecContext(ctx, `
               UPDATE project
               SET updated = NOW() at time zone 'utc'
               WHERE id = $1;`, projectID)
	return err
}

func refreshProjectsUpdated(ctx context.Context, tx *sql.Tx, rows *sql.Rows) error {
	var projects []int
	var err error
	for rows.Next() {
		var projectID int
		if err = rows.Scan(&projectID); err != nil {
			return err
		}
		projects = append(projects, projectID)
	}
	if len(projects) > 0 {
		_, err := tx.ExecContext(ctx, `
                       UPDATE project
                       SET updated = NOW() at time zone 'utc'
                       WHERE id = ANY($1);`, pq.Array(projects))
		return err
	}
	return nil
}
