"""Phase 2 单测:抽取阶段拆分件(temp_id 分配、PromptBuilder tag 注入)。"""

from app.models.subject import Subject
from app.models.tag import Tag
from app.models.tag_category import TagCategory
from app.services.importing.extract import _assign_temp_ids
from app.services.importing.prompt import PromptBuilder


def test_assign_temp_ids_fills_and_links_children():
    items = [
        {"content": "材料题", "children": [{"content": "子题1"}, {"content": "子题2"}]},
        {"content": "独立题", "id": "keep-me"},
    ]
    out = _assign_temp_ids(items)

    parent = out[0]
    assert parent["id"]
    for child in parent["children"]:
        assert child["id"]
        assert child["parent_id"] == parent["id"]
    # 已有 id 的题保持不变。
    assert out[1]["id"] == "keep-me"
    assert "parent_id" not in out[1]


async def test_prompt_builder_injects_tag_context(db_session):
    subject = Subject(name="数学", slug="math")
    db_session.add(subject)
    await db_session.commit()
    await db_session.refresh(subject)

    category = TagCategory(name="年份", subject_id=subject.id, sort_order=1)
    db_session.add(category)
    await db_session.commit()
    await db_session.refresh(category)
    db_session.add(Tag(name="2024", category_id=category.id, subject_id=subject.id))
    await db_session.commit()

    prompt = await PromptBuilder().build(db_session, mode="extract", subject_id=None)

    # 分类与标签都进入 prompt 上下文。
    assert "年份" in prompt
    assert "2024" in prompt
