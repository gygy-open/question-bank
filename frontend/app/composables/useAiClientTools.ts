// Tools the model can ask the browser to execute.
//
// The channel is: backend emits an SSE `client_tool` frame and parks the still-open
// stream on a ticket; we run the handler here and POST the result back, which wakes
// the generator. Because Nuxt runs as an SPA and the chat stream has no AbortController,
// a route change does NOT interrupt the stream — so "navigate, then report back"
// works inside a single request.
//
// SECURITY: handlers take structured arguments only. Never accept a raw URL or path
// from the model — imported documents are fed to it, so a prompt injection would turn
// a path-taking navigation tool into an open redirect.

interface ClientToolResult {
    ok: boolean
    content?: string
    data?: Record<string, unknown>
}

type ClientToolHandler = (args: Record<string, any>) => Promise<ClientToolResult>

const COMPOSITION_SCOPES = new Set(['shared', 'personal'])

// Keys must match PAGE_KEYS in backend/app/ai/tools/client.py exactly.
const PAGE_ROUTES: Record<string, string> = {
    question_library: '/questions',
    knowledge_points: '/knowledge-points',
    subjects: '/subjects',
    tags: '/tags',
    compositions_shared: '/compositions/shared',
    compositions_personal: '/compositions/personal',
    import_review: '/imports',
    dashboard: '/',
}

const handlers: Record<string, ClientToolHandler> = {
    async open_composition(args) {
        const id = Number(args?.composition_id)
        const scope = String(args?.scope ?? '')
        if (!Number.isInteger(id) || id <= 0) {
            return { ok: false, content: 'composition_id 不是有效的稿件 id。' }
        }
        if (!COMPOSITION_SCOPES.has(scope)) {
            return { ok: false, content: 'scope 只能是 shared 或 personal。' }
        }
        // URL is built here from validated parts; the model never supplies a path.
        await navigateTo(`/compositions/${scope}/${id}`)
        return { ok: true, content: '已在浏览器中打开该稿件。', data: { composition_id: id } }
    },

    async open_page(args) {
        const page = String(args?.page ?? '')
        const path = PAGE_ROUTES[page]
        if (!path) {
            return { ok: false, content: `未知的页面标识：${page}` }
        }
        await navigateTo(path)
        return { ok: true, content: '已在浏览器中打开该页面。', data: { page } }
    },
}

export function useAiClientTools() {
    const run = async (name: string, args: Record<string, any>): Promise<ClientToolResult> => {
        const handler = handlers[name]
        if (!handler) return { ok: false, content: `前端没有实现工具 ${name}。` }
        try {
            return await handler(args ?? {})
        } catch (e: any) {
            return { ok: false, content: `前端执行失败：${e?.message ?? e}` }
        }
    }

    /** Execute the requested tool and report the outcome back to the parked run. */
    const handleRequest = async (payload: {
        run_id: string
        ticket: string
        tool: string
        input?: Record<string, any>
    }) => {
        // Captured before navigating: a route change crosses an await, and Nuxt's
        // composable context does not survive that, so useCookie() must run wrapped
        // in this reference rather than being called fresh afterwards.
        const nuxtApp = useNuxtApp()
        const result = await run(payload.tool, payload.input ?? {})
        const token = nuxtApp.runWithContext(() => useCookie('token').value)
        try {
            await $fetch(`/api/v1/chat/runs/${payload.run_id}/client-tool-result`, {
                method: 'POST',
                headers: token ? { Authorization: `Bearer ${token}` } : undefined,
                body: { ticket: payload.ticket, ...result },
            })
        } catch (e) {
            // The run will fall back to its own timeout; nothing useful to do here.
            console.error('Failed to report client tool result', e)
        }
    }

    return { run, handleRequest }
}
