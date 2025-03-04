package main

import (
	"git.sr.ht/~sircmpwn/core-go/config"
	"git.sr.ht/~sircmpwn/core-go/server"
	work "git.sr.ht/~sircmpwn/dowork"

	"git.sr.ht/~sircmpwn/hub.sr.ht/api/account"
	"git.sr.ht/~sircmpwn/hub.sr.ht/api/graph"
	"git.sr.ht/~sircmpwn/hub.sr.ht/api/graph/api"
)

func main() {
	appConfig := config.LoadConfig(":5114")

	gqlConfig := api.Config{Resolvers: &graph.Resolver{}}
	gqlConfig.Directives.Internal = server.Internal
	schema := api.NewExecutableSchema(gqlConfig)

	// TODO: Populate this after scopes have been added to the schema
	scopes := make([]string, 0)

	queueSize := config.GetInt(appConfig, "hub.sr.ht::api",
		"account-del-queue-size", config.DefaultQueueSize)
	accountQueue := work.NewQueue("account", queueSize)

	gsrv := server.NewServer("hub.sr.ht", appConfig).
		WithDefaultMiddleware().
		WithMiddleware(
			account.Middleware(accountQueue),
		).
		WithSchema(schema, scopes).
		WithQueues(accountQueue)

	gsrv.Run()
}
