import { describe, it, expect } from 'vitest'
import type { CompositionFolder } from '@/types/composition'
import {
  isCompositionScope,
  normalizeScope,
  scopedBasePath,
  folderItemPath,
  compositionItemPath,
  compositionRestorePath,
  compositionVersionsPath,
  compositionVersionItemPath,
  compositionEventsPath,
  compositionListQuery,
  buildFolderTree,
  folderBreadcrumb,
  collectDescendantIds,
} from '@/lib/compositions'

function folder(id: number, parent_id: number | null, name = `f${id}`): CompositionFolder {
  return {
    id,
    name,
    scope_type: 'shared',
    owner_id: null,
    subject_id: 1,
    parent_id,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

describe('scope 校验与规整', () => {
  it('isCompositionScope 仅接受 shared/personal', () => {
    expect(isCompositionScope('shared')).toBe(true)
    expect(isCompositionScope('personal')).toBe(true)
    expect(isCompositionScope('team')).toBe(false)
    expect(isCompositionScope(undefined)).toBe(false)
  })

  it('normalizeScope 非法值回退 shared', () => {
    expect(normalizeScope('personal')).toBe('personal')
    expect(normalizeScope('bogus')).toBe('shared')
    expect(normalizeScope(['personal'])).toBe('shared')
  })
})

describe('URL 构建', () => {
  it('scoped 基础路径', () => {
    expect(scopedBasePath(7, 'folders')).toBe('/subjects/7/folders')
    expect(scopedBasePath(7, 'compositions')).toBe('/subjects/7/compositions')
  })

  it('单项与 restore 路径', () => {
    expect(folderItemPath(7, 3)).toBe('/subjects/7/folders/3')
    expect(compositionItemPath(7, 9)).toBe('/subjects/7/compositions/9')
    expect(compositionRestorePath(7, 9)).toBe('/subjects/7/compositions/9/restore')
  })

  it('版本集合与单版本路径', () => {
    expect(compositionVersionsPath(7, 9)).toBe('/subjects/7/compositions/9/versions')
    expect(compositionVersionItemPath(7, 9, 3)).toBe('/subjects/7/compositions/9/versions/3')
  })

  it('时间线路径', () => {
    expect(compositionEventsPath(7, 9)).toBe('/subjects/7/compositions/9/events')
  })
})

describe('列表 query 构建', () => {
  it('仅 scope 时省略其它键', () => {
    expect(compositionListQuery({ scope: 'shared' })).toEqual({ scope: 'shared' })
  })

  it('folderId=null 不下发 folder_id', () => {
    expect(compositionListQuery({ scope: 'personal', folderId: null })).toEqual({
      scope: 'personal',
    })
  })

  it('根目录视图下发 root_only', () => {
    expect(compositionListQuery({ scope: 'shared', rootOnly: true })).toEqual({
      scope: 'shared',
      root_only: true,
    })
  })

  it('携带 folder_id 与 only_deleted', () => {
    expect(compositionListQuery({ scope: 'shared', folderId: 4, onlyDeleted: true })).toEqual({
      scope: 'shared',
      folder_id: 4,
      only_deleted: true,
    })
  })
})

describe('目录树 / 面包屑 / 后代', () => {
  const folders = [
    folder(1, null, 'A'),
    folder(2, 1, 'A-1'),
    folder(3, 1, 'A-2'),
    folder(4, 2, 'A-1-1'),
    folder(5, null, 'B'),
  ]

  it('buildFolderTree 正确嵌套并按名排序', () => {
    const tree = buildFolderTree(folders)
    expect(tree.map((n) => n.name)).toEqual(['A', 'B'])
    const a = tree[0]!
    expect(a.children.map((n) => n.name)).toEqual(['A-1', 'A-2'])
    expect(a.children[0]!.children.map((n) => n.name)).toEqual(['A-1-1'])
  })

  it('孤儿节点挂到根', () => {
    const tree = buildFolderTree([folder(9, 999, 'orphan')])
    expect(tree.map((n) => n.name)).toEqual(['orphan'])
  })

  it('folderBreadcrumb 从根到目标', () => {
    expect(folderBreadcrumb(folders, 4).map((f) => f.name)).toEqual(['A', 'A-1', 'A-1-1'])
    expect(folderBreadcrumb(folders, null)).toEqual([])
    expect(folderBreadcrumb(folders, 12345)).toEqual([])
  })

  it('collectDescendantIds 收集全部后代（不含自身）', () => {
    expect([...collectDescendantIds(folders, 1)].sort()).toEqual([2, 3, 4])
    expect([...collectDescendantIds(folders, 5)]).toEqual([])
  })
})
