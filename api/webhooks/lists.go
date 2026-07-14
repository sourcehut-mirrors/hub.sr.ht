package webhooks

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"html"
	"math/rand"
	"net/mail"
	"net/url"
	"strings"

	"git.sr.ht/~sircmpwn/core-go/config"
	"git.sr.ht/~sircmpwn/core-go/database"
	"git.sr.ht/~sircmpwn/hub.sr.ht/api/graph"
	builds "git.sr.ht/~sircmpwn/hub.sr.ht/api/services/builds"
	git "git.sr.ht/~sircmpwn/hub.sr.ht/api/services/git"
	lists "git.sr.ht/~sircmpwn/hub.sr.ht/api/services/lists"
)

func ProcessListsUserWebhook(ctx context.Context, userID int, webhookPayload []byte) error {
	var body struct {
		Data struct {
			Webhook lists.MailingListEvent `json:"webhook"`
		} `json:"data"`
	}
	if err := json.Unmarshal(webhookPayload, &body); err != nil {
		return err
	}

	list := body.Data.Webhook.List
	switch body.Data.Webhook.Event {
	case lists.WebhookEventListUpdated:
		return database.WithTx(ctx,
			&sql.TxOptions{
				Isolation: 0,
				ReadOnly:  false,
			},
			func(tx *sql.Tx) error {
				projects, err := tx.QueryContext(ctx, `
					UPDATE mailing_list
					SET
						name = $1,
						description = $2,
						visibility = $3,
						updated = NOW() at time zone 'utc'
					WHERE remote_rid = $4
					RETURNING project_id;
				`, list.Name, list.Description, list.Visibility, list.Rid)
				if err != nil {
					return err
				}
				return refreshProjectsUpdated(ctx, tx, projects)
			},
		)
	case lists.WebhookEventListDeleted:
		return database.WithTx(ctx,
			&sql.TxOptions{
				Isolation: 0,
				ReadOnly:  false,
			}, func(tx *sql.Tx) error {
				projects, err := tx.QueryContext(ctx, `
					DELETE FROM mailing_list
					WHERE remote_rid = $1
					RETURNING project_id;
				`, list.Rid)
				if err != nil {
					return err
				}
				return refreshProjectsUpdated(ctx, tx, projects)
			},
		)
	default:
		panic(fmt.Errorf("unexpected event type: %s", body.Data.Webhook.Event))
	}
}

func ProcessListsWebhook(ctx context.Context, listID int, webhookPayload []byte) error {
	var body struct {
		Data struct {
			Webhook lists.WebhookPayload `json:"webhook"`
		} `json:"data"`
	}
	if err := json.Unmarshal(webhookPayload, &body); err != nil {
		return err
	}

	switch body.Data.Webhook.Event {
	case lists.WebhookEventEmailReceived:
		email := body.Data.Webhook.Value.(*lists.EmailEvent).Email
		return processEmailReceivedEvent(ctx, listID, email)
	case lists.WebhookEventPatchsetReceived:
		patchset := body.Data.Webhook.Value.(*lists.PatchsetEvent).Patchset
		return processPatchsetReceivedEvent(ctx, listID, patchset)
	}
	return nil
}

func processEmailReceivedEvent(ctx context.Context, listID int, email *lists.Email) error {
	listsOrigin := config.GetOrigin(config.ForContext(ctx), "lists.sr.ht", true)
	listURL := fmt.Sprintf("%s/%s/%s", listsOrigin, email.List.Owner.CanonicalName, email.List.Name)
	messageID := fmt.Sprintf("<%s>", email.MessageID)
	archiveURL := fmt.Sprintf("%s/%s", listURL, url.QueryEscape(messageID))
	return database.WithTx(ctx,
		&sql.TxOptions{
			Isolation: 0,
			ReadOnly:  false,
		},
		func(tx *sql.Tx) error {
			var senderUserID int
			switch s := email.Sender.Value.(type) {
			case *lists.User:
				user := tx.QueryRowContext(ctx, `
					SELECT id FROM "user" u
					WHERE u.username = $1
					`, s.Username)
				if err := user.Scan(&senderUserID); err != nil {
					return err
				}
			}

			var projectID int
			ml := tx.QueryRowContext(ctx, `
				UPDATE mailing_list
				SET updated = NOW() at time zone 'utc'
				WHERE id = $1
				RETURNING project_id`, listID)
			if err := ml.Scan(&projectID); err != nil {
				return err
			}
			if err := refreshProjectUpdated(ctx, tx, projectID); err != nil {
				return err
			}

			existingEventID := dedupeEvent(ctx, tx, "lists.sr.ht",
				projectID, archiveURL, senderUserID)
			if existingEventID == 0 {
				summary := fmt.Sprintf("<a href='%s'>%s</a>",
					archiveURL, html.EscapeString(email.Subject))
				var senderInfo string
				if senderUserID != 0 {
					senderInfo = fmt.Sprintf(
						"<a href='%s/%s'>%s</a>",
						listsOrigin, email.Sender.CanonicalName,
						html.EscapeString(email.Sender.CanonicalName))
				} else {
					senderInfo = html.EscapeString(email.Sender.CanonicalName)
				}
				details := fmt.Sprintf("%s via <a href='%s'>%s</a>",
					senderInfo,
					listURL,
					email.List.Name)
				var eventUserID *int
				if senderUserID != 0 {
					eventUserID = &senderUserID
				}
				event := tx.QueryRowContext(ctx, `
					INSERT INTO event(
						created, user_id, event_type,
						mailing_list_id, external_source,
						external_summary, external_details,
						external_url)
					VALUES(
						NOW() at time zone 'utc', $1, $2,
						$3, $4, $5, $6, $7
					)
					RETURNING id;
				`, eventUserID, "external_event", listID,
					"lists.sr.ht", summary, details, archiveURL)
				if err := event.Scan(&existingEventID); err != nil {
					return err
				}
			}
			return addEventProjectAssociation(ctx, tx, existingEventID, projectID)
		},
	)
}

func processPatchsetTrailers(ctx context.Context, listName string,
	listOwnerCanonicalName string, patchset *lists.Patchset,
) {
	listsOrigin := config.GetOrigin(config.ForContext(ctx), "lists.sr.ht", true)
	listURL := fmt.Sprintf("%s/%s/%s", listsOrigin,
		listOwnerCanonicalName, listName)

	var userForTrailer string
	switch s := patchset.Submitter.Value.(type) {
	case *lists.User:
		userForTrailer = s.Username
	case *lists.Mailbox:
		userForTrailer = listOwnerCanonicalName[1:]
	}

	for _, email := range patchset.Patches.Results {
		subject := email.Subject
		var senderName string
		switch s := email.Sender.Value.(type) {
		case *lists.User:
			senderName = s.Username
		case *lists.Mailbox:
			senderName = s.Name
		}
		messageID := fmt.Sprintf("<%s>", email.MessageID)
		archiveURL := fmt.Sprintf("%s/patches/%d#%s", listURL,
			email.Patchset.Id, url.QueryEscape(messageID))
		comment := fmt.Sprintf(
			`<i>%s referenced this ticket in a patch:</i>

<a href="%s">%s</a>`,
			html.EscapeString(senderName), archiveURL,
			html.EscapeString(subject))
		if email.Patch != nil && len(email.Patch.Trailers) > 0 {
			for _, trailer := range email.Patch.Trailers {
				handleTrailer(ctx, trailer.Name, trailer.Value,
					userForTrailer, comment, false)
			}
		}
	}
}

func processPatchsetReceivedEvent(ctx context.Context, listID int,
	patchset *lists.Patchset,
) error {
	listName := patchset.List.Name
	listOwnerCanonicalName := patchset.List.Owner.CanonicalName

	processPatchsetTrailers(ctx, listName, listOwnerCanonicalName, patchset)

	buildsOrigin := config.GetOrigin(config.ForContext(ctx), "builds.sr.ht", true)
	if len(buildsOrigin) == 0 {
		return nil
	}
	var (
		repoID           int
		repoType         string
		repoOwnerName    string
		repoName         string
		repoVisibility   string
		projectID        int
		projectOwnerName string
	)
	if patchset.Prefix == nil {
		return nil
	}
	repoName = *patchset.Prefix
	if err := database.WithTx(ctx,
		&sql.TxOptions{
			Isolation: 0,
			ReadOnly:  false,
		},
		func(tx *sql.Tx) error {
			repo := tx.QueryRowContext(ctx, `
					SELECT
						r.id, u.username, r.repo_type,
						r.visibility, r.project_id,
						o.username
					FROM
						source_repo r, "user" u,
						project p, "user" o
					WHERE
						r.name = $1 AND
						r.owner_id = u.id AND
						r.project_id=p.id AND
						p.owner_id=o.id`, repoName)
			if err := repo.Scan(&repoID, &repoOwnerName, &repoType,
				&repoVisibility, &projectID, &projectOwnerName); err != nil {
				return err
			}
			if err := refreshProjectUpdated(ctx, tx, projectID); err != nil {
				return err
			}
			return nil
		},
	); err != nil {
		return err
	}
	if repoType != "GIT" {
		return nil
	}

	var jobIDs []int32
	manifests, err := git.GetManifests(
		graph.NewGitClientForUser(ctx, projectOwnerName), ctx,
		repoOwnerName, repoName,
	)
	if err != nil {
		return err
	}
	if len(manifests.Repository.Paths) == 0 {
		// The repository has no manifest
		return nil
	}
	sender, err := getSenderAddress(patchset)
	if err != nil {
		return err
	}
	version := ""
	if patchset.Version != 1 {
		version = fmt.Sprintf(" v%d", patchset.Version)
	}
	listsOrigin := config.GetOrigin(config.ForContext(ctx), "lists.sr.ht", true)
	listURL := fmt.Sprintf("%s/%s/%s", listsOrigin,
		patchset.List.Owner.CanonicalName, patchset.List.Name)
	buildNote := fmt.Sprintf(
		`[%s][0]%s from [%s][1]

[0]: %s/patches/%d
[1]: mailto:%s`,
		html.EscapeString(patchset.Subject), version,
		html.EscapeString(sender.Name), listURL, patchset.Id,
		html.EscapeString(sender.Address))
	buildsClient := graph.NewBuildsClientForUser(ctx, projectOwnerName)
	type manifestInfo struct {
		name     string
		contents string
	}
	var allManifests []manifestInfo
	for i := range manifests.Repository.Paths {
		var contents, manifestName string
		switch i {
		case 0: // .build.yml
			manifestName = ".build.yml"
			if manifests.Repository.Paths[i] != nil {
				contents = manifests.Repository.Paths[i].Object.Value.(*git.TextBlob).Text
			}
		case 1: // .build.yaml
			manifestName = ".build.yaml"
			if manifests.Repository.Paths[i] != nil {
				contents = manifests.Repository.Paths[i].Object.Value.(*git.TextBlob).Text
			}
		default: // .builds.*
			if manifests.Repository.Paths[i] != nil {
				tree := manifests.Repository.Paths[i].Object.Value.(*git.Tree)
				for _, entry := range tree.Entries.Results {
					name := entry.Name
					isYAML := strings.HasSuffix(name, ".yml") ||
						strings.HasSuffix(name, ".yaml")
					if !isYAML {
						continue
					}
					manifestName = name
					contents = entry.Object.Value.(*git.TextBlob).Text
				}
			}
		}

		if len(contents) == 0 {
			continue
		}
		allManifests = append(allManifests, manifestInfo{
			name:     manifestName,
			contents: contents,
		})
	}

	// Shuffle manifests to ensure a good distribution of coverage over
	// time time on repositories with more than the maximum number of
	// manifests.
	rand.Shuffle(len(allManifests), func(i, j int) {
		allManifests[i], allManifests[j] = allManifests[j], allManifests[i]
	})

	nManifests := 0
	for _, m := range allManifests {
		nManifests = nManifests + 1
		if nManifests > 4 {
			break
		}

		jobID := createJobForManifest(ctx, patchset, listID,
			m.name, m.contents,
			buildNote,
			projectOwnerName, repoName, repoVisibility)
		if jobID != nil {
			jobIDs = append(jobIDs, *jobID)
		}
	}

	messageID := patchset.Thread.Root.MessageID
	listPostingAddr := fmt.Sprintf("%s/%s", listOwnerCanonicalName, listName)
	triggerInputs := []builds.TriggerInput{
		builds.TriggerInput{
			Type:      builds.TriggerTypeEmail,
			Condition: builds.TriggerConditionAlways,
			Email: &builds.EmailTriggerInput{
				To:        sender.String(),
				Cc:        &listPostingAddr,
				InReplyTo: &messageID,
			},
		},
	}
	builds.CreateGroup(buildsClient, ctx, jobIDs,
		triggerInputs, buildNote)
	return nil
}

func getSenderAddress(patchset *lists.Patchset) (mail.Address, error) {
	var sender mail.Address
	if inReplyTo := patchset.Thread.Root.InReplyTo; inReplyTo != nil {
		addr, err := mail.ParseAddress(*inReplyTo)
		if err != nil {
			return sender, err
		}
		sender = *addr
	} else {
		var senderName, senderAddress string
		switch s := patchset.Submitter.Value.(type) {
		case *lists.User:
			senderName = s.Username
			senderAddress = s.Email
		case *lists.Mailbox:
			senderName = s.Name
			senderAddress = s.Address
		}
		sender = mail.Address{
			Name:    senderName,
			Address: senderAddress,
		}
	}
	return sender, nil
}

func createJobForManifest(ctx context.Context, patchset *lists.Patchset, listID int,
	manifestName string, manifestContents string,
	buildNote string,
	projectOwnerName string,
	repoName string, repoVisibility string,
) *int32 {
	listsClient := graph.NewListsClientForUser(ctx, projectOwnerName)
	manifest, err := ManifestFromYAML(manifestContents)
	if err != nil {
		lists.CreateTool(
			listsClient, ctx, patchset.Id,
			fmt.Sprintf("Failed to submit build: error parsing YAML: %s",
				err.Error()),
			lists.ToolIconFailed,
		)
		return nil
	}
	if manifest.Submitter != nil && manifest.Submitter.Hub != nil &&
		!manifest.Submitter.Hub.Enabled {
		return nil
	}

	tool, err := lists.CreateTool(
		listsClient, ctx, patchset.Id,
		fmt.Sprintf("build pending: %s", manifestName),
		lists.ToolIconPending)
	if err != nil {
		return nil
	}

	webhookDocument := fmt.Sprintf(`{
		"mailing_list": %d,
		"patchset_id": %d,
		"tool_id": %d,
		"name": "%s",
		"user": "~%s"
	}`, listID, patchset.Id, tool.Id, manifestName, projectOwnerName)
	manifest.UpdateForPatchset(ctx, projectOwnerName, patchset, webhookDocument)

	newManifest, err := manifest.ToYAML()
	if err != nil {
		return nil
	}

	vis := builds.Visibility(repoVisibility)
	startBuild := false
	buildsClient := graph.NewBuildsClientForUser(ctx, projectOwnerName)
	job, err := builds.SubmitBuild(
		buildsClient, ctx, newManifest, buildNote,
		[]string{repoName, "patches", manifestName},
		&startBuild,
		&vis)
	if err != nil {
		lists.UpdateTool(
			listsClient, ctx, tool.Id,
			fmt.Sprintf("Failed to submit build: %s", err),
			lists.ToolIconFailed,
		)
		return nil
	}
	buildsOrigin := config.GetOrigin(config.ForContext(ctx), "builds.sr.ht", true)
	buildURL := fmt.Sprintf("%s/~%s/job/%d", buildsOrigin,
		projectOwnerName, job.Id)
	waitingDetails := fmt.Sprintf("[#%d](%s) running %s", job.Id,
		buildURL, manifestName)
	lists.UpdateTool(
		listsClient, ctx, tool.Id, waitingDetails,
		lists.ToolIconWaiting,
	)

	return &job.Id
}
