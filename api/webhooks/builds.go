package webhooks

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"net/http"

	"git.sr.ht/~sircmpwn/core-go/config"
	"git.sr.ht/~sircmpwn/core-go/crypto"
	"git.sr.ht/~sircmpwn/core-go/database"
	"git.sr.ht/~sircmpwn/hub.sr.ht/api/graph"
	lists "git.sr.ht/~sircmpwn/hub.sr.ht/api/services/lists"
	"github.com/go-chi/chi/v5"
)

func ProcessBuildCompleteWebhook(w http.ResponseWriter, r *http.Request) {
	decryptedDetails := crypto.DecryptWithoutExpiration([]byte(chi.URLParam(r, "details")))
	var details struct {
		ListID     int    `json:"mailing_list"`
		PatchsetID int    `json:"patchset_id"`
		ToolID     int    `json:"tool_id"`
		Name       string `json:"name"`
		User       string `json:"user"`
	}
	if err := json.Unmarshal(decryptedDetails, &details); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	body, _ := io.ReadAll(r.Body)
	defer r.Body.Close()
	var payload struct {
		ID     int    `json:"id"`
		Status string `json:"status"`
		Owner  struct {
			CanonicalName string `json:"canonical_name"`
		} `json:"owner"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	if payload.Owner.CanonicalName != details.User {
		w.Write([]byte("Discarding webhook from unauthorized build"))
		w.WriteHeader(http.StatusUnauthorized)
		return
	}

	ctx := r.Context()

	var projectOwnerName string
	if err := database.WithTx(ctx,
		&sql.TxOptions{
			Isolation: 0,
			ReadOnly:  true,
		},
		func(tx *sql.Tx) error {
			owner := tx.QueryRowContext(ctx, `
				SELECT u.username FROM "user" u, project, mailing_list
				WHERE project.owner_id = u.id AND
					mailing_list.project_id = project.id AND
					mailing_list.id = $1`, details.ListID)
			if err := owner.Scan(&projectOwnerName); err != nil {
				return err
			}
			return nil
		},
	); err != nil {
		w.Write([]byte("Unknown mailing list"))
		w.WriteHeader(http.StatusNotFound)
		return
	}

	buildsOrigin := config.GetOrigin(config.ForContext(ctx), "builds.sr.ht", true)
	buildURL := fmt.Sprintf("%s/~%s/job/%d", buildsOrigin, projectOwnerName, payload.ID)
	statusDetails := fmt.Sprintf("[#%d](%s) %s %s", payload.ID, buildURL, details.Name, payload.Status)

	var icon lists.ToolIcon
	switch payload.Status {
	case "pending":
		icon = lists.ToolIconPending
	case "queued", "running":
		icon = lists.ToolIconWaiting
	case "success":
		icon = lists.ToolIconSuccess
	case "failed", "timeout":
		icon = lists.ToolIconFailed
	case "cancelled'":
		icon = lists.ToolIconCancelled
	}

	listsClient := graph.NewListsClientForUser(ctx, projectOwnerName)
	lists.UpdateTool(
		listsClient, ctx, int32(details.ToolID),
		statusDetails,
		icon,
	)

	w.WriteHeader(http.StatusOK)
	w.Write([]byte("Thanks!"))
}
