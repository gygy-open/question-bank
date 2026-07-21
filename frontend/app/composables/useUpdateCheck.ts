/**
 * Desktop update check.
 *
 * Compares the running app version (from the backend `/system/version`) against
 * the latest published GitHub Release and exposes whether an update is
 * available. The result is shared app-wide via `useState` so both the sidebar
 * entry and the startup toast read the same data.
 */

interface VersionInfo {
  version: string
  repo: string
  releases_url: string
}

interface UpdateState {
  current: string
  latest: string
  hasUpdate: boolean
  releaseUrl: string
  checkedAt: number
  checking: boolean
  error: string | null
}

/** Parse a version string into numeric parts, ignoring a leading `v` and any
 * pre-release/build suffix (e.g. `v1.2.3-beta.1` -> [1, 2, 3]). */
function parseVersion(v: string): number[] {
  const core = v.replace(/^v/, '').split(/[-+]/)[0] ?? ''
  return core.split('.').map((n) => Number.parseInt(n, 10) || 0)
}

/** Returns true when `latest` is strictly newer than `current`. */
function isNewer(latest: string, current: string): boolean {
  const a = parseVersion(latest)
  const b = parseVersion(current)
  const len = Math.max(a.length, b.length)
  for (let i = 0; i < len; i++) {
    const x = a[i] ?? 0
    const y = b[i] ?? 0
    if (x > y) return true
    if (x < y) return false
  }
  return false
}

export function useUpdateCheck() {
  const state = useState<UpdateState>('update-check', () => ({
    current: '',
    latest: '',
    hasUpdate: false,
    releaseUrl: '',
    checkedAt: 0,
    checking: false,
    error: null,
  }))

  const { $api } = useNuxtApp()

  async function check(force = false): Promise<void> {
    // Skip if checked within the last 6 hours, unless forced.
    const sixHours = 6 * 60 * 60 * 1000
    if (!force && state.value.checkedAt && Date.now() - state.value.checkedAt < sixHours) {
      return
    }
    if (state.value.checking) return

    state.value.checking = true
    state.value.error = null
    try {
      // Current version + release repo from our own backend.
      const info = await $api<VersionInfo>('/system/version')
      state.value.current = info.version

      // Latest release from GitHub (public API, CORS-enabled).
      const release = await $fetch<{ tag_name: string; html_url: string }>(
        `https://api.github.com/repos/${info.repo}/releases/latest`,
        { headers: { Accept: 'application/vnd.github+json' } }
      )
      const latest = release.tag_name?.replace(/^v/, '') ?? ''
      state.value.latest = latest
      state.value.releaseUrl = release.html_url || info.releases_url
      state.value.hasUpdate = latest !== '' && isNewer(latest, info.version)
    } catch (e: unknown) {
      state.value.error = e instanceof Error ? e.message : 'update check failed'
    } finally {
      state.value.checking = false
      state.value.checkedAt = Date.now()
    }
  }

  return { state, check }
}
