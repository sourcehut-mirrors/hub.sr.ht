package graph

import (
	"context"
	"database/sql"
	"log"
	"net/http"

	"git.sr.ht/~sircmpwn/core-go/auth"
	"git.sr.ht/~sircmpwn/core-go/database"
	coremodel "git.sr.ht/~sircmpwn/core-go/model"
	work "git.sr.ht/~sircmpwn/dowork"
	gitclient "git.sr.ht/~sircmpwn/hub.sr.ht/api/services/git"
	listsclient "git.sr.ht/~sircmpwn/hub.sr.ht/api/services/lists"
	todoclient "git.sr.ht/~sircmpwn/hub.sr.ht/api/services/todo"
)

type contextKey struct {
	name string
}

var ctxKey = &contextKey{"deletion"}

func ProjectMiddleware(queue *work.Queue) func(next http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			ctx := context.WithValue(r.Context(), ctxKey, queue)
			r = r.WithContext(ctx)
			next.ServeHTTP(w, r)
		})
	}
}

// Schedules a project deletion.
func DeleteProject(ctx context.Context, rid coremodel.RID) {
	queue, ok := ctx.Value(ctxKey).(*work.Queue)
	if !ok {
		panic("No project deletion worker for this context")
	}

	user := auth.ForContext(ctx)
	task := work.NewTask(func(ctx context.Context) error {
		log.Printf("Processing deletion of project %s", rid.String())

		ctx = auth.Context(ctx, user)

		var listWebhookIDs, gitWebhookIDs, todoWebhookIDs []int
		if err := database.WithTx(ctx, nil, func(tx *sql.Tx) error {
			var projectID int

			// Collect the associated resources' webhook IDs for clean-up
			// if the project deletion succeeds (note that hg does not
			// support repository webhooks).
			listWebhookIDs, _ = collectWebhookIDs(ctx, tx, projectID, MailingList)
			gitWebhookIDs, _ = collectWebhookIDs(ctx, tx, projectID, GitRepository)
			todoWebhookIDs, _ = collectWebhookIDs(ctx, tx, projectID, Tracker)

			_, err := tx.ExecContext(ctx, `
				DELETE FROM project WHERE rid = $1;
			`, rid)
			return err
		}); err != nil {
			return err
		}

		// Best-effort clean-up of the associated webhooks.
		for _, whID := range listWebhookIDs {
			listsclient.DeleteListWebhook(
				NewListsGQLClient(ctx),
				ctx, int32(whID),
			)
		}
		for _, whID := range gitWebhookIDs {
			gitclient.DeleteRepoWebhook(
				NewGitGQLClient(ctx),
				ctx, int32(whID),
			)
		}
		for _, whID := range todoWebhookIDs {
			todoclient.DeleteTrackerWebhook(
				NewTodoGQLClient(ctx),
				ctx, int32(whID),
			)
		}

		log.Printf("Deletion of project %s complete", rid.String())
		return nil
	})
	queue.Enqueue(task)
	log.Printf("Enqueued deletion of project %s", rid.String())
}
