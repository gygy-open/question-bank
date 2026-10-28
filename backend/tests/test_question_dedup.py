"""题目查重:签名维护钩子、候选查询与回填。"""
import json

import pytest
from sqlalchemy import select

from app.models.question import Question, QuestionDedupBand, QuestionVisibility
from app.models.stimulus import Stimulus
from app.models.subject import Subject
from app.models.subject_member import SubjectMember
from app.models.user import User
from app.services import question_dedup
from app.services.question_dedup_core import DEDUP_VERSION, BANDS
from app.services.question_dedup import BatchItem, find_duplicates, find_duplicates_batch, key_from_payload

LONG = "在三角形 ABC 中，已知角 A 等于六十度，边 BC 的长度为二，求三角形面积的最大值。"


def doc(text):
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


@pytest.fixture
async def env(db_session):
    alice = User(username="alice", hashed_password="x", is_active=True)
    bob = User(username="bob", hashed_password="x", is_active=True)
    math = Subject(name="数学", slug="math")
    phys = Subject(name="物理", slug="phys")
    db_session.add_all([alice, bob, math, phys])
    await db_session.commit()
    for user in (alice, bob):
        db_session.add(SubjectMember(user_id=user.id, subject_id=math.id, role="editor"))
    await db_session.commit()
    from app.crud import crud_user
    alice = await crud_user.user.get_with_memberships(db_session, id=alice.id)
    bob = await crud_user.user.get_with_memberships(db_session, id=bob.id)
    return {"alice": alice, "bob": bob, "math": math, "phys": phys}


async def add_question(db, *, subject, user, text, q_type="free_response", **kw):
    q = Question(
        content=json.dumps(doc(text), ensure_ascii=False),
        q_type=q_type,
        subject_id=subject.id,
        created_by=user.id,
        **kw,
    )
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return q


async def bands_of(db, qid):
    return (await db.execute(select(QuestionDedupBand).where(QuestionDedupBand.question_id == qid))).scalars().all()


async def test_hook_maintains_signature_and_bands(db_session, env):
    q = await add_question(db_session, subject=env["math"], user=env["alice"], text=LONG)
    assert q.dedup_version == DEDUP_VERSION
    assert len(q.dedup_fingerprint) == 64
    assert "三角形" in q.dedup_text
    bands = await bands_of(db_session, q.id)
    assert len(bands) == BANDS and all(b.subject_id == env["math"].id for b in bands)

    old = q.dedup_fingerprint
    q.content = json.dumps(doc(LONG + "并说明理由"), ensure_ascii=False)
    await db_session.commit()
    await db_session.refresh(q)
    assert q.dedup_fingerprint != old
    assert len(await bands_of(db_session, q.id)) == BANDS


async def test_unrelated_update_keeps_signature(db_session, env):
    q = await add_question(db_session, subject=env["math"], user=env["alice"], text=LONG)
    before = (q.dedup_fingerprint, [b.hash for b in await bands_of(db_session, q.id)])
    q.status = "published"
    await db_session.commit()
    assert (q.dedup_fingerprint, [b.hash for b in await bands_of(db_session, q.id)]) == before


async def test_stimulus_change_recomputes_children(db_session, env):
    stim = Stimulus(subject_id=env["math"].id, content=json.dumps(doc("材料甲"), ensure_ascii=False))
    db_session.add(stim)
    await db_session.commit()
    q = await add_question(db_session, subject=env["math"], user=env["alice"], text="(1) 求 x 的值",
                           stimulus_id=stim.id, stimulus_position=0)
    assert "材料甲" in q.dedup_text
    stim.content = json.dumps(doc("材料乙"), ensure_ascii=False)
    await db_session.commit()
    await db_session.refresh(q)
    assert "材料乙" in q.dedup_text


async def test_find_duplicates_levels_and_visibility(db_session, env):
    math, alice, bob = env["math"], env["alice"], env["bob"]
    exact = await add_question(db_session, subject=math, user=alice, text="1. " + LONG)
    similar = await add_question(db_session, subject=math, user=alice, text=LONG.replace("长度为", "长为"))
    variant = await add_question(db_session, subject=math, user=alice, text=LONG.replace("ABC", "ABD") + " 12")
    other_type = await add_question(db_session, subject=math, user=alice, text=LONG, q_type="single_choice")
    private = await add_question(db_session, subject=math, user=bob, text=LONG,
                                 visibility=QuestionVisibility.PRIVATE.value)
    other_subject = await add_question(db_session, subject=env["phys"], user=alice, text=LONG)

    key = key_from_payload(q_type="free_response", content=doc(LONG))
    found = await find_duplicates(db_session, viewer=alice, subject_id=math.id, key=key)
    by_id = {c.question_id: c for c in found}
    assert by_id[exact.id].level == "duplicate" and by_id[exact.id].similarity == 1.0
    assert by_id[similar.id].level == "similar" and not by_id[similar.id].variant
    assert by_id[similar.id].diff
    assert other_type.id not in by_id and private.id not in by_id and other_subject.id not in by_id
    assert found[0].question_id == exact.id
    if variant.id in by_id:
        assert by_id[variant.id].variant

    # 私有题对创建者可见
    found_bob = await find_duplicates(db_session, viewer=bob, subject_id=math.id, key=key)
    assert private.id in {c.question_id for c in found_bob}

    # 排除自身 / 软删除
    found = await find_duplicates(db_session, viewer=alice, subject_id=math.id, key=key, exclude_ids=[exact.id])
    assert exact.id not in {c.question_id for c in found}
    from datetime import datetime
    similar.deleted_at = datetime.utcnow()
    await db_session.commit()
    found = await find_duplicates(db_session, viewer=alice, subject_id=math.id, key=key)
    assert similar.id not in {c.question_id for c in found}


async def test_short_questions_match_only_exactly(db_session, env):
    q = await add_question(db_session, subject=env["math"], user=env["alice"], text="1+1=?")
    hit = await find_duplicates(db_session, viewer=env["alice"], subject_id=env["math"].id,
                                key=key_from_payload(q_type="free_response", content=doc("1 + 1 = ？")))
    assert [c.question_id for c in hit] == [q.id]
    miss = await find_duplicates(db_session, viewer=env["alice"], subject_id=env["math"].id,
                                 key=key_from_payload(q_type="free_response", content=doc("1+2=?")))
    assert miss == []


async def test_batch_and_intra_batch(db_session, env):
    await add_question(db_session, subject=env["math"], user=env["alice"], text=LONG)
    items = [
        BatchItem("a", key_from_payload(q_type="free_response", content=doc(LONG))),
        BatchItem("b", key_from_payload(q_type="free_response", content=doc("全新的一道题目，描述某个完全不同的场景与问题"))),
        BatchItem("c", key_from_payload(q_type="free_response", content=doc("全新的一道题目，描述某个完全不同的场景与问题。"))),
    ]
    existing, intra = await find_duplicates_batch(db_session, viewer=env["alice"], subject_id=env["math"].id, items=items)
    assert set(existing) == {"a"}
    assert intra == {"c": [{"ref": "b", "level": "duplicate", "similarity": 1.0}]}


async def test_backfill(db_session, env):
    q = await add_question(db_session, subject=env["math"], user=env["alice"], text=LONG)
    # 模拟存量:清掉签名与分桶
    q.dedup_fingerprint = None
    q.dedup_text = None
    await db_session.commit()
    from sqlalchemy import update, delete
    await db_session.execute(update(Question).values(dedup_version=None, dedup_fingerprint=None))
    await db_session.execute(delete(QuestionDedupBand))
    await db_session.commit()
    db_session.expire_all()

    assert await question_dedup.backfill(db_session) == 1
    q = await db_session.get(Question, q.id)
    assert q.dedup_version == DEDUP_VERSION and q.dedup_fingerprint
    assert len(await bands_of(db_session, q.id)) == BANDS
    assert await question_dedup.backfill(db_session) == 0
