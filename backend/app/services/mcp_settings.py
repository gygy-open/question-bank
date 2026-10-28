"""MCP 服务总开关(系统设置 `mcp.enabled`,缺省开启)。"""
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models.system_setting import MCP_KEY_PREFIX, SystemSetting

MCP_ENABLED_KEY = f"{MCP_KEY_PREFIX}enabled"


async def is_mcp_enabled(db: AsyncSession) -> bool:
    setting = await crud.system_setting.get_by_key(db, MCP_ENABLED_KEY)
    if setting is None or setting.value is None:
        return True
    return setting.value.strip().lower() not in ("false", "0", "off", "no")


async def set_mcp_enabled(db: AsyncSession, enabled: bool) -> None:
    value = "true" if enabled else "false"
    setting = await crud.system_setting.get_by_key(db, MCP_ENABLED_KEY)
    if setting is None:
        db.add(SystemSetting(key=MCP_ENABLED_KEY, value=value, description="MCP service switch"))
    else:
        setting.value = value
    await db.commit()
