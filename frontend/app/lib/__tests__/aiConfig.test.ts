import { describe, expect, it } from 'vitest'
import { flattenModels, modelsForScene, pickChatModel, sceneState, usageMap } from '@/lib/ai-config'
import type { AIProvider } from '@/types/ai-config'

const provider = (id: number, active: boolean, models: [number, string, boolean, boolean][]): AIProvider => ({
  id,
  name: `P${id}`,
  interface_type: 'openai',
  is_active: active,
  owner_id: null,
  is_personal: false,
  api_key_set: true,
  models: models.map(([mid, name, vision, embedding]) => ({
    id: mid, provider_id: id, name, is_vision_capable: vision, is_embedding_model: embedding,
  })),
})

const models = flattenModels([
  provider(1, true, [[1, 'chat', false, false], [2, 'vl', true, false], [3, 'emb', false, true]]),
  provider(2, false, [[4, 'off-chat', true, false]]),
])

describe('modelsForScene', () => {
  it('never offers embedding models for text or vision', () => {
    expect(modelsForScene(models, 'text').map(m => m.id)).toEqual([1, 2])
    expect(modelsForScene(models, 'vision').map(m => m.id)).toEqual([2])
    expect(modelsForScene(models, 'embedding').map(m => m.id)).toEqual([3])
  })

  it('hides models of disabled providers', () => {
    expect(modelsForScene(models, 'text').some(m => m.id === 4)).toBe(false)
  })
})

describe('sceneState', () => {
  it('distinguishes unset, ok and unavailable', () => {
    expect(sceneState(models, 'vision', null)).toBe('unset')
    expect(sceneState(models, 'vision', 2)).toBe('ok')
    expect(sceneState(models, 'vision', 4)).toBe('unavailable')
    expect(sceneState(models, 'text', 3)).toBe('unavailable')
  })
})

describe('usageMap', () => {
  it('collects every scene a model is used in', () => {
    expect(usageMap({ text: 2, vision: 2, embedding: null }).get(2)).toEqual(['aiModels.scenes.text.label', 'aiModels.scenes.vision.label'])
  })
})

describe('pickChatModel', () => {
  it('uses the default on first load', () => {
    expect(pickChatModel([1, 2, 3], null, 2, undefined)).toBe(2)
  })

  it('switches to a newly configured default even if another model was selected', () => {
    expect(pickChatModel([1, 2, 3], 1, 3, 1)).toBe(3)
  })

  it('keeps a manual choice while the default is unchanged', () => {
    expect(pickChatModel([1, 2, 3], 1, 3, 3)).toBe(1)
  })

  it('falls back when the current model disappears', () => {
    expect(pickChatModel([2, 3], 1, 3, 3)).toBe(3)
    expect(pickChatModel([2, 3], 1, null, null)).toBe(2)
    expect(pickChatModel([], 1, null, null)).toBeNull()
  })
})
