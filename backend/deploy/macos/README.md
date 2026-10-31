# macOS 桌面版打包

产物：`QuestionBank.app`（测试版为 `QuestionBank Preview.app`），封装成
`QuestionBank-<version>-macos-<arch>.dmg`。arm64 与 x86_64 分别构建（onnxruntime 等依赖没有 universal2 wheel）。最低系统版本 macOS 13（受 onnxruntime 限制）。

## 组成

| 文件 | 作用 |
| --- | --- |
| `../../run.spec` | PyInstaller 配置。macOS 分支走 onedir + `BUNDLE` 生成 `.app`，不启用 Splash（PyInstaller 在 macOS 上不支持），并写入 Info.plist（Bundle ID、版本号、本地网络权限说明等）。 |
| `package.sh` | `sign` / `smoke` / `dmg` / `notarize` / `all`：签名、冒烟测试、生成 DMG、公证。 |
| `entitlements.plist` | Developer ID 签名时 hardened runtime 所需的 entitlements。 |
| `../../app/macos_dock.py` | Dock 集成：点击 Dock 图标打开界面、⌘Q / Dock 退出时先停服务。 |
| `../../app/macos_login_item.py` | 「登录时启动」：通过 `SMAppService` 注册 / 取消登录项。 |

## 本地构建

需要 Xcode Command Line Tools、`uv`、`pnpm`。在 `backend/` 下：

```bash
just package-macos        # 构建前端 → PyInstaller → ad-hoc 签名 → 冒烟测试 → DMG
# 或分步：
just package
deploy/macos/package.sh all
```

只能在 Mac 上构建，且产物架构与本机一致（Apple 芯片出 arm64，Intel 出 x86_64）。

调试：在终端直接运行 `dist/QuestionBank.app/Contents/MacOS/question-bank`，日志输出到终端；从访达/Dock 启动时日志写到
`~/Library/Application Support/QuestionBank/logs/app.log`。

## CI（`.github/workflows/desktop-build.yml`）

`build-macos` 任务在 `macos-15`（arm64）和 `macos-15-intel`（x86_64）上并行构建，DMG 与 Windows 安装包一起进入草稿 Release。
GitHub 的 Intel macOS 构建机支持到 2027 年 8 月，之后删掉 matrix 里的 x86_64 一项即可。

### 签名与公证（可选）

未配置下列 Secrets 时，构建只做 ad-hoc 签名（fork / PR 也能正常构建），用户首次打开需要在「隐私与安全性」中点「仍要打开」。
配置后自动用 Developer ID 签名、提交 Apple 公证并 staple，用户可直接打开。

| Secret | 内容 |
| --- | --- |
| `MACOS_CERTIFICATE_P12` | 「Developer ID Application」证书（含私钥）导出的 `.p12`，经 `base64 -i cert.p12` 编码 |
| `MACOS_CERTIFICATE_PASSWORD` | 导出 `.p12` 时设置的密码 |
| `MACOS_SIGN_IDENTITY` | 证书名，如 `Developer ID Application: Your Name (TEAMID)`（`security find-identity -v -p codesigning` 可查） |
| `APPLE_API_KEY_P8` | App Store Connect API Key（`.p8`，角色 Developer 即可），经 base64 编码 |
| `APPLE_API_KEY_ID` | 该 API Key 的 Key ID |
| `APPLE_API_ISSUER_ID` | App Store Connect 的 Issuer ID |

需要一个 Apple Developer Program 账号（个人或组织）。只配置证书、不配置 API Key 时，只签名、不公证。

本地签名/公证同样可用：

```bash
MACOS_SIGN_IDENTITY="Developer ID Application: …" \
APPLE_API_KEY_PATH=~/keys/AuthKey_XXXX.p8 APPLE_API_KEY_ID=XXXX APPLE_API_ISSUER_ID=… \
deploy/macos/package.sh all
```

## 与 Windows 版的差异

- 没有安装器：拖进「应用程序」即安装，删除 `.app` 即卸载；数据目录 `~/Library/Application Support/QuestionBank[-Preview]` 不会被删除。
- 开机自启不在安装时设置，而是菜单栏菜单里的「登录时启动」开关（默认关闭，`app/macos_login_item.py`，基于 `SMAppService.mainApp`，与系统设置的登录项同步）。
- 局域网共享不需要改防火墙：macOS 会在首次监听 `0.0.0.0` / 广播 mDNS 时弹出系统授权。
- 单实例由 LaunchServices 保证；再次打开 `.app` 会触发 reopen 事件，打开已在运行的实例的界面。
