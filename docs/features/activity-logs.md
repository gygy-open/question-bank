# 操作审计

操作审计记录系统中的关键操作，便于追溯与合规。

## 记录内容

每条日志包含：

| 字段 | 说明 |
|------|------|
| `user_id` | 操作用户 |
| `action` | 动作类型（create / update / delete / login / review 等） |
| `resource_type` | 资源类型（question / knowledge_point / subject / tag / user 等） |
| `resource_id` | 资源 ID |
| `details` | 变更快照（JSON） |
| `ip_address` | 请求来源 IP |
| `created_at` | 时间戳 |

## 查看

- 分页浏览，可按用户筛选。
- 表格展示 ID、用户、动作、资源类型、资源 ID、IP、时间与详情。

## 权限

::: warning 仅超级管理员
操作审计视图仅对**超级管理员**开放（用于查看全量日志）。普通用户无法访问。
:::

## 与审核工作流的关系

题目的审核动作（`action = review`）也会写入活动日志，可结合 [审核工作流](/features/review-workflow) 追溯每题的审核历史。
