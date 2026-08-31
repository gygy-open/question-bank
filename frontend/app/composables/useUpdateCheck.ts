import { useLocalStorage } from '@vueuse/core'

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

interface ParsedVersion {
  core: number[]
  /** `null` means no pre-release suffix (a full release, which outranks any pre-release). */
  prerelease: string[] | null
}

/** Parse `v1.2.3-beta.1` into its numeric core and pre-release identifiers, per semver rules. */
function parseVersion(v: string): ParsedVersion {
  const stripped = v.replace(/^v/, '').split('+')[0] ?? ''
  const [corePart, ...preParts] = stripped.split('-')
  const core = (corePart ?? '').split('.').map((n) => Number.parseInt(n, 10) || 0)
  const prereleaseStr = preParts.join('-')
  const prerelease = prereleaseStr ? prereleaseStr.split('.') : null
  return { core, prerelease }
}

/** Compares two semver-like identifiers the way semver does: numeric fields compare numerically. */
function compareIdentifier(a: string, b: string): number {
  const na = Number.parseInt(a, 10)
  const nb = Number.parseInt(b, 10)
  const aIsNum = !Number.isNaN(na) && String(na) === a
  const bIsNum = !Number.isNaN(nb) && String(nb) === b
  if (aIsNum && bIsNum) return na - nb
  if (aIsNum) return -1 // numeric identifiers sort before alphanumeric ones
  if (bIsNum) return 1
  return a < b ? -1 : a > b ? 1 : 0
}

/** Returns >0 if `latest` is newer than `current`, <0 if older, 0 if equal. */
function compareVersions(latest: string, current: string): number {
  const a = parseVersion(latest)
  const b = parseVersion(current)
  const len = Math.max(a.core.length, b.core.length)
  for (let i = 0; i < len; i++) {
    const diff = (a.core[i] ?? 0) - (b.core[i] ?? 0)
    if (diff !== 0) return diff
  }
  // Same core version: no pre-release suffix outranks any pre-release (1.0.0 > 1.0.0-beta.1).
  if (a.prerelease === null && b.prerelease === null) return 0
  if (a.prerelease === null) return 1
  if (b.prerelease === null) return -1
  const preLen = Math.max(a.prerelease.length, b.prerelease.length)
  for (let i = 0; i < preLen; i++) {
    if (a.prerelease[i] === undefined) return -1
    if (b.prerelease[i] === undefined) return 1
    const diff = compareIdentifier(a.prerelease[i], b.prerelease[i])
    if (diff !== 0) return diff
  }
  return 0
}

/** Returns true when `latest` is strictly newer than `current`. */
function isNewer(latest: string, current: string): boolean {
  return compareVersions(latest, current) > 0
}

interface GithubRelease {
  tag_name: string
  html_url: string
  draft: boolean
  prerelease: boolean
}

/**
 * `/releases/latest` silently ignores pre-releases, so a user tracking a pre-release
 * channel would never be told about a newer alpha/beta/rc. When the installed version
 * is itself a pre-release, fall back to the full releases list instead.
 */
async function fetchLatestRelease(repo: string, includePrerelease: boolean): Promise<GithubRelease | null> {
  const headers = { Accept: 'application/vnd.github+json' }
  if (!includePrerelease) {
    return $fetch<GithubRelease>(`https://api.github.com/repos/${repo}/releases/latest`, { headers })
  }
  const releases = await $fetch<GithubRelease[]>(`https://api.github.com/repos/${repo}/releases`, { headers })
  return releases.find((r) => !r.draft) ?? null
}

export function useUpdateCheck() {
  const state = useLocalStorage<UpdateState>('update-check', {
    current: '',
    latest: '',
    hasUpdate: false,
    releaseUrl: '',
    checkedAt: 0,
    checking: false,
    error: null,
  })

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
      const isCurrentPrerelease = parseVersion(info.version).prerelease !== null
      const release = await fetchLatestRelease(info.repo, isCurrentPrerelease)
      const latest = release?.tag_name?.replace(/^v/, '') ?? ''
      state.value.latest = latest
      state.value.releaseUrl = release?.html_url || info.releases_url
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
