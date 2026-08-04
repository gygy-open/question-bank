from sqlalchemy import Column, Integer, String, Table, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from .base import Base

class Tag(Base):
    """标签表 (如: 期末, 易错, 重点)"""
    __tablename__ = 'tags'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), index=True, nullable=False)
    category = Column(String(50), default="general", index=True, nullable=False) # 标签分类: year, source, grade, semester, exam_type, feature(典型,压轴,同步等)
    color = Column(String(20), default="#grey") # 标签颜色

    # 标签归属的科目（学科级隔离，不同科目允许同名标签）
    subject_id = Column(Integer, ForeignKey('subjects.id'), nullable=False, index=True)

    created_by = Column(Integer, ForeignKey('user.id'), nullable=True)
    updated_by = Column(Integer, ForeignKey('user.id'), nullable=True)

    creator = relationship("User", foreign_keys=[created_by], back_populates="tags_created")
    updater = relationship("User", foreign_keys=[updated_by], back_populates="tags_updated")
    subject = relationship("Subject", backref="tags")

    # 关系
    # secondary 将在 question.py 中定义 table 后引用，或者我们在这里引用字符串
    questions = relationship("Question", secondary="question_tags", back_populates="tags")

    __table_args__ = (
        UniqueConstraint('subject_id', 'name', name='uq_tag_subject_name'),
    )
