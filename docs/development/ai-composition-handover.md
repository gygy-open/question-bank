# 组稿 AI 化 —— 交接文档

> 承接 [组稿 AI 化方案](./ai-composition-plan.md) 第 6 节「实施顺序」的第 1-3 步，
> 外加追加的「全局助手工具作用域」与「最小 client tool 通道」。
>
> 状态：**已实现，自动化测试全绿，未做人工/真实模型验收。**
> 测试：后端 495 passed / 1 skipped，前端 170 passed。**无 DB schema 变更，不需要迁移。**

---

## 一、做了什么

一句话：**补上组稿域缺失的权限门禁**，**修好并扩展题目检索工具**，**让全局助手按页面只带相关工具**，
然后**让 AI 能端到端生成一份稿件并自动跳过去**。

原方案里的场景 1「做一个知识点的专题讲义，找一道例题和几道检测题」现在可以跑通：

```
search_knowledge_points → search_questions → create_composition
    → write_composition_nodes → open_composition（浏览器自动跳转）
```

### A. 组稿门禁（前置，不可跳过）

组稿域此前**只校验登录**。因为 `shared` scope 的 `owner_id` 恒为 `NULL`，
任何登录用户都能读写任意学科的共享稿件 —— 这是本次真正堵上的洞。

- 11 个 `composition.*` capability 从 `Authz.NONE` 改为 `Authz.PERMISSION` + `Permission.EDIT_QUESTION`，
  并从 `UNGATED_ALLOWLIST` 中移除（该白名单有集合相等断言，漏改会直接测试失败）。
- 8 条读路由补 `Permission.VIEW_QUESTION`。收敛到两个 helper 里，没有散落到每个端点：
  - `_require_subject_access()`（原 `_ensure_subject`）覆盖 folders / compositions / 详情 / question-revisions
  - `_scoped_composition_for_versions()` 覆盖 versions / export / events
- 复用 `EDIT_QUESTION`，**没有**新增 `EDIT_COMPOSITION` 权限（避免动 `ROLE_PERMISSIONS`、
  `/users/me/permissions` 和前端所有权限消费方）。
- `personal` 稿件同样要求学科成员身份 —— `owner_id` 只决定可见性，不决定权限。

### B. `search_questions` 修复与扩展

- **修了一个真 bug**：工具 schema 让模型传 `"选择题"/"填空题"/"解答题"`，但 DB 列是
  `Enum(QuestionType)` 存 `single_choice` 等，比对时在参数绑定期就抛 `LookupError`，
  工具只会回一句错误给模型。枚举现在从 `QuestionType` 派生，schema 与模型单一真源。
- 暴露了 CRUD 早就支持、只是没开放的 `knowledge_point_ids`（自动含下级）与 `tag_ids`。
- `keyword` 改为可选（"按知识点找题"不需要关键词），但要求三者至少给一个，避免把整个题库倒给模型。
- 注入 `subject_id`，不再跨学科召回；`limit` 钳到 1..50。

### C. 工具作用域

全局助手挂在每个页面上，但此前**无条件把全部工具 schema 发给模型，且每轮重发**。

- `ToolSpec.scenes` 声明工具在哪些页面可用；页面用 `useAiScene()` 声明自己是什么场景。
- **`dispatch` 硬拦截**，不只是"不广播" —— 模型可能从历史消息里学到工具名。
- 系统提示词追加一行页面上下文（只放 id 与标题，不放文档内容）。

实测载荷：`unscoped` 8 工具 13152 字符 → `composition_editor` 6 工具 4891 字符，**-63%**。

### D + E. Markdown 落点与组稿工具

- `composition_authoring.build_nodes()`：把 AI 的「意图节点」翻译成合法 AST。
  节点 id、`node_kind`、`slot` 全由系统生成；`question` 节点只收 `question_id`，
  内容快照由服务端从题库实时冻结。
- 正文走 Markdown 而非 tiptap JSON（公式要嵌 mathfield、表格三层嵌套，模型直接产 JSON 错误率高、
  token 也是数倍）。复用后端已有的 `question_content_converter`，**不在前端再实现一份**。
- 两个工具 `create_composition` / `write_composition_nodes`，都挂 capability，
  因此 A 阶段的门禁在 AI 通道上同样生效。

### F. 最小 client tool 通道

原方案把它列为"大"成本（缺口 3：client 通道 + 跨页面 resume）。实际做下来**小得多**，因为：

- Nuxt 是 SPA（`ssr: false`），chat 流在模块作用域且**没有 `AbortController`**
  → **路由跳转不会中断 SSE**，同一个请求里就能走完"先导航、再回报"。
- 所有部署模式都是**单 uvicorn 进程**（server 角色传的是 app 对象，`workers>1` 会直接
  `sys.exit(1)`；Docker 无 gunicorn 无 replicas；nginx 是静态单上游）。

所以**不需要** `agent_run.status = waiting_client`、不需要跨页面重连、不需要 DB 迁移，
一个内存 Future 注册表就够。等待超时 30s，远低于 nginx 的 `proxy_read_timeout 600s`，
因此也不需要 SSE keepalive 帧。

### 文件清单

**新增（后端）**
| 文件 | 作用 |
|---|---|
| `app/services/composition_authoring.py` | AI 意图节点 → AST |
| `app/ai/tools/compositions.py` | `create_composition` / `write_composition_nodes` |
| `app/ai/tools/client.py` | `open_composition`（前端执行） |
| `app/ai/client_channel.py` | 前端工具的等待/回传通道 |
| `tests/test_api_composition_permissions.py` | 门禁矩阵（38 test） |
| `tests/test_composition_authoring.py` | AST 翻译（16 test） |
| `tests/test_ai_tools_composition.py` | 组稿工具端到端（12 test） |
| `tests/test_ai_client_channel.py` | 通道语义（15 test） |

**新增（前端）**
`app/composables/useAiScene.ts`、`app/composables/useAiClientTools.ts`，各自带 `__tests__`。

**修改**：25 个文件，+650 / -82。主要是
`capabilities/{compositions,registry}.py`、`api/v1/endpoints/{compositions,chat}.py`、
`ai/{contracts,events,runtime}.py`、`ai/tools/{registry,questions,__init__}.py`、
`ai/adapters/sse.py`、`schemas/chat.py`、`services/prompts.py`、
`tests/conftest.py` + 5 个组稿测试文件的 `ctx` fixture、
前端 `useGlobalChat.ts` + 3 个页面。

---

## 二、部署前必读：行为变更

### ⚠️ 破坏性变更：非学科成员会被挡在组稿之外

**没有任何代码路径会自动授予学科成员身份。** 唯一的来源是管理员在
`/subjects` 页面点「成员管理」手动添加（`PUT /api/v1/subjects/{id}/members/{user_id}`）。
注册、建学科、首次安装向导都不会自动授权，也没有任何迁移做过回填。

**但风险比听起来小**：题目域**本来就**已经按成员身份过滤（`visible_questions_filter`
→ `accessible_subject_ids`）。也就是说，零成员关系的用户此前就已经看不到任何题目了。
这次只是把同一道门禁扩展到组稿这个新面。

**真正受影响的人群**：只用组稿、不用题库的用户 —— 他们此前靠着 `shared` 稿件
`owner_id` 恒为 NULL 的漏洞在跨学科使用。这类用户理论上存在，实际很可能没有。

**部署前请跑一次审计**（MySQL；`user` 是保留字，需反引号）：

```sql
SELECT u.id, u.username, COUNT(sm.subject_id) AS memberships
FROM `user` u
LEFT JOIN subject_members sm ON sm.user_id = u.id
WHERE u.is_superuser = 0 AND u.is_active = 1
GROUP BY u.id, u.username
HAVING memberships = 0;
```

有结果 → 这些账号部署后会在组稿页收到 403。逐个在「成员管理」里补角色即可
（`viewer` 只读、`editor` 可组稿、`manager` 还能管成员）。超管不受影响。

### ⚠️ 运维约束：不要设 `WEB_CONCURRENCY`

client tool 通道是**进程内**的。仓库现有的所有部署方式都是单进程，唯一能打破它的
是设 `WEB_CONCURRENCY > 1` —— 那会让回传落到错误的 worker，且**失败是静默的**
（生成器一直挂到 nginx 600s 超时）。

已加护栏：`client_channel.is_enabled()` 在 `WEB_CONCURRENCY > 1` 时**直接不注册前端工具**，
功能降级但不会挂起。

### ✅ 非破坏性：工具作用域是纯增量

只有**显式声明了场景的页面**才会减面。未声明场景的页面（绝大多数）行为与改动前
逐字节一致 —— 这是刻意设计的，避免悄悄少给工具。目前只有 3 个页面声明了场景：
组稿编辑器、题库列表、导入审阅。

---

## 三、怎么验收

### 3.1 自动化（应当全绿）

```bash
cd backend && uv run pytest tests/ -q          # 期望 495 passed, 1 skipped
cd frontend && pnpm test                        # 期望 170 passed
```

单独跑关键部分：

```bash
cd backend
uv run pytest tests/test_api_composition_permissions.py -q   # 门禁矩阵
uv run pytest tests/test_capability_registry.py -q           # allowlist 集合相等
uv run pytest tests/test_ai_client_channel.py tests/test_agent_runtime.py -q
uv run pytest tests/test_migrations.py -q                    # 确认确实无 schema 漂移
```

复核工具载荷是否真的减面了：

```bash
cd backend && uv run python -c "
import json
from app.ai import tools
from app.ai.contracts import AgentScene
for s in AgentScene:
    sc = tools.openai_schemas(s)
    print(f'{s.value:20s} tools={len(sc)}  chars={len(json.dumps(sc,ensure_ascii=False))}')
"
```

期望 `composition_editor` 明显小于 `unscoped`（约 4.9k vs 13.2k）。

> 注：前端没有 `typecheck` script、`vue-tsc` 未声明依赖，**vitest 是唯一可用的前端闸门**。

### 3.2 人工测试

准备：`just run-desktop`（或 `cd backend && uv run fastapi dev app/main.py` + `cd frontend && pnpm dev`）。
需要 3 个账号：**超管**、**learner（某学科的 editor）**、**outsider（无任何学科成员关系）**。
在 `/subjects` → 「成员管理」里配。

---

#### 测试 1：组稿门禁（对应 Phase A）

| # | 操作 | 预期 |
|---|---|---|
| 1.1 | outsider 登录，打开组稿列表页 | 403，看不到任何稿件/目录 |
| 1.2 | outsider 直接访问某个已知稿件的 URL | 403 |
| 1.3 | learner 登录，进入所属学科的组稿列表 | 正常，能看到 shared 稿件 |
| 1.4 | learner 新建目录 / 新建稿件 / 拖题排版 / 保存 | 全部正常 |
| 1.5 | learner 定稿一个版本、查看版本历史、导出 DOCX | 全部正常 |
| 1.6 | learner 删除稿件、去回收站恢复 | 全部正常 |
| 1.7 | 把 learner 在该学科的角色改成 `viewer`，刷新 | 能读，但新建/保存返回 403 |
| 1.8 | 超管访问任意学科的组稿 | 全部正常（超管绕过一切检查） |

> **重点回归 1.4/1.5**：这两条覆盖了改动最大的 `_scoped_composition_for_versions`。

---

#### 测试 2：工具作用域（对应 Phase C）

打开浏览器开发者工具 Network 面板，筛选 `chat/sessions/*/messages`。

| # | 操作 | 预期 |
|---|---|---|
| 2.1 | 在**题库页**打开助手，随便发一句话，看请求体 | 有 `"scene": "question_library"` |
| 2.2 | 在**组稿编辑器**里打开助手发一句话，看请求体 | `"scene": "composition_editor"`，且 `scene_context` 里有 `composition_id` / `scope` / `title` / `revision` |
| 2.3 | 在**首页/仪表盘**（未声明场景）发一句话 | 请求体里**没有** `scene` 字段 |
| 2.4 | 在题库页说"帮我把这道题存到题库"（给一道题） | 能正常走 `propose_question_draft`，出现确认卡片 |
| 2.5 | 在组稿编辑器里说同样的话 | AI **不应**调用 `propose_*`（工具没发给它），应改为用文字回应或建议去题库页 |
| 2.6 | 在首页（未声明场景）说同样的话 | 仍能正常调用 `propose_*`（未声明场景 = 全部工具） |

> **2.6 是回归保护**：如果这条挂了，说明作用域退化成了默认减面，会让大量页面丢工具。

---

#### 测试 3：杀手场景 —— 生成专题讲义（对应 Phase D/E/F）

以 **learner** 身份，在**任意页面**打开助手，说：

> 帮我做一份"二次函数"的专题讲义，从题库里找一道例题（要显示解析）和三道检测题（不显示答案），最后加一个参考答案模块

| # | 观察点 | 预期 |
|---|---|---|
| 3.1 | 助手的工具调用日志 | 依次出现 `search_knowledge_points` → `search_questions` → `create_composition` → `write_composition_nodes` → `open_composition` |
| 3.2 | 页面行为 | **自动跳转**到新建稿件的组稿编辑器 |
| 3.3 | 稿件内容 | 有标题、有 AI 写的讲义正文段落、有引用的题目、末尾有「参考答案」模块 |
| 3.4 | 题目内容 | 与题库里的原题一致（快照由服务端冻结，不是 AI 编的） |
| 3.5 | 例题 / 检测题 | 例题下方显示解析，检测题不显示 |
| 3.6 | 正文里的公式 | 若 AI 写了 `$$...$$`，应正确渲染为公式而不是纯文本 |
| 3.7 | 保存并导出 DOCX | 排版正常，公式/表格不丢 |

**边界情况：**

| # | 操作 | 预期 |
|---|---|---|
| 3.8 | 触发 `open_composition` 后**立刻关掉标签页** | 30 秒后后端 run 优雅收尾，日志有 `Client tool ticket timed out`，**不会**挂到 nginx 超时 |
| 3.9 | 以 **outsider** 身份说同样的话 | `create_composition` 返回"没有该学科的组稿权限"，AI 用文字告知用户，**不崩、不建稿** |
| 3.10 | 让 AI 引用一道**其它学科**的题 | 返回可读提示，建议改用 `search_questions` 重新找题 |
| 3.11 | 生成后不刷新，再让 AI 往同一份稿件写一次 | 应使用返回的**新 revision**；若用旧的，会收到"revision 不是最新的，请不要直接重试" |

---

#### 测试 4：`search_questions`（对应 Phase B）

| # | 操作 | 预期 |
|---|---|---|
| 4.1 | 说"搜索题库里的单选题，关于抛物线的" | 能返回结果（此前 `q_type` 一传就报错） |
| 4.2 | 说"把知识点『二次函数』下面的题都找出来" | 能按知识点检索，且**包含下级知识点**的题 |
| 4.3 | 切换到另一个学科再搜同样的词 | 不应返回上一个学科的题 |
| 4.4 | 说"搜索题目"（不给任何条件） | 返回引导语要求补充条件，而不是倒出整个题库 |

---

## 四、待做什么

### 4.1 本期明确不做（原方案第 4-5 步，下一期）

> **已完成**，见 [组稿 AI 增量编辑 —— 交接文档](./ai-composition-incremental-edit.md)。
> 一处偏差：`wrapInModule` 在本仓库的 AST 里不成立（`question_details` 不包含它描述的题目），已删除。

| 项 | 说明 |
|---|---|
| **AST 增量原语** | `insertNodes` / `removeNodes` / `moveNode` / `setNodeProps` / `wrapInModule`，在前端实现 |
| **语义原语** | `showQuestionFields` / `addDetailsModule`，复用前端 `DETAIL_PRESETS` |
| **diff 预览** | AI 提交一组原语 → 前端内存 apply + normalize → 算 before/after diff → 用户确认后才写入 |
| **投影读工具** | 把当前稿件的节点大纲（id + 类型 + 关键 props + 摘要，**保留 module 嵌套**）喂给模型 |
| **场景 2** | 「帮我在第一题后面插入一个解题思路」——依赖上面全部 |
| **MCP** | 若要开放，走的是本期已有的 server 生成路径，零额外设计 |

> 本期的 `write_composition_nodes` 是**整份替换**，只对新建的空稿件安全。
> 工具描述里已明确要求不要用它做局部修改。局部编辑必须等 AST 原语。

### 4.2 顺手发现、本期没动的既有问题

| 问题 | 位置 | 严重度 |
|---|---|---|
| `enrichment.py` 是死代码 | `backend/app/ai/tools/enrichment.py` — 无 `register()` 调用、无任何引用，是 `questions.py` 的陈旧近似副本 | 低，可单独开 PR 删 |
| 请求级 `db` 被传进 background task | `chat.py` 的 `generate_session_title` — FastAPI ≥0.106 的 yield 依赖 teardown **先于** background task 执行，那个 session 很可能已关闭 | 中，可能静默不生成标题 |
| `ChatRequest.temperature` 是死字段 | `schemas/chat.py` — 接收后从未使用 | 低 |
| `action_result` 按工具名匹配最后一个 action | `useGlobalChat.ts` — 同一工具并行调用时会错配 | 低 |
| SSE `done` 事件前端没处理 | 后端发了，前端静默忽略 | 低 |
| `subject_prompts.py` 同样无 `deps.require` | 与组稿改动前是同类缺口 | 中，建议一并补 |
| 组稿读路径的 403 会暴露存在性 | `load` 先于 `authorize`，非成员访问已存在稿件得 403 而非 404 | 低，本期有意接受，与 `deps.require` 风格一致 |

### 4.3 待观察 / 可能需要调整

- **场景粒度**：目前 4 个（`unscoped` / `question_library` / `composition_editor` / `import_review`）。
  若用户频繁在组稿页说"顺手建道题"而撞墙，可以把 `propose_*` 也放宽到 `unscoped`
  —— 但那样就拿不到减面收益，需要权衡。
- **`open_composition` 的触发时机**：目前完全由模型自己决定。如果它跳得太频繁（比如
  用户只是问问题也跳走），需要在提示词里加约束。
- **client 通道的并发**：内存注册表在单进程下没问题，但如果将来要横向扩容，
  必须换成 `agent_run.status = waiting_client` + DB 交接。届时再做，现在做是过度设计。
- **`propose_*` 的 schema 体积**：`QUESTION_SCHEMA_PROPERTIES` 因三层 children 嵌套 +
  两个工具复用，在载荷里出现 6 次，约 7.9k 字符。作用域缓解了它，但没有根治。

---

## 五、关键决策记录

实施中偏离或修正了原方案的地方，都在这里，便于 review 时对照。

| # | 决策 | 理由 |
|---|---|---|
| 1 | **不给 search 设 `status=published` 默认值** | 原方案要这么做，但 `Question.status` 模型默认是 `draft`，绝大多数题是草稿，默认 published 会让搜索几乎永远返回空。改为纯可选。 |
| 2 | **拆分 `AgentScene.ANY` 的双重语义** | 原设计让它同时表示"工具处处可见"和"请求未声明场景"，结果是未登记场景的页面会**静默丢掉** `propose_*`（全局助手挂在每个页面，只有 3 个页面登记了）。改为 `ToolSpec.scenes = None`（处处可用）+ `AgentScene.UNSCOPED`（未声明 → 暴露全部）。 |
| 3 | **`rich_text` 按顶层块拆成 N 个 `schema_version=2` 节点** | 查证：前端 `convert.ts` 的 `pmDocToEditorDocument` 在加载时本就会把多块节点拆成 N 行并**给后续块重新发 UUID**。写 sv1 多块会导致稿件一打开 node id 就变。拆分才是与画布同源的写法。 |
| 4 | **heading 不走 Markdown 转换** | `markdown_to_rich_doc` 会把 `# x` 降级成 paragraph（转换器的目标节点集刻意不含 heading）。标题改为收 `{text, level}` 后独立构造单段落 RichDoc。 |
| 5 | **空 Markdown 报错而非静默跳过** | 静默丢弃会让模型以为写成功了。 |
| 6 | **测试 fixture 给两个学科都授权** | 这样跨学科用例的 404 断言继续由 `get_scoped` 的 subject 过滤产生，而不是被 `deps.require` 抢先变成 403。72 个既有测试的**测试体零改动**。 |
| 7 | **先只改 fixture 跑一遍绿，再加门禁** | 用于区分"fixture 问题"和"门禁问题"。中间验证点：87 passed。 |
| 8 | **client 工具参数结构化，URL 由前端拼** | 文档导入链路会把外部内容喂给模型，一旦存在提示注入，能传任意路径的跳转工具就等于开放重定向。`open_composition` 只收 `composition_id` + 枚举 `scope`，有针对性测试。 |
| 9 | **暂停前先 `commit`** | SQLAlchemy 在 commit 时把连接还池。若带着未结事务等待客户端，约 15 个并发就能耗尽连接池并锁死整个 API。 |
| 10 | **`ClientToolRequested` 是独立 AgentEvent，不是 `UIDirective`** | directive 只在 `ToolCallFinished` 时发出，而前端工具必须在**开始等待之前**就把请求推出去。 |

### 实施中修复的一个真竞态

初版 `client_channel.resolve()` 先 `_PENDING.pop()` 再兑现 future。但生成器 `yield`
出事件后，要等消费者再驱动一次才会进入 `wait_for` —— **前端回传完全可能早于 `wait_for`**，
而"导航很快完成"恰恰就是这条路径。提前 pop 会让 `wait_for` 查不到票据，白等满 30 秒超时。

已改为：`resolve` 只兑现不摘除，一次性靠 `future.done()` 保证；条目统一由 `wait_for`
的 `finally` 回收。回归测试：`test_reply_arriving_before_the_wait_is_not_lost`。

---

## 六、给 reviewer 的阅读顺序

1. `app/capabilities/compositions.py` + `app/capabilities/registry.py` —— 门禁改了什么（最短）
2. `app/api/v1/endpoints/compositions.py` 的两个 helper —— 读路径门禁
3. `tests/test_api_composition_permissions.py` —— 门禁的行为契约
4. `app/ai/contracts.py` 的 `AgentScene` / `ToolSpec` —— 作用域机制的核心
5. `app/services/composition_authoring.py` —— AST 翻译（纯函数，最好读）
6. `app/ai/client_channel.py` —— 唯一的新并发原语，模块 docstring 里写了成立前提
7. `app/ai/runtime.py` 的 client 分支 —— 唯一改了控制流的地方
