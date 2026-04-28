package graph

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"git.sr.ht/~sircmpwn/core-go/auth"
	"git.sr.ht/~sircmpwn/core-go/client"
	"git.sr.ht/~sircmpwn/core-go/config"
	"git.sr.ht/~sircmpwn/core-go/crypto"
	gqlclient "git.sr.ht/~sircmpwn/gqlclient"
	"git.sr.ht/~sircmpwn/hub.sr.ht/api/graph/model"
	gitclient "git.sr.ht/~sircmpwn/hub.sr.ht/api/services/git"
	hgclient "git.sr.ht/~sircmpwn/hub.sr.ht/api/services/hg"
)

type httpTransport struct {
	ctx context.Context
}

func (tr *httpTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	req.Header.Add("User-Agent",
		fmt.Sprintf("%s -- SourceHut project hub (https://git.sr.ht/~sircmpwn/hub.sr.ht)",
			config.ServiceName(tr.ctx)))
	auth := client.InternalAuth{
		Name:     auth.ForContext(tr.ctx).Username,
		ClientID: config.ServiceName(tr.ctx),
		NodeID:   "hub.sr.ht",
	}
	authBlob, err := json.Marshal(&auth)
	if err != nil {
		panic(err) // Programmer error
	}
	req.Header.Add("Authorization", fmt.Sprintf("Internal %s",
		crypto.Encrypt(authBlob)))

	return http.DefaultTransport.RoundTrip(req)
}

func newGQLClient(ctx context.Context, service string) *gqlclient.Client {
	conf := config.ForContext(ctx)

	apiOrigin := config.GetAPI(conf, service, false)

	var (
		timeout time.Duration
		err error
	)
	if to, ok := conf.Get(fmt.Sprintf("%s::api", service), "max-duration"); ok {
		timeout, err = time.ParseDuration(to)
		if err != nil {
			panic(err)
		}
	} else {
		timeout = 3 * time.Second
	}

	return gqlclient.New(apiOrigin+"/query",
		&http.Client{
			Transport: &httpTransport{
				ctx: ctx,
			},
			Timeout: timeout,
		},
	)
}

func NewListsGQLClient(ctx context.Context) *gqlclient.Client {
	return newGQLClient(ctx, LISTS_SERVICE)
}

func NewGitGQLClient(ctx context.Context) *gqlclient.Client {
	return newGQLClient(ctx, GIT_SERVICE)
}

func NewHgGQLClient(ctx context.Context) *gqlclient.Client {
	return newGQLClient(ctx, HG_SERVICE)
}

func NewTodoGQLClient(ctx context.Context) *gqlclient.Client {
	return newGQLClient(ctx, TODO_SERVICE)
}

var features *model.Features

func Features() model.Features {
	if features == nil {
		conf := config.LoadConfig()
		features = &model.Features{
			Lists: len(config.GetOrigin(conf, LISTS_SERVICE, true)) > 0,
			Git:   len(config.GetOrigin(conf, GIT_SERVICE, true)) > 0,
			Hg:    len(config.GetOrigin(conf, HG_SERVICE, true)) > 0,
			Todo:  len(config.GetOrigin(conf, TODO_SERVICE, true)) > 0,
		}
	}
	return *features
}

type RepoWrapper struct {
	gitRepo *gitclient.Repository
	hgRepo  *hgclient.Repository
}

func NewRepoWrapper(git *gitclient.Repository, hg *hgclient.Repository) (*RepoWrapper, error) {
	if (git == nil && hg == nil) || (git != nil && hg != nil) {
		return nil, fmt.Errorf("exactly one actual repository required")
	}
	return &RepoWrapper {
		gitRepo: git,
		hgRepo:  hg,
	}, nil
}

func (repo *RepoWrapper) RepoType() string {
	if repo.gitRepo != nil {
		return "GIT"
	}
	return "HG"
}

func (repo *RepoWrapper) ID() int32 {
	if repo.gitRepo != nil {
		return (*repo.gitRepo).Id
	}
	return (*repo.hgRepo).Id
}

func (repo *RepoWrapper) RID() string {
	if repo.gitRepo != nil {
		return (*repo.gitRepo).Rid
	}
	return (*repo.hgRepo).Rid
}

func (repo *RepoWrapper) Name() string {
	if repo.gitRepo != nil {
		return (*repo.gitRepo).Name
	}
	return (*repo.hgRepo).Name
}

func (repo *RepoWrapper) Description() *string {
	if repo.gitRepo != nil {
		return (*repo.gitRepo).Description
	}
	return (*repo.hgRepo).Description
}

func (repo *RepoWrapper) Visibility() string {
	if repo.gitRepo != nil {
		return string((*repo.gitRepo).Visibility)
	}
	return string((*repo.hgRepo).Visibility)
}
