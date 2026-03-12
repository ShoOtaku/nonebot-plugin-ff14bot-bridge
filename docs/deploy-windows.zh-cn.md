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

## 2. 安装 WSL2（Windows 侧，详细步骤）

> 适用系统：Windows 11，或 Windows 10 2004+（内部版本号 19041 及以上）。

### 2.1 用管理员身份打开 PowerShell

1. 开始菜单搜索 `PowerShell`。
2. 右键“Windows PowerShell”。
3. 选择“以管理员身份运行”。

### 2.2 检查 WSL 状态（可选但推荐）

```powershell
wsl --status
```

如果提示找不到 `wsl`，先安装系统更新，再继续后续步骤。

### 2.3 安装 WSL 与 Ubuntu

```powershell
wsl --install -d Ubuntu-22.04
wsl --set-default-version 2
```

如果你的系统较旧、`wsl --install` 不可用，可改用兼容命令：

```powershell
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
```

执行后重启 Windows，再回到管理员 PowerShell 执行：

```powershell
wsl --set-default-version 2
wsl --install -d Ubuntu-22.04
```

### 2.4 首次初始化 Ubuntu

1. 重启后打开 `Ubuntu 22.04`。
2. 首次启动会提示创建 Linux 用户名与密码（与 Windows 账号无关）。
3. 完成后会进入 Ubuntu shell。

### 2.5 安装结果验证（必须做）

在 PowerShell 执行：

```powershell
wsl -l -v
```

确认 `Ubuntu-22.04` 一行中的 `VERSION` 为 `2`。  
如果不是 2，执行：

```powershell
wsl --set-version Ubuntu-22.04 2
```

在 Ubuntu 终端执行：

```bash
uname -r
cat /etc/os-release
```

看到内核版本与 Ubuntu 版本信息即可。

### 2.6 常见报错与修复

1. 报错 `0x80370102`：通常是 BIOS 没开虚拟化（Intel VT-x / AMD-V），开启后重试。
2. 报错“请启用 Virtual Machine Platform”：重新执行上面的 `dism.exe` 两条命令并重启。
3. `wsl -l -v` 里没有 Ubuntu：重新执行 `wsl --install -d Ubuntu-22.04`。
4. 首次打开 Ubuntu 卡住：先执行 `wsl --shutdown`，再重新打开 Ubuntu。

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
sudo mkdir -p /opt/nonebot-bot
sudo chown -R $USER:$USER /opt/nonebot-bot
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
HOST=0.0.0.0
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

说明：WSL2 内若 NapCat 使用 Docker，`HOST=0.0.0.0` 可让容器访问到 NoneBot。

## 6. 部署 NapCat（在 WSL2 内）

创建持久化目录：

```bash
sudo mkdir -p /opt/napcat/QQ
sudo mkdir -p /opt/napcat/config
sudo mkdir -p /opt/napcat/plugins
```

启动容器（把 `你的QQ号` 改成实际值）：

```bash
docker pull mlikiowa/napcat-docker:latest
docker run -d \
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

若拉取镜像时报 `connection reset by peer` / `failed to resolve reference`，先检查：

```bash
curl -I https://registry-1.docker.io/v2/
```

若你中断过拉取后出现 layer 校验/解压错误，可清理后重试：

```bash
docker rm -f napcat 2>/dev/null || true
docker image rm -f mlikiowa/napcat-docker:latest 2>/dev/null || true
docker builder prune -af
docker image prune -af
docker pull mlikiowa/napcat-docker:latest
```

查看 WebUI Token：

```bash
docker logs napcat --tail 100
```

Windows 浏览器访问：

```text
http://localhost:6099/webui
```

若无法打开，再在 WSL 查询 IP 后访问：

```bash
hostname -I
```

```text
http://<WSL的IP>:6099/webui
```

## 7. 配置 NapCat 反向 WS 到 NoneBot

在 NapCat WebUI 中启用 `Reverse WebSocket`，上报地址填写：

```text
ws://host.docker.internal:8080/onebot/v11/ws
```

连接类型请选择：`WebSocket 客户端（Reverse WS）`。  
消息格式请选择：`array`。

如果 NapCat 不是 Docker 部署，而是与 NoneBot 同机直接运行，可改回：

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

若 NapCat 日志报 `ECONNREFUSED ... host.docker.internal:8080`，先在 WSL 检查 NoneBot 监听：

```bash
ss -lntp | grep 8080
```

应看到 `0.0.0.0:8080`（或 `*:8080`）。若不是，请确认 `.env` 中 `HOST=0.0.0.0` 后重启 NoneBot。

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
   - Docker 部署 NapCat 时应配置为 `ws://host.docker.internal:8080/onebot/v11/ws`。
   - 并确认 NoneBot 监听为 `0.0.0.0:8080`。
4. 配了 Token 后连不上：
   - `ONEBOT_ACCESS_TOKEN` 两边必须完全一致。
