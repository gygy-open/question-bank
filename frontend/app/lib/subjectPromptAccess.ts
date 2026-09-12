interface SubjectWithId {
  id: number
}

interface PermissionSnapshot {
  is_superuser: boolean
  capabilities: Record<string, string[]>
}

export const filterPromptManageableSubjects = <T extends SubjectWithId>(
  subjects: T[],
  permissions: PermissionSnapshot | null,
): T[] => {
  if (!permissions) return []
  if (permissions.is_superuser) return subjects
  return subjects.filter(subject =>
    permissions.capabilities[String(subject.id)]?.includes('manage_subject'),
  )
}