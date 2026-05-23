# Create Reference Index

create 子 skill 已支持以下正式入口。通用规则：

- 无 `--confirm` 只 dry-run 预览，不 POST。
- 追加 `--confirm` 后才解析引用、执行查重并创建。
- dry-run、成功和错误输出都会脱敏密文字段或密文语义字段。
- 组织限制以根级 [路由与安全边界](../../../references/routing-and-safety.md) 为准。

| 命令 | 脚本 | 功能 | 参考 |
|---|---|---|---|
| `create-user` | [`jms_create_user.py`](../scripts/jms_create_user.py) | 创建本地用户 | [create-user.md](create-user.md) |
| `create-user-group` | [`jms_create_user_group.py`](../scripts/jms_create_user_group.py) | 创建用户组 | [create-user-group.md](create-user-group.md) |
| `create-organization` | [`jms_create_org.py`](../scripts/jms_create_org.py) | 创建组织 | [create-organization.md](create-organization.md) |
| `invite-user-to-org` | [`jms_invite_user.py`](../scripts/jms_invite_user.py) | 邀请用户加入组织 | [invite-user-to-org.md](invite-user-to-org.md) |
| `add-user-to-user-group` | [`jms_add_user_to_group.py`](../scripts/jms_add_user_to_group.py) | 添加用户到用户组 | [add-user-to-user-group.md](add-user-to-user-group.md) |
| `create-label` | [`jms_create_label.py`](../scripts/jms_create_label.py) | 创建标签 | [create-label.md](create-label.md) |
| `create-node` | [`jms_create_node.py`](../scripts/jms_create_node.py) | 创建资产节点 | [create-node.md](create-node.md) |
| `create-host-asset` | [`jms_create_asset.py`](../scripts/jms_create_asset.py) | 创建主机资产 | [create-asset.md](create-asset.md) |
| `create-device-asset` | [`jms_create_asset.py`](../scripts/jms_create_asset.py) | 创建网络设备资产 | [create-asset.md](create-asset.md) |
| `create-database-asset` | [`jms_create_asset.py`](../scripts/jms_create_asset.py) | 创建数据库资产 | [create-asset.md](create-asset.md) |
| `create-web-asset` | [`jms_create_asset.py`](../scripts/jms_create_asset.py) | 创建 Web 资产 | [create-asset.md](create-asset.md) |
| `create-zone` | [`jms_create_zone_gateway.py`](../scripts/jms_create_zone_gateway.py) | 创建网域 | [create-zone-gateway.md](create-zone-gateway.md) |
| `create-gateway` | [`jms_create_zone_gateway.py`](../scripts/jms_create_zone_gateway.py) | 创建网关机器 | [create-zone-gateway.md](create-zone-gateway.md) |
| `create-account-template` | [`jms_create_account_template.py`](../scripts/jms_create_account_template.py) | 创建账号模板 | [create-account-template.md](create-account-template.md) |
| `add-account-to-assets` | [`jms_asset_account_bulk.py`](../scripts/jms_asset_account_bulk.py) | 给资产批量添加账号 | [asset-account-bulk.md](asset-account-bulk.md) |
| `add-account-template-to-assets` | [`jms_asset_account_bulk.py`](../scripts/jms_asset_account_bulk.py) | 给资产或节点批量添加账号模板 | [asset-account-bulk.md](asset-account-bulk.md) |
| `create-command-group` | [`jms_create_command_acl.py`](../scripts/jms_create_command_acl.py) | 创建命令组 | [create-command-acl.md](create-command-acl.md) |
| `create-command-filter-rule` | [`jms_create_command_acl.py`](../scripts/jms_create_command_acl.py) | 创建命令过滤规则 | [create-command-acl.md](create-command-acl.md) |
| `create-login-acl` | [`jms_create_login_acl.py`](../scripts/jms_create_login_acl.py) | 创建用户登录控制 | [create-login-acl.md](create-login-acl.md) |
| `create-connect-method-acl` | [`jms_create_connect_method_acl.py`](../scripts/jms_create_connect_method_acl.py) | 创建连接方式过滤器 | [create-connect-method-acl.md](create-connect-method-acl.md) |
| `create-asset-permission` | [`jms_create_asset_permission.py`](../scripts/jms_create_asset_permission.py) | 创建资产授权规则 | [create-asset-permission.md](create-asset-permission.md) |
| `create-login-asset-acl` | [`jms_create_login_asset_acl.py`](../scripts/jms_create_login_asset_acl.py) | 创建资产连接规则 | [create-login-asset-acl.md](create-login-asset-acl.md) |
| `create-data-masking-rule` | [`jms_create_data_masking_rule.py`](../scripts/jms_create_data_masking_rule.py) | 创建数据脱敏过滤规则 | [create-data-masking-rule.md](create-data-masking-rule.md) |
