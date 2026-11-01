"""表格紧跟在有序列表项之后时,markdown-it 会把整张表当成列表项的懒续行。

    普通文字 + 无空行       -> table
    （1）小问 + 无空行       -> table
    1. 小问   + 无空行       -> 纯文本(竖线成了字面量)   ← 修复前
    1. 小问   + 空行         -> table

归一放在 markdown_to_rich_doc 里:结构化解析会丢掉题干里的空行,AI 产出等路径也只经过转换器。
用例与思路来自 #19(@laozhudu)。
"""
from typing import Any, List

import pytest

from app.services.question_content_converter import (
    _ensure_blank_line_before_tables,
    markdown_to_rich_doc,
)
from app.services.structured_parser import parse_structured

TABLE = "| 年份 | 数量 |\n| --- | --- |\n| 2020 | 10 |\n"


def _types(node: Any) -> List[str]:
    out = [node.get("type")]
    for child in node.get("content") or []:
        out.extend(_types(child))
    return out


def _has_table(md: str) -> bool:
    return "table" in _types(markdown_to_rich_doc(md))


@pytest.mark.parametrize(
    "prefix",
    [
        "1. 根据下表回答问题。\n",
        "12. 根据下表回答问题。\n",
        "1) 根据下表回答问题。\n",
        "根据下表回答问题。\n",
        "（1）根据下表回答问题。\n",
    ],
)
def test_table_after_line_becomes_table_node(prefix):
    assert _has_table(prefix + TABLE)


def test_structured_question_with_numbered_sub_item_keeps_table():
    # 结构化解析会丢掉题干里的空行,所以只在导入入口补空行不够。
    md = "1.【题目】阅读材料\n1. 根据下表回答。\n" + TABLE + "【答案】A\n"
    content = parse_structured(md).questions[0]["content"]
    assert _has_table(content)


def test_existing_blank_line_not_duplicated():
    md = "1. 题目\n\n" + TABLE
    assert _ensure_blank_line_before_tables(md) == md


def test_table_at_document_start_untouched():
    assert _ensure_blank_line_before_tables(TABLE) == TABLE


def test_table_after_table_gets_blank_line():
    out = _ensure_blank_line_before_tables(TABLE + TABLE)
    assert "\n\n| 年份 | 数量 |" in out


@pytest.mark.parametrize("fence", ["```", "~~~", "````"])
def test_code_fence_content_untouched(fence):
    md = f"1. 题目\n{fence}\n| a | b |\n| --- | --- |\n| 1 | 2 |\n{fence}\n"
    assert _ensure_blank_line_before_tables(md) == md
    assert "table" not in _types(markdown_to_rich_doc(md))


def test_shorter_inner_fence_does_not_close_outer_fence():
    md = "````\n```\n1. 题目\n| a | b |\n| --- | --- |\n````\n"
    assert _ensure_blank_line_before_tables(md) == md


def test_non_header_pipe_line_untouched():
    md = "1. 题目\n| 这不是表格\n"
    assert _ensure_blank_line_before_tables(md) == md
