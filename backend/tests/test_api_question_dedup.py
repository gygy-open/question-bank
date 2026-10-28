"""题目查重在各写入入口的行为:网页单题、修改、批量、整卷导入(预检/提交)、后台导入、站内 AI。"""
import json

import pytest
from sqlalchemy import select

from app.core.permissions import SubjectRole
from app.core.security import create_access_token
from app.models.import_task import ImportTask, ImportTaskStatus
from app.models.question import Question
from app.models.subject import Subject
from app.models.user import User

API = "/api/v1"
STEM = "在三角形 ABC 中，已知角 A 等于六十度，边 BC 的长度为二，求三角形面积的最大值。"


def doc(text):
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _payload(text, sid, **extra):
    return {"content": doc(text), "q_type": "free_response", "subject_id": sid, **extra}


def _paper_q(temp_id, text):
    return {
        "temp_id": temp_id,
        "q_type": "free_response",
        "content": doc(text),
        "answer": {"kind": "free_response", "reference": None},
        "status": "draft",
    }


@pytest.fixture
async def ctx(db_session, grant_role):
    editor = User(username="editor", full_name="编辑", hashed_password="x", is_active=True)
    db_session.add(editor)
    subject = Subject(name="数学", slug="math")
    db_session.add(subject)
    await db_session.commit()
    await grant_role(editor, subject, SubjectRole.EDITOR)
    return {"editor": editor, "subject": subject}


async def _create(client, ctx, text, **extra):
    return await client.post(f"{API}/questions", json=_payload(text, ctx["subject"].id, **extra), headers=_auth(ctx["editor"]))


# --------------------------------------------------------------------------- #
# 单题
# --------------------------------------------------------------------------- #
async def test_create_blocks_duplicate_until_confirmed(client, ctx):
    first = await _create(client, ctx, STEM)
    assert first.status_code == 200

    dup = await _create(client, ctx, "1.  " + STEM.replace("，", ","))
    assert dup.status_code == 409
    body = dup.json()
    assert body["code"] == "question.duplicate_suspected"
    cand = body["params"]["candidates"][0]
    assert cand["question_id"] == first.json()["id"]
    assert cand["level"] == "duplicate" and cand["created_by"] == "编辑"

    similar = await _create(client, ctx, STEM.replace("长度为", "长为"))
    assert similar.status_code == 409
    assert similar.json()["params"]["candidates"][0]["level"] == "similar"

    ok = await _create(client, ctx, STEM, allow_duplicate=True)
    assert ok.status_code == 200
    assert "allow_duplicate" not in ok.json()


async def test_duplicate_check_endpoint(client, ctx):
    created = (await _create(client, ctx, STEM)).json()
    h = _auth(ctx["editor"])
    r = await client.post(f"{API}/questions/duplicate-check", json=_payload(STEM, ctx["subject"].id), headers=h)
    assert r.status_code == 200
    assert [c["question_id"] for c in r.json()["candidates"]] == [created["id"]]

    r = await client.post(f"{API}/questions/duplicate-check",
                          json=_payload(STEM, ctx["subject"].id, exclude_question_id=created["id"]), headers=h)
    assert r.json()["candidates"] == []
    r = await client.post(f"{API}/questions/duplicate-check",
                          json=_payload("完全不同的另一道题目，内容与前者毫无关系", ctx["subject"].id), headers=h)
    assert r.json()["candidates"] == []


async def test_update_checks_only_when_signature_changes(client, ctx):
    a = (await _create(client, ctx, STEM)).json()
    b = (await _create(client, ctx, "已知数列的前 n 项和为 Sn，且满足递推关系，求数列的通项公式。")).json()
    h = _auth(ctx["editor"])

    # 改成与 a 重复 → 409;确认后放行
    r = await client.put(f"{API}/questions/{b['id']}", json={"content": doc(STEM)}, headers=h)
    assert r.status_code == 409
    r = await client.put(f"{API}/questions/{b['id']}", json={"content": doc(STEM), "allow_duplicate": True}, headers=h)
    assert r.status_code == 200

    # 现在 a、b 内容相同;只改难度不应再被拦,也不应把自己算进去
    r = await client.put(f"{API}/questions/{a['id']}", json={"difficulty": 4}, headers=h)
    assert r.status_code == 200
    r = await client.put(f"{API}/questions/{a['id']}", json={"content": doc(STEM + " ")}, headers=h)
    assert r.status_code == 200  # 归一化后签名未变


async def test_batch_create_reports_all_hits(client, ctx):
    await _create(client, ctx, STEM)
    h = _auth(ctx["editor"])
    other = "已知数列的前 n 项和为 Sn，且满足递推关系，求数列的通项公式。"
    batch = {"questions": [
        _payload(STEM, ctx["subject"].id, temp_id="a"),
        _payload(other, ctx["subject"].id, temp_id="b"),
        _payload(other, ctx["subject"].id, temp_id="c"),
    ]}
    r = await client.post(f"{API}/questions/batch", json=batch, headers=h)
    assert r.status_code == 409
    items = {item["ref"]: item for item in r.json()["params"]["items"]}
    assert set(items) == {"a", "c"}
    assert items["c"]["batch"][0]["ref"] == "b"

    for q in batch["questions"]:
        q["allow_duplicate"] = True
    r = await client.post(f"{API}/questions/batch", json=batch, headers=h)
    assert r.status_code == 200 and len(r.json()) == 3


# --------------------------------------------------------------------------- #
# 整卷导入
# --------------------------------------------------------------------------- #
async def test_paper_import_preview_and_commit(client, ctx, db_session):
    existing = (await _create(client, ctx, STEM)).json()
    sid = ctx["subject"].id
    h = _auth(ctx["editor"])
    other = "已知数列的前 n 项和为 Sn，且满足递推关系，求数列的通项公式。"
    questions = [_paper_q("t1", STEM), _paper_q("t2", other), _paper_q("t3", other + "。")]

    preview = await client.post(f"{API}/subjects/{sid}/paper-imports/preview",
                                json={"scope": "personal", "questions": questions}, headers=h)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert [c["question_id"] for c in body["duplicates"]["t1"]] == [existing["id"]]
    assert body["intra_batch_duplicates"] == {"t3": [{"ref": "t2", "level": "duplicate", "similarity": 1.0}]}

    # 未确认的命中题被跳过,需要用户同意部分导入
    r = await client.post(f"{API}/subjects/{sid}/paper-imports",
                          json={"scope": "personal", "questions": questions}, headers=h)
    assert r.status_code == 422 and r.json()["code"] == "paper_import.partial_skipped"
    r = await client.post(f"{API}/subjects/{sid}/paper-imports",
                          json={"scope": "personal", "questions": questions, "proceed_with_partial": True}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["created_count"] == 1
    assert {s["temp_id"] for s in r.json()["skipped"]} == {"t1", "t3"}
    assert "#%d" % existing["id"] in next(s for s in r.json()["skipped"] if s["temp_id"] == "t1")["message"]


async def test_paper_import_commit_with_confirmed_duplicates(client, ctx):
    await _create(client, ctx, STEM)
    sid = ctx["subject"].id
    r = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={"scope": "personal", "questions": [_paper_q("t1", STEM)], "allow_duplicate_temp_ids": ["t1"]},
        headers=_auth(ctx["editor"]),
    )
    assert r.status_code == 200, r.text
    assert r.json()["created_count"] == 1 and r.json()["skipped"] == []


async def test_worker_import_records_duplicates(client, ctx, db_session):
    from app.services.paper_import_service import commit_extracted_paper_import

    existing = (await _create(client, ctx, STEM)).json()
    task = ImportTask(user_id=ctx["editor"].id, subject_id=ctx["subject"].id, file_path="x.md",
                      original_filename="x.md", file_type="markdown", status=ImportTaskStatus.PROCESSING)
    db_session.add(task)
    await db_session.commit()
    from app.crud.crud_user import user as crud_user
    actor = await crud_user.get_with_memberships(db_session, id=ctx["editor"].id)

    extraction = {"questions": [
        {"q_type": "free_response", "content": STEM, "answer": ""},
        {"q_type": "free_response", "content": "全新的一道题目，描述某个完全不同的场景与问题", "answer": ""},
        {"q_type": "free_response", "content": "全新的一道题目，描述某个完全不同的场景与问题。", "answer": ""},
    ]}
    result = await commit_extracted_paper_import(
        db_session, actor=actor, subject_id=ctx["subject"].id, extraction=extraction, import_task=task
    )
    await db_session.commit()
    assert len(result.created_questions) == 3  # 无人值守:照常入库
    created = [q.id for q in result.created_questions]
    summary = json.loads(task.result_summary)
    dups = summary["duplicates"]
    assert set(dups) == {str(created[0]), str(created[2])}
    assert dups[str(created[0])][0]["question_id"] == existing["id"]
    assert dups[str(created[2])][0]["question_id"] == created[1]


# --------------------------------------------------------------------------- #
# 站内 AI:提案照常创建,但把查重结果告诉模型
# --------------------------------------------------------------------------- #
async def test_chat_proposal_flags_duplicates(client, ctx, db_session):
    from app.ai.tools.questions import propose_question_draft
    from app.capabilities.context import ExecutionContext, Surface
    from app.crud.crud_user import user as crud_user

    existing = (await _create(client, ctx, STEM)).json()
    actor = await crud_user.get_with_memberships(db_session, id=ctx["editor"].id)
    ec = ExecutionContext(db=db_session, actor=actor, surface=Surface.CHAT, subject_id=ctx["subject"].id)
    result = await propose_question_draft(ec, {"q_type": "free_response", "content": STEM, "answer": "略"})
    new_id = result.data["question_ids"][0]
    assert new_id != existing["id"]
    assert result.data["duplicates"][new_id][0]["question_id"] == existing["id"]
    assert f"#{existing['id']}" in result.content
