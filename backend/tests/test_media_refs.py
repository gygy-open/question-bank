"""媒体引用索引:写路径同步 media_references、跨学科/不存在资产拒绝、列表计数与"被引用于"。"""
import io
import uuid
import zipfile

import pytest
from PIL import Image
from sqlalchemy import select

from app.core.config import settings
from app.core.permissions import SubjectRole
from app.core.security import create_access_token
from app.models.composition import CompositionNode
from app.models.media_asset import MediaOwnerType, MediaReference
from app.models.question import Question
from app.models.subject import Subject
from app.models.user import User

API = "/api/v1"


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}


def _png(color: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(buf, format="PNG")
    return buf.getvalue()


def _doc_with_image(asset_id: int | None = None, text: str = "题干") -> dict:
    content: list = [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]
    if asset_id is not None:
        content.append({
            "type": "image",
            "attrs": {"src": f"/api/v1/media/{asset_id}/content", "assetId": asset_id},
        })
    return {"type": "doc", "content": content}


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    (tmp_path / "static").mkdir()
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture
async def ctx(db_session, grant_role):
    editor = User(username="ref_editor", hashed_password="x", is_active=True)
    other = User(username="ref_other", hashed_password="x", is_active=True)
    viewer = User(username="ref_viewer", hashed_password="x", is_active=True)
    outsider = User(username="ref_outsider", hashed_password="x", is_active=True)
    subject = Subject(name="生物", slug="bio-refs")
    other_subject = Subject(name="历史", slug="his-refs")
    db_session.add_all([editor, other, viewer, outsider, subject, other_subject])
    await db_session.commit()
    for user in (editor, other):
        await grant_role(user, subject, SubjectRole.EDITOR)
        await grant_role(user, other_subject, SubjectRole.EDITOR)
    await grant_role(viewer, subject, SubjectRole.VIEWER)
    return {
        "editor": editor, "other": other, "viewer": viewer, "outsider": outsider,
        "subject": subject, "other_subject": other_subject,
    }


async def _asset(client, user, subject_id: int, color: str = "red") -> int:
    r = await client.post(
        f"{API}/subjects/{subject_id}/media",
        files={"file": (f"{color}.png", _png(color), "image/png")},
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _refs(db_session, owner_type: MediaOwnerType, owner_id: int) -> set[int]:
    rows = await db_session.scalars(
        select(MediaReference.asset_id).where(
            MediaReference.owner_type == owner_type.value,
            MediaReference.owner_id == owner_id,
        )
    )
    return set(rows.all())


async def _create_question(client, user, subject_id: int, content: dict, visibility="public"):
    # 这里的测试会故意建内容相同的题(不同用户/可见性),与查重无关
    return await client.post(
        f"{API}/questions",
        json={"content": content, "q_type": "free_response", "subject_id": subject_id,
              "visibility": visibility, "allow_duplicate": True},
        headers=_auth(user),
    )


async def test_question_writes_keep_refs_in_sync(client, ctx, db_session):
    sid = ctx["subject"].id
    a, b = await _asset(client, ctx["editor"], sid, "red"), await _asset(client, ctx["editor"], sid, "blue")

    created = await _create_question(client, ctx["editor"], sid, _doc_with_image(a))
    assert created.status_code == 200, created.text
    qid = created.json()["id"]
    assert await _refs(db_session, MediaOwnerType.QUESTION, qid) == {a}

    updated = await client.put(
        f"{API}/questions/{qid}",
        json={"content": _doc_with_image(b), "analysis": _doc_with_image(a, "解析")},
        headers=_auth(ctx["editor"]),
    )
    assert updated.status_code == 200, updated.text
    assert await _refs(db_session, MediaOwnerType.QUESTION, qid) == {a, b}

    cleared = await client.put(
        f"{API}/questions/{qid}",
        json={"content": _doc_with_image(None), "analysis": None},
        headers=_auth(ctx["editor"]),
    )
    assert cleared.status_code == 200, cleared.text
    assert await _refs(db_session, MediaOwnerType.QUESTION, qid) == set()


async def test_question_rejects_foreign_or_missing_assets(client, ctx, db_session):
    foreign = await _asset(client, ctx["editor"], ctx["other_subject"].id)

    cross = await _create_question(client, ctx["editor"], ctx["subject"].id, _doc_with_image(foreign))
    missing = await _create_question(client, ctx["editor"], ctx["subject"].id, _doc_with_image(999999))

    assert cross.status_code == 422, cross.text
    assert missing.status_code == 422, missing.text
    assert (await db_session.scalars(select(MediaReference))).all() == []


async def test_stimulus_refs_follow_content(client, ctx, db_session):
    sid = ctx["subject"].id
    a = await _asset(client, ctx["editor"], sid)

    created = await client.post(
        f"{API}/subjects/{sid}/stimuli", json={"content": _doc_with_image(a)}, headers=_auth(ctx["editor"])
    )
    assert created.status_code == 201, created.text
    stimulus = created.json()
    assert await _refs(db_session, MediaOwnerType.STIMULUS, stimulus["id"]) == {a}

    updated = await client.put(
        f"{API}/subjects/{sid}/stimuli/{stimulus['id']}",
        json={"expected_revision": stimulus["revision"], "content": _doc_with_image(None)},
        headers=_auth(ctx["editor"]),
    )
    assert updated.status_code == 200, updated.text
    assert await _refs(db_session, MediaOwnerType.STIMULUS, stimulus["id"]) == set()


def _rich_text_node(asset_id: int | None) -> dict:
    return {
        "id": str(uuid.uuid4()), "node_kind": "block", "node_type": "rich_text",
        "content": _doc_with_image(asset_id, "说明"),
    }


async def test_composition_refs_and_frozen_versions(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["editor"])
    a = await _asset(client, ctx["editor"], sid)
    comp = (await client.post(f"{API}/subjects/{sid}/compositions?scope=shared", json={"title": "稿"}, headers=h)).json()
    base = f"{API}/subjects/{sid}/compositions/{comp['id']}"

    put = await client.put(f"{base}/nodes?scope=shared", json={"expected_revision": 1, "nodes": [_rich_text_node(a)]}, headers=h)
    assert put.status_code == 200, put.text
    assert await _refs(db_session, MediaOwnerType.COMPOSITION, comp["id"]) == {a}

    version = await client.post(f"{base}/versions?scope=shared", json={"expected_revision": 2}, headers=h)
    assert version.status_code == 201, version.text
    version_id = version.json()["id"]

    cleared = await client.put(f"{base}/nodes?scope=shared", json={"expected_revision": 2, "nodes": []}, headers=h)
    assert cleared.status_code == 200, cleared.text
    assert await _refs(db_session, MediaOwnerType.COMPOSITION, comp["id"]) == set()
    # 定稿版本的引用不随工作区变化。
    assert await _refs(db_session, MediaOwnerType.COMPOSITION_VERSION, version_id) == {a}

    foreign = await _asset(client, ctx["editor"], ctx["other_subject"].id)
    rejected = await client.put(
        f"{base}/nodes?scope=shared", json={"expected_revision": 3, "nodes": [_rich_text_node(foreign)]}, headers=h
    )
    assert rejected.status_code == 422, rejected.text


async def test_list_subject_media_counts_usage(client, ctx):
    sid = ctx["subject"].id
    used = await _asset(client, ctx["editor"], sid, "red")
    unused = await _asset(client, ctx["editor"], sid, "blue")
    await _create_question(client, ctx["editor"], sid, _doc_with_image(used))
    await _create_question(client, ctx["editor"], sid, _doc_with_image(used, "第二题"))

    url = f"{API}/subjects/{sid}/media"
    page = (await client.get(url, headers=_auth(ctx["viewer"]))).json()
    assert page["total"] == 2
    assert {item["id"]: item["usage_count"] for item in page["items"]} == {used: 2, unused: 0}

    only_unused = (await client.get(f"{url}?used=false", headers=_auth(ctx["viewer"]))).json()
    assert [item["id"] for item in only_unused["items"]] == [unused]
    by_name = (await client.get(f"{url}?q=blue", headers=_auth(ctx["viewer"]))).json()
    assert [item["id"] for item in by_name["items"]] == [unused]

    assert (await client.get(url, headers=_auth(ctx["outsider"]))).status_code == 403


async def test_references_hide_what_viewer_cannot_see(client, ctx):
    sid = ctx["subject"].id
    a = await _asset(client, ctx["editor"], sid)
    public = (await _create_question(client, ctx["editor"], sid, _doc_with_image(a, "公开题"))).json()
    await _create_question(client, ctx["other"], sid, _doc_with_image(a, "他人私有题"), visibility="private")

    refs = await client.get(f"{API}/media/{a}/references", headers=_auth(ctx["viewer"]))
    assert refs.status_code == 200, refs.text
    body = refs.json()
    assert [(i["owner_type"], i["owner_id"], i["title"]) for i in body["items"]] == [
        ("question", public["id"], "公开题"),
    ]
    assert body["hidden_count"] == 1

    assert (await client.get(f"{API}/media/{a}/references", headers=_auth(ctx["outsider"]))).status_code == 404


async def test_update_and_delete_media(client, ctx):
    sid = ctx["subject"].id
    used = await _asset(client, ctx["editor"], sid, "red")
    unused = await _asset(client, ctx["editor"], sid, "blue")
    await _create_question(client, ctx["editor"], sid, _doc_with_image(used))

    patched = await client.patch(
        f"{API}/media/{unused}", json={"original_filename": " 地图.png ", "alt": ""}, headers=_auth(ctx["editor"])
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["original_filename"] == "地图.png" and patched.json()["alt"] is None
    assert (await client.patch(f"{API}/media/{unused}", json={"alt": "x"}, headers=_auth(ctx["viewer"]))).status_code == 403

    in_use = await client.delete(f"{API}/media/{used}", headers=_auth(ctx["editor"]))
    assert in_use.status_code == 409
    assert (await client.delete(f"{API}/media/{unused}", headers=_auth(ctx["viewer"]))).status_code == 403
    assert (await client.delete(f"{API}/media/{unused}", headers=_auth(ctx["editor"]))).status_code == 204

    listed = (await client.get(f"{API}/subjects/{sid}/media", headers=_auth(ctx["editor"]))).json()
    assert [item["id"] for item in listed["items"]] == [used]
    # 重新上传同一文件会恢复原资产。
    assert await _asset(client, ctx["editor"], sid, "blue") == unused

    download = await client.get(f"{API}/media/{used}/content?download=true", headers=_auth(ctx["viewer"]))
    assert download.headers["content-disposition"].startswith("attachment")


async def test_replace_rewrites_editable_refs_and_keeps_versions(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["editor"])
    old = await _asset(client, ctx["editor"], sid, "red")
    new = await _asset(client, ctx["editor"], sid, "blue")
    foreign = await _asset(client, ctx["editor"], ctx["other_subject"].id, "green")

    mine = (await _create_question(client, ctx["editor"], sid, _doc_with_image(old))).json()
    await client.put(f"{API}/questions/{mine['id']}", json={"analysis": _doc_with_image(old, "解析")}, headers=h)
    hidden = (await _create_question(client, ctx["other"], sid, _doc_with_image(old), visibility="private")).json()

    comp = (await client.post(f"{API}/subjects/{sid}/compositions?scope=shared", json={"title": "稿"}, headers=h)).json()
    base = f"{API}/subjects/{sid}/compositions/{comp['id']}"
    node = {"id": str(uuid.uuid4()), "node_kind": "block", "node_type": "question", "question_id": mine["id"]}
    assert (await client.put(f"{base}/nodes?scope=shared", json={"expected_revision": 1, "nodes": [node]}, headers=h)).status_code == 200
    version = (await client.post(f"{base}/versions?scope=shared", json={"expected_revision": 2}, headers=h)).json()

    url = f"{API}/media/{old}/replace"
    assert (await client.post(url, json={"new_asset_id": foreign}, headers=h)).status_code == 422
    assert (await client.post(url, json={"new_asset_id": new}, headers=_auth(ctx["viewer"]))).status_code == 403
    hidden_target = {"new_asset_id": new, "targets": [{"owner_type": "question", "owner_id": hidden["id"]}]}
    assert (await client.post(url, json=hidden_target, headers=h)).status_code == 403
    unrelated = {"new_asset_id": new, "targets": [{"owner_type": "stimulus", "owner_id": 1}]}
    assert (await client.post(url, json=unrelated, headers=h)).status_code == 422

    result = await client.post(url, json={"new_asset_id": new}, headers=h)
    assert result.status_code == 200, result.text
    body = result.json()
    assert {(t["owner_type"], t["owner_id"]) for t in body["replaced"]} == {
        ("question", mine["id"]), ("composition", comp["id"]),
    }
    assert (body["skipped"], body["frozen"]) == (1, 1)

    question = (await client.get(f"{API}/questions/{mine['id']}", headers=h)).json()
    assert question["content"]["content"][1]["attrs"] == {"src": f"/api/v1/media/{new}/content", "assetId": new}
    assert question["analysis"]["content"][1]["attrs"]["assetId"] == new
    assert await _refs(db_session, MediaOwnerType.QUESTION, mine["id"]) == {new}
    assert await _refs(db_session, MediaOwnerType.QUESTION, hidden["id"]) == {old}
    assert await _refs(db_session, MediaOwnerType.COMPOSITION, comp["id"]) == {new}
    assert await _refs(db_session, MediaOwnerType.COMPOSITION_VERSION, version["id"]) == {old}

    # 原本已同步的稿件节点跟随新的题目内容版本,不被误报为过期。
    rows = await db_session.execute(
        select(CompositionNode.question_revision, Question.content_revision)
        .join(Question, Question.id == CompositionNode.question_id)
        .where(CompositionNode.composition_id == comp["id"])
    )
    pinned, current = rows.one()
    assert pinned == current


async def test_batch_delete_update_and_archive(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["editor"])
    used = await _asset(client, ctx["editor"], sid, "red")
    unused = await _asset(client, ctx["editor"], sid, "blue")
    foreign = await _asset(client, ctx["editor"], ctx["other_subject"].id, "green")
    await _create_question(client, ctx["editor"], sid, _doc_with_image(used))
    base = f"{API}/subjects/{sid}/media"

    updated = await client.post(f"{base}/batch-update", json={"ids": [used, unused, foreign], "source": " 课本 "}, headers=h)
    assert updated.json() == {"affected": 2, "skipped": 1}
    sources = {i["id"]: i["source"] for i in (await client.get(base, headers=h)).json()["items"]}
    assert sources == {used: "课本", unused: "课本"}
    assert (await client.post(f"{base}/batch-update", json={"ids": [used]}, headers=_auth(ctx["viewer"]))).status_code == 403

    archive = await client.get(f"{base}/archive", params=[("ids", used), ("ids", unused), ("ids", foreign)], headers=_auth(ctx["viewer"]))
    assert archive.status_code == 200, archive.text
    with zipfile.ZipFile(io.BytesIO(archive.content)) as zf:
        assert sorted(zf.namelist()) == sorted([f"{used}-red.png", f"{unused}-blue.png"])
    assert (await client.get(f"{base}/archive", params={"ids": foreign}, headers=h)).status_code == 404

    deleted = await client.post(f"{base}/batch-delete", json={"ids": [used, unused, foreign]}, headers=h)
    assert deleted.json() == {"affected": 1, "skipped": 2}
    assert [i["id"] for i in (await client.get(base, headers=h)).json()["items"]] == [used]


async def test_copy_to_another_subject_shares_file(client, ctx, db_session, grant_role):
    sid, other = ctx["subject"].id, ctx["other_subject"].id
    source = await _asset(client, ctx["editor"], sid, "red")
    await client.patch(f"{API}/media/{source}", json={"alt": "细胞"}, headers=_auth(ctx["editor"]))

    copied = await client.post(f"{API}/media/{source}/copy", json={"subject_id": other}, headers=_auth(ctx["editor"]))
    assert copied.status_code == 201, copied.text
    body = copied.json()
    assert body["id"] != source and (body["subject_id"], body["alt"]) == (other, "细胞")
    # 目标学科已有同一文件时复用,不重复建资产。
    again = await client.post(f"{API}/media/{source}/copy", json={"subject_id": other}, headers=_auth(ctx["editor"]))
    assert again.json()["id"] == body["id"]

    # viewer 能读源图,但在目标学科没有编辑权。
    await grant_role(ctx["viewer"], ctx["other_subject"], SubjectRole.VIEWER)
    denied = await client.post(f"{API}/media/{source}/copy", json={"subject_id": other}, headers=_auth(ctx["viewer"]))
    assert denied.status_code == 403
