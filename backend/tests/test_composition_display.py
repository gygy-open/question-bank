from app.models.composition import CompositionBlock, BlockType
from app.models.question import Question, QuestionType
from app.services.composition_renderer import composition_renderer
from app.services.composition_display import (
    make_display,
    resolve_region,
    REGION_INLINE,
    REGION_APPENDIX,
    REGION_HIDDEN,
)


def _q(qid: int = 1) -> Question:
    return Question(
        id=qid,
        content="题干",
        q_type=QuestionType.FREE_RESPONSE,
        answer="42",
        thinking="分析内容",
        analysis="解析内容",
        summary="小结",
        source="来源出处",
        difficulty=1,
    )


def _block(q: Question, display=None) -> CompositionBlock:
    content = {}
    if display is not None:
        content["display"] = display
    return CompositionBlock(
        block_type=BlockType.QUESTION.value, sequence=0, content=content, question=q
    )


def test_resolve_region_cascade():
    doc = make_display({"answer": REGION_APPENDIX, "analysis": REGION_HIDDEN})
    block = {"fields": {"answer": {"region": REGION_INLINE}}}

    assert resolve_region("answer", block, doc) == REGION_INLINE       # 题块覆盖胜
    assert resolve_region("analysis", block, doc) == REGION_HIDDEN      # 落到文档默认
    assert resolve_region("summary", None, None) == REGION_HIDDEN       # 系统兜底


def test_inline_before_appendix():
    doc = make_display({"answer": REGION_INLINE, "explanation": REGION_APPENDIX})
    md = composition_renderer.generate_markdown("卷", [_block(_q())], doc_display=doc)

    assert "【答案】" in md
    assert "参考答案与解析" in md
    assert "【解析】" in md
    assert md.index("【答案】") < md.index("参考答案与解析") < md.index("【解析】")


def test_block_override_forces_inline():
    doc = make_display({"answer": REGION_HIDDEN})
    block = _block(_q(), display={"fields": {"answer": {"region": REGION_INLINE}}})

    md = composition_renderer.generate_markdown("卷", [block], doc_display=doc)

    assert "【答案】" in md
    assert "参考答案与解析" not in md


def test_hidden_fields_absent():
    doc = make_display({})  # 全部兜底 hidden
    md = composition_renderer.generate_markdown("卷", [_block(_q())], doc_display=doc)

    assert "【答案】" not in md
    assert "参考答案与解析" not in md
