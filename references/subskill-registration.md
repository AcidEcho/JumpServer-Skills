# 子 Skill 独立注册

根目录主 Skill 是推荐入口。宿主一次只能注册一个 Skill，或只需要某一能力域时，也可注册 `subskills/` 下的单个目录。

## 注册入口

| 子 Skill 根目录 | 接入描述 | 主要本地入口 |
|---|---|---|
| `subskills/common/` | `subskills/common/agents/openai.yaml` | `scripts/jms_common.py` |
| `subskills/access/` | `subskills/access/agents/openai.yaml` | `scripts/jms_ssh_connect.py connect-info`、`scripts/jms_db_connect.py db-query` |
| `subskills/query/` | `subskills/query/agents/openai.yaml` | `scripts/jms_access.py user-assets/user-nodes/user-asset-access`、`scripts/jms_query.py`、`scripts/jms_permissions.py`、`scripts/jms_audit.py`、`scripts/jms_inspect.py`、`scripts/jms_runtime_query.py`、`scripts/jms_report.py` |
| `subskills/create/` | `subskills/create/agents/openai.yaml` | `scripts/jms_create_*.py`、`scripts/jms_*user*.py`、`scripts/jms_asset_account_bulk.py` |
| `subskills/update/` | `subskills/update/agents/openai.yaml` | 当前无可执行入口，只负责阻塞和边界说明 |

## 路径规则

- 从仓库根目录执行：使用 `python3 subskills/<domain>/scripts/<entry>.py ...`。
- 把子目录注册为 Skill 根目录并以该目录为 cwd：使用 `python3 scripts/<entry>.py ...`。
- 子 Skill 脚本仍依赖完整仓库中的 sibling `common`、references、template 和 requirements。只复制单个子目录不是自包含安装。
- Query 的 `subskills/query/scripts/jms_access.py` 是用户有效访问范围的正式入口；Access 的 `subskills/access/scripts/jms_ssh_connect.py` 提供 `connect-info`，`jms_db_connect.py` 提供 MySQL/MariaDB `db-query`。
- Access 与 Query 零代码依赖，双方不得互相导入或加载；两者只复用 sibling Common 运行时。
- 不要为了独立注册复制 `jumpserver_common`。

## 注册前检查

1. 确认完整仓库目录仍在原结构中。
2. 读取目标子 Skill 的 `SKILL.md` 和 `agents/openai.yaml`。
3. 从计划使用的 cwd 执行一个 `--help` 命令。
4. common/access/query/create 仍遵循根级 [路由与安全边界](routing-and-safety.md)。
5. update 子 Skill 当前只能解释不支持范围，不能用临时 HTTP/SDK 绕过。

## 验收命令

```bash
python3 subskills/common/scripts/jms_common.py --help
python3 subskills/access/scripts/jms_ssh_connect.py --help
python3 subskills/access/scripts/jms_db_connect.py --help
python3 subskills/query/scripts/jms_inspect.py --help
python3 subskills/create/scripts/jms_create_user.py --help
```

在子 Skill 目录作为 cwd 时，把路径缩短为 `python3 scripts/<entry>.py --help`。
