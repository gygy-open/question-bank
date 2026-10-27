# AI Assistant

The AI Assistant provides session-based, multi-model chat with image input, provider / model switching, and access to question bank tools.

## Sessions and Messages

- **Session**: each conversation is a separate session with a title and created / updated times.
- **Message**: roles include `user` / `assistant` / `system` / `tool`.
- Sessions and messages are **stored persistently**, so you can review history at any time.

## Multiple Models

- Supports OpenAI, Gemini, DeepSeek, and compatible APIs (configured in [AI Providers & Models](/en/admin/ai-config); users can connect their own providers under **Settings → My AI Models**).
- You can choose the **text model** used for chat; image input requires a **vision model**.

Active models are controlled by system settings:

- `AI_TEXT_MODEL_ID` — chat text model
- `AI_VISION_MODEL_ID` — image processing model
- `AI_EMBEDDING_MODEL_ID` — vector embedding model

## Image Input

- You can attach images to messages; the system converts them to data URIs for the model automatically (png / jpeg / webp supported).
- Requires an active **vision model**.

## Tool Calls (Question Bank Integration)

During a conversation, the AI can call question bank tools as needed:

- `search_questions` — search questions
- `create_question_draft` — create a question draft
- `create_questions_batch` — create questions in bulk

::: tip On Request Only
By default, the AI uses these tools **only when you explicitly ask**, to avoid unintended actions. This behavior is controlled by the built-in chat prompt, is updated with each release, and needs no manual configuration.
:::

## Streaming Responses

Replies are streamed (SSE) and rendered progressively in the frontend, so you can see progress immediately even for long answers.

## Session Management

- Create a session
- Session list (paginated)
- View all messages in a session
- Delete a session
