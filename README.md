# nonebot-plugin-ff14bot-bridge

FF14 本地聊天桥接插件（NoneBot2），支持多用户独立密钥管理。  
用户通过私聊机器人执行 `ff14bot` 命令注册自己的 `Bridge Key/Secret`，游戏端按个人凭证上报聊天消息。

## 功能特性

- 多用户隔离：每个用户独立 `key + secret + target`
- HMAC-SHA256 验签：防伪造、防篡改
- 时间窗校验：防重放
- 去重与限流：防刷屏、防重复消息
- 自助命令：`ff14bot register/show/rotate/enable/disable/unregister/status`
- 管理员列表：`ff14bot list`（仅管理员）

## 安装

从源码安装：

```bash
git clone https://github.com/<your-org>/nonebot-plugin-ff14bot-bridge.git
cd nonebot-plugin-ff14bot-bridge
pip install -e .
```

在 NoneBot 项目中启用插件：

```python
nonebot.load_plugin("nonebot_plugin_ff14bot_bridge")
```

## 环境变量

参考 [.env.example](./.env.example)。

核心变量：

- `FF14_BRIDGE_ENABLED=true`
- `FF14_BRIDGE_CLIENTS_FILE=data/ff14_bridge/clients.json`
- `FF14_BRIDGE_ALLOW_SELF_REGISTER=true`
- `FF14_BRIDGE_PUBLIC_ENDPOINT=https://your-domain/ff14/bridge/ingest`
- `FF14_BRIDGE_ADMIN_USERS=10001,10002`
- `FF14_BRIDGE_TIME_WINDOW_SECONDS=60`
- `FF14_BRIDGE_DEDUP_TTL_SECONDS=300`
- `FF14_BRIDGE_RATE_LIMIT_PER_MINUTE=120`

## 用户使用流程

1. 用户私聊机器人：`ff14bot register`
2. 机器人返回：
   - Endpoint
   - Bridge Key
   - Bridge Secret
3. 用户将以上参数填入游戏端插件
4. 游戏端上报成功后，机器人向该用户目标会话转发消息

## 命令说明

- `ff14bot help`
- `ff14bot register`
- `ff14bot show`
- `ff14bot rotate`
- `ff14bot enable`
- `ff14bot disable`
- `ff14bot unregister`
- `ff14bot status`
- `ff14bot list`（管理员）

## HTTP 接口

- `POST /ff14/bridge/ingest`

请求头：

- `X-Bridge-Key`
- `X-Bridge-Timestamp`
- `X-Bridge-Signature`

请求体字段：

- `event_id`
- `source`
- `chat_type`
- `player`
- `world`
- `content`
- `sent_at`

## 生产部署建议

- 必须通过 Nginx/Caddy 暴露 HTTPS
- 不要在公网直接暴露纯 HTTP 接口
- 使用 `ff14bot rotate` 定期轮换密钥
- 配置日志采集并监控 401/429/503

详见 [docs/DEPLOY_ZH.md](./docs/DEPLOY_ZH.md)。
