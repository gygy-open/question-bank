"""题目写能力的权限矩阵 —— 补齐 test_api_permissions 未覆盖的 update/delete/batch 路径。

这些判定在 Phase 3 之前散落在端点里(`_can_delete_question`、inline require),
迁到 `app/capabilities/questions.py` 后必须逐字保持,尤其是:
- 不可见 → 404(防枚举),而非 403;
- 批量操作对无权条目「跳过」而非整批失败。
"""
import json

import pytest

from app.core.security import create_access_token
from app.models.question import Question, QuestionType, QuestionVisibility
from app.models.subject import Subject
from app.models.subject_member import SubjectMember
from app.models.user import User

API = "/api/v1"

_DOC = {"type": "doc", "content": [{"type": "paragraph"}]}


async def _seed_user(db_session, *, username, is_superuser=False) -> User:
    user = User(
        username=username, full_name=username, hashed_password="x",
        is_active=True, is_superuser=is_superuser,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _seed_question(db_session, *, subject, created_by, visibility=QuestionVisibility.PUBLIC.value):
    q = Question(
        content=json.dumps(_DOC),
        q_type=QuestionType.FREE_RESPONSE,
        subject_id=subject.id,
        created_by=created_by.id,
        visibility=visibility,
    )
    db_session.add(q)
    await db_session.commit()
    await db_session.refresh(q)
    return q


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}


@pytest.fixture
async def ctx(db_session):
    admin = await _seed_user(db_session, username="admin", is_superuser=True)
    math = Subject(name="数学", slug="math")
    other = Subject(name="物理", slug="phys")
    db_session.add_all([math, other])
    await db_session.commit()
    await db_session.refresh(math)
    await db_session.refresh(other)

    author = await _seed_user(db_session, username="author")
    editor = await _seed_user(db_session, username="editor")
    viewer = await _seed_user(db_session, username="viewer")
    manager = await _seed_user(db_session, username="manager")
    outsider = await _seed_user(db_session, username="outsider")
    for user, role in [(author, "editor"), (editor, "editor"), (viewer, "viewer"), (manager, "manager")]:
        db_session.add(SubjectMember(user_id=user.id, subject_id=math.id, role=role))
    await db_session.commit()

    question = await _seed_question(db_session, subject=math, created_by=author)
    return {
        "admin": admin, "math": math, "other": other, "author": author,
        "editor": editor, "viewer": viewer, "manager": manager,
        "outsider": outsider, "question": question,
    }


# --------------------------------------------------------------------------- #
# question.update —— EDIT_QUESTION,按题目自身的学科判定
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "actor, expected",
    [("author", 200), ("editor", 200), ("manager", 200), ("admin", 200), ("viewer", 403)],
)
async def test_update_permission_matrix(client, ctx, actor, expected):
    r = await client.put(
        f"{API}/questions/{ctx['question'].id}",
        json={"difficulty": 3},
        headers=_auth(ctx[actor]),
    )
    assert r.status_code == expected


async def test_update_by_outsider_is_404_not_403(client, ctx):
    """跨学科不可见的题目一律 404,不能靠状态码探测题目是否存在。"""
    r = await client.put(
        f"{API}/questions/{ctx['question'].id}",
        json={"difficulty": 3},
        headers=_auth(ctx["outsider"]),
    )
    assert r.status_code == 404


async def test_update_missing_question_is_404(client, ctx):
    r = await client.put(
        f"{API}/questions/999999", json={"difficulty": 3}, headers=_auth(ctx["editor"])
    )
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# question.delete —— 创建者 / 学科负责人 / 超管
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "actor, expected",
    [("author", 200), ("manager", 200), ("admin", 200), ("editor", 403), ("viewer", 403)],
)
async def test_delete_permission_matrix(client, ctx, actor, expected):
    r = await client.delete(f"{API}/questions/{ctx['question'].id}", headers=_auth(ctx[actor]))
    assert r.status_code == expected


async def test_delete_by_outsider_is_404(client, ctx):
    r = await client.delete(f"{API}/questions/{ctx['question'].id}", headers=_auth(ctx["outsider"]))
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# 批量:无权条目跳过,不整批失败
# --------------------------------------------------------------------------- #
async def test_batch_delete_skips_unauthorized(client, ctx, db_session):
    mine = await _seed_question(db_session, subject=ctx["math"], created_by=ctx["editor"])
    r = await client.post(
        f"{API}/questions/batch-delete",
        json={"ids": [ctx["question"].id, mine.id]},
        headers=_auth(ctx["editor"]),
    )
    assert r.status_code == 200
    # author 的那道题 editor 删不了,只删掉自己的一道。
    assert r.json()["deleted_count"] == 1


async def test_batch_update_only_touches_own_questions(client, ctx, db_session):
    mine = await _seed_question(db_session, subject=ctx["math"], created_by=ctx["editor"])
    r = await client.post(
        f"{API}/questions/batch-update",
        json={"ids": [ctx["question"].id, mine.id], "source": "x"},
        headers=_auth(ctx["editor"]),
    )
    assert r.status_code == 200
    assert r.json()["updated_count"] == 1


async def test_batch_confirm_rejects_bad_action(client, ctx):
    """Invalid 领域错误经 handler 映射回 400,与迁移前的 HTTPException 一致。"""
    r = await client.post(
        f"{API}/questions/batch-confirm",
        json={"question_ids": [ctx["question"].id], "action": "nonsense"},
        headers=_auth(ctx["editor"]),
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "Invalid action. Must be 'approve' or 'reject'."
