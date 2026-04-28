package graph

import (
	"context"
	"database/sql"
	"fmt"

	"git.sr.ht/~sircmpwn/core-go/auth"
	coremodel "git.sr.ht/~sircmpwn/core-go/model"
	"git.sr.ht/~sircmpwn/hub.sr.ht/api/graph/model"
)

type Resolver struct{}

func UnlinkResource(
	r *mutationResolver, ctx context.Context, tx *sql.Tx,
	project coremodel.RID, resource coremodel.RID,
) (model.ProjectResource, error) {
	projectRow, err := r.Query().Project(ctx, project)
	if err != nil || projectRow == nil {
		return nil, fmt.Errorf("no project with RID %s found for this user", project.String())
	}

	if projectRow.OwnerID != auth.ForContext(ctx).UserID {
		return nil, fmt.Errorf("modifications only allowed to project owners")
	}

	resourceRow, err := r.Project().Resource(ctx, projectRow, resource)
	if err != nil || resourceRow == nil {
		return nil, fmt.Errorf("no resource with RID %s linked to this project", resource.String())
	}

	var tableName string
	switch t := resourceRow.(type) {
	case *model.MailingList:
		tableName = t.Table()
	case *model.SourceRepo:
		tableName = t.Table()
	case *model.Tracker:
		tableName = t.Table()
	default:
		panic(fmt.Sprintf("Unexpected resource type %T!\n", t))
	}

	_, err = tx.ExecContext(ctx, fmt.Sprintf(`
		DELETE FROM %s
		WHERE project_id = $1 AND remote_rid = $2
	`, tableName), projectRow.ID, resource.String())
	return resourceRow, err
}
