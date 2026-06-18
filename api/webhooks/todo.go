package webhooks

import (
       "context"
       "database/sql"
       "encoding/json"
       "fmt"
       "html"
       "net/url"
       "strconv"
       "strings"

       "git.sr.ht/~sircmpwn/core-go/config"
       "git.sr.ht/~sircmpwn/core-go/database"
       "git.sr.ht/~sircmpwn/hub.sr.ht/api/graph"
       todo "git.sr.ht/~sircmpwn/hub.sr.ht/api/services/todo"
)

func ProcessTrackerUserWebhook(ctx context.Context, userID int, webhookPayload []byte) error {
       var body struct {
               Data struct {
                       Webhook todo.TrackerEvent `json:"webhook"`
               } `json:"data"`
       }
       if err := json.Unmarshal(webhookPayload, &body); err != nil {
               return err
       }

       tracker := body.Data.Webhook.Tracker
       switch body.Data.Webhook.Event {
       case todo.WebhookEventTrackerUpdate:
               return database.WithTx(ctx,
                       &sql.TxOptions{
                               Isolation: 0,
                               ReadOnly:  false,
                       },
                       func(tx *sql.Tx) error {
                               projects, err := tx.QueryContext(ctx, `
                                       UPDATE tracker
                                       SET
                                               name = $1,
                                               description = $2,
                                               visibility = $3,
                                               updated = NOW() at time zone 'utc'
                                       WHERE remote_rid = $4
                                       RETURNING project_id;`,
                                       tracker.Name, tracker.Description,
                                       tracker.Visibility, tracker.Rid)
                               if err != nil {
                                       return err
                               }
                               return refreshProjectsUpdated(ctx, tx, projects)
                       },
               )
       case todo.WebhookEventTrackerDeleted:
               return database.WithTx(ctx,
                       &sql.TxOptions{
                               Isolation: 0,
                               ReadOnly:  false,
                       }, func(tx *sql.Tx) error {
                               projects, err := tx.QueryContext(ctx, `
                                       DELETE FROM tracker
                                       WHERE remote_rid = $1
                                       RETURNING project_id;
                               `, tracker.Rid)
                               if err != nil {
                                       return err
                               }
                               return refreshProjectsUpdated(ctx, tx, projects)
                       },
               )
       default:
               panic(fmt.Errorf("unexpected event type: %s",
                       body.Data.Webhook.Event))
       }
}

func ProcessTrackerWebhook(ctx context.Context, trackerID int, webhookPayload []byte) error {
       var body struct {
               Data struct {
                       Webhook todo.WebhookPayload `json:"webhook"`
               } `json:"data"`
       }
       if err := json.Unmarshal(webhookPayload, &body); err != nil {
               return err
       }

       var submitter *todo.Entity
       switch event := body.Data.Webhook.Value.(type) {
       case *todo.TicketEvent:
               submitter = event.Ticket.Submitter
       case *todo.EventCreated:
               if event.NewEvent == nil {
                       return nil
               }
               var comments []*todo.Comment
               for _, change := range event.NewEvent.Changes {
                       if change.EventType == todo.EventTypeComment {
                               comments = append(comments, change.Value.(*todo.Comment))
                       }
               }
               if len(comments) != 1 {
                       return nil
               }
               submitter = comments[0].Author
       }
       if submitter == nil {
               return nil
       }
       submitterUserID, submitterURL := getSubmitterInfo(ctx, submitter)

       var (
               ticket *todo.Ticket
               action string
       )
       switch event := body.Data.Webhook.Value.(type) {
       case *todo.TicketEvent:
               ticket = event.Ticket
               action = "filed ticket"
       case *todo.EventCreated:
               ticket = event.NewEvent.Ticket
               action = "commented"
       }
       if ticket == nil {
               return nil
       }
       todoOrigin := config.GetOrigin(config.ForContext(ctx), "todo.sr.ht", true)
       ticketURL := fmt.Sprintf("%s/%s/%s/%d", todoOrigin,
               ticket.Tracker.Owner.CanonicalName,
               ticket.Tracker.Name, ticket.Id)
       externalSummary := fmt.Sprintf("<a href='%s'>#%d</a> %s",
               ticketURL, ticket.Id, html.EscapeString(ticket.Subject))
       externalSummaryPlain := fmt.Sprintf("#%d %s", ticket.Id, ticket.Subject)
       trackerURL := fmt.Sprintf("%s/%s/%s", todoOrigin,
               ticket.Tracker.Owner.CanonicalName,
               ticket.Tracker.Name)
       externalDetails := fmt.Sprintf("%s %s on <a href='%s'>%s</a> todo",
               submitterURL, action, trackerURL, ticket.Tracker.Name)
       externalDetailsPlain := fmt.Sprintf("%s %s on %s todo",
               submitter.CanonicalName, action, ticket.Tracker.Name)

       return database.WithTx(ctx,
               &sql.TxOptions{
                       Isolation: 0,
                       ReadOnly:  false,
               },
               func(tx *sql.Tx) error {
                       var eventUserID *int32
                       if submitterUserID != 0 {
                               eventUserID = &submitterUserID
                       }
                       var projectID int
                       tracker := tx.QueryRowContext(ctx, `
                               UPDATE tracker
                               SET updated = NOW() at time zone 'utc'
                               WHERE id = $1
                               RETURNING project_id`, trackerID)
                       if err := tracker.Scan(&projectID); err != nil {
                               return err
                       }
                       if err := refreshProjectUpdated(ctx, tx, projectID); err != nil {
                               return err
                       }
                       var eventID int
                       event := tx.QueryRowContext(ctx, `
                                       INSERT INTO event(
                                               created, user_id, event_type,
                                               tracker_id, external_source,
                                               external_summary, external_summary_plain,
                                               external_details, external_details_plain,
                                               external_url)
                                       VALUES(
                                               NOW() at time zone 'utc', $1, $2,
                                               $3, $4, $5, $6, $7, $8, $9
                                       )
                                       RETURNING id;
                               `, eventUserID, "external_event",
                               trackerID, "todo.sr.ht",
                               externalSummary, externalSummaryPlain,
                               externalDetails, externalDetailsPlain,
                               ticketURL)
                       if err := event.Scan(&eventID); err != nil {
                               return err
                       }
                       return addEventProjectAssociation(ctx, tx, eventID, projectID)
               },
       )
}

func handleTrailer(
       ctx context.Context, trailerName string, trailerValue string,
       actorName string, comment string, allowResolution bool,
) {
       if !graph.Features().Todo {
               return
       }
       switch trailerName {
       case "References", "Implements", "Fixes", "Closes":
       default:
               return
       }

       ticketURL, err := url.Parse(trailerValue)
       if err != nil {
               return
       }
       todoOrigin := config.GetOrigin(config.ForContext(ctx), "todo.sr.ht", true)
       todoURL, _ := url.Parse(todoOrigin)
       if ticketURL.Host != todoURL.Host {
               return
       }
       pathParts := strings.Split(ticketURL.Path, "/")
       if len(pathParts) != 4 {
               return
       }
       trackerOwner := pathParts[1][1:]
       trackerName := pathParts[2]
       ticketID, err := strconv.Atoi(pathParts[3])
       if err != nil {
               return
       }

       todoClient := graph.NewTodoClientForUser(ctx, actorName)
       comments, err := todo.GetTicketComments(
               todoClient, ctx,
               trackerOwner, trackerName, int32(ticketID),
       )
       if err != nil || comments.Tracker == nil || comments.Tracker.Ticket == nil {
               // Bail out in case of error or if the referenced tracker/ticket
               // does not exist.
               return
       }
       if comments.Tracker.Ticket.Events != nil {
               for _, evt := range comments.Tracker.Ticket.Events.Results {
                       for _, change := range evt.Changes {
                               switch t := change.Value.(type) {
                               case *todo.Comment:
                                       if t.Text == comment {
                                               // Don't add duplicate comments.
                                               return
                                       }
                               }
                       }
               }
       }

       var (
               resolution *todo.TicketResolution
               status     *todo.TicketStatus
       )
       if allowResolution {
               targetStatus := todo.TicketStatusResolved
               targetResolution := todo.TicketResolutionUnresolved
               switch trailerName {
               case "References":
               case "Implements":
                       targetResolution = todo.TicketResolutionImplemented
               case "Fixes":
                       targetResolution = todo.TicketResolutionFixed
               case "Closes":
                       targetResolution = todo.TicketResolutionClosed
               }

               if targetResolution != todo.TicketResolutionUnresolved {
                       status = &targetStatus
                       resolution = &targetResolution
               }
       }
       _, err = todo.SubmitComment(
               todoClient, ctx, comments.Tracker.Id, int32(ticketID),
               todo.SubmitCommentInput{
                       Text:       comment,
                       Status:     status,
                       Resolution: resolution,
               },
       )
       if err != nil && allowResolution && trailerName == "Closes" {
               // If the user attempted to resolve the ticket, they might not
               // have triage permissions, so retry commenting without
               // resolving.
               if err.Error() == "gqlclient: server failure: Access denied" {
                       todo.SubmitComment(
                               todoClient, ctx, comments.Tracker.Id, int32(ticketID),
                               todo.SubmitCommentInput{
                                       Text: comment,
                               },
                       )
               }
       }
}

func getSubmitterInfo(ctx context.Context, submitter *todo.Entity) (int32, string) {
       var (
               submitterUserID int32
               submitterURL    string
       )
       todoOrigin := config.GetOrigin(config.ForContext(ctx), "todo.sr.ht", true)
       switch s := submitter.Value.(type) {
       case *todo.User:
               submitterUserID = s.Id
               submitterURL = fmt.Sprintf("<a href='%s/%s'>%s</a>",
                       todoOrigin, s.CanonicalName, s.CanonicalName)
       case *todo.EmailAddress:
               linkLabel := html.EscapeString(s.Mailbox)
               if s.Name != nil {
                       linkLabel = html.EscapeString(*s.Name)
               }
               submitterURL = fmt.Sprintf(
                       "<a href='mailto:%s'>%s</a>",
                       html.EscapeString(s.Mailbox),
                       linkLabel,
               )
       case *todo.ExternalUser:
               submitterURL = html.EscapeString(s.ExternalId)
               if s.ExternalUrl != nil {
                       submitterURL = fmt.Sprintf(
                               "<a href='%s' rel='nofollow noopener'>%s</a>",
                               html.EscapeString(*s.ExternalUrl),
                               submitterURL,
                       )
               }
       }
       return submitterUserID, submitterURL
}
