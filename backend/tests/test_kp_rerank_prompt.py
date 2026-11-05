"""知识点 rerank 提示词：正文进注册表、按学科覆盖、两个 provider 共用一份。

这些断言只针对"提示词该从哪来"，不连数据库、不调用模型。
"""
import asyncio
import json

import pytest

from app.services import prompts
from app.services.ai_provider import GeminiProvider, OpenAIProvider
from app.services.importing import prompt as prompt_module
from app.services.importing.prompt import PromptBuilder
from app.services.prompt_utils import render_subject_prompt

KEY = "AI_KP_RERANK_PROMPT"

ITEMS = [
    {"id": "0", "content": "解方程 x^2-3x+2=0", "candidates": ["一元二次方程", "数与代数 > 方程"]},
    {"id": "1", "content": "求证：平行四边形的对角线互相平分", "candidates": ["平行四边形"]},
]


class _Result:
    def __init__(self, subject=None):
        self._subject = subject

    def scalar_one_or_none(self):
        return self._subject


class _DB:
    def __init__(self, subject=None):
        self._subject = subject

    async def execute(self, *args, **kwargs):
        return _Result(self._subject)


class _Crud:
    def __init__(self, template):
        self.template = template

    async def get_value(self, db, subject_id, key):
        return self.template


class _Subject:
    def __init__(self, name="数学", description="初中数学"):
        self.name = name
        self.description = description


def _render(template=None, items=None, contract="CONTRACT"):
    return prompts.render_kp_rerank_prompt(
        template, GeminiProvider()._kp_rerank_items_block(items or ITEMS), contract
    )


# --------------------------------------------------------------------------- #
# 注册表：有了 key 才有配置框，且前端/接口按字典渲染，不需要另改端点
# --------------------------------------------------------------------------- #
def test_key_is_registered_with_metadata():
    meta = prompts.SUBJECT_PROMPTS[KEY]
    assert meta["default"].strip()
    assert meta["title"].strip()
    assert meta["description"].strip()


def test_default_prompt_keeps_placeholders():
    default = prompts.get_default_prompt(KEY)
    assert "{items}" in default
    assert "{subject_name}" in default
    assert "{subject_description}" in default


def test_list_endpoint_picks_up_the_new_key():
    """端点遍历 SUBJECT_PROMPTS，所以加 key 就等于加一个配置项。"""
    from app.api.v1.endpoints import subject_prompts

    out = subject_prompts._to_out(KEY, None)
    assert out.key == KEY
    assert out.is_custom is False
    assert out.default.strip()


# --------------------------------------------------------------------------- #
# 正文只有一份：两个 provider 的差异只在输出契约
# --------------------------------------------------------------------------- #
def test_both_providers_share_one_body():
    """骨架来自注册表、题块来自一次渲染、末尾只有各自契约——没有第三份副本。"""
    gemini = GeminiProvider()._kp_rerank_prompt(ITEMS)
    openai = OpenAIProvider()._kp_rerank_prompt(ITEMS)
    body = render_subject_prompt(prompts.get_default_prompt(KEY), None).split("{items}")[0].strip()
    items_block = GeminiProvider()._kp_rerank_items_block(ITEMS)

    for prompt, contract in (
        (gemini, GeminiProvider.KP_RERANK_OUTPUT_CONTRACT),
        (openai, OpenAIProvider.KP_RERANK_OUTPUT_CONTRACT),
    ):
        assert prompt.startswith(body)
        assert prompt.endswith(contract)
        assert items_block in prompt
        residue = (
            prompt[len(body):].replace(items_block, "").replace(contract, "").strip()
        )
        assert residue == "", f"provider-specific text leaked into the body: {residue!r}"

    assert gemini != openai


def test_default_path_leaves_no_raw_placeholder():
    prompt = GeminiProvider()._kp_rerank_prompt(ITEMS)
    assert "{subject_name}" not in prompt
    assert "{subject_description}" not in prompt
    assert "{items}" not in prompt


def test_output_contracts_stay_provider_specific():
    assert "JSON array" in GeminiProvider.KP_RERANK_OUTPUT_CONTRACT
    assert "JSON object" in OpenAIProvider.KP_RERANK_OUTPUT_CONTRACT


# --------------------------------------------------------------------------- #
# 题块渲染
# --------------------------------------------------------------------------- #
def test_items_block_carries_id_content_and_candidates():
    block = GeminiProvider()._kp_rerank_items_block(ITEMS)
    for item in ITEMS:
        assert f"Question ID: {item['id']}" in block
        assert item["content"] in block
        assert json.dumps(item["candidates"], ensure_ascii=False) in block


def test_items_block_still_truncates_content_at_200():
    """本次只搬提示词，不改截断长度——那是独立的一次改动。"""
    block = GeminiProvider()._kp_rerank_items_block(
        [{"id": "0", "content": "题" * 500, "candidates": ["A"]}]
    )
    assert "题" * 200 + "..." in block
    assert "题" * 201 not in block


# --------------------------------------------------------------------------- #
# 学科覆盖
# --------------------------------------------------------------------------- #
def test_missing_items_placeholder_appends_instead_of_dropping():
    rendered = _render(template="自定义规则，没有占位符", items=ITEMS)
    assert "自定义规则，没有占位符" in rendered
    for item in ITEMS:
        assert item["content"] in rendered
    assert rendered.endswith("CONTRACT")


def test_subject_override_wins_and_placeholders_are_filled():
    prompt_module.crud_subject_prompt = _Crud("自定义 {subject_name} 规则\n\n{items}")
    try:
        text = asyncio.run(
            PromptBuilder().build_kp_rerank(_DB(_Subject()), subject_id=1)
        )
    finally:
        prompt_module.crud_subject_prompt = _Crud(None)

    assert text.startswith("自定义 数学 规则")
    assert "{subject_name}" not in text


def test_falls_back_to_default_without_override():
    prompt_module.crud_subject_prompt = _Crud(None)
    text = asyncio.run(PromptBuilder().build_kp_rerank(_DB(_Subject()), subject_id=1))
    assert text == render_subject_prompt(prompts.get_default_prompt(KEY), _Subject())


def test_no_subject_still_returns_default():
    text = asyncio.run(PromptBuilder().build_kp_rerank(_DB(), subject_id=None))
    assert prompts.get_default_prompt(KEY).replace("{subject_name} ", "").replace(
        "{subject_description}", ""
    ) in text
