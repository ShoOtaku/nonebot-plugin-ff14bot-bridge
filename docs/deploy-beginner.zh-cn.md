# NoneBot 新手部署教程（可复制执行）

本文档给新手准备，目标是“按顺序复制命令就能跑起来”。  
场景：Ubuntu/Debian Linux 服务器，部署 NoneBot2 + OneBot V11 适配器 + `nonebot-plugin-ff14bot-bridge`。

Windows 用户建议先安装 WSL2，然后在 WSL2 Ubuntu 里执行本文所有 `bash` 命令。

## 0. 你需要准备

1. 一台 Linux 服务器（推荐 Ubuntu 22.04+）。
2. 一个域名（例如 `nb.example.com`），并已解析到服务器 IP。
3. 一个可用 QQ 号（给协议端登录）。
4. 你可以用 `root` 或 sudo 用户登录服务器。

## 0.1 Windows 用户先做 WSL2 初始化（可选）

如果你是 Windows 10/11，请先在“管理员 PowerShell”执行：

```powershell
wsl --install -d Ubuntu-22.04
wsl --set-default-version 2
```

重启 Windows 后打开 Ubuntu，创建 Linux 用户。  
之后本文命令都在 Ubuntu 终端里执行，不在 PowerShell 里执行。

## 1. 登录服务器

远程 Linux 服务器：

```bash
ssh root@你的服务器IP
```

如果你是在本机 WSL2 Ubuntu 部署，可跳过 `ssh`，直接继续下一步。

## 2. 安装基础依赖

```bash
apt update
apt install -y python3 python3-venv python3-pip git curl nginx certbot python3-certbot-nginx
```

## 3. 创建项目目录与虚拟环境

```bash
mkdir -p /opt/nonebot-bot
cd /opt/nonebot-bot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip setuptools wheel
```

## 4. 安装 NoneBot 与插件

```bash
pip install "nonebot2[fastapi]" "nonebot-adapter-onebot" "git+https://github.com/ShoOtaku/nonebot-plugin-ff14bot-bridge.git"
```

说明：截至 2026-03-11，本插件尚未发布到 PyPI，不能直接使用 `pip install nonebot-plugin-ff14bot-bridge`。

## 5. 创建最小可运行 `bot.py`

把下面内容整段复制执行：

```bash
cat > /opt/nonebot-bot/bot.py <<'PY'
import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

nonebot.load_plugin("nonebot_plugin_ff14bot_bridge")

if __name__ == "__main__":
    nonebot.run()
PY
```

## 6. 写 `.env` 配置

先生成模板：

```bash
cat > /opt/nonebot-bot/.env <<'ENV'
HOST=127.0.0.1
PORT=8080

DRIVER=~fastapi

FF14_BRIDGE_ENABLED=true
FF14_BRIDGE_CLIENTS_FILE=data/ff14_bridge/clients.json
FF14_BRIDGE_ALLOW_SELF_REGISTER=true
FF14_BRIDGE_PUBLIC_ENDPOINT=https://nb.example.com/ff14/bridge/ingest
FF14_BRIDGE_ADMIN_USERS=123456
FF14_BRIDGE_WS_ENABLED=true
ENV
```

把域名替换为你的真实域名：

```bash
sed -i 's#nb.example.com#你的真实域名#g' /opt/nonebot-bot/.env
```

如果你要启用 OneBot Access Token，再追加：

```bash
echo 'ONEBOT_ACCESS_TOKEN=请替换成强密码' >> /opt/nonebot-bot/.env
```

## 7. 先前台运行一次（自检）

```bash
cd /opt/nonebot-bot
source .venv/bin/activate
python bot.py
```

看到类似 `Running on http://127.0.0.1:8080` 说明启动成功。  
按 `Ctrl + C` 退出，继续下一步。

## 8. 配置 systemd 开机自启

```bash
cat > /etc/systemd/system/nonebot.service <<'UNIT'
[Unit]
Description=NoneBot2 Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/nonebot-bot
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/nonebot-bot/.venv/bin/python /opt/nonebot-bot/bot.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
```

```bash
systemctl daemon-reload
systemctl enable nonebot
systemctl restart nonebot
systemctl status nonebot --no-pager
```

查看实时日志：

```bash
journalctl -u nonebot -f
```

## WSL2 说明（第 9~11 步）

如果你是在本机 WSL2 调试，且暂时不做公网接入，可以先跳过第 9~11 步（Nginx/HTTPS）。  
这时 `FF14_BRIDGE_PUBLIC_ENDPOINT` 可先用本地地址，后续需要公网时再补做 Nginx + 证书。

## 9. 配置 Nginx 反向代理

```bash
cat > /etc/nginx/conf.d/nonebot.conf <<'NGINX'
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
NGINX
```

替换域名：

```bash
sed -i 's#nb.example.com#你的真实域名#g' /etc/nginx/conf.d/nonebot.conf
```

## 10. 申请 HTTPS 证书并重载 Nginx

```bash
certbot --nginx -d 你的真实域名
nginx -t
systemctl reload nginx
```

## 11. 验证桥接接口是否可达

```bash
curl -i -X POST "https://你的真实域名/ff14/bridge/ingest" -d '{}'
```

返回 `401`（如 `invalid_key`）是正常的，说明接口链路打通了，只是鉴权没带正确 key/签名。

## 12. 对接 NapCat（协议端）

## 12.1 安装 Docker（已安装可跳过）

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
systemctl enable docker
systemctl start docker
docker --version
```

## 12.2 部署 NapCat 容器

创建持久化目录：

```bash
mkdir -p /opt/napcat/QQ
mkdir -p /opt/napcat/config
mkdir -p /opt/napcat/plugins
```

启动容器（把 `你的QQ号` 改成实际值）：

```bash
docker run -d \
  --name napcat \
  --restart=always \
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

查看日志并记录 WebUI Token：

```bash
docker logs napcat --tail 100
```

打开 WebUI：

```text
http://你的服务器IP:6099/webui
```

## 12.3 配置 NapCat 反向 WebSocket

在 WebUI 的 OneBot V11 网络设置中，启用 `Reverse WebSocket`，填入：

```text
ws://127.0.0.1:8080/onebot/v11/ws
```

如果你配置了 Access Token，也要同步到 NoneBot：

```bash
echo 'ONEBOT_ACCESS_TOKEN=和NapCat里一致的值' >> /opt/nonebot-bot/.env
systemctl restart nonebot
```

## 12.4 验证 NapCat 与 NoneBot 连通

查看双端日志：

```bash
journalctl -u nonebot -f
docker logs -f napcat
```

在 QQ 私聊机器人发送：

```text
ff14bot help
ff14bot register
ff14bot status
```

能正常返回即对接完成。

## 13. 最终验收清单

1. `systemctl status nonebot` 为 active。
2. `nginx -t` 通过。
3. `https://你的真实域名/ff14/bridge/ingest` 可访问。
4. QQ 私聊机器人执行 `ff14bot help` 能返回帮助。
5. 私聊执行 `ff14bot register` 能返回 `Bridge Key / Secret / Endpoint`。

## 14. 常见问题（新手高频）

1. 机器人没反应：先看 `journalctl -u nonebot -f`。
2. 证书申请失败：检查域名是否解析到本机，以及 80 端口是否放行。
3. `ff14bot register` 没返回：通常是协议端（NapCat）没连上 NoneBot。
4. 游戏端收不到下行：优先检查 `/ff14/bridge/ws` 的 Nginx Upgrade 配置是否正确。

