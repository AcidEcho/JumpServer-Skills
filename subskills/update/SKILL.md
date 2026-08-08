---
name: jumpserver-update
description: Reserved JumpServer update-operation subskill. Use when a user asks about future update-class operations; currently no executable update command is allowed.
---

# Update

更新类能力预留在本子 Skill。本版没有开放任何业务更新入口。

若本目录被独立注册，使用 [agents/openai.yaml](agents/openai.yaml)。独立注册不扩大权限，本版仍只负责阻塞更新请求。

## 输入 / 输出

| 项 | 内容 |
|---|---|
| 输入 | 用户提出的更新、删除、解锁、关系变更请求 |
| 输出 | 明确阻塞原因、当前不支持范围、可用的 create/query 替代入口 |

## 当前状态

| 请求 | 处理 |
|---|---|
| JumpServer 业务更新 | 阻塞 |
| 删除、解锁、追加关系、移除关系 | 阻塞 |
| 临时 HTTP/Python/SDK 绕过正式入口 | 阻塞 |
| 只读确认或对象查询 | 转到 query 子 Skill |

## 未来入口位置

后续新增更新类脚本时，放到 `subskills/update/scripts/`，并同步主 Skill、路由安全文档和测试守卫。

## 边界

- 不执行 JumpServer 业务更新。
- 不临时拼 HTTP/Python 脚本绕过正式入口。
- 不复用 create 脚本模拟更新。

## 成功标准

- 已明确说明本版无可执行更新入口。
- 已阻塞业务写入。
- 如适用，已建议使用 query 查询对象状态或 create 白名单入口。
