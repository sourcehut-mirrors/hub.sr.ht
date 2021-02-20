import email.utils
import json
import random
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
    if len(manifests) > 4:
        keys = list(manifests.keys())
        random.shuffle(keys)
        manifests = { key: manifests[key] for key in keys[:4] }

    ids = []

    version = payload["version"]
    if version == 1:
        version = ""
    else:
        version = f" v{version}"

    reply_to = payload.get("reply_to")
    if reply_to:
        submitter = email.utils.parseaddr(reply_to)
    else:
        submitter = email.utils.parseaddr(payload["submitter"])

    build_note = f"""[{subject}][0]{version} from [{submitter[0]}][1]

[0]: {ml.url()}/patches/{payload["id"]}
[1]: mailto:{submitter[1]}"""

    for key, value in manifests.items():
        tool_key = f"hub.sr.ht:builds.sr.ht:{key}"
        lists.patchset_set_tool(ml.owner, ml.name, payload["id"],
                tool_key, "pending", f"build pending: {key}")

        try:
            manifest = Manifest(yaml.safe_load(value))
        except:
            # TODO: Maybe we should email the user with the error details?
            return
        # TODO: https://todo.sr.ht/~sircmpwn/builds.sr.ht/291
        task = Task({
            "_apply_patch": f"""echo Applying patch from lists.sr.ht
git config --global user.name 'builds.sr.ht'
git config --global user.email builds@sr.ht
cd {repo.name}
curl -sS {ml.url()}/patches/{payload["id"]}/mbox >/tmp/{payload["id"]}.patch
git am -3 /tmp/{payload["id"]}.patch"""
        })
        manifest.tasks.insert(0, task)

        if not manifest.environment:
            manifest.environment = {}

        manifest.environment.setdefault("BUILD_SUBMITTER", "hub.sr.ht")
        manifest.environment.setdefault("BUILD_REASON", "patchset")
        manifest.environment.setdefault("PATCHSET_ID", payload["id"])
        manifest.environment.setdefault("PATCHSET_URL",
                f"{ml.url()}/patches/{payload['id']}")

        # Add webhook trigger
        root = get_origin("hub.sr.ht", external=True)
        details = fernet.encrypt(json.dumps({
            "mailing_list": ml.id,
            "patchset_id": payload["id"],
            "key": tool_key,
            "name": key,
            "user": project.owner.canonical_name,
        }).encode()).decode()
        manifest.triggers.append(Trigger({
            "action": TriggerAction.webhook,
            "condition": TriggerCondition.always,
            "url": root + url_for("webhooks.build_complete", details=details),
        }))

        b = builds.submit_build(project.owner, manifest, build_note,
            tags=[repo.name, "patches", key], execute=False)
        ids.append(b["id"])
        build_url = f"{buildsrht}/{project.owner.canonical_name}/job/{b['id']}"
        lists.patchset_set_tool(ml.owner, ml.name, payload["id"],
                tool_key, "waiting", f"[#{b['id']}]({build_url}) running {key}")

    trigger = Trigger({
        "action": TriggerAction.email,
        "condition": TriggerCondition.always,
    })
    trigger.attrs["to"] = email.utils.formataddr(submitter)
    trigger.attrs["cc"] = ml.posting_addr()
    trigger.attrs["in_reply_to"] = payload["message_id"]
    builds.create_group(project.owner, ids, build_note, [trigger.to_dict()])
    return ids
