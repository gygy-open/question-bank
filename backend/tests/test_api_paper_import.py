"""整卷导入 API 的聚焦测试。

覆盖产品规格里的关键决策:默认不建稿、空间/目录由用户指定、题号重排可选、
部分失败由用户决定、私有题不得进共享稿件、幂等重放、权限矩阵,
以及"正常路径原子"——建稿失败不得留下半份题目。
"""
import json

import pytest
from sqlalchemy import select

from app.core.permissions import SubjectRole
from app.core.security import create_access_token
from app.models.composition import Composition, CompositionNode
from app.models.import_task import CompositionImportState, ImportTask
from app.models.question import Question
from app.models.question_group import (
    QuestionGroup,
    QuestionGroupItem,
    QuestionRelation,
    Stimulus,
)
from app.models.subject import Subject
from app.models.subject_member import SubjectMember
from app.models.user import User

API = "/api/v1"


async def _seed_user(db_session, *, username: str) -> User:
    user = User(username=username, full_name=username, hashed_password="x", is_active=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _seed_subject(db_session, *, name="数学", slug="math") -> Subject:
    subject = Subject(name=name, slug=slug)
    db_session.add(subject)
    await db_session.commit()
    await db_session.refresh(subject)
    return subject


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}


def _question(temp_id: str, content: str, *, visibility="public", **extra) -> dict:
    payload = {
        "temp_id": temp_id,
        "q_type": "free_response",
        "content": {
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": content}]}],
        },
        "answer": {"kind": "free_response", "reference": None},
        "status": "draft",
        "difficulty": 3,
        "visibility": visibility,
    }
    payload.update(extra)
    return payload


def _broken_question(temp_id: str) -> dict:
    """答案引用了不存在的选项 —— 不依赖 status,必定被领域校验拒绝。"""
    return {
        "temp_id": temp_id,
        "q_type": "single_choice",
        "content": {
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "坏题"}]}],
        },
        "options": [
            {"id": "opt-a", "label": "A", "content": None},
            {"id": "opt-b", "label": "B", "content": None},
        ],
        "answer": {"kind": "single_choice", "correct": "opt-does-not-exist"},
        "status": "draft",
        "difficulty": 3,
        "visibility": "public",
    }


@pytest.fixture
async def ctx(db_session, grant_role):
    editor = await _seed_user(db_session, username="editor")
    viewer = await _seed_user(db_session, username="viewer")
    outsider = await _seed_user(db_session, username="outsider")
    subject = await _seed_subject(db_session)

    await grant_role(editor, subject, SubjectRole.EDITOR)
    db_session.add(
        SubjectMember(user_id=viewer.id, subject_id=subject.id, role=SubjectRole.VIEWER.value)
    )
    await db_session.commit()

    return {"editor": editor, "viewer": viewer, "outsider": outsider, "subject": subject}


# --------------------------------------------------------------------------- #
# 默认行为:仅导入题目
# --------------------------------------------------------------------------- #
async def test_import_without_composition_creates_questions_only(client, ctx, db_session):
    sid = ctx["subject"].id

    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={
            "scope": "shared",
            "questions": [_question("t1", "第一题"), _question("t2", "第二题")],
            "outline": [
                {"kind": "question_ref", "temp_id": "t1"},
                {"kind": "question_ref", "temp_id": "t2"},
            ],
            "save_as_composition": False,
        },
        headers=_auth(ctx["editor"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created_count"] == 2
    assert body["composition_id"] is None

    task = (await db_session.execute(select(ImportTask))).scalars().one()
    assert task.composition_state is CompositionImportState.NOT_REQUESTED


# --------------------------------------------------------------------------- #
# 同时保存为稿件
# --------------------------------------------------------------------------- #
async def test_import_with_composition_builds_full_paper(client, ctx, db_session):
    sid = ctx["subject"].id

    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={
            "scope": "shared",
            "questions": [_question("t1", "选择题"), _question("t2", "解答题")],
            "outline": [
                {"kind": "rich_text", "markdown": "考试时间 120 分钟"},
                {"kind": "heading", "text": "一、选择题", "level": 2},
                {"kind": "question_ref", "temp_id": "t1", "number": "1"},
                {"kind": "heading", "text": "二、解答题", "level": 2},
                {"kind": "question_ref", "temp_id": "t2", "number": "2"},
            ],
            "save_as_composition": True,
            "title": "高一周测",
            "filename": "week1.docx",
        },
        headers=_auth(ctx["editor"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["composition_id"] is not None
    assert body["composition_title"] == "高一周测"
    assert set(body["temp_id_map"]) == {"t1", "t2"}

    detail = await client.get(
        f"{API}/subjects/{sid}/compositions/{body['composition_id']}?scope=shared",
        headers=_auth(ctx["editor"]),
    )
    assert detail.status_code == 200, detail.text
    node_types = [n["node_type"] for n in detail.json()["nodes"]]
    assert node_types == ["rich_text", "heading", "question", "heading", "question"]

    numbers = [
        n["props"]["number"] for n in detail.json()["nodes"] if n["node_type"] == "question"
    ]
    assert numbers == ["1", "2"]
    assert detail.json()["numbering_enabled"] is True

    comp = (await db_session.execute(select(Composition))).scalars().one()
    assert comp.source_import_task_id is not None
    # 来源固化为快照:原文件被清理后仍可读。
    assert comp.source_snapshot["original_filename"] == "week1.docx"
    assert comp.source_snapshot["question_count"] == 2


async def test_renumber_reassigns_sequential_numbers(client, ctx):
    sid = ctx["subject"].id

    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={
            "scope": "shared",
            "questions": [_question("t1", "题一"), _question("t2", "题二")],
            # 原卷题号是 3 / 7(中间的题已在审核页删除)。
            "outline": [
                {"kind": "question_ref", "temp_id": "t1", "number": "3"},
                {"kind": "question_ref", "temp_id": "t2", "number": "7"},
            ],
            "save_as_composition": True,
            "title": "重排题号",
            "renumber": True,
        },
        headers=_auth(ctx["editor"]),
    )
    assert response.status_code == 200, response.text

    detail = await client.get(
        f"{API}/subjects/{sid}/compositions/{response.json()['composition_id']}?scope=shared",
        headers=_auth(ctx["editor"]),
    )
    numbers = [
        n["props"]["number"] for n in detail.json()["nodes"] if n["node_type"] == "question"
    ]
    assert numbers == ["1", "2"]
    assert detail.json()["numbering_enabled"] is True


async def test_keeping_original_numbers_allows_gaps(client, ctx):
    sid = ctx["subject"].id

    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={
            "scope": "shared",
            "questions": [_question("t1", "题一"), _question("t2", "题二")],
            "outline": [
                {"kind": "question_ref", "temp_id": "t1", "number": "3"},
                {"kind": "question_ref", "temp_id": "t2", "number": "7"},
            ],
            "save_as_composition": True,
            "title": "保留原题号",
            "renumber": False,
        },
        headers=_auth(ctx["editor"]),
    )
    detail = await client.get(
        f"{API}/subjects/{sid}/compositions/{response.json()['composition_id']}?scope=shared",
        headers=_auth(ctx["editor"]),
    )
    numbers = [
        n["props"]["number"] for n in detail.json()["nodes"] if n["node_type"] == "question"
    ]
    assert numbers == ["3", "7"]
    assert detail.json()["numbering_enabled"] is True


async def test_legacy_parent_reference_creates_relation_without_writing_parent_id(
    client, ctx, db_session
):
    sid = ctx["subject"].id

    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={
            "scope": "shared",
            "questions": [
                _question("parent", "材料题"),
                _question("child", "子问一", parent_temp_id="parent"),
            ],
            "outline": [],
            "save_as_composition": False,
        },
        headers=_auth(ctx["editor"]),
    )
    assert response.status_code == 200, response.text
    mapping = response.json()["temp_id_map"]

    child = (
        await db_session.execute(select(Question).where(Question.id == mapping["child"]))
    ).scalars().one()
    assert not hasattr(child, "parent_id")
    relation = (await db_session.execute(select(QuestionRelation))).scalars().one()
    assert relation.source_question_id == mapping["parent"]
    assert relation.target_question_id == mapping["child"]
    assert relation.relation_type == "decomposed_from"


async def test_legacy_nested_children_create_relation_not_material_group(
    client, ctx, db_session
):
    sid = ctx["subject"].id
    parent = _question("parent", "原题")
    parent["children"] = [_question("child", "拆解题")]
    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={
            "scope": "shared",
            "questions": [parent],
            "save_as_composition": False,
        },
        headers=_auth(ctx["editor"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["created_count"] == 2
    questions = (await db_session.execute(select(Question))).scalars().all()
    assert all(not hasattr(question, "parent_id") for question in questions)
    assert len((await db_session.execute(select(QuestionRelation))).scalars().all()) == 1
    assert (await db_session.execute(select(Stimulus))).scalars().all() == []
    assert (await db_session.execute(select(QuestionGroup))).scalars().all() == []


async def test_explicit_material_group_persists_and_builds_ordered_composition(
    client, ctx, db_session
):
    sid = ctx["subject"].id
    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={
            "scope": "shared",
            "questions": [_question("q1", "第一小题"), _question("q2", "第二小题")],
            "stimuli": [
                {
                    "temp_id": "s1",
                    "markdown": "阅读材料 **甲**",
                    "metadata": {"source_page": 3},
                }
            ],
            "question_groups": [
                {
                    "temp_id": "g1",
                    "stimulus_temp_id": "s1",
                    "question_temp_ids": ["q2", "q1"],
                    "metadata": {"number": "12"},
                }
            ],
            "outline": [{"kind": "question_group_ref", "temp_id": "g1"}],
            "save_as_composition": True,
            "title": "材料题试卷",
            "filename": "material.md",
        },
        headers=_auth(ctx["editor"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body["stimulus_temp_id_map"]) == {"s1"}
    assert set(body["question_group_temp_id_map"]) == {"g1"}

    stimulus = (await db_session.execute(select(Stimulus))).scalars().one()
    assert json.loads(stimulus.content)["type"] == "doc"
    assert stimulus.source == "material.md"
    assert json.loads(stimulus.metadata_json) == {"source_page": 3}
    group = (await db_session.execute(select(QuestionGroup))).scalars().one()
    items = (
        await db_session.execute(
            select(QuestionGroupItem)
            .where(QuestionGroupItem.group_id == group.id)
            .order_by(QuestionGroupItem.position)
        )
    ).scalars().all()
    assert [item.question_id for item in items] == [
        body["temp_id_map"]["q2"],
        body["temp_id_map"]["q1"],
    ]

    detail = await client.get(
        f"{API}/subjects/{sid}/compositions/{body['composition_id']}?scope=shared",
        headers=_auth(ctx["editor"]),
    )
    nodes = detail.json()["nodes"]
    module = next(node for node in nodes if node["node_type"] == "question_group")
    assert module["question_group_id"] == body["question_group_temp_id_map"]["g1"]
    children = sorted(
        [node for node in nodes if node["parent_id"] == module["id"]],
        key=lambda node: node["position"],
    )
    assert [node["question_id"] for node in children] == [
        body["temp_id_map"]["q2"],
        body["temp_id_map"]["q1"],
    ]


async def test_stimulus_can_be_reused_by_two_imported_groups(client, ctx, db_session):
    sid = ctx["subject"].id
    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={
            "scope": "shared",
            "questions": [_question("q1", "题一"), _question("q2", "题二")],
            "stimuli": [{"temp_id": "s1", "markdown": "共用材料"}],
            "question_groups": [
                {"temp_id": "g1", "stimulus_temp_id": "s1", "question_temp_ids": ["q1"]},
                {"temp_id": "g2", "stimulus_temp_id": "s1", "question_temp_ids": ["q2"]},
            ],
            "save_as_composition": False,
        },
        headers=_auth(ctx["editor"]),
    )
    assert response.status_code == 200, response.text
    groups = (await db_session.execute(select(QuestionGroup))).scalars().all()
    assert len(groups) == 2
    assert len({group.stimulus_id for group in groups}) == 1


async def test_shared_stimulus_is_self_contained_per_group_and_outline_order_is_preserved(
    client, ctx
):
    sid = ctx["subject"].id
    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={
            "scope": "shared",
            "questions": [
                _question("q0", "独立题一"),
                _question("q1", "材料题一"),
                _question("q2", "材料题二"),
                _question("q3", "独立题二"),
            ],
            "stimuli": [{"temp_id": "s1", "markdown": "共用材料"}],
            "question_groups": [
                {"temp_id": "g1", "stimulus_temp_id": "s1", "question_temp_ids": ["q1"]},
                {"temp_id": "g2", "stimulus_temp_id": "s1", "question_temp_ids": ["q2"]},
            ],
            "outline": [
                {"kind": "question_ref", "temp_id": "q0"},
                {"kind": "question_group_ref", "temp_id": "g1"},
                {"kind": "question_ref", "temp_id": "q3"},
                {"kind": "question_group_ref", "temp_id": "g2"},
            ],
            "save_as_composition": True,
            "title": "共用材料试卷",
        },
        headers=_auth(ctx["editor"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    detail = await client.get(
        f"{API}/subjects/{sid}/compositions/{body['composition_id']}?scope=shared",
        headers=_auth(ctx["editor"]),
    )
    nodes = detail.json()["nodes"]
    roots = sorted(
        [node for node in nodes if node["parent_id"] is None],
        key=lambda node: node["position"],
    )
    assert [node["node_type"] for node in roots] == [
        "question", "question_group", "question", "question_group"
    ]
    groups = [node for node in roots if node["node_type"] == "question_group"]
    assert groups[0]["content"] == groups[1]["content"]
    assert groups[0]["content"]["content"][0]["content"][0]["text"] == "共用材料"
    assert [
        next(
            node["question_id"] for node in nodes
            if node["parent_id"] == group["id"] and node["node_type"] == "question"
        )
        for group in groups
    ] == [body["temp_id_map"]["q1"], body["temp_id_map"]["q2"]]


async def test_fallback_outline_follows_extraction_question_order(client, ctx):
    sid = ctx["subject"].id
    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={
            "scope": "shared",
            "questions": [
                _question("q0", "独立题一"),
                _question("q1", "材料题"),
                _question("q2", "独立题二"),
            ],
            "stimuli": [{"temp_id": "s1", "markdown": "材料"}],
            "question_groups": [
                {"temp_id": "g1", "stimulus_temp_id": "s1", "question_temp_ids": ["q1"]}
            ],
            "outline": [],
            "save_as_composition": True,
            "title": "回退顺序",
        },
        headers=_auth(ctx["editor"]),
    )
    body = response.json()
    detail = await client.get(
        f"{API}/subjects/{sid}/compositions/{body['composition_id']}?scope=shared",
        headers=_auth(ctx["editor"]),
    )
    nodes = detail.json()["nodes"]
    roots = sorted(
        [node for node in nodes if node["parent_id"] is None],
        key=lambda node: node["position"],
    )
    assert [node["node_type"] for node in roots] == [
        "question", "question_group", "question"
    ]
    assert roots[0]["question_id"] == body["temp_id_map"]["q0"]
    assert roots[2]["question_id"] == body["temp_id_map"]["q2"]
    group_child = next(node for node in nodes if node["parent_id"] == roots[1]["id"])
    assert group_child["question_id"] == body["temp_id_map"]["q1"]


async def test_bad_group_temp_reference_fails_before_any_write(client, ctx, db_session):
    sid = ctx["subject"].id
    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={
            "scope": "shared",
            "questions": [_question("q1", "题一")],
            "stimuli": [{"temp_id": "s1", "markdown": "材料"}],
            "question_groups": [
                {
                    "temp_id": "g1",
                    "stimulus_temp_id": "s1",
                    "question_temp_ids": ["missing"],
                }
            ],
            "save_as_composition": False,
        },
        headers=_auth(ctx["editor"]),
    )
    assert response.status_code == 422, response.text
    assert "不存在的题目 temp_id" in response.json()["detail"]
    assert (await db_session.execute(select(Question))).scalars().all() == []
    assert (await db_session.execute(select(Stimulus))).scalars().all() == []
    assert (await db_session.execute(select(QuestionGroup))).scalars().all() == []
    assert (await db_session.execute(select(ImportTask))).scalars().all() == []


@pytest.mark.parametrize(
    ("outline", "message"),
    [
        ([{"kind": "question_ref", "temp_id": "missing"}], "不存在的题目 temp_id"),
        ([{"kind": "question_group_ref", "temp_id": "missing"}], "不存在的题组 temp_id"),
    ],
)
async def test_missing_outline_reference_fails_before_any_write(
    client, ctx, db_session, outline, message
):
    sid = ctx["subject"].id
    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={
            "scope": "shared",
            "questions": [_question("q1", "题一")],
            "outline": outline,
            "save_as_composition": True,
            "title": "坏引用",
        },
        headers=_auth(ctx["editor"]),
    )
    assert response.status_code == 422, response.text
    assert message in response.json()["detail"]
    assert (await db_session.execute(select(ImportTask))).scalars().all() == []
    assert (await db_session.execute(select(Question))).scalars().all() == []


@pytest.mark.parametrize("save_as_composition", [False, True])
async def test_question_subject_must_match_url_subject(
    client, ctx, db_session, save_as_composition
):
    other = await _seed_subject(db_session, name="物理", slug="physics")
    sid = ctx["subject"].id
    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={
            "scope": "shared",
            "questions": [_question("q1", "跨学科题", subject_id=other.id)],
            "outline": [{"kind": "question_ref", "temp_id": "q1"}],
            "save_as_composition": save_as_composition,
            "title": "跨学科" if save_as_composition else None,
        },
        headers=_auth(ctx["editor"]),
    )
    assert response.status_code == 422, response.text
    assert "subject_id" in response.json()["detail"]
    assert (await db_session.execute(select(ImportTask))).scalars().all() == []
    assert (await db_session.execute(select(Question))).scalars().all() == []


async def test_replace_nodes_failure_rolls_back_all_import_entities(
    client, ctx, db_session, monkeypatch
):
    from app.services import composition_service

    async def fail_replace_nodes(*args, **kwargs):
        raise RuntimeError("forced node failure")

    monkeypatch.setattr(composition_service, "replace_nodes", fail_replace_nodes)
    sid = ctx["subject"].id
    with pytest.raises(RuntimeError, match="forced node failure"):
        await client.post(
            f"{API}/subjects/{sid}/paper-imports",
            json={
                "scope": "shared",
                "questions": [
                    _question("parent", "材料题"),
                    _question("child", "子题", parent_temp_id="parent"),
                ],
                "stimuli": [{"temp_id": "s1", "markdown": "材料"}],
                "question_groups": [
                    {
                        "temp_id": "g1",
                        "stimulus_temp_id": "s1",
                        "question_temp_ids": ["child"],
                    }
                ],
                "outline": [{"kind": "question_group_ref", "temp_id": "g1"}],
                "save_as_composition": True,
                "title": "应回滚",
            },
            headers=_auth(ctx["editor"]),
        )

    for model in (
        ImportTask,
        Question,
        QuestionRelation,
        Stimulus,
        QuestionGroup,
        Composition,
        CompositionNode,
    ):
        assert (await db_session.execute(select(model))).scalars().all() == []


async def test_preview_reports_duplicate_group_question_reference(client, ctx):
    sid = ctx["subject"].id
    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports/preview",
        json={
            "scope": "shared",
            "questions": [_question("q1", "题一")],
            "stimuli": [{"temp_id": "s1", "markdown": "材料"}],
            "question_groups": [
                {
                    "temp_id": "g1",
                    "stimulus_temp_id": "s1",
                    "question_temp_ids": ["q1", "q1"],
                }
            ],
        },
        headers=_auth(ctx["editor"]),
    )
    assert response.status_code == 200, response.text
    assert "重复的题目引用" in response.json()["blocking_reason"]


# --------------------------------------------------------------------------- #
# 私有题与共享空间
# --------------------------------------------------------------------------- #
async def test_private_question_blocked_from_shared_composition(client, ctx, db_session):
    sid = ctx["subject"].id

    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={
            "scope": "shared",
            "questions": [_question("t1", "私有题", visibility="private")],
            "outline": [{"kind": "question_ref", "temp_id": "t1"}],
            "save_as_composition": True,
            "title": "共享稿件",
        },
        headers=_auth(ctx["editor"]),
    )

    assert response.status_code == 422
    assert "私有题" in response.json()["detail"]
    # 被拒绝时不得留下任何题目。
    assert (await db_session.execute(select(Question))).scalars().all() == []


async def test_private_question_allowed_in_personal_space(client, ctx):
    sid = ctx["subject"].id

    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={
            "scope": "personal",
            "questions": [_question("t1", "私有题", visibility="private")],
            "outline": [{"kind": "question_ref", "temp_id": "t1"}],
            "save_as_composition": True,
            "title": "我的试卷",
        },
        headers=_auth(ctx["editor"]),
    )

    assert response.status_code == 200, response.text
    assert response.json()["composition_id"] is not None


# --------------------------------------------------------------------------- #
# 部分失败由用户决定
# --------------------------------------------------------------------------- #
async def test_partial_failure_is_rejected_until_user_decides(client, ctx, db_session):
    sid = ctx["subject"].id

    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={
            "scope": "shared",
            "questions": [_question("t1", "好题"), _broken_question("bad")],
            "outline": [
                {"kind": "question_ref", "temp_id": "t1"},
                {"kind": "question_ref", "temp_id": "bad"},
            ],
            "save_as_composition": True,
            "title": "含坏题",
            "proceed_with_partial": False,
        },
        headers=_auth(ctx["editor"]),
    )

    assert response.status_code == 422
    assert "未能入库" in response.json()["detail"]
    assert (await db_session.execute(select(Question))).scalars().all() == []


async def test_partial_failure_proceeds_when_user_confirms(client, ctx):
    sid = ctx["subject"].id

    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={
            "scope": "shared",
            "questions": [_question("t1", "好题"), _broken_question("bad")],
            "outline": [
                {"kind": "question_ref", "temp_id": "t1"},
                {"kind": "question_ref", "temp_id": "bad"},
            ],
            "save_as_composition": True,
            "title": "含坏题",
            "proceed_with_partial": True,
        },
        headers=_auth(ctx["editor"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created_count"] == 1
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["temp_id"] == "bad"
    assert body["composition_id"] is not None


# --------------------------------------------------------------------------- #
# 幂等
# --------------------------------------------------------------------------- #
async def test_replay_with_same_idempotency_key_does_not_duplicate(client, ctx, db_session):
    sid = ctx["subject"].id
    payload = {
        "scope": "shared",
        "questions": [_question("t1", "唯一题")],
        "outline": [{"kind": "question_ref", "temp_id": "t1"}],
        "save_as_composition": True,
        "title": "幂等试卷",
        "idempotency_key": "fixed-key-001",
    }
    headers = _auth(ctx["editor"])

    first = await client.post(f"{API}/subjects/{sid}/paper-imports", json=payload, headers=headers)
    second = await client.post(f"{API}/subjects/{sid}/paper-imports", json=payload, headers=headers)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["reused_existing"] is True
    assert second.json()["composition_id"] == first.json()["composition_id"]
    for field in (
        "created_count",
        "created_question_ids",
        "skipped",
        "degraded",
        "composition_id",
        "composition_title",
        "temp_id_map",
        "stimulus_temp_id_map",
        "question_group_temp_id_map",
    ):
        assert second.json()[field] == first.json()[field]

    assert len((await db_session.execute(select(Question))).scalars().all()) == 1
    assert len((await db_session.execute(select(Composition))).scalars().all()) == 1


# --------------------------------------------------------------------------- #
# 权限
# --------------------------------------------------------------------------- #
async def test_viewer_cannot_import(client, ctx, db_session):
    sid = ctx["subject"].id

    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={
            "scope": "shared",
            "questions": [_question("t1", "题")],
            "outline": [{"kind": "question_ref", "temp_id": "t1"}],
            "save_as_composition": True,
            "title": "越权",
        },
        headers=_auth(ctx["viewer"]),
    )

    assert response.status_code == 403
    assert (await db_session.execute(select(Question))).scalars().all() == []


async def test_outsider_cannot_import(client, ctx):
    sid = ctx["subject"].id

    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports",
        json={
            "scope": "shared",
            "questions": [_question("t1", "题")],
            "outline": [{"kind": "question_ref", "temp_id": "t1"}],
            "save_as_composition": False,
        },
        headers=_auth(ctx["outsider"]),
    )

    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# 预检
# --------------------------------------------------------------------------- #
async def test_preview_reports_blocking_and_degraded_without_writing(client, ctx, db_session):
    sid = ctx["subject"].id

    response = await client.post(
        f"{API}/subjects/{sid}/paper-imports/preview",
        json={
            "scope": "shared",
            "questions": [_question("t1", "私有题", visibility="private")],
            "outline": [
                {"kind": "question_ref", "temp_id": "t1"},
                {"kind": "degraded", "markdown": "复杂表格", "reason": "表格结构无法完整表达"},
            ],
        },
        headers=_auth(ctx["editor"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["importable_count"] == 1
    assert "私有题" in body["blocking_reason"]
    assert body["degraded"][0]["reason"] == "表格结构无法完整表达"
    # 预检不写库。
    assert (await db_session.execute(select(Question))).scalars().all() == []
