"""权限内核 (RBAC-lite + capability)。

设计约束(见 docs 决策):
- 角色是固定枚举 {viewer,editor,manager} + 全局 admin(=User.is_superuser)。
- 鉴权走能力语义:调用点问 `can(user, Capability.X, subject_id=...)`,不比角色大小。
- 角色→能力映射集中在唯一常量 ROLE_CAPABILITIES;改权限/加角色只动这里。
- 前向兼容:role 在 DB 里存字符串;将来若上动态 RBAC,把此映射换成 DB 表即可,
  `can()` 签名不变,上层调用点零改动。

所有判定函数都是纯函数,读取已加载到内存的 `user.subject_memberships`
(由 deps.get_current_user 预先 selectinload),不在此处触发 DB IO。
"""
from __future__ import annotations

import enum


class SubjectRole(str, enum.Enum):
    """学科作用域角色。"""
    VIEWER = "viewer"    # 只读
    EDITOR = "editor"    # 可编辑题目
    MANAGER = "manager"  # 学科负责人:管成员/配置


class Capability(str, enum.Enum):
    """能力(动作)枚举。加新动作 = 加一个值,并在 ROLE_CAPABILITIES 里授予。"""
    VIEW_QUESTION = "view_question"
    EDIT_QUESTION = "edit_question"
    MANAGE_SUBJECT = "manage_subject"    # 改学科配置/知识点/标签
    MANAGE_MEMBERS = "manage_members"    # 在本学科内分配成员与角色
    VIEW_PRIVATE_ANY = "view_private_any"  # 查看他人私有题(v1 仅 admin)


# 唯一的角色→能力映射。admin 单独走全量,不在此表内。
ROLE_CAPABILITIES: dict[SubjectRole, frozenset[Capability]] = {
    SubjectRole.VIEWER: frozenset({Capability.VIEW_QUESTION}),
    SubjectRole.EDITOR: frozenset({Capability.VIEW_QUESTION, Capability.EDIT_QUESTION}),
    SubjectRole.MANAGER: frozenset(
        {
            Capability.VIEW_QUESTION,
            Capability.EDIT_QUESTION,
            Capability.MANAGE_SUBJECT,
            Capability.MANAGE_MEMBERS,
        }
    ),
}

# 超级管理员拥有全部能力(含 VIEW_PRIVATE_ANY)。
ALL_CAPABILITIES: frozenset[Capability] = frozenset(Capability)


def role_in_subject(user, subject_id: int) -> SubjectRole | None:
    """用户在某学科的角色;无成员关系返回 None。要求 user.subject_memberships 已加载。"""
    for m in getattr(user, "subject_memberships", []) or []:
        if m.subject_id == subject_id:
            try:
                return SubjectRole(m.role)
            except ValueError:
                return None
    return None


def capabilities_for(user, subject_id: int | None = None) -> frozenset[Capability]:
    """用户在给定学科作用域下的生效能力集。"""
    if getattr(user, "is_superuser", False):
        return ALL_CAPABILITIES
    if subject_id is None:
        return frozenset()
    role = role_in_subject(user, subject_id)
    if role is None:
        return frozenset()
    return ROLE_CAPABILITIES[role]


def can(
    user,
    capability: Capability,
    *,
    subject_id: int | None = None,
    resource=None,  # 预留:v2 资源级判定(密卷/密题组成员)从此进入
) -> bool:
    """能力判定统一入口。"""
    if getattr(user, "is_superuser", False):
        return True
    return capability in capabilities_for(user, subject_id=subject_id)


def accessible_subject_ids(user) -> set[int] | None:
    """用户可访问的学科集合;返回 None 表示不受限(admin)。"""
    if getattr(user, "is_superuser", False):
        return None
    return {m.subject_id for m in (getattr(user, "subject_memberships", []) or [])}
