from typing import Optional

from pydantic import BaseModel, field_validator

from app.core.permissions import SubjectRole


def _validate_role(v: str) -> str:
    try:
        SubjectRole(v)
    except ValueError:
        allowed = ", ".join(r.value for r in SubjectRole)
        raise ValueError(f"role 必须是 {allowed} 之一")
    return v


class SubjectMemberSetRole(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        return _validate_role(v)


class SubjectMemberOut(BaseModel):
    id: int
    user_id: int
    subject_id: int
    role: str
    username: Optional[str] = None
    full_name: Optional[str] = None


class SubjectMembershipMini(BaseModel):
    subject_id: int
    role: str


class MyPermissions(BaseModel):
    """/users/me/permissions:前端权限判定的单一真源。"""
    is_superuser: bool
    # None 表示不受限(admin);否则是可访问学科 id 列表。
    accessible_subject_ids: Optional[list[int]] = None
    memberships: list[SubjectMembershipMini] = []
    # subject_id(字符串键) -> 生效能力值列表。
    capabilities: dict[str, list[str]] = {}
