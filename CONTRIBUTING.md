# Contributing to Question Bank

感谢你对本项目感兴趣！在提交贡献前，请阅读以下说明。

## 授权协议

本项目采用 **AGPL-3.0-or-later** 协议。提交 Pull Request 即视为你同意以相同协议授权你的贡献。

## 开发环境

- Python 3.13+ (通过 [uv](https://github.com/astral-sh/uv) 管理)
- Node.js 20+ 和 [pnpm](https://pnpm.io/)
- MySQL 8.0
- Docker & Docker Compose（可选，用于一键启动）

参考根目录 `README.md` 的「快速开始」部分完成初始化。

## 分支与提交

- 从 `main` 分支创建 feature 分支：`feat/xxx`、`fix/xxx`、`docs/xxx`
- Commit message 建议使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式，例如：
  - `feat: 增加题目批量导出接口`
  - `fix: 修复填空题答案 LaTeX 渲染错误`
  - `docs: 更新部署文档`

## 代码规范

### 后端 (Python)
- 强制类型注解（`typing.List`、`typing.Optional` 等）
- 数据库操作全部走 `AsyncSession`，使用 SQLAlchemy 2.0 语法：`select(Model).where(...)`
- 新增 CRUD 请继承 `app/crud/base.py:CRUDBase`
- 新增依赖：`uv add <package>`
- 数据库变更：`uv run alembic revision --autogenerate -m "message"`

### 前端 (Vue/TypeScript)
- 组件使用 `<script setup lang="ts">`
- 优先 `ref` 而非 `reactive`
- 表单校验用 `zod` + `vee-validate`
- 样式使用 Tailwind v4 utility class，避免 scoped CSS
- 图标统一使用 `lucide-vue-next`
- API 调用统一走 `useAPI` composable

## 提交 Pull Request

1. Fork 本仓库并创建 feature 分支
2. 提交前确保本地能正常启动前后端
3. 涉及数据库变更请附带 Alembic 迁移文件
4. 涉及 UI 变更请附截图
5. PR 描述中说明动机、方案与验证步骤

## 报告问题

在 Issues 中请尽量提供：

- 复现步骤
- 期望行为 vs 实际行为
- 环境信息（OS、Python/Node 版本、浏览器等）
- 相关日志或截图

## 安全问题

**请不要在公开 Issue 中提交安全漏洞。** 请通过邮件私下联系维护者。
