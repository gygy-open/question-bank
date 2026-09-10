import { describe, it, expect, vi, beforeEach } from 'vitest'

const navigateTo = vi.fn()
vi.stubGlobal('navigateTo', navigateTo)
vi.stubGlobal('useCookie', () => ({ value: 'token' }))

const { useAiClientTools } = await import('../useAiClientTools')

describe('useAiClientTools.open_composition', () => {
    beforeEach(() => navigateTo.mockReset())

    it('builds the URL from validated parts', async () => {
        const res = await useAiClientTools().run('open_composition', {
            composition_id: 42,
            scope: 'personal',
        })
        expect(res.ok).toBe(true)
        expect(navigateTo).toHaveBeenCalledWith('/compositions/personal/42')
    })

    it('never navigates to a model-supplied path', async () => {
        // A prompt injection in an imported document must not become an open redirect.
        const res = await useAiClientTools().run('open_composition', {
            composition_id: '../../evil',
            scope: 'personal',
        })
        expect(res.ok).toBe(false)
        expect(navigateTo).not.toHaveBeenCalled()
    })

    it('rejects an unknown scope', async () => {
        const res = await useAiClientTools().run('open_composition', {
            composition_id: 1,
            scope: 'https://evil.test',
        })
        expect(res.ok).toBe(false)
        expect(navigateTo).not.toHaveBeenCalled()
    })

    it('rejects a non-positive id', async () => {
        const res = await useAiClientTools().run('open_composition', {
            composition_id: 0,
            scope: 'shared',
        })
        expect(res.ok).toBe(false)
        expect(navigateTo).not.toHaveBeenCalled()
    })

    it('reports unknown tools instead of throwing', async () => {
        const res = await useAiClientTools().run('rm_rf', {})
        expect(res.ok).toBe(false)
        expect(res.content).toContain('rm_rf')
    })
})
