# 组件负载与改密失败分析

## 组件负载概览

- capability：`component-load-overview`
- 入口：`python3 subskills/query/scripts/jms_inspect.py inspect --capability component-load-overview --days 1`
- 数据源：`/api/v1/terminal/terminals/`

适用于查看 Koko、Lion 等终端组件的存活状态、CPU、内存、磁盘、在线会话与高负载标记。

主要输出：

- `summary.component_count`：组件总数。
- `summary.metric_ready_count`：至少存在 CPU、内存、磁盘或 load 指标的组件数。
- `summary.high_load_component_count`：高负载组件数。
- `records[]`：组件名称/类型/地址、存活状态、各项负载、在线会话与 `is_high_load`。

高负载判定：CPU `>= 80%`、内存 `>= 80%`、磁盘 `>= 85%` 或 `load_value >= 0.8`，满足任一项即标记。接口没有指标时保留组件基础状态，并通过 `metric_ready_count` 明确覆盖范围，不能把缺失指标解释为零负载。

## 改密失败报错分析

- capability：`change-password-failure-report`
- 入口：`python3 subskills/query/scripts/jms_inspect.py inspect --capability change-password-failure-report --days 30`
- 数据源：`/api/v1/audits/password-change-logs/`

适用于统计改密成功/失败数量及占比，并按错误类型、资产、用户给出失败 Top 和最多 200 条失败明细。

支持 `--date-from`、`--date-to`、`--days`、`--search`、`--user`、`--change-by`、`--remote-addr`、`--status`。低频或版本相关过滤字段仍可使用重复的 `--filter key=value`。

失败识别顺序：

1. 检查 `status/status_display/result/reason/type`。
2. 检查 `reason/detail/message/error/error_message/type`。
3. 命中 `fail/failed/error/denied/timeout/invalid/失败/错误/超时` 时判为失败。
4. 没有可用错误详情时，错误类型为 `unknown`，不从状态文本臆造原因。

主要输出：

- `summary.total/success_total/failed_total`。
- `summary.success_rate/failure_rate`。
- `summary.top_error_types/top_failed_assets/top_failed_users`。
- `records[]`：失败记录的用户、资产、账号、执行人、来源地址、状态、错误类型和时间。

## 版本与数据边界

- 当前实现目标版本为 JumpServer V4.10；其他版本若字段或端点不同，先用 `jms_common.py endpoint-verify` 验证。
- 比例只基于本次正式入口在明确组织和时间窗内返回的记录。
- `metric_ready_count=0` 或改密记录为空时，只报告数据事实，不推断组件健康或改密任务未运行的原因。
