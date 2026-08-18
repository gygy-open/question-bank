from app.crud.crud_composition import composition as crud_comp
from app.crud.crud_folder import folder as crud_folder
from app.models.composition import BlockType, FolderScope
from app.models.subject import Subject
from app.schemas.composition import CompositionCreate, BlockWrite
from app.services.composition_templates import SYSTEM_TEMPLATES


async def _seed_subject(db_session):
    subject = Subject(name="数学", slug="math")
    db_session.add(subject)
    await db_session.commit()
    await db_session.refresh(subject)
    return subject


async def _root(db_session, subject_id):
    return await crud_folder.ensure_root(
        db_session, owner_id=1, subject_id=subject_id, scope=FolderScope.PERSONAL.value
    )


async def test_create_from_system_template_seeds_settings(db_session):
    subject = await _seed_subject(db_session)
    root = await _root(db_session, subject.id)
    tpl = SYSTEM_TEMPLATES["exam_paper"]

    comp = await crud_comp.create_from_system_template(
        db_session, template=tpl, title="期中卷", folder_id=root.id, owner_id=1
    )

    assert comp.meta_data == tpl.meta_data
    assert comp.is_template is False


async def test_save_as_template_lists_and_excludes_from_normal(db_session):
    subject = await _seed_subject(db_session)
    comp = await crud_comp.create_for_owner(
        db_session,
        obj_in=CompositionCreate(title="原稿", subject_id=subject.id),
        owner_id=1,
        subject_id=subject.id,
    )
    await crud_comp.replace_blocks(
        db_session,
        composition=comp,
        blocks=[BlockWrite(block_type=BlockType.TEXT, content={"text": "hi"})],
    )
    root = await _root(db_session, subject.id)

    tpl = await crud_comp.duplicate(
        db_session, composition=comp, title="我的模板", folder_id=root.id, owner_id=1, is_template=True
    )
    assert tpl.is_template is True

    template_ids = [t.id for t in await crud_comp.list_templates(
        db_session, subject_id=subject.id, owner_id=1
    )]
    assert tpl.id in template_ids

    normal_ids = [c.id for c in await crud_comp.list(db_session, subject_id=subject.id)]
    assert comp.id in normal_ids
    assert tpl.id not in normal_ids


async def test_duplicate_deep_copies_blocks(db_session):
    subject = await _seed_subject(db_session)
    comp = await crud_comp.create_for_owner(
        db_session,
        obj_in=CompositionCreate(title="原稿", subject_id=subject.id),
        owner_id=1,
        subject_id=subject.id,
    )
    await crud_comp.replace_blocks(
        db_session,
        composition=comp,
        blocks=[BlockWrite(block_type=BlockType.TEXT, content={"text": "hi"})],
    )

    dup = await crud_comp.duplicate(db_session, composition=comp)

    assert dup.id != comp.id
    dup_blocks = await crud_comp.get_ordered_blocks(db_session, comp_id=dup.id)
    assert len(dup_blocks) == 1
    assert dup_blocks[0].content == {"text": "hi"}
