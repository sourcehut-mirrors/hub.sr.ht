//go:build generate
// +build generate

package services

import (
	_ "git.sr.ht/~sircmpwn/gqlclient/cmd/gqlclientgen"
)

//go:generate go run git.sr.ht/~sircmpwn/gqlclient/cmd/gqlclientgen -a -n gql_lists_gen -s $ASSETS/lists.sr.ht.graphqls -q lists/queries.graphql -o lists/gql.go
//go:generate go run git.sr.ht/~sircmpwn/gqlclient/cmd/gqlclientgen -a -n gql_git_gen -s $ASSETS/git.sr.ht.graphqls -q git/queries.graphql -o git/gql.go
//go:generate go run git.sr.ht/~sircmpwn/gqlclient/cmd/gqlclientgen -a -n gql_hg_gen -s $ASSETS/hg.sr.ht.graphqls -q hg/queries.graphql -o hg/gql.go
//go:generate go run git.sr.ht/~sircmpwn/gqlclient/cmd/gqlclientgen -a -n gql_todo_gen -s $ASSETS/todo.sr.ht.graphqls -q todo/queries.graphql -o todo/gql.go
