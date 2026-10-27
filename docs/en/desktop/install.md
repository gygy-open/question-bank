# Installation & First Launch

The desktop edition is a Windows tray app with a built-in backend, frontend, and SQLite database. **No database or Docker installation is needed** — just run the installer and start using it.

## System Requirements

- Windows 10 / 11 (64-bit)
- AI features require access to an AI provider, such as Gemini / OpenAI / Alibaba Cloud.

## Download and Install

1. Open [GitHub Releases](https://github.com/gygy-open/question-bank/releases) and download the latest `QuestionBank-Setup-x.y.z.exe`.

![](../../public/install/github-release-download.png)

2. Double-click the installer to run it (administrator rights required).
3. Follow the wizard to finish installing. Optional checkboxes:
   - **Launch at startup**: starts automatically in the background after you sign in to Windows.
   - **Create a desktop shortcut**.


## First Launch

Once installed, the app stays in the bottom-right corner of the taskbar as a **tray icon**.

![](../../public/install/tray-icon.png)

Right-click the tray icon to see the menu:

| Menu item | Description |
|--------|------|
| Open QuestionBank | Opens the question bank in your default browser |
| LAN sharing | When checked, opens access to devices on the same subnet (**off by default**); see [LAN Sharing](/en/desktop/lan-sharing) |
| Restart | Restarts the built-in service |
| Quit | Closes the app and the built-in service |

::: tip Interface language
The installer picks Simplified Chinese or English automatically based on the Windows display language; for any other language it first shows a language selection dialog. The tray menu and dialogs start out in the language chosen during installation; after that, when you switch the language in the web interface on this computer, the tray follows. Colleagues switching languages over the LAN do not affect this computer's tray.
:::

The first time you click **Open QuestionBank**, you enter the **setup wizard**:

1. Choose a database: the desktop edition uses the built-in **SQLite** by default, with no extra configuration.
2. Create an administrator account (username + password).
3. Once done, sign in and start using it.

::: tip What if the port is in use?
The desktop edition listens on `8000` by default (`8001` for the Preview version). If another program on your computer is already using that port, the app automatically switches to the next free port and tells you in a pop-up; **Open QuestionBank** in both the tray menu and the Start menu opens the correct address. If LAN sharing is on, give your colleagues the new address.

Double-clicking the icon again does not start a second instance — when the app detects it is already running, it just brings up the interface.
:::

## Where Is the Data Stored?

All desktop edition data is stored in:

```
%APPDATA%\QuestionBank
```

Paste the path above into the File Explorer address bar to open it. Typical contents:

- `config.json` — local configuration (including the auto-generated `SECRET_KEY`)
- SQLite database file — your question bank data
- `logs\app.log` — runtime log (check it when troubleshooting)

::: tip Backups are easy
After closing the app, simply copy the entire `%APPDATA%\QuestionBank` directory to make a backup. See [Personal Use · Backup and Restore](/en/desktop/personal#backup-and-restore).
:::

## Next Steps

- Day-to-day workflow → [Personal Use](/en/desktop/personal)
- Let colleagues use it too → [LAN Sharing](/en/desktop/lan-sharing)
- Configure AI providers → [AI Providers & Models](/en/admin/ai-config)
