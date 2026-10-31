"""表格紧跟在有序列表项之后时,markdown-it 会把整张表当成列表项的懒续行。

实测(同一张两列表,只改前置写法):

    普通文字 + 无空行       -> table 1
    （1）小问 + 无空行       -> table 1
    1. 题号   + 无空行       -> table 0   ← 整表退化成纯文本,竖线成了字面量
    1. 题号   + 空行         -> table 1

退化过程完全静默:没有异常、没有 warning,RichDoc 里只剩一段带硬换行的文字,
竖线原样留在文本里。normalize_markdown_tables 在表头前补一个空行即可恢复。
"""
import asyncio

import pytest

from app.services.importing.ingest import (
    MarkdownIngestor,
    normalize_markdown_tables,
)

TABLE = "| 年份 | 数量 |\n| --- | --- |\n| 2020 | 10 |\n"


@pytest.mark.parametrize(
    "prefix",
    [
        "1. 根据下表回答问题。\n",       # 有序列表 —— 旧的失败场景
        "12. 根据下表回答问题。\n",
        "1) 根据下表回答问题。\n",
        "根据下表回答问题。\n",          # 普通段落,本来就正常
        "（1）根据下表回答问题。\n",
    ],
)
def test_blank_line_inserted_before_table(prefix):
    out = normalize_markdown_tables(prefix + TABLE)
    lines = out.split("\n")
    header = lines.index("| 年份 | 数量 |")
    assert lines[header - 1] == "", "表头前必须是空行"


def test_existing_blank_line_not_duplicated():
    md = "1. 题目\n\n" + TABLE
    assert normalize_markdown_tables(md) == md


def test_table_at_document_start_untouched():
    assert normalize_markdown_tables(TABLE) == TABLE


def test_table_after_table_gets_blank_line():
    md = TABLE + TABLE
    out = normalize_markdown_tables(md)
    assert "\n\n| 年份 | 数量 |" in out


def test_code_fence_content_untouched():
    md = "1. 题目\n```\n| a | b |\n| --- | --- |\n| 1 | 2 |\n```\n"
    assert normalize_markdown_tables(md) == md


def test_non_header_pipe_line_untouched():
    # 单行竖线文本、没有分隔行,不是表格
    md = "1. 题目\n| 这不是表格\n"
    assert normalize_markdown_tables(md) == md


def test_markdown_ingestor_applies_normalization():
    doc = asyncio.run(MarkdownIngestor().ingest("1. 题目\n" + TABLE))
    assert "\n\n| 年份 | 数量 |" in doc.markdown
