// 前端权限判定:消费后端 /users/me/permissions 单一真源,不在此重抄角色→能力映射。
export const Capability = {
  VIEW_QUESTION: 'view_question',
  EDIT_QUESTION: 'edit_question',
  MANAGE_SUBJECT: 'manage_subject',
  MANAGE_MEMBERS: 'manage_members',
  VIEW_PRIVATE_ANY: 'view_private_any',
  VIEW_ASSESSMENT: 'view_assessment',
  EDIT_SCORE: 'edit_score',
  MANAGE_ASSESSMENT: 'manage_assessment',
} as const

export type CapabilityValue = typeof Capability[keyof typeof Capability]

export interface SubjectMembershipMini {
  subject_id: number
  role: string
}

export interface MyPermissions {
  is_superuser: boolean
  accessible_subject_ids: number[] | null
  memberships: SubjectMembershipMini[]
  capabilities: Record<string, string[]>
}

export const usePermissions = () => {
  const perms = useState<MyPermissions | null>('auth-permissions', () => null)
  const { $api } = useNuxtApp()

  const fetchPermissions = async (): Promise<MyPermissions | null> => {
    try {
      perms.value = await $api<MyPermissions>('/users/me/permissions')
    } catch {
      perms.value = null
    }
    return perms.value
  }

  const isAdmin = computed(() => !!perms.value?.is_superuser)

  // 是否为任意学科的负责人(用于展示"学科管理"等管理入口)。
  const isManagerSomewhere = computed(() =>
    (perms.value?.memberships ?? []).some((m) => m.role === 'manager'),
  )

  const can = (capability: CapabilityValue, subjectId?: number | null): boolean => {
    if (perms.value?.is_superuser) return true
    if (subjectId == null) return false
    const caps = perms.value?.capabilities?.[String(subjectId)]
    return !!caps && caps.includes(capability)
  }

  const roleInSubject = (subjectId: number): string | null => {
    return perms.value?.memberships?.find((m) => m.subject_id === subjectId)?.role ?? null
  }

  const accessibleSubjectIds = computed<number[] | null>(
    () => perms.value?.accessible_subject_ids ?? null,
  )

  return { permissions: perms, fetchPermissions, isAdmin, isManagerSomewhere, can, roleInSubject, accessibleSubjectIds }
}
