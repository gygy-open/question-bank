"""Snapshot v2 → CompositionExportDoc 装配器(导出格式无关)。

树重建与 answer_item 有效字段解析,与前端 `compositionSnapshot.ts` 的
`buildSnapshotTree` / `effectiveAnswerFields` 语义严格对齐,保证导出与只读预览
(SnapshotRenderer.vue)的内容一致(见 docs/development/composition-next-phase-plan.md §5.3)。

version-driven:只消费传入的不可变 snapshot dict,绝不查询实时 Question/Composition。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional

from app.services.exporting.composition_contracts import (
    CompositionExportDoc,
    CompositionExportNode,
    ExportAnswerEntry,
    ExportHeadingNode,
    ExportOption,
    ExportPageBreakNode,
    ExportQuestionDetailsNode,
    ExportQuestionNode,
    ExportRichTextNode,
    QuestionDetailsChild,
)
from app.services.question_content_converter import rich_doc_to_plain_text

ANSWER_FIELD_KEYS = ("answer", "thinking", "analysis", "summary")
SUPPORTED_SCHEMA_VERSION = 2


class CompositionExportError(Exception):
    """导出装配失败;detail/node_id/node_type 供 API 层转换成 422 响应体。"""

    def __init__(self, detail: str, *, node_id: Optional[str] = None, node_type: Optional[str] = None):
        super().__init__(detail)
        self.detail = detail
        self.node_id = node_id
        self.node_type = node_type


def _parse_options(raw: Any) -> list[ExportOption]:
    result: list[ExportOption] = []
    if isinstance(raw, list):
        for idx, opt in enumerate(raw):
            if isinstance(opt, dict):
                result.append(
                    ExportOption(
                        id=str(opt.get("id", "")),
                        label=str(opt.get("label", "") or chr(65 + idx)),
                        content=opt.get("content"),
                    )
                )
    return result


def _option_has_wide_content(doc: Any) -> bool:
    """选项含图片/表格/块公式时视为"宽内容"(镜像前端 optionHasWideContent)。"""
    if not isinstance(doc, dict):
        return False

    def walk(node: Any) -> bool:
        if not isinstance(node, dict):
            return False
        if node.get("type") in ("image", "table", "blockMath"):
            return True
        return any(walk(c) for c in node.get("content") or [])

    return any(walk(n) for n in doc.get("content") or [])


def _resolve_option_columns(options: list[ExportOption], layout: Any) -> int:
    """镜像前端 compositionDocument.ts 的 resolveOptionColumns:手动固定列数按选项数收窄,
    auto 按最长选项文本长度自适应,含宽内容(图片/表格/块公式)强制单列。
    """
    count = len(options)
    if count == 0:
        return 1
    if layout in (1, 2, 4):
        return min(layout, count)
    max_len = 0
    for opt in options:
        if _option_has_wide_content(opt.content):
            return 1
        max_len = max(max_len, len(rich_doc_to_plain_text(opt.content)))
    desired = 4 if max_len <= 4 else 2 if max_len <= 12 else 1
    return min(desired, count)


class CompositionAssembler:
    def assemble(self, snapshot: dict[str, Any]) -> CompositionExportDoc:
        if snapshot.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
            raise CompositionExportError(
                f"Unsupported snapshot schema_version: {snapshot.get('schema_version')!r}"
            )

        nodes = snapshot.get("nodes") or []
        numbering_enabled = bool(snapshot.get("numbering_enabled"))
        scoring_enabled = bool(snapshot.get("scoring_enabled"))
        question_display = {
            k: bool((snapshot.get("question_display") or {}).get(k, False)) for k in ANSWER_FIELD_KEYS
        }

        roots: list[dict[str, Any]] = []
        children_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
        question_nodes_by_id: dict[str, dict[str, Any]] = {}
        for n in nodes:
            if n.get("parent_id") is None:
                roots.append(n)
            else:
                children_by_parent[n["parent_id"]].append(n)
            if n.get("node_type") == "question":
                question_nodes_by_id[n["id"]] = n
        roots.sort(key=lambda n: (n["position"], n["id"]))

        export_nodes: list[CompositionExportNode] = [
            self._assemble_node(
                n,
                children_by_parent,
                question_nodes_by_id,
                numbering_enabled=numbering_enabled,
                scoring_enabled=scoring_enabled,
                question_display=question_display,
            )
            for n in roots
        ]
        return CompositionExportDoc(title=snapshot.get("title") or "", nodes=export_nodes)

    def _assemble_node(
        self,
        n: dict[str, Any],
        children_by_parent: dict[str, list[dict[str, Any]]],
        question_nodes_by_id: dict[str, dict[str, Any]],
        *,
        numbering_enabled: bool,
        scoring_enabled: bool,
        question_display: dict[str, bool],
    ) -> CompositionExportNode:
        node_type = n.get("node_type")
        if node_type == "rich_text":
            return ExportRichTextNode(content=n.get("content"))
        if node_type == "heading":
            props = n.get("props") or {}
            return ExportHeadingNode(level=int(props.get("level", 2)), content=n.get("content"))
        if node_type == "page_break":
            return ExportPageBreakNode()
        if node_type == "question":
            return self._assemble_question(
                n,
                numbering_enabled=numbering_enabled,
                scoring_enabled=scoring_enabled,
                question_display=question_display,
            )
        if node_type == "question_details":
            return self._assemble_question_details(n, children_by_parent, question_nodes_by_id)
        raise CompositionExportError(
            f"Unsupported snapshot node type: {node_type!r}", node_id=n.get("id"), node_type=node_type,
        )

    def _assemble_question(
        self,
        n: dict[str, Any],
        *,
        numbering_enabled: bool,
        scoring_enabled: bool,
        question_display: dict[str, bool],
    ) -> ExportQuestionNode:
        q = n.get("question") or {}
        props = n.get("props") or {}
        options = _parse_options(q.get("options"))

        number = (props.get("number") or "") if numbering_enabled else ""
        score = props.get("score") if scoring_enabled else None
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            score = None

        columns = _resolve_option_columns(options, props.get("optionLayout"))
        show = props.get("show") or {}

        def field_or_none(key: str) -> Any:
            override = show.get(key)
            visible = override if isinstance(override, bool) else question_display.get(key, False)
            return q.get(key) if visible else None

        return ExportQuestionNode(
            number=number,
            score=score,
            q_type=str(q.get("q_type", "")),
            stem=q.get("content"),
            options=options,
            option_columns=columns,
            answer=field_or_none("answer"),
            thinking=field_or_none("thinking"),
            analysis=field_or_none("analysis"),
            summary=field_or_none("summary"),
        )

    def _assemble_question_details(
        self,
        n: dict[str, Any],
        children_by_parent: dict[str, list[dict[str, Any]]],
        question_nodes_by_id: dict[str, dict[str, Any]],
    ) -> ExportQuestionDetailsNode:
        props = n.get("props") or {}
        scope = str(props.get("scope", "all"))
        module_fields = props.get("fields") or {}
        raw_children = sorted(
            children_by_parent.get(n["id"], []), key=lambda c: (c["position"], c["id"])
        )

        children: list[QuestionDetailsChild] = []
        for c in raw_children:
            ctype = c.get("node_type")
            if ctype == "heading":
                cprops = c.get("props") or {}
                children.append(ExportHeadingNode(level=int(cprops.get("level", 2)), content=c.get("content")))
            elif ctype == "rich_text":
                children.append(ExportRichTextNode(content=c.get("content")))
            elif ctype == "answer_item":
                entry = self._assemble_answer_item(c, question_nodes_by_id, module_fields)
                if entry is not None:
                    children.append(entry)
            else:
                raise CompositionExportError(
                    f"Unsupported question_details child node type: {ctype!r}",
                    node_id=c.get("id"), node_type=ctype,
                )
        return ExportQuestionDetailsNode(scope=scope, children=children)

    def _assemble_answer_item(
        self,
        c: dict[str, Any],
        question_nodes_by_id: dict[str, dict[str, Any]],
        module_fields: dict[str, Any],
    ) -> Optional[ExportAnswerEntry]:
        props = c.get("props") or {}
        # included=false:该题在此模块内被排除,与前端 effectiveAnswerFields 一致地整条跳过。
        if not props.get("included", False):
            return None

        source_id = c.get("source_question_node_id")
        source = question_nodes_by_id.get(source_id) if source_id else None
        if source is None:
            raise CompositionExportError(
                "answer_item source question node not found in snapshot",
                node_id=c.get("id"), node_type="answer_item",
            )

        q = source.get("question") or {}
        overrides = props.get("overrides") or {}

        def field_or_none(key: str) -> Any:
            override = overrides.get(key)
            visible = override if isinstance(override, bool) else bool(module_fields.get(key, False))
            return q.get(key) if visible else None

        return ExportAnswerEntry(
            question_id=q.get("id"),
            q_type=str(q.get("q_type", "")),
            stem=q.get("content"),
            options=_parse_options(q.get("options")),
            answer=field_or_none("answer"),
            thinking=field_or_none("thinking"),
            analysis=field_or_none("analysis"),
            summary=field_or_none("summary"),
        )
