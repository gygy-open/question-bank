import json

from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.models.question import Question
from app.models.question_group import QuestionRelation
from app.models.subject import Subject
from app.models.user import User


async def test_legacy_batch_partially_succeeds_without_persisting_unresolved(
    client,
    db_session,
):
    user = User(
        username="legacy-importer",
        full_name="Legacy Importer",
        hashed_password=get_password_hash("s3cret"),
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    token = create_access_token(subject=user.id)

    response = await client.post(
        "/api/v1/questions/batch-legacy",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "filename": "legacy.md",
            "questions": [
                {
                    "content": "计算 **1 + 1**。",
                    "q_type": "free_response",
                    "answer": "答案是 $2$。",
                    "difficulty": 1,
                },
                {
                    "content": "无法确定答案的选择题",
                    "q_type": "single_choice",
                    "options": ["A. 甲", "B. 乙"],
                    "answer": "见解析",
                    "difficulty": 2,
                },
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["import_task_id"] is not None
    assert len(body["created"]) == 1
    assert body["failed"] == [
        {"index": 1, "message": "single_choice 答案无法解析为 v2(原文: '见解析'),需人工复核"}
    ]
    assert body["created"][0]["content"]["type"] == "doc"
    assert body["created"][0]["answer"]["kind"] == "free_response"

    rows = (await db_session.execute(select(Question))).scalars().all()
    assert len(rows) == 1
    assert rows[0].content_schema_version == 1
    assert rows[0].needs_review is False
    assert json.loads(rows[0].content)["type"] == "doc"
    assert json.loads(rows[0].answer)["kind"] == "free_response"


async def test_batch_nested_children_create_relations_without_parent_id(
    client, db_session
):
    subject = Subject(name="数学", slug="batch-math")
    user = User(
        username="batch-importer",
        full_name="Batch Importer",
        hashed_password=get_password_hash("s3cret"),
        is_active=True,
        is_superuser=False,
    )
    db_session.add_all([subject, user])
    await db_session.flush()
    user.last_active_subject_id = subject.id
    await db_session.commit()
    token = create_access_token(subject=user.id)

    def question(content: str) -> dict:
        return {
            "q_type": "free_response",
            "content": {
                "type": "doc",
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": content}]}
                ],
            },
            "answer": {"kind": "free_response", "reference": None},
            "difficulty": 1,
            "subject_id": subject.id,
        }

    parent = question("母题")
    parent["children"] = [question("子题")]
    response = await client.post(
        "/api/v1/questions/batch",
        headers={"Authorization": f"Bearer {token}"},
        json={"filename": "nested.json", "questions": [parent]},
    )

    assert response.status_code == 200, response.text
    rows = (await db_session.execute(select(Question).order_by(Question.id))).scalars().all()
    assert len(rows) == 2
    assert all(row.parent_id is None for row in rows)
    relation = (await db_session.execute(select(QuestionRelation))).scalars().one()
    assert relation.source_question_id == rows[0].id
    assert relation.target_question_id == rows[1].id

