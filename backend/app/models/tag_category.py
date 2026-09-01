from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint
from .base import Base

class TagCategory(Base):
    """标签分类表"""
    __tablename__ = 'tag_categories'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False) # 显示名称，如：年份
    subject_id = Column(Integer, ForeignKey('subjects.id'), nullable=False, index=True)
    sort_order = Column(Integer, default=0) # 排序
    is_active = Column(Boolean, default=True) # 是否启用

    __table_args__ = (
        UniqueConstraint('subject_id', 'name', name='uq_tag_category_subject_name'),
    )
