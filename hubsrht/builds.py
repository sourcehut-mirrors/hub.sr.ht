import yaml
import email.utils
from srht.config import get_origin
from hubsrht.services import builds, git
from hubsrht.types import SourceRepo, RepoType
from sqlalchemy import func

def submit_patchset(ml, payload):
    if not get_origin("builds.sr.ht", default=None):
        return None
    from buildsrht.manifest import Manifest, Task
    from buildsrht.manifest import Trigger, TriggerAction, TriggerCondition

    project = ml.project
    subject = payload["subject"]
    prefix = payload["prefix"]
    # TODO: More sophisticated matching is possible
    # - test if patch is applicable to a repo; see the following:
    #   https://github.com/libgit2/pygit2/pull/1019
    # Will be useful for mailing lists shared by many repositories
    repo = (SourceRepo.query
            .filter(SourceRepo.project_id == project.id)
            .filter(func.lower(SourceRepo.name) == prefix.lower())).one_or_none()
    if repo.repo_type != RepoType.git:
        # TODO: support for hg.sr.ht
        return None
    manifests = git.get_manifests(repo.owner, repo.remote_id)
    if not manifests:
        return None
    # TODO: Add UI to lists.sr.ht indicating build status
    ids = []
    for key, value in manifests.items():
        manifest = Manifest(yaml.safe_load(value))
        # TODO: https://todo.sr.ht/~sircmpwn/builds.sr.ht/291
        task = Task({
            "_apply_patch": f"""echo Applying patch from lists.sr.ht
git config --global user.name 'builds.sr.ht'
git config --global user.email builds@sr.ht
cd {repo.name}
curl -s {ml.url()}/patches/{payload["id"]}/mbox >/tmp/{payload["id"]}.patch
git am -3 /tmp/{payload["id"]}.patch"""
        })
        manifest.tasks.insert(0, task)

        trigger = next((t for t in manifest.triggers
            if t.action == TriggerAction.email), None)
        if not trigger:
            trigger = Trigger({
                "action": TriggerAction.email,
                "condition": TriggerCondition.always,
            })
            manifest.triggers.append(trigger)
        trigger.condition = TriggerCondition.always

        addrs = email.utils.getaddresses(trigger.attrs.get("to", ""))
        submitter = email.utils.parseaddr(payload["submitter"])
        if submitter not in addrs:
            addrs.append(submitter)
        trigger.attrs["to"] = ", ".join([email.utils.formataddr(a) for a in addrs])

        cc = email.utils.getaddresses(trigger.attrs.get("cc", ""))
        if not ml.posting_addr() in cc:
            cc.append(('', ml.posting_addr()))
        trigger.attrs["cc"] = ", ".join([email.utils.formataddr(a) for a in cc])

        trigger.attrs["in_reply_to"] = payload["message_id"]

        version = payload["version"]
        if version == 1:
            version = ""
        else:
            version = f" v{version}"
        b = builds.submit_build(project.owner, manifest,
        f"""[{subject}][0]{version} from [{submitter[0]}][1]

[0]: {ml.url()}/patches/{payload["id"]}
[1]: mailto:{submitter[1]}""", tags=[repo.name, "patches", key])
        ids.append(b["id"])
    return ids
