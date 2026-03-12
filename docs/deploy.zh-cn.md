# NoneBot2 部署教程（详细版）

本文档面向“要上线可长期运行机器人”的场景，覆盖从零创建 NoneBot2 到部署 `nonebot-plugin-ff14bot-bridge` 的完整流程（开发机调试 + Linux 生产部署）。

## 快速入口

- 新手一步一步复制执行：[deploy-beginner.zh-cn.md](./deploy-beginner.zh-cn.md)
- NapCat 部署与对接：已整合在本文第 6 节
- Windows 部署（WSL2 + NoneBot + NapCat）：[deploy-windows.zh-cn.md](./deploy-windows.zh-cn.md)

## 1. 官方参考（建议先收藏）

以下链接来自 NoneBot 官方站点，可与本文配合阅读：

- 快速开始：<https://nonebot.dev/docs/quick-start>
- 创建机器人应用：<https://nonebot.dev/docs/tutorial/application>
- 配置说明：<https://nonebot.dev/docs/appendices/config>
- 生产部署最佳实践：<https://nonebot.dev/docs/best-practice/deployment>
- 适配器商店：<https://nonebot.dev/store/adapters>
- 驱动商店：<https://nonebot.dev/store/drivers>

## 2. 部署目标与架构

推荐生产架构如下：

1. QQ 协议端（如 NapCat / go-cqhttp）通过 OneBot V11 与 NoneBot 通信。
2. NoneBot 加载本插件后提供 3 个桥接接口：
   - `POST /ff14/bridge/ingest`
   - `POST /ff14/bridge/pull`
   - `WS /ff14/bridge/ws`
3. Nginx 暴露 `443`，统一反代到本地 NoneBot（如 `127.0.0.1:8080`）。
4. FF14 端只访问 HTTPS/WSS 公网域名，不直连内网端口。

如果你仅做本机调试（无域名、无公网接入），可暂时不走 Nginx/HTTPS，直接使用 `http://127.0.0.1:8080` 与 `ws://127.0.0.1:8080`。

## 3. 前置条件

## 3.1 软件与版本

- Linux 服务器（Ubuntu 22.04+ / Debian 12+）
- Python 3.9+
- Git
- 可用域名（例：`nb.example.com`，仅公网 HTTPS 接入时需要）
- OneBot V11 协议端（NapCat、go-cqhttp 等）

## 3.2 网络与端口建议

- 对外仅开放：
  - `80/tcp`（申请证书时可临时使用）
  - `443/tcp`
- NoneBot 监听 `127.0.0.1:8080`（不直接公网暴露；若 NapCat 用 Docker 反向 WS，可改为 `0.0.0.0:8080`）

无域名本地调试时，可不开放公网端口，仅本机访问 `127.0.0.1:8080`。

## 4. 从零创建 NoneBot2 项目（如你已有项目可跳过）

## 4.1 创建虚拟环境

```bash
mkdir -p /opt/nonebot-bot
cd /opt/nonebot-bot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip wheel setuptools
```

## 4.2 安装 nb-cli 并初始化项目

```bash
pip install -U nb-cli
nb create
```

执行 `nb create` 后按提示选择：

1. 机器人目录（建议当前目录）
2. 驱动（建议 FastAPI 驱动）
3. 适配器（此项目推荐 OneBot V11）

如果你是已有项目，也可直接安装依赖：

```bash
pip install "nonebot2[fastapi]" "nonebot-adapter-onebot"
```

## 5. 安装并启用本插件

在 NoneBot 项目根目录执行：

```bash
pip install "git+https://github.com/ShoOtaku/nonebot-plugin-ff14bot-bridge.git"
```

说明：截至 2026-03-11，本插件尚未发布到 PyPI，不能直接使用 `pip install nonebot-plugin-ff14bot-bridge`。

如果你已经把仓库克隆到本地，也可以在仓库目录执行：

```bash
pip install -e .
```

在 `bot.py`（或统一插件加载文件）中确保已加载：

```python
nonebot.load_plugin("nonebot_plugin_ff14bot_bridge")
```

## 6. 配置 OneBot V11 连接（核心）

本插件只是 NoneBot 插件，命令收发依赖 OneBot 适配器在线。推荐使用 NapCat 作为协议端，并用反向 WebSocket 对接 NoneBot。

## 6.1 部署 NapCat（Docker 推荐）

先安装 Docker（已安装可跳过）：

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo systemctl enable docker
sudo systemctl start docker
sudo docker --version
```

创建持久化目录：

```bash
sudo mkdir -p /opt/napcat/QQ
sudo mkdir -p /opt/napcat/config
sudo mkdir -p /opt/napcat/plugins
```

启动 NapCat 容器（把 `你的QQ号` 改成实际值）：

```bash
sudo docker pull mlikiowa/napcat-docker:latest
sudo docker run -d \
  --name napcat \
  --restart=always \
  --add-host=host.docker.internal:host-gateway \
  -e ACCOUNT=你的QQ号 \
  -e WSR_ENABLE=true \
  -e NAPCAT_UID=$(id -u) \
  -e NAPCAT_GID=$(id -g) \
  -p 6099:6099 \
  -v /opt/napcat/QQ:/app/.config/QQ \
  -v /opt/napcat/config:/app/napcat/config \
  -v /opt/napcat/plugins:/app/napcat/plugins \
  mlikiowa/napcat-docker:latest
```

若拉取镜像时停在 `Pulling fs layer`，通常只是下载慢；若报 `connection reset by peer`，先检查：

```bash
curl -I https://registry-1.docker.io/v2/
```

若中断过下载并出现 layer 校验/解压错误（如 `filesystem layer verification failed`、`unexpected EOF`、`failed to register layer`），可清理后重拉：

```bash
sudo docker rm -f napcat 2>/dev/null || true
sudo docker image rm -f mlikiowa/napcat-docker:latest 2>/dev/null || true
sudo docker builder prune -af
sudo docker image prune -af
sudo docker pull mlikiowa/napcat-docker:latest
```

查看日志（含 WebUI Token 信息）：

```bash
sudo docker logs napcat --tail 100
```

WebUI 默认地址：

```text
http://你的服务器IP:6099/webui
```

若在 Windows 访问 WSL2 内 NapCat，可先在 WSL 查询 IP：

```bash
hostname -I
```

然后访问 `http://<WSL的IP>:6099/webui`。

## 6.2 配置 NapCat 反向 WebSocket

在 NapCat WebUI 中，找到 OneBot V11 网络配置并启用 `Reverse WebSocket`，上报地址填写：

```text
ws://host.docker.internal:8080/onebot/v11/ws
```

连接类型请选择：`WebSocket 客户端（Reverse WS）`。  
消息格式请选择：`array`。

如果 NapCat 不是 Docker 部署，而是与 NoneBot 同机运行，可使用：

- `ws://127.0.0.1:8080/onebot/v11/`
- `ws://127.0.0.1:8080/onebot/v11/ws/`
- `ws://127.0.0.1:8080/onebot/v11/ws`

如果你在 NapCat 里启用了 Access Token，请在 NoneBot `.env` 同步：

```dotenv
ONEBOT_ACCESS_TOKEN=和NapCat里一致的值
```

## 6.3 连通性检查

完成配置后，检查以下三点：

1. 协议端与 NoneBot 连通（正向或反向 WebSocket 均可）。
2. NoneBot 收到消息事件后，机器人可响应任意测试命令。
3. 机器人具备向私聊/群发送消息的权限（插件下行依赖 `send_private_msg`/`send_group_msg`）。

常用检查命令：

```bash
sudo journalctl -u nonebot -f
sudo docker logs -f napcat
```

建议先完成“机器人可正常聊天回复”，再继续桥接部署。

## 7. 配置插件环境变量

复制示例文件：

```bash
cp .env.example .env
```

至少修改以下关键项（按你的场景和管理员 QQ）：

```env
FF14_BRIDGE_ENABLED=true
FF14_BRIDGE_CLIENTS_FILE=data/ff14_bridge/clients.json
FF14_BRIDGE_ALLOW_SELF_REGISTER=true
FF14_BRIDGE_PUBLIC_ENDPOINT=http://127.0.0.1:8080/ff14/bridge/ingest
FF14_BRIDGE_ADMIN_USERS=123456,10001
FF14_BRIDGE_WS_ENABLED=true
```

如果是公网 HTTPS 场景，再改成：

```env
FF14_BRIDGE_PUBLIC_ENDPOINT=https://你的真实域名/ff14/bridge/ingest
```

如果 NapCat 使用 Docker 反向 WS，建议在 `.env` 中设置：

```env
HOST=0.0.0.0
```

参数说明（与代码一致）：

- 鉴权与抗滥用：
  - `FF14_BRIDGE_TIME_WINDOW_SECONDS`（默认 60）
  - `FF14_BRIDGE_DEDUP_TTL_SECONDS`（默认 300）
  - `FF14_BRIDGE_RATE_LIMIT_PER_MINUTE`（默认 120）
- 下行消息队列：
  - `FF14_BRIDGE_DOWNLINK_QUEUE_SIZE`（默认 100）
  - `FF14_BRIDGE_DOWNLINK_TTL_SECONDS`（默认 300）
  - `FF14_BRIDGE_DOWNLINK_MAX_LENGTH`（默认 180）
  - `FF14_BRIDGE_PULL_RATE_LIMIT_PER_MINUTE`（默认 240）
- WebSocket：
  - `FF14_BRIDGE_WS_PING_INTERVAL_SECONDS`（默认 30）
  - `FF14_BRIDGE_WS_CLIENT_TIMEOUT_SECONDS`（默认 90）
  - `FF14_BRIDGE_WS_PUSH_BATCH_SIZE`（默认 5）
  - `FF14_BRIDGE_WS_ACK_TIMEOUT_SECONDS`（默认 15）

## 8. 本地启动与功能自检

## 8.1 启动

```bash
source .venv/bin/activate
python bot.py
```

## 8.2 命令链路检查

在 QQ 私聊机器人执行：

```text
ff14bot help
ff14bot register
ff14bot status
```

期望：

1. `register` 返回 `Endpoint / Pull Endpoint / WebSocket Endpoint / Bridge Key / Bridge Secret`
2. `status` 显示当前注册信息和统计

## 8.3 HTTP 接口通断检查

未带有效签名时，返回 `401 invalid_key` 是正常现象，说明路由已打通：

```bash
curl -i -X POST "http://127.0.0.1:8080/ff14/bridge/ingest" -d '{}'
```

## 8.4 NapCat 对接确认

在 QQ 私聊机器人执行：

```text
ff14bot help
ff14bot register
ff14bot status
```

命令返回正常即表示 NapCat 与 NoneBot 已正确对接。

## 9. 生产部署（systemd + Nginx + HTTPS）

如果你无域名、仅本地调试，可先完成 `9.1`，暂时跳过 `9.2` 与 `9.3`。

## 9.1 systemd 守护进程

创建 `/etc/systemd/system/nonebot.service`：

```ini
[Unit]
Description=NoneBot2 Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/nonebot-bot
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/nonebot-bot/.venv/bin/python bot.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

启用服务：

```bash
systemctl daemon-reload
systemctl enable nonebot
systemctl restart nonebot
systemctl status nonebot
```

查看日志：

```bash
journalctl -u nonebot -f
```

## 9.2 Nginx 反向代理（含 WS）

`/etc/nginx/conf.d/nonebot.conf` 示例：

```nginx
server {
    listen 80;
    server_name nb.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
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

测试并重载：

```bash
nginx -t
systemctl reload nginx
```

## 9.3 HTTPS 证书（Certbot）

```bash
apt update
apt install -y certbot python3-certbot-nginx
certbot --nginx -d nb.example.com
```

## 10. FF14 用户接入流程

1. 用户私聊机器人：`ff14bot register`
2. 机器人返回凭据：
   - `Bridge Key`
   - `Bridge Secret`
   - `Endpoint / Pull Endpoint / WebSocket Endpoint`
3. 用户将凭据填入游戏端桥接配置。
4. 游戏消息通过 `ingest` 上行到 QQ。
5. QQ `ff14bot send 你好` 下行到游戏端（优先 WS，失败回退 Pull）。

## 11. 常用运维命令

- `ff14bot status`：查看统计与个人状态
- `ff14bot rotate`：轮换当前用户 secret
- `ff14bot disable`：禁用当前用户桥接
- `ff14bot enable`：重新启用
- `ff14bot unregister`：注销当前用户桥接
- `ff14bot send <消息>`：向游戏下发
- `ff14bot list`：管理员查看全量客户端

## 12. 故障排查清单

## 12.1 `401 invalid_key`

- 游戏端 `Bridge Key` 填错
- 请求头未按协议附带签名
- 该用户桥接被禁用

## 12.2 `401 invalid_timestamp`

- 服务器时间漂移
- 游戏端与服务器时间差超过 `FF14_BRIDGE_TIME_WINDOW_SECONDS`

建议开启 NTP（`chrony`/`systemd-timesyncd`）。

## 12.3 `401 invalid_signature`

- Secret 不一致
- 签名算法或拼接顺序错误（应为 `timestamp + "." + raw_body` 的 HMAC-SHA256）

## 12.4 `429 rate_limited` / `pull_rate_limited`

- 上行/拉取频率超限
- 临时调高限流参数，并排查客户端重试风暴

## 12.5 `503 bridge_disabled` 或消息发送失败

- `FF14_BRIDGE_ENABLED=false`
- OneBot 机器人不在线或无发消息权限
- 目标会话 ID 无效

## 12.6 NapCat 反向 WS 报 `ECONNREFUSED ... host.docker.internal:8080`

- NoneBot 仅监听了 `127.0.0.1`
- NapCat（Docker）应使用 `ws://host.docker.internal:8080/onebot/v11/ws`

可执行：

```bash
sed -i 's/^HOST=.*/HOST=0.0.0.0/' .env
sudo systemctl restart nonebot
sudo ss -lntp | grep 8080
```

## 13. 安全与备份建议

1. 仅对公网暴露 Nginx，NoneBot 绑定内网地址。
2. 强制 HTTPS/WSS，不要明文 HTTP 外网传输。
3. 定期轮换 secret（管理员可要求周期轮换）。
4. 备份 `data/ff14_bridge/clients.json`（包含用户桥接状态与密钥）。
5. 监控 `401/429/503` 比例并设置告警阈值。

## 14. 升级与回滚建议

## 14.1 升级

```bash
source .venv/bin/activate
pip install -U "git+https://github.com/ShoOtaku/nonebot-plugin-ff14bot-bridge.git@main"
systemctl restart nonebot
```

## 14.2 回滚

```bash
source .venv/bin/activate
pip install "git+https://github.com/ShoOtaku/nonebot-plugin-ff14bot-bridge.git@<commit_or_tag>"
systemctl restart nonebot
```

升级前建议先备份：

- `.env`
- `data/ff14_bridge/clients.json`

## 15. 最终验收（上线前 5 分钟检查）

1. `systemctl status nonebot` 为 active。
2. （公网 HTTPS 场景）`nginx -t` 通过且 `systemctl status nginx` 正常。
3. 无域名本地调试时：`http://127.0.0.1:8080/ff14/bridge/ingest` 可访问（无 key 时返回 401）。
4. 公网 HTTPS 场景时：`https://你的真实域名/ff14/bridge/ingest` 可访问（无 key 时返回 401）。
5. 机器人私聊命令 `ff14bot register/status/send` 全部可用。
6. 游戏端能收到 QQ 下行消息，且 WS 断开后 Pull 回退正常。
