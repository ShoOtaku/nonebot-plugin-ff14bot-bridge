# NapCat 部署与对接 NoneBot 教程（新手版）

本文档聚焦 NapCat 协议端部署，并与 NoneBot2（OneBot V11）完成对接。  
推荐模式：**NapCat 反向 WebSocket -> NoneBot**（官方推荐连接方式之一）。

## 1. 官方参考

- NapCat 官方文档入口：<https://napneko.github.io/>
- NapCat Docker 仓库：<https://github.com/NapNeko/NapCat-Docker>
- NapCat 安装脚本仓库：<https://github.com/NapNeko/NapCat-Installer>
- NoneBot OneBot 连接配置：<https://github.com/nonebot/adapter-onebot/blob/master/website/docs/guide/setup.md>

## 2. 先决条件

1. 你已按 `docs/deploy-beginner.zh-cn.md` 启动 NoneBot。若 NapCat 用 Docker，建议 NoneBot 监听 `0.0.0.0:8080`。
2. 服务器已安装 Docker（若未安装，见下面命令）。
3. 你有可登录的 QQ 账号。

## 3. 安装 Docker（如已安装可跳过）

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo systemctl enable docker
sudo systemctl start docker
sudo docker --version
```

## 4. 使用 Docker 部署 NapCat（推荐）

## 4.1 创建持久化目录

```bash
sudo mkdir -p /opt/napcat/QQ
sudo mkdir -p /opt/napcat/config
sudo mkdir -p /opt/napcat/plugins
```

## 4.2 启动容器（反向 WS 模式）

把 `你的QQ号` 改成真实 QQ 号后执行：

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

如果拉取镜像时长时间停在 `Pulling fs layer`，通常是下载慢，可等待 5~20 分钟。  
若报 `connection reset by peer` / `failed to resolve reference`，先检查：

```bash
curl -I https://registry-1.docker.io/v2/
```

如果中断过下载，随后出现 `filesystem layer verification failed`、`unexpected EOF`、`failed to register layer`，可清理后重拉：

```bash
sudo docker rm -f napcat 2>/dev/null || true
sudo docker image rm -f mlikiowa/napcat-docker:latest 2>/dev/null || true
sudo docker builder prune -af
sudo docker image prune -af
sudo docker pull mlikiowa/napcat-docker:latest
```

查看容器状态：

```bash
sudo docker ps
```

查看日志（含 WebUI Token 信息）：

```bash
sudo docker logs napcat --tail 100
```

## 4.3 登录 NapCat WebUI

浏览器打开：

```text
http://你的服务器IP:6099/webui
```

若在 Windows 访问 WSL2 内 NapCat，也可先在 WSL 查询 IP：

```bash
hostname -I
```

再访问：

```text
http://<WSL的IP>:6099/webui
```

默认 Token 常见为 `napcat`，如不一致以日志/配置文件为准。  
首次登录后，请立即修改 Token 或相关安全配置。

## 5. 在 NapCat 中配置反向 WebSocket

在 WebUI 中找到 OneBot V11 的网络配置，启用 `Reverse WebSocket`，填入：

```text
ws://host.docker.internal:8080/onebot/v11/ws
```

连接类型请选择：`WebSocket 客户端（Reverse WS）`。  
消息格式请选择：`array`。

如果 NapCat 不是 Docker 部署，而是与 NoneBot 同机直接运行，可使用：

- `ws://127.0.0.1:8080/onebot/v11/`
- `ws://127.0.0.1:8080/onebot/v11/ws/`
- `ws://127.0.0.1:8080/onebot/v11/ws`

如果你在 NapCat 里配置了 Access Token，请在 NoneBot `.env` 中同步：

```dotenv
ONEBOT_ACCESS_TOKEN=和NapCat里一致的值
```

修改 `.env` 后重启 NoneBot：

```bash
sudo systemctl restart nonebot
```

如果日志出现 `ECONNREFUSED ... host.docker.internal:8080`（或 `172.x.x.x:8080`），通常是 NoneBot 仅监听了 `127.0.0.1`。可执行：

```bash
sed -i 's/^HOST=.*/HOST=0.0.0.0/' /opt/nonebot-bot/.env
sudo systemctl restart nonebot
sudo ss -lntp | grep 8080
```

## 6. 验证 NapCat 与 NoneBot 连通

## 6.1 看 NoneBot 日志

```bash
sudo journalctl -u nonebot -f
```

## 6.2 看 NapCat 日志

```bash
sudo docker logs -f napcat
```

## 6.3 机器人命令验证

在 QQ 私聊机器人发送：

```text
ff14bot help
ff14bot register
ff14bot status
```

能正常返回内容即说明连接成功。

## 7. 常用维护命令

重启 NapCat：

```bash
sudo docker restart napcat
```

更新 NapCat（拉新镜像并重建）：

```bash
sudo docker rm -f napcat
sudo docker pull mlikiowa/napcat-docker:latest
```

然后按第 4.2 节命令重新 `docker run` 一次。

备份数据：

```bash
sudo tar -czf /opt/napcat_backup_$(date +%F).tar.gz /opt/napcat
```

## 8. 另一种方式：官方安装脚本（可选）

如果你不想手动写 `docker run`，可使用官方安装器：

```bash
curl -o napcat.sh https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.sh
sudo bash napcat.sh --docker y --qq "你的QQ号" --mode reverse_ws --confirm
```

说明：

1. 这是 NapCat 官方安装器仓库提供的脚本方式。
2. 生产环境建议你先理解第 4 节再使用脚本，便于后续维护。

## 9. 常见问题排查

1. WebUI 打不开：检查 `6099` 端口防火墙与 `docker ps`。
2. 能登录 NapCat，但机器人无响应：检查反向 WS 地址是否为 `/onebot/v11/ws`。
3. 反向 WS 一直重连：Docker 部署时确认地址为 `ws://host.docker.internal:8080/onebot/v11/ws`，且 NoneBot 监听 `0.0.0.0:8080`。
4. 配了 Access Token 后连不上：`ONEBOT_ACCESS_TOKEN` 两边必须完全一致。
5. 重启后掉登录：确认已挂载 `/opt/napcat/QQ` 与 `/opt/napcat/config`。

