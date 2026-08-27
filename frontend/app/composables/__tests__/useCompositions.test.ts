import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useCompositions, CompositionConflictError } from '@/composables/useCompositions'

// 捕获 $api 调用参数；useNuxtApp 在测试环境用全局桩替代。
let calls: Array<{ url: string; opts: any }>
let apiImpl: (url: string, opts: any) => Promise<any>

const $api = vi.fn((url: string, opts: any) => {
  calls.push({ url, opts })
  return apiImpl(url, opts)
})

beforeEach(() => {
  calls = []
  apiImpl = () => Promise.resolve({})
  vi.stubGlobal('useNuxtApp', () => ({ $api }))
})

afterEach(() => {
  vi.unstubAllGlobals()
  $api.mockClear()
})

describe('CompositionConflictError 分类', () => {
  it('识别 revision / folder-not-empty / other', () => {
    expect(new CompositionConflictError('Composition revision mismatch').kind).toBe('revision')
    expect(new CompositionConflictError('Folder is not empty').kind).toBe('folder-not-empty')
    expect(new CompositionConflictError('nope').kind).toBe('other')
  })
})

describe('useCompositions 请求构建', () => {
  it('listFolders 带 scope', async () => {
    const api = useCompositions()
    await api.listFolders(3, 'personal')
    expect(calls[0]!.url).toBe('/subjects/3/folders')
    expect(calls[0]!.opts.query).toEqual({ scope: 'personal' })
  })

  it('createComposition 传 body 与 scope，绝不带 owner_id', async () => {
    const api = useCompositions()
    await api.createComposition(3, 'personal', { title: 'T', folder_id: null })
    expect(calls[0]!.url).toBe('/subjects/3/compositions')
    expect(calls[0]!.opts.method).toBe('POST')
    expect(calls[0]!.opts.query).toEqual({ scope: 'personal' })
    expect(calls[0]!.opts.body).toEqual({ title: 'T', folder_id: null })
    expect(JSON.stringify(calls[0]!.opts)).not.toContain('owner_id')
  })

  it('updateComposition 带 expected_revision 与显式 folder_id=null', async () => {
    const api = useCompositions()
    await api.updateComposition(3, 'shared', 9, { expected_revision: 5, folder_id: null })
    expect(calls[0]!.url).toBe('/subjects/3/compositions/9')
    expect(calls[0]!.opts.method).toBe('PATCH')
    expect(calls[0]!.opts.body).toEqual({ expected_revision: 5, folder_id: null })
  })

  it('deleteComposition 把 expected_revision 放到 query', async () => {
    const api = useCompositions()
    await api.deleteComposition(3, 'shared', 9, 5)
    expect(calls[0]!.url).toBe('/subjects/3/compositions/9')
    expect(calls[0]!.opts.method).toBe('DELETE')
    expect(calls[0]!.opts.query).toEqual({ scope: 'shared', expected_revision: 5 })
  })

  it('restoreComposition 命中 restore 路径', async () => {
    const api = useCompositions()
    await api.restoreComposition(3, 'personal', 9, 2)
    expect(calls[0]!.url).toBe('/subjects/3/compositions/9/restore')
    expect(calls[0]!.opts.method).toBe('POST')
    expect(calls[0]!.opts.query).toEqual({ scope: 'personal', expected_revision: 2 })
  })

  it('replaceNodes PUT 到 nodes 路径，带 scope 与 body', async () => {
    const api = useCompositions()
    const payload = {
      expected_revision: 4,
      batch_id: 'b-1',
      nodes: [
        { id: 'n1', node_kind: 'block' as const, node_type: 'rich_text' as const, content: { type: 'doc' as const, content: [] } },
        { id: 'n2', node_kind: 'block' as const, node_type: 'page_break' as const },
      ],
    }
    await api.replaceNodes(3, 'shared', 9, payload)
    expect(calls[0]!.url).toBe('/subjects/3/compositions/9/nodes')
    expect(calls[0]!.opts.method).toBe('PUT')
    expect(calls[0]!.opts.query).toEqual({ scope: 'shared' })
    expect(calls[0]!.opts.body).toBe(payload)
  })

  it('getQuestionRevisions GET 题目版本状态路径，仅带 scope', async () => {
    const api = useCompositions()
    await api.getQuestionRevisions(3, 'shared', 9)
    expect(calls[0]!.url).toBe('/subjects/3/compositions/9/question-revisions')
    expect(calls[0]!.opts.method).toBeUndefined()
    expect(calls[0]!.opts.query).toEqual({ scope: 'shared' })
  })

  it('syncQuestionNodes POST 同步路径，带 scope 与 body', async () => {
    const api = useCompositions()
    const payload = { expected_revision: 4, node_ids: ['n7', 'n8'] }
    await api.syncQuestionNodes(3, 'personal', 9, payload)
    expect(calls[0]!.url).toBe('/subjects/3/compositions/9/question-nodes/sync')
    expect(calls[0]!.opts.method).toBe('POST')
    expect(calls[0]!.opts.query).toEqual({ scope: 'personal' })
    expect(calls[0]!.opts.body).toBe(payload)
  })
})

describe('409 冲突映射', () => {
  it('把后端 409 revision 冲突翻译为可识别错误', async () => {
    apiImpl = () =>
      Promise.reject({ status: 409, data: { detail: 'Composition revision mismatch' } })
    const api = useCompositions()
    await expect(
      api.updateComposition(1, 'shared', 1, { expected_revision: 1, title: 'x' }),
    ).rejects.toMatchObject({ name: 'CompositionConflictError', kind: 'revision' })
  })

  it('把删除非空目录 409 翻译为 folder-not-empty', async () => {
    apiImpl = () =>
      Promise.reject({ response: { status: 409, _data: { detail: 'Folder is not empty' } } })
    const api = useCompositions()
    await expect(api.deleteFolder(1, 'shared', 2)).rejects.toMatchObject({
      kind: 'folder-not-empty',
    })
  })

  it('replaceNodes 的 revision 409 被翻译为可识别冲突', async () => {
    apiImpl = () =>
      Promise.reject({ status: 409, data: { detail: 'Composition revision mismatch' } })
    const api = useCompositions()
    await expect(
      api.replaceNodes(1, 'shared', 1, { expected_revision: 1, nodes: [] }),
    ).rejects.toMatchObject({ name: 'CompositionConflictError', kind: 'revision' })
  })

  it('syncQuestionNodes 的 revision 409 被翻译为可识别冲突', async () => {
    apiImpl = () =>
      Promise.reject({ status: 409, data: { detail: 'Composition revision mismatch' } })
    const api = useCompositions()
    await expect(
      api.syncQuestionNodes(1, 'shared', 1, { expected_revision: 1, node_ids: ['n2'] }),
    ).rejects.toMatchObject({ name: 'CompositionConflictError', kind: 'revision' })
  })

  it('非 409 错误原样抛出', async () => {
    apiImpl = () => Promise.reject({ status: 500 })
    const api = useCompositions()
    await expect(api.deleteFolder(1, 'shared', 2)).rejects.not.toBeInstanceOf(
      CompositionConflictError,
    )
  })
})

describe('版本 (Version) API 请求构建', () => {
  it('finalizeVersion POST 到 versions 路径，带 scope 与 body', async () => {
    const api = useCompositions()
    await api.finalizeVersion(3, 'shared', 9, { expected_revision: 2, label: '终稿' })
    expect(calls[0]!.url).toBe('/subjects/3/compositions/9/versions')
    expect(calls[0]!.opts.method).toBe('POST')
    expect(calls[0]!.opts.query).toEqual({ scope: 'shared' })
    expect(calls[0]!.opts.body).toEqual({ expected_revision: 2, label: '终稿' })
    expect(JSON.stringify(calls[0]!.opts)).not.toContain('owner_id')
  })

  it('listVersions GET versions 路径，仅带 scope', async () => {
    const api = useCompositions()
    await api.listVersions(3, 'personal', 9)
    expect(calls[0]!.url).toBe('/subjects/3/compositions/9/versions')
    expect(calls[0]!.opts.method).toBeUndefined()
    expect(calls[0]!.opts.query).toEqual({ scope: 'personal' })
  })

  it('getVersion GET 单版本路径（按 version_no），带 scope', async () => {
    const api = useCompositions()
    await api.getVersion(3, 'shared', 9, 4)
    expect(calls[0]!.url).toBe('/subjects/3/compositions/9/versions/4')
    expect(calls[0]!.opts.query).toEqual({ scope: 'shared' })
  })

  it('listEvents GET events 路径，带 scope/before_id/limit', async () => {
    const api = useCompositions()
    await api.listEvents(3, 'shared', 9, { beforeId: 42, limit: 10 })
    expect(calls[0]!.url).toBe('/subjects/3/compositions/9/events')
    expect(calls[0]!.opts.method).toBeUndefined()
    expect(calls[0]!.opts.query).toEqual({ scope: 'shared', before_id: 42, limit: 10 })
  })

  it('listEvents 省略可选参数时 query 仅带 scope 与 undefined', async () => {
    const api = useCompositions()
    await api.listEvents(3, 'shared', 9)
    expect(calls[0]!.url).toBe('/subjects/3/compositions/9/events')
    expect(calls[0]!.opts.query).toEqual({ scope: 'shared', before_id: undefined, limit: undefined })
  })

  it('finalizeVersion 的 revision 409 被翻译为可识别冲突', async () => {
    apiImpl = () =>
      Promise.reject({ status: 409, data: { detail: 'Composition revision mismatch' } })
    const api = useCompositions()
    await expect(
      api.finalizeVersion(1, 'shared', 1, { expected_revision: 1 }),
    ).rejects.toMatchObject({ name: 'CompositionConflictError', kind: 'revision' })
  })
})
