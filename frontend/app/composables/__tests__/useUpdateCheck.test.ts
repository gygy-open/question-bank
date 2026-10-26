import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

let backendVersion = '1.5.0'
const $api = vi.fn(async (_url: string) => ({
  version: backendVersion,
  repo: 'o/r',
  releases_url: 'https://github.com/o/r/releases/latest',
}))
const $fetch = vi.fn(async (_url: string) => ({
  tag_name: 'v1.5.0',
  html_url: 'https://github.com/o/r/releases/tag/v1.5.0',
  draft: false,
  prerelease: false,
}))

async function load() {
  vi.resetModules()
  const mod = await import('@/composables/useUpdateCheck')
  return mod.useUpdateCheck()
}

beforeEach(() => {
  localStorage.clear()
  backendVersion = '1.5.0'
  vi.stubGlobal('useNuxtApp', () => ({ $api }))
  vi.stubGlobal('$fetch', $fetch)
})

afterEach(() => {
  vi.unstubAllGlobals()
  $api.mockClear()
  $fetch.mockClear()
})

describe('useUpdateCheck', () => {
  it('ignores a stale legacy cache stuck in checking and reports the running version', async () => {
    localStorage.setItem('update-check', JSON.stringify({
      current: '1.0.0-alpha.1', latest: '', hasUpdate: false, releaseUrl: '',
      checkedAt: Date.now(), checking: true, error: null,
    }))

    const { state, check } = await load()
    await check()

    expect(state.value.current).toBe('1.5.0')
    expect(state.value.checking).toBe(false)
    expect(localStorage.getItem('update-check')).toBeNull()
    expect($fetch).toHaveBeenCalledTimes(1)
  })

  it('always refreshes the running version but caches the GitHub result', async () => {
    const { state, check } = await load()
    await check()
    await check()

    expect($api).toHaveBeenCalledTimes(2)
    expect($fetch).toHaveBeenCalledTimes(1)
    expect(state.value.hasUpdate).toBe(false)
  })

  it('refetches the release when the installed version changed since the cached check', async () => {
    backendVersion = '1.4.0'
    let { state, check } = await load()
    await check()
    expect(state.value.hasUpdate).toBe(true)

    backendVersion = '1.5.0'
    ;({ state, check } = await load())
    await check()

    expect($fetch).toHaveBeenCalledTimes(2)
    expect(state.value.current).toBe('1.5.0')
    expect(state.value.hasUpdate).toBe(false)
  })

  it('shares one in-flight check between concurrent callers', async () => {
    const { check } = await load()
    await Promise.all([check(), check()])

    expect($api).toHaveBeenCalledTimes(1)
    expect($fetch).toHaveBeenCalledTimes(1)
  })

  it('still reports the running version when GitHub is unreachable', async () => {
    $fetch.mockRejectedValueOnce(new Error('network'))
    const { state, check } = await load()
    await check()

    expect(state.value.current).toBe('1.5.0')
    expect(state.value.error).toBe('network')
    expect(state.value.checking).toBe(false)
  })
})
