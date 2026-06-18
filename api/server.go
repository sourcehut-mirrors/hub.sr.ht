package main

import (
	"context"
	"io"
	"net/http"
	"os"
	"strconv"

	"git.sr.ht/~sircmpwn/core-go/config"
	"git.sr.ht/~sircmpwn/core-go/server"
	work "git.sr.ht/~sircmpwn/dowork"
	"github.com/99designs/gqlgen/graphql"

	"git.sr.ht/~sircmpwn/hub.sr.ht/api/account"
	"git.sr.ht/~sircmpwn/hub.sr.ht/api/graph"
	"git.sr.ht/~sircmpwn/hub.sr.ht/api/graph/api"
	"git.sr.ht/~sircmpwn/hub.sr.ht/api/graph/model"
	"git.sr.ht/~sircmpwn/hub.sr.ht/api/loaders"
	"git.sr.ht/~sircmpwn/hub.sr.ht/api/webhooks"
	"github.com/go-chi/chi/v5"
)

func main() {
	appConfig := config.LoadConfig()

	gqlConfig := api.Config{Resolvers: &graph.Resolver{}}
	gqlConfig.Directives.Internal = server.Internal
	gqlConfig.Directives.Access = func(ctx context.Context, obj any,
		next graphql.Resolver, scope model.AccessScope,
		kind model.AccessKind) (any, error) {
		return server.Access(ctx, obj, next, scope.String(), kind.String())
	}
	schema := api.NewExecutableSchema(gqlConfig)

	scopes := make([]string, len(model.AllAccessScope))
	for i, s := range model.AllAccessScope {
		scopes[i] = s.String()
	}

	accountQueueSize := config.GetInt(appConfig, "hub.sr.ht::api",
		"account-del-queue-size", config.DefaultQueueSize)
	accountQueue := work.NewQueue("account", accountQueueSize)

	projectQueueSize := config.GetInt(appConfig, "hub.sr.ht::api",
		"project-del-queue-size", config.DefaultQueueSize)
	projectQueue := work.NewQueue("project", projectQueueSize)

	gsrv := server.New("hub.sr.ht", ":5114", appConfig, os.Args).
		WithDefaultMiddleware().
		WithMiddleware(
			loaders.Middleware,
			account.Middleware(accountQueue),
			graph.ProjectMiddleware(projectQueue),
		).
		WithSchema(schema, scopes).
		WithQueues(accountQueue, projectQueue)

	gsrv.WebhookRouter().Post("/query/mailing-list-user/{id}", func(w http.ResponseWriter, r *http.Request) {
		userID, err := strconv.Atoi(chi.URLParam(r, "id"))
		if err != nil {
			w.WriteHeader(http.StatusBadRequest)
			w.Write([]byte("Invalid user ID\r\n"))
			return
		}

		bodyBytes, _ := io.ReadAll(r.Body)
		defer r.Body.Close()
		err = webhooks.ProcessListsUserWebhook(r.Context(), userID, bodyBytes)
		if err != nil {
			w.WriteHeader(http.StatusBadRequest)
		} else {
			w.WriteHeader(http.StatusOK)
		}
	})

	gsrv.WebhookRouter().Post("/query/mailing-list/{id}", func(w http.ResponseWriter, r *http.Request) {
		listID, err := strconv.Atoi(chi.URLParam(r, "id"))
		if err != nil {
			w.WriteHeader(http.StatusBadRequest)
			w.Write([]byte("Invalid mailing list ID\r\n"))
			return
		}

		bodyBytes, _ := io.ReadAll(r.Body)
		defer r.Body.Close()
		err = webhooks.ProcessListsWebhook(r.Context(), listID, bodyBytes)
		if err != nil {
			w.WriteHeader(http.StatusBadRequest)
		} else {
			w.WriteHeader(http.StatusOK)
		}
	})

	gsrv.WebhookRouter().Post("/query/git-user/{id}", func(w http.ResponseWriter, r *http.Request) {
		processRepoUserWebhook(w, r, "GIT")
	})
	gsrv.WebhookRouter().Post("/query/hg-user/{id}", func(w http.ResponseWriter, r *http.Request) {
		processRepoUserWebhook(w, r, "HG")
	})

	gsrv.WebhookRouter().Post("/query/git-repo/{id}", func(w http.ResponseWriter, r *http.Request) {
		repoID, err := strconv.Atoi(chi.URLParam(r, "id"))
		if err != nil {
			w.WriteHeader(http.StatusBadRequest)
			w.Write([]byte("Invalid repository ID\r\n"))
			return
		}

		bodyBytes, _ := io.ReadAll(r.Body)
		defer r.Body.Close()
		err = webhooks.ProcessGitRepoWebhook(r.Context(), repoID, bodyBytes)
		if err != nil {
			w.WriteHeader(http.StatusBadRequest)
		} else {
			w.WriteHeader(http.StatusOK)
		}
	})

	gsrv.WebhookRouter().Post("/query/todo-user/{id}", func(w http.ResponseWriter, r *http.Request) {
		userID, err := strconv.Atoi(chi.URLParam(r, "id"))
		if err != nil {
			w.WriteHeader(http.StatusBadRequest)
			w.Write([]byte("Invalid user ID\r\n"))
			return
		}

		bodyBytes, _ := io.ReadAll(r.Body)
		defer r.Body.Close()
		err = webhooks.ProcessTrackerUserWebhook(r.Context(), userID, bodyBytes)
		if err != nil {
			w.WriteHeader(http.StatusBadRequest)
		} else {
			w.WriteHeader(http.StatusOK)
		}
	})

	gsrv.WebhookRouter().Post("/query/todo-tracker/{id}", func(w http.ResponseWriter, r *http.Request) {
		trackerID, err := strconv.Atoi(chi.URLParam(r, "id"))
		if err != nil {
			w.WriteHeader(http.StatusBadRequest)
			w.Write([]byte("Invalid repository ID\r\n"))
			return
		}

		bodyBytes, _ := io.ReadAll(r.Body)
		defer r.Body.Close()
		err = webhooks.ProcessTrackerWebhook(r.Context(), trackerID, bodyBytes)
		if err != nil {
			w.WriteHeader(http.StatusBadRequest)
		} else {
			w.WriteHeader(http.StatusOK)
		}
	})

	gsrv.WebhookRouter().Post(
		"/query/build-complete/{details}",
		webhooks.ProcessBuildCompleteWebhook,
	)

	gsrv.Run()
}

func processRepoUserWebhook(w http.ResponseWriter, r *http.Request, t string) {
	userID, err := strconv.Atoi(chi.URLParam(r, "id"))
	if err != nil {
		w.WriteHeader(http.StatusBadRequest)
		w.Write([]byte("Invalid user ID\r\n"))
		return
	}

	bodyBytes, _ := io.ReadAll(r.Body)
	defer r.Body.Close()
	err = webhooks.ProcessSourceRepoUserWebhook(r.Context(), userID, t, bodyBytes)
	if err != nil {
		w.WriteHeader(http.StatusBadRequest)
	} else {
		w.WriteHeader(http.StatusOK)
	}
}
