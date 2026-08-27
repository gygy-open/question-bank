import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useCompositionExport } from '@/composables/useCompositionExport'

// 捕获 $api 调用参数；useNuxtApp 在测试环境用全局桩替代（与 useCompositions.test.ts 一致）。
let calls: Array<{ url: string; opts: any }>
let apiImpl: (url: string, opts: any) => Promise<any>

const $api = vi.fn((url: string, opts: any) => {
  calls.push({ url, opts })
  return apiImpl(url, opts)
})

const LAST_FORMAT_KEY = 'qb:composition:last-export-format'

beforeEach(() => {
  calls = []
  apiImpl = () => Promise.resolve(new Blob(['x']))
  vi.stubGlobal('useNuxtApp', () => ({ $api }))
  vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:mock'), revokeObjectURL: vi.fn() })
  window.localStorage.removeItem(LAST_FORMAT_KEY)
})

afterEach(() => {
  vi.unstubAllGlobals()
  $api.mockClear()
})

describe('useCompositionExport.downloadVersion', () => {
  it('成功时调用 exportVersion、触发下载并记住格式', async () => {
    const exportApi = useCompositionExport()
    const createElementSpy = vi.spyOn(document, 'createElement')

    const ok = await exportApi.downloadVersion({
      subjectId: 3, scope: 'shared', compositionId: 9, versionNo: 2, title: '期中卷', format: 'docx',
    })

    expect(ok).toBe(true)
    expect(calls[0]!.url).toBe('/subjects/3/compositions/9/versions/2/export')
    expect(calls[0]!.opts.method).toBe('POST')
    expect(calls[0]!.opts.query).toEqual({ scope: 'shared' })
    expect(calls[0]!.opts.body).toEqual({ format: 'docx' })
    expect(calls[0]!.opts.responseType).toBe('blob')

    const anchor = createElementSpy.mock.results.find((r) => r.value.tagName === 'A')!.value as HTMLAnchorElement
    expect(anchor.getAttribute('download')).toBe('期中卷-v2.docx')
    expect(window.localStorage.getItem(LAST_FORMAT_KEY)).toBe('docx')
  })

  it('文件名清理非法字符', async () => {
    const exportApi = useCompositionExport()
    const createElementSpy = vi.spyOn(document, 'createElement')

    await exportApi.downloadVersion({
      subjectId: 1, scope: 'shared', compositionId: 1, versionNo: 1, title: 'A/B:C*D?E"F<G>H|I', format: 'latex',
    })

    const anchor = createElementSpy.mock.results.find((r) => r.value.tagName === 'A')!.value as HTMLAnchorElement
    expect(anchor.getAttribute('download')).toBe('A_B_C_D_E_F_G_H_I-v1-latex.zip')
  })

  it('isExporting 在请求期间为 true，结束后为 false', async () => {
    const exportApi = useCompositionExport()
    let resolveFn!: (v: Blob) => void
    apiImpl = () => new Promise((resolve) => { resolveFn = resolve })

    const promise = exportApi.downloadVersion({
      subjectId: 1, scope: 'shared', compositionId: 1, versionNo: 1, title: 'T', format: 'docx',
    })
    expect(exportApi.isExporting(1, 1, 'docx')).toBe(true)
    resolveFn(new Blob(['x']))
    await promise
    expect(exportApi.isExporting(1, 1, 'docx')).toBe(false)
  })

  it('422 时返回 false 并回传 node 定位信息，不触发 onNotFound', async () => {
    apiImpl = () => Promise.reject({
      response: { status: 422, _data: { detail: 'Unsupported snapshot node', node_id: 'n1' } },
    })
    const exportApi = useCompositionExport()
    const onNotFound = vi.fn()

    const ok = await exportApi.downloadVersion({
      subjectId: 1, scope: 'shared', compositionId: 1, versionNo: 1, title: 'T', format: 'docx', onNotFound,
    })

    expect(ok).toBe(false)
    expect(onNotFound).not.toHaveBeenCalled()
  })

  it('404 时返回 false 并触发 onNotFound', async () => {
    apiImpl = () => Promise.reject({ response: { status: 404 } })
    const exportApi = useCompositionExport()
    const onNotFound = vi.fn()

    const ok = await exportApi.downloadVersion({
      subjectId: 1, scope: 'shared', compositionId: 1, versionNo: 1, title: 'T', format: 'docx', onNotFound,
    })

    expect(ok).toBe(false)
    expect(onNotFound).toHaveBeenCalledTimes(1)
  })
})

describe('useCompositionExport.lastFormat', () => {
  it('默认返回 docx，下载成功后记住最近一次格式', async () => {
    const exportApi = useCompositionExport()
    expect(exportApi.lastFormat()).toBe('docx')

    await exportApi.downloadVersion({
      subjectId: 1, scope: 'shared', compositionId: 1, versionNo: 1, title: 'T', format: 'latex',
    })

    expect(exportApi.lastFormat()).toBe('latex')
  })
})
