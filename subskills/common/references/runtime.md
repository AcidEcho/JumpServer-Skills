# 运行入口与环境

## 快速概览

- 这份文档是所有 `common / access / query / create / update` 请求的统一预检入口。
- 面向用户的正式业务入口固定为 `subskills/*/scripts/jms_*.py`；同目录下其余 `jms_*.py` 文件是公共运行时/请求/发现/聚合模块，不作为独立业务入口。
- 首次运行任一正式入口时，脚本会先按当前解释器环境自动检查 `requirements.txt` 中的依赖；缺失时自动安装，再执行 `python3 subskills/common/scripts/jms_common.py config-status --json` 检查本地配置是否完整。
- 若配置不完整，按固定顺序对话收集 `JMS_API_URL -> (JMS_ACCESS_KEY_ID + JMS_ACCESS_KEY_SECRET 或 JMS_USERNAME + JMS_PASSWORD) -> JMS_TIMEOUT -> JMS_VERIFY_TLS`，回显脱敏摘要后执行 `config-write --confirm` 生成本地 `.env`。
- 预检分两级：当前解释器环境缺依赖时先做依赖自愈 + 全量校验，依赖已就绪的后续请求做轻量校验。
- `.env` 支持保存当前组织 ID：`JMS_ORG_ID`。
- 未显式传组织时，正式入口使用 `.env JMS_ORG_ID` 作为 `X-JMS-ORG`。
- `select-org` 不带 `--confirm` 只预览；带 `--confirm` 写回 `.env JMS_ORG_ID`。
- 多组织且没有当前组织时，返回 `candidate_orgs` 并阻塞，要求先选择组织。
- 手工执行正式入口时，推荐优先使用显式参数和重复的 `--filter key=value`；`--filters '{"key":"value"}'` 仅兼容旧命令。

## 预检模式总览

| 模式 | 何时使用 | 检查内容 | 失败动作 |
|---|---|---|---|
| 全量校验 | 当前解释器环境首次运行，或检测到缺依赖 | Python 3、自动依赖检查/安装、`config-status --json`、必要时 `config-write --confirm`、环境完整性、`ping` | 停止业务命令，先补环境 |
| 轻量校验 | 同一解释器环境且依赖已就绪的后续请求 | 关键环境、`ping` | 升级为全量校验 |
| 全量回退 | 环境变化、依赖自检失败或轻量校验失败 | 重新执行完整全量流程 | 仍失败则停止业务命令 |

说明：

- “同一解释器环境”指同一台机器、同一 skill 工作目录、同一个 Python 解释器 / venv，以及同一套 `.env` 或 shell 环境，且用户没有明确切换 JumpServer 环境。
- 这里的“首次 / 后续”不依赖程序级状态文件，而是按当前解释器环境中依赖是否已安装来判断。

## 首次全量校验

### 1. Python 3

| 平台 | 首选命令 | 回退命令 | 通过标准 |
|---|---|---|---|
| Linux/macOS | `python3 --version` | 无 | 返回 Python 3 版本 |
| Windows / PowerShell | `python --version` | `py -3 --version` | 返回 Python 3 版本 |

### 2. 依赖自动检查与安装

正式入口会先检查当前解释器环境是否已安装 `requirements.txt` 中的依赖；如果缺失，会自动执行等价于下列命令的安装流程：

```bash
python3 -m pip install -r requirements.txt
```

规则：

- 自动安装始终绑定当前实际运行脚本的 Python 解释器。
- 自动安装失败时，不继续执行业务命令，并返回手动兜底安装命令。
- 离线环境需要自行准备本地 wheel、内部镜像源，或手动补齐 pip 安装能力。

### 3. 本地配置状态检查

```text
python3 subskills/common/scripts/jms_common.py config-status --json
  -> complete=true: 继续全量校验
  -> complete=false: 查看 missing_fields / invalid_fields -> 对话收集配置 -> 脱敏确认 -> python3 subskills/common/scripts/jms_common.py config-write --payload '<json>' --confirm
```

说明：

- `missing_fields` 表示缺失的必需字段。
- `invalid_fields` 表示字段已提供，但格式或取值非法；当前至少会校验 `JMS_API_URL` 与 `JMS_TIMEOUT`。
- CLI 失败返回通常包含 `user_message`、`action_hint`、`suggested_commands`；优先按 `suggested_commands` 重试。
- `.env` 固定使用 UTF-8；读取兼容 UTF-8 BOM，正式写回统一使用无 BOM UTF-8。
- `config-write --confirm` 使用版本化的对称 codec，引号、反斜杠和 Unicode 值可精确往返；旧格式在下次成功写入时迁移，并保留旧 reader 当前解析到的值。
- 所有配置都是单行标量；CR/LF/NUL 会被拒绝并返回 `invalid_env_value`，错误结果不会回显原值。
- 非 UTF-8 或损坏字节返回 `invalid_env_encoding`，不自动猜测 GBK 或系统编码。
- 所有内部配置写入共用 `0600` 的 `.env.lock`；写入先完成完整编码，再通过同目录临时文件原子替换。编码或写盘失败时保留原 `.env`。
- 已被旧 codec 改坏的特殊字符凭据无法可靠反推原值，需要重新输入完整的新配置。
- 现存 `.env` 返回 `invalid_env_encoding`、`invalid_env_format` 或读取期 `invalid_env_value` 时，可执行 `config-write --payload '<完整-json>' --recover-invalid-env --confirm`。正常文件或缺失文件会返回 `env_recovery_not_required`，符号链接和非普通文件会被拒绝。
- 恢复 payload 不读取旧值，也不借用 shell 环境补齐；必须显式提供 `JMS_API_URL` 和至少一套完整认证，未知字段、缺失字段或非法字段会在备份前阻塞。
- 恢复写入前按原始字节生成同目录 `.env.recovery-*.bak`，权限为 `0600`；返回包含 `backup_file_path` 和 `recovery_reason_code`。备份包含旧凭据，不会自动删除。
- 恢复提交会先把当前文件原子移入 `.env.recovery-*.stage` 并核对原始字节，再以“不覆盖已存在路径”的方式安装新文件；正常成功会删除 stage。若检测到并发修改，返回 `env_recovery_conflict`，保留并通过 `staged_file_path` 指明未能安全归位的文件。
- 移动旧文件前会真实预检同目录硬链接能力；exFAT、部分 SMB 等不支持时返回 `env_recovery_hardlink_unsupported`，原 `.env` 不移动。

### 4. 环境完整性

| 类别 | 变量 | 要求 | 说明 |
|---|---|---|---|
| 地址 | `JMS_API_URL` | 必需 | JumpServer 地址 |
| AK/SK 鉴权 | `JMS_ACCESS_KEY_ID`、`JMS_ACCESS_KEY_SECRET` | 与用户名密码二选一，且需成组完整 | API Access Key |
| 用户名密码鉴权 | `JMS_USERNAME`、`JMS_PASSWORD` | 与 AK/SK 二选一，且需成组完整 | JumpServer 登录凭据 |
| 超时 | `JMS_TIMEOUT` | 可选 | 请求超时秒数 |
| TLS 校验 | `JMS_VERIFY_TLS` | 可选 | 默认 `false` |
| 当前组织 | `JMS_ORG_ID` | 可选 | 可先留空，之后由 `select-org --confirm` 写入 |

### 5. 连通性进入检查

```text
python3 subskills/common/scripts/jms_common.py ping
  -> 进入 query / create / update
```

## 后续轻量校验

| 步骤 | 检查内容 | 通过标准 |
|---|---|---|
| 本地配置状态 | `python3 subskills/common/scripts/jms_common.py config-status --json` | `complete=true` |
| 连通性 | `python3 subskills/common/scripts/jms_common.py ping` | 返回可连接结果 |

## 组织默认与显式传入

| 条件 | 固定规则 |
|---|---|
| 普通业务未传组织 | 使用 `.env JMS_ORG_ID` 当前组织 |
| 报告未传组织 | 默认使用全局组织 `00000000-0000-0000-0000-000000000000`，不写 `.env JMS_ORG_ID` |
| 报告显式传组织名或组织 ID | 使用对应组织 ID，仅限本次报告，不写入 `.env JMS_ORG_ID` |
| 普通业务显式传组织名 | 先用 `select-org` 或组织查询解析成组织 ID，再传业务脚本 |
| 普通业务显式传组织 ID | 本次命令通过 `X-JMS-ORG` 请求头临时限定组织 |
| 多组织且未选择当前组织 | 返回 `candidate_orgs`，要求先执行 `select-org --confirm` |

## Common 正式入口

| 入口 | 用途 |
|---|---|
| `python3 subskills/common/scripts/jms_common.py config-status --json` | 查看当前本地配置状态 |
| `python3 subskills/common/scripts/jms_common.py config-write --payload '<json>' --confirm` | 生成或覆盖本地 `.env` |
| `python3 subskills/common/scripts/jms_common.py config-write --payload '<完整-json>' --recover-invalid-env --confirm` | 备份并替换现存且无法解析的 `.env` |
| `python3 subskills/common/scripts/jms_common.py select-org --org-id <org-id> --confirm` | 按组织 ID 写入 `.env JMS_ORG_ID` |
| `python3 subskills/common/scripts/jms_common.py select-org --org-name <org-name>` | 按组织名称预览组织，不写回 `.env` |
| `python3 subskills/common/scripts/jms_common.py ping` | 连通性检查 |
| `python3 subskills/common/scripts/jms_common.py endpoint-inventory/endpoint-verify` | 端点 inventory 与验证 |

查询、创建和更新入口边界见根级 [路由与安全边界](../../../references/routing-and-safety.md)。
