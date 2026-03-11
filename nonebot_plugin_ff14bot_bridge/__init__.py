from __future__ import annotations

import asyncio
import datetime as dt
import time

from fastapi import APIRouter, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from nonebot import get_driver, logger, on_command
from nonebot.adapters import Event, Message
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from pydantic import BaseModel, Field, ValidationError

from .config import Config
from .service import FF14BridgeService, IngestPayload

__plugin_meta__ = PluginMetadata(
    name="ff14_bridge",
    description="接收 FF14 本地聊天桥接消息并转发到机器人目标会话（多用户）",
    usage=(
        "/ff14bot help\n"
        "/ff14bot register\n"
        "/ff14bot show\n"
        "/ff14bot rotate\n"
        "/ff14bot enable|disable\n"
        "/ff14bot status\n"
        "/ff14bot send <消息>\n"
        "HTTP: /ff14/bridge/ingest, /ff14/bridge/pull\n"
        "WS: /ff14/bridge/ws"
    ),
    type="application",
)


class PullRequest(BaseModel):
    limit: int = Field(default=5, ge=1, le=20)


class WsAuthRequest(BaseModel):
    op: str = Field(default="auth")
    bridge_key: str = Field(min_length=1)
    timestamp: str = Field(min_length=1)
    nonce: str = Field(min_length=1)
    signature: str = Field(min_length=1)


def _model_validate(model_cls, raw):
    if hasattr(model_cls, "model_validate"):
        return model_cls.model_validate(raw)
    return model_cls.parse_obj(raw)


def _load_config() -> Config:
    driver = get_driver()
    raw = driver.config.dict() if hasattr(driver.config, "dict") else driver.config.model_dump()
    if hasattr(Config, "model_validate"):
        return Config.model_validate(raw)
    return Config.parse_obj(raw)


def _is_group_context(event: Event) -> bool:
    return getattr(event, "group_id", None) is not None


def _format_time(ts: float) -> str:
    if ts <= 0:
        return "无"
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


plugin_config = _load_config()
service = FF14BridgeService(plugin_config)
router = APIRouter()


@router.post("/ff14/bridge/ingest")
async def ingest_bridge_message(
    request: Request,
    x_bridge_key: str = Header(default=""),
    x_bridge_timestamp: str = Header(default=""),
    x_bridge_signature: str = Header(default=""),
) -> dict:
    if not plugin_config.ff14_bridge_enabled:
        raise HTTPException(status_code=503, detail="bridge_disabled")

    raw_body = await request.body()
    bridge_client = service.get_client_by_key(x_bridge_key)
    if bridge_client is None:
        service.mark_rejected("invalid_key")
        raise HTTPException(status_code=401, detail="invalid_key")

    if not service.check_timestamp(x_bridge_timestamp):
        service.mark_rejected("invalid_timestamp")
        raise HTTPException(status_code=401, detail="invalid_timestamp")

    if not service.verify_signature(raw_body, x_bridge_timestamp, x_bridge_signature, bridge_client.secret):
        service.mark_rejected("invalid_signature")
        raise HTTPException(status_code=401, detail="invalid_signature")

    try:
        if hasattr(IngestPayload, "model_validate_json"):
            payload = IngestPayload.model_validate_json(raw_body)
        else:
            payload = IngestPayload.parse_raw(raw_body)
    except ValidationError:
        service.mark_rejected("invalid_payload")
        raise HTTPException(status_code=400, detail="invalid_payload")

    duplicated = await service.check_and_mark_duplicate(bridge_client.bridge_key, payload.event_id)
    if duplicated:
        return {"ok": True, "accepted": True, "deduplicated": True, "message": "duplicate"}

    source_ip = request.client.host if request.client else "unknown"
    if not await service.check_rate_limit(bridge_client.bridge_key, source_ip):
        service.mark_rejected("rate_limited")
        raise HTTPException(status_code=429, detail="rate_limited")

    message_text = service.format_message(payload)
    success, reason = await service.send_to_target(
        text=message_text,
        target_type=bridge_client.target_type,
        target_id=bridge_client.target_id,
    )
    if not success:
        service.mark_rejected(reason)
        raise HTTPException(status_code=503, detail=reason)

    service.mark_accepted()
    return {"ok": True, "accepted": True, "deduplicated": False, "message": "queued"}


@router.post("/ff14/bridge/pull")
async def pull_bridge_command(
    request: Request,
    x_bridge_key: str = Header(default=""),
    x_bridge_timestamp: str = Header(default=""),
    x_bridge_signature: str = Header(default=""),
) -> dict:
    if not plugin_config.ff14_bridge_enabled:
        raise HTTPException(status_code=503, detail="bridge_disabled")

    raw_body = await request.body()
    if not raw_body:
        raw_body = b"{}"

    bridge_client = service.get_client_by_key(x_bridge_key)
    if bridge_client is None:
        service.mark_rejected("invalid_key")
        raise HTTPException(status_code=401, detail="invalid_key")

    if not service.check_timestamp(x_bridge_timestamp):
        service.mark_rejected("invalid_timestamp")
        raise HTTPException(status_code=401, detail="invalid_timestamp")

    if not service.verify_signature(raw_body, x_bridge_timestamp, x_bridge_signature, bridge_client.secret):
        service.mark_rejected("invalid_signature")
        raise HTTPException(status_code=401, detail="invalid_signature")

    try:
        if hasattr(PullRequest, "model_validate_json"):
            pull_request = PullRequest.model_validate_json(raw_body)
        else:
            pull_request = PullRequest.parse_raw(raw_body)
    except ValidationError:
        service.mark_rejected("invalid_pull_payload")
        raise HTTPException(status_code=400, detail="invalid_pull_payload")

    source_ip = request.client.host if request.client else "unknown"
    if not await service.check_pull_rate_limit(bridge_client.bridge_key, source_ip):
        service.mark_rejected("pull_rate_limited")
        raise HTTPException(status_code=429, detail="pull_rate_limited")

    messages = await service.dequeue_downlink(bridge_client.bridge_key, pull_request.limit)
    return {"ok": True, "count": len(messages), "messages": messages}


async def _safe_ws_close(websocket: WebSocket, code: int = 1000, reason: str = "") -> None:
    try:
        await websocket.close(code=code, reason=reason)
    except Exception:  # noqa: BLE001
        return


@router.websocket("/ff14/bridge/ws")
async def ws_bridge_command(websocket: WebSocket) -> None:
    bridge_key = ""
    ws_registered = False

    if not plugin_config.ff14_bridge_enabled or not plugin_config.ff14_bridge_ws_enabled:
        await _safe_ws_close(websocket, code=1008, reason="bridge_disabled")
        return

    await websocket.accept()

    try:
        raw_auth = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
        auth = _model_validate(WsAuthRequest, raw_auth)
        if (auth.op or "").strip().lower() != "auth":
            await _safe_ws_close(websocket, code=1008, reason="invalid_op")
            return

        bridge_key = auth.bridge_key.strip()
        bridge_client = service.get_client_by_key(bridge_key)
        if bridge_client is None:
            await _safe_ws_close(websocket, code=1008, reason="invalid_key")
            return

        if not service.check_timestamp(auth.timestamp):
            await _safe_ws_close(websocket, code=1008, reason="invalid_timestamp")
            return

        auth_body = service.build_ws_auth_body(bridge_key, auth.nonce)
        if not service.verify_signature(auth_body, auth.timestamp, auth.signature, bridge_client.secret):
            await _safe_ws_close(websocket, code=1008, reason="invalid_signature")
            return

        _, registered = await service.register_ws_client(bridge_key, websocket)
        if not registered:
            logger.warning(
                "[ff14_bridge] websocket duplicate rejected: "
                f"bridge_key={bridge_key}, reason=already_connected"
            )
            await _safe_ws_close(websocket, code=1013, reason="already_connected")
            return

        ws_registered = True

        await websocket.send_json({"op": "auth_ok", "ts": int(time.time())})
        await _run_ws_session(websocket, bridge_key)
    except WebSocketDisconnect:
        pass
    except asyncio.TimeoutError:
        await _safe_ws_close(websocket, code=1008, reason="auth_timeout")
    except ValidationError:
        await _safe_ws_close(websocket, code=1008, reason="invalid_auth_payload")
    except Exception as ex:  # noqa: BLE001
        logger.warning(f"[ff14_bridge] websocket session error: {ex}")
        await _safe_ws_close(websocket, code=1011, reason="internal_error")
    finally:
        if ws_registered and bridge_key:
            await service.unregister_ws_client(bridge_key, websocket)
            await service.requeue_pending_downlink(bridge_key)


async def _run_ws_session(websocket: WebSocket, bridge_key: str) -> None:
    ping_interval = max(plugin_config.ff14_bridge_ws_ping_interval_seconds, 5)
    client_timeout = max(plugin_config.ff14_bridge_ws_client_timeout_seconds, ping_interval + 5)
    push_batch = max(plugin_config.ff14_bridge_ws_push_batch_size, 1)

    next_ping_at = time.time() + ping_interval

    while True:
        outbound = await service.acquire_downlink_for_ws(bridge_key, push_batch)
        for item in outbound:
            await websocket.send_json({"op": "push", **item})

        now = time.time()
        if now >= next_ping_at:
            await websocket.send_json({"op": "ping", "ts": int(now)})
            next_ping_at = now + ping_interval

        last_pong = await service.get_ws_last_pong(bridge_key)
        if last_pong > 0 and now - last_pong > client_timeout:
            await _safe_ws_close(websocket, code=1001, reason="pong_timeout")
            return

        try:
            payload = await asyncio.wait_for(websocket.receive_json(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        except WebSocketDisconnect:
            return

        op = str(payload.get("op", "")).strip().lower() if isinstance(payload, dict) else ""
        if op == "ack":
            message_id = str(payload.get("message_id", "")).strip() if isinstance(payload, dict) else ""
            if message_id:
                await service.ack_downlink(bridge_key, message_id)
            continue

        if op == "pong":
            await service.touch_ws_pong(bridge_key)
            continue

        if op == "ping":
            await service.touch_ws_pong(bridge_key)
            await websocket.send_json({"op": "pong", "ts": int(time.time())})
            continue


driver = get_driver()
server_app = getattr(driver, "server_app", None)
if server_app is not None:
    server_app.include_router(router)
else:
    logger.warning("[ff14_bridge] 当前 driver 无 server_app，HTTP 路由未挂载")


ff14bot_command = on_command("ff14bot", priority=10, block=True)


@ff14bot_command.handle()
async def handle_ff14bot(event: Event, args: Message = CommandArg()) -> None:
    plain = args.extract_plain_text().strip()
    tokens = [token for token in plain.split() if token]
    action = tokens[0].lower() if tokens else "help"
    user_id = event.get_user_id()
    is_group = _is_group_context(event)

    sensitive_actions = {"register", "注册", "show", "配置", "rotate", "轮换"}
    if is_group and action in sensitive_actions:
        await ff14bot_command.finish("[ff14bot] 为避免泄露密钥，请私聊机器人执行该命令。")

    if action in {"help", "帮助", "h", "?"}:
        await ff14bot_command.finish(
            "\n".join(
                [
                    "[ff14bot] 命令帮助",
                    "ff14bot register  - 注册并生成个人桥接凭证",
                    "ff14bot show      - 查看个人凭证",
                    "ff14bot rotate    - 轮换个人密钥",
                    "ff14bot enable    - 启用个人桥接",
                    "ff14bot disable   - 禁用个人桥接",
                    "ff14bot unregister- 注销个人桥接",
                    "ff14bot status    - 查看桥接状态",
                    "ff14bot send xxx  - 下发消息到游戏(优先WS)",
                ]
            )
        )

    if action in {"status", "状态"}:
        stats = service.snapshot()
        own_client = service.get_user_client(user_id)
        own_queue_size = await service.get_user_downlink_queue_size(user_id)
        ws_online_clients = await service.get_ws_online_client_count()
        lines = [
            "[ff14bot] 状态",
            f"accepted: {stats.accepted}",
            f"rejected: {stats.rejected}",
            f"duplicated: {stats.duplicated}",
            f"registered_clients: {stats.registered_clients}",
            f"ws_online_clients: {ws_online_clients}",
            f"last_error: {stats.last_error or '无'}",
            f"last_accepted_at: {_format_time(stats.last_accepted_at)}",
        ]
        if own_client is not None:
            lines.extend(
                [
                    "---",
                    "你的桥接配置：",
                    f"bridge_key: {own_client.bridge_key}",
                    f"enabled: {own_client.enabled}",
                    f"target: {own_client.target_type}:{own_client.target_id}",
                    f"downlink_queue_size: {own_queue_size}",
                ]
            )
        else:
            lines.append("你的桥接配置：未注册（可执行 ff14bot register）")
        await ff14bot_command.finish("\n".join(lines))

    if action in {"register", "注册"}:
        if not plugin_config.ff14_bridge_allow_self_register and not service.is_admin(user_id):
            await ff14bot_command.finish("[ff14bot] 当前不允许自助注册，请联系管理员。")

        client, created = await service.register_user(user_id)
        action_text = "已创建新凭证" if created else "你已存在凭证，已直接返回"
        await ff14bot_command.finish(
            "\n".join(
                [
                    f"[ff14bot] {action_text}",
                    f"Endpoint: {service.get_public_endpoint()}",
                    f"Pull Endpoint: {service.get_public_pull_endpoint()}",
                    f"WebSocket Endpoint: {service.get_public_ws_endpoint()}",
                    f"Bridge Key: {client.bridge_key}",
                    f"Bridge Secret: {client.secret}",
                    f"Target: {client.target_type}:{client.target_id}",
                    "请将以上 Key/Secret 填入卫月端【远程聊天】配置。",
                ]
            )
        )

    if action in {"show", "配置"}:
        client = service.get_user_client(user_id)
        if client is None:
            await ff14bot_command.finish("[ff14bot] 你还没有桥接凭证，请先执行 ff14bot register。")
        await ff14bot_command.finish(
            "\n".join(
                [
                    "[ff14bot] 你的桥接凭证",
                    f"Endpoint: {service.get_public_endpoint()}",
                    f"Pull Endpoint: {service.get_public_pull_endpoint()}",
                    f"WebSocket Endpoint: {service.get_public_ws_endpoint()}",
                    f"Bridge Key: {client.bridge_key}",
                    f"Bridge Secret: {client.secret}",
                    f"Enabled: {client.enabled}",
                    f"Target: {client.target_type}:{client.target_id}",
                ]
            )
        )

    if action in {"rotate", "轮换"}:
        client = await service.rotate_user_secret(user_id)
        if client is None:
            await ff14bot_command.finish("[ff14bot] 你还没有桥接凭证，请先执行 ff14bot register。")
        await ff14bot_command.finish(
            "\n".join(
                [
                    "[ff14bot] 已轮换密钥",
                    f"Endpoint: {service.get_public_endpoint()}",
                    f"Pull Endpoint: {service.get_public_pull_endpoint()}",
                    f"WebSocket Endpoint: {service.get_public_ws_endpoint()}",
                    f"Bridge Key: {client.bridge_key}",
                    f"Bridge Secret: {client.secret}",
                    "请立即更新卫月端配置。",
                ]
            )
        )

    if action in {"send", "发送"}:
        message_text = plain[len(tokens[0]):].strip() if tokens else ""
        if not message_text:
            await ff14bot_command.finish("[ff14bot] 用法: ff14bot send 你好世界")

        success, reason, client = await service.enqueue_user_downlink(user_id, message_text)
        if not success:
            if reason == "no_registered_client":
                await ff14bot_command.finish("[ff14bot] 你还没有桥接凭证，请先执行 ff14bot register。")
            if reason == "client_disabled":
                await ff14bot_command.finish("[ff14bot] 你的桥接已禁用，请先执行 ff14bot enable。")
            if reason == "empty_message":
                await ff14bot_command.finish("[ff14bot] 消息为空，请重新输入。")
            await ff14bot_command.finish("[ff14bot] 下发失败，请稍后重试。")

        queue_size = await service.get_bridge_downlink_queue_size(client.bridge_key if client else "")
        await ff14bot_command.finish(f"[ff14bot] 已入队，等待游戏端 WS 推送或 Pull 拉取。当前待处理: {queue_size}")

    if action in {"enable", "启用"}:
        client = await service.set_user_enabled(user_id, True)
        if client is None:
            await ff14bot_command.finish("[ff14bot] 你还没有桥接凭证，请先执行 ff14bot register。")
        await ff14bot_command.finish(f"[ff14bot] 已启用桥接：{client.bridge_key}")

    if action in {"disable", "禁用"}:
        client = await service.set_user_enabled(user_id, False)
        if client is None:
            await ff14bot_command.finish("[ff14bot] 你还没有桥接凭证，请先执行 ff14bot register。")
        await ff14bot_command.finish(f"[ff14bot] 已禁用桥接：{client.bridge_key}")

    if action in {"unregister", "注销", "delete", "删除"}:
        removed = await service.remove_user(user_id)
        if not removed:
            await ff14bot_command.finish("[ff14bot] 你还没有桥接凭证。")
        await ff14bot_command.finish("[ff14bot] 已注销你的桥接凭证。")

    if action in {"list", "列表"}:
        if not service.is_admin(user_id):
            await ff14bot_command.finish("[ff14bot] 仅管理员可查看全量列表。")
        clients = service.list_clients()
        if not clients:
            await ff14bot_command.finish("[ff14bot] 当前没有已注册客户端。")
        lines = ["[ff14bot] 客户端列表"]
        for client in clients[:30]:
            lines.append(
                f"- {client.bridge_key} | owner={client.owner_user_id or '-'} | "
                f"target={client.target_type}:{client.target_id} | enabled={client.enabled}"
            )
        if len(clients) > 30:
            lines.append(f"... 共 {len(clients)} 个客户端，仅显示前 30 个")
        await ff14bot_command.finish("\n".join(lines))

    await ff14bot_command.finish("[ff14bot] 未知命令，输入 ff14bot help 查看帮助。")
