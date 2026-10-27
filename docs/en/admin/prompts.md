# Prompt Templates

Prompt templates store frequently used prompts so you can reuse them in conversations and elsewhere.

## Template Fields

| Field | Description |
|------|------|
| Title | Template name |
| Content | Prompt text |
| Ownership | Per user (each user manages their own templates) |

## Actions

- Create / edit / delete templates
- Use them in workflows such as the [AI Assistant](/en/features/chat)

## How They Differ from System Prompts

- **Prompt templates**: user-level, reusable prompt snippets.
- **Subject prompts** (question extraction `AI_EXTRACT_PROMPT` / solving `AI_SOLVE_PROMPT`): control extraction / solving behavior and are configured **per subject**. Default templates are built into the code, and subjects without customization fall back to the default automatically. You can override them per subject on the settings page, or use **Reset to Default** to remove the override.
- **Chat tool policy**: built into the system and evolves with the code; not exposed for editing.
