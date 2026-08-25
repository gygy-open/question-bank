"""题目内容转换器:legacy/Markdown → `content_schema_version = 1` 的 RichDoc/AnswerSpec。

纯 Python,供 Alembic data-migration 与运行时导入/渲染路径共用。

职责:
- 把存量 Markdown 字符串转成 Tiptap `RichDoc` JSON(`markdown_to_rich_doc`)。
- 把 `RichDoc` 抽成纯文本用于校验/抽样比对(`rich_doc_to_plain_text`)。
- 把旧 `options`([{label, content(md)}])升级为 `{id, label, content: RichDoc}`,`id` 稳定确定性。
- 把五种题型的旧 `answer` 升级为 `AnswerSpec` 判别联合;无法解析的选择/判断答案降级为
  只读的 `legacy_unresolved` variant 并标记需人工复核。

设计约束(见 docs/development/question-model-v2.md §0/§7/§10):
- 目标节点集 = 前端 `schemaExtensions.ts` 白名单;不启用 heading/blockquote/strike/code/
  codeblock/horizontalRule,一律降级为纯文本段落且保留可见文字。
- 任何无法识别的输入绝不静默丢字符。
- 空字段 → `None`(不存空 doc)。
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Optional

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode
from mdit_py_plugins.attrs import attrs_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin

# RichDoc / 节点的宽松别名(全部是可 JSON 序列化的原生 dict/list)。
Mark = dict[str, Any]
Node = dict[str, Any]
RichDoc = Optional[dict[str, Any]]
AnswerSpec = dict[str, Any]

_MD_PARSER = (
    MarkdownIt("commonmark", {"html": True})
    .enable("strikethrough")
    .use(dollarmath_plugin, double_inline=True)
    .use(attrs_plugin, after=("image",), allowed=("width", "height"))
)

_DETACHED_IMAGE_SIZE_RE = re.compile(
    r"(!\[[^\]\n]*\]\([^\n]*?\))[ \t]*\r?\n[ \t]*"
    r"(\{(?=[^{}]*(?:width|height)\s*=)[^{}]*\})",
    re.IGNORECASE,
)
_IMAGE_DIMENSION_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)?|\.\d+)\s*(px|in|cm|mm|pt)\s*$",
    re.IGNORECASE,
)
_PX_PER_UNIT = {
    "px": 1.0,
    "in": 96.0,
    "cm": 96.0 / 2.54,
    "mm": 96.0 / 25.4,
    "pt": 96.0 / 72.0,
}
_MAX_IMAGE_DIMENSION_PX = 20_000.0


# --------------------------------------------------------------------------- #
# Markdown → RichDoc
# --------------------------------------------------------------------------- #
def markdown_to_rich_doc(md: Optional[str]) -> RichDoc:
    """把一段 Markdown 转成 Tiptap RichDoc;空/纯空白 → None。"""
    doc, _ = markdown_to_rich_doc_with_review(md)
    return doc


def markdown_to_rich_doc_with_review(md: Optional[str]) -> tuple[RichDoc, bool]:
    """转换 Markdown,并返回是否因未知/异常输入需要人工复核。"""
    if md is None:
        return None, False
    if md.strip() == "":
        return None, False

    needs_review = [False]
    try:
        normalized_md = _DETACHED_IMAGE_SIZE_RE.sub(r"\1\2", md)
        tokens = _MD_PARSER.parse(normalized_md)
        root = SyntaxTreeNode(tokens)

        content: list[Node] = []
        for child in root.children:
            content.extend(_convert_block(child, needs_review))
    except Exception:
        return {"type": "doc", "content": [_paragraph([_text(md)])]}, True

    if not content:
        return {"type": "doc", "content": [_paragraph([_text(md)])]}, True
    return {"type": "doc", "content": content}, needs_review[0]


def _convert_block(node: SyntaxTreeNode, needs_review: list[bool]) -> list[Node]:
    """把一个块级 SyntaxTreeNode 转成 0..N 个 Tiptap 块节点。"""
    t = node.type

    if t == "paragraph":
        return [_paragraph(_convert_inline(node.children, needs_review))]

    if t == "heading":
        # 降级:标题 → 普通段落,保留可见文字。
        return [_paragraph(_convert_inline(node.children, needs_review))]

    if t == "blockquote":
        # 降级:引用 → 内部块原样展开(保留可见文字)。
        out: list[Node] = []
        for child in node.children:
            out.extend(_convert_block(child, needs_review))
        return out

    if t in ("bullet_list", "ordered_list"):
        list_type = "bulletList" if t == "bullet_list" else "orderedList"
        items: list[Node] = []
        for item in node.children:
            item_content: list[Node] = []
            for child in item.children:
                item_content.extend(_convert_block(child, needs_review))
            if not item_content:
                item_content = [_paragraph([])]
            items.append({"type": "listItem", "content": item_content})
        if not items:
            return []
        return [{"type": list_type, "content": items}]

    if t in ("fence", "code_block"):
        # 降级:代码块 → 纯文本段落,保留代码原文。
        text = node.content.rstrip("\n")
        return [_paragraph([_text(text)] if text else [])]

    if t == "hr":
        # 分隔线无可见文字,不产出任何字符。
        return []

    if t in ("math_block", "math_block_label"):
        latex = node.content.strip()
        return [{"type": "blockMath", "attrs": {"latex": latex}}]

    if t == "html_block":
        # 降级:原始 HTML 块 → 纯文本,保留原文不丢字符。
        needs_review[0] = True
        text = node.content.strip()
        return [_paragraph([_text(text)] if text else [])]

    # 未知块:优先展开子节点,否则把可见内容塞进段落,绝不丢字符。
    needs_review[0] = True
    if node.children:
        out = []
        for child in node.children:
            out.extend(_convert_block(child, needs_review))
        return out
    if node.content:
        return [_paragraph([_text(node.content)])]
    return []


def _convert_inline(
    children: list[SyntaxTreeNode],
    needs_review: list[bool],
    active_marks: Optional[list[Mark]] = None,
) -> list[Node]:
    """把一串行内 SyntaxTreeNode 转成 Tiptap 行内节点列表。

    嵌套的 strong/em 通过递归传递 marks;基于 HTML `<sup>`/`<sub>` 的上下标是同级
    开闭标签,用局部栈追踪当前打开的 mark。
    """
    base = list(active_marks or [])
    html_marks: list[Mark] = []
    out: list[Node] = []

    for node in children:
        current = _dedupe_marks(base + html_marks)
        t = node.type

        if t == "text":
            if node.content:
                out.append(_text(node.content, current))
        elif t == "inline":
            out.extend(_convert_inline(node.children, needs_review, current))
        elif t == "strong":
            out.extend(
                _convert_inline(
                    node.children, needs_review, current + [{"type": "bold"}]
                )
            )
        elif t == "em":
            out.extend(
                _convert_inline(
                    node.children, needs_review, current + [{"type": "italic"}]
                )
            )
        elif t == "s":
            # 删除线未启用:降级为无 mark 文本,保留文字。
            out.extend(_convert_inline(node.children, needs_review, current))
        elif t == "link":
            # 链接 mark 未在白名单:降级保留链接文字。
            out.extend(_convert_inline(node.children, needs_review, current))
        elif t == "code_inline":
            # 降级:行内代码 → 纯文本,保留代码原文。
            if node.content:
                out.append(_text(node.content, current))
        elif t in ("softbreak", "hardbreak"):
            out.append({"type": "hardBreak"})
        elif t.startswith("math_inline"):
            out.append({"type": "inlineMath", "attrs": {"latex": node.content.strip()}})
        elif t == "image":
            out.append(_image(node, needs_review))
        elif t == "html_inline":
            handled = _apply_html_inline(node.content, html_marks)
            if not handled and node.content:
                # 无法识别的行内 HTML → 原样保留为文本,不丢字符。
                needs_review[0] = True
                out.append(_text(node.content, current))
        else:
            # 未知行内节点:优先展开子节点,否则保留原文。
            needs_review[0] = True
            if node.children:
                out.extend(_convert_inline(node.children, needs_review, current))
            elif node.content:
                out.append(_text(node.content, current))

    return out


def _apply_html_inline(raw: str, html_marks: list[Mark]) -> bool:
    """处理行内 HTML `<sup>`/`<sub>` 开闭标签,更新 mark 栈。返回是否已识别。"""
    tag = raw.strip().lower()
    if tag in ("<sup>",):
        html_marks.append({"type": "superscript"})
        return True
    if tag in ("<sub>",):
        html_marks.append({"type": "subscript"})
        return True
    if tag in ("</sup>",):
        _pop_mark(html_marks, "superscript")
        return True
    if tag in ("</sub>",):
        _pop_mark(html_marks, "subscript")
        return True
    return False


def _pop_mark(marks: list[Mark], mark_type: str) -> None:
    for i in range(len(marks) - 1, -1, -1):
        if marks[i].get("type") == mark_type:
            del marks[i]
            return


def _paragraph(content: list[Node]) -> Node:
    node: Node = {"type": "paragraph"}
    if content:
        node["content"] = content
    return node


def _text(text: str, marks: Optional[list[Mark]] = None) -> Node:
    node: Node = {"type": "text", "text": text}
    if marks:
        node["marks"] = _dedupe_marks(marks)
    return node


def _image(node: SyntaxTreeNode, needs_review: list[bool]) -> Node:
    attrs = dict(node.attrs)
    src = str(attrs.get("src", ""))
    # alt 文本在 image 节点的子文本节点里(markdown-it 不放进 attrs)。
    alt = attrs.get("alt") or "".join(
        c.content for c in node.children if c.type == "text"
    ) or node.content or ""
    image_attrs: dict[str, Any] = {"src": src, "alt": str(alt)}
    title = attrs.get("title")
    if title:
        image_attrs["title"] = str(title)
    for name in ("width", "height"):
        raw_dimension = attrs.get(name)
        if raw_dimension is None:
            continue
        dimension = _image_dimension_to_px(raw_dimension)
        if dimension is None:
            needs_review[0] = True
            continue
        image_attrs[name] = dimension
    return {"type": "image", "attrs": image_attrs}


def _image_dimension_to_px(raw: Any) -> Optional[float]:
    match = _IMAGE_DIMENSION_RE.fullmatch(str(raw))
    if not match:
        return None
    value = float(match.group(1)) * _PX_PER_UNIT[match.group(2).lower()]
    if value <= 0 or value > _MAX_IMAGE_DIMENSION_PX:
        return None
    return round(value, 4)


def _dedupe_marks(marks: list[Mark]) -> list[Mark]:
    seen: set[str] = set()
    out: list[Mark] = []
    for m in marks:
        key = m.get("type", "")
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


# --------------------------------------------------------------------------- #
# RichDoc → 纯文本
# --------------------------------------------------------------------------- #
def rich_doc_to_plain_text(doc: RichDoc) -> str:
    """把 RichDoc 抽成纯文本(用于校验/抽样比对),空 → ""。"""
    if not doc:
        return ""
    return _node_text(doc).strip()


# listItem 不单独换行,靠其内部段落分隔,避免列表项间出现空行。
_BLOCK_TYPES = {"paragraph", "heading", "blockMath"}


def _node_text(node: Node) -> str:
    t = node.get("type")
    if t == "text":
        return node.get("text", "")
    if t in ("inlineMath", "blockMath"):
        latex = node.get("attrs", {}).get("latex", "")
        return (latex + "\n") if t == "blockMath" else latex
    if t == "image":
        attrs = node.get("attrs", {})
        return attrs.get("alt") or attrs.get("src") or ""
    if t == "hardBreak":
        return "\n"

    inner = "".join(_node_text(c) for c in node.get("content", []))
    if t in _BLOCK_TYPES:
        return inner + "\n"
    return inner


# --------------------------------------------------------------------------- #
# options 升级
# --------------------------------------------------------------------------- #
def make_option_id(index: int, label: str, content_md: str) -> str:
    """基于 (下标, label, 原文) 生成稳定确定性的 opt_ id(同输入 → 同 id)。"""
    raw = f"{index}\u0000{label}\u0000{content_md}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"opt_{digest[:8]}"


def convert_options(raw_options: Any) -> list[Node]:
    """把旧 options([{label, content(md)}])升级为 [{id, label, content: RichDoc}]。"""
    options, _ = convert_options_with_review(raw_options)
    return options


def convert_options_with_review(raw_options: Any) -> tuple[list[Node], bool]:
    """升级 options,并聚合所有选项正文的 Markdown 转换复核信号。"""
    if not isinstance(raw_options, list):
        return [], False
    out: list[Node] = []
    needs_review = False
    for index, opt in enumerate(raw_options):
        if isinstance(opt, dict):
            label = str(opt.get("label", "") or "")
            content_md = opt.get("content", "")
        else:
            label = ""
            content_md = opt
        content_md = "" if content_md is None else str(content_md)
        content, content_needs_review = markdown_to_rich_doc_with_review(content_md)
        needs_review = needs_review or content_needs_review
        out.append(
            {
                "id": make_option_id(index, label, content_md),
                "label": label,
                "content": content,
            }
        )
    return out, needs_review


# --------------------------------------------------------------------------- #
# answer 升级
# --------------------------------------------------------------------------- #
_TRUE_LITERALS = {"t", "true", "yes", "y"}
_FALSE_LITERALS = {"f", "false", "no", "n"}
_TRUE_CJK = {"对", "正确", "是", "√", "✓"}
_FALSE_CJK = {"错", "错误", "否", "×", "✗"}


def _legacy_unresolved(expected_kind: str, raw: str) -> tuple[AnswerSpec, bool]:
    return {
        "kind": "legacy_unresolved",
        "expected_kind": expected_kind,
        "raw": markdown_to_rich_doc(raw),
    }, True


# 明确的答案前缀标签(答案/正确答案/answer…)+ 可选的 :：=是为 连接符。
_ANSWER_PREFIX_RE = re.compile(
    r"^\s*(?:正确答案|参考答案|标准答案|答案|answer|ans)\s*[:：=是为]?\s*",
    re.IGNORECASE,
)
# 选项字母之间允许的分隔符:顿号/斜杠/竖线/空白/和/与/加号。逗号只在“后接字母”时视作分隔符。
_LETTER_SEP = r"、,，/\\|\s和与\+"
# 分隔列表:字母(分隔符+字母)*,如 A、B、D 或 A/B。逗号后必须跟字母才继续(否则视为解释起点)。
_PURE_CHOICE_RE = re.compile(rf"[A-Za-z](?:[{_LETTER_SEP}]+[A-Za-z])*")
# 连写大写字母,如 ABD。
_UPPER_RUN_RE = re.compile(r"[A-Z]{2,}")


def _pure_choice_letters(s: str) -> Optional[list[str]]:
    """把 s 当作“纯选择表达式”严格解析,只接受明确格式,否则返回 None(不误判)。"""
    s = s.strip()
    if not s:
        return None
    if _PURE_CHOICE_RE.fullmatch(s):
        return [c.upper() for c in re.findall(r"[A-Za-z]", s)]
    if _UPPER_RUN_RE.fullmatch(s):
        return list(s)
    return None


def _leading_choice_region(s: str) -> str:
    """取字符串开头的“字母+分隔符”连续片段(明确前缀后使用),去掉尾部分隔符。"""
    s = s.lstrip()
    m = re.match(rf"[A-Za-z][A-Za-z{_LETTER_SEP}]*", s)
    if not m:
        return ""
    return re.sub(rf"[{_LETTER_SEP}]+$", "", m.group(0))


def _extract_choice_letters(raw: Any) -> list[str]:
    """从旧答案文本中抽取选择字母,只支持明确格式,绝不扫描整段解释里的任意字母。

    - 有明确前缀(答案:A / 答案:A,因为…):取前缀后的开头字母片段。
    - 无前缀:整串必须本身就是纯选择表达式(A / A、B、D / ABD),否则判为无法解析。
    """
    s = "" if raw is None else str(raw)
    s = s.strip()
    if not s:
        return []
    m = _ANSWER_PREFIX_RE.match(s)
    if m:
        letters = _pure_choice_letters(_leading_choice_region(s[m.end():]))
    else:
        letters = _pure_choice_letters(s)
    return letters or []


def _extract_option_ids(raw: str, options: list[Node]) -> list[str]:
    """从旧答案文本抽取明确的选择字母,映射到 option label → id(去重保序)。"""
    letters = _extract_choice_letters(raw)
    if not letters:
        return []
    label_to_id: dict[str, str] = {}
    for opt in options:
        label = str(opt.get("label", "")).strip().upper()
        if label:
            label_to_id.setdefault(label, str(opt.get("id", "")))
    found: list[str] = []
    for ch in letters:
        oid = label_to_id.get(ch.upper())
        if oid and oid not in found:
            found.append(oid)
    return found


def _parse_true_false(raw: str) -> Optional[bool]:
    s = raw.strip()
    low = s.lower()
    if low in _TRUE_LITERALS or s in _TRUE_CJK:
        return True
    if low in _FALSE_LITERALS or s in _FALSE_CJK:
        return False
    return None


def convert_answer(
    q_type: str, raw_answer: Any, options: Optional[list[Node]] = None
) -> tuple[Optional[AnswerSpec], bool]:
    """把旧 answer 升级为 AnswerSpec;返回 (answer_spec, needs_review)。

    - single/multiple/true_false 无法解析 → legacy_unresolved + needs_review=True。
    - options 需为已升级后的 [{id, label, ...}](选择题用)。
    """
    options = options or []
    qt = getattr(q_type, "value", q_type)

    # 真正缺失的答案不是“有内容但无法解析”。迁移保持为 null，是否需要复核由
    # 题目生命周期(status)决定。
    if raw_answer is None or (isinstance(raw_answer, str) and not raw_answer.strip()):
        return None, False

    if qt == "fill_in_the_blank":
        return _convert_fill_answer(raw_answer)

    raw_str = "" if raw_answer is None else str(raw_answer)

    if qt == "free_response":
        reference, needs_review = markdown_to_rich_doc_with_review(raw_str)
        return {"kind": "free_response", "reference": reference}, needs_review

    if qt == "single_choice":
        ids = _extract_option_ids(raw_str, options)
        if len(ids) == 1:
            return {"kind": "single_choice", "correct": ids[0]}, False
        return _legacy_unresolved(qt, raw_str)

    if qt == "multiple_choice":
        ids = _extract_option_ids(raw_str, options)
        if ids:
            return {"kind": "multiple_choice", "correct": ids}, False
        return _legacy_unresolved(qt, raw_str)

    if qt == "true_false":
        value = _parse_true_false(raw_str)
        if value is None:
            return _legacy_unresolved(qt, raw_str)
        return {"kind": "true_false", "correct": value}, False

    # 未知题型:兜底为 legacy_unresolved,不丢原文。
    return _legacy_unresolved(str(qt), raw_str)


def _convert_fill_answer(raw_answer: Any) -> tuple[AnswerSpec, bool]:
    """旧填空答案 List[List[str]](或其 JSON 串)→ blank + RichDoc。"""
    data = raw_answer
    if isinstance(raw_answer, str):
        try:
            data = json.loads(raw_answer)
        except (ValueError, TypeError):
            data = None

    if not isinstance(data, list):
        raw_str = "" if raw_answer is None else str(raw_answer)
        return _legacy_unresolved("fill_in_the_blank", raw_str)

    blanks: list[Node] = []
    needs_review = False
    for i, group in enumerate(data):
        if not isinstance(group, list):
            group = [group]
        accept: list[RichDoc] = []
        for item in group:
            item_str = "" if item is None else str(item)
            doc, item_needs_review = markdown_to_rich_doc_with_review(item_str)
            needs_review = needs_review or item_needs_review
            if doc is not None:
                accept.append(doc)
        if not accept:
            needs_review = True
        blanks.append({"id": f"blk_{i + 1}", "accept": accept})

    return {"kind": "fill_in_the_blank", "blanks": blanks}, needs_review


# --------------------------------------------------------------------------- #
# RichDoc 合并(迁移期把 legacy_unresolved 原答案并入 analysis)
# --------------------------------------------------------------------------- #
def merge_rich_docs(
    base: RichDoc, addition: RichDoc, separator: Optional[str] = None
) -> RichDoc:
    """确定性合并两个 RichDoc:把 ``addition`` 的块级节点追加到 ``base`` 之后。

    - 不覆盖、不丢内容:``base`` 的块全部保留,``addition`` 的块整体追加在后。
    - ``base`` 与 ``addition`` 都非空且给了 ``separator`` 时,在二者之间插入一个
      仅含 ``separator`` 文本的段落作为可见分隔。
    - 任一侧为空即返回另一侧(空 → None)。对相同输入结果确定。
    """
    base_content = list(base["content"]) if base and base.get("content") else []
    add_content = list(addition["content"]) if addition and addition.get("content") else []

    if not add_content:
        return {"type": "doc", "content": base_content} if base_content else None
    if not base_content:
        return {"type": "doc", "content": add_content}

    merged: list[Node] = list(base_content)
    if separator:
        merged.append(_paragraph([_text(separator)]))
    merged.extend(add_content)
    return {"type": "doc", "content": merged}


def merge_legacy_answer_into_analysis(
    analysis: RichDoc, raw_answer: Any, separator: str = "原答案:"
) -> RichDoc:
    """把无法解析的旧答案原文并入 ``analysis``,不覆盖既有解析,空原文时原样返回。"""
    raw_str = "" if raw_answer is None else str(raw_answer)
    answer_doc = markdown_to_rich_doc(raw_str)
    if answer_doc is None:
        return analysis
    return merge_rich_docs(analysis, answer_doc, separator=separator)
