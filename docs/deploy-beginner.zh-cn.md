# NoneBot 新手部署教程（可复制执行）

本文档给新手准备，目标是“按顺序复制命令就能跑起来”。  
场景：Ubuntu/Debian Linux 服务器，部署 NoneBot2 + OneBot V11 适配器 + `nonebot-plugin-ff14bot-bridge`。

Windows 用户建议先安装 WSL2，然后在 WSL2 Ubuntu 里执行本文所有 `bash` 命令。

## 0. 你需要准备

1. 一台 Linux 服务器（推荐 Ubuntu 22.04+）。
2. 一个域名（例如 `nb.example.com`，仅公网 HTTPS 接入时需要）。
3. 一个可用 QQ 号（给协议端登录）。
4. 你可以用 `root` 或 sudo 用户登录服务器。

如果你没有域名、仅本机调试（如 WSL2 本地部署），可以继续按本文执行：把 `FF14_BRIDGE_PUBLIC_ENDPOINT` 设为本地地址，并跳过第 9~11 步（Nginx/HTTPS）。

## 0.1 Windows 用户先做 WSL2 初始化（可选）

如果你是 Windows 10/11，请先在“管理员 PowerShell”执行（详细版见 `docs/deploy-windows.zh-cn.md` 第 2 节）：

```powershell
wsl --install -d Ubuntu-22.04
wsl --set-default-version 2
```

若 `wsl --install` 不可用，先执行：

```powershell
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
```

然后重启，再执行前面的 `wsl` 命令。

安装完成后请验证：

```powershell
wsl -l -v
```

确认 `Ubuntu-22.04` 的 `VERSION` 为 `2`，否则执行：

```powershell
wsl --set-version Ubuntu-22.04 2
```

最后打开 Ubuntu，创建 Linux 用户。  
之后本文命令都在 Ubuntu 终端执行，不在 PowerShell 执行。

## 1. 登录服务器

远程 Linux 服务器：

```bash
ssh root@你的服务器IP
```

如果你是在本机 WSL2 Ubuntu 部署，可跳过 `ssh`，直接继续下一步。

## 2. 安装基础依赖

先确认当前是否 root（输出 `0` 表示 root）：

```bash
id -u
```

如果不是 root（WSL2 默认是普通用户），请使用 `sudo`：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git curl
```

仅当你需要“域名 + 公网 HTTPS”时，再额外安装：

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

如果你当前就是 root，可以把上面的 `sudo` 去掉后执行。

## 3. 创建项目目录与虚拟环境

```bash
sudo mkdir -p /opt/nonebot-bot
sudo chown -R $USER:$USER /opt/nonebot-bot
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
FF14_BRIDGE_PUBLIC_ENDPOINT=http://127.0.0.1:8080/ff14/bridge/ingest
FF14_BRIDGE_ADMIN_USERS=123456
FF14_BRIDGE_WS_ENABLED=true
ENV
```

如果你有域名并准备做公网 HTTPS，再改成：

```bash
sed -i 's#http://127.0.0.1:8080/ff14/bridge/ingest#https://你的真实域名/ff14/bridge/ingest#g' /opt/nonebot-bot/.env
```

如果你使用 Docker 部署 NapCat（第 12 步），建议把监听地址改为：

```bash
sed -i 's/^HOST=.*/HOST=0.0.0.0/' /opt/nonebot-bot/.env
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

注意：不要使用 `sudo cat > /etc/...`，重定向 `>` 仍由当前普通用户执行，会导致 `Permission denied`。请按下方 `sudo tee` 写入。

```bash
sudo tee /etc/systemd/system/nonebot.service > /dev/null <<'UNIT'
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
sudo systemctl daemon-reload
sudo systemctl enable nonebot
sudo systemctl restart nonebot
sudo systemctl status nonebot --no-pager
```

查看实时日志：

```bash
sudo journalctl -u nonebot -f
```

## WSL2 说明（第 9~11 步）

如果你是在本机 WSL2 调试，或无域名仅本地部署，可以先跳过第 9~11 步（Nginx/HTTPS）。  
这时 `FF14_BRIDGE_PUBLIC_ENDPOINT` 可先用本地地址，后续需要公网时再补做 Nginx + 证书。
如果你的 WSL 未启用 systemd（执行 `systemctl` 报错 `System has not been booted with systemd`），也先跳过第 8 步，改用前台运行或 `nohup` 临时启动。

## 9. 配置 Nginx 反向代理（仅有域名时需要）

```bash
sudo tee /etc/nginx/conf.d/nonebot.conf > /dev/null <<'NGINX'
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
sudo sed -i 's#nb.example.com#你的真实域名#g' /etc/nginx/conf.d/nonebot.conf
```

## 10. 申请 HTTPS 证书并重载 Nginx（仅有域名时需要）

```bash
sudo certbot --nginx -d 你的真实域名
sudo nginx -t
sudo systemctl reload nginx
```

## 11. 验证桥接接口是否可达

无域名、本地部署：

```bash
curl -i -X POST "http://127.0.0.1:8080/ff14/bridge/ingest" -d '{}'
```

有域名、HTTPS 部署：

```bash
curl -i -X POST "https://你的真实域名/ff14/bridge/ingest" -d '{}'
```

返回 `401`（如 `invalid_key`）是正常的，说明接口链路打通了，只是鉴权没带正确 key/签名。

## 12. 对接 NapCat（协议端）

## 12.1 安装 Docker（已安装可跳过）

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo systemctl enable docker
sudo systemctl start docker
sudo docker --version
```

## 12.2 部署 NapCat 容器

创建持久化目录：

```bash
sudo mkdir -p /opt/napcat/QQ
sudo mkdir -p /opt/napcat/config
sudo mkdir -p /opt/napcat/plugins
```

先拉取镜像（便于提前暴露网络问题）：

```bash
sudo docker pull mlikiowa/napcat-docker:latest
```

说明：首次拉取大镜像时，终端长时间停在 `Pulling fs layer` 可能只是下载慢（常见 5~20 分钟），不一定是死锁。

如果这里报错 `failed to resolve reference`、`connection reset by peer` 或超时，按下面处理后再重试：

```bash
curl -I https://registry-1.docker.io/v2/
```

若返回异常（连不上 Docker Hub），为 Docker 配置镜像加速地址（把 `你的镜像加速地址` 换成你可用的地址）：

```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json > /dev/null <<'JSON'
{
  "registry-mirrors": [
    "https://你的镜像加速地址"
  ]
}
JSON
sudo systemctl restart docker
```

然后再次执行：

```bash
sudo docker pull mlikiowa/napcat-docker:latest
```

如果长时间无进度（例如超过 10 分钟）可按 `Ctrl + C` 中断，然后依次执行：

```bash
curl -I https://registry-1.docker.io/v2/
sudo docker info
sudo systemctl restart docker
sudo docker pull mlikiowa/napcat-docker:latest
```

如果你中断过下载，随后出现 layer 校验/解压相关错误（如 `filesystem layer verification failed`、`unexpected EOF`、`failed to register layer`），可先清理再重拉：

```bash
sudo docker rm -f napcat 2>/dev/null || true
sudo docker image rm -f mlikiowa/napcat-docker:latest 2>/dev/null || true
sudo docker builder prune -af
sudo docker image prune -af
sudo systemctl restart docker
sudo docker pull mlikiowa/napcat-docker:latest
```

启动容器（把 `你的QQ号` 改成实际值）：

```bash
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

查看日志并记录 WebUI Token：

```bash
sudo docker logs napcat --tail 100
```

打开 WebUI：

```text
http://你的服务器IP:6099/webui
```

如果你在 Windows 访问 WSL2 内的 NapCat，可先在 WSL 查询 IP：

```bash
hostname -I
```

取第一个 IPv4 访问：

```text
http://<WSL的IP>:6099/webui
```

## 12.3 配置 NapCat 反向 WebSocket

在 WebUI 的 OneBot V11 网络设置中，启用 `Reverse WebSocket`，填入：

```text
ws://host.docker.internal:8080/onebot/v11/ws
```

连接类型请选择：`WebSocket 客户端（Reverse WS）`（不要选 WebSocket 服务器）。

消息格式请选择：`array`（推荐）。

说明：如果 NapCat 不是 Docker 部署，而是与 NoneBot 在同一台机器直接运行，再使用：

```text
ws://127.0.0.1:8080/onebot/v11/ws
```

如果日志出现 `ECONNREFUSED ... host.docker.internal:8080`（或 `172.x.x.x:8080`），通常是 NoneBot 仅监听了 `127.0.0.1`。请执行：

```bash
sed -i 's/^HOST=.*/HOST=0.0.0.0/' /opt/nonebot-bot/.env
sudo systemctl restart nonebot
sudo ss -lntp | grep 8080
```

`ss` 输出中看到 `0.0.0.0:8080`（或 `*:8080`）后，再让 NapCat 重连。

如果你配置了 Access Token，也要同步到 NoneBot：

```bash
echo 'ONEBOT_ACCESS_TOKEN=和NapCat里一致的值' >> /opt/nonebot-bot/.env
sudo systemctl restart nonebot
```

## 12.4 验证 NapCat 与 NoneBot 连通

查看双端日志：

```bash
sudo journalctl -u nonebot -f
sudo docker logs -f napcat
```

在 QQ 私聊机器人发送：

```text
ff14bot help
ff14bot register
ff14bot status
```

能正常返回即对接完成。

## 13. 最终验收清单

1. `sudo systemctl status nonebot` 为 active。
2. （有域名时）`sudo nginx -t` 通过。
3. 无域名时可访问 `http://127.0.0.1:8080/ff14/bridge/ingest`；有域名时可访问 `https://你的真实域名/ff14/bridge/ingest`。
4. QQ 私聊机器人执行 `ff14bot help` 能返回帮助。
5. 私聊执行 `ff14bot register` 能返回 `Bridge Key / Secret / Endpoint`。

## 14. 常见问题（新手高频）

1. 机器人没反应：先看 `sudo journalctl -u nonebot -f`。
2. （仅 HTTPS）证书申请失败：检查域名是否解析到本机，以及 80 端口是否放行。
3. `ff14bot register` 没返回：通常是协议端（NapCat）没连上 NoneBot。
4. 游戏端收不到下行：优先检查 `/ff14/bridge/ws` 的 Nginx Upgrade 配置是否正确。

