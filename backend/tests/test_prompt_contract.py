"""提示词契约测试：规则优先级、占位符、标签注入位置、截断守卫。

这些断言针对的是"提示词与调用契约"，不依赖数据库、不调用模型。
"""
import asyncio

import pytest

from app.services import prompts
from app.services.ai_provider import ResponseTruncatedError, _guard_truncated
from app.services.importing import prompt as prompt_module
from app.services.importing.prompt import PromptBuilder

REQUIRED_PLACEHOLDERS = ["{subject_name}", "{subject_description}", "{tags}", "{content}"]


class _Choice:
    def __init__(self, finish_reason):
        self.finish_reason = finish_reason


class _Result:
    def scalar_one_or_none(self):
        return None


class _DB:
    async def execute(self, *args, **kwargs):
        return _Result()


class _Crud:
    def __init__(self, template):
        self.template = template

    async def get_value(self, db, subject_id, key):
        return self.template


def _build(monkeypatch, template, tag_context="\n## TAGS\n- 题型: 计算"):
    monkeypatch.setattr(prompt_module, "crud_subject_prompt", _Crud(template))

    async def fake_tags(self, db):
        return tag_context

    monkeypatch.setattr(PromptBuilder, "_build_tag_context", fake_tags)
    return asyncio.run(PromptBuilder().build(_DB(), mode="extract", subject_id=1))


# --------------------------------------------------------------------------- #
# 规则优先级：两条规则冲突时必须有裁决顺序，而不是让模型二选一
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "template_name", ["DEFAULT_EXTRACT_PROMPT", "DEFAULT_SOLVE_PROMPT"]
)
def test_both_prompts_declare_rule_precedence(template_name):
    template = getattr(prompts, template_name)
    assert "Rule precedence" in template
    assert "Content fidelity" in template
    assert "Math syntax" in template


@pytest.mark.parametrize(
    "template_name", ["DEFAULT_EXTRACT_PROMPT", "DEFAULT_SOLVE_PROMPT"]
)
def test_prompts_keep_required_placeholders(template_name):
    template = getattr(prompts, template_name)
    for placeholder in REQUIRED_PLACEHOLDERS:
        assert placeholder in template, f"{template_name} 缺少 {placeholder}"
    # {output_language} 可选：apply_output_language 据此注入语言要求
    assert "{output_language}" in template


def test_extract_prompt_has_no_self_contradiction():
    """§1 允许逐字保留原文，§2 要求转换公式定界符——必须写明 §2 是唯一例外。"""
    template = prompts.DEFAULT_EXTRACT_PROMPT
    assert "Never modify them" not in template
    assert "delimiter normalization" in template


# --------------------------------------------------------------------------- #
# 知识点数量：软要求实测不生效，改为精度优先的硬约束
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "template_name", ["DEFAULT_EXTRACT_PROMPT", "DEFAULT_SOLVE_PROMPT"]
)
def test_knowledge_point_contract_is_precision_first(template_name):
    template = getattr(prompts, template_name)
    assert "3-5" not in template
    assert "1 to 3" in template
    assert "Do not pad" in template or "do not pad" in template


# --------------------------------------------------------------------------- #
# {tags} 注入位置：漏写占位符时不能把指令追加到素材之后
# --------------------------------------------------------------------------- #
def test_tags_inserted_before_content_when_placeholder_missing(monkeypatch):
    out = _build(monkeypatch, "RULES\n\n{content}\n")
    assert "## TAGS" in out
    assert out.index("## TAGS") < out.index("{content}")


def test_tags_replaced_in_place_when_placeholder_present(monkeypatch):
    out = _build(monkeypatch, "RULES\n{tags}\n\n{content}\n")
    assert "{tags}" not in out
    assert out.index("## TAGS") < out.index("{content}")


def test_tags_appended_only_when_no_placeholder_at_all(monkeypatch):
    # 两个占位符都没有时不猜插入点，追加到末尾；apply_output_language 之后可能再补语言段，
    # 因此只断言相对位置。
    out = _build(monkeypatch, "RULES ONLY\n")
    assert "## TAGS" in out
    assert out.index("RULES ONLY") < out.index("## TAGS")


# --------------------------------------------------------------------------- #
# 截断守卫：finish_reason=length 必须报错，不能被当成"题目变少"
# --------------------------------------------------------------------------- #
def test_guard_raises_on_length():
    with pytest.raises(ResponseTruncatedError):
        _guard_truncated(_Choice("length"))


@pytest.mark.parametrize("reason", ["stop", "tool_calls", None])
def test_guard_passes_through_normal_finish(reason):
    _guard_truncated(_Choice(reason))
