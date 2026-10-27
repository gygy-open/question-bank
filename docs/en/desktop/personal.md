# Personal Use

Personal use is the desktop edition's default mode: the built-in service binds only to `127.0.0.1` on this computer, so **only your computer can access it**, and data is stored in a local SQLite database. It suits personal lesson prep, entering questions, and building papers.

## Daily Workflow

1. **Start**: if you enabled launch at startup, the app runs in the background after your computer boots; otherwise, start it from the Start menu.
2. **Open the question bank**: right-click the tray icon → **Open QuestionBank**; the interface opens in your browser, then sign in.
3. **Configure AI** (first time): go to Settings and add an AI provider and models; see [AI Providers & Models](/en/admin/ai-config).
4. **Add questions**:
   - Create them manually, or
   - Use [Smart Import](/en/features/import) to upload Word / Markdown / images and let AI extract them.
5. **Manage and build papers**: filter, edit, and review in the [Question Bank](/en/features/questions), then build and export papers in **Compositions**.

## Data Storage

In personal use mode, all data stays on this computer:

```
%APPDATA%\QuestionBank
```

This includes the SQLite database, uploaded original files, configuration, and logs. There is no cloud sync — your data is entirely under your control.

## Backup and Restore {#backup-and-restore}

**Back up:**

1. Right-click the tray icon → **Quit** to make sure the app is closed.
2. Copy the entire `%APPDATA%\QuestionBank` directory to a safe location (external drive / cloud storage).

**Restore / move to a new computer:**

1. Install the desktop edition on the new computer and launch it at least once (to create the directory).
2. Quit the app.
3. Overwrite the new computer's `%APPDATA%\QuestionBank` directory with your backup.
4. Start the app again.

::: warning Note
Always back up / restore while the app is **closed**, so the SQLite database is not being written to and the files do not get corrupted.
:::

## Moving from Personal Use to Team Collaboration

If colleagues need to use it later, you have two options:

- **Temporary collaboration on the same subnet** → just turn on [LAN sharing](/en/desktop/lan-sharing); no data migration needed.
- **Formal team deployment** → migrate to the [server edition](/en/server/docker).
