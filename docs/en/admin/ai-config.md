# AI Providers & Models

AI configuration (providers, models, API keys) is **stored in the database** and managed through the UI. Changes take effect **immediately**, with no restart required.

There are two levels of configuration:

| Level | Where | Who can configure | Who can use |
|------|------|-----------|-----------|
| Global | Settings → **Global AI Models** | Super Administrator | All users |
| Personal | Settings → **My AI Models** | Any signed-in user | Only themselves |

## Adding a Provider

Click **Add Provider** and complete the three-step wizard:

1. **Choose a provider**: DeepSeek, Qwen, Zhipu GLM, Kimi, OpenAI, Google Gemini, or **Other / Custom** (any OpenAI-compatible service, self-hosted deployment, or relay). Presets fill in the API type and endpoint automatically.
2. **Enter the API key and test the connection**: the system uses the key to fetch the provider's model list. If the connection fails, it tells you why (invalid key, wrong endpoint, timeout, etc.). Some providers don't offer a model list; you can skip this and enter models manually.
3. **Select the models to use**: the **Vision** and **Embedding** tags are inferred from the model name and can be changed by clicking them. You can also add model names manually.

After you add a provider, if some features don't have a model configured yet, the system **preselects** suitable models from the new provider. These are not saved automatically — confirm them under **Currently in Use**.

On a provider card you can: enable / disable it, edit the connection details (leave the API key blank to keep it unchanged), test the connection, add models, edit a model's name and capability tags, and delete. Models currently in use show tags such as **Text Model** or **Vision Model**.

## Model Capabilities

| Tag | Meaning | Can be used as |
|------|------|-------|
| (none) | Regular text model | Text model |
| Vision | Accepts image input | Text model, vision model |
| Embedding | Embedding model; only produces vectors, cannot chat | Embedding model |

Dropdowns list only models with matching capabilities whose provider is enabled.

## Currently in Use (Global)

| Purpose | System setting key | Affects |
|------|-----------|---------|
| Text model | `AI_TEXT_MODEL_ID` | [AI Assistant](/en/features/chat), text-based import extraction, knowledge point matching |
| Vision model | `AI_VISION_MODEL_ID` | Image recognition import |
| Embedding model | `AI_EMBEDDING_MODEL_ID` | [Knowledge point RAG](/en/features/knowledge-points), similar question search |

Each entry shows a status: **Available**, **Not configured** (the feature is unavailable for now), or **Unavailable** (the provider is disabled, the model was deleted, or its capabilities don't match). After you make changes, the page shows **Unsaved changes**; click Save and they take effect immediately.

Global settings can only use models from global providers; models from personal providers cannot be set as the site-wide default.

::: warning Changing the Embedding Model
Indexes produced by different embedding models are incompatible. When you change the embedding model, the UI warns you and offers **Save and Rebuild Index**. If you choose **Save Only**, rebuild the index manually on the Knowledge Points page later.
:::

## My AI Models (Personal)

Regular users can:

- Choose their own **default text model** and **default vision model**: any global model or one of their own. Choosing **Follow Global Default** uses the administrator's setting.
- Connect **their own providers** with their own API keys; usage is billed to their own account.

Model selection order: **model specified for the call → personal default → global default**. If a personal default model is deleted or its provider is disabled, it falls back to the global default automatically.

Personal settings apply to AI conversations the user starts (the chat window's model list is grouped into **My Models** and **Global Models**, with the personal default selected), document / image import extraction, and knowledge point matching. **The embedding model always uses the global configuration**, because the vector index is shared site-wide.

Administrators can see all users' personal providers (without API keys) at the bottom of the **Global AI Models** page and delete them if necessary. When a user is deleted, their personal providers are deleted too.

## Security

- API keys are **stored encrypted** with a key derived from `SECRET_KEY`. No API ever returns the key itself, only whether it has been set.
- A personal provider's key is used only for its owner's requests; other users (including administrators) can neither see nor use it.
- If you change `SECRET_KEY`, saved keys can no longer be decrypted and must be re-entered in the UI.
