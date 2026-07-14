from sqlalchemy import Column, String, Text
from .base import Base

class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(50), primary_key=True, index=True)
    value = Column(Text, nullable=True)
    description = Column(String(255), nullable=True)
