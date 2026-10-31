# 安装与首次启动

桌面版是一个 Windows 托盘应用 / macOS 菜单栏应用，内置后端、前端与 SQLite 数据库，**无需安装数据库或 Docker**，双击安装即可使用。

## 系统要求

- Windows 10 / 11（64 位）
- macOS 13 Ventura 及以上（Apple 芯片或 Intel 芯片）
- AI 功能需要可访问的 AI 供应商，如：Gemini / OpenAI / 阿里云等。

## 下载与安装

1. 打开 [GitHub Releases](https://github.com/gygy-open/question-bank/releases)，下载最新的 `QuestionBank-Setup-x.y.z.exe`。

![](../public/install/github-release-download.png)

2. 双击运行安装程序（需要管理员权限）。
3. 按向导完成安装，可选勾选：
   - **开机自启**：登录 Windows 后自动在后台启动。
   - **创建桌面快捷方式**。


## macOS 安装

1. 在 [GitHub Releases](https://github.com/gygy-open/question-bank/releases) 下载与你的电脑匹配的 DMG：
   - Apple 芯片（M1 / M2 / M3 …）：`QuestionBank-x.y.z-macos-arm64.dmg`
   - Intel 芯片：`QuestionBank-x.y.z-macos-x86_64.dmg`

   不确定时，点左上角  →「关于本机」，看「芯片」或「处理器」一栏。
2. 双击打开 DMG，把 **QuestionBank** 拖进「应用程序」文件夹。
3. 在「应用程序」中双击 **QuestionBank** 启动。

启动后，菜单栏右上角会出现题库图标，Dock 中也会显示应用图标：

- 点击 **Dock 图标**（或再次双击应用）即可打开题库界面；
- 点击**菜单栏图标**可使用「打开题库 / 局域网共享 / 登录时启动 / 重启 / 退出」菜单；
- 按 <kbd>⌘Q</kbd> 或在 Dock 图标上右键 →「退出」会同时关闭内置服务。

::: warning 提示「无法验证开发者」/「已损坏」？
未经 Apple 公证的版本首次打开时会被系统拦截。请打开「系统设置 → 隐私与安全性」，在页面下方找到 QuestionBank 的提示，点击 **「仍要打开」** 并确认，之后即可正常使用。

若仍提示「已损坏，无法打开」，在「终端」中执行下面的命令后再打开：

```bash
xattr -dr com.apple.quarantine /Applications/QuestionBank.app
```
:::

::: tip 登录时自动启动
点击菜单栏图标，勾选 **「登录时启动」**，之后每次登录 Mac 都会自动在后台运行（默认关闭）。它与「系统设置 → 通用 → 登录项」中的设置是同一项，在任一处修改都可以。如果在系统设置里关掉过，再次勾选时会自动打开该设置页，请在那里重新允许。
:::

## 首次启动

安装完成后，应用会以**托盘图标**形式常驻在任务栏右下角。

![](../public/install/tray-icon.png)

右键托盘图标可看到菜单：

| 菜单项 | 说明 |
|--------|------|
| 打开题库 | 用默认浏览器打开题库界面 |
| 局域网共享 | 勾选后开放给同网段访问（**默认关闭**），详见 [局域网共享](/desktop/lan-sharing) |
| 登录时启动 | 仅 macOS：勾选后登录 Mac 时自动运行（**默认关闭**） |
| 重启 | 重启内置服务 |
| 退出 | 关闭应用与内置服务 |

::: tip 界面语言
安装向导按 Windows 显示语言自动选择简体中文或英文，其他语言会先弹出语言选择框。托盘菜单和提示框一开始使用安装时选的语言；之后在本机网页界面里切换语言，托盘会跟着切换。同事通过局域网访问时切换语言，不影响本机托盘。
:::

首次点击「打开题库」后，会进入 **初始化向导**：

1. 选择数据库：桌面版默认使用内置 **SQLite**，无需额外配置。
2. 创建管理员账号（用户名 + 密码）。
3. 完成后即可登录使用。

::: tip 端口被占用怎么办？
桌面版默认监听 `8000`（测试版 `8001`）。如果这个端口已被电脑上别的程序占用，应用会自动改用后面一个空闲端口并弹窗告知，托盘菜单和开始菜单的「打开题库」都会打开正确的地址。开启了局域网共享时，请把新地址告知同事。

重复双击图标不会启动第二个实例——应用检测到自己已在运行时，只会把界面调出来。
:::

## 数据存在哪？

桌面版的数据统一存放在：

```
%APPDATA%\QuestionBank                          (Windows)
~/Library/Application Support/QuestionBank     (macOS)
```

Windows 在资源管理器地址栏粘贴上面的路径即可打开；macOS 在访达中按 <kbd>⇧⌘G</kbd> 粘贴路径前往。常见内容：

- `config.json` — 本地配置（含自动生成的 `SECRET_KEY`）
- SQLite 数据库文件 — 你的题库数据
- `logs\app.log` — 运行日志（排查问题时查看）

::: tip 备份很简单
关闭应用后，直接复制整个数据目录即可完成备份。详见 [个人使用 · 备份与恢复](/desktop/personal#备份与恢复)。
:::

## 下一步

- 日常使用流程 → [个人使用](/desktop/personal)
- 让同事一起用 → [局域网共享](/desktop/lan-sharing)
- 配置 AI 供应商 → [AI 供应商与模型](/admin/ai-config)
