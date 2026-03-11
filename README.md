# nonebot-plugin-ff14bot-bridge

FF14 聊天桥接插件（NoneBot2），支持多用户独立密钥管理与双向通信。  
游戏端上行走 HTTP，机器人下行优先 WebSocket，失败回退 Pull。

## 功能特性

- 多用户隔离：每个用户独立 `key + secret + target`
- 安全校验：HMAC-SHA256 + 时间窗 + 去重 + 限流
- 下行链路：WS push + ACK，异常自动回退 pull
- 自助命令：`ff14bot register/show/rotate/enable/disable/unregister/status/send`
- 管理员命令：`ff14bot list`

## 接口

- `POST /ff14/bridge/ingest`
- `POST /ff14/bridge/pull`
- `WS /ff14/bridge/ws`

## 安装

```bash
git clone https://github.com/ShoOtaku/nonebot-plugin-ff14bot-bridge.git
cd nonebot-plugin-ff14bot-bridge
pip install -e .
```

在 NoneBot 项目中启用：

```python
nonebot.load_plugin("nonebot_plugin_ff14bot_bridge")
```

## 环境变量

参考 [.env.example](./.env.example)。

核心参数：

- `FF14_BRIDGE_PUBLIC_ENDPOINT=https://your-domain/ff14/bridge/ingest`
- 本地无域名调试可用：`FF14_BRIDGE_PUBLIC_ENDPOINT=http://127.0.0.1:8080/ff14/bridge/ingest`
- `FF14_BRIDGE_WS_ENABLED=true`
- `FF14_BRIDGE_WS_PING_INTERVAL_SECONDS=30`
- `FF14_BRIDGE_WS_CLIENT_TIMEOUT_SECONDS=90`
- `FF14_BRIDGE_WS_PUSH_BATCH_SIZE=5`
- `FF14_BRIDGE_WS_ACK_TIMEOUT_SECONDS=15`

## 用户流程

1. 私聊机器人执行 `ff14bot register`
2. 拿到 Endpoint / Key / Secret
3. 填入卫月插件配置
4. 机器人下发 `ff14bot send <消息>` 时，游戏端优先通过 WS 收到

## 文档

- 详细部署文档：[docs/deploy.zh-cn.md](./docs/deploy.zh-cn.md)
- 新手复制版教程：[docs/deploy-beginner.zh-cn.md](./docs/deploy-beginner.zh-cn.md)
- NapCat 独立文档（可选）：[docs/deploy-napcat.zh-cn.md](./docs/deploy-napcat.zh-cn.md)
- Windows 部署教程（WSL2 + NoneBot + NapCat）：[docs/deploy-windows.zh-cn.md](./docs/deploy-windows.zh-cn.md)

## 测试

```bash
pip install -e .[test]
pytest -q
```
