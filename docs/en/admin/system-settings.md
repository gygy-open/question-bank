# System Settings

System settings are **dynamic business configuration** stored in the database. They can be changed at runtime through the UI and take effect immediately. This page is **for Super Administrators only**.

## Common Settings

| Key | Description |
|----|------|
| `AI_TEXT_MODEL_ID` | Active chat / text model |
| `AI_VISION_MODEL_ID` | Active vision model |
| `AI_EMBEDDING_MODEL_ID` | Active embedding model |

Each setting has a key, a value, and a description. Model settings are usually set indirectly on the [AI Providers & Models](/en/admin/ai-config) page.

## Sign-Up Settings

The **Sign-Up** tab on the settings page manages self sign-up with toggles, which map to the following settings:

| Key | Description |
|----|------|
| `USER_REGISTRATION_ENABLED` | Whether visitors can sign up themselves (when on, the sign-in page shows a sign-up link) |
| `USER_REGISTRATION_REQUIRES_APPROVAL` | Whether new accounts require administrator approval (when on, they are disabled by default and can sign in only after being enabled) |

See [Users · Self Sign-Up](/en/admin/users).

> Question extraction / solving prompts are now **configured per subject** (defaults are built into the code and used automatically when not customized). They are no longer global system settings; see [Prompt Templates](/en/admin/prompts).

## Static vs. Dynamic Configuration

| Type | Stored in | How to change | Examples |
|------|---------|---------|------|
| Static | Environment variables / `.env` | Edit, then restart | `SECRET_KEY`, `DB_URL` |
| Dynamic | Database (`system_setting`) | Hot update in the UI | Active models, system prompts |

For static configuration of the server edition, see [Configuration Reference](/en/server/configuration).
