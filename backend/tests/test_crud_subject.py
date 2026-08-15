import pytest

from app.crud.crud_subject import subject as crud_subject
from app.schemas.subject import SubjectCreate, SubjectUpdate


async def test_create_and_get(db_session):
    created = await crud_subject.create(
        db_session, obj_in=SubjectCreate(name="数学", slug="math")
    )

    assert created.id is not None
    fetched = await crud_subject.get(db_session, created.id)
    assert fetched is not None
    assert fetched.name == "数学"
    assert fetched.slug == "math"


async def test_get_multi(db_session):
    await crud_subject.create(db_session, obj_in=SubjectCreate(name="语文", slug="chinese"))
    await crud_subject.create(db_session, obj_in=SubjectCreate(name="英语", slug="english"))

    rows = await crud_subject.get_multi(db_session)

    assert {r.slug for r in rows} == {"chinese", "english"}


async def test_update(db_session):
    created = await crud_subject.create(
        db_session, obj_in=SubjectCreate(name="物理", slug="physics")
    )

    updated = await crud_subject.update(
        db_session, db_obj=created, obj_in=SubjectUpdate(name="高中物理")
    )

    assert updated.name == "高中物理"
    assert updated.slug == "physics"


async def test_remove(db_session):
    created = await crud_subject.create(
        db_session, obj_in=SubjectCreate(name="化学", slug="chemistry")
    )

    await crud_subject.remove(db_session, id=created.id)

    assert await crud_subject.get(db_session, created.id) is None
