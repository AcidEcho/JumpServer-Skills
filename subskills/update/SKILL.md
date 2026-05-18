---
name: jumpserver-update
description: Reserved JumpServer update-operation subskill. Use when a user asks about future update-class operations; currently no executable update command is allowed.
---

# Update

更新类能力预留在本子 Skill。本版没有开放任何更新入口。

## Rules

- 不执行 JumpServer 业务更新。
- 不临时拼 HTTP/Python 脚本绕过正式入口。
- 后续新增更新类脚本时，放到 `subskills/update/scripts/`。
