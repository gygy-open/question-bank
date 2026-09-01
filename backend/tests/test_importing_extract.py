"""Phase 2 单测:抽取阶段拆分件(temp_id 分配、PromptBuilder tag 注入、图片遮罩还原)。"""

import app.services.importing.extract as extract_module
from app.models.subject import Subject
from app.models.tag import Tag
from app.models.tag_category import TagCategory
from app.schemas.ai import AIQuestion
from app.services.importing.extract import AIExtractor, _assign_temp_ids
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


class _StubPromptBuilder:
    async def build(self, db, *, mode, subject_id):
        return "STUB_PROMPT"


class _StubEnricher:
    async def enrich(self, questions, *, subject_id, provider, config):
        return None


class _StubProvider:
    def __init__(self, questions):
        self._questions = questions
        self.received_content = None

    async def extract_questions(self, content, image_data=None, config=None):
        self.received_content = content
        return self._questions


async def test_extract_masks_images_before_ai_and_restores_after(monkeypatch, db_session):
    original_image = '![](/static/media/t1/a.png){width="1.59in" height="1.18in"}'
    doc_content = f"第一题：见图 {original_image}\n"

    stub_provider = _StubProvider(
        [AIQuestion(q_type="single_choice", content="第一题：见图 @@IMG0@@")]
    )

    async def _stub_resolve_active_provider(db, *, is_vision=False):
        return "gemini", {}

    monkeypatch.setattr(extract_module, "resolve_active_provider", _stub_resolve_active_provider)
    monkeypatch.setattr(extract_module, "get_ai_provider", lambda name: stub_provider)

    extractor = AIExtractor(prompt_builder=_StubPromptBuilder(), enricher=_StubEnricher())
    result = await extractor.extract(doc_content, db_session, mode="extract", subject_id=None)

    # AI 实际收到的内容不含真实图片路径/尺寸,只有占位符。
    assert original_image not in stub_provider.received_content
    assert "@@IMG0@@" in stub_provider.received_content

    # 还原后的题目 content 里包含完整原始图片 token。
    assert original_image in result[0]["content"]


async def test_extract_strips_hallucinated_placeholder_not_in_map(monkeypatch, db_session):
    """真实场景复现:文档只有 1 张图,但 AI 额外幻觉出一个不存在的 @@IMG1@@ 编号。"""
    original_image = "![](/static/media/t1/a.png)"
    doc_content = f"第一题：见图 {original_image}\n"

    stub_provider = _StubProvider(
        [
            AIQuestion(
                q_type="single_choice",
                content="第一题：见图 @@IMG0@@",
                options=["A. 正常选项", "B. 幻觉图 @@IMG1@@"],
            )
        ]
    )

    async def _stub_resolve_active_provider(db, *, is_vision=False):
        return "gemini", {}

    monkeypatch.setattr(extract_module, "resolve_active_provider", _stub_resolve_active_provider)
    monkeypatch.setattr(extract_module, "get_ai_provider", lambda name: stub_provider)

    extractor = AIExtractor(prompt_builder=_StubPromptBuilder(), enricher=_StubEnricher())
    result = await extractor.extract(doc_content, db_session, mode="extract", subject_id=None)

    # 真实存在的占位符被正确还原。
    assert result[0]["content"] == f"第一题：见图 {original_image}"
    # 幻觉出的占位符不会原样落库,只是被清掉。
    assert "@@IMG1@@" not in result[0]["options"][1]
    assert result[0]["options"][1] == "B. 幻觉图 "


async def test_extract_recovers_when_ai_writes_wrong_placeholder_number(monkeypatch, db_session):
    """真实场景复现:文档有 2 张图,AI 把第 2 张的编号写错(如 @@IMG1@@ → @@IMG2@@),
    但第一张编号是对的。应按出现顺序把写错编号的占位符补配给唯一未被引用的图。"""
    image_a = "![](/static/media/t1/a.png)"
    image_b = '![](/static/media/t1/b.png){width="3in"}'
    doc_content = f"第一题：见图 {image_a}\n\n第二题：见图 {image_b}\n"

    stub_provider = _StubProvider(
        [
            AIQuestion(q_type="single_choice", content="第一题：见图 @@IMG0@@"),
            # 正确编号应为 @@IMG1@@,这里模拟 AI 写错成不存在的 @@IMG2@@。
            AIQuestion(q_type="single_choice", content="第二题：见图 @@IMG2@@"),
        ]
    )

    async def _stub_resolve_active_provider(db, *, is_vision=False):
        return "gemini", {}

    monkeypatch.setattr(extract_module, "resolve_active_provider", _stub_resolve_active_provider)
    monkeypatch.setattr(extract_module, "get_ai_provider", lambda name: stub_provider)

    extractor = AIExtractor(prompt_builder=_StubPromptBuilder(), enricher=_StubEnricher())
    result = await extractor.extract(doc_content, db_session, mode="extract", subject_id=None)

    assert result[0]["content"] == f"第一题：见图 {image_a}"
    assert result[1]["content"] == f"第二题：见图 {image_b}"


async def test_extract_without_images_is_a_no_op_for_masking(monkeypatch, db_session):
    stub_provider = _StubProvider([AIQuestion(q_type="single_choice", content="没有图片的题目")])

    async def _stub_resolve_active_provider(db, *, is_vision=False):
        return "gemini", {}

    monkeypatch.setattr(extract_module, "resolve_active_provider", _stub_resolve_active_provider)
    monkeypatch.setattr(extract_module, "get_ai_provider", lambda name: stub_provider)

    extractor = AIExtractor(prompt_builder=_StubPromptBuilder(), enricher=_StubEnricher())
    result = await extractor.extract("没有图片的内容", db_session, mode="extract", subject_id=None)

    assert "没有图片的内容" in stub_provider.received_content
    assert result[0]["content"] == "没有图片的题目"
