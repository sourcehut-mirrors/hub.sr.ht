import email.utils
import json
import yaml
from flask import url_for
from hubsrht.services import builds, git, lists
from hubsrht.types import SourceRepo, RepoType
from sqlalchemy import func
from srht.config import get_origin
from srht.crypto import fernet

def submit_patchset(ml, payload):
    buildsrht = get_origin("builds.sr.ht", external=True, default=None)
    if not buildsrht:
        return None
    from buildsrht.manifest import Manifest, Task
    from buildsrht.manifest import Trigger, TriggerAction, TriggerCondition

    project = ml.project
    subject = payload["subject"]

    prefix = payload["prefix"]
    if not prefix:
        # TODO: More sophisticated matching is possible
        # - test if patch is applicable to a repo; see the following:
        #   https://github.com/libgit2/pygit2/pull/1019
        # Will be useful for mailing lists shared by many repositories
        return None

    repo = (SourceRepo.query
            .filter(SourceRepo.project_id == project.id)
            .filter(func.lower(SourceRepo.name) == prefix.lower())).one_or_none()
    if not repo:
        return None
    if repo.repo_type != RepoType.git:
        # TODO: support for hg.sr.ht
        return None
    manifests = git.get_manifests(repo.owner, repo.remote_id)
    if not manifests:
        return None
    ids = []
    for key, value in manifests.items():
        tool_key = f"hub.sr.ht:builds.sr.ht:{key}"
        lists.patchset_set_tool(ml.owner, ml.name, payload["id"],
                tool_key, "pending", f"build pending: {key}")

        manifest = Manifest(yaml.safe_load(value))
        # TODO: https://todo.sr.ht/~sircmpwn/builds.sr.ht/291
        task = Task({
            "_apply_patch": f"""echo Applying patch from lists.sr.ht
git config --global user.name 'builds.sr.ht'
git config --global user.email builds@sr.ht
cd {repo.name}
curl --no-progress-meter {ml.url()}/patches/{payload["id"]}/mbox >/tmp/{payload["id"]}.patch
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

        root = get_origin("hub.sr.ht", external=True)
        details = fernet.encrypt(json.dumps({
            "mailing_list": ml.id,
            "patchset_id": payload["id"],
            "key": tool_key,
            "name": key,
        }).encode()).decode()
        manifest.triggers.append(Trigger({
            "action": TriggerAction.webhook,
            "condition": TriggerCondition.always,
            "url": root + url_for("webhooks.build_complete", details=details),
        }))

        addrs = email.utils.getaddresses(trigger.attrs.get("to", ""))
        reply_to = payload.get("reply_to")
        if reply_to:
            submitter = email.utils.parseaddr(reply_to)
        else:
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
        build_url = f"{buildsrht}/{project.owner.canonical_name}/job/{b['id']}"
        lists.patchset_set_tool(ml.owner, ml.name, payload["id"],
                tool_key, "waiting", f"[#{b['id']}]({build_url}) running {key}")
    return ids
