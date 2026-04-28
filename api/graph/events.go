package graph

import (
	"context"
	"database/sql"
	"fmt"
)

func addResourceEvent(
	ctx context.Context, tx *sql.Tx,
	projectID int, resType ResourceType, resID int, userID int,
) error {
	var (
		prefix string
		err error
	)
	switch resType {
	case MailingList:
		prefix = "mailing_list"
	case GitRepository:
		prefix = "source_repo"
	case HgRepository:
		prefix = "source_repo"
	case Tracker:
		prefix = "tracker"
	default:
		panic(fmt.Sprintf("Unexpected resource type %T!\n", resType))
	}
	var eventID int
	event_id := tx.QueryRowContext(ctx, fmt.Sprintf(`
		INSERT INTO event (
			created, event_type, %s_id, user_id
		) VALUES (
			NOW() at time zone 'utc', $1, $2, $3
		) RETURNING id;`, prefix),
		fmt.Sprintf("%s_added", prefix), resID, userID)
	if err := event_id.Scan(&eventID); err != nil {
		return err
	}

	_, err = tx.ExecContext(ctx, `
		INSERT INTO event_project_association(event_id, project_id)
		VALUES($1, $2);
	`, eventID, projectID)
	return err
}
