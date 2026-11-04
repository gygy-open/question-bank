"""题干结构化的开关。

- 总开关:系统设置 ``structure.enabled``,缺省开启。关闭后不再接受新的拆解请求、
  不再自动入队,界面隐藏结构化入口;已有数据保留。
- 学科开关:学科设置 ``structure.auto_decompose``(存 subject_settings),缺省关闭。
  开启后,该学科的题目在新建、导入入库、审核通过后自动排队拆解。
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.crud.crud_subject_setting import subject_setting as crud_subject_setting
from app.models.system_setting import STRUCTURE_KEY_PREFIX, SystemSetting

ENABLED_KEY = f"{STRUCTURE_KEY_PREFIX}enabled"
AUTO_DECOMPOSE_KEY = "structure.auto_decompose"


async def is_enabled(db: AsyncSession) -> bool:
    """结构化功能是否开启(缺省开启)。"""
    setting = await crud.system_setting.get_by_key(db, ENABLED_KEY)
    if setting is None or setting.value is None:
        return True
    return setting.value.strip().lower() not in ("false", "0", "off", "no")


async def set_enabled(db: AsyncSession, enabled: bool) -> None:
    """设置总开关并提交。"""
    value = "true" if enabled else "false"
    setting = await crud.system_setting.get_by_key(db, ENABLED_KEY)
    if setting is None:
        db.add(SystemSetting(key=ENABLED_KEY, value=value, description="Question structure switch"))
    else:
        setting.value = value
    await db.commit()


async def is_auto_decompose(db: AsyncSession, subject_id: int) -> bool:
    """该学科是否在入库后自动拆解(缺省关闭)。"""
    return bool(await crud_subject_setting.get_value(db, subject_id, AUTO_DECOMPOSE_KEY))


async def set_auto_decompose(db: AsyncSession, subject_id: int, enabled: bool) -> None:
    """设置学科开关并提交;关闭即删除覆盖,回到缺省。"""
    if enabled:
        await crud_subject_setting.upsert(db, subject_id, AUTO_DECOMPOSE_KEY, True)
    else:
        await crud_subject_setting.remove(db, subject_id, AUTO_DECOMPOSE_KEY)
