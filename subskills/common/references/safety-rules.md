# Common 本地写入边界

## 快速概览

- common 子 Skill 只负责配置、预检、组织选择、连通性和端点验证。
- common 允许的本地写入只有 `.env` 运行时配置和 `.env JMS_ORG_ID` 当前组织。
- 全仓库写操作白名单和阻塞规则见根级 [路由与安全边界](../../../references/routing-and-safety.md)。

## 风险等级

| 风险等级 | 场景 |
|---|---|
| 低 | 配置状态读取、连通性检查、端点验证 |
| 中 | 本地 `.env` 写入、当前组织确认 |

## Common 动作边界

| 动作 | 当前是否支持 | 处理方式 |
|---|---|---|
| `config-status --json` | 支持 | 读取本地配置状态 |
| `config-write --confirm` | 支持 | 写入或覆盖本地 `.env` |
| `ping` | 支持 | 验证 JumpServer 连通性 |
| `select-org` | 支持 | 不带 `--confirm` 只预览 |
| `select-org --confirm` | 支持 | 写入 `.env JMS_ORG_ID` |
| `endpoint-inventory` / `endpoint-verify` | 支持 | 端点清单与连通验证 |

## 阻塞规则

| 条件 | 要求 |
|---|---|
| 配置缺失或格式非法 | 先补齐 `.env` 或通过 `config-write --confirm` 写入 |
| 认证信息不完整 | 补齐 AK/SK 或用户名密码中的一组 |
| 多组织且没有当前组织 | 先用 `select-org --confirm` 写入 `.env JMS_ORG_ID` |
| 组织名称未匹配或多匹配 | 返回 `candidate_orgs`，确认后重试 |
| 连通性失败 | 先修复地址、认证、TLS 或网络 |

## 推荐阻塞模板

```text
common 范围：配置、预检、组织选择、连通性、端点验证。
目标动作：<config / org selection / ping / endpoint verify>
阻塞原因：<配置缺失 / 认证缺失 / 组织未确认 / 连通性失败>

建议下一步：
1. 先执行 `config-status --json` 查看缺失项。
2. 补齐配置后执行 `ping`。
3. 多组织场景先执行 `select-org --confirm`。
```
