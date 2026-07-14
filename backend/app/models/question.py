from sqlalchemy import Column, Integer, Text, ForeignKey, Table, Enum, DateTime, JSON, String
from sqlalchemy.orm import relationship, backref
from datetime import datetime
import enum
from .base import Base

# 题目与标签的多对多关联表
question_tags = Table(
    'question_tags',
    Base.metadata,
    Column('question_id', Integer, ForeignKey('questions.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id'), primary_key=True)
)

# 题目与知识点的多对多关联表
question_knowledge_points = Table(
    'question_knowledge_points',
    Base.metadata,
    Column('question_id', Integer, ForeignKey('questions.id'), primary_key=True),
    Column('knowledge_point_id', Integer, ForeignKey('knowledge_points.id'), primary_key=True)
)

class QuestionType(str, enum.Enum):
    SINGLE_CHOICE = "single_choice"     # 单选
    MULTIPLE_CHOICE = "multiple_choice" # 多选
    TRUE_FALSE = "true_false"           # 判断
    FILL_IN_THE_BLANK = "fill_in_the_blank" # 填空
    FREE_RESPONSE = "free_response"   # 解答

class QuestionStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING = "pending"
    PUBLISHED = "published"
    ARCHIVED = "archived"

class Question(Base):
    """题目表"""
    __tablename__ = 'questions'

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False) # 题干 (支持 Markdown/HTML)
    
    # 选项: 存储 JSON 列表, 例如 [{"label": "A", "content": "选项内容"}, ...]
    # 对于非选择题，此字段可为空
    options = Column(JSON, nullable=True) 
    
    answer = Column(Text, nullable=True)  # 参考答案
    thinking = Column(Text, nullable=True) # 分析
    analysis = Column(Text, nullable=True) # 解析
    summary = Column(Text, nullable=True)  # 总结
    deleted_at = Column(DateTime, nullable=True) # 软删除时间
    
    q_type = Column(Enum(QuestionType, values_callable=lambda obj: [e.value for e in obj]), nullable=False) # 题目类型
    status = Column(String(20), default=QuestionStatus.PUBLISHED.value, nullable=False) # 状态
    difficulty = Column(Integer, default=1) # 难度 1-5
    review_count = Column(Integer, default=0) # 审核次数

    subject_id = Column(Integer, ForeignKey('subjects.id'), nullable=True)
    import_task_id = Column(Integer, ForeignKey('import_tasks.id'), nullable=True)
    parent_id = Column(Integer, ForeignKey('questions.id'), nullable=True, index=True)
    source = Column(String(255), nullable=True) # 来源 (例如导入的文件名)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    created_by = Column(Integer, ForeignKey('user.id'), nullable=True)
    updated_by = Column(Integer, ForeignKey('user.id'), nullable=True)
    
    creator = relationship("User", foreign_keys=[created_by], back_populates="questions_created")
    updater = relationship("User", foreign_keys=[updated_by], back_populates="questions_updated")
    
    import_task = relationship("ImportTask", back_populates="questions")
    subject = relationship("Subject", backref="questions")

    # 审核记录关联
    review_logs = relationship(
        "ActivityLog",
        primaryjoin="and_(foreign(ActivityLog.resource_id) == Question.id, "
                    "ActivityLog.resource_type == 'question', "
                    "ActivityLog.action == 'review')",
        viewonly=True,
        order_by="desc(ActivityLog.created_at)"
    )

    # 关系
    children = relationship("Question",
                backref=backref('parent', remote_side=[id]),
                cascade="all, delete-orphan")
    knowledge_points = relationship("KnowledgePoint", secondary=question_knowledge_points, back_populates="questions")
    tags = relationship("Tag", secondary=question_tags, back_populates="questions")
