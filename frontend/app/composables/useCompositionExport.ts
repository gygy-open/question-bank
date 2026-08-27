// 组稿版本导出下载的共享逻辑：编辑页头部快捷下载、版本历史列表行内下载、
// 版本只读预览页下载按钮共用同一份触发/报错提示/记忆格式逻辑，避免各处各写一遍。
import { ref } from 'vue'
import { toast } from 'vue-sonner'
import { useCompositions } from '@/composables/useCompositions'
import type { CompositionExportFormat, CompositionScope } from '@/types'

const LAST_FORMAT_STORAGE_KEY = 'qb:composition:last-export-format'

function sanitizeFilename(name: string): string {
  return name.replace(/[\\/:*?"<>|]/g, '_')
}

function readLastFormat(): CompositionExportFormat {
  if (typeof window === 'undefined') return 'docx'
  return window.localStorage.getItem(LAST_FORMAT_STORAGE_KEY) === 'latex' ? 'latex' : 'docx'
}

function rememberFormat(format: CompositionExportFormat): void {
  if (typeof window !== 'undefined') window.localStorage.setItem(LAST_FORMAT_STORAGE_KEY, format)
}

function parseExportError(err: unknown): { status?: number; detail?: string; nodeId?: string } {
  const e = err as { response?: { status?: number; _data?: { detail?: unknown; node_id?: string } } }
  const data = e?.response?._data
  return {
    status: e?.response?.status,
    detail: typeof data?.detail === 'string' ? data.detail : undefined,
    nodeId: data?.node_id,
  }
}

export function useCompositionExport() {
  const api = useCompositions()
  const exportingKey = ref<string | null>(null)

  function isExporting(compositionId: number, versionNo: number, format: CompositionExportFormat): boolean {
    return exportingKey.value === `${compositionId}:${versionNo}:${format}`
  }

  async function downloadVersion(params: {
    subjectId: number
    scope: CompositionScope
    compositionId: number
    versionNo: number
    title: string
    format: CompositionExportFormat
    onNotFound?: () => void
  }): Promise<boolean> {
    const { subjectId, scope, compositionId, versionNo, title, format, onNotFound } = params
    const key = `${compositionId}:${versionNo}:${format}`
    exportingKey.value = key
    try {
      const blob = await api.exportVersion(subjectId, scope, compositionId, versionNo, { format })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      const suffix = format === 'latex' ? '-latex.zip' : '.docx'
      link.setAttribute('download', sanitizeFilename(`${title}-v${versionNo}${suffix}`))
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      rememberFormat(format)
      toast.success('导出成功')
      return true
    } catch (err) {
      const { status, detail, nodeId } = parseExportError(err)
      if (status === 422) {
        const reason = detail ?? '内容存在无法识别的节点'
        toast.error(nodeId ? `导出失败：${reason}（节点 ${nodeId}）` : `导出失败：${reason}`)
      } else if (status === 404) {
        toast.error('版本不存在或无权访问')
        onNotFound?.()
      } else {
        toast.error('导出失败，请稍后重试')
      }
      return false
    } finally {
      if (exportingKey.value === key) exportingKey.value = null
    }
  }

  return { downloadVersion, isExporting, lastFormat: readLastFormat }
}
