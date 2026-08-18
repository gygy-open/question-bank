"""组稿内容显示策略 (DisplayPolicy) — 字段注册表与级联解析.

见 docs/specs/composition-display-policy.md。
"""
from typing import Any, Dict, List, Optional

# 落位区域 (开放枚举, 未来可加 margin / separate_booklet / collapsible)
REGION_INLINE = "inline"
REGION_APPENDIX = "appendix"
REGION_HIDDEN = "hidden"

# 字段注册表: field key -> questions 列 / 导出标签。集中消化 thinking/analysis 命名错位。
FIELD_ORDER: List[str] = ["answer", "analysis", "explanation", "summary", "source"]
FIELD_SOURCE: Dict[str, str] = {
    "answer": "answer",
    "analysis": "thinking",
    "explanation": "analysis",
    "summary": "summary",
    "source": "source",
}
FIELD_LABEL: Dict[str, str] = {
    "answer": "答案",
    "analysis": "分析",
    "explanation": "解析",
    "summary": "总结",
    "source": "来源",
}

# 任一层都未指定时的兜底落位 (纯题干)
SYSTEM_DEFAULT_REGION = REGION_HIDDEN


def _region_of(display: Optional[Dict[str, Any]], field: str) -> Optional[str]:
    if not isinstance(display, dict):
        return None
    fields = display.get("fields")
    if not isinstance(fields, dict):
        return None
    spec = fields.get(field)
    return spec.get("region") if isinstance(spec, dict) else None


def resolve_region(
    field: str, block_display: Optional[Dict], doc_display: Optional[Dict]
) -> str:
    """逐字段级联: 题块覆盖 > 文档默认 > 系统兜底。"""
    return (
        _region_of(block_display, field)
        or _region_of(doc_display, field)
        or SYSTEM_DEFAULT_REGION
    )


def make_display(regions: Dict[str, str]) -> Dict[str, Any]:
    """便捷构造完整文档级策略 (模板 seed 用)。"""
    return {
        "v": 1,
        "fields": {
            f: {"region": regions.get(f, SYSTEM_DEFAULT_REGION)} for f in FIELD_ORDER
        },
    }
