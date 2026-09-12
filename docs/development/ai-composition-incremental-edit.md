# 组稿 AI 增量编辑 —— 交接文档

> 承接 [组稿 AI 化方案](./ai-composition-plan.md) 第 6 节「实施顺序」的第 5 步，
> 以及 [上一期交接文档](./ai-composition-handover.md) 第 4.1 节列的「本期明确不做」。
>
> 状态：**已实现，自动化测试全绿，未做人工/真实模型验收。**
> 测试：后端 548 passed / 1 skipped，前端 220 passed（17 个文件）。**无 DB schema 变更，不需要迁移。**

---

## 一、做了什么

一句话：**让 AI 能改一份已经存在的稿件**，而不只是从零生成一份。

上一期的 `write_composition_nodes` 是整份替换，只对新建的空稿件安全。本期补上
**按节点 id 寻址的增量原语**，外加**用户确认这一关** —— 排版是主观的，AI 改错了必须能一键退回。

原方案的场景 2「帮我在第一题后面插入一个解题思路」现在可以跑通：

```
read_composition_outline  →（歧义时 AI 反问）→ edit_composition
    → 画布切到预览态 + 顶部变更横幅 → 用户点「应用」才落库
```

### A. 两个前端工具，而不是七个

原方案列了 5 个通用原语 + 2 个语义原语。真做成 7 个工具会有两个问题：
schema 体积翻倍，以及**一次对话里的多步改动会产出多份互相叠加的 diff**，用户没法确认。

所以收敛成两个：

| 工具 | 作用 |
|---|---|
| `read_composition_outline` | 无参。读出当前在编文档的大纲：节点 id + 类型 + 关键 props + 内容摘要，**保留 module 嵌套** |
| `edit_composition(operations[])` | 一批操作 → 一份 diff → 一次确认 |

`operations` 里承载全部 6 个原语，用**扁平 object + `op` 枚举**表达联合类型
（Gemini 的 `FunctionDeclaration` 不吃 `anyOf`/`$ref`，与既有 `write_composition_nodes.nodes` 同一套写法）。
有专门的测试断言 schema 里不出现 `$ref`/`$defs`/`anyOf`/`oneOf`。

实现的 6 个原语：

```
insert_nodes(after: nodeId | 'start' | 'end', nodes[])
remove_nodes(node_ids[])
move_node(node_id, before: nodeId | null)      # v1 仅 root 层
set_node_props(node_id, props, clear[])
show_question_fields(node_id, show{})           # 语义原语，三态
add_details_module(after, scope, fields, title) # 语义原语
```

### B. ⚠️ `wrapInModule` 从方案里删掉了

原方案的通用原语列表里有 `wrapInModule(nodeIds[], moduleProps)`。**在本仓库的 AST 里它不成立。**

`question_details` 模块**不包含**它所描述的题目 —— 它的子节点是 `normalizeDocument`
按 `scope`（`all` / `before`）从 root 层 question 节点**派生**出来的 `answer_item`。
整个 AST 里没有任何「通用容器」节点可供包裹。

替代品是语义原语 `add_details_module`：插入模块，子节点交给规范化派生。
这也解释了为什么 `remove_nodes` 会**拒绝**直接删 `answer_item` —— 删了下一次规范化就长回来。

### C. 原语落在前端，Markdown 转换留在后端

AST 代数（插入/删除/移动/规范化）在 `frontend/app/lib/compositionDocument.ts` 已有一份完整实现，
后端只保留「全量替换 + 校验」这一个持久化边界。而且**只有前端手里有用户未保存的在编文档**，
以及做 diff 所需的 before/after。所以原语在前端跑。

但 `rich_text` 的正文是 Markdown，md → RichDoc 的转换器（含公式与表格）只有后端有一份。
为此给 `ToolSpec` 加了一个 **`prepare` 钩子**：

```python
prepare: Optional[Callable[[ExecutionContext, Dict], Awaitable[Dict]]] = None
```

`AgentRunner` 在**开票之前**对 client 工具的入参跑一遍 prepare，把 Markdown 转成
**已按顶层块拆分**的 RichDoc 数组（复用上一期决策 #3 的口径），顺带校验全部原语形状。
前端只做纯结构操作，拿到的节点意图是 1:1 映射的。

> **prepare 失败时不开票。** 否则请求推不出去、前端无从回传，只会白等满一轮 30s 超时。
> 失败路径改为发一对完整的 `ToolCallStarted` + `ToolCallFinished`，前端的 `action_result`
> 才找得到对应的 `action` 卡片。

### D. 确认这一关：为什么工具立刻返回

`client_channel.DEFAULT_TIMEOUT_S = 30`，`RunBudget.wall_clock_s = 180`。
**人工确认可能要几分钟，绝不能让 run 挂着等。**

所以采用 **fire-and-return**：前端在内存里应用完这批原语、算出变更清单、把画布切到 after 文档后
**立刻返回**（远小于 30s），工具结果告诉模型「已生成 N 处改动的预览，等待用户确认」。
用户点「应用 / 放弃」发生在 run 之外。

语义上与既有的 `propose_question_draft` 一致（工具先返回，卡片后确认），
没有引入 `agent_run.status = waiting_client`，没有 DB 交接，没有新的并发原语。

**代价**：AI 本轮不知道用户最终点了什么。可接受 —— 用户想让它知道，直接说一句就行。

### E. 预览就是画布本身

前端没有任何 diff 依赖，也**没有引入**。本领域的最小单位是节点，节点有稳定 UUID，
按 id 配对就能直接说出「新增 / 删除 / 移动 / 修改」；文本行 diff 反而会丢掉节点身份。

真正的预览是**把 `document` 直接换成 after 文档**（所见即所得），
变更清单只负责解释画布上发生了什么。「放弃」= 用 before 快照原样还原，是天然的单级撤销。

移动判定用 **LIS（最长保序子序列）** 求最小移动集：直接比下标会把一次交换算成两个节点都动了，
清单会吵。

### F. ⚠️ 两处 keepalive 相关的作用域修正

`app.vue` 是全局 `<NuxtPage keepalive />`，**用户导航走之后组稿页仍然 mounted**。

1. `useAiClientTools.ts` 的静态 handler map 改成**模块级动态注册表**，
   页面用 `onActivated` 注册 / `onDeactivated` 注销。若用 `onMounted`/`onUnmounted`，
   助手在别的页面依然能改这块看不见的画布。有测试挂真的 `<KeepAlive>` 去 deactivate 并断言工具失效。
2. 顺手修了 `useAiScene.useSceneWhileMounted` 的同类问题 —— 它此前用 `onMounted`/`onUnmounted`，
   导致导航离开后 scene 仍停在 `composition_editor`，模型会继续拿到这个页面的工具。
   现在 mount/activate 都 claim（幂等），deactivate/unmount 都 release。

### G. 权限

client 工具没有 capability，但落盘走的是 `PUT .../nodes` → `composition.replace_nodes`，
上一期加的 `EDIT_QUESTION` 门禁照常生效。前端在 `!can(EDIT_QUESTION, subjectId)` 时
**只注册 read 工具**，`edit_composition` 直接回「没有编辑权限」，不做无用功也不产生会 403 的预览。

### 文件清单

**新增（后端）**
| 文件 | 行数 | 作用 |
|---|---|---|
| `app/services/composition_ops.py` | 282 | 原语的服务端校验 + 归一（Markdown → RichDoc 在此） |
| `app/ai/tools/composition_edit.py` | 202 | 两个 client 工具 + schema |
| `tests/test_composition_ops.py` | 175 | 校验/归一/工具契约（18 test） |

**新增（前端）**
| 文件 | 行数 | 作用 |
|---|---|---|
| `app/lib/compositionPrimitives.ts` | 336 | `applyOperations` —— 6 个原语 |
| `app/lib/compositionOutline.ts` | 137 | 大纲投影 + 节点人话描述 |
| `app/lib/compositionDiff.ts` | 151 | `diffDocuments` —— 按 id 配对 + LIS 求移动集 |
| `app/composables/useCompositionAiTools.ts` | 121 | 页面级工具注册（activate/deactivate） |
| `app/components/composition/CompositionAiChangesBar.vue` | 54 | 变更横幅（应用 / 放弃 / 查看变更） |
| `app/lib/__tests__/compositionPrimitives.test.ts` | 370 | 23 test |
| `app/lib/__tests__/compositionDiff.test.ts` | 150 | 8 test |
| `app/composables/__tests__/useCompositionAiTools.test.ts` | 222 | 8 test |

**修改**：10 个文件，+210 / −26。
后端 `ai/{contracts,runtime}.py`、`ai/tools/__init__.py`、
`services/{composition_authoring,prompts}.py`、`tests/{test_agent_runtime,test_ai_tools}.py`；
前端 `composables/{useAiClientTools,useAiScene}.ts`、组稿编辑页。

---

## 二、部署前必读：行为变更

### ✅ 没有运行时破坏性变更

无 DB schema 变更，无迁移。新增的两个工具只在 `composition_editor` 场景暴露，
其余页面的工具集**逐字节未变**。

后续清理从 `ChatRequest` 的 OpenAPI schema 删除了从未生效的 `temperature` 字段。
Pydantic 仍按默认策略忽略额外字段，所以旧客户端继续发送它不会收到 422，但新生成的客户端不再看到该字段。

### ⚠️ 学科提示词权限已改为学科级

此前学科提示词接口仅超管可用，但没有走统一的 `deps.require`。现在成员凭
`VIEW_QUESTION` 读取，负责人凭 `MANAGE_SUBJECT` 修改或重置，超管仍有全部权限。
负责人可从侧栏进入设置页，但只会看到「提示词配置」和自己负责的学科；系统级设置仍只对超管开放。

### ⚠️ SSE 现在区分正常完成与连接中断

`action`、`client_tool`、`action_result` 都携带 `tool_call_id`，前端按调用 id 精确收尾，
连续调用同名工具不会再匹配错卡片。只有收到 SSE `done` 才算正常完成；连接提前结束时，
仍在运行的工具卡片会转为错误态并提示重试，不再永久转圈。

### ⚠️ `useAiScene` 的作用域收紧会影响另外两个页面

题库列表页与导入审阅页也用 `useSceneWhileMounted`。改动前，用户从这两个页面导航走之后
scene 仍然停在那里（keepalive 不触发 `onUnmounted`），模型继续按那个页面减面；
改动后离开即释放，回落到 `unscoped`（= 暴露全部工具）。

这是**朝着「不悄悄少给工具」的方向**修正，符合上一期决策 #2 的取向，但行为确实变了：
在首页发消息时，此前可能残留着 `question_library` 的减面，现在一律是全量。

### ⚠️ 运维约束不变：不要设 `WEB_CONCURRENCY`

两个新工具和 `open_composition` 一样挂在 `client_channel.is_enabled()` 之下，
`WEB_CONCURRENCY > 1` 时**整体不注册**，功能降级但不会挂起。

### 工具载荷

| 场景 | 工具数 | 字符数 |
|---|---|---|
| `unscoped` | 11 | 18533 |
| `question_library` | 9 | 14247 |
| `composition_editor` | 9 | 9666 |
| `import_review` | 9 | 14247 |

两个新工具给组稿页增加约 4.8k 字符。

> 既有测试 `test_scoping_actually_shrinks_the_payload` 原本断言「组稿页载荷 < 全量 50%」，
> 这个阈值是按当时的工具集标定的，**任何组稿页专属工具都会同时抬高分子分母**而让它失效。
> 已改成断言「组稿页省下的 ≥ 两个 `propose_*` 的体量」—— 那才是作用域真正的不变量，
> 且不随工具集演进漂移。

---

## 三、怎么验收

### 3.1 自动化（应当全绿）

```bash
cd backend && uv run python -m pytest tests/ -q    # 期望 548 passed, 1 skipped
cd frontend && pnpm test                            # 期望 220 passed（17 files）
```

> 注：用 `uv run python -m pytest`，直接 `uv run pytest` 会 `Permission denied`。
> 前端没有可用的 `typecheck`，vitest 是唯一闸门。

单独跑关键部分：

```bash
cd backend
uv run python -m pytest tests/test_composition_ops.py -q       # 原语校验 + 工具契约
uv run python -m pytest tests/test_agent_runtime.py -q         # 含 prepare 分支
uv run python -m pytest tests/test_ai_tools.py -q              # 注册表 + 作用域
uv run python -m pytest tests/test_ai_adapters_sse.py -q       # tool_call_id SSE 契约
uv run python -m pytest tests/test_chat_session_title.py -q    # 后台标题独立 DB session
uv run python -m pytest tests/test_api_subject_prompts.py -q   # 学科提示词权限矩阵

cd ../frontend
pnpm vitest run app/lib/__tests__/compositionPrimitives.test.ts
pnpm vitest run app/composables/__tests__/useCompositionAiTools.test.ts
pnpm vitest run app/lib/__tests__/chatStream.test.ts
pnpm vitest run app/lib/__tests__/subjectPromptAccess.test.ts
```

复核工具载荷：

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

### 3.2 人工测试

准备：`just run-desktop`（或后端 `uv run fastapi dev app/main.py` + 前端 `pnpm dev`）。
需要 **learner（某学科的 editor）** 与 **viewer（同学科只读）** 两个账号，在 `/subjects` →「成员管理」里配。
先建一份含 3 道题、一个标题的稿件。

---

#### 测试 1：读大纲（对应 A）

| # | 操作 | 预期 |
|---|---|---|
| 1.1 | 在组稿编辑器里问「这份稿件现在什么结构？」 | 调用 `read_composition_outline`，复述出标题、题号、每道题的摘要 |
| 1.2 | 稿件里加一个参考答案模块再问一次 | 模块下的 `answer_item` 以缩进 `└` 呈现，**不是**拍平的一维列表 |
| 1.3 | 检查工具返回内容 | 只有题干摘要（≤60 字），**没有**完整的冻结快照 JSON |
| 1.4 | 在画布里改点东西**但不等自动保存**，立刻问结构 | 大纲反映的是**未保存的**当前内容 |

> **1.4 是这个工具走 client 而非 server 的全部理由**：读写必须同源，否则模型拿到的
> node id 和实际编辑目标会对不上。

---

#### 测试 2：杀手场景 —— 场景 2 的歧义（对应 A/D）

对着一份有题的稿件说：

> 帮我在第一题后面加一个解题思路

| # | 观察点 | 预期 |
|---|---|---|
| 2.1 | AI 的第一反应 | **反问**：是显示题目已有的思路字段，还是现写一段文字？ |
| 2.2 | 回答「显示已有的」 | 调 `edit_composition` 的 `show_question_fields`，第一题下方出现思路 |
| 2.3 | 页面顶部 | 出现紫色横幅「助手改动了 1 处，尚未保存」+ 摘要 |
| 2.4 | 点「查看变更」 | 展开一条：`修改 第 1 题「…」：思路显示` |
| 2.5 | **等 5 秒不动**，看 Network 面板 | **没有** `PUT .../compositions/*/nodes` 请求 |
| 2.6 | 点「放弃」 | 画布还原，横幅消失，思路不再显示 |
| 2.7 | 重来一次，改回答「你写一段」 | 走 `insert_nodes` 的 `rich_text`，第一题后多一段 AI 写的文字 |
| 2.8 | 点「应用」，等 2 秒后刷新页面 | 改动还在（自动保存接管了） |

> **2.5 是本期最关键的一条回归**。页面有 1400ms 去抖的 `autosaveNodes`，
> pending 期间若不挂起，「确认」就是形同虚设的装饰。

---

#### 测试 3：其余原语（对应 A/B）

| # | 操作 | 预期 |
|---|---|---|
| 3.1 | 「把所有解答题的分值改成 12 分」 | 一次 `edit_composition` 多条 `set_node_props`，变更清单列出 N 条 |
| 3.2 | 「在末尾加一个参考答案模块」 | `add_details_module`；标题「参考答案」是模块**前面的同级块**，模块内 `answer_item` 自动齐全 |
| 3.3 | 「把第三题移到第一题前面」 | `move_node`；变更清单**只有一条** moved，不是三条 |
| 3.4 | 「删掉第二题」 | 题目消失，参考答案模块里对应的那条 `answer_item` 也一并消失 |
| 3.5 | 「把参考答案模块里的第一条答案删掉」 | 报错「派生节点，不能单独删除」，并建议删题目或整个模块 |
| 3.6 | 「在开头加一段前言，里面写个公式 $x^2+1$」 | 公式正确渲染成公式，不是纯文本 |
| 3.7 | 「插入一道 id 是 999999 的题」（不存在的 id） | 单条操作失败并回报原因，**不崩、不建空节点** |
| 3.8 | 让 AI 用一个编造的 node id 去改 | 回「找不到节点 xxx，请先用 read_composition_outline…」 |

> **3.3 验的是 LIS**：直接比下标会把一次移动算成多个节点都动了。
> **3.2 验的是 A-slim**：标题若塞进 `module.children`，画布一加载就会把它上提，稿件「自己变形」。

---

#### 测试 4：边界与权限（对应 F/G）

| # | 操作 | 预期 |
|---|---|---|
| 4.1 | 触发 `edit_composition` 后**立刻切到别的页面** | 30 秒内返回可读失败（「前端没有实现工具…」），**不挂到 nginx 超时** |
| 4.2 | 在**别的页面**让助手改稿件 | 工具没发给模型（scene 已释放）；即使它硬调，dispatch 也会硬拦 |
| 4.3 | 上一批改动还没确认，就让 AI 再改一次 | 回「上一批改动还等着用户确认…」，**不叠加出第二份 diff** |
| 4.4 | 以 **viewer** 身份进入同一份稿件，问结构 | 能读到大纲 |
| 4.5 | viewer 让 AI 改稿件 | 回「没有这个学科的组稿编辑权限」，横幅不出现 |
| 4.6 | pending 期间让另一个人改同一份稿件，然后点「应用」 | 出现 revision 冲突条；本地改动保留，由用户决定是否重载 |
| 4.7 | pending 期间点冲突条的「重新加载」 | AI 的未确认改动一并作废（`load()` 会清 pending） |

---

## 四、待做什么

### 4.1 本期明确不做

| 项 | 说明 |
|---|---|
| **画布内联 diff 高亮** | 新增绿底 / 删除幽灵态。当前是「画布直接切到 after + 变更清单」，已经能用，高亮是锦上添花 |
| **同一 run 内等待用户确认** | 需要 `agent_run.status = waiting_client` + DB 交接才能撑过几分钟的人工确认。现在做是过度设计 |
| **多级撤销栈** | 只支持「放弃这一批 AI 改动」的单级还原 |
| **module 子层的 `move_node` / 跨 module 搬运** | root 层够覆盖目前的场景 |
| **MCP** | 走的是既有的 server 工具生成路径，零额外设计 |
| **`write_composition_nodes` 改成增量** | 它的整份替换语义不变，职责边界是「新建空稿件的一次性写入」 |

### 4.2 已知取舍 / 待观察

| 项 | 现状 | 何时需要动 |
|---|---|---|
| **大纲里的 node id 是完整 UUID** | 36 字符 ≈ 15 token/节点，30 个节点约 450 token | 若上下文吃紧，可以发短别名，但别名表要跨工具调用存活，就有状态了 |
| **摘要截断 60 字** | `compositionOutline.ts` 的 `SUMMARY_LIMIT` | 跑一轮真实模型看它能不能靠摘要定位到正确的题；不够就调大 |
| **pending 期间用户手动编辑** | 「放弃」会连用户自己的编辑一起还原 | 若实际用起来常撞，可以在用户编辑时自动把 pending 转成「已接受」 |
| **AI 不知道用户点了什么** | fire-and-return 的固有代价 | 若模型频繁追问「改好了吗」，可在提示词里明说它不会收到确认结果 |
| **`option_layout` 没开放给 AI** | 枚举是 `'auto' \| 1 \| 2 \| 4`，混合类型在 JSON Schema 里表达得很丑 | 有人真的要 AI 调选项列数时再说 |

### 4.3 上一期遗留问题已清理

下面这些问题来自 [上一期文档](./ai-composition-handover.md) 第 4.2 节，已在后续维护中处理：

| 问题 | 处理 | 验证 |
|---|---|---|
| `enrichment.py` 是死代码 | 删除未导入、未注册的重复实现 | 工具注册表与全量后端测试通过 |
| 请求级 `db` 被传进 background task | `generate_session_title` 在任务内创建并关闭 `SessionLocal` | 覆盖成功、空标题和 provider 异常 |
| `ChatRequest.temperature` 是死字段 | 从请求 schema 删除；旧客户端多传仍按 Pydantic 默认策略忽略 | schema 契约测试 |
| `action_result` 按工具名匹配最后一个 action | 三类工具事件透传 `tool_call_id`，前端按 id 关联；旧载荷才按同名 running action 回退 | 覆盖同名工具乱序返回 |
| SSE `done` 事件前端没处理 | 显式记录 `done`；EOF 未见 `done` 时提示中断，并将遗留 action 标为错误 | 覆盖正常完成与提前 EOF |
| `subject_prompts.py` 无 `deps.require` | `VIEW_QUESTION` 可读，`MANAGE_SUBJECT` 可写；负责人获得裁剪后的前端入口 | viewer/editor/manager/admin/跨学科权限矩阵 |

---

## 五、关键决策记录

| # | 决策 | 理由 |
|---|---|---|
| 1 | **删掉 `wrapInModule`** | 本 AST 没有通用容器节点：`question_details` 靠 `normalizeDocument` 按 scope 派生 `answer_item`，不「包裹」任何东西。原方案这一条是凭抽象写的，落到代码上不成立。 |
| 2 | **两个工具而非七个** | 批量 op 保证「一批改动 = 一份 diff = 一次确认」，避免多份 diff 互相叠加导致用户无法确认；顺带省 schema token。 |
| 3 | **fire-and-return，不 park run** | 人工确认可能几分钟，远超 30s 票据与 180s run 预算。语义对齐既有的 `propose_question_draft`。 |
| 4 | **`prepare` 钩子 > 新增 HTTP 转换端点** | 零额外往返；AI 面向 Markdown 的接口形状不变；md→RichDoc 保持后端单一实现（原方案缺口 2 的「倾向后者」）。 |
| 5 | **prepare 失败不开票** | 开了票却推不出请求，前端无从回传，白等满 30s 超时。改为发一对完整的 started/finished，前端卡片才配得上。 |
| 6 | **投影读走 client 而非 server** | 读写必须同源。服务端读的是已保存的版本，而编辑作用在含未保存改动的在编文档上，两者错位会让 node id 对不上。代价是离开组稿页读不到 —— 与 `composition_editor` 场景门禁本就一致。 |
| 7 | **画布即预览，不做双栏 diff 视图** | 直接换 `document` 就是所见即所得，比渲染两份文档便宜得多；变更清单只承担「解释」职责。 |
| 8 | **不引 diff 库** | 按 node id 的结构化 diff 天然贴合本领域；文本行 diff 会丢掉节点身份，反而更差。 |
| 9 | **移动判定用 LIS** | 直接比下标会把一次交换算成两个节点都动了。有针对性测试（三节点、答案唯一）。 |
| 10 | **`add_details_module` 写成 heading + module 两个同级 root** | `convert.ts` 的 A-slim 在加载时本就会把 module 内的自定义块上提成同级块。直接写最终形态，免得稿件一打开就变形。`DETAIL_PRESETS.summary()` 是旧形态，没有复用。 |
| 11 | **`edit_composition` 的 `mutating = False`** | 它自身不落库，落盘走 `PUT /nodes` → `composition.replace_nodes` capability。既有测试 `test_client_tools_have_no_server_handler` 断言 client 工具不得 mutating，这个断言是对的。 |
| 12 | **`set_node_props` 用属性白名单 + 显式 `clear[]`** | 节点 id / `content` / 软指针 / `question_id` 的真值不在模型手里，开放就会让稿件和题库对不上。`clear` 是因为 JSON Schema 里没法给 `score` 表达可空。 |
| 13 | **部分成功而非整批回滚** | 单条失败逐条回报给模型让它自己补救，比让它重发一整批便宜。但 `remove_nodes` **内部**是全有全无 —— 半删一半是纯粹的意外。 |
| 14 | **顺手修 `useAiScene` 的 keepalive 作用域** | 它和本期新加的工具注册是同一类 bug，且直接影响本功能的正确性（scene 不释放 = 模型在别的页面仍拿到组稿工具）。 |

---

## 六、给 reviewer 的阅读顺序

1. `app/services/composition_ops.py` —— 原语的契约长什么样（纯函数，最好读）
2. `app/ai/tools/composition_edit.py` —— 两个工具的 schema 与作用域
3. `app/ai/runtime.py` 的 client 分支 —— `prepare` 插在哪、为什么失败时不开票
4. `frontend/app/lib/compositionPrimitives.ts` 的 `applyOperations` —— 部分成功语义
5. `frontend/app/composables/useCompositionAiTools.ts` —— 桥接与三道门禁（权限 / pending / 空改动）
6. `frontend/app/pages/compositions/[scope]/[id]/index.vue` 的 `pendingAiEdit` —— 自动保存挂起
7. `frontend/app/lib/compositionDiff.ts` 的 `movedNodeIds` —— 唯一一段非平凡算法
