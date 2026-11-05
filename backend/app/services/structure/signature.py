"""条件内容签名:同源检索(规格 §12.3 N3)用来找「共享相同条件」的题。

归一化沿用题目查重的规则(``question_dedup_core.normalize_text``):公式按 LaTeX 规范化,
标点、空白、大小写差异不影响签名,因此 ``$\\dfrac{1}{2}$`` 与 ``$\\frac12$`` 视为相同。
查重规则版本(``DEDUP_VERSION``)变化时,数据迁移会按新规则重算存量签名。
"""
from __future__ import annotations

import hashlib
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question_structure import StructElement
from app.services.question_dedup_core import normalize_text

# 回填时每批处理的条数。
_BATCH = 500


def content_signature(content: Optional[str]) -> Optional[str]:
    """条件内容的签名(64 位十六进制);归一化后为空时返回 None。"""
    normalized = normalize_text(content or "")
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def backfill(db: AsyncSession, *, recompute: bool = False) -> int:
    """为存量条件补算签名(``recompute`` 时全部重算),分批提交。返回更新的条数。"""
    updated = 0
    last_id = 0
    while True:
        query = select(StructElement).where(StructElement.id > last_id).order_by(StructElement.id).limit(_BATCH)
        if not recompute:
            query = query.where(StructElement.content_sig.is_(None))
        rows = (await db.execute(query)).scalars().all()
        if not rows:
            break
        for element in rows:
            sig = content_signature(element.content)
            if sig != element.content_sig:
                element.content_sig = sig
                updated += 1
        last_id = rows[-1].id
        await db.commit()
    return updated
