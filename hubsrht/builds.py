import email.utils
import json
import random
import yaml
from flask import url_for
from fnmatch import fnmatch
from hubsrht.services.builds import BuildsClient, GraphQLClientGraphQLMultiError
from hubsrht.services.builds import TriggerInput, EmailTriggerInput, TriggerType
from hubsrht.services.builds import TriggerCondition, Visibility
from hubsrht.services.git import GitClient
from hubsrht.services.lists import ListsClient, ToolIcon
from hubsrht.types import SourceRepo, RepoType
from sqlalchemy import func
from srht.config import get_origin
from srht.crypto import fernet
from srht.graphql import InternalAuth
from yaml.error import YAMLError

def submit_patchset(ml, patchset):
    buildsrht = get_origin("builds.sr.ht", external=True, default=None)
    if not buildsrht:
        return None
    from buildsrht.manifest import Manifest, Task, Trigger

    project = ml.project
    auth = InternalAuth(project.owner)
    builds_client = BuildsClient(auth)
    git_client = GitClient(auth)
    lists_client = ListsClient(auth)

    patch_id = patchset.id
    patch_url = f"{ml.url()}/patches/{patch_id}"
    patch_mbox = f"{ml.url()}/patches/{patch_id}/mbox"
    subject = patchset.subject
    prefix = patchset.prefix

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

    repo = git_client.get_manifests(repo.owner.username, repo.name).user.repository
    assert repo is not None

    manifests = dict()
    if repo.multiple:
        for dirent in repo.multiple.object.entries.results:
            if not dirent.object:
                continue
            if not any(fnmatch(dirent.name, pat) for pat in ["*.yml", "*.yaml"]):
                continue
            manifests[dirent.name] = dirent.object.text
    elif repo.single_yml:
        manifests[".build.yml"] = repo.single_yml.object.text
    elif repo.single_yaml:
        manifests[".build.yaml"] = repo.single_yaml.object.text
    else:
        return None

    if len(manifests) > 4:
        keys = list(manifests.keys())
        random.shuffle(keys)
        manifests = { key: manifests[key] for key in keys[:4] }

    ids = []

    version = patchset.version
    if version == 1:
        version = ""
    else:
        version = f" v{version}"

    message_id = patchset.thread.root.message_id
    reply_to = patchset.thread.root.reply_to
    if reply_to:
        submitter = email.utils.parseaddr(reply_to)
    else:
        name = patchset.submitter.name
        address = patchset.submitter.address
        submitter = (name, address)

    build_note = f"""[{subject}][0]{version} from [{submitter[0]}][1]

[0]: {ml.url()}/patches/{patch_id}
[1]: mailto:{submitter[1]}"""

    for key, value in manifests.items():
        try:
            manifest = Manifest(yaml.safe_load(value))
        except YAMLError:
            lists_client.create_tool(
                    patchset_id=patch_id,
                    icon=ToolIcon.FAILED,
                    details=f"Failed to submit build: error parsing YAML")
            continue

        submit_build = True
        sub = manifest.submitter
        if sub != None and "hub.sr.ht" in sub:
            hub_sub = sub["hub.sr.ht"]
            if "enabled" in hub_sub:
                submit_build = hub_sub["enabled"]
        if not submit_build:
            continue

        tool_id = lists_client.create_tool(
                patchset_id=patch_id,
                icon=ToolIcon.PENDING,
                details=f"build pending: {key}").create_tool.id

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
            "action": "webhook",
            "condition": "always",
            "url": root + url_for("webhooks.build_complete", details=details),
        }))

        try:
            manifest = yaml.dump(manifest.to_dict(), default_flow_style=False)
            job = builds_client.submit_build(
                    manifest=manifest,
                    note=build_note,
                    tags=[repo.name, "patches", key],
                    execute=False,
                    visibility=Visibility(repo.visibility.value)).submit
        except GraphQLClientGraphQLMultiError as err:
            details = ", ".join([e.message for e in err.errors])
            lists_client.update_tool(
                    tool_id=tool_id,
                    icon=ToolIcon.FAILED,
                    details=f"Failed to submit build: {details}")
            continue

        ids.append(job.id)
        build_url = f"{buildsrht}/{project.owner.canonical_name}/job/{job.id}"
        lists_client.update_tool(
                tool_id=tool_id,
                icon=ToolIcon.WAITING,
                details=f"[#{job.id}]({build_url}) running {key}")

    trigger = TriggerInput(
        type=TriggerType.EMAIL,
        condition=TriggerCondition.ALWAYS,
        email=EmailTriggerInput(
            to=email.utils.formataddr(submitter),
            cc=ml.posting_addr(),
            in_reply_to=f"<{message_id}>",
        )
    )
    builds_client.create_group(
        jobs=ids,
        triggers=[trigger],
        note=build_note)
    return ids
