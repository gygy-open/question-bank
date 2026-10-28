# Upgrade & Uninstall

## Upgrading to a New Version

1. Download the latest installer from [GitHub Releases](https://github.com/gygy-open/question-bank/releases).
2. Right-click the tray icon → **Quit** to close the running app.
3. Run the new installer and **install over** the existing version.

::: tip Your data is kept
An upgrade installs over the existing version: program files are replaced, but your data directory `%APPDATA%\QuestionBank` (SQLite database, uploaded files, configuration) is **not affected**. To be safe, we still recommend making a [backup](/en/desktop/personal#backup-and-restore) before upgrading.
:::

::: info First launch after upgrading
On its first launch, a new version automatically tidies up old data in the background (for example, moving images previously inserted into questions into the **Media Library**). Questions remain usable during this process, which usually takes a few seconds to a few minutes and runs only once.
:::

The installer automatically ends the running old version during an upgrade. If you see a "file in use" message, quit the app manually first and try again.

## Trying the Preview Version

The Preview version (version numbers with `-alpha` / `-beta`, e.g. `1.5.0-alpha.1`) is **fully isolated** from the stable version; you can install and run both at the same time:

| | Stable | Preview |
| --- | --- | --- |
| Program name | QuestionBank | QuestionBank Preview |
| Icon color | Teal | Amber |
| Data directory | `%APPDATA%\QuestionBank` | `%APPDATA%\QuestionBank-Preview` |
| Address | `http://localhost:8000` | `http://localhost:8001` |

On its first launch, if the Preview version finds data from the stable version, it asks whether to copy it over for testing:

- **Yes**: the Preview version uses a **copy**; the stable version's data is not modified.
- **No**: the Preview version starts fresh.

If the stable version uses a MySQL database, the data cannot be copied automatically and the Preview version starts fresh. In that case, do not connect the Preview version to the database the stable version is using.

When you no longer need the Preview version, uninstall **QuestionBank Preview** in **Settings → Apps**, then delete `%APPDATA%\QuestionBank-Preview`. The stable version is not affected.

::: tip Signing in to both
When both versions are open on the same computer, signing in to one may require you to sign in again to the other. This is expected.
:::

## Uninstalling

1. Right-click the tray icon → **Quit**.
2. In Windows **Settings → Apps** or **Control Panel → Programs and Features**, find **QuestionBank** and uninstall it.

The uninstaller will:

- End the running app process;
- Remove the program files and the startup entry;
- Remove the firewall rule added by LAN sharing.

## Is Data Kept After Uninstalling?

Uninstalling does **not** automatically delete your data directory `%APPDATA%\QuestionBank`.

- To remove everything: delete the directory manually.
- To keep / migrate it: copy the directory first, then delete it; after reinstalling, put it back to restore your data.

::: warning Deletion is permanent
Manually deleting `%APPDATA%\QuestionBank` permanently deletes all your question bank data. Make sure you have a backup before doing this.
:::
