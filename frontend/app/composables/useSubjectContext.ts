import type { Subject } from '~/types'

const STORAGE_KEY = 'currentSubjectId'

/**
 * Global subject context — the "current working subject" applied across the
 * whole app (question list, knowledge points, tags, import, ...).
 *
 * Resolution order on init: localStorage -> user's last_active_subject_id ->
 * first available subject.
 */
export const useSubjectContext = () => {
  const currentSubjectId = useState<number | null>('subject-current-id', () => null)
  const subjects = useState<Subject[]>('subject-list', () => [])
  const initialized = useState<boolean>('subject-initialized', () => false)
  const switching = useState<boolean>('subject-switching', () => false)

  const { $api } = useNuxtApp()
  const { user } = useAuth()

  const currentSubject = computed(
    () => subjects.value.find((s) => s.id === currentSubjectId.value) ?? null
  )
  const hasSubjects = computed(() => subjects.value.length > 0)

  const persist = (id: number | null) => {
    if (import.meta.client) {
      if (id === null) localStorage.removeItem(STORAGE_KEY)
      else localStorage.setItem(STORAGE_KEY, String(id))
    }
  }

  const resolveInitialId = (): number | null => {
    // 1. localStorage
    if (import.meta.client) {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        const id = Number(stored)
        if (subjects.value.some((s) => s.id === id)) return id
      }
    }
    // 2. user's last active subject
    const lastId = user.value?.last_active_subject_id
    if (lastId && subjects.value.some((s) => s.id === lastId)) return lastId
    // 3. first available subject
    return subjects.value[0]?.id ?? null
  }

  const refreshSubjects = async () => {
    subjects.value = await $api<Subject[]>('/subjects')
  }

  const init = async (force = false) => {
    if (initialized.value && !force) return
    await refreshSubjects()
    currentSubjectId.value = resolveInitialId()
    initialized.value = true
  }

  const setSubject = async (id: number) => {
    if (switching.value || id === currentSubjectId.value) return
    const previous = currentSubjectId.value
    switching.value = true
    try {
      // Optimistic update + local persistence
      currentSubjectId.value = id
      persist(id)
      // Silent server sync (non-blocking failure)
      await $api('/users/me/last-subject', {
        method: 'PUT',
        body: { subject_id: id },
      })
    } catch (err) {
      currentSubjectId.value = previous
      persist(previous)
      throw err
    } finally {
      switching.value = false
    }
  }

  // Degrade gracefully when the current subject gets deleted elsewhere.
  watch(subjects, (list) => {
    if (currentSubjectId.value && !list.some((s) => s.id === currentSubjectId.value)) {
      const fallback = list[0]?.id ?? null
      currentSubjectId.value = fallback
      persist(fallback)
    }
  })

  return {
    currentSubjectId,
    currentSubject,
    subjects,
    hasSubjects,
    switching,
    initialized,
    init,
    setSubject,
    refreshSubjects,
  }
}
