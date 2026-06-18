package webhooks

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"html"
	"slices"
	"strings"

	"git.sr.ht/~sircmpwn/core-go/config"
	"git.sr.ht/~sircmpwn/core-go/database"
	git "git.sr.ht/~sircmpwn/hub.sr.ht/api/services/git"
	hg "git.sr.ht/~sircmpwn/hub.sr.ht/api/services/hg"
)

func ProcessSourceRepoUserWebhook(ctx context.Context, userID int,
	repoType string, webhookPayload []byte,
) error {
	switch repoType {
	case "GIT":
		var body struct {
			Data struct {
				Webhook git.RepositoryEvent `json:"webhook"`
			} `json:"data"`
		}
		if err := json.Unmarshal(webhookPayload, &body); err != nil {
			return err
		}

		repo := body.Data.Webhook.Repository
		switch body.Data.Webhook.Event {
		case git.WebhookEventRepoUpdate:
			return updateRepository(ctx, repo.Rid, repo.Name,
				repoType, repo.Visibility, repo.Description)
		case git.WebhookEventRepoDeleted:
			return deleteRepository(ctx, repo.Rid, repoType)
		}
	case "HG":
		var body struct {
			Data struct {
				Webhook hg.RepositoryEvent `json:"webhook"`
			} `json:"data"`
		}
		if err := json.Unmarshal(webhookPayload, &body); err != nil {
			return err
		}

		repo := body.Data.Webhook.Repository
		switch body.Data.Webhook.Event {
		case hg.WebhookEventRepoUpdate:
			return updateRepository(ctx, repo.Rid, repo.Name,
				repoType, repo.Visibility, repo.Description)
		case hg.WebhookEventRepoDeleted:
			return deleteRepository(ctx, repo.Rid, repoType)
		}
	}

	return nil
}

func updateRepository(ctx context.Context,
	repoRID string, repoName string, repoType string,
	repoVisibility any, repoDescription *string,
) error {
	return database.WithTx(ctx,
		&sql.TxOptions{
			Isolation: 0,
			ReadOnly:  false,
		},
		func(tx *sql.Tx) error {
			projects, err := tx.QueryContext(ctx, `
                               UPDATE source_repo
                               SET
                                       name = $1,
                                       description = $2,
                                       visibility = $3,
                                       updated = NOW() at time zone 'utc'
                               WHERE remote_rid = $4 AND repo_type = $5
                               RETURNING project_id;`,
				repoName, repoDescription,
				repoVisibility, repoRID, repoType)
			if err != nil {
				return err
			}
			return refreshProjectsUpdated(ctx, tx, projects)
		},
	)
}

func deleteRepository(ctx context.Context, repoRID string, repoType string) error {
	return database.WithTx(ctx,
		&sql.TxOptions{
			Isolation: 0,
			ReadOnly:  false,
		}, func(tx *sql.Tx) error {
			projects, err := tx.QueryContext(ctx, `
                               DELETE FROM source_repo
                               WHERE remote_rid = $1 AND repo_type = $2
                               RETURNING project_id;
                       `, repoRID, repoType)
			if err != nil {
				return err
			}
			return refreshProjectsUpdated(ctx, tx, projects)
		},
	)
}

func ProcessGitRepoWebhook(ctx context.Context, repoID int, webhookPayload []byte) error {
	var body struct {
		Data struct {
			Webhook git.GitEvent `json:"webhook"`
		} `json:"data"`
	}
	if err := json.Unmarshal(webhookPayload, &body); err != nil {
		return err
	}

	if body.Data.Webhook.Event != git.WebhookEventGitPostReceive {
		return nil
	}

	repoName := body.Data.Webhook.Repository.Name
	repoOwnerCanonicalName := body.Data.Webhook.Repository.Owner.CanonicalName

	return database.WithTx(ctx,
		&sql.TxOptions{
			Isolation: 0,
			ReadOnly:  false,
		},
		func(tx *sql.Tx) error {
			var projectID int
			repo := tx.QueryRowContext(ctx, `
                               UPDATE source_repo
                               SET updated = NOW() at time zone 'utc'
                               WHERE id = $1
                               RETURNING project_id`, repoID)
			if err := repo.Scan(&projectID); err != nil {
				return err
			}
			if err := refreshProjectUpdated(ctx, tx, projectID); err != nil {
				return err
			}

			var (
				pusherUserID int
				eventUserID  *int
			)
			switch s := body.Data.Webhook.Pusher.Value.(type) {
			case *git.User:
				user := tx.QueryRowContext(ctx, `
                                       SELECT id FROM "user" u
                                       WHERE u.username = $1
                                       `, s.Username)
				if err := user.Scan(&pusherUserID); err != nil {
					return err
				}
				eventUserID = &pusherUserID
			}
			pusherCanonicalName := body.Data.Webhook.Pusher.CanonicalName

			gitOrigin := config.GetOrigin(config.ForContext(ctx),
				"git.sr.ht", true)
			repoUrl := fmt.Sprintf("%s/%s/%s", gitOrigin,
				repoOwnerCanonicalName, repoName)
			for _, update := range body.Data.Webhook.Updates {
				if update.New == nil {
					continue
				}
				commitSha := update.New.ShortId
				commitUrl := fmt.Sprintf("%s/commit/%s",
					repoUrl, commitSha)
				var commitMsg string
				switch v := update.New.Value.(type) {
				case *git.Commit:
					commitMsg = v.Message
				case *git.Tag:
					commitMsg = v.Message
				}
				commitMsg = strings.Split(commitMsg, "\n")[0]

				existingEventID := dedupeEvent(
					ctx, tx, "git.sr.ht", projectID,
					commitUrl, pusherUserID)
				if existingEventID == 0 {
					err := createEvent(ctx, tx,
						projectID,
						repoID, repoName, repoUrl,
						repoOwnerCanonicalName,
						commitUrl, commitSha, commitMsg,
						pusherUserID, pusherCanonicalName,
						eventUserID)
					if err != nil {
						return err
					}
				}

				// Handle commit trailers
				if update.Log == nil {
					continue
				}
				slices.Reverse(update.Log.Results)
				for _, commit := range update.Log.Results {
					comment := fmt.Sprintf(
						`<i>%s referenced this ticket in commit [%s] on <a href="%s">%s</a>.</i>

[%s]: %s "%s"`,
						html.EscapeString(commit.Author.Name),
						commitSha, repoUrl, repoName,
						commitSha, commitUrl,
						html.EscapeString(commitMsg))
					for _, trailer := range commit.Trailers {
						handleTrailer(ctx, trailer.Name,
							trailer.Value,
							pusherCanonicalName[1:],
							comment, true)
					}
				}
			}

			return nil
		},
	)
}

func createEvent(ctx context.Context, tx *sql.Tx,
	projectID int,
	repoID int, repoName string, repoUrl string, repoOwnerCanonicalName string,
	commitUrl string, commitSha string, commitMsg string,
	pusherUserID int, pusherCanonicalName string,
	eventUserID *int,
) error {
	summary := fmt.Sprintf("<a href='%s'>%s</a> <code>%s</code>",
		commitUrl, commitSha,
		html.EscapeString(commitMsg))
	summaryPlain := fmt.Sprintf("%s - Commit %s", commitSha, repoName)
	var pusherInfo string
	if pusherUserID != 0 {
		gitOrigin := config.GetOrigin(config.ForContext(ctx),
			"git.sr.ht", true)
		pusherInfo = fmt.Sprintf(
			"<a href='%s/%s'>%s</a>",
			gitOrigin,
			pusherCanonicalName,
			pusherCanonicalName)
	} else {
		pusherInfo = pusherCanonicalName
	}
	details := fmt.Sprintf(
		"%s pushed to <a href='%s'>%s/%s</a> git",
		pusherInfo, repoUrl,
		repoOwnerCanonicalName, repoName)
	detailsPlain := fmt.Sprintf("%s pushed to %s/%s git",
		pusherCanonicalName,
		pusherCanonicalName, repoName)
	event := tx.QueryRowContext(ctx, `
		INSERT INTO event(
			created, user_id, event_type,
			source_repo_id, external_source,
			external_summary, external_summary_plain,
			external_details, external_details_plain,
			external_url)
		VALUES(
			NOW() at time zone 'utc', $1, $2,
			$3, $4, $5, $6, $7, $8, $9
		)
		RETURNING id;
		`, eventUserID, "external_event", repoID,
		"git.sr.ht", summary,
		summaryPlain, details,
		detailsPlain, commitUrl)
	var existingEventID int
	if err := event.Scan(&existingEventID); err != nil {
		return err
	}
	return addEventProjectAssociation(ctx, tx, existingEventID, projectID)
}
