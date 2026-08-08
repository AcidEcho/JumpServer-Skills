# 新增子 Skill 与能力指南

本指南约束 `jumpserver-skills` 后续扩展，目标是保持 `主 Skill -> common/access/query/create/update -> 正式 CLI -> core/runtime` 的现有结构。

## 先判断扩展类型

| 需求 | 放置位置 |
|---|---|
| 现有查询意图下新增一个统计、排行或巡检 | `query` capability：handler + metadata + reference + test |
| 现有对象增加清单、详情或解析 | `jms_query.py` 与 `object-map.md` |
| 新增用户有效访问命令 | `query` 域；实现放在 `subskills/query/scripts/jms_access.py`，保持 `user-assets/user-nodes/user-asset-access` 为 Query 正式能力 |
| 新增当前身份一次性 SSH 连接命令 | `access` 域；实现放在 `subskills/access/scripts/jms_ssh_connect.py`，仅扩展 `connect-info`；Access 与 Query 只共享 Common，双方不得互相导入或加载 |
| 新增权限、审计或只读运行时命令 | 对应 query 入口；不要全部塞进 `jms_query.py` |
| 新增允许的创建命令 | `subskills/create/scripts/` + 独立 reference + 全局白名单 |
| 新增更新类命令 | 先完成安全设计和用户授权，再替换 `update` 预留边界 |
| 出现稳定且无法归入 common/access/query/create/update 的用户意图 | 才考虑新增顶级子 Skill 域 |

仅增加一个 API、字段或 capability 时，不新建子 Skill。

## 目录职责

```text
SKILL.md                              # 主路由与全局行为
agents/openai.yaml                    # 主 Skill 接入描述
references/routing-and-safety.md      # 全局路由、写白名单、安全边界
subskills/<domain>/SKILL.md           # 域内行为与边界
subskills/<domain>/agents/openai.yaml # 独立注册接入描述
subskills/<domain>/references/        # 域内细节
subskills/<domain>/scripts/           # 正式 CLI 与域内实现
tests/                                # 单元、回归和 live acceptance
```

共享认证、组织上下文、请求和脱敏逻辑只放 `subskills/common/scripts/jumpserver_common/`。不要在其他子 Skill 复制一份。

## 新增 query capability

必须同步完成：

1. 在 `subskills/query/scripts/jms_inspect_core.py` 或 `jms_audit_core.py` 增加单一职责 handler。
2. 在对应 `HANDLERS` 注册 handler。
3. 在 `subskills/query/references/metadata/capabilities.json` 增加唯一 `capability_id`、入口、参数、端点、摘要和错误策略。
4. 在 `capabilities.md` 加入正确优先级表。
5. 若能力有独立口径、阈值或字段回退，新增/更新专用 reference。
6. 在 `intent-routing.md` 增加触发词和最近邻边界。
7. 增加 handler 单元测试；必要时更新 live acceptance 参数构造。

capability metadata 中的 `entrypoint` 必须与 CLI 枚举逻辑一致：治理/巡检使用 `jms_inspect.py inspect`，调查/取证使用 `jms_audit.py audit-analyze`。

## 新增 create 命令

必须同步完成：

1. 在 `subskills/create/scripts/` 增加或扩展正式入口。
2. 默认 dry-run；只有 `--confirm` 才执行服务端写入。
3. 在 `subskills/create/references/` 写字段语义、payload、组织规则、脱敏和示例。
4. 更新 `subskills/create/references/index.md` 的命令映射。
5. 更新 `references/routing-and-safety.md` 的唯一写操作白名单。
6. 更新 create `SKILL.md` 和独立 `agents/openai.yaml` 的触发面。
7. 增加 dry-run、confirm、组织、重名/引用解析、脱敏和错误路径测试。

未进入根级白名单的命令，不得通过临时 HTTP/SDK、通用 payload 入口或复用其他 create 命令绕过。

## 新增顶级子 Skill 域

只有满足以下条件才新增：

- 用户意图长期稳定，且现有四域无法准确表达。
- 有独立的触发条件、行为流程和安全边界。
- 有至少一个正式入口，或明确的阻塞职责。
- 独立注册能带来实际价值，不只是目录拆分。

最小结构：

```text
subskills/<domain>/
  SKILL.md
  agents/openai.yaml
  references/
  scripts/              # 有正式入口时创建
```

随后更新根 `SKILL.md`、`agents/openai.yaml`、中英文 README、`references/routing-and-safety.md`、`references/subskill-registration.md` 和测试路径清单。

## SKILL.md 与接入描述

- `description` 写真实用户触发语义和边界，不写内部实现历史。
- 主体先规定触发后的动作，再指向按需 reference。
- `SKILL.md` 不复制完整 API 手册；超过一个主题的深层说明拆到 references。
- `agents/openai.yaml` 必须说明本域范围、正式入口、独立注册 cwd 路径和不能绕过的红线。
- 查询相邻意图必须同时提供 should-trigger、should-not-trigger 和最近邻样例。

## 单一信息来源

| 事实 | 唯一来源 |
|---|---|
| 全局写操作白名单、组织和安全边界 | `references/routing-and-safety.md` |
| create 命令到脚本/字段文档映射 | `subskills/create/references/index.md` |
| query capability 结构化事实 | `subskills/query/references/metadata/capabilities.json` |
| query 二次意图路由 | `subskills/query/references/intent-routing.md` |
| 当前身份 SSH API 流程和 token 生命周期 | `subskills/access/references/ssh-connection.md` |
| 运行时和组织行为 | `subskills/common/references/runtime.md` |
| 使用报告流程 | `subskills/query/references/report-template-playbook.md` |

其他文档链接到唯一来源，不复制容易漂移的大表。

## 验证清单

1. JSON/YAML 能解析，Python 能编译。
2. 新正式入口或受影响入口的 `--help` 可执行。
3. metadata 中每个 capability 都有 handler，CLI `capabilities` 可列出。
4. 至少有 3 个 should-trigger、3 个 should-not-trigger 和 1 个最近邻样例。
5. 定向单元测试通过。
6. 受影响的完整回归测试通过。
7. 文档中的命令路径从仓库根 cwd 和独立子 Skill cwd 都不混淆。

常用验证：

```bash
python3 -m unittest tests.test_inspection_capabilities
python3 -m unittest discover -s tests -p 'test_*.py'
python3 subskills/query/scripts/jms_inspect.py capabilities
python3 subskills/query/scripts/jms_inspect.py inspect --help
```

live acceptance 只在已有受控 JumpServer 测试环境并显式启用时运行，不能把生产环境当测试夹具。
