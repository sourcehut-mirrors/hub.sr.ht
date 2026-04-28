package graph

import (
	"context"
	"database/sql"
	"fmt"

	"git.sr.ht/~sircmpwn/core-go/auth"
	"git.sr.ht/~sircmpwn/core-go/config"
	gitclient "git.sr.ht/~sircmpwn/hub.sr.ht/api/services/git"
	hgclient "git.sr.ht/~sircmpwn/hub.sr.ht/api/services/hg"
	listsclient "git.sr.ht/~sircmpwn/hub.sr.ht/api/services/lists"
	todoclient "git.sr.ht/~sircmpwn/hub.sr.ht/api/services/todo"
)

type ResourceType int

const (
	MailingList ResourceType = iota
	GitRepository
	HgRepository
	Tracker
)

const (
	LISTS_SERVICE = "lists.sr.ht"
	GIT_SERVICE   = "git.sr.ht"
	HG_SERVICE    = "hg.sr.ht"
	TODO_SERVICE  = "todo.sr.ht"

	GIT_WEBHOOK_VERSION   = 3
	HG_WEBHOOK_VERSION    = 2
	LISTS_WEBHOOK_VERSION = 6
	TODO_WEBHOOK_VERSION  = 2
)

func getTypeForWebhook(resType ResourceType) string {
	switch resType {
	case MailingList:
		return "mailing-list"
	case GitRepository:
		return "git-repo"
	case HgRepository:
		return "hg-repo"
	case Tracker:
		return "todo-tracker"
	default:
		panic(fmt.Sprintf("Unexpected resource type %T!\n", resType))
	}
}

func getTypeForUserWebhook(resType ResourceType) string {
	switch resType {
	case MailingList:
		return "mailing-list-user"
	case GitRepository:
		return "git-user"
	case HgRepository:
		return "hg-user"
	case Tracker:
		return "todo-user"
	default:
		panic(fmt.Sprintf("Unexpected resource type %T!\n", resType))
	}
}

func GetWebhookURL(ctx context.Context, resType ResourceType, id int) string {
	return fmt.Sprintf("%s/webhooks/gql/%s/%d",
		config.GetOrigin(config.ForContext(ctx),
			"hub.sr.ht",
			false,
		),
		getTypeForWebhook(resType),
		id)
}

func getUserWebhookURL(ctx context.Context, resType ResourceType) string {
	return fmt.Sprintf("%s/webhooks/gql/%s/%d",
		config.GetOrigin(config.ForContext(ctx),
			"hub.sr.ht",
			false,
		),
		getTypeForUserWebhook(resType),
		auth.ForContext(ctx).UserID)
}

func CreateListUserWebhook(ctx context.Context) (int32, error) {
	sub, err := listsclient.CreateUserWebhook(
		NewListsGQLClient(ctx),
		ctx, listsclient.EventWebhookQuery,
		getUserWebhookURL(ctx, MailingList),
	)
	if err != nil {
		return 0, err
	}
	return sub.Id, nil
}

func CreateGitUserWebhook(ctx context.Context) (int32, error) {
	sub, err := gitclient.CreateUserWebhook(
		NewGitGQLClient(ctx),
		ctx, gitclient.EventWebhookQuery,
		getUserWebhookURL(ctx, GitRepository),
	)
	if err != nil {
		return 0, err
	}
	return sub.Id, nil
}

func CreateHgUserWebhook(ctx context.Context) (int32, error) {
	sub, err := hgclient.CreateUserWebhook(
		NewHgGQLClient(ctx),
		ctx, hgclient.EventWebhookQuery,
		getUserWebhookURL(ctx, HgRepository),
	)
	if err != nil {
		return 0, err
	}
	return sub.Id, nil
}

func CreateTrackerUserWebhook(ctx context.Context) (int32, error) {
	sub, err := todoclient.CreateUserWebhook(
		NewTodoGQLClient(ctx),
		ctx, todoclient.EventWebhookQuery,
		getUserWebhookURL(ctx, Tracker),
	)
	if err != nil {
		return 0, err
	}
	return sub.Id, nil
}

type userWebhook struct {
	ID                  int
	UserID              int
	GitWebhookID        *int
	GitWebhookVersion   *int
	HgWebhookID         *int
	HgWebhookVersion    *int
	ListsWebhookID      *int
	ListsWebhookVersion *int
	TodoWebhookID       *int
	TodoWebhookVersion  *int
}

func isUserWebhookSetup(uwh userWebhook, resType ResourceType) bool {
	return (resType == MailingList && uwh.ListsWebhookID != nil) ||
		(resType == GitRepository && uwh.GitWebhookID != nil) ||
		(resType == HgRepository && uwh.HgWebhookID != nil) ||
		(resType == Tracker && uwh.TodoWebhookID != nil)
}

func SetupUserWebhook(
	ctx context.Context,
	tx *sql.Tx,
	resType ResourceType,
	createWebHook func(ctx context.Context) (int32, error),
) error {
	var uwh userWebhook
	uwhRow := tx.QueryRowContext(ctx, `
		SELECT git_webhook_id, hg_webhook_id,
		       lists_webhook_id, todo_webhook_id
		FROM user_webhooks WHERE user_id = $1
		`, auth.ForContext(ctx).UserID)
	err := uwhRow.Scan(&uwh.GitWebhookID, &uwh.HgWebhookID,
		&uwh.ListsWebhookID, &uwh.TodoWebhookID)
	if err != nil && err != sql.ErrNoRows {
		return err
	}

	if !isUserWebhookSetup(uwh, resType) {
		uwhID, err := createWebHook(ctx)
		if err != nil {
			return err
		}
		var (
			colPrefix string
			whVersion int
		)
		switch resType {
		case MailingList:
			colPrefix = "lists"
			whVersion = LISTS_WEBHOOK_VERSION
		case GitRepository:
			colPrefix = "git"
			whVersion = GIT_WEBHOOK_VERSION
		case HgRepository:
			colPrefix = "hg"
			whVersion = HG_WEBHOOK_VERSION
		case Tracker:
			colPrefix = "todo"
			whVersion = TODO_WEBHOOK_VERSION
		default:
			panic(fmt.Sprintf("Unexpected resource type %T!\n", resType))
		}
		row := tx.QueryRowContext(ctx, fmt.Sprintf(`
			INSERT INTO user_webhooks (
				user_id, %s_webhook_id, %s_webhook_version
			) VALUES (
				$1, $2, $3
			)
			ON CONFLICT ON CONSTRAINT user_webhooks_user_id_key
			DO UPDATE SET %s_webhook_id = $2, %s_webhook_version = $3
			RETURNING id;`,
			colPrefix, colPrefix, colPrefix, colPrefix),
			auth.ForContext(ctx).UserID, uwhID, whVersion)
		var ID int
		if err := row.Scan(&ID); err != nil {
			return err
		}
	}
	return nil
}

func collectWebhookIDs(ctx context.Context, tx *sql.Tx, projectID int, resType ResourceType) ([]int, error) {
	var (
		tableName string
		ret       []int
	)
	switch resType {
	case MailingList:
		tableName = "mailing_list"
	case GitRepository:
		tableName = "source_repo"
	case Tracker:
		tableName = "tracker"
	default:
		panic(fmt.Sprintf("Unexpected resource type %T!\n", resType))
	}
	lists, err := tx.QueryContext(ctx, fmt.Sprintf(`
		SELECT webhook_id FROM %s
		WHERE project_id = $1 AND owner_id = $2 AND webhook_id != 0
	`, tableName), projectID, auth.ForContext(ctx).UserID)
	if err != nil && err != sql.ErrNoRows {
		return nil, err
	}
	defer lists.Close()
	for lists.Next() {
		var whID int
		if err := lists.Scan(&whID); err != nil {
			continue
		}
		ret = append(ret, whID)
	}
	return ret, nil
}
