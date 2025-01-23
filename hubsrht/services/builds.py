import yaml
from hubsrht.services import SrhtService
from srht.config import get_origin, cfg

_buildsrht = get_origin("builds.sr.ht", default=None)
_buildsrht_api = cfg("builds.sr.ht", "api-origin", default=None) or _buildsrht

class BuildService(SrhtService):
    def __init__(self):
        super().__init__("builds.sr.ht")

    def submit_build(self, user, manifest, note, tags, execute=True, valid=None, visibility=None):
        resp = self.exec(user, """
        mutation SubmitBuild(
            $manifest: String!,
            $note: String,
            $tags: [String!],
            $secrets: Boolean,
            $execute: Boolean,
            $visibility: Visibility,
        ) {
            submit(
                manifest: $manifest,
                note: $note,
                tags: $tags,
                secrets: $secrets,
                execute: $execute,
                visibility: $visibility,
            ) {
                id
            }
        }
        """, **{
            "manifest": yaml.dump(manifest.to_dict(), default_flow_style=False),
            "tags": tags,
            "note": note,
            "secrets": False,
            "execute": execute,
            "visibility": visibility.value if visibility else None,
        })
        return resp["submit"]

    def create_group(self, user, job_ids, note, triggers, valid=None):
        return self.exec(user, """
        mutation CreateGroup(
            $jobIds: [Int!]!,
            $triggers: [TriggerInput!]!,
            $note: String!,
        ) {
            createGroup(jobIds: $jobIds, triggers: $triggers, note: $note) {
                id
            }
        }
        """, jobIds=job_ids, note=note, triggers=triggers, valid=valid)
