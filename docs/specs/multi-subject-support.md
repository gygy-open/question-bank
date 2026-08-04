# 产品规格：多学科支持与全局学科切换

**版本**: v1.0  
**日期**: 2026-08-04  
**状态**: 待评审

---

## 1. 背景与问题

### 当前痛点

1. **用户-学科关系限制**  
   - 数据模型：`User.subject_id` (nullable, 1:1 关系)
   - 约束：一个老师只能负责一个学科
   - **用户反馈**："有没有想过一个老师多学科？"

2. **重复的学科选择操作**  
   用户在多个功能模块需反复选择学科：
   - 新增题目时选学科
   - 知识点管理页有学科 Tab
   - 题目列表页有学科 Tab
   - 批量导入时默认使用用户负责的学科

3. **标签管理缺乏学科隔离**  
   - 数据模型：`Tag` 表无 `subject_id` 字段
   - 问题：所有学科共享标签池，容易混淆（如"函数"在数学和编程中含义不同）
   - 用户反馈：数学老师不希望看到英语相关的标签

4. **批量导入的学科假设**  
   当前导入逻辑假设用户只有一个学科，自动填充 `user.subject_id`，对多学科场景支持不足。

### 核心用户

- **主要**：跨学科任教老师（如小学全科老师、中学兼职老师）
- **次要**：备课组长、教研组长（需查看多个学科数据）

---

## 2. 目标

### 业务目标

- 支持一个老师管理多个学科的题目与知识点
- 减少用户在不同功能模块的重复学科选择操作
- 提升跨学科场景的批量导入体验

### 用户价值

- 多学科老师不再需要多个账号或反复切换
- 全局学科切换器让工作流更流畅（类似"当前工作区"的概念）

---

## 3. 方案：系统级学科上下文

### 3.1 核心设计原则

**学科作为全局上下文（Global Subject Context）**

- 在系统顶层（如顶栏、侧边栏）提供**全局学科选择器**
- 用户显式切换后，所有功能模块默认使用该学科
- 持久化用户最后选择的学科（localStorage + 后端会话记忆）

### 3.2 设计模式对比

| 维度 | 当前设计（功能级） | 提案设计（系统级） |
|------|-------------------|-------------------|
| **学科选择位置** | 每个功能模块独立 | 全局顶栏/侧边栏 |
| **切换频率** | 高（每次进入模块） | 低（跨模块保持） |
| **认知负担** | 用户需在每个页面确认学科 | 明确"当前工作学科" |
| **多学科支持** | 需扩展用户-学科关系 | 天然支持（切换即可） |
| **边缘场景** | 少 | 需处理"无学科"状态 |

### 3.3 利弊分析

#### 优势 ✅

1. **流程简化**  
   - 一次切换，全局生效，避免重复操作
   - 符合"工作区"心智模型（如 IDE 的项目切换）

2. **自然支持多学科**  
   - 无需修改用户-学科关系（`User.subject_id` 可废弃或转为"默认学科"）
   - 用户可在任意学科间无缝切换

3. **批量导入体验提升**  
   - 导入时读取全局学科上下文，无需二次确认
   - 支持用户快速切换学科后连续导入

4. **扩展性强**  
   - 未来可在全局上下文添加更多维度（如年级、学期）

#### 风险 ⚠️

1. **"无学科"状态处理**  
   - 新用户或系统管理员可能未设置学科
   - 需要友好的引导流程

2. **跨学科操作场景**  
   - 如"对比不同学科的题目"需要特殊交互
   - 部分管理功能（如学科管理本身）不应受全局学科限制

3. **迁移成本**  
   - 现有用户习惯需平滑过渡
   - 前端多个组件需重构（移除局部学科选择器）

---

## 4. 用户故事与验收标准

### 4.1 全局学科切换器

**用户故事**  
> 作为一名跨学科任教的老师，  
> 我希望在系统顶栏切换"当前工作学科"，  
> 以便在不同功能模块自动应用该学科，减少重复操作。

**验收标准** (Given-When-Then)

```gherkin
Given 我是已登录用户，系统有学科 A、B、C
When 我在顶栏学科选择器中选择"数学"
Then 全局学科上下文切换为"数学"
  And 题目列表默认筛选"数学"题目
  And 知识点管理默认显示"数学"知识点树
  And 新增题目表单默认选中"数学"
  And 批量导入默认关联"数学"
  And 我的选择被持久化（刷新页面后仍保持）
```

### 4.2 多学科工作流

**用户故事**  
> 作为同时教数学和物理的老师，  
> 我希望能快速在两个学科间切换，  
> 以便连续完成不同学科的备课任务。

**验收标准**

```gherkin
Given 我当前在"数学"学科上下文
When 我在顶栏切换为"物理"
Then 所有功能模块立即切换到"物理"数据
  And 不影响我在"数学"中的未保存草稿
  And 切换动作被记录到活动日志（可选）
```

### 4.3 新用户初始化

**用户故事**  
> 作为新注册用户，  
> 我希望系统引导我选择一个默认学科，  
> 以便开始使用系统功能。

**验收标准**

```gherkin
Given 我是新注册的用户，未设置任何学科
When 我首次登录系统
Then 系统显示"选择工作学科"的引导弹窗
  And 列出所有可用学科供我选择
  And 我可以选择"稍后设置"（但进入功能模块前必须选择）
When 我选择"数学"并确认
Then 全局学科上下文被初始化为"数学"
  And 我被导航到首页或题目列表
```

### 4.4 无学科场景保护

**用户故事**  
> 作为系统管理员，  
> 我希望在未设置学科时仍能访问管理功能（如用户管理、系统设置），  
> 以便完成系统初始化。

**验收标准**

```gherkin
Given 我是超级管理员，系统尚未创建任何学科
When 我登录系统
Then 全局学科选择器显示"无学科（请先创建）"
  And 我可以正常访问"学科管理"、"用户管理"、"系统设置"
  And 我无法访问"题目列表"、"知识点管理"等依赖学科的功能
  And 相关页面显示友好提示："请先创建学科"
```

### 4.5 标签管理按学科隔离

**用户故事**  
> 作为数学老师，  
> 我希望标签管理页只显示数学相关的标签，  
> 以便避免被其他学科的标签干扰，提高管理效率。

**验收标准**

```gherkin
Given 我已切换到"数学"学科
When 我进入"标签管理"页面
Then 只显示属于"数学"的标签
  And 我创建的新标签自动关联到"数学"
  And 我无法看到或编辑其他学科的标签
When 我切换到"物理"学科
Then 标签列表立即更新为"物理"的标签
  And 两个学科可以有同名标签（如都有"重点"），互不冲突
```

### 4.6 批量导入学科自动关联

**用户故事**  
> 作为老师，  
> 我希望批量导入时自动使用当前工作学科，  
> 以便快速完成导入，无需每次手动选择。

**验收标准**

```gherkin
Given 我已切换到"英语"学科
When 我进入"智能导入"页面
Then 学科选择器默认预填"英语"
  And 我仍可手动修改为其他学科（覆盖全局上下文）
When 我上传文件并完成导入
Then 所有导入的题目关联到"英语"学科
```

---

## 5. 功能范围

### In Scope ✅

1. **全局学科选择器**
   - UI 位置：**侧边栏 Header 区域**（Logo 下方，导航菜单上方）
   - 交互：展开时显示完整下拉选择器，折叠时显示首字徽章 + Popover
   - 持久化：前端 localStorage + 后端用户会话

2. **学科上下文应用范围**
   - 题目列表（默认筛选当前学科）
   - 知识点管理（默认显示当前学科树）
   - 标签管理（默认显示并管理当前学科标签）
   - 新增/编辑题目（默认选中当前学科）
   - 批量导入（默认关联当前学科）
   - 组卷（默认从当前学科选题）

3. **新用户引导**
   - 首次登录时弹窗引导选择学科
   - 支持"稍后设置"（但功能受限）

4. **边界处理**
   - 无学科状态的保护与提示
   - 学科被删除后的降级处理

### Out of Scope ❌

1. **多学科权限控制**  
   不涉及细粒度权限（如"只能查看数学，可编辑物理"）——留待后续"权限管理"需求

2. **跨学科联合分析**  
   如"对比数学和物理的题目难度分布"——留待"数据分析"需求

3. **学科维度的数据隔离**  
   题目、知识点不强制隔离（用户仍可通过搜索看到其他学科内容）——仅做默认筛选  
   **例外**：标签按学科强隔离，避免标签命名空间冲突

4. **历史数据迁移**  
   `User.subject_id` 字段保留但不再作为唯一约束，历史数据兼容

---

## 6. 依赖与约束

### 前置条件

- 系统至少存在一个学科（由管理员创建）
- 用户已登录

### 技术依赖

- 前端：需全局状态管理（如 Pinia store）存储 `currentSubjectId`
- 后端：需新增 API 保存/读取用户最后选择的学科（或复用 session）

### 非功能约束

- 学科切换响应时间 < 200ms（前端切换，数据加载异步）
- 全局学科选择器在所有页面可见（除登录/注册页）

---

## 7. 优先级（MoSCoW）

| 特性 | 优先级 | 说明 |
|------|--------|------|
| 全局学科选择器（侧边栏 Header） | **Must** | 核心交互 |
| 学科上下文应用（题目/知识点/导入） | **Must** | 核心价值 |
| 标签按学科隔离（Tag.subject_id） | **Must** | 避免标签命名冲突 |
| 前端持久化（localStorage） | **Must** | 基础体验 |
| 后端会话保存 | **Should** | 跨设备同步 |
| 新用户引导弹窗 | **Should** | 降低学习成本 |
| 无学科状态保护 | **Should** | 边界安全 |
| 历史标签数据迁移工具 | **Should** | 平滑升级 |
| 切换动画/过渡效果 | **Could** | 锦上添花 |
| 切换历史记录 | **Won't** | 暂不需要 |

---

## 8. 开放问题

1. **UI 位置确认** ✅ **已确定**  
   - 采用**侧边栏 Header 方案**（Logo 下方）
   - 理由：真正的全局组件、符合"应用级上下文"定位、侧边栏本身就是全局导航枢纽
   - 折叠处理：Icon 模式（显示首字徽章）+ Popover 弹出选择器

2. **多学科权限**  
   - 是否允许所有用户查看所有学科？
   - 还是需要"用户-学科关联表"限制可见范围？
   - **建议**：第一版不限制，第二版引入权限

3. **学科切换的范围**  
   - 是否影响"聊天助手"（是否只回答当前学科问题）？
   - **建议**：聊天助手不受限，但可标注学科上下文

4. **历史数据**  
   - 是否需要工具将现有 `User.subject_id` 迁移为"默认学科"？
   - **建议**：作为启动时的默认学科，无需强制迁移

5. **历史标签数据迁移**  
   - 现有的全局标签如何分配到各个学科？
   - **选项 A**：为每个学科复制一份现有标签（数据冗余但安全）
   - **选项 B**：让用户手动分配标签所属学科（灵活但有学习成本）
   - **选项 C**：根据标签关联的题目所属学科自动推断（智能但复杂）
   - **待定**：需结合实际数据量评估

---

## 9. 后续迭代方向

1. **多维度上下文**  
   - 扩展为"学科 + 年级 + 学期"组合
   - 用户可同时管理"高一数学"和"高二物理"

2. **学科工作区收藏**  
   - 支持"常用学科"快速切换

3. **跨学科功能**  
   - "对比视图"：并排查看两个学科数据
   - "跨学科标签"：标记跨学科通用题目

4. **标签模板与共享**  
   - 系统预设常用标签模板（如"期末""易错""重点"）
   - 支持学科间复制标签体系（快速为新学科建立标签）

---

## 10. 附录：数据模型变更建议（供架构师参考）

**注意**：以下仅为参考，不属于产品规格范畴。

### 方案 A：保留 `User.subject_id` 作为默认学科

```python
# User 模型
default_subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True)  # 改名
last_active_subject_id = Column(Integer, nullable=True)  # 新增：最后选择的学科
```

### 方案 B：新增用户-学科关联表（支持多学科权限）

```python
class UserSubject(Base):
    user_id = Column(Integer, ForeignKey("user.id"), primary_key=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), primary_key=True)
    is_default = Column(Boolean, default=False)  # 标记默认学科
```

### 方案 C：标签增加学科关联

```python
# Tag 模型
subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)  # 新增
# 修改唯一约束：允许不同学科有同名标签
__table_args__ = (
    UniqueConstraint('subject_id', 'name', name='uq_tag_subject_name'),
)
```

**说明**：标签按学科强隔离，不同学科可以创建同名标签（如数学和物理都可以有"重点"标签）。

**推荐**：第一版采用方案 A + C（用户模型简化 + 标签隔离），第二版视权限需求采用方案 B。

---

## 11. 附录：标签隔离的数据迁移方案（供 implementer 参考）

> **注意**：本项目**同时支持 SQLite（桌面零配置版）和 MySQL（Web/Docker 版）**，见 `backend/app/db/session.py`、`backend/app/core/config.py`。所有迁移必须**方言无关**，否则桌面版会崩溃。

### 11.1 核心难题：标签的"扇出"问题

当前数据关系：

```
Tag (全局)  ←──── question_tags (M:N) ────→  Question (有 subject_id)
```

一个标签（如"重点"）可能同时被数学题、物理题引用。加 `subject_id` 后必须回答：**这个标签归属哪个学科？**

| 场景 | 描述 | 处理 |
|------|------|------|
| **单学科标签** | 只被某一学科题目引用 | 直接归属 |
| **跨学科标签** | 被多个学科题目引用（如"重点"） | 拆分成各学科独立副本 |
| **孤儿标签** | 未被任何题目引用 | 归到默认学科 |

### 11.2 推荐策略：按题目学科自动拆分 + 重建关联

为每个"标签×学科"组合创建独立标签，并把题目关联重定向到对应学科的标签，用户几乎无感知，无数据丢失。

| 方案 | 数据安全 | 用户体验 | 复杂度 |
|------|:---:|:---:|:---:|
| **A. 自动拆分（推荐）** | ✅ 无丢失 | ✅ 透明 | ⚠️ 中 |
| B. 全部归默认学科 | ✅ 无丢失 | ❌ 需手动重分 | ✅ 低 |
| C. 每学科全量复制 | ✅ 无丢失 | ⚠️ 标签冗余 | ✅ 低 |

### 11.3 方言无关的迁移实现

```python
from alembic import op
import sqlalchemy as sa
from collections import defaultdict

def upgrade():
    conn = op.get_bind()

    # 1. 先加可空列（SQLite/MySQL 均支持）
    op.add_column('tags', sa.Column('subject_id', sa.Integer(), nullable=True))

    # 2. 内联 table 定义——不 import ORM 模型（迁移须时间冻结，见 11.4）
    tags = sa.table('tags',
        sa.column('id', sa.Integer), sa.column('name', sa.String),
        sa.column('category', sa.String), sa.column('color', sa.String),
        sa.column('subject_id', sa.Integer))
    qt = sa.table('question_tags',
        sa.column('question_id', sa.Integer), sa.column('tag_id', sa.Integer))
    questions = sa.table('questions',
        sa.column('id', sa.Integer), sa.column('subject_id', sa.Integer))

    # 3. 查每个标签涉及的学科（标准 SELECT，方言无关）
    rows = conn.execute(
        sa.select(qt.c.tag_id, questions.c.subject_id)
        .select_from(qt.join(questions, qt.c.question_id == questions.c.id))
        .where(questions.c.subject_id.isnot(None)).distinct()
    ).fetchall()

    tag_subjects = defaultdict(set)
    for tag_id, sid in rows:
        tag_subjects[tag_id].add(sid)

    for tag_id, sids in tag_subjects.items():
        first, *rest = list(sids)
        # 单学科 / 跨学科的第一个学科：复用原标签
        conn.execute(tags.update().where(tags.c.id == tag_id).values(subject_id=first))
        # 跨学科的其余学科：克隆并重定向
        for sid in rest:
            src = conn.execute(sa.select(tags.c.name, tags.c.category, tags.c.color)
                               .where(tags.c.id == tag_id)).fetchone()
            res = conn.execute(tags.insert().values(
                name=src.name, category=src.category, color=src.color, subject_id=sid))
            new_id = res.inserted_primary_key[0]   # ✅ 跨驱动通用，替代 lastrowid

            # 逐题重定向（避免 SQLite 不支持的多表 UPDATE JOIN）
            q_ids = [r[0] for r in conn.execute(
                sa.select(questions.c.id).where(questions.c.subject_id == sid)).fetchall()]
            if q_ids:
                conn.execute(qt.update().where(sa.and_(
                    qt.c.tag_id == tag_id, qt.c.question_id.in_(q_ids)
                )).values(tag_id=new_id))

    # 4. 孤儿标签 + NULL 学科题目 → 默认学科（首个学科）
    default_sid = conn.execute(
        sa.select(sa.column('id')).select_from(sa.table('subjects'))
        .order_by(sa.column('id')).limit(1)).scalar()
    if default_sid is not None:
        conn.execute(tags.update().where(tags.c.subject_id.is_(None))
                     .values(subject_id=default_sid))

    # 5. 收紧约束——SQLite 需 batch 模式（自动建新表→拷数据→改名）
    with op.batch_alter_table('tags') as batch:
        batch.alter_column('subject_id', nullable=False)
        batch.create_unique_constraint('uq_tag_subject_name', ['subject_id', 'name'])
```

### 11.4 双数据库兼容的三个硬性要点

1. **禁用方言专属语法**
   - ❌ `UPDATE ... JOIN`（多表更新，SQLite 不支持）→ ✅ 先 `SELECT` 出 id 再 `IN (...)` 更新
   - ❌ `.lastrowid` → ✅ `res.inserted_primary_key[0]`

2. **SQLite 的 ALTER 限制 → 用 `op.batch_alter_table`**
   SQLite 不支持 `ALTER COLUMN` / 加约束。batch 模式会自动"建新表→拷数据→改名"模拟，MySQL 上退化为普通 ALTER。这是双库迁移的标准姿势。

3. **不要在迁移里 `import` ORM 模型 → 用 `sa.table()` 内联定义**
   迁移是"时间冻结"的。若 import `Tag` 模型，未来模型字段变化会让这个历史迁移在**新用户全新安装**时崩溃。内联定义只锁定当时的列，保证迁移链永远可重放。

### 11.5 运行特性与边界

- **只运行一次**：Alembic 通过 `alembic_version` 表记录，`upgrade head` 幂等
- **全新安装安全**：空库里无标签/题目，此 data migration 为 no-op
- **空系统兜底**：`default_sid` 可能为 `None`（尚未建学科），此时应保持列可空或迁移前置检查提示先建学科
- **downgrade 不可逆**：克隆出的标签会造成全局重名，无法完美还原。**Release note 必须标注"不可逆迁移 + 强制备份"**

### 11.6 落地步骤（交给 implementer）

1. `Tag` 模型加 `subject_id`（先 nullable）+ 关系
2. `TagCreate` schema 注入当前学科上下文
3. 编写上述方言无关 data migration（`just make_migration "tag subject isolation"`）
4. 更新 `crud_tag.get_multi` / API 端点按 `subject_id` 过滤
5. 迁移单测：构造跨学科标签场景，在 SQLite **和** MySQL 两种引擎下验证拆分与关联正确
6. Release note 标注**不可逆 + 强制备份**

---

## 更新日志

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-08-04 | 初始版本 |
| v1.1 | 2026-08-04 | 补充第 11 章：标签隔离的方言无关数据迁移方案（SQLite/MySQL 双库兼容） |
| v1.2 | 2026-08-04 | 确定 UI 位置：侧边栏 Header 方案（第 5.1、8.1 节） |
