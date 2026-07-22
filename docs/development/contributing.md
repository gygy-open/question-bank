# 贡献指南

欢迎贡献！完整说明见仓库根目录的 [`CONTRIBUTING.md`](https://github.com/gygy-open/question-bank/blob/main/CONTRIBUTING.md)，此处为摘要。

## 授权协议

本项目采用 **AGPL-3.0-or-later**。提交 Pull Request 即视为你同意以相同协议授权你的贡献。

## 分支与提交

- 从 `main` 创建 feature 分支：`feat/xxx`、`fix/xxx`、`docs/xxx`。
- Commit message 建议使用 [Conventional Commits](https://www.conventionalcommits.org/):
  - `feat: 增加题目批量导出接口`
  - `fix: 修复填空题答案 LaTeX 渲染错误`
  - `docs: 更新部署文档`

## 代码规范

**后端（Python）**

- 强制类型注解；数据库走 `AsyncSession` + SQLAlchemy 2.0 语法。
- 新增 CRUD 继承 `app/crud/base.py:CRUDBase`。
- 新增依赖 `uv add <package>`；数据库变更附带 Alembic 迁移。

**前端（Vue/TS）**

- `<script setup lang="ts">`；优先 `ref`。
- 表单校验用 `zod` + `vee-validate`。
- Tailwind v4 utility class，避免 scoped CSS；图标用 `lucide-vue-next`。
- API 走 `useAPI`。

详见 [后端约定](/development/backend) 与 [前端约定](/development/frontend)。

## 提交 Pull Request

1. Fork 仓库并创建 feature 分支。
2. 提交前确保本地前后端能正常启动。
3. 涉及数据库变更请附带 Alembic 迁移文件。
4. 涉及 UI 变更请附截图。
5. PR 描述中说明动机、方案与验证步骤。

## 报告问题

在 Issues 中尽量提供：复现步骤、期望 vs 实际、环境信息（OS、Python/Node 版本、浏览器）、相关日志或截图。

## 安全问题

::: warning
请**不要**在公开 Issue 中提交安全漏洞，请通过邮件私下联系维护者。
:::

## 文档贡献

本文档站基于 [VitePress](https://vitepress.dev/) 构建，源码在 `docs/`。本地预览：

```bash
cd docs
pnpm install
pnpm docs:dev
```

向 `main` 分支的 `docs/**` 推送后，GitHub Actions 会自动构建并部署到 GitHub Pages。
