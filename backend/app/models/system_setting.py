from sqlalchemy import Column, String, Text
from .base import Base

# 系统内部记录(如一次性数据迁移的完成标记),不在设置页展示,也不允许经通用设置 API 修改。
# `mcp.` 下的开关由专用端点(/api-keys/mcp-settings)维护。
DATA_MIGRATION_KEY_PREFIX = "data_migration."
MCP_KEY_PREFIX = "mcp."
INTERNAL_KEY_PREFIXES = (DATA_MIGRATION_KEY_PREFIX, MCP_KEY_PREFIX)


def is_internal_key(key: str) -> bool:
    return key.startswith(INTERNAL_KEY_PREFIXES)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(50), primary_key=True, index=True)
    value = Column(Text, nullable=True)
    description = Column(String(255), nullable=True)
