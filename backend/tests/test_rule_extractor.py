"""规则抽取器的行为测试：零 AI、零数据库。

关键断言是"不碰模型"——这条路径的价值就在于它不需要 AI 配置、不依赖提示词、
不会因为上游 502 而失败。
"""
import asyncio
import inspect

import pytest

from app.services.importing import markdown_rules
from app.services.importing.markdown_rules import RuleBasedExtractor, build_questions, split_segments

PLAIN = """1. 已知 $x=1$，求 $x+1$ 的值。

A. 1 B. 2 C. 3 D. 4

2. 方程 $x^2-1=0$ 的解是（B）

A. $x=1$ B. $x=\\pm 1$ C. $x=0$ D. 无解
"""


def _run(text, **kwargs):
    return asyncio.run(RuleBasedExtractor().extract(text, db=None, **kwargs))


# --------------------------------------------------------------------------- #
# 零 AI
# --------------------------------------------------------------------------- #
def test_module_does_not_import_any_model_client():
    source = inspect.getsource(markdown_rules)

    for forbidden in ("ai_provider", "AsyncOpenAI", "KnowledgePointEnricher", "openai"):
        assert forbidden not in source, f"规则抽取不应该依赖 {forbidden}"


def test_extract_runs_without_db_or_provider():
    """db=None、没有任何模型配置也能跑 —— 这条路径在离线环境下可用。"""
    result = _run(PLAIN)

    assert len(result.questions) == 2
    assert result.paper is None
    assert result.stimuli == []


# --------------------------------------------------------------------------- #
# 抽取正确性
# --------------------------------------------------------------------------- #
def test_answers_come_only_from_source_markers():
    result = _run(PLAIN)
    first, second = result.questions

    # 第 1 题原文没写答案 → 留空（等做题阶段处理）
    assert not first["answer"]
    # 第 2 题原文有 (B) → 脚本剥出来
    assert second["answer"] == "B"


def test_options_and_type_inferred_from_structure():
    result = _run(PLAIN)
    first, second = result.questions

    assert len(first["options"]) == 4
    assert first["q_type"] == "single_choice"
    assert second["q_type"] == "single_choice"


def test_ids_are_unique_per_extraction():
    result = _run(PLAIN)
    ids = [q["id"] for q in result.questions]

    assert len(ids) == len(set(ids))


def test_frac_is_upgraded_to_dfrac():
    result = _run("1. 化简 $\\frac{1}{2}+\\frac{1}{3}$\n")

    assert "\\frac" not in result.questions[0]["content"]
    assert "\\dfrac{1}{2}" in result.questions[0]["content"]


def test_image_reference_survives():
    result = _run("1. 如图 ![图](images/a.jpg) 求面积\n")

    assert "![图](images/a.jpg)" in result.questions[0]["content"]


def test_empty_document_yields_nothing():
    assert _run("## 只有标题，没有题目\n\n正文也没有题号。\n").questions == []


# --------------------------------------------------------------------------- #
# 明确的拒绝，而不是静默降级
# --------------------------------------------------------------------------- #
def test_whole_paper_is_rejected_with_reason():
    """整卷/材料题结构无法用规则还原，必须让人显式换 AI 路径。"""
    doc = "【题目材料】材料一\n材料正文。\n【题组】材料一\n1.【题目】小题\n"

    with pytest.raises(ValueError) as exc:
        _run(doc)

    assert "method='ai'" in str(exc.value)


def test_image_input_is_rejected_with_reason():
    with pytest.raises(ValueError) as exc:
        _run("irrelevant", image_data=b"\x89PNG")

    assert "method='ai'" in str(exc.value)


# --------------------------------------------------------------------------- #
# 切段边界（保持原有行为）
# --------------------------------------------------------------------------- #
def test_split_ignores_decimals_and_solution_steps():
    doc = "1. 圆周率 3.14 是无理数吗\n\n解：(1)先化简\n1）原式=x+1\n\n2. 下一题\n"
    segments = split_segments(doc)

    assert len(segments) == 2


def test_build_questions_accepts_segments_only():
    """签名回归：不再需要 AI 答案参数。"""
    params = list(inspect.signature(build_questions).parameters)
    assert params == ["segments"]
