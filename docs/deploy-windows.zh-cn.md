# Windows 部署教程（WSL2 内部署 NoneBot + NapCat）

本文档推荐 Windows 用户使用 **WSL2（Ubuntu）** 部署。  
原因：运行环境与 Linux 生产环境一致，排障和迁移成本更低。

部署目标：

1. 在 Windows 安装 WSL2 + Ubuntu
2. 在 Ubuntu 内部署 NoneBot2 + `nonebot-plugin-ff14bot-bridge`
3. 在 Ubuntu 内用 Docker 部署 NapCat
4. 使用 NapCat 反向 WebSocket 对接 NoneBot

## 1. 官方参考

- NoneBot 快速开始：<https://nonebot.dev/docs/quick-start>
- NoneBot 配置说明：<https://nonebot.dev/docs/appendices/config>
- OneBot 连接配置：<https://github.com/nonebot/adapter-onebot/blob/master/website/docs/guide/setup.md>
- NapCat 官方文档：<https://napneko.github.io/>
- NapCat Docker 仓库：<https://github.com/NapNeko/NapCat-Docker>

## 2. 安装 WSL2（Windows 侧）

使用“管理员 PowerShell”执行：

```powershell
wsl --install -d Ubuntu-22.04
wsl --set-default-version 2
```

安装后重启 Windows，然后打开 Ubuntu 终端，按提示创建 Linux 用户名和密码。

## 3. 在 WSL2 启用 systemd（推荐）

在 Ubuntu 终端执行：

```bash
sudo tee /etc/wsl.conf >/dev/null <<'EOF'
[boot]
systemd=true
EOF
```

回到 PowerShell 执行：

```powershell
wsl --shutdown
```

然后重新打开 Ubuntu 终端继续后续步骤。

## 4. WSL2 内安装基础依赖

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git curl docker.io
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER
```

执行完 `usermod` 后，关闭并重新打开 Ubuntu 终端，再检查 Docker：

```bash
docker --version
docker ps
```

## 5. 部署 NoneBot（在 WSL2 内）

```bash
mkdir -p /opt/nonebot-bot
cd /opt/nonebot-bot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip setuptools wheel
pip install "nonebot2[fastapi]" "nonebot-adapter-onebot" "git+https://github.com/ShoOtaku/nonebot-plugin-ff14bot-bridge.git"
```

说明：截至 2026-03-11，本插件尚未发布到 PyPI，不能直接使用 `pip install nonebot-plugin-ff14bot-bridge`。

创建 `bot.py`：

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

创建 `.env`：

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

## 6. 部署 NapCat（在 WSL2 内）

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

查看 WebUI Token：

```bash
docker logs napcat --tail 100
```

Windows 浏览器访问：

```text
http://127.0.0.1:6099/webui
```

## 7. 配置 NapCat 反向 WS 到 NoneBot

在 NapCat WebUI 中启用 `Reverse WebSocket`，上报地址填写：

```text
ws://127.0.0.1:8080/onebot/v11/ws
```

如果启用了 Access Token，在 `/opt/nonebot-bot/.env` 追加同样值：

```dotenv
ONEBOT_ACCESS_TOKEN=和NapCat里一致的值
```

## 8. 启动与验证

启动 NoneBot：

```bash
cd /opt/nonebot-bot
source .venv/bin/activate
python bot.py
```

在另一个 Ubuntu 终端看 NapCat 日志：

```bash
docker logs -f napcat
```

QQ 私聊机器人执行：

```text
ff14bot help
ff14bot register
ff14bot status
```

接口连通性检查（可选）：

```bash
curl -i -X POST "http://127.0.0.1:8080/ff14/bridge/ingest" -d '{}'
```

返回 `401 invalid_key` 属于正常现象。

## 9. WSL2 注意事项（务必看）

1. WSL2 是 NAT 网络，公网访问需在 Windows 做额外端口转发/防火墙放行。
2. 仅本机调试时，`127.0.0.1` 通常可直接从 Windows 访问 WSL2 服务。
3. 如果你需要 24/7 生产常驻，建议优先独立 Linux 服务器。
4. 若需要 HTTPS 公网接入，请参考 Linux 文档配置 Nginx + Certbot：
   - `docs/deploy.zh-cn.md`

## 10. 常见问题排查

1. `docker ps` 权限报错：
   - 重新登录 Ubuntu 会话，确认用户已加入 docker 组。
2. NapCat WebUI 打不开：
   - 先看 `docker ps` 是否有 `0.0.0.0:6099->6099/tcp`。
3. `ff14bot` 无响应：
   - 检查 NapCat 是否配置为 `ws://127.0.0.1:8080/onebot/v11/ws`。
4. 配了 Token 后连不上：
   - `ONEBOT_ACCESS_TOKEN` 两边必须完全一致。
