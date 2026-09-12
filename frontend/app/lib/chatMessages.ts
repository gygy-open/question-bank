// Stable UI identity for chat messages.
//
// Optimistic messages are pushed into the list before the backend assigns a
// numeric id; that id arrives later on the `message_meta` SSE event. The UI must
// key each message by an identifier that never changes across that update —
// otherwise Vue would tear down and rebuild the streaming message, dropping its
// scroll anchoring and in-flight state. `uiId` provides that stable identity;
// the backend `id` is attached separately without disturbing it.

let counter = 0

export function nextChatMessageUiId(): string {
    counter += 1
    return `m${counter}-${Math.random().toString(36).slice(2, 8)}`
}

export interface ChatMessageMeta {
    role: string
    id: number
}

export interface HasBackendId {
    id?: number
    role: string
}

// Attach a backend id from a `message_meta` event to the matching optimistic
// message without touching its stable uiId. The assistant meta targets the last
// (streaming) message; the user meta targets the user turn just before it.
// Returns true when a message was updated.
export function applyChatMessageMeta<T extends HasBackendId>(
    messages: T[],
    meta: ChatMessageMeta,
): boolean {
    if (messages.length === 0) return false
    if (meta.role === 'user' && messages.length >= 2) {
        messages[messages.length - 2].id = meta.id
        return true
    }
    if (meta.role === 'assistant') {
        messages[messages.length - 1].id = meta.id
        return true
    }
    return false
}
