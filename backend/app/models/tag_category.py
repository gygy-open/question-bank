from sqlalchemy import Column, Integer, String, Boolean
from .base import Base

class TagCategory(Base):
    """标签分类表"""
    __tablename__ = 'tag_categories'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False) # 显示名称，如：年份
    slug = Column(String(50), unique=True, index=True, nullable=False) # 代码，如：year
    sort_order = Column(Integer, default=0) # 排序
    is_active = Column(Boolean, default=True) # 是否启用
