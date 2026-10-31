"""智能导入草稿:让抽取结果能跨过页面刷新与关闭。

背景
----
`/upload/*` 四个入口(docx / markdown / markdown-text / markdown-archive /
image-recognition)把整篇原文丢给模型,结果**只放在响应体里**:既不建导入任务,
也不落库。实测 786 题整本抽取约 268 秒,这期间刷新页面或关掉标签页,浏览器会中断
请求,服务端算完的结果没有任何人去接,也没有留下可恢复的痕迹——用户只能从头再来,
而已经消耗的模型调用无法退回。

更糟的是响应体里那个 `task_id` 是个随机 UUID,而 `import_tasks` 的主键是整数,
拿它去 `GET /import-tasks/{id}` 永远 404,看起来像有任务可恢复,实际没有。

做法
----
抽取成功后把**响应体原样**存成一份草稿(独立目录、内容寻址、TTL 清理),响应里多带
一个 `draft_id`。页面重新打开时按 id 取回同一份草稿,从审核那一步接着走。提交入库
后调用 `delete_draft_id` 回收。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from app.core import storage

logger = logging.getLogger(__name__)

# 一本 786 题的教辅抽取后约几 MB;留足余量,同时挡住误存的超大对象。
DRAFT_MAX_BYTES = 32 * 1024 * 1024
# 草稿只服务于「刷新/关页后接着做」,不需要长期留存。
DRAFT_TTL_SECONDS = 7 * 86400


class DraftTooLarge(ValueError):
    """抽取结果超出草稿上限。"""


def save_draft(payload: Dict[str, Any]) -> str:
    """保存草稿,返回 draft_id(内容哈希)。同内容重复保存复用同一份。"""
    try:
        raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    except (TypeError, ValueError) as exc:  # 理论上不会发生,兜底避免整个导入失败
        logger.warning("Failed to serialize import draft: %s", exc)
        raise DraftTooLarge(str(exc)) from exc

    if len(raw) > DRAFT_MAX_BYTES:
        raise DraftTooLarge(
            f"抽取结果 {len(raw)} 字节,超过草稿上限 {DRAFT_MAX_BYTES} 字节"
        )

    draft_id = storage.put_draft(raw)
    # 顺手清理过期草稿:草稿目录通常只有个位数文件,代价可忽略。
    try:
        storage.cleanup_drafts(DRAFT_TTL_SECONDS)
    except OSError as exc:
        logger.warning("Failed to clean stale import drafts: %s", exc)
    return draft_id


def load_draft(draft_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """按 id 取回草稿;不存在或已过期返回 None(页面就当没有可恢复的导入)。"""
    if not draft_id:
        return None
    try:
        raw = storage.read_draft(draft_id)
    except storage.StorageError:
        return None
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        logger.warning("Corrupted import draft %s: %s", draft_id, exc)
        return None
    return payload if isinstance(payload, dict) else None


def delete_draft_id(draft_id: Optional[str]) -> None:
    if draft_id:
        storage.delete_draft(draft_id)


def attach_draft(result: Dict[str, Any]) -> Dict[str, Any]:
    """把抽取结果登记成草稿,并在响应里带上 draft_id。

    保存失败不影响本次导入(结果仍在响应体里),只记 warning。
    """
    try:
        result["draft_id"] = save_draft(result)
    except (DraftTooLarge, OSError) as exc:
        logger.warning("Import draft not saved: %s", exc)
    return result


async def attach_draft_async(result: Dict[str, Any]) -> Dict[str, Any]:
    """大结果序列化会阻塞事件循环,放到线程里做。"""
    return await asyncio.to_thread(attach_draft, result)
