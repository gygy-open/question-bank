"""DOCX 中“带下划线格式的空白”(Word/WPS 的 U 按钮画出的填空横线)→ 下划线字符。

pandoc 会把只含空白的下划线 run 压成一个普通空格,横线信息(和宽度)就此丢失。这里在 pandoc
之前预处理 docx:把连续的、只含空格/制表符的下划线 run 合并成一个由 ``_`` 组成的 run(并去掉
下划线格式),下游沿用「连续下划线 = 填空」的约定(见 question_content_converter)。
带文字的下划线 run(如被强调的词)保持原样。
"""
from __future__ import annotations

import logging
import re
import zipfile
from pathlib import Path
from typing import List

from lxml import etree

logger = logging.getLogger(__name__)

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_XML_NS = "http://www.w3.org/XML/1998/namespace"
_W = f"{{{_W_NS}}}"

_PART_RE = re.compile(r"^word/(document|footnotes|endnotes)\.xml$")

# 制表符宽度近似为若干个空格;少于该数量的下划线空白更像排版间隔而不是填空。
_TAB_CHARS = 4
_MIN_BLANK_CHARS = 3
_WHITESPACE = " \t\u00a0\u3000"


def _has_underline(run: etree._Element) -> bool:
    rpr = run.find(f"{_W}rPr")
    if rpr is None:
        return False
    u = rpr.find(f"{_W}u")
    if u is None:
        return False
    return u.get(f"{_W}val", "single") not in ("none", "0", "false")


def _blank_width(run: etree._Element) -> int | None:
    """纯空白(空格/制表符)的下划线 run 返回等效字符数;否则返回 None。"""
    if not _has_underline(run):
        return None
    width = 0
    for child in run:
        if child.tag == f"{_W}rPr":
            continue
        if child.tag == f"{_W}t":
            text = child.text or ""
            if text.strip(_WHITESPACE) != "":
                return None
            width += len(text)
        elif child.tag == f"{_W}tab":
            width += _TAB_CHARS
        else:
            return None
    return width or None


def _rewrite_group(group: List[etree._Element], width: int) -> None:
    first = group[0]
    for child in list(first):
        if child.tag != f"{_W}rPr":
            first.remove(child)
    rpr = first.find(f"{_W}rPr")
    if rpr is not None:
        for u in rpr.findall(f"{_W}u"):
            rpr.remove(u)
    t = etree.SubElement(first, f"{_W}t")
    t.set(f"{{{_XML_NS}}}space", "preserve")
    t.text = "_" * width
    for run in group[1:]:
        run.getparent().remove(run)


def _convert_part(root: etree._Element) -> int:
    changed = 0
    for parent in list(root.iter()):
        children = list(parent)
        group: List[etree._Element] = []
        total = 0

        def flush() -> None:
            nonlocal group, total, changed
            if group and total >= _MIN_BLANK_CHARS:
                _rewrite_group(group, total)
                changed += 1
            group, total = [], 0

        for child in children:
            width = _blank_width(child) if child.tag == f"{_W}r" else None
            if width is None:
                flush()
                continue
            group.append(child)
            total += width
        flush()
    return changed


def preprocess_underline_blanks(docx_path: Path, output_path: Path) -> Path:
    """把下划线空白 run 改写为 ``_`` 字符,写出到 output_path。

    没有任何改动时不写新文件,返回原路径。
    """
    with zipfile.ZipFile(docx_path) as zf:
        changed_parts: dict[str, bytes] = {}
        for part in zf.namelist():
            if not _PART_RE.match(part):
                continue
            root = etree.fromstring(zf.read(part))
            if _convert_part(root):
                changed_parts[part] = etree.tostring(
                    root, xml_declaration=True, encoding="UTF-8", standalone=True
                )

        if not changed_parts:
            return docx_path

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as out:
            for item in zf.infolist():
                out.writestr(item, changed_parts.get(item.filename) or zf.read(item.filename))
    return output_path
