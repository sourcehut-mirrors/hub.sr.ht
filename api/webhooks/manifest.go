package webhooks

import (
	"bytes"
	"context"
	"fmt"
	"regexp"
	"strings"

	builds "git.sr.ht/~sircmpwn/builds.sr.ht/api"
	"git.sr.ht/~sircmpwn/core-go/config"
	"git.sr.ht/~sircmpwn/core-go/crypto"
	lists "git.sr.ht/~sircmpwn/hub.sr.ht/api/services/lists"
	"github.com/goccy/go-yaml"
)

type HubSubmitter struct {
	Enabled bool `yaml:"enabled,omitempty"`
}

type Submitter struct {
	Hub *HubSubmitter `yaml:"hub.sr.ht,omitempty"`
}

type Manifest struct {
	builds.Manifest
	Submitter *Submitter `yaml:"submitter,omitempty"`
}

func ManifestFromYAML(src string) (Manifest, error) {
	var m Manifest
	if err := yaml.Unmarshal([]byte(src), &m.Manifest); err != nil {
		return m, err
	}
	if err := yaml.Unmarshal([]byte(src), &m); err != nil {
		return m, err
	}
	// XXX: We could do validation here, but builds.sr.ht will also catch it
	// for us later so it's not especially important to
	return m, nil
}

func (manifest Manifest) ToYAML() (string, error) {
	var buf bytes.Buffer
	enc := yaml.NewEncoder(&buf, yaml.UseLiteralStyleIfMultiline(true))
	err := enc.Encode(&manifest.Manifest)
	if err != nil {
		return "", err
	}
	if manifest.Submitter != nil {
		err = enc.Encode(&manifest.Submitter)
		if err != nil {
			return "", err
		}
	}
	return buf.String(), nil
}

func (manifest *Manifest) UpdateForPatchset(ctx context.Context,
	projectOwner string, patchset *lists.Patchset,
	webhookDoc string,
) {
	if manifest.Environment == nil {
		manifest.Environment = make(map[string]any)
	}
	listsOrigin := config.GetOrigin(config.ForContext(ctx), "lists.sr.ht", true)
	listURL := fmt.Sprintf("%s/%s/%s", listsOrigin,
		patchset.List.Owner.CanonicalName, patchset.List.Name)
	manifest.Environment["BUILD_SUBMITTER"] = "hub.sr.ht"
	manifest.Environment["BUILD_REASON"] = "patchset"
	manifest.Environment["PATCHSET_ID"] = patchset.Id
	manifest.Environment["PATCHSET_URL"] = fmt.Sprintf("%s/patches/%d",
		listURL, patchset.Id)

	script := generateApplyCommand(ctx, patchset)
	manifest.Tasks = append(
		[]builds.Task{builds.Task{
			Name:   "_apply_patch",
			Script: script,
		}},
		manifest.Tasks...,
	)

	details := crypto.Encrypt([]byte(webhookDoc))
	hubOrigin := config.GetAPI(config.ForContext(ctx), "hub.sr.ht", false)
	detailsUrl := fmt.Sprintf("%s/query/build-complete/%s",
		hubOrigin, details)
	manifest.Triggers = append(
		manifest.Triggers,
		builds.Trigger{
			Action:    "webhook",
			Condition: "always",
			Url:       &detailsUrl,
		},
	)
}

var shunsafe = regexp.MustCompile(`[^\w@%+=:,./-]`)

func shQuote(s string) string {
	// Algorithm aped from shlex.py
	if s == "" {
		return "''"
	}
	if !shunsafe.MatchString(s) {
		return s
	}
	return "'" + strings.ReplaceAll(s, "'", "'\"'\"'") + "'"
}

func generateApplyCommand(ctx context.Context, patchset *lists.Patchset) string {
	listsOrigin := config.GetOrigin(config.ForContext(ctx), "lists.sr.ht", true)
	listURL := fmt.Sprintf("%s/%s/%s", listsOrigin,
		patchset.List.Owner.CanonicalName, patchset.List.Name)

	prefix := ""
	if patchset.Prefix != nil {
		prefix = *patchset.Prefix
	}

	patchMbox := fmt.Sprintf("%s/patches/%d/mbox", listURL, patchset.Id)
	return fmt.Sprintf(`curl -sS '%s' >/tmp/patch
git -C %s am -3 /tmp.patch
`,
		shQuote(patchMbox),
		shQuote(prefix))
}
