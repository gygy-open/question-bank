import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useAssessments, AssessmentConflictError } from '@/composables/useAssessments'

// 捕获 $api 调用参数;useNuxtApp 在测试环境用全局桩替代。
let calls: Array<{ url: string; opts: any }>
let apiImpl: (url: string, opts: any) => Promise<any>

const $api = vi.fn((url: string, opts: any) => {
  calls.push({ url, opts })
  return apiImpl(url, opts ?? {})
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

describe('AssessmentConflictError 分类', () => {
  it('识别 revision / status / batch / duplicate / other', () => {
    expect(new AssessmentConflictError('成绩版本冲突,请刷新后重试').kind).toBe('revision')
    expect(new AssessmentConflictError('评测状态已变更,请刷新后重试').kind).toBe('revision')
    expect(new AssessmentConflictError('batch_id 已用于其他录分请求').kind).toBe('batch')
    expect(new AssessmentConflictError('batch_id 已用于其他成绩导入请求').kind).toBe('batch')
    expect(new AssessmentConflictError('只有评分中的投放可以录分').kind).toBe('status')
    expect(new AssessmentConflictError('只有未开始评分的投放可以开始录分').kind).toBe('status')
    expect(new AssessmentConflictError('只有评分中的投放可以定稿').kind).toBe('status')
    expect(new AssessmentConflictError('评测已定稿,不能再修改成绩').kind).toBe('status')
    expect(new AssessmentConflictError('学号在本学科内已存在').kind).toBe('duplicate')
    expect(new AssessmentConflictError('该用户已在本学科绑定学生').kind).toBe('duplicate')
    expect(new AssessmentConflictError('班级名在本学科内已存在').kind).toBe('duplicate')
    expect(new AssessmentConflictError('nope').kind).toBe('other')
  })
})

describe('useAssessments 请求构建', () => {
  it('listStudents 省略空 query，带 keyword/page', async () => {
    const api = useAssessments()
    await api.listStudents(3)
    expect(calls[0]!.url).toBe('/subjects/3/students')
    expect(calls[0]!.opts.query).toEqual({})

    await api.listStudents(3, { keyword: '张', page: 2, pageSize: 20 })
    expect(calls[1]!.opts.query).toEqual({ keyword: '张', page: 2, page_size: 20 })
  })

  it('createStudent POST body', async () => {
    const api = useAssessments()
    await api.createStudent(3, { student_no: 'S1', name: '张三' })
    expect(calls[0]!.url).toBe('/subjects/3/students')
    expect(calls[0]!.opts.method).toBe('POST')
    expect(calls[0]!.opts.body).toEqual({ student_no: 'S1', name: '张三' })
  })

  it('listClassrooms / createClassroom', async () => {
    const api = useAssessments()
    await api.listClassrooms(3)
    expect(calls[0]!.url).toBe('/subjects/3/classrooms')
    expect(calls[0]!.opts).toBeUndefined()

    await api.createClassroom(3, { name: '一班' })
    expect(calls[1]!.opts.method).toBe('POST')
    expect(calls[1]!.opts.body).toEqual({ name: '一班' })
  })

  it('listClassroomStudents GET 成员路径', async () => {
    const api = useAssessments()
    await api.listClassroomStudents(3, 7)
    expect(calls[0]!.url).toBe('/subjects/3/classrooms/7/students')
    expect(calls[0]!.opts).toBeUndefined()
  })

  it('replaceClassroomMembers PUT body', async () => {
    const api = useAssessments()
    await api.replaceClassroomMembers(3, 7, { student_ids: [1, 2] })
    expect(calls[0]!.url).toBe('/subjects/3/classrooms/7/students')
    expect(calls[0]!.opts.method).toBe('PUT')
    expect(calls[0]!.opts.body).toEqual({ student_ids: [1, 2] })
  })

  it('listAssessments 省略空 query，带 status', async () => {
    const api = useAssessments()
    await api.listAssessments(3)
    expect(calls[0]!.url).toBe('/subjects/3/assessments')
    expect(calls[0]!.opts.query).toEqual({})

    await api.listAssessments(3, { status: 'active' })
    expect(calls[1]!.opts.query).toEqual({ status: 'active' })
  })

  it('createAssessment POST body', async () => {
    const api = useAssessments()
    await api.createAssessment(3, {
      title: '期中考',
      composition_version_id: 5,
      classroom_id: 7,
      session_name: '一班场次',
    })
    expect(calls[0]!.url).toBe('/subjects/3/assessments')
    expect(calls[0]!.opts.method).toBe('POST')
    expect(calls[0]!.opts.body).toEqual({
      title: '期中考',
      composition_version_id: 5,
      classroom_id: 7,
      session_name: '一班场次',
    })
  })

  it('getAssessment GET 详情路径', async () => {
    const api = useAssessments()
    await api.getAssessment(3, 5)
    expect(calls[0]!.url).toBe('/subjects/3/assessments/5')
    expect(calls[0]!.opts).toBeUndefined()
  })

  it('listSessions 省略空 query，带 gradingStatus/assessmentId', async () => {
    const api = useAssessments()
    await api.listSessions(3)
    expect(calls[0]!.url).toBe('/subjects/3/assessment-sessions')
    expect(calls[0]!.opts.query).toEqual({})

    await api.listSessions(3, { gradingStatus: 'in_progress', assessmentId: 5 })
    expect(calls[1]!.opts.query).toEqual({ grading_status: 'in_progress', assessment_id: 5 })
  })

  it('getSession / startGrading / finalizeGrading 路径与方法', async () => {
    const api = useAssessments()
    await api.getSession(3, 9)
    expect(calls[0]!.url).toBe('/subjects/3/assessment-sessions/9')
    expect(calls[0]!.opts).toBeUndefined()

    await api.startGrading(3, 9)
    expect(calls[1]!.url).toBe('/subjects/3/assessment-sessions/9/grading/start')
    expect(calls[1]!.opts.method).toBe('POST')

    await api.finalizeGrading(3, 9)
    expect(calls[2]!.url).toBe('/subjects/3/assessment-sessions/9/grading/finalize')
    expect(calls[2]!.opts.method).toBe('POST')
  })

  it('getGradebook GET 带分页 / getItemStatistics GET', async () => {
    const api = useAssessments()
    await api.getGradebook(3, 9)
    expect(calls[0]!.url).toBe('/subjects/3/assessment-sessions/9/gradebook')
    expect(calls[0]!.opts.query).toEqual({})

    await api.getGradebook(3, 9, { page: 2, pageSize: 25 })
    expect(calls[1]!.opts.query).toEqual({ page: 2, page_size: 25 })

    await api.getItemStatistics(3, 9)
    expect(calls[2]!.url).toBe('/subjects/3/assessment-sessions/9/item-statistics')
    expect(calls[2]!.opts).toBeUndefined()
  })

  it('appendGrades PATCH body', async () => {
    const api = useAssessments()
    const payload = { expected_revision: 1, batch_id: 'b-1', items: [{ item_id: 11, score: 10 }] }
    await api.appendGrades(3, 42, payload)
    expect(calls[0]!.url).toBe('/subjects/3/assessment-attempts/42/grades')
    expect(calls[0]!.opts.method).toBe('PATCH')
    expect(calls[0]!.opts.body).toBe(payload)
  })

  it('Excel 导出为 blob，预检与应用使用 multipart', async () => {
    const api = useAssessments()
    const file = new File(['xlsx'], 'scores.xlsx')

    await api.exportGradebook(3, 9)
    expect(calls[0]!.url).toBe('/subjects/3/assessment-sessions/9/gradebook.xlsx')
    expect(calls[0]!.opts.responseType).toBe('blob')

    await api.previewGradeImport(3, 9, file)
    expect(calls[1]!.url).toBe('/subjects/3/assessment-sessions/9/grade-imports/preview')
    expect(calls[1]!.opts.method).toBe('POST')
    expect(calls[1]!.opts.body.get('file')).toBe(file)

    await api.applyGradeImport(3, 9, file, 'batch-1')
    expect(calls[2]!.url).toBe('/subjects/3/assessment-sessions/9/grade-imports/apply')
    expect(calls[2]!.opts.body.get('file')).toBe(file)
    expect(calls[2]!.opts.body.get('batch_id')).toBe('batch-1')

    await api.applyGradeImport(3, 9, file)
    expect(calls[3]!.opts.body.get('file')).toBe(file)
    expect(calls[3]!.opts.body.get('batch_id')).toBeNull()
  })
})

describe('409 冲突映射', () => {
  it('appendGrades 版本冲突翻译为 revision', async () => {
    apiImpl = () => Promise.reject({ status: 409, data: { detail: '成绩版本冲突,请刷新后重试' } })
    const api = useAssessments()
    await expect(
      api.appendGrades(3, 42, { expected_revision: 1, items: [{ item_id: 11, score: 1 }] }),
    ).rejects.toMatchObject({ name: 'AssessmentConflictError', kind: 'revision' })
  })

  it('startGrading 状态冲突翻译为 status', async () => {
    apiImpl = () => Promise.reject({ response: { status: 409, _data: { detail: '只有未开始评分的投放可以开始录分' } } })
    const api = useAssessments()
    await expect(api.startGrading(3, 9)).rejects.toMatchObject({
      name: 'AssessmentConflictError',
      kind: 'status',
    })
  })

  it('applyGradeImport batch 冲突翻译为 batch', async () => {
    apiImpl = () => Promise.reject({ status: 409, data: { detail: 'batch_id 已用于其他成绩导入请求' } })
    const api = useAssessments()
    const file = new File(['xlsx'], 'scores.xlsx')
    await expect(api.applyGradeImport(3, 9, file, 'batch-1')).rejects.toMatchObject({
      name: 'AssessmentConflictError',
      kind: 'batch',
    })
  })

  it('非 409 错误原样抛出', async () => {
    apiImpl = () => Promise.reject({ status: 404, data: { detail: 'Assessment session not found' } })
    const api = useAssessments()
    await expect(api.getSession(3, 9)).rejects.not.toBeInstanceOf(AssessmentConflictError)
  })
})
