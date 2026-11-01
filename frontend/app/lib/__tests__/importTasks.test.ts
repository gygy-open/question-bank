import { describe, expect, it } from 'vitest'
import { createdCount, failureMessage, groupTasks, statusLine } from '../importTasks'
import type { ImportTaskItem } from '@/composables/useImportQueue'

const task = (overrides: Partial<ImportTaskItem>): ImportTaskItem => ({
  id: 1,
  original_filename: 'a.docx',
  description: null,
  source: 'import',
  file_type: 'docx',
  status: 'pending',
  method: 'auto',
  mode: 'extract',
  auto_commit: false,
  subject_id: 1,
  progress: {},
  paused_reason: null,
  error_message: null,
  result_summary: null,
  has_result: false,
  queue_ahead: null,
  owner_id: 1,
  owner_name: null,
  created_at: '2026-11-01T00:00:00',
  updated_at: null,
  ...overrides,
})

describe('groupTasks', () => {
  it('puts imports waiting for review first and keeps list order inside a group', () => {
    const groups = groupTasks([
      task({ id: 1, status: 'completed' }),
      task({ id: 2, status: 'processing' }),
      task({ id: 3, status: 'review_ready' }),
      task({ id: 4, status: 'pending' }),
      task({ id: 5, status: 'cancelled' }),
      task({ id: 6, status: 'paused' }),
    ])
    expect(groups.map((g) => [g.group, g.tasks.map((t) => t.id)])).toEqual([
      ['review', [3]],
      ['active', [2, 4]],
      ['paused', [6]],
      ['history', [1, 5]],
    ])
  })
})

describe('statusLine', () => {
  it('describes queue position, stage, review count and pause reason', () => {
    expect(statusLine(task({ queue_ahead: 2 }))).toEqual({ key: 'imports.line.queuedAhead', params: { count: 2 } })
    expect(statusLine(task({ queue_ahead: 0 }))).toEqual({ key: 'imports.line.queued' })
    expect(statusLine(task({ status: 'processing', progress: { stage: 'matching' } }))).toEqual({ key: 'imports.stages.matching' })
    expect(statusLine(task({ status: 'processing', progress: {} }))).toEqual({ key: 'imports.stages.parsing' })
    expect(statusLine(task({ status: 'review_ready', progress: { count: 24 } }))).toEqual({ key: 'imports.line.questions', params: { count: 24 } })
    expect(statusLine(task({ status: 'paused', paused_reason: 'quota' }))).toEqual({ key: 'imports.line.paused.quota' })
  })

  it('counts saved questions from the result summary', () => {
    const summary = JSON.stringify({ created_question_ids: [1, 2, 3] })
    expect(createdCount(task({ result_summary: summary }))).toBe(3)
    expect(createdCount(task({ result_summary: 'not json' }))).toBe(0)
    expect(statusLine(task({ status: 'completed', result_summary: summary }))).toEqual({ key: 'imports.line.saved', params: { count: 3 } })
  })
})

describe('failureMessage', () => {
  it('maps known error codes and hints at tags for structured parsing', () => {
    expect(failureMessage(task({ progress: { error_code: 'ai_document' } }))).toEqual({ key: 'imports.errors.ai_document' })
    expect(failureMessage(task({ progress: { error_code: 'no_questions', method: 'structured' } })).key).toBe('imports.errors.noQuestionsStructured')
    expect(failureMessage(task({ progress: { error_code: 'something_new' } }))).toEqual({ key: 'imports.errors.generic' })
  })
})
