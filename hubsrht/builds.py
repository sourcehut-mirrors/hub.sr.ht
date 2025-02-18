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
from srht.graphql import GraphQLError

def submit_patchset(ml, payload, valid=None):
    buildsrht = get_origin("builds.sr.ht", external=True, default=None)
    if not buildsrht:
        return None
    from buildsrht.manifest import Manifest, Task
    from buildsrht.manifest import Trigger, TriggerAction, TriggerCondition

    project = ml.project

    patch_id = payload["id"]
    patch_url = f"{ml.url()}/patches/{patch_id}"
    patch_mbox = f"{ml.url()}/patches/{patch_id}/mbox"
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
    manifests = git.get_manifests(repo.owner, repo.name)
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

    message_id = payload["thread"]["root"]["messageID"]
    reply_to = payload["thread"]["root"]["reply_to"]
    if reply_to:
        submitter = email.utils.parseaddr(reply_to)
    else:
        name = payload["submitter"]["name"]
        address = payload["submitter"]["address"]
        submitter = (name, address)

    build_note = f"""[{subject}][0]{version} from [{submitter[0]}][1]

[0]: {ml.url()}/patches/{patch_id}
[1]: mailto:{submitter[1]}"""

    for key, value in manifests.items():
        tool_id = lists.patchset_create_tool(ml.owner, patch_id,
                "PENDING", f"build pending: {key}")

        manifest = Manifest(yaml.safe_load(value))
        # TODO: https://todo.sr.ht/~sircmpwn/builds.sr.ht/291
        task = Task({
            "_apply_patch": f"""echo Applying patch from lists.sr.ht
git config --global user.name 'builds.sr.ht'
git config --global user.email builds@sr.ht
cd {repo.name}
curl -sS {patch_mbox} >/tmp/{patch_id}.patch
git am -3 /tmp/{patch_id}.patch"""
        })
        manifest.tasks.insert(0, task)

        if not manifest.environment:
            manifest.environment = {}

        manifest.environment.setdefault("BUILD_SUBMITTER", "hub.sr.ht")
        manifest.environment.setdefault("BUILD_REASON", "patchset")
        manifest.environment.setdefault("PATCHSET_ID", patch_id)
        manifest.environment.setdefault("PATCHSET_URL", patch_url)

        # Add webhook trigger
        root = get_origin("hub.sr.ht", external=True)
        details = fernet.encrypt(json.dumps({
            "mailing_list": ml.id,
            "patchset_id": patch_id,
            "tool_id": tool_id,
            "name": key,
            "user": project.owner.canonical_name,
        }).encode()).decode()
        manifest.triggers.append(Trigger({
            "action": TriggerAction.webhook,
            "condition": TriggerCondition.always,
            "url": root + url_for("webhooks.build_complete", details=details),
        }))

        try:
            b = builds.submit_build(project.owner, manifest, build_note,
                tags=[repo.name, "patches", key], execute=False, valid=valid,
                visibility=repo.visibility)
        except GraphQLError as err:
            details = ", ".join([e["message"] for e in err.errors])
            lists.patchset_update_tool(ml.owner, tool_id, "FAILED",
                f"Failed to submit build: {details}")
            continue
        ids.append(b["id"])
        build_url = f"{buildsrht}/{project.owner.canonical_name}/job/{b['id']}"
        lists.patchset_update_tool(ml.owner, tool_id, "WAITING",
                   f"[#{b['id']}]({build_url}) running {key}")

    # XXX: This is a different format than the REST API uses
    trigger = {
            "type": "EMAIL",
            "condition": "ALWAYS",
            "email": {
                "to": email.utils.formataddr(submitter),
                "cc": ml.posting_addr(),
                "inReplyTo": f"<{message_id}>",
            },
    }
    builds.create_group(project.owner, ids, build_note, [trigger], valid=valid)
    return ids
