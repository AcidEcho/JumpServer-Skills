# JumpServer 创建类接口汇总

## 1. 创建用户

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/users/users/` |

### 实现情况

- 已实现。对应 `create-user`，接口 `/api/v1/users/users/`。

### Payload

```json
{
  "password_strategy": "custom",
  "need_update_password": true,
  "mfa_level": 0,
  "source": "local",
  "system_roles": [
    "00000000-0000-0000-0000-000000000003",
    "00000000-0000-0000-0000-000000000001",
    "00000000-0000-0000-0000-000000000002"
  ],
  "org_roles": [
    "00000000-0000-0000-0000-000000000007",
    "00000000-0000-0000-0000-000000000005",
    "00000000-0000-0000-0000-000000000006"
  ],
  "is_active": true,
  "date_expired": "2096-04-25T13:11:06.317281Z",
  "phone": "+8613576878810",
  "name": "名称",
  "username": "用户名",
  "email": "qq@qq.com",
  "groups": [
    {
      "pk": "70cbcc8a-c4a8-480c-9f63-95e9c7166bd6"
    }
  ],
  "password": "Calong@2015",
  "comment": "备注"
}
```

### 补充信息

- `password_strategy` 值选项：
  - `custom`：自定义密码
  - `email`：生成重置密码链接，通过邮件发送给用户
- `mfa_level` 值选项：
  - `0`：禁用
  - `1`：启用
  - `3`：强制启用

## 2. 邀请用户加入某个组织

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/users/users/invite/` |

### 实现情况

- 已实现。对应 `invite-user-to-org`，接口 `/api/v1/users/users/invite/`。

### Payload

```json
{
    "users": [
        "c85d65e8-5909-47d2-b2b3-65f752583197",
        "4509bddf-0449-4982-89c5-05aac5c9721f",
        "95f1c16a-e0cc-444d-9e5c-777ccd61824a",
        "7ee123d6-7e8b-469b-ab28-a17af43da182"
    ],
    "org_roles": [
        "00000000-0000-0000-0000-000000000005",
        "00000000-0000-0000-0000-000000000006",
        "00000000-0000-0000-0000-000000000007"
    ]
}
```

### 补充信息

- `user`：用户id，可以是单个可以是多个
- `org_roles`：组织角色id，可以是单个可以是多个

## 3. 创建用户组

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/users/groups/` |

### 实现情况

- 已实现。对应 `create-user-group`，接口 `/api/v1/users/groups/`。

### Payload

```json
{
  "users": [
    {
      "pk": "636ee32f-9fbb-42a4-b9f7-3ae85444b74f"
    }
  ],
  "name": "用户组111",
  "comment": "备注"
}
```

### 补充信息

- 待补充

## 4. 添加用户到用户组

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/users/users-groups-relations/` |

### 实现情况

- 已实现。对应 `add-user-to-user-group`，接口 `/api/v1/users/users-groups-relations/`。

### Payload

```json
[
  {
    "user": "c85d65e8-5909-47d2-b2b3-65f752583197",
    "usergroup": "461341da-5152-4605-9db8-3674a6fb8955"
  },
  {
    "user": "4509bddf-0449-4982-89c5-05aac5c9721f",
    "usergroup": "461341da-5152-4605-9db8-3674a6fb8955"
  },
  {
    "user": "7ee123d6-7e8b-469b-ab28-a17af43da182",
    "usergroup": "461341da-5152-4605-9db8-3674a6fb8955"
  },
  {
    "user": "08f93832-8672-4179-ba4d-3ae4a15f8810",
    "usergroup": "461341da-5152-4605-9db8-3674a6fb8955"
  },
  {
    "user": "00dadc4e-3f2d-4155-9cfc-ff5eb6e261ef",
    "usergroup": "461341da-5152-4605-9db8-3674a6fb8955"
  }
]
```

### 补充信息

- 待补充

## 5. 新建组织

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/orgs/orgs/` |

### 实现情况

- 已实现。对应 `create-organization`，接口 `/api/v1/orgs/orgs/`。

### Payload

```json
{
  "name": "new",
  "comment": "备注"
}
```

### 补充信息

- 待补充

## 6. 新建标签

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/labels/labels/` |

### 实现情况

- 已实现。对应 `create-label`，接口 `/api/v1/labels/labels/`。

### Payload

```json
{
  "color": "#689f7d",
  "name": "123",
  "value": "321",
  "comment": "备注"
}
```

### 补充信息

- 待补充

## 7. 创建用户登录控制

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/acls/login-acls/` |

### 实现情况

- 已实现。对应 `create-login-acl`，接口 `/api/v1/acls/login-acls/`。

### Payload

```json
{
  "name": "用户登录控制",
  "priority": 50,
  "users": {
    "type": "all"
  },
  "rules": {
    "ip_group": [
      "1.1.1.1",
      "*"
    ],
    "time_period": [
      {
        "id": 1,
        "value": "00:00~00:00"
      },
      {
        "id": 2,
        "value": "00:00~00:00"
      },
      {
        "id": 3,
        "value": "00:00~00:00"
      },
      {
        "id": 4,
        "value": "00:00~00:00"
      },
      {
        "id": 5,
        "value": "00:00~00:00"
      },
      {
        "id": 6,
        "value": "00:00~00:00"
      },
      {
        "id": 0,
        "value": "00:00~00:00"
      }
    ]
  },
  "action": "notice",
  "reviewers": [
    {
      "pk": "636ee32f-9fbb-42a4-b9f7-3ae85444b74f"
    },
    {
      "pk": "c85d65e8-5909-47d2-b2b3-65f752583197"
    }
  ],
  "is_active": true,
  "comment": ""
}
```

### 补充信息
- `priority`：优先级，如果用户未显式指定优先级，默认设置为 50
- 用户登录控制只能在全局组织下创建。
- `action` 值选项：
  - `review`：审批
  - `accept`：接受
  - `reject`：拒绝
  - `notice`：通知
- `action`：如果用户未显式传入，默认设置为 `reject`
- `action` 为 `review`、`notice` 时，才需要选择 `reviewers`，审批人，通知接收人都需要复用现有用户查询功能，查询对应的用uuid
- `rules.ip_group` 支持：
  - `*`：匹配所有
  - 单个 IP：`192.168.10.1`
  - CIDR：`192.168.1.0/24`
  - IP 范围：`10.1.1.1-10.1.1.20`
  - IPv6：`2001:db8:2de::e13`
  - IPv6 CIDR：`2001:db8:1a:1110::/64`
- `time_period`：规则时段
  - `value`：时间范围
  - `id` 值字段含义:
    - `1`：周一、星期一
    - `2`：周二、星期二
    - `3`：周三、星期三
    - `4`：周四、星期四
    - `5`：周五、星期五
    - `6`：周六、星期六
    - `0`：周日、星期天
- `users.type` 值选项：
  - `all`：全部用户
  - `ids`：指定用户
  - `attrs`：属性筛选
- `users.type` 为 `attrs` 时，字段含义：
  - `name` 值选项：
    - `is_active`：激活状态
    - `is_first_login`：首次登录
    - `email`：邮箱
    - `username`：用户名
    - `name`：名称
    - `org_roles`：组织角色
    - `system_roles`：系统角色
    - `comment`：备注
  - `match` 值选项：
    - `exact`：等于
    - `not`：不等于
    - `endswith`：以...结尾
    - `in`：在...中
    - `startswith`：以...开头
    - `m2m`：任意包含
    - `m2m_all`：同时包含
    - `regex`：正则匹配
- 名称、用户名、邮箱、备注字段的 `match` 值选项有：
    - `exact`：等于
    - `not`：不等于
    - `endswith`：以...结尾
    - `in`：在...中
    - `startswith`：以...开头
    - `regex`：正则匹配
- 系统角色、组织角色字段的 `match` 值选项有：
    - `m2m`：任意包含
    - `m2m_all`：同时包含
- 激活、首次登录字段的 `match` 值选项有：
    - `exact`：等于
    - `not`：不等于
- 激活、首次登录字段的 `value` 只有 true、false

- `users.type` 为 `attrs` 时，配置示例：
```json
[
  {
    "name": "is_active",
    "match": "exact",
    "value": true
  },
  {
    "name": "is_first_login",
    "match": "not",
    "value": true
  },
  {
    "name": "email",
    "match": "endswith",
    "value": "111@11.com"
  },
  {
    "name": "username",
    "match": "in",
    "value": [
      "213"
    ]
  },
  {
    "name": "name",
    "match": "startswith",
    "value": "111"
  },
  {
    "name": "org_roles",
    "match": "m2m",
    "value": [
      "00000000-0000-0000-0000-000000000005",
      "00000000-0000-0000-0000-000000000007",
      "00000000-0000-0000-0000-000000000006"
    ]
  },
  {
    "name": "system_roles",
    "match": "m2m_all",
    "value": [
      "00000000-0000-0000-0000-000000000001",
      "00000000-0000-0000-0000-000000000002",
      "00000000-0000-0000-0000-000000000003"
    ]
  },
  {
    "name": "comment",
    "match": "regex",
    "value": "111"
  }
]
```

## 8. 创建主机资产 - 主机

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/assets/hosts/` |

### 实现情况

- 已实现。对应 `create-host-asset`，接口 `/api/v1/assets/hosts/`。

### Payload

```json
{
    "platform": {
        "pk": 1
    },
    "nodes": [
        {
            "pk": "6040812c-63f9-4be5-93c8-3a5dcee8ac29"
        }
    ],
    "protocols": [
        {
            "name": "ssh",
            "port": 22
        },
        {
            "name": "sftp",
            "port": 22
        }
    ],
    "labels": [
        {
            "pk": "4c51013c-47ed-44ac-bbcb-3702eae79909"
        }
    ],
    "is_active": true,
    "name": "Linux",
    "address": "1.1.1.1",
    "accounts": [
        {
            "privileged": true,
            "secret_type": "password",
            "secret_reset": true,
            "push_now": false,
            "on_invalid": "error",
            "is_active": true,
            "username": "root",
            "name": "root",
            "secret": "123321"
        },
        {
            "template": "98f6a57c-9d68-40d3-8018-355eff682dee"
        }
    ],
    "zone": "1a52f8a4-93b2-44d9-af45-7b3adbe7e342",
    "comment": "备注"
}
```

### 补充信息
- platform，nodes，labels，accounts.template，zone都要复用现有查询功能进行查询对应的id
- `platforms` 的 `pk` 值是平台id
- accounts创建资产时，同时创建账号配置示例：
```json
"accounts": [
  {
      "privileged": true,
      "secret_type": "password",
      "secret_reset": true,
      "push_now": false,
      "on_invalid": "error",
      "is_active": true,
      "username": "root",
      "name": "root",
      "secret": "123321"
  }
]   
```
- accounts创建资产时，同时引用账号模版配置示例：
```json
"accounts": [
  {
    "template": "98f6a57c-9d68-40d3-8018-355eff682dee"
  }
]
```
- `accounts` 的 `secret_type` 值选项：
  - `privileged`：是否勾选特权账号
  - `password`： 密码
  - `ssh_key`：ssh密钥
- 当`accounts` 的 `secret_type` 值选项为`ssh_key`时：
  - `passphrase`：密钥密码
  - `secret`：密钥内容


## 9. 创建主机资产 - 网络设备

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/assets/devices/` |

### 实现情况

- 已实现。对应 `create-device-asset`，接口 `/api/v1/assets/devices/`。

### Payload

```json
{
  "platform": {
    "pk": 14
  },
  "nodes": [
    {
      "pk": "6040812c-63f9-4be5-93c8-3a5dcee8ac29"
    }
  ],
  "protocols": [
    {
      "name": "ssh",
      "port": 22
    }
  ],
  "labels": [
    {
      "pk": "3b4996c3-1e95-46d0-aba8-282b9cd3bca7"
    }
  ],
  "is_active": true,
  "name": "网络设备",
  "address": "1.1.1.1",
  "accounts": [
    {
      "privileged": false,
      "secret_type": "password",
      "secret_reset": true,
      "push_now": false,
      "on_invalid": "error",
      "is_active": true,
      "name": "11",
      "username": "11",
      "comment": "11",
      "secret": "123123131"
    },
    {
      "template": "4c9d3129-9d5d-48cd-a62c-f7547012248f",
      "name": "root",
      "username": "root",
      "secret_type": "password",
      "privileged": true,
      "secret": ""
    }
  ],
  "zone": "ca97cfc7-8a08-4fd9-a9cb-4d3e615a768d",
  "comment": "1213"
}
```

### 补充信息

- `platforms` 的 `pk` 值是平台id
- `accounts` 的 `secret_type` 值选项：
  - `privileged`：是否勾选特权账号
  - `password`： 密码
  - `ssh_key`：ssh密钥
- 当`accounts` 的 `secret_type` 值选项为`ssh_key`时：
  - `passphrase`：密钥密码
  - `secret`：密钥内容

## 10. 创建主机资产 - 数据库

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/assets/database/` |

### 实现情况

- 已实现。对应 `create-database-asset`，接口 `/api/v1/assets/database/`。

### Payload

```json
{
  "platform": {
    "pk": 17
  },
  "nodes": [
    {
      "pk": "5047530a-36bb-4382-931c-9a7cb9958056"
    }
  ],
  "protocols": [
    {
      "name": "mysql",
      "port": 3306
    }
  ],
  "use_ssl": false,
  "allow_invalid_cert": false,
  "labels": [
    {
      "pk": "4c51013c-47ed-44ac-bbcb-3702eae79909"
    }
  ],
  "is_active": true,
  "name": "mysql",
  "address": "1.1.1.1",
  "db_name": "mysql",
  "accounts": [
    {
      "privileged": true,
      "secret_type": "password",
      "secret_reset": true,
      "push_now": false,
      "on_invalid": "error",
      "is_active": true,
      "name": "mysql",
      "username": "mysql",
      "comment": "beizhu",
      "secret": "123321"
    },
    {
      "template": "4c9d3129-9d5d-48cd-a62c-f7547012248f",
      "name": "root",
      "username": "root",
      "secret_type": "password",
      "privileged": true,
      "secret": ""
    }
  ],
  "zone": "ca97cfc7-8a08-4fd9-a9cb-4d3e615a768d",
  "comment": "beizu"
}
```

### 补充信息

- `platforms` 的 `pk` 值是平台id
- `accounts` 的 `secret_type` 值选项：
  - `privileged`：是否勾选特权账号
  - `password`： 密码
- `db_name`是默认数据库，当类型是MongoDB、POstgreSQL时，此项是必填，ClickHouse，Dameng，DB2，MariaDB，Oracle，Redis，SQLServer都不是必填项

## 11. 创建主机资产 - web资产

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/assets/webs/` |

### 实现情况

- 已实现。对应 `create-web-asset`，接口 `/api/v1/assets/webs/`。

### Payload

```json
{
  "name": "1231321",
  "address": "https://1.1.1.12:8654",
  "platform": {
    "pk": 26
  },
  "nodes": [
    {
      "pk": "0d36685e-e5df-4067-9673-3235f5ce4c10"
    }
  ],
  "autofill": "script",
  "username_selector": "name=username",
  "password_selector": "name=password",
  "submit_selector": "id=login_button",
  "script": [
    {
      "step": 1,
      "value": "{USERNAME}",
      "target": "id=username",
      "command": "type"
    },
    {
      "step": 2,
      "value": "",
      "target": "id=hide_pwd",
      "command": "click"
    },
    {
      "step": 3,
      "value": "{SECRET}",
      "target": "id=platcontent",
      "command": "type"
    },
    {
      "step": 4,
      "value": "",
      "target": "xpath=//*[@id='btn_login-button']",
      "command": "click"
    }
  ],
  "protocols": [
    {
      "name": "http",
      "port": "8654"
    }
  ],
  "directory_services": [],
  "zone": "ca97cfc7-8a08-4fd9-a9cb-4d3e615a768d",
  "labels": [
    {
      "pk": "3b4996c3-1e95-46d0-aba8-282b9cd3bca7"
    }
  ],
  "is_active": true,
  "comment": "43"
}
```

### 补充信息

- `platforms` 的 `pk` 值是平台id
- `autofill` 的 `secret_type` 值选项：
  - `no`：禁用代填
  - `basic`： 基本的代填方式
  - `script`：脚本代填方式
    - `autofill` 的 `secret_type` 值为`script`时，需要配置`script`字段

## 12. 创建网域

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/assets/zones/` |

### 实现情况

- 已实现。对应 `create-zone`，接口 `/api/v1/assets/zones/`。

### Payload

```json
{
  "name": "网域名称",
  "assets": [
    "674f8a0f-3e32-4ac1-a395-72d84222787f",
    "00171a41-a383-49c2-88a4-700985d57208"
  ],
  "comment": "备注"
}
```

### 补充信息

- 待补充

## 13. 创建节点

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/assets/nodes/` |

### 实现情况

- 已实现。对应 `create-node`，接口 `/api/v1/assets/nodes/`。

### Payload

```json
{
  "org_id": "00000000-0000-0000-0000-000000000002",
  "full_value": "/Default/Linux/新节点2",
  "value": "新节点2"
}
```

### 补充信息

- `value`：新节点名称
- `full_value`：新节点路径
- `org_id`：组织id

## 14. 创建网域网关机器

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/assets/gateways/` |

### 实现情况

- 已实现。对应 `create-gateway`，接口 `/api/v1/assets/gateways/`。

### Payload

```json
{
  "platform": {
    "pk": 11
  },
  "nodes": [
    {
      "pk": "0d36685e-e5df-4067-9673-3235f5ce4c10"
    }
  ],
  "protocols": [
    {
      "name": "ssh",
      "port": 22
    },
    {
      "name": "sftp",
      "port": 22
    }
  ],
  "zone": "ca97cfc7-8a08-4fd9-a9cb-4d3e615a768d",
  "labels": [
    {
      "pk": "48570c5d-ce3d-4187-935d-5030f83ae5a7"
    }
  ],
  "is_active": true,
  "name": "网关名称",
  "address": "1.1.1.1",
  "accounts": [
    {
      "privileged": true,
      "secret_type": "password",
      "secret_reset": true,
      "push_now": false,
      "on_invalid": "error",
      "is_active": true,
      "name": "root",
      "username": "root",
      "secret": "123123"
    }
  ],
  "comment": "备注"
}
```

### 补充信息

- `platforms` 的 `pk` 值是平台id
- `accounts` 的 `secret_type` 值选项：
  - `privileged`：是否勾选特权账号
  - `password`： 密码
  - `ssh_key`：ssh密钥
- 当`accounts` 的 `secret_type` 值选项为`ssh_key`时：
  - `passphrase`：密钥密码
  - `secret`：密钥内容
- `zone`：网域id

## 15. 给某个资产或者一批资产添加账号

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/accounts/accounts/bulk/` |

### 实现情况

- 已实现。对应 `add-account-to-assets`，接口 `/api/v1/accounts/accounts/bulk/`。

### Payload

```json
{
  "privileged": true,
  "secret_type": "password",
  "secret_reset": true,
  "push_now": false,
  "on_invalid": "skip",
  "is_active": true,
  "name": "kk",
  "username": "kk",
  "assets": [
    "674f8a0f-3e32-4ac1-a395-72d84222787f",
    "00171a41-a383-49c2-88a4-700985d57208",
    "4bfeeb4c-8404-4156-b755-65fb8e0fca58"
  ],
  "comment": "备注",
  "secret": "123123"
}
```

### 补充信息

- `privileged`：是否勾选特权账号
- `on_invalid`值选项：
  - `skip`：跳过
  - `update`：更新
  - `error`：失败
- `secret_type`值选项：
  - `ssh_key`：密钥
  - `password`：密码
  - `token`：令牌
  - `access_key`：访问密钥
  - `api_key`：API Key
- `passphrase`：密钥密码
  - `secret_type`值选项为`ssh_key`，可以选择配置`passphrase`

## 16. 给某个资产或者一批资产添加账号模板

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/accounts/accounts/bulk/` |

### 实现情况

- 已实现。对应 `add-account-template-to-assets`，接口 `/api/v1/accounts/accounts/bulk/`。

### Payload

```json
{
  "privileged": false,
  "secret_type": "password",
  "secret_reset": true,
  "push_now": false,
  "on_invalid": "error",
  "is_active": true,
  "template": [
    "c700ff23-f95f-4331-9394-67562419bf9a"
  ],
  "nodes": [
    "4a8391ec-05c8-43e9-bdab-dc34cf7bc618"
  ],
  "assets": [
    "674f8a0f-3e32-4ac1-a395-72d84222787f"
  ]
}
```

### 补充信息

- `privileged`：是否勾选特权账号
- `on_invalid`值选项：
  - `skip`：跳过
  - `update`：更新
  - `error`：失败
- `template`：账号模板id
- `nodes`：资产节点id
- `assets`：资产id

## 17. 创建账号模板

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/accounts/account-templates/` |

### 实现情况

- 已实现。对应 `create-account-template`，接口 `/api/v1/accounts/account-templates/`。

### Payload

```json
{
    "privileged": false,
    "secret_type": "password",
    "secret_strategy": "specific",
    "password_rules": {
        "length": 16,
        "lowercase": true,
        "uppercase": true,
        "digit": true,
        "symbol": true,
        "exclude_symbols": ""
    },
    "auto_push": true,
    "push_params": {},
    "name": "123123",
    "username": "ext1",
    "su_from": "c700ff23-f95f-4331-9394-67562419bf9a",
    "secret": "1232123",
    "platforms": [
        {
            "pk": 1
        }
    ],
    "comment": "123123"
}
```

### 补充信息
- `su_from`:切换至，选项请求接口：GET http://10.1.12.46/api/v1/accounts/account-templates/su-from-account-templates/?&search=&offset=0&limit=10
- `auto_push`: 是否自动推送，默认不勾选
  - `true`: 勾选后，需要配置`platforms`参数
    - 值可以请求对应的接口：GET https://acid.fit2cloud.cn:4433/api/v1/assets/platforms/?search=&offset=10&limit=10
    - 最好是复用现有查询功能
  - `false`：默认值，不自动推送
- `privileged`：是否勾选特权账号
- `secret_type`是密码类型，值选项：
  - `ssh_key`：密钥
  - `password`：密码
  - `token`：令牌
  - `access_key`：访问密钥
  - `api_key`：API Key
- `secret_type`值为 `password`时：
  - `secret_strategy`是密文策略，值选项：
    - `random`：随机生成
    - `password_rules`是密码规则：
        - `length`：长度，默认16
        - `lowercase`：大写字母，默认勾选，值为true，false
        - `uppercase`：小写字母，默认勾选，值为true，false
        - `digit`：数字，默认勾选，值为true，false
        - `symbol`：特殊字符，默认勾选，值为true，false
        - `exclude_symbols`：排除字符，默认为空
    - `specific`：指定密码
- `secret_type`值为 `ssh_key`时：
  - `secret_strategy`是密文策略，值选项：
    - `random`：随机生成，没有`password_rules`
    - `specific`：指定密码
- `secret_type`值为 `token`，`access_key`，`api_key`，只需要填写`secret`

## 18. 创建资产授权规则

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/perms/asset-permissions/` |

### 实现情况

- 已实现。对应 `create-asset-permission`，接口 `/api/v1/perms/asset-permissions/`。

### Payload

```json
{
  "assets": [
    "0a3fc9bf-720c-4991-bea3-1d03cda170f3",
    "54c2bb43-067c-476f-9423-6f410b290751"
  ],
  "nodes": [
    {
      "pk": "5047530a-36bb-4382-931c-9a7cb9958056"
    }
  ],
  "accounts": [
    "@ALL",
    "@ANON",
    "@USER",
    "@INPUT"
  ],
  "protocols": [
    "all"
  ],
  "actions": [
    "connect",
    "upload",
    "download",
    "copy",
    "paste",
    "delete",
    "share"
  ],
  "is_active": true,
  "date_start": "2026-05-14T02:49:53.056198Z",
  "date_expired": "2096-04-26T02:49:53.056217Z",
  "name": "测试",
  "users": [
    {
      "pk": "636ee32f-9fbb-42a4-b9f7-3ae85444b74f"
    }
  ],
  "user_groups": [
    {
      "pk": "70cbcc8a-c4a8-480c-9f63-95e9c7166bd6"
    }
  ],
  "comment": "测试"
}
```

### 补充信息
- assets，nodes，users，user_groups 复用现有解析功能
- protocols 默认all，代表所有协议，如果指定协议的话，需要请求接口：GET http://10.1.12.46/api/v1/assets/protocols/?search=&offset=0&limit=10，返回label字段值时显示内容，需要传入value字段值
- accounts：账号
  - "@ALL"：所有账号
  - "@SPEC"：指定账号
  - 排除账号写法示例："accounts": ["!root","!tome"]
  - 无账号写法示例："accounts": []
  - 虚拟账号：
    - "@INPUT"：手动账号，代表手动输入账号密码
    - "@USER"：与被授权人用户名相同的账号
    - "@ANON"：连接资产时不使用用户名和密码，仅支持 web类型 和 自定义类型 的资产
- 所有账号，指定账号，排除账号，无账号四个选项互斥，但是单独可以和虚拟账号组成组合
- accounts 如果用户未显式传入，默认使用 `["@ALL"]`
- actions 如果用户未显式传入，默认使用全部动作 value：`connect/upload/download/copy/paste/delete/share`
- actions：连接允许动作；payload 只发送 value 字符串列表，label 仅用于显示名称

## 19. 创建资产连接规则

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/acls/login-asset-acls/` |

### 实现情况

- 已实现。对应 `create-login-asset-acl`，接口 `/api/v1/acls/login-asset-acls/`。

### Payload

```json
{
  "priority": 50,
  "accounts": [
    "@ALL"
  ],
  "rules": {
    "ip_group": [
      "*",
      "192.168.10.1",
      "192.168.1.0/24",
      "10.1.1.1-10.1.1.20"
    ],
    "time_period": [
      {
        "id": 1,
        "value": "00:00~00:00"
      },
      {
        "id": 2,
        "value": "01:00~18:00"
      },
      {
        "id": 3,
        "value": "04:00~17:00"
      },
      {
        "id": 4,
        "value": "00:00~19:00"
      },
      {
        "id": 5,
        "value": "00:00~19:00"
      },
      {
        "id": 6,
        "value": "01:00~13:00"
      },
      {
        "id": 0,
        "value": "08:00~15:00"
      }
    ]
  },
  "action": "reject",
  "is_active": true,
  "users": {
    "type": "ids",
    "ids": [
      "e9f10a08-21d6-47c1-9044-c2988479dbcc"
    ]
  },
  "assets": {
    "type": "ids",
    "ids": [
      "674f8a0f-3e32-4ac1-a395-72d84222787f"
    ]
  },
  "name": "资产连接规则名称",
  "comment": "备注",
  "reviewers": []
}
```

### 补充信息
- `priority`：优先级，如果用户未显式指定优先级，默认设置为 50
- `action` 值选项：
  - `review`：审批
  - `accept`：接受
  - `reject`：拒绝，默认值
  - `notice`：通知
  - `face_verify`：人脸验证
  - `face_online`：人脸在线
- `action` 为 `review`、`notice` 时，才需要选择 `reviewers`，审批人，通知接收人都需要复用现有用户查询功能，查询对应的用uuid
- `accounts`勾选账号配置示例：
```json
[
  "@SPEC",
  "administrator",
  "12"
]
```
- `action` 为 `review`、`notice` 时，才需要选择 `reviewers`。
- `rules.ip_group` 支持：
  - `*`：匹配所有
  - 单个 IP：`192.168.10.1`
  - CIDR：`192.168.1.0/24`
  - IP 范围：`10.1.1.1-10.1.1.20`
  - IPv6：`2001:db8:2de::e13`
  - IPv6 CIDR：`2001:db8:1a:1110::/64`
- `time_period`：规则时段
  - `value`：时间范围
  - `id` 值字段含义:
    - `1`：周一、星期一
    - `2`：周二、星期二
    - `3`：周三、星期三
    - `4`：周四、星期四
    - `5`：周五、星期五
    - `6`：周六、星期六
    - `0`：周日、星期天
- `users.type` 值选项：
  - `all`：全部用户
  - `ids`：指定用户
  - `attrs`：属性筛选
- `users.type` 为 `attrs` 时，字段含义：
  - `name` 字段：
    - `name`：名称
    - `username`：用户名
    - `email`：邮箱
    - `comment`：备注
    - `is_active`：激活状态
    - `is_first_login`：首次登录
    - `org_roles`：组织角色
    - `system_roles`：系统角色
    - `groups`：用户组
    - `labels`：标签
  - `match` 值选项：
    - `exact`：等于
    - `not`：不等于
    - `endswith`：以...结尾
    - `in`：在...中
    - `startswith`：以...开头
    - `m2m`：任意包含
    - `m2m_all`：同时包含
    - `regex`：正则匹配
  - 名称、用户名、邮箱、备注字段的 `match` 值选项有：
    - `exact`：等于
    - `not`：不等于
    - `endswith`：以...结尾
    - `in`：在...中
    - `startswith`：以...开头
    - `regex`：正则匹配
  - 系统角色、组织角色、用户组、标签字段的 `match` 值选项有：
    - `m2m`：任意包含
    - `m2m_all`：同时包含
  - 激活、首次登录字段的 `match` 值选项有：
    - `exact`：等于
    - `not`：不等于
  - 激活、首次登录字段的 `value` 只有 true、false
- `assets.type` 值选项：
  - `all`：全部资产
  - `ids`：指定资产
  - `attrs`：属性筛选
- `assets.type` 为 `attrs` 时，字段含义：
  - `name` 字段：
    - `name`：名称
    - `address`：地址
    - `nodes`：节点
    - `platform`：平台
    - `category`：类别
    - `type`：类型
    - `protocols`：协议
    - `labels`：标签
    - `comment`：备注
  - `match` 值选项：
    - `exact`：等于
    - `not`：不等于
    - `endswith`：以...结尾
    - `in`：在...中
    - `startswith`：以...开头
    - `m2m`：任意包含
    - `m2m_all`：同时包含
    - `regex`：正则匹配
  - 名称、地址、备注字段的 `match` 值选项有：
    - `exact`：等于
    - `not`：不等于
    - `endswith`：以...结尾
    - `in`：在...中
    - `startswith`：以...开头
    - `regex`：正则匹配
  - 节点、平台、标签字段的 `match` 值选项有：
    - `m2m`：任意包含
    - `m2m_all`：同时包含
  - 类别、类型、协议字段的 `match` 值选项有：
    - `exact`：等于
    - `not`：不等于

## 20. 创建命令过滤规则

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/acls/command-filter-acls/` |

### 实现情况

- 已实现。对应 `create-command-filter-rule`，接口 `/api/v1/acls/command-filter-acls/`。

### Payload

```json
{
  "priority": 50,
  "accounts": [
    "@ALL"
  ],
  "action": "reject",
  "is_active": true,
  "users": {
    "type": "attrs",
    "attrs": [
      {
        "name": "name",
        "match": "exact",
        "value": "123"
      }
    ]
  },
  "assets": {
    "type": "attrs",
    "attrs": [
      {
        "name": "name",
        "match": "exact",
        "value": "123"
      }
    ]
  },
  "command_groups": [
    {
      "pk": "09bb62d7-7d1f-4c38-8961-21d255adafd2"
    }
  ],
  "name": "132"
}
```

### 补充信息
- `priority`：优先级，如未传入值，则默认为`50`
- `accounts`：默认勾选所有账号"@ALL"
  - 当勾选指定账号配置示例：
```json
[
  "@SPEC",
  "administrator",
  "12"
]
```
- `action` 值选项：
  - `review`：审批
  - `accept`：接受
  - `reject`：拒绝，默认值
  - `warning`：告警
  - `notice`：通知
  - `notify_and_warn`：提醒并告警

- `action` 为 `review`、`notice`、`notify_and_warn` 时，才需要选择 `reviewers`，审批人、通知接收人都需要复用现有用户查询功能，查询对应的用户 UUID
- `users.type` 值选项：
  - `all`：全部用户
  - `ids`：指定用户
  - `attrs`：属性筛选
- `users.type` 为 `attrs` 时，字段含义：
  - `name` 值选项：
    - `is_active`：激活状态
    - `is_first_login`：首次登录
    - `email`：邮箱
    - `username`：用户名
    - `name`：名称
    - `org_roles`：组织角色
    - `system_roles`：系统角色
    - `comment`：备注
  - `match` 值选项：
    - `exact`：等于
    - `not`：不等于
    - `endswith`：以...结尾
    - `in`：在...中
    - `startswith`：以...开头
    - `m2m`：任意包含
    - `m2m_all`：同时包含
    - `regex`：正则匹配
  - 名称、用户名、邮箱、备注字段的 `match` 值选项有：
    - `exact`：等于
    - `not`：不等于
    - `endswith`：以...结尾
    - `in`：在...中
    - `startswith`：以...开头
    - `regex`：正则匹配
  - 系统角色、组织角色字段的 `match` 值选项有：
    - `m2m`：任意包含
    - `m2m_all`：同时包含
  - 激活、首次登录字段的 `match` 值选项有：
    - `exact`：等于
    - `not`：不等于
  - 激活、首次登录字段的 `value` 只有 true、false
- `assets.type` 值选项：
  - `all`：全部资产
  - `ids`：指定资产
  - `attrs`：属性筛选
- `assets.type` 为 `attrs` 时，字段含义：
  - `name` 字段：
    - `name`：名称
    - `address`：地址
    - `nodes`：节点
    - `platform`：平台
    - `category`：类别
    - `type`：类型
    - `protocols`：协议
    - `labels`：标签
    - `comment`：备注
  - `match` 值选项：
    - `exact`：等于
    - `not`：不等于
    - `endswith`：以...结尾
    - `in`：在...中
    - `startswith`：以...开头
    - `m2m`：任意包含
    - `m2m_all`：同时包含
    - `regex`：正则匹配
  - 名称、地址、备注字段的 `match` 值选项有：
    - `exact`：等于
    - `not`：不等于
    - `endswith`：以...结尾
    - `in`：在...中
    - `startswith`：以...开头
    - `regex`：正则匹配
  - 节点、平台、标签字段的 `match` 值选项有：
    - `m2m`：任意包含
    - `m2m_all`：同时包含
  - 类别、类型、协议字段的 `match` 值选项有：
    - `exact`：等于
    - `not`：不等于
- `command_groups`：命令组id

## 21. 创建命令组

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/acls/command-groups/` |

### 实现情况

- 已实现。对应 `create-command-group`，接口 `/api/v1/acls/command-groups/`。

### Payload

- type值为
```json
{
  "type": "command",
  "ignore_case": true,
  "name": "命令",
  "content": "rm",
  "comment": "备注"
}
```

### 补充信息

- `type`值选项：
  - `command`：命令
    - `content`配置示例："content": "rm"
  - `regex`：正则表达式
    - `content`配置示例："content": "(?i)^\\s*update\\b(?=[^;]*\\bset\\b)(?![^;]*\\bwhere\\b)[^;]*;?\\s*$"

## 22. 创建连接方式过滤器

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/acls/connect-method-acls/` |

### 实现情况

- 已实现。对应 `create-connect-method-acl`，接口 `/api/v1/acls/connect-method-acls/`。

### Payload

```json
{
  "connect_methods": [
    "web_cli",
    "ssh_client",
    "ssh_guide",
    "sftp_client",
    "web_sftp",
    "db_client",
    "db_guide",
    "web_gui",
    "mstsc",
    "vnc_client",
    "vnc_guide",
    "chrome"
  ],
  "action": "accept",
  "is_active": true,
  "users": {
    "type": "attrs",
    "attrs": [
      {
        "name": "name",
        "match": "exact",
        "value": "123"
      }
    ]
  },
  "name": "12312",
  "comment": "321321"
}
```

### 补充信息

- 连接方式过滤器只能在全局组织下创建。
- `connect_methods`：需要限制的连接方式
- `action` 值选项：
  - `accept`：接受
  - `reject`：拒绝
- `action`：如果用户未显式传入，默认设置为 `reject`
- `users.type` 为 `attrs` 时，字段含义：
  - `name` 字段：
    - `name`：名称
    - `username`：用户名
    - `email`：邮箱
    - `comment`：备注
    - `is_active`：激活状态
    - `is_first_login`：首次登录
    - `system_roles`：系统角色
    - `groups`：用户组
    - `labels`：标签
  - `match` 值选项：
    - `exact`：等于
    - `not`：不等于
    - `endswith`：以...结尾
    - `in`：在...中
    - `startswith`：以...开头
    - `m2m`：任意包含
    - `m2m_all`：同时包含
    - `regex`：正则匹配
  - 名称、用户名、邮箱、备注字段的 `match` 值选项有：
    - `exact`：等于
    - `not`：不等于
    - `endswith`：以...结尾
    - `in`：在...中
    - `startswith`：以...开头
    - `regex`：正则匹配
  - 系统角色、用户组、标签字段的 `match` 值选项有：
    - `m2m`：任意包含
    - `m2m_all`：同时包含
  - 激活、首次登录字段的 `match` 值选项有：
    - `exact`：等于
    - `not`：不等于
  - 激活、首次登录字段的 `value` 只有 true、false

## 23. 创建数据脱敏过滤规则

### 基本信息

| 字段 | 内容 |
| --- | --- |
| 请求方法 | POST |
| 请求地址 | `http://10.1.12.46/api/v1/acls/data-masking-rules/` |

### 实现情况

- 已实现。对应 `create-data-masking-rule`，接口 `/api/v1/acls/data-masking-rules/`。

### Payload

```json
{
  "name": "test",
  "priority": 50,
  "users": {
    "type": "attrs",
    "attrs": [
      {
        "name": "name",
        "match": "exact",
        "value": "1"
      },
      {
        "name": "username",
        "match": "exact",
        "value": "1"
      }
    ]
  },
  "assets": {
    "type": "attrs",
    "attrs": [
      {
        "name": "name",
        "match": "exact",
        "value": "1"
      },
      {
        "name": "address",
        "match": "exact",
        "value": "1"
      }
    ]
  },
  "accounts": [
    "@ALL"
  ],
  "fields_pattern": "password",
  "masking_method": "fixed_char",
  "mask_pattern": "######",
  "is_active": true,
  "comment": "热"
}
```

### 补充信息
- `priority`：优先级，如果用户未显式指定优先级，默认设置为 50
- `accounts`：默认勾选所有账号"@ALL"
  - 当勾选指定账号配置示例：
```json
[
  "@SPEC",
  "administrator",
  "12"
]
```
  - 只支持 `["@ALL"]` 或 `["@SPEC", "账号名", ...]`；不支持无账号、排除账号或虚拟账号
- `users.type` 值选项：
  - `all`：全部用户
  - `ids`：指定用户
  - `attrs`：属性筛选
- `users.type` 为 `attrs` 时，字段含义：
  - `name` 字段：
    - `name`：名称
    - `username`：用户名
    - `email`：邮箱
    - `comment`：备注
    - `is_active`：激活状态
    - `is_first_login`：首次登录
    - `org_roles`：组织角色
    - `system_roles`：系统角色
    - `groups`：用户组
    - `labels`：标签
  - `match` 值选项：
    - `exact`：等于
    - `not`：不等于
    - `endswith`：以...结尾
    - `in`：在...中
    - `startswith`：以...开头
    - `m2m`：任意包含
    - `m2m_all`：同时包含
    - `regex`：正则匹配
  - 名称、用户名、邮箱、备注字段的 `match` 值选项有：
    - `exact`：等于
    - `not`：不等于
    - `endswith`：以...结尾
    - `in`：在...中
    - `startswith`：以...开头
    - `regex`：正则匹配
  - 系统角色、组织角色、用户组、标签字段的 `match` 值选项有：
    - `m2m`：任意包含
    - `m2m_all`：同时包含
  - 激活、首次登录字段的 `match` 值选项有：
    - `exact`：等于
    - `not`：不等于
  - 激活、首次登录字段的 `value` 只有 true、false
- `assets.type` 值选项：
  - `all`：全部资产
  - `ids`：指定资产
  - `attrs`：属性筛选
- `assets.type` 为 `attrs` 时，字段含义：
  - `name` 字段：
    - `name`：名称
    - `address`：地址
    - `nodes`：节点
    - `platform`：平台
    - `category`：类别
    - `type`：类型
    - `protocols`：协议
    - `labels`：标签
    - `comment`：备注
  - `match` 值选项：
    - `exact`：等于
    - `not`：不等于
    - `endswith`：以...结尾
    - `in`：在...中
    - `startswith`：以...开头
    - `m2m`：任意包含
    - `m2m_all`：同时包含
    - `regex`：正则匹配
  - 名称、地址、备注字段的 `match` 值选项有：
    - `exact`：等于
    - `not`：不等于
    - `endswith`：以...结尾
    - `in`：在...中
    - `startswith`：以...开头
    - `regex`：正则匹配
  - 节点、平台、标签字段的 `match` 值选项有：
    - `m2m`：任意包含
    - `m2m_all`：同时包含
  - 类别、类型、协议字段的 `match` 值选项有：
    - `exact`：等于
    - `not`：不等于
- `fields_pattern`：遮盖列名，默认值为`password`
- `masking_method`：遮盖方式
  - `fixed_char`：固定字符替换
    - `mask_pattern`：遮盖字符内容，只有当`masking_method`值为`fixed_char`时才需要配置`mask_pattern`内容，默认值为`######`
  - `hide_middle`：隐藏中间字符
  - `keep_prefix`：保留前缀
  - `keep_suffix`：保留后缀
