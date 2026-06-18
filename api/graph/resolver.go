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
	projectRID coremodel.RID, resourceRID coremodel.RID,
) (model.ProjectResource, error) {
	project, err := r.Query().Project(ctx, projectRID)
	if err != nil || project == nil {
		return nil, fmt.Errorf("no project with RID %s found for this user", projectRID.String())
	}

	if project.OwnerID != auth.ForContext(ctx).UserID {
		return nil, fmt.Errorf("modifications only allowed to project owners")
	}

	resource, err := r.Project().Resource(ctx, project, resourceRID)
	if err != nil || resource == nil {
		return nil, fmt.Errorf("no resource with RID %s linked to this project", resourceRID.String())
	}

	var tableName string
	switch t := resource.(type) {
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
	`, tableName), project.ID, resourceRID.String())
	return resource, err
}
