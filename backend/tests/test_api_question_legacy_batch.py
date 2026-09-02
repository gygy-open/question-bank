import json

from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.models.question import Question
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

