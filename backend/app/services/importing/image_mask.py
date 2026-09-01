"""AI 抽取前把 markdown 图片 token 换成短占位符 `@@IMGn@@` 再喂给 AI，还原时换回。

图片 token(含长 UUID 路径和高精度浮点尺寸)对 AI 无语义价值，让它抄写又浪费 token 又容易
出错。映射表只在单次调用内存活，不持久化。两个需要特别处理的现实情况:
- AI 偶尔把占位符编号写错(如 @@IMG2@@ 写成 @@IMG1@@)，所以 `restore_images` 除了按编号精确
  换回，还会把换不回的占位符按出现顺序补配给未被引用的图片。
- pandoc 把过长行硬换行，图片 markdown 的 alt/URL/尺寸属性块里都可能夹着换行，所以匹配
  正则必须允许这些片段内出现换行，否则被切断的图片会漏遮罩。
"""
from __future__ import annotations

import json
import re
from typing import Any

# 图片 markdown + 可选尺寸属性块;alt/URL/属性块内允许换行(pandoc 硬换行),属性块需含
# width/height 才吞掉,避免误吃无关的花括号。
IMAGE_TOKEN_RE = re.compile(
    r"!\[[^\]]*\]"
    r"\([^)]*\)"
    r"(?:[ \t\r\n]*\{(?=[^{}]*(?:width|height)\s*=)[^{}]*\})?",
    re.IGNORECASE,
)

_PLACEHOLDER_RE = re.compile(r"@@IMG\d+@@")


def mask_images(markdown: str) -> tuple[str, dict[str, str]]:
    """把 markdown 里的图片 token 依次替换成 `@@IMG0@@`/`@@IMG1@@`/...。

    返回 (遮罩后的文本, {占位符: 原始 token 文本})。没有图片时原样返回、映射为空(零开销)。
    """
    mapping: dict[str, str] = {}
    counter = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal counter
        placeholder = f"@@IMG{counter}@@"
        mapping[placeholder] = match.group(0)
        counter += 1
        return placeholder

    masked = IMAGE_TOKEN_RE.sub(_replace, markdown)
    return masked, mapping


def _walk(value: Any, on_str: Any) -> Any:
    """通用递归:对 str 叶子节点调用 on_str,list/dict 原结构递归,其它类型原样返回。"""
    if isinstance(value, str):
        return on_str(value)
    if isinstance(value, list):
        return [_walk(item, on_str) for item in value]
    if isinstance(value, dict):
        return {key: _walk(val, on_str) for key, val in value.items()}
    return value


def unmask(value: Any, mapping: dict[str, str]) -> Any:
    """把 value 里出现的占位符按编号精确换回映射表里的原文;编号对不上的原样保留。"""
    if not mapping:
        return value

    def _replace(text: str) -> str:
        for placeholder, original in mapping.items():
            if placeholder in text:
                text = text.replace(placeholder, original)
        return text

    return _walk(value, _replace)


def restore_images(value: Any, mapping: dict[str, str]) -> tuple[Any, int, int]:
    """把 value 里的 @@IMGn@@ 占位符换回真实图片 token,容忍 AI 把编号写错。

    先按编号精确换回;换不回的占位符按出现顺序补配给"未被精确引用过"的图片;配不上的
    直接清空，绝不让裸露的 @@IMGn@@ 落库。返回 (还原后的 value, 被清空的占位符数,
    仍未被引用的图片数);两个计数仅供调用方记日志。
    """
    raw_combined = json.dumps(value, ensure_ascii=False)
    unused_originals = [original for key, original in mapping.items() if key not in raw_combined]

    restored = unmask(value, mapping)

    index = 0
    dropped = 0

    def _replace_leftover(text: str) -> str:
        nonlocal index, dropped

        def _sub(_match: re.Match[str]) -> str:
            nonlocal index, dropped
            if index < len(unused_originals):
                original = unused_originals[index]
                index += 1
                return original
            dropped += 1
            return ""

        return _PLACEHOLDER_RE.sub(_sub, text)

    restored = _walk(restored, _replace_leftover)
    return restored, dropped, len(unused_originals) - index

