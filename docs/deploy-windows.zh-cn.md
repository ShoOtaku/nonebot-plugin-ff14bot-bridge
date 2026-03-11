# Windows 部署教程（NoneBot + NapCat）

本文档面向 Windows 10/11 新手，目标是从零部署：

1. NoneBot2（OneBot V11 适配器）
2. `nonebot-plugin-ff14bot-bridge`
3. NapCat 协议端
4. NapCat 反向 WebSocket 对接 NoneBot

## 1. 官方参考

- NoneBot 快速开始：<https://nonebot.dev/docs/quick-start>
- NoneBot 配置说明：<https://nonebot.dev/docs/appendices/config>
- OneBot 连接配置：<https://github.com/nonebot/adapter-onebot/blob/master/website/docs/guide/setup.md>
- NapCat 官方文档：<https://napneko.github.io/>
- NapCat 安装器仓库：<https://github.com/NapNeko/NapCat-Installer>

## 2. 环境准备（PowerShell）

建议使用“以管理员身份运行”的 PowerShell。

安装 Python 与 Git（若已安装可跳过）：

```powershell
winget install -e --id Python.Python.3.12
winget install -e --id Git.Git
```

允许当前用户运行本地脚本（仅需执行一次）：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 3. 创建 NoneBot 项目目录

```powershell
New-Item -ItemType Directory -Path "C:\bot\nonebot-bot" -Force | Out-Null
Set-Location "C:\bot\nonebot-bot"
```

创建虚拟环境并激活：

```powershell
py -3 -m venv ".venv"
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip setuptools wheel
```

## 4. 安装 NoneBot 与桥接插件

```powershell
pip install "nonebot2[fastapi]" "nonebot-adapter-onebot" nonebot-plugin-ff14bot-bridge
```

## 5. 创建最小可运行 `bot.py`

```powershell
@'
import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

nonebot.load_plugin("nonebot_plugin_ff14bot_bridge")

if __name__ == "__main__":
    nonebot.run()
'@ | Set-Content -Path "C:\bot\nonebot-bot\bot.py" -Encoding UTF8
```

## 6. 创建 `.env`

先写一份可本地跑通的配置：

```powershell
@'
HOST=127.0.0.1
PORT=8080
DRIVER=~fastapi

FF14_BRIDGE_ENABLED=true
FF14_BRIDGE_CLIENTS_FILE=data/ff14_bridge/clients.json
FF14_BRIDGE_ALLOW_SELF_REGISTER=true
FF14_BRIDGE_PUBLIC_ENDPOINT=http://127.0.0.1:8080/ff14/bridge/ingest
FF14_BRIDGE_ADMIN_USERS=123456
FF14_BRIDGE_WS_ENABLED=true
'@ | Set-Content -Path "C:\bot\nonebot-bot\.env" -Encoding UTF8
```

如果你已经有公网域名和 HTTPS 反代，把 `FF14_BRIDGE_PUBLIC_ENDPOINT` 改成：

```text
https://你的域名/ff14/bridge/ingest
```

## 7. 启动 NoneBot（测试）

```powershell
Set-Location "C:\bot\nonebot-bot"
.\.venv\Scripts\Activate.ps1
python .\bot.py
```

看到监听 `127.0.0.1:8080` 即成功。先不要关闭这个窗口，继续安装 NapCat。

## 8. 安装 NapCat（Windows 官方安装器）

在新开的“管理员 PowerShell”中执行：

```powershell
curl -o install.ps1 https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.ps1
powershell -ExecutionPolicy ByPass -File .\install.ps1 -verb runas
```

按安装器提示完成安装并登录 QQ。

## 9. 配置 NapCat 对接 NoneBot

打开 NapCat WebUI（通常安装后会提示地址），配置 OneBot V11：

1. 启用 `Reverse WebSocket`
2. 上报地址填写：
   - `ws://127.0.0.1:8080/onebot/v11/ws`
3. 如果你配置了 Access Token，则 NoneBot `.env` 里也要加同样值：

```dotenv
ONEBOT_ACCESS_TOKEN=和NapCat里完全一致
```

若刚改过 `.env`，重启 NoneBot：

```powershell
Set-Location "C:\bot\nonebot-bot"
.\.venv\Scripts\Activate.ps1
python .\bot.py
```

## 10. 功能验证

在 QQ 私聊机器人发送：

```text
ff14bot help
ff14bot register
ff14bot status
```

期望：

1. `help` 返回命令列表
2. `register` 返回 `Bridge Key / Bridge Secret / Endpoint`
3. `status` 显示桥接统计和个人状态

接口连通性检查（可选）：

```powershell
curl.exe -i -X POST "http://127.0.0.1:8080/ff14/bridge/ingest" -d "{}"
```

返回 `401 invalid_key` 属于正常，说明接口已可达。

## 11. 开机自动启动（NoneBot）

下面命令会创建一个“系统启动时运行”的计划任务：

```powershell
schtasks /Create /TN "NoneBotBridge" /SC ONSTART /RU SYSTEM /TR "cmd /c cd /d C:\bot\nonebot-bot && C:\bot\nonebot-bot\.venv\Scripts\python.exe bot.py" /F
```

手动触发一次：

```powershell
schtasks /Run /TN "NoneBotBridge"
```

删除任务（如需要）：

```powershell
schtasks /Delete /TN "NoneBotBridge" /F
```

## 12. 重要说明（NapCat 在 Windows）

1. NapCat 依赖 QQ 登录态与桌面会话，通常需要用户会话环境。
2. 仅把 NoneBot 做成系统任务不等于 NapCat 也完全后台可用。
3. 建议服务器长期在线场景优先 Linux（文档：`docs/deploy.zh-cn.md`）。

## 13. 常见问题排查

1. `ff14bot` 没响应：
   - 先确认 NapCat 已连接到 `ws://127.0.0.1:8080/onebot/v11/ws`
2. PowerShell 无法执行脚本：
   - 执行 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
3. 端口冲突：
   - 检查 `8080` 是否被占用，必要时改 `.env` 的 `PORT`
4. 配了 Token 后连不上：
   - `ONEBOT_ACCESS_TOKEN` 两边必须完全一致
5. 想公网接入 FF14：
   - 需要额外配置 HTTPS 反代，并把 `FF14_BRIDGE_PUBLIC_ENDPOINT` 改成公网地址

