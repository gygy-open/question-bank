<script setup lang="ts">
/**
 * 题干结构面板:查看、审核、编辑一道题(或一份材料)的题干拆解。
 *
 * 布局(规格 docs/specs/question-structure.md §8.1):
 *   头部(状态、来源、操作) → 任务进度 / 过期提示 → 体检汇总 → 原文(高亮)
 *   → 条件列表 → 设问列表 → 同结构题。
 *
 * 两种模式:
 * - 查看:悬停条目 ↔ 高亮原文片段双向联动;对待审版本可采纳 / 驳回。
 * - 编辑:在原文中选中文字即可「设为条件 / 设为设问」;每条可改写、选类型、排序、
 *   合并、拆分;保存为一份新的「人工修改」快照(AI 结果保留,便于对比)。
 *
 * 审核页通过 defineExpose 暴露 accept / reject / startEdit / redecompose,供键盘快捷键调用。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  ArrowDown, ArrowUp, Check, ChevronDown, ChevronRight, Combine, Copy, Loader2, Pencil, RefreshCw,
  Boxes, PackagePlus, Shuffle, Sparkles, Trash2, TriangleAlert, Variable, X,
} from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Textarea } from '@/components/ui/textarea'
import MathText from '@/components/structure/MathText.vue'
import StructTypeSelect from '@/components/structure/StructTypeSelect.vue'
import StructParamEditor, { type EditParam } from '@/components/structure/StructParamEditor.vue'
import StructVariantDialog from '@/components/structure/StructVariantDialog.vue'
import KnowledgeSuggestions from '@/components/structure/KnowledgeSuggestions.vue'
import StructComposeDialog from '@/components/structure/StructComposeDialog.vue'
import StructGroupReplaceDialog from '@/components/structure/StructGroupReplaceDialog.vue'
import { getApiErrorDetail } from '@/lib/apiErrors'
import { formatDateTime } from '@/lib/locale'
import { cn } from '@/lib/utils'
import {
  domainClasses, formatParamDomain, locateParamValue, spanInMath, stemTokens, tokenOffset, type StemToken,
} from '@/lib/structure'
import type {
  StructCheckIssue,
  StructElementGroup,
  StructGroupInput,
  StructFacet,
  StructItemInput,
  StructParam,
  StructParamInput,
  StructRun,
  StructSimilarItem,
  StructSimilarMode,
  StructTargetType,
  StructType,
  StructureView,
} from '~/types'

const props = withDefaults(defineProps<{
  targetType: StructTargetType
  targetId: number
  /** 同时有待审与已采纳版本时默认展示哪一个(审核页传 draft)。 */
  preferRun?: 'draft' | 'accepted'
}>(), {
  preferRun: 'draft',
})

const emit = defineEmits<{
  /** 保存、审核、重新拆解完成后通知外层刷新。 */
  (e: 'changed'): void
}>()

const { t } = useI18n()
const api = useStructure()

/** 编辑中的一条条件 / 设问。uid 只在本地使用,用来在编辑时表达「设问依赖哪些条件」。 */
interface EditItem {
  uid: number
  content: string
  source: string | null
  span: [number, number] | null
  type_id: number | null
  type_hint: string | null
  facet: StructFacet | null
  ref_element_id: number | null
  /** 仅设问:依赖的条件 uid。 */
  depends: number[]
}

// region 状态

// 当前展示的对象:默认是 props 指定的,点击「来自材料」的条件时可切换到材料。
const currentType = ref<StructTargetType>(props.targetType)
const currentId = ref<number>(props.targetId)

const view = ref<StructureView | null>(null)
const types = ref<StructType[]>([])
const canEdit = ref(false)
const loading = ref(false)
const busy = ref(false)
// 同时有待审与已采纳版本时,当前看哪一个。
const showing = ref<'draft' | 'accepted'>(props.preferRun)

const editing = ref(false)
const editElements = ref<EditItem[]>([])
const editAsks = ref<EditItem[]>([])
const editParams = ref<EditParam[]>([])
// 编辑模式:正在为哪条条目输入参数值(key 为 "e:<uid>" / "a:<uid>")及输入内容。
const paramDraftKey = ref<string | null>(null)
const paramDraftValue = ref('')
let nextUid = 1

const variantOpen = ref(false)

// 元素组:编辑中的组(成员用条件的本地 uid),以及整组替换、命题篮对话框。
interface EditGroup {
  uid: number
  name: string
  members: number[]
  replaceable: boolean
}
const editGroups = ref<EditGroup[]>([])
const replacingGroup = ref<StructElementGroup | null>(null)
const replaceOpen = ref(false)
const composeOpen = ref(false)
const basket = useComposeBasket()

// 悬停中的条目 key("e:<id>" / "a:<id>",编辑时用 uid),用于原文与列表的双向高亮。
const hoveredKey = ref<string | null>(null)

// 原文选区浮动工具条(编辑模式):选中范围在 stem_text 中的偏移 + 工具条位置。
const selection = ref<{ start: number, end: number, top: number, left: number } | null>(null)
const sourceBox = ref<HTMLElement | null>(null)

const similarOpen = ref(false)
const similarItems = ref<StructSimilarItem[] | null>(null)
const similarLoading = ref(false)
const similarMode = ref<StructSimilarMode>('types')
const similarModes = computed(() => [
  { value: 'types' as const, label: t('structure.panel.similarModes.types'), hint: t('structure.panel.similarModes.typesHint') },
  { value: 'elements' as const, label: t('structure.panel.similarModes.elements'), hint: t('structure.panel.similarModes.elementsHint') },
  { value: 'params' as const, label: t('structure.panel.similarModes.params'), hint: t('structure.panel.similarModes.paramsHint') },
])

// 任务进行中时轮询的定时器。
let pollTimer: ReturnType<typeof setInterval> | null = null

// endregion

// region 计算属性

/** 当前展示的拆解快照。 */
const run = computed<StructRun | null>(() => {
  const v = view.value
  if (!v) return null
  if (showing.value === 'accepted') return v.accepted ?? v.draft
  return v.draft ?? v.accepted
})

const hasBoth = computed(() => !!view.value?.draft && !!view.value?.accepted)
const enabled = computed(() => view.value?.enabled !== false)
const writable = computed(() => enabled.value && canEdit.value)
const isDraft = computed(() => run.value?.state === 'draft')

/** 原文、条目 key 与区间:编辑模式用本地编辑数据,查看模式用快照。 */
const stemText = computed(() => run.value?.stem_text ?? '')

const ranges = computed(() => {
  if (editing.value) {
    return [
      ...editElements.value.map(item => ({ key: `e:${item.uid}`, span: item.span })),
      ...editAsks.value.map(item => ({ key: `a:${item.uid}`, span: item.span })),
    ]
  }
  const r = run.value
  if (!r) return []
  return [
    ...r.elements.map(item => ({ key: `e:${item.id}`, span: item.span })),
    ...r.asks.map(item => ({ key: `a:${item.id}`, span: item.span })),
  ]
})

/** 参数的区间(key 以 "p:" 开头):原文中以下划线标出。 */
const paramRanges = computed(() => {
  if (editing.value) return editParams.value.map(p => ({ key: `p:${p.uid}`, span: p.span as [number, number] | null }))
  return (run.value?.params ?? []).map(p => ({ key: `p:${p.id}`, span: p.span }))
})

const tokens = computed(() => stemTokens(stemText.value, [...ranges.value, ...paramRanges.value]))

/** 条目 → 它的参数(查看模式)。 */
const paramsByOwner = computed(() => {
  const map = new Map<string, StructParam[]>()
  for (const param of run.value?.params ?? []) {
    const key = param.element_id != null ? `e:${param.element_id}` : `a:${param.ask_id}`
    map.set(key, [...(map.get(key) ?? []), param])
  }
  return map
})

/** 当前展示的是可用于命题的版本:题目的、已采纳且未过期的拆解。 */
const composable = computed(() =>
  currentType.value === 'question' && !!run.value && run.value.state === 'accepted' && !run.value.stale,
)

/** 能否生成变式:题目的、未过期的拆解里有可替换的参数,且有编辑权限。 */
const canVariant = computed(() =>
  writable.value && currentType.value === 'question' && !!run.value && !run.value.stale
  && run.value.state !== 'rejected' && run.value.params.some(p => p.replaceable && p.span),
)

/** key → 类型 id:原文片段按覆盖它的第一条条目所属领域着色。 */
const typeByKey = computed(() => {
  const map = new Map<string, number | null>()
  if (editing.value) {
    for (const item of editElements.value) map.set(`e:${item.uid}`, item.type_id)
    for (const item of editAsks.value) map.set(`a:${item.uid}`, item.type_id)
  } else if (run.value) {
    for (const item of run.value.elements) map.set(`e:${item.id}`, item.type_id)
    for (const item of run.value.asks) map.set(`a:${item.id}`, item.type_id)
  }
  return map
})

/** 体检问题按条目分组:"element:0" → issues;整题级的放在 "stem"。 */
const issuesByItem = computed(() => {
  const grouped = new Map<string, StructCheckIssue[]>()
  for (const issue of run.value?.check_report?.issues ?? []) {
    if (issue.severity === 'info' && issue.code !== 'uncovered') continue
    const key = issue.target != null && issue.index != null ? `${issue.target}:${issue.index}` : 'stem'
    const list = grouped.get(key) ?? []
    list.push(issue)
    grouped.set(key, list)
  }
  return grouped
})

const coveragePercent = computed(() => `${Math.round((run.value?.check_report?.coverage ?? 0) * 100)}%`)

/** 条件序号:设问「依赖：1、3」用。 */
const elementNumber = computed(() => {
  const map = new Map<number, number>()
  run.value?.elements.forEach((item, index) => map.set(item.id, index + 1))
  return map
})

const facetOptions = computed(() => [
  { value: '', label: t('structure.panel.noFacet') },
  ...(['form', 'quant', 'qual', 'proc'] as StructFacet[]).map(value => ({ value, label: t(`structure.facets.${value}`) })),
])

const jobLabel = computed(() => {
  const job = view.value?.job
  if (!job) return ''
  if (job.status === 'pending' && job.queue_ahead != null) {
    return t('structure.panel.jobQueued', { count: job.queue_ahead })
  }
  if (job.status === 'paused') {
    const reason = job.paused_reason ? t(`structure.pausedReasons.${job.paused_reason}`) : ''
    return t('structure.panel.jobPaused', { reason })
  }
  return t(`structure.jobStatuses.${job.status}`)
})

// endregion

// region 公共方法(审核页的快捷键也会调用)

/** 重新加载全貌、类型树与权限。 */
async function load(): Promise<void> {
  loading.value = true
  try {
    const result = await api.getView(currentType.value, currentId.value)
    applyView(result)
    if (result.subject_id != null) {
      // 类型树与权限按学科取一次即可;切换对象时学科一般不变,但这里简单起见每次都取。
      const [typeList, settings] = await Promise.all([
        api.listTypes(result.subject_id),
        api.getSettings(result.subject_id),
      ])
      types.value = typeList.items
      canEdit.value = !!settings.can_edit
    }
  } catch (e) {
    toast.error(t('structure.panel.loadFailed'), { description: getApiErrorDetail(e, '') })
  } finally {
    loading.value = false
  }
}

/** 排队(重新)拆解,并开始轮询进度。 */
async function redecompose(): Promise<void> {
  if (!writable.value || busy.value) return
  busy.value = true
  try {
    const result = await api.decompose([currentId.value], currentType.value)
    if (!result.queued.length) {
      toast.error(t('structure.panel.decomposeSkipped'))
      return
    }
    toast.success(t('structure.panel.decomposeQueued'))
    applyView(await api.getView(currentType.value, currentId.value))
  } catch (e) {
    toast.error(t('structure.panel.decomposeFailed'), { description: getApiErrorDetail(e, '') })
  } finally {
    busy.value = false
  }
}

/** 采纳当前展示的待审版本。 */
async function accept(): Promise<void> {
  await reviewCurrent('accept')
}

/** 驳回当前展示的待审版本。 */
async function reject(): Promise<void> {
  await reviewCurrent('reject')
}

/** 进入编辑模式:以当前展示的快照为起点复制一份本地数据。 */
function startEdit(): void {
  if (!writable.value) return
  const r = run.value
  const elementUid = new Map<number, number>()
  editElements.value = (r?.elements ?? []).map((item) => {
    const uid = nextUid++
    elementUid.set(item.id, uid)
    return {
      uid,
      content: item.content,
      source: item.span ? stemText.value.slice(item.span[0], item.span[1]) : null,
      span: item.span,
      type_id: item.type_id,
      type_hint: item.type_hint,
      facet: item.facet,
      ref_element_id: item.ref_element_id,
      depends: [],
    }
  })
  const askUid = new Map<number, number>()
  editAsks.value = (r?.asks ?? []).map((item) => {
    const uid = nextUid++
    askUid.set(item.id, uid)
    return {
      uid,
      content: item.content,
      source: item.span ? stemText.value.slice(item.span[0], item.span[1]) : null,
      span: item.span,
      type_id: item.type_id,
      type_hint: item.type_hint,
      facet: null,
      ref_element_id: null,
      // 设问依赖用条件 id 记录,这里换成本地 uid,保存时再换成下标。
      depends: item.depends_on.map(id => elementUid.get(id)).filter((dep): dep is number => dep != null),
    }
  })
  editParams.value = (r?.params ?? []).flatMap((param) => {
    const ownerUid = param.element_id != null ? elementUid.get(param.element_id) : askUid.get(param.ask_id ?? -1)
    if (ownerUid == null || !param.span) return []
    return [{
      uid: nextUid++,
      ownerKind: param.element_id != null ? 'element' as const : 'ask' as const,
      ownerUid,
      name: param.name,
      value: param.value,
      slot_kind: param.slot_kind,
      span: param.span,
      domain: param.domain ? { ...param.domain } : null,
      domain_confirmed: param.domain_confirmed,
      replaceable: param.replaceable,
    }]
  })
  editGroups.value = (r?.groups ?? []).map(group => ({
    uid: nextUid++,
    name: group.name,
    members: group.element_ids.map(id => elementUid.get(id)).filter((uid): uid is number => uid != null),
    replaceable: group.replaceable,
  }))
  paramDraftKey.value = null
  editing.value = true
  selection.value = null
}

function cancelEdit(): void {
  editing.value = false
  selection.value = null
}

/** 保存编辑结果;accept=true 时同时采纳。 */
async function saveEdit(acceptNow: boolean): Promise<void> {
  if (busy.value) return
  // 空内容的条目没有意义,保存前提示而不是交给后端报错。
  if ([...editElements.value, ...editAsks.value].some(item => !item.content.trim())) {
    toast.error(t('structure.panel.emptyItem'))
    return
  }
  busy.value = true
  try {
    const indexOfUid = new Map(editElements.value.map((item, index) => [item.uid, index]))
    const toInput = (item: EditItem, isAsk: boolean): StructItemInput => ({
      content: item.content.trim(),
      source: item.source,
      span_start: item.span?.[0] ?? null,
      span_end: item.span?.[1] ?? null,
      type_id: item.type_id,
      type_hint: item.type_id ? null : item.type_hint,
      facet: isAsk ? null : item.facet,
      ref_element_id: isAsk ? null : item.ref_element_id,
      depends_on: isAsk
        ? item.depends.map(uid => indexOfUid.get(uid)).filter((index): index is number => index != null)
        : [],
    })
    const askIndexOfUid = new Map(editAsks.value.map((item, index) => [item.uid, index]))
    const params: StructParamInput[] = editParams.value.flatMap((param) => {
      const ownerIndex = (param.ownerKind === 'element' ? indexOfUid : askIndexOfUid).get(param.ownerUid)
      if (ownerIndex == null) return []
      return [{
        owner: param.ownerKind,
        owner_index: ownerIndex,
        name: param.name.trim() || param.value,
        value: param.value,
        slot_kind: param.slot_kind,
        span_start: param.span[0],
        span_end: param.span[1],
        domain: param.domain,
        domain_confirmed: param.domain_confirmed && !!param.domain,
        replaceable: param.replaceable,
      }]
    })
    const result = await api.save({
      target_type: currentType.value,
      target_id: currentId.value,
      base_run_id: run.value?.id ?? null,
      elements: editElements.value.map(item => toInput(item, false)),
      asks: editAsks.value.map(item => toInput(item, true)),
      params,
      groups: editGroups.value
        .map((group): StructGroupInput => ({
          name: group.name.trim(),
          replaceable: group.replaceable,
          element_indices: group.members.map(uid => indexOfUid.get(uid)).filter((i): i is number => i != null),
        }))
        .filter(group => group.name && group.element_indices.length >= 2),
      accept: acceptNow,
    })
    editing.value = false
    showing.value = acceptNow ? 'accepted' : 'draft'
    applyView(result)
    toast.success(t(acceptNow ? 'structure.panel.savedAccepted' : 'structure.panel.saved'))
    emit('changed')
  } catch (e) {
    toast.error(t('common.saveFailed'), { description: getApiErrorDetail(e, '') })
  } finally {
    busy.value = false
  }
}

defineExpose({ accept, reject, startEdit, redecompose, reload: load, isDraft, editing })

// endregion

// region 事件处理:编辑操作

/** 原文中松开鼠标:把选区换算成 stem_text 偏移,在选区上方显示「设为条件 / 设问」工具条。 */
function onSourceMouseUp(): void {
  if (!editing.value) return
  const range = window.getSelection()?.rangeCount ? window.getSelection()!.getRangeAt(0) : null
  if (!range || range.collapsed || !sourceBox.value?.contains(range.commonAncestorContainer)) {
    selection.value = null
    return
  }
  const start = resolveEdge(range.startContainer, range.startOffset, 'start')
  const end = resolveEdge(range.endContainer, range.endOffset, 'end')
  if (start == null || end == null || end <= start) {
    selection.value = null
    return
  }
  // 工具条定位在选区矩形上方,坐标相对原文容器。
  const rect = range.getBoundingClientRect()
  const box = sourceBox.value.getBoundingClientRect()
  selection.value = { start, end, top: rect.top - box.top - 36, left: Math.max(0, rect.left - box.left) }
}

/** 选区 → 新增一条条件或设问。 */
function addFromSelection(kind: 'element' | 'ask'): void {
  if (!selection.value) return
  const { start, end } = selection.value
  const text = stemText.value.slice(start, end).trim()
  const item: EditItem = {
    uid: nextUid++,
    content: text,
    source: stemText.value.slice(start, end),
    span: [start, end],
    type_id: null,
    type_hint: null,
    facet: null,
    ref_element_id: null,
    depends: [],
  }
  if (kind === 'element') insertBySpan(editElements.value, item)
  else insertBySpan(editAsks.value, item)
  selection.value = null
  window.getSelection()?.removeAllRanges()
}

/** 手动新增一条空条目(没有原文对应,例如需要补充的隐含说明)。 */
function addEmpty(kind: 'element' | 'ask'): void {
  const item: EditItem = {
    uid: nextUid++, content: '', source: null, span: null, type_id: null, type_hint: null,
    facet: null, ref_element_id: null, depends: [],
  }
  if (kind === 'element') editElements.value.push(item)
  else editAsks.value.push(item)
}

/** 选区 → 参数:挂在原文区间包含该选区的第一条条件(其次设问)上。 */
function addParamFromSelection(): void {
  if (!selection.value) return
  const { start, end } = selection.value
  const owner = findOwner(start, end)
  if (!owner) {
    toast.error(t('structure.params.noOwner'))
    return
  }
  addParam(owner.kind, owner.item, [start, end])
  selection.value = null
  window.getSelection()?.removeAllRanges()
}

/** 条目下「添加参数」:在该条目的原文区间里找输入的值(公式里的数也能找到)。 */
function submitParamDraft(kind: 'element' | 'ask', item: EditItem): void {
  const value = paramDraftValue.value.trim()
  if (!value || !item.span) return
  const occupied = editParams.value.filter(p => p.ownerKind === kind && p.ownerUid === item.uid).length
  let span: [number, number] | null = null
  for (let occurrence = 1; occurrence <= occupied + 1; occurrence += 1) {
    const found = locateParamValue(stemText.value, value, item.span, occurrence)
    if (found && !editParams.value.some(p => p.span[0] < found[1] && p.span[1] > found[0])) {
      span = found
      break
    }
  }
  if (!span) {
    toast.error(t('structure.params.notFound', { value }))
    return
  }
  addParam(kind, item, span)
  paramDraftKey.value = null
  paramDraftValue.value = ''
}

function addParam(kind: 'element' | 'ask', item: EditItem, span: [number, number]): void {
  if (editParams.value.some(p => p.span[0] < span[1] && p.span[1] > span[0])) {
    toast.error(t('structure.params.overlap'))
    return
  }
  const value = stemText.value.slice(span[0], span[1])
  editParams.value.push({
    uid: nextUid++,
    ownerKind: kind,
    ownerUid: item.uid,
    name: value,
    value,
    slot_kind: /^-?[\d.]+$/.test(value) ? 'numeric' : 'expression',
    span,
    domain: null,
    domain_confirmed: false,
    replaceable: true,
  })
}

function removeParam(uid: number): void {
  editParams.value = editParams.value.filter(p => p.uid !== uid)
}

function paramsOf(kind: 'element' | 'ask', uid: number): EditParam[] {
  return editParams.value.filter(p => p.ownerKind === kind && p.ownerUid === uid)
}

function openParamDraft(key: string): void {
  paramDraftKey.value = paramDraftKey.value === key ? null : key
  paramDraftValue.value = ''
}

function addGroup(): void {
  editGroups.value.push({ uid: nextUid++, name: '', members: [], replaceable: true })
}

/** 一条条件只能属于一个组:勾选时从其他组移出。 */
function toggleGroupMember(group: EditGroup, uid: number, checked: boolean | 'indeterminate'): void {
  if (checked === true) {
    for (const other of editGroups.value) other.members = other.members.filter(m => m !== uid)
    group.members.push(uid)
  } else {
    group.members = group.members.filter(m => m !== uid)
  }
}

function openReplace(group: StructElementGroup): void {
  replacingGroup.value = group
  replaceOpen.value = true
}

function groupMembers(group: StructElementGroup): string[] {
  return (run.value?.elements ?? []).filter(e => group.element_ids.includes(e.id)).map(e => e.content)
}

/** 加入命题篮;篮中是其他学科的条目时会先清空。 */
function addToBasket(kind: 'element' | 'ask' | 'group', id: number, content: string): void {
  const cleared = basket.add({ kind, id, question_id: currentId.value, subject_id: view.value?.subject_id ?? null, content })
  toast.success(t(cleared ? 'structure.compose.addedNewSubject' : 'structure.compose.added'))
}

function move(list: EditItem[], index: number, delta: -1 | 1): void {
  const target = index + delta
  if (target < 0 || target >= list.length) return
  const [item] = list.splice(index, 1)
  list.splice(target, 0, item!)
}

function removeItem(list: EditItem[], index: number, kind: 'element' | 'ask'): void {
  const [removed] = list.splice(index, 1)
  if (removed) editParams.value = editParams.value.filter(p => !(p.ownerKind === kind && p.ownerUid === removed.uid))
  if (removed && kind === 'element') {
    for (const group of editGroups.value) group.members = group.members.filter(uid => uid !== removed.uid)
  }
  // 删除条件时,同时从各设问的依赖里去掉它。
  if (kind === 'element' && removed) {
    for (const ask of editAsks.value) ask.depends = ask.depends.filter(uid => uid !== removed.uid)
  }
}

/** 合并相邻两条条件:内容用「；」连接,原文区间取两者的并集。 */
function mergeWithNext(index: number): void {
  const list = editElements.value
  const first = list[index]
  const second = list[index + 1]
  if (!first || !second) return
  const span: [number, number] | null = first.span && second.span
    ? [Math.min(first.span[0], second.span[0]), Math.max(first.span[1], second.span[1])]
    : first.span ?? second.span
  first.content = [first.content, second.content].filter(Boolean).join(t('structure.panel.mergeSeparator'))
  first.span = span
  first.source = span ? stemText.value.slice(span[0], span[1]) : first.source
  first.type_id = first.type_id ?? second.type_id
  list.splice(index + 1, 1)
  for (const param of editParams.value) {
    if (param.ownerKind === 'element' && param.ownerUid === second.uid) param.ownerUid = first.uid
  }
  for (const group of editGroups.value) {
    group.members = [...new Set(group.members.map(uid => (uid === second.uid ? first.uid : uid)))]
  }
  // 依赖了被合并条件的设问,改为依赖合并后的条件。
  for (const ask of editAsks.value) {
    if (ask.depends.includes(second.uid)) {
      ask.depends = [...new Set(ask.depends.map(uid => (uid === second.uid ? first.uid : uid)))]
    }
  }
}

/** 拆分:复制一条紧随其后,再分别修改内容。 */
function splitItem(list: EditItem[], index: number): void {
  const item = list[index]
  if (!item) return
  list.splice(index + 1, 0, { ...item, uid: nextUid++, depends: [...item.depends] })
}

function toggleDepend(ask: EditItem, uid: number, checked: boolean | 'indeterminate'): void {
  ask.depends = checked === true ? [...new Set([...ask.depends, uid])] : ask.depends.filter(value => value !== uid)
}

// endregion

// region 事件处理:其他

/** 点击「来自材料」:在面板内切换到材料的拆解。 */
async function openStimulus(stimulusId: number): Promise<void> {
  currentType.value = 'stimulus'
  currentId.value = stimulusId
  editing.value = false
  await load()
}

/** 从材料返回原题。 */
async function backToTarget(): Promise<void> {
  currentType.value = props.targetType
  currentId.value = props.targetId
  await load()
}

async function toggleSimilar(): Promise<void> {
  similarOpen.value = !similarOpen.value
  if (!similarOpen.value || similarItems.value) return
  await loadSimilar()
}

/** 切换相关题的查找方式(类型相近 / 共享条件)并重新加载。 */
async function setSimilarMode(mode: StructSimilarMode): Promise<void> {
  if (similarMode.value === mode) return
  similarMode.value = mode
  await loadSimilar()
}

async function loadSimilar(): Promise<void> {
  if (currentType.value !== 'question') return
  similarLoading.value = true
  try {
    similarItems.value = (await api.similar(currentId.value, { mode: similarMode.value })).items
  } catch (e) {
    toast.error(t('structure.panel.loadFailed'), { description: getApiErrorDetail(e, '') })
  } finally {
    similarLoading.value = false
  }
}

// endregion

// region 内部辅助函数

/** 写入新的全貌,并根据是否有进行中的任务开启 / 停止轮询。 */
function applyView(next: StructureView): void {
  const hadJob = !!view.value?.job
  view.value = next
  if (!next.draft && next.accepted) showing.value = 'accepted'
  else if (next.draft && props.preferRun === 'draft') showing.value = 'draft'
  if (next.job) startPolling()
  else {
    stopPolling()
    // 任务刚结束(从有到无):有了新的拆解结果,通知外层刷新列表。
    if (hadJob) {
      similarItems.value = null
      emit('changed')
    }
  }
}

function startPolling(): void {
  if (pollTimer) return
  // 每 3 秒拉一次:拆解通常十几秒完成,太频繁会给后端无谓压力。
  pollTimer = setInterval(async () => {
    try {
      applyView(await api.getView(currentType.value, currentId.value))
    } catch {
      stopPolling()
    }
  }, 3000)
}

function stopPolling(): void {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
}

async function reviewCurrent(action: 'accept' | 'reject'): Promise<void> {
  const r = run.value
  if (!writable.value || !r || r.state !== 'draft' || busy.value) return
  busy.value = true
  try {
    const result = await api.review([r.id], action)
    if (!result.updated.length) {
      toast.error(t('structure.panel.reviewSkipped'))
      return
    }
    toast.success(t(action === 'accept' ? 'structure.panel.accepted' : 'structure.panel.rejected'))
    showing.value = 'accepted'
    applyView(await api.getView(currentType.value, currentId.value))
    emit('changed')
  } catch (e) {
    toast.error(t('structure.panel.reviewFailed'), { description: getApiErrorDetail(e, '') })
  } finally {
    busy.value = false
  }
}

/**
 * 选区端点(DOM 节点 + 偏移) → stem_text 偏移。
 *
 * 原文按渲染单元输出,每个单元元素带 data-token(在 tokens 中的下标)。文字单元的 DOM 文本与
 * 原文一一对应,可以直接用单元内偏移;公式单元由 KaTeX 渲染,DOM 文本与 LaTeX 不对应,
 * 因此落在公式里的端点吸附到公式边界(见 tokenOffset)。
 */
function resolveEdge(node: Node, offset: number, edge: 'start' | 'end'): number | null {
  const element = (node.nodeType === Node.ELEMENT_NODE ? node as Element : node.parentElement)
    ?.closest<HTMLElement>('[data-token]')
  if (!element) {
    // 端点落在单元之间(例如容器本身):按容器子节点位置取最近单元的边界。
    return null
  }
  const token: StemToken | undefined = tokens.value[Number(element.dataset.token)]
  if (!token) return null
  if (token.math) return tokenOffset(token, 0, edge)
  // 单元内偏移 = 从单元开头到端点的文字长度。
  const probe = document.createRange()
  probe.setStart(element, 0)
  probe.setEnd(node, offset)
  return tokenOffset(token, probe.toString().length, edge)
}

/** 原文区间包含 [start, end) 的第一条条件(其次设问)。 */
function findOwner(start: number, end: number): { kind: 'element' | 'ask', item: EditItem } | null {
  const contains = (item: EditItem) => !!item.span && item.span[0] <= start && end <= item.span[1]
  const element = editElements.value.find(contains)
  if (element) return { kind: 'element', item: element }
  const ask = editAsks.value.find(contains)
  return ask ? { kind: 'ask', item: ask } : null
}

/** 参数值的展示:落在公式里的参数值是 LaTeX,包上 $ 渲染。 */
function paramText(value: string, span: [number, number] | null): string {
  return span && spanInMath(stemText.value, span) ? `$${value}$` : value
}

/** 按原文位置插入,让列表顺序与题干顺序一致。 */
function insertBySpan(list: EditItem[], item: EditItem): void {
  const position = item.span?.[0] ?? Number.MAX_SAFE_INTEGER
  const index = list.findIndex(other => (other.span?.[0] ?? Number.MAX_SAFE_INTEGER) > position)
  if (index < 0) list.push(item)
  else list.splice(index, 0, item)
}

/** 原文单元的高亮样式:被悬停条目覆盖的加深,其余被覆盖的按领域浅色。 */
function tokenClass(token: StemToken): string {
  const itemKeys = token.keys.filter(key => !key.startsWith('p:'))
  const param = token.keys.some(key => key.startsWith('p:'))
    && 'underline decoration-primary decoration-dotted decoration-2 underline-offset-4'
  if (!itemKeys.length) return cn(param)
  const hovered = hoveredKey.value != null && token.keys.includes(hoveredKey.value)
  const colors = domainClasses(types.value, typeByKey.value.get(itemKeys[0]!) ?? null)
  return cn('rounded-sm transition-colors', colors.bg, param, hovered && 'ring-2 ring-primary/60 bg-primary/20')
}

function hoverToken(token: StemToken): void {
  const key = token.keys.find(k => !k.startsWith('p:'))
  if (key) hoveredKey.value = key
}

function typeLabel(path: string[]): string {
  return path.join(' › ')
}

function issueText(issue: StructCheckIssue): string {
  const key = `structure.check.codes.${issue.code}`
  const text = t(key, { detail: issue.detail })
  return text === key ? issue.message : text
}

function itemIssues(target: 'element' | 'ask', index: number): StructCheckIssue[] {
  return issuesByItem.value.get(`${target}:${index}`) ?? []
}

// endregion

watch(
  () => [props.targetType, props.targetId] as const,
  ([type, id]) => {
    currentType.value = type
    currentId.value = id
    editing.value = false
    similarOpen.value = false
    similarItems.value = null
    showing.value = props.preferRun
    void load()
  },
  { immediate: true },
)

onBeforeUnmount(stopPolling)
</script>

<template>
  <div class="space-y-4">
    <div v-if="loading && !view" class="flex items-center gap-2 py-10 text-sm text-muted-foreground">
      <Loader2 class="h-4 w-4 animate-spin" /> {{ t('common.loading') }}
    </div>

    <template v-else-if="view">
      <!-- 查看材料时提供返回原题 -->
      <button
        v-if="currentType !== targetType || currentId !== targetId"
        type="button"
        class="text-sm text-primary hover:underline"
        @click="backToTarget"
      >
        ← {{ t('structure.panel.backToQuestion') }}
      </button>

      <!-- 头部:状态、来源、操作 -->
      <div class="flex flex-wrap items-center gap-2">
        <template v-if="run">
          <Badge variant="outline" :class="isDraft ? 'border-amber-500/50 text-amber-700 dark:text-amber-300' : 'border-emerald-500/40 text-emerald-700 dark:text-emerald-300'">
            {{ t(`structure.runStates.${run.state}`) }}
          </Badge>
          <Badge v-if="run.stale" variant="outline" class="border-destructive/40 text-destructive">
            {{ t('structure.states.stale') }}
          </Badge>
          <span class="text-xs text-muted-foreground">
            {{ t(`structure.origins.${run.origin}`) }}<template v-if="run.model"> · {{ run.model }}</template><template v-if="run.prompt_version"> · {{ run.prompt_version }}</template>
            · {{ formatDateTime(run.created_at) }}
          </span>
          <div v-if="hasBoth && !editing" class="ml-1 inline-flex overflow-hidden rounded-md border text-xs">
            <button
              type="button"
              :class="cn('px-2 py-0.5', showing === 'draft' ? 'bg-accent font-medium' : 'text-muted-foreground')"
              @click="showing = 'draft'"
            >{{ t('structure.runStates.draft') }}</button>
            <button
              type="button"
              :class="cn('border-l px-2 py-0.5', showing === 'accepted' ? 'bg-accent font-medium' : 'text-muted-foreground')"
              @click="showing = 'accepted'"
            >{{ t('structure.runStates.accepted') }}</button>
          </div>
        </template>

        <div v-if="writable && !editing" class="ml-auto flex flex-wrap items-center gap-2">
          <Button v-if="run && isDraft" size="sm" :disabled="busy" @click="accept">
            <Check class="mr-1 h-4 w-4" /> {{ t('structure.panel.accept') }}
          </Button>
          <Button v-if="run && isDraft" size="sm" variant="outline" :disabled="busy" @click="reject">
            <X class="mr-1 h-4 w-4" /> {{ t('structure.panel.reject') }}
          </Button>
          <Button v-if="run" size="sm" variant="outline" :disabled="busy" @click="startEdit">
            <Pencil class="mr-1 h-4 w-4" /> {{ t('structure.panel.edit') }}
          </Button>
          <Button v-if="canVariant" size="sm" variant="outline" :disabled="busy" @click="variantOpen = true">
            <Shuffle class="mr-1 h-4 w-4" /> {{ t('structure.variant.button') }}
          </Button>
          <Button v-if="basket.count.value" size="sm" variant="outline" @click="composeOpen = true">
            <Boxes class="mr-1 h-4 w-4" /> {{ t('structure.compose.basket', { count: basket.count.value }) }}
          </Button>
          <Button v-if="run" size="sm" variant="ghost" :disabled="busy || !!view.job" @click="redecompose">
            <RefreshCw class="mr-1 h-4 w-4" /> {{ t('structure.panel.redecompose') }}
          </Button>
        </div>
        <div v-if="editing" class="ml-auto flex flex-wrap items-center gap-2">
          <Button size="sm" :disabled="busy" @click="saveEdit(true)">
            <Check class="mr-1 h-4 w-4" /> {{ t('structure.panel.saveAndAccept') }}
          </Button>
          <Button size="sm" variant="outline" :disabled="busy" @click="saveEdit(false)">
            {{ t('structure.panel.saveDraft') }}
          </Button>
          <Button size="sm" variant="ghost" :disabled="busy" @click="cancelEdit">
            {{ t('common.cancel') }}
          </Button>
        </div>
      </div>

      <p v-if="!enabled" class="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
        {{ t('structure.panel.disabled') }}
      </p>

      <!-- 进行中的拆解任务 -->
      <div v-if="view.job" class="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm">
        <Loader2 v-if="view.job.status !== 'paused'" class="h-4 w-4 animate-spin text-primary" />
        <TriangleAlert v-else class="h-4 w-4 text-amber-600" />
        <span>{{ jobLabel }}</span>
      </div>

      <!-- 已过期 -->
      <div
        v-if="run?.stale && !editing"
        class="flex flex-wrap items-center gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm"
      >
        <TriangleAlert class="h-4 w-4 text-destructive" />
        <span>{{ t('structure.panel.staleHint') }}</span>
        <Button v-if="writable" size="sm" variant="outline" class="ml-auto" :disabled="busy || !!view.job" @click="redecompose">
          {{ t('structure.panel.redecompose') }}
        </Button>
      </div>

      <!-- 还没有任何拆解 -->
      <div v-if="!run && !view.job" class="rounded-lg border border-dashed px-4 py-8 text-center">
        <Sparkles class="mx-auto mb-2 h-6 w-6 text-muted-foreground" />
        <p class="mb-3 text-sm text-muted-foreground">{{ t('structure.panel.empty') }}</p>
        <Button v-if="writable" size="sm" :disabled="busy" @click="redecompose">
          {{ t('structure.panel.start') }}
        </Button>
      </div>

      <template v-if="run">
        <!-- 体检汇总 -->
        <div v-if="run.check_report && !editing" class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
          <span class="font-medium">{{ t('structure.check.title') }}</span>
          <span v-if="run.check_report.errors === 0 && run.check_report.warnings === 0" class="text-emerald-700 dark:text-emerald-300">
            {{ t('structure.check.ok') }}
          </span>
          <span v-else :class="run.check_report.errors ? 'text-destructive' : 'text-amber-700 dark:text-amber-300'">
            {{ t('structure.check.summary', { errors: run.check_report.errors, warnings: run.check_report.warnings }) }}
          </span>
          <span class="text-muted-foreground">{{ t('structure.check.coverage', { percent: coveragePercent }) }}</span>
        </div>

        <!-- 原文:按渲染单元输出,公式整体渲染;编辑模式下可选中文字新增条目 -->
        <div class="relative">
          <div class="mb-1 flex items-center justify-between text-xs text-muted-foreground">
            <span>{{ t('structure.panel.source') }}</span>
            <span v-if="editing">{{ t('structure.panel.selectHint') }}</span>
          </div>
          <div
            ref="sourceBox"
            class="relative rounded-md border bg-muted/30 px-3 py-2 text-sm leading-7"
            @mouseup="onSourceMouseUp"
          >
            <span
              v-for="(token, index) in tokens"
              :key="`${token.start}-${token.end}`"
              :data-token="index"
              :class="tokenClass(token)"
              @mouseenter="hoverToken(token)"
              @mouseleave="hoveredKey = null"
            ><MathText v-if="token.math" :text="token.display ? `$$${token.value}$$` : `$${token.value}$`" /><span v-else class="whitespace-pre-wrap">{{ token.value }}</span></span>

            <!-- 选区工具条 -->
            <div
              v-if="selection"
              class="absolute z-10 flex gap-1 rounded-md border bg-popover p-1 shadow-md"
              :style="{ top: `${Math.max(0, selection.top)}px`, left: `${selection.left}px` }"
              @mousedown.prevent
            >
              <Button size="sm" variant="ghost" class="h-7 px-2" @click="addFromSelection('element')">
                {{ t('structure.panel.asCondition') }}
              </Button>
              <Button size="sm" variant="ghost" class="h-7 px-2" @click="addFromSelection('ask')">
                {{ t('structure.panel.asAsk') }}
              </Button>
              <Button size="sm" variant="ghost" class="h-7 px-2" @click="addParamFromSelection">
                {{ t('structure.params.asParam') }}
              </Button>
            </div>
          </div>
          <ul v-if="!editing && issuesByItem.get('stem')?.length" class="mt-1 space-y-0.5 text-xs">
            <li v-for="(issue, i) in issuesByItem.get('stem')" :key="i" class="text-muted-foreground">
              {{ issue.code === 'uncovered' ? t('structure.check.residual', { text: issue.detail }) : issueText(issue) }}
            </li>
          </ul>
        </div>

        <!-- 查看模式:条件与设问 -->
        <template v-if="!editing">
          <section>
            <h4 class="mb-2 text-sm font-medium">{{ t('structure.conditions') }} <span class="text-muted-foreground">({{ run.elements.length }})</span></h4>
            <ol class="space-y-1.5">
              <li
                v-for="(item, index) in run.elements"
                :key="item.id"
                :class="cn('rounded-md border px-3 py-2 transition-colors', hoveredKey === `e:${item.id}` && 'border-primary bg-primary/5')"
                @mouseenter="hoveredKey = `e:${item.id}`"
                @mouseleave="hoveredKey = null"
              >
                <div class="flex items-start gap-2 text-sm">
                  <span class="mt-0.5 w-5 shrink-0 text-xs text-muted-foreground">{{ index + 1 }}</span>
                  <div class="min-w-0 flex-1 space-y-1">
                    <MathText :text="item.content" />
                    <div class="flex flex-wrap items-center gap-1.5 text-xs">
                      <span
                        v-if="item.type_path.length"
                        :class="cn('rounded border px-1.5 py-0.5', domainClasses(types, item.type_id).border, domainClasses(types, item.type_id).text)"
                      >{{ typeLabel(item.type_path) }}</span>
                      <span v-if="item.type_hint && item.type_path.length" class="italic text-muted-foreground">{{ item.type_hint }}</span>
                      <NuxtLink
                        v-else-if="item.type_hint"
                        to="/structure/types?tab=candidates"
                        class="italic text-muted-foreground underline-offset-2 hover:underline"
                        :title="t('structure.panel.unclassifiedLink')"
                      >{{ t('structure.panel.unclassifiedHint', { hint: item.type_hint }) }}</NuxtLink>
                      <span v-else-if="!item.type_path.length" class="italic text-muted-foreground">{{ t('structure.unclassified') }}</span>
                      <Badge v-if="item.facet" variant="secondary" class="h-5 px-1.5 text-[11px] font-normal">{{ t(`structure.facets.${item.facet}`) }}</Badge>
                      <button
                        v-if="item.shared_from_stimulus_id"
                        type="button"
                        class="text-primary hover:underline"
                        @click="openStimulus(item.shared_from_stimulus_id)"
                      >{{ t('structure.shared') }}</button>
                      <button
                        v-if="composable"
                        type="button"
                        :class="cn('ml-auto text-muted-foreground hover:text-primary', basket.has('element', item.id) && 'text-primary')"
                        :title="t('structure.compose.add')"
                        @click="addToBasket('element', item.id, item.content)"
                      ><PackagePlus class="h-3.5 w-3.5" /></button>
                    </div>
                    <div v-if="paramsByOwner.get(`e:${item.id}`)?.length" class="flex flex-wrap gap-1.5 text-xs">
                      <span
                        v-for="param in paramsByOwner.get(`e:${item.id}`)"
                        :key="param.id"
                        class="inline-flex items-center gap-1 rounded border border-dashed border-primary/40 px-1.5 py-0.5"
                        :title="formatParamDomain(param.domain)"
                      >
                        <Variable class="h-3 w-3 text-primary" />{{ param.name }} = <MathText :text="paramText(param.value, param.span)" />
                        <span v-if="param.domain" :class="param.domain_confirmed ? 'text-emerald-600' : 'text-amber-600'">
                          {{ param.domain_confirmed ? '✓' : '?' }}
                        </span>
                      </span>
                    </div>
                    <p
                      v-for="(issue, i) in itemIssues('element', index)"
                      :key="i"
                      :class="cn('text-xs', issue.severity === 'error' ? 'text-destructive' : 'text-amber-700 dark:text-amber-300')"
                    >{{ issueText(issue) }}</p>
                  </div>
                </div>
              </li>
              <li v-if="!run.elements.length" class="text-sm text-muted-foreground">{{ t('structure.panel.noConditions') }}</li>
            </ol>
          </section>

          <section>
            <h4 class="mb-2 text-sm font-medium">{{ t('structure.asks') }} <span class="text-muted-foreground">({{ run.asks.length }})</span></h4>
            <ol class="space-y-1.5">
              <li
                v-for="(item, index) in run.asks"
                :key="item.id"
                :class="cn('rounded-md border px-3 py-2 transition-colors', hoveredKey === `a:${item.id}` && 'border-primary bg-primary/5')"
                @mouseenter="hoveredKey = `a:${item.id}`"
                @mouseleave="hoveredKey = null"
              >
                <div class="flex items-start gap-2 text-sm">
                  <span class="mt-0.5 w-5 shrink-0 text-xs text-muted-foreground">Q{{ index + 1 }}</span>
                  <div class="min-w-0 flex-1 space-y-1">
                    <MathText :text="item.content" />
                    <div class="flex flex-wrap items-center gap-1.5 text-xs">
                      <span
                        v-if="item.type_path.length"
                        :class="cn('rounded border px-1.5 py-0.5', domainClasses(types, item.type_id).border, domainClasses(types, item.type_id).text)"
                      >{{ typeLabel(item.type_path) }}</span>
                      <span v-if="item.type_hint" class="italic text-muted-foreground">{{ item.type_hint }}</span>
                      <span v-if="item.depends_on.length" class="text-muted-foreground">
                        {{ t('structure.dependsOn', { items: item.depends_on.map(id => elementNumber.get(id)).filter(Boolean).join(t('structure.panel.listSeparator')) }) }}
                      </span>
                      <button
                        v-if="composable"
                        type="button"
                        :class="cn('ml-auto text-muted-foreground hover:text-primary', basket.has('ask', item.id) && 'text-primary')"
                        :title="t('structure.compose.add')"
                        @click="addToBasket('ask', item.id, item.content)"
                      ><PackagePlus class="h-3.5 w-3.5" /></button>
                    </div>
                    <div v-if="paramsByOwner.get(`a:${item.id}`)?.length" class="flex flex-wrap gap-1.5 text-xs">
                      <span
                        v-for="param in paramsByOwner.get(`a:${item.id}`)"
                        :key="param.id"
                        class="inline-flex items-center gap-1 rounded border border-dashed border-primary/40 px-1.5 py-0.5"
                        :title="formatParamDomain(param.domain)"
                      >
                        <Variable class="h-3 w-3 text-primary" />{{ param.name }} = <MathText :text="paramText(param.value, param.span)" />
                      </span>
                    </div>
                    <p
                      v-for="(issue, i) in itemIssues('ask', index)"
                      :key="i"
                      :class="cn('text-xs', issue.severity === 'error' ? 'text-destructive' : 'text-amber-700 dark:text-amber-300')"
                    >{{ issueText(issue) }}</p>
                  </div>
                </div>
              </li>
              <li v-if="!run.asks.length" class="text-sm text-muted-foreground">{{ t('structure.panel.noAsks') }}</li>
            </ol>
          </section>

          <section v-if="run.groups?.length">
            <h4 class="mb-2 text-sm font-medium">{{ t('structure.groups.title') }} <span class="text-muted-foreground">({{ run.groups.length }})</span></h4>
            <ul class="space-y-1.5">
              <li v-for="group in run.groups" :key="group.id" class="flex flex-wrap items-center gap-2 rounded-md border border-dashed px-3 py-2 text-sm">
                <Boxes class="h-4 w-4 text-muted-foreground" />
                <span class="font-medium">{{ group.name }}</span>
                <span class="text-xs text-muted-foreground">
                  {{ t('structure.groups.members', { items: group.element_ids.map(id => elementNumber.get(id)).filter(Boolean).join(t('structure.panel.listSeparator')) }) }}
                </span>
                <div class="ml-auto flex gap-1">
                  <Button
                    v-if="composable && writable && group.replaceable"
                    size="sm" variant="ghost" class="h-7 px-2 text-xs"
                    :disabled="!group.type_ids.length"
                    :title="group.type_ids.length ? '' : t('structure.groups.needTypes')"
                    @click="openReplace(group)"
                  >{{ t('structure.groups.replace') }}</Button>
                  <Button
                    v-if="composable"
                    size="sm" variant="ghost" class="h-7 px-2 text-xs"
                    @click="addToBasket('group', group.id, groupMembers(group).join(t('structure.panel.mergeSeparator')))"
                  ><PackagePlus class="mr-1 h-3.5 w-3.5" />{{ t('structure.compose.add') }}</Button>
                </div>
              </li>
            </ul>
          </section>

          <KnowledgeSuggestions
            v-if="currentType === 'question' && view.accepted"
            :question-id="currentId"
            :editable="writable"
            @changed="emit('changed')"
          />

          <!-- 同结构题 -->
          <section v-if="currentType === 'question' && view.accepted" class="border-t pt-3">
            <button type="button" class="flex items-center gap-1 text-sm font-medium" @click="toggleSimilar">
              <ChevronDown v-if="similarOpen" class="h-4 w-4" /><ChevronRight v-else class="h-4 w-4" />
              {{ t('structure.panel.similar') }}
            </button>
            <div v-if="similarOpen" class="mt-2 space-y-1.5">
              <div class="flex gap-1">
                <Button
                  v-for="mode in similarModes"
                  :key="mode.value"
                  size="sm"
                  :variant="similarMode === mode.value ? 'secondary' : 'ghost'"
                  class="h-7 px-2 text-xs"
                  :title="mode.hint"
                  @click="setSimilarMode(mode.value)"
                >{{ mode.label }}</Button>
              </div>
              <div v-if="similarLoading" class="text-sm text-muted-foreground">{{ t('common.loading') }}</div>
              <p v-else-if="!similarItems?.length" class="text-sm text-muted-foreground">{{ t('structure.panel.noSimilar') }}</p>
              <NuxtLink
                v-for="item in similarLoading ? [] : similarItems ?? []"
                :key="item.question_id"
                :to="`/questions?id=${item.question_id}`"
                class="block rounded-md border px-3 py-2 text-sm hover:bg-accent"
              >
                <div class="flex items-start gap-2">
                  <span class="shrink-0 text-xs text-muted-foreground">#{{ item.question_id }}</span>
                  <MathText class="min-w-0 flex-1 line-clamp-2" :text="item.preview" />
                  <Badge variant="secondary" class="shrink-0 font-normal">{{ Math.round(item.score * 100) }}%</Badge>
                </div>
                <p v-if="item.shared_params?.length" class="mt-1 text-xs text-muted-foreground">
                  {{ t('structure.panel.sharedParams', { names: item.shared_params.join(t('structure.panel.listSeparator')) }) }}
                </p>
                <ul v-if="item.shared_elements?.length" class="mt-1.5 space-y-0.5 border-t pt-1.5 text-xs text-muted-foreground">
                  <li v-for="(content, i) in item.shared_elements" :key="i" class="flex gap-1">
                    <span class="shrink-0">=</span><MathText class="min-w-0" :text="content" />
                  </li>
                </ul>
              </NuxtLink>
            </div>
          </section>
        </template>

        <!-- 编辑模式 -->
        <template v-else>
          <section v-for="kind in (['element', 'ask'] as const)" :key="kind">
            <div class="mb-2 flex items-center justify-between">
              <h4 class="text-sm font-medium">{{ kind === 'element' ? t('structure.conditions') : t('structure.asks') }}</h4>
              <Button size="sm" variant="ghost" class="h-7" @click="addEmpty(kind)">+ {{ t('structure.panel.addItem') }}</Button>
            </div>
            <ol class="space-y-2">
              <li
                v-for="(item, index) in (kind === 'element' ? editElements : editAsks)"
                :key="item.uid"
                :class="cn('space-y-2 rounded-md border px-3 py-2', hoveredKey === `${kind === 'element' ? 'e' : 'a'}:${item.uid}` && 'border-primary')"
                @mouseenter="hoveredKey = `${kind === 'element' ? 'e' : 'a'}:${item.uid}`"
                @mouseleave="hoveredKey = null"
              >
                <div class="flex items-start gap-2">
                  <span class="mt-2 w-6 shrink-0 text-xs text-muted-foreground">{{ kind === 'element' ? index + 1 : `Q${index + 1}` }}</span>
                  <div class="min-w-0 flex-1 space-y-2">
                    <Textarea v-model="item.content" rows="2" class="min-h-[2.5rem] text-sm" :placeholder="t('structure.panel.contentPlaceholder')" />
                    <p v-if="item.content.includes('$')" class="text-xs text-muted-foreground"><MathText :text="item.content" /></p>
                    <p v-if="item.ref_element_id" class="text-xs text-primary">{{ t('structure.shared') }}</p>
                    <div class="flex flex-wrap items-center gap-2">
                      <div class="w-56">
                        <StructTypeSelect
                          v-model="item.type_id"
                          :types="types"
                          :kind="kind === 'element' ? 'condition' : 'ask'"
                          trigger-class="h-8"
                        />
                      </div>
                      <NativeSelect v-if="kind === 'element'" v-model="item.facet" class="h-8 w-28 text-xs">
                        <NativeSelectOption v-for="option in facetOptions" :key="option.value" :value="option.value || null">
                          {{ option.label }}
                        </NativeSelectOption>
                      </NativeSelect>
                      <span v-if="!item.type_id && item.type_hint" class="text-xs italic text-muted-foreground">{{ item.type_hint }}</span>
                    </div>
                    <!-- 设问依赖的条件 -->
                    <div v-if="kind === 'ask' && editElements.length" class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                      <span class="text-muted-foreground">{{ t('structure.panel.depends') }}</span>
                      <label v-for="(condition, ci) in editElements" :key="condition.uid" class="flex items-center gap-1">
                        <Checkbox
                          :model-value="item.depends.includes(condition.uid)"
                          @update:model-value="(value) => toggleDepend(item, condition.uid, value)"
                        />
                        {{ ci + 1 }}
                      </label>
                    </div>
                    <!-- 参数槽 -->
                    <StructParamEditor
                      v-for="param in paramsOf(kind, item.uid)"
                      :key="param.uid"
                      :param="param"
                      :is-math="spanInMath(stemText, param.span)"
                      @remove="removeParam(param.uid)"
                    />
                    <div v-if="item.span" class="flex flex-wrap items-center gap-2 text-xs">
                      <Button
                        size="sm" variant="ghost" class="h-7 px-2 text-xs"
                        @click="openParamDraft(`${kind}:${item.uid}`)"
                      ><Variable class="mr-1 h-3.5 w-3.5" />{{ t('structure.params.add') }}</Button>
                      <template v-if="paramDraftKey === `${kind}:${item.uid}`">
                        <Input
                          v-model="paramDraftValue"
                          class="h-7 w-32 font-mono text-xs"
                          :placeholder="t('structure.params.valuePlaceholder')"
                          @keydown.enter.prevent="submitParamDraft(kind, item)"
                        />
                        <Button size="sm" class="h-7 px-2 text-xs" @click="submitParamDraft(kind, item)">{{ t('common.confirm') }}</Button>
                      </template>
                    </div>
                  </div>
                  <div class="flex shrink-0 flex-col gap-0.5">
                    <Button size="icon" variant="ghost" class="h-6 w-6" :title="t('structure.panel.moveUp')" @click="move(kind === 'element' ? editElements : editAsks, index, -1)"><ArrowUp class="h-3.5 w-3.5" /></Button>
                    <Button size="icon" variant="ghost" class="h-6 w-6" :title="t('structure.panel.moveDown')" @click="move(kind === 'element' ? editElements : editAsks, index, 1)"><ArrowDown class="h-3.5 w-3.5" /></Button>
                    <Button size="icon" variant="ghost" class="h-6 w-6" :title="t('structure.panel.split')" @click="splitItem(kind === 'element' ? editElements : editAsks, index)"><Copy class="h-3.5 w-3.5" /></Button>
                    <Button
                      v-if="kind === 'element' && index < editElements.length - 1"
                      size="icon" variant="ghost" class="h-6 w-6" :title="t('structure.panel.mergeNext')"
                      @click="mergeWithNext(index)"
                    ><Combine class="h-3.5 w-3.5" /></Button>
                    <Button size="icon" variant="ghost" class="h-6 w-6 text-destructive" :title="t('common.delete')" @click="removeItem(kind === 'element' ? editElements : editAsks, index, kind)"><Trash2 class="h-3.5 w-3.5" /></Button>
                  </div>
                </div>
              </li>
              <li v-if="!(kind === 'element' ? editElements : editAsks).length" class="text-sm text-muted-foreground">
                {{ t('structure.panel.selectHint') }}
              </li>
            </ol>
          </section>
          <!-- 元素组 -->
          <section v-if="editElements.length >= 2">
            <div class="mb-2 flex items-center justify-between">
              <h4 class="text-sm font-medium">{{ t('structure.groups.title') }}</h4>
              <Button size="sm" variant="ghost" class="h-7" @click="addGroup">+ {{ t('structure.groups.add') }}</Button>
            </div>
            <ul class="space-y-2">
              <li v-for="(group, gi) in editGroups" :key="group.uid" class="space-y-2 rounded-md border border-dashed px-3 py-2">
                <div class="flex items-center gap-2">
                  <Input v-model="group.name" class="h-8 w-48 text-sm" :placeholder="t('structure.groups.namePlaceholder')" />
                  <label class="flex items-center gap-1 text-xs">
                    <Checkbox :model-value="group.replaceable" @update:model-value="group.replaceable = $event === true" />{{ t('structure.params.replaceable') }}
                  </label>
                  <Button size="icon" variant="ghost" class="ml-auto h-7 w-7" :title="t('common.delete')" @click="editGroups.splice(gi, 1)">
                    <Trash2 class="h-3.5 w-3.5" />
                  </Button>
                </div>
                <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                  <span class="text-muted-foreground">{{ t('structure.groups.pick') }}</span>
                  <label v-for="(condition, ci) in editElements" :key="condition.uid" class="flex items-center gap-1" :title="condition.content">
                    <Checkbox
                      :model-value="group.members.includes(condition.uid)"
                      @update:model-value="(value) => toggleGroupMember(group, condition.uid, value)"
                    />{{ ci + 1 }}
                  </label>
                </div>
                <p v-if="group.members.length < 2" class="text-xs text-amber-700 dark:text-amber-300">{{ t('structure.groups.needTwo') }}</p>
              </li>
            </ul>
          </section>
        </template>
      </template>
    </template>
    <StructGroupReplaceDialog
      v-model:open="replaceOpen"
      :group="replacingGroup"
      :members="replacingGroup ? groupMembers(replacingGroup) : []"
    />
    <StructComposeDialog v-model:open="composeOpen" />
    <StructVariantDialog
      v-if="currentType === 'question'"
      v-model:open="variantOpen"
      :run="run"
      :question-id="currentId"
    />
  </div>
</template>
