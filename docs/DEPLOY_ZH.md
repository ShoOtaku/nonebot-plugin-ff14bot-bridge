# 部署文档（中文）

本文档用于从零部署 `nonebot-plugin-ff14bot-bridge`，并通过 Nginx + HTTPS 对外提供桥接入口（含 WebSocket）。

## 1. 前置条件

- 已有 NoneBot2 项目（推荐 OneBot V11 适配器）
- Python 3.9+
- 一台有公网 IP 的 Linux 服务器
- 已解析域名，例如 `nb.example.com`

## 2. 安装插件

在 NoneBot 项目根目录执行：

```bash
pip install nonebot-plugin-ff14bot-bridge
```

并在 `bot.py` 或插件加载逻辑中添加：

```python
nonebot.load_plugin("nonebot_plugin_ff14bot_bridge")
```

## 3. 配置环境变量

复制 `.env.example` 到你的 `.env`，至少配置：

```env
FF14_BRIDGE_ENABLED=true
FF14_BRIDGE_CLIENTS_FILE=data/ff14_bridge/clients.json
FF14_BRIDGE_ALLOW_SELF_REGISTER=true
FF14_BRIDGE_PUBLIC_ENDPOINT=https://nb.example.com/ff14/bridge/ingest
FF14_BRIDGE_ADMIN_USERS=10001,10002
FF14_BRIDGE_WS_ENABLED=true
```

### 可选参数

- `FF14_BRIDGE_TIME_WINDOW_SECONDS`：时间窗，默认 60
- `FF14_BRIDGE_DEDUP_TTL_SECONDS`：去重缓存 TTL，默认 300
- `FF14_BRIDGE_RATE_LIMIT_PER_MINUTE`：每 Key 每分钟限流，默认 120
- `FF14_BRIDGE_DOWNLINK_QUEUE_SIZE`：下行队列长度，默认 100
- `FF14_BRIDGE_DOWNLINK_TTL_SECONDS`：下行消息保留秒数，默认 300
- `FF14_BRIDGE_DOWNLINK_MAX_LENGTH`：下行单条最大长度，默认 180
- `FF14_BRIDGE_PULL_RATE_LIMIT_PER_MINUTE`：每 Key 每分钟 pull 限流，默认 240
- `FF14_BRIDGE_WS_PING_INTERVAL_SECONDS`：WS ping 间隔秒数，默认 30
- `FF14_BRIDGE_WS_CLIENT_TIMEOUT_SECONDS`：WS 客户端 pong 超时秒数，默认 90
- `FF14_BRIDGE_WS_PUSH_BATCH_SIZE`：单次 WS 推送批量，默认 5
- `FF14_BRIDGE_WS_ACK_TIMEOUT_SECONDS`：ACK 超时后重推秒数，默认 15

## 4. Nginx 反代（HTTPS）

示例：将公网 `443` 反代到本机 NoneBot 的 `8080`。

```nginx
server {
    listen 80;
    server_name nb.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name nb.example.com;

    ssl_certificate /etc/letsencrypt/live/nb.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/nb.example.com/privkey.pem;

    location /ff14/bridge/ws {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

验证：

```bash
curl -i -X POST https://nb.example.com/ff14/bridge/ingest -d '{}'
```

返回 `401 invalid_key` 说明链路已经通了（只是鉴权未通过）。

## 5. 用户接入流程

1. 用户私聊机器人：`ff14bot register`
2. 机器人返回：
   - Endpoint
   - Bridge Key
   - Bridge Secret
3. 用户将这些值填入游戏端桥接配置
4. 游戏内触发消息后，机器人将收到并转发
5. QQ 输入 `ff14bot send 你好`，消息优先通过 WS 下发，WS 不可用时由 Pull 获取

## 6. 运维命令

- `ff14bot status`：查看统计
- `ff14bot rotate`：轮换当前用户 secret
- `ff14bot disable`：禁用当前用户桥接
- `ff14bot enable`：重新启用
- `ff14bot send <消息>`：下发到游戏
- `ff14bot list`：管理员查看全部客户端

## 7. 安全建议

- 始终使用 HTTPS 暴露接口
- 为 `/ff14/bridge/ws` 正确配置 Upgrade 头
- 定期轮换 Secret
- 监控 401、429、503 比例
- 建议仅允许 Nginx 暴露公网，NoneBot 监听本地回环或内网

此插件纯Vibe产物，请注意使用。
