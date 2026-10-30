# Installation & First Launch

The desktop edition is a Windows tray app / macOS menu-bar app with a built-in backend, frontend, and SQLite database. **No database or Docker installation is needed** — just run the installer and start using it.

## System Requirements

- Windows 10 / 11 (64-bit)
- macOS 13 Ventura or later (Apple silicon or Intel)
- AI features require access to an AI provider, such as Gemini / OpenAI / Alibaba Cloud.

## Download and Install

1. Open [GitHub Releases](https://github.com/gygy-open/question-bank/releases) and download the latest `QuestionBank-Setup-x.y.z.exe`.

![](../../public/install/github-release-download.png)

2. Double-click the installer to run it (administrator rights required).
3. Follow the wizard to finish installing. Optional checkboxes:
   - **Launch at startup**: starts automatically in the background after you sign in to Windows.
   - **Create a desktop shortcut**.


## Installing on macOS

1. From [GitHub Releases](https://github.com/gygy-open/question-bank/releases), download the DMG that matches your Mac:
   - Apple silicon (M1 / M2 / M3 …): `QuestionBank-x.y.z-macos-arm64.dmg`
   - Intel: `QuestionBank-x.y.z-macos-x86_64.dmg`

   Not sure? Click  → **About This Mac** and check the **Chip** or **Processor** line.
2. Open the DMG and drag **QuestionBank** into the **Applications** folder.
3. Double-click **QuestionBank** in Applications to start it.

Once started, the QuestionBank icon appears in the menu bar (top right) and in the Dock:

- Click the **Dock icon** (or open the app again) to open the question bank;
- Click the **menu-bar icon** for the Open QuestionBank / LAN sharing / Restart / Quit menu;
- <kbd>⌘Q</kbd> or right-clicking the Dock icon → **Quit** also stops the built-in service.

::: warning "Cannot verify the developer" / "is damaged"?
Builds that are not notarized by Apple are blocked on first launch. Open **System Settings → Privacy & Security**, find the QuestionBank message near the bottom, click **Open Anyway** and confirm. It opens normally from then on.

If it still says the app "is damaged and can't be opened", run this in Terminal and open it again:

```bash
xattr -dr com.apple.quarantine /Applications/QuestionBank.app
```
:::

::: tip Start at login
The macOS version has no installer-time "launch at startup" option yet. To run it automatically after you sign in, add QuestionBank under **System Settings → General → Login Items**.
:::

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
%APPDATA%\QuestionBank                          (Windows)
~/Library/Application Support/QuestionBank     (macOS)
```

On Windows, paste the path into the File Explorer address bar; on macOS, press <kbd>⇧⌘G</kbd> in Finder and paste it. Typical contents:

- `config.json` — local configuration (including the auto-generated `SECRET_KEY`)
- SQLite database file — your question bank data
- `logs\app.log` — runtime log (check it when troubleshooting)

::: tip Backups are easy
After closing the app, simply copy the entire data directory to make a backup. See [Personal Use · Backup and Restore](/en/desktop/personal#backup-and-restore).
:::

## Next Steps

- Day-to-day workflow → [Personal Use](/en/desktop/personal)
- Let colleagues use it too → [LAN Sharing](/en/desktop/lan-sharing)
- Configure AI providers → [AI Providers & Models](/en/admin/ai-config)
