from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, Dict, Optional, Tuple

from nonebot import get_bots, logger
from pydantic import BaseModel, Field

from .config import Config


class IngestPayload(BaseModel):
    event_id: str = Field(min_length=1)
    source: str = Field(default="xsztoolbox")
    chat_type: str = Field(default="")
    player: str = Field(default="")
    world: str = Field(default="")
    content: str = Field(min_length=1)
    sent_at: str = Field(default="")


class BridgeClient(BaseModel):
    bridge_key: str = Field(min_length=1)
    secret: str = Field(min_length=1)
    target_type: str = Field(default="private")
    target_id: str = Field(default="")
    owner_user_id: str = Field(default="")
    enabled: bool = Field(default=True)
    created_at: int = Field(default=0)
    updated_at: int = Field(default=0)


@dataclass
class BridgeStats:
    accepted: int = 0
    rejected: int = 0
    duplicated: int = 0
    last_error: str = ""
    last_accepted_at: float = 0.0
    registered_clients: int = 0


class FF14BridgeService:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.stats = BridgeStats()
        self._dedup_cache: Dict[str, float] = {}
        self._rate_cache: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()
        self._clients_lock = asyncio.Lock()

        self._clients_path = Path((config.ff14_bridge_clients_file or "data/ff14_bridge/clients.json").strip())
        self._clients_by_key: Dict[str, BridgeClient] = {}
        self._admin_users = self._parse_admin_users(config.ff14_bridge_admin_users)
        self._load_clients_from_disk()

    @staticmethod
    def _parse_admin_users(raw: object) -> set[str]:
        if raw is None:
            return set()
        normalized = str(raw).strip()
        if not normalized:
            return set()
        normalized = normalized.replace(";", ",").replace("\n", ",")
        return {item.strip() for item in normalized.split(",") if item.strip()}

    @staticmethod
    def _model_validate(model_cls, raw):
        if hasattr(model_cls, "model_validate"):
            return model_cls.model_validate(raw)
        return model_cls.parse_obj(raw)

    @staticmethod
    def _model_dump(model_obj) -> dict:
        if hasattr(model_obj, "model_dump"):
            return model_obj.model_dump()
        return model_obj.dict()

    def _load_clients_from_disk(self) -> None:
        self._clients_by_key = {}

        if self._clients_path.exists():
            try:
                payload = json.loads(self._clients_path.read_text(encoding="utf-8"))
                self._load_clients_from_payload(payload)
            except Exception as ex:  # noqa: BLE001
                logger.warning(f"[ff14_bridge] 读取 clients 文件失败: {ex}")

        if not self._clients_by_key:
            migrated = self._migrate_legacy_single_client()
            if not migrated:
                logger.info("[ff14_bridge] 当前无已注册客户端，可使用 ff14bot register 创建")

    def _load_clients_from_payload(self, payload: object) -> None:
        raw_clients = payload
        if isinstance(payload, dict) and "clients" in payload:
            raw_clients = payload.get("clients")

        if isinstance(raw_clients, dict):
            iterable = raw_clients.items()
        elif isinstance(raw_clients, list):
            iterable = []
            for item in raw_clients:
                if isinstance(item, dict):
                    key = str(item.get("bridge_key", "")).strip()
                    iterable.append((key, item))
        else:
            iterable = []

        loaded = 0
        for key_hint, raw in iterable:
            if not isinstance(raw, dict):
                continue

            raw_copy = dict(raw)
            key = str(raw_copy.get("bridge_key") or key_hint or "").strip()
            if not key:
                continue
            raw_copy["bridge_key"] = key

            try:
                client = self._model_validate(BridgeClient, raw_copy)
            except Exception:  # noqa: BLE001
                logger.warning(f"[ff14_bridge] 跳过无效 client 配置: {key}")
                continue

            normalized = self._normalize_client(client)
            if not normalized.secret:
                logger.warning(f"[ff14_bridge] client 缺少 secret，已跳过: {key}")
                continue

            self._clients_by_key[normalized.bridge_key] = normalized
            loaded += 1

        if loaded > 0:
            logger.info(f"[ff14_bridge] 已加载 {loaded} 个桥接客户端")

    def _normalize_client(self, client: BridgeClient) -> BridgeClient:
        now = int(time.time())
        client.bridge_key = (client.bridge_key or "").strip()
        client.secret = (client.secret or "").strip()
        client.target_type = (client.target_type or "private").strip().lower()
        client.target_id = str(client.target_id or "").strip()
        client.owner_user_id = str(client.owner_user_id or "").strip()
        if client.target_type not in {"private", "group"}:
            client.target_type = "private"
        if client.created_at <= 0:
            client.created_at = now
        if client.updated_at <= 0:
            client.updated_at = now
        return client

    def _migrate_legacy_single_client(self) -> bool:
        key = (self.config.ff14_bridge_key or "").strip()
        secret = (self.config.ff14_bridge_secret or "").strip()
        target_type = (self.config.ff14_bridge_target_type or "private").strip().lower()
        target_id = str(self.config.ff14_bridge_target_id or "").strip()
        if not key or not secret or not target_id:
            return False

        if target_type not in {"private", "group"}:
            target_type = "private"

        now = int(time.time())
        owner_user_id = target_id if target_type == "private" else ""
        self._clients_by_key[key] = BridgeClient(
            bridge_key=key,
            secret=secret,
            target_type=target_type,
            target_id=target_id,
            owner_user_id=owner_user_id,
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        self._save_clients_to_disk()
        logger.info(f"[ff14_bridge] 已迁移旧版单客户端配置，bridge_key={key}")
        return True

    def _save_clients_to_disk(self) -> None:
        self._clients_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "clients": {
                key: self._model_dump(client)
                for key, client in sorted(self._clients_by_key.items(), key=lambda item: item[0])
            },
        }
        self._clients_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def is_admin(self, user_id: str) -> bool:
        return str(user_id).strip() in self._admin_users

    def get_public_endpoint(self) -> str:
        endpoint = (self.config.ff14_bridge_public_endpoint or "").strip()
        if endpoint:
            return endpoint
        return "http://127.0.0.1:8080/ff14/bridge/ingest"

    def get_client_by_key(self, bridge_key: str) -> Optional[BridgeClient]:
        key = (bridge_key or "").strip()
        if not key:
            return None
        client = self._clients_by_key.get(key)
        if client is None or not client.enabled:
            return None
        return client

    def get_user_client(self, user_id: str) -> Optional[BridgeClient]:
        owner = str(user_id).strip()
        if not owner:
            return None
        for client in self._clients_by_key.values():
            if client.owner_user_id == owner:
                return client
        return None

    def list_clients(self) -> list[BridgeClient]:
        return sorted(self._clients_by_key.values(), key=lambda item: item.created_at, reverse=True)

    async def register_user(self, user_id: str) -> Tuple[BridgeClient, bool]:
        owner = str(user_id).strip()
        now = int(time.time())
        async with self._clients_lock:
            existing = self.get_user_client(owner)
            if existing is not None:
                if not existing.enabled:
                    existing.enabled = True
                    existing.updated_at = now
                    self._save_clients_to_disk()
                return existing, False

            bridge_key = self._generate_unique_bridge_key()
            secret = self._generate_secret()
            client = BridgeClient(
                bridge_key=bridge_key,
                secret=secret,
                target_type="private",
                target_id=owner,
                owner_user_id=owner,
                enabled=True,
                created_at=now,
                updated_at=now,
            )
            self._clients_by_key[bridge_key] = client
            self._save_clients_to_disk()
            return client, True

    async def rotate_user_secret(self, user_id: str) -> Optional[BridgeClient]:
        owner = str(user_id).strip()
        now = int(time.time())
        async with self._clients_lock:
            existing = self.get_user_client(owner)
            if existing is None:
                return None
            existing.secret = self._generate_secret()
            existing.updated_at = now
            self._save_clients_to_disk()
            return existing

    async def set_user_enabled(self, user_id: str, enabled: bool) -> Optional[BridgeClient]:
        owner = str(user_id).strip()
        now = int(time.time())
        async with self._clients_lock:
            existing = self.get_user_client(owner)
            if existing is None:
                return None
            existing.enabled = enabled
            existing.updated_at = now
            self._save_clients_to_disk()
            return existing

    async def remove_user(self, user_id: str) -> bool:
        owner = str(user_id).strip()
        async with self._clients_lock:
            target_key = None
            for key, client in self._clients_by_key.items():
                if client.owner_user_id == owner:
                    target_key = key
                    break
            if not target_key:
                return False
            self._clients_by_key.pop(target_key, None)
            self._save_clients_to_disk()
            return True

    async def set_user_target(self, user_id: str, target_type: str, target_id: str) -> Optional[BridgeClient]:
        owner = str(user_id).strip()
        normalized_type = (target_type or "").strip().lower()
        normalized_id = str(target_id or "").strip()
        if normalized_type not in {"private", "group"} or not normalized_id:
            return None

        now = int(time.time())
        async with self._clients_lock:
            existing = self.get_user_client(owner)
            if existing is None:
                return None
            existing.target_type = normalized_type
            existing.target_id = normalized_id
            existing.updated_at = now
            self._save_clients_to_disk()
            return existing

    @staticmethod
    def _generate_secret() -> str:
        return secrets.token_hex(32)

    def _generate_unique_bridge_key(self) -> str:
        for _ in range(16):
            key = f"ff14_{secrets.token_hex(6)}"
            if key not in self._clients_by_key:
                return key
        return f"ff14_{secrets.token_hex(8)}"

    def check_timestamp(self, timestamp: str) -> bool:
        try:
            ts = int(timestamp)
        except (TypeError, ValueError):
            return False

        now = int(time.time())
        return abs(now - ts) <= max(self.config.ff14_bridge_time_window_seconds, 1)

    def verify_signature(self, raw_body: bytes, timestamp: str, signature: str, secret: str) -> bool:
        if not signature or not secret:
            return False

        payload = timestamp.encode("utf-8") + b"." + raw_body
        expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature.strip().lower(), expected.lower())

    async def check_and_mark_duplicate(self, bridge_key: str, event_id: str) -> bool:
        now = time.time()
        ttl = max(self.config.ff14_bridge_dedup_ttl_seconds, 1)
        dedup_key = f"{bridge_key}:{event_id}"

        async with self._lock:
            self._cleanup_dedup(now, ttl)
            if dedup_key in self._dedup_cache:
                self.stats.duplicated += 1
                return True
            self._dedup_cache[dedup_key] = now
            return False

    async def check_rate_limit(self, bridge_key: str, source_ip: str) -> bool:
        now = time.time()
        key = f"{bridge_key}:{source_ip}"
        limit = max(self.config.ff14_bridge_rate_limit_per_minute, 1)
        window_seconds = 60.0

        async with self._lock:
            queue = self._rate_cache[key]
            while queue and now - queue[0] > window_seconds:
                queue.popleft()
            if len(queue) >= limit:
                return False
            queue.append(now)
            return True

    def format_message(self, payload: IngestPayload) -> str:
        sent_at = payload.sent_at or time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        return (
            f"[FF14桥接] {payload.chat_type}\n"
            f"玩家: {payload.player}@{payload.world}\n"
            f"时间: {sent_at}\n"
            f"内容: {payload.content}"
        )

    async def send_to_target(self, text: str, target_type: str, target_id: str) -> Tuple[bool, str]:
        bots = get_bots()
        if not bots:
            return False, "no_bot_online"

        normalized_target_id = str(target_id or "").strip()
        if not normalized_target_id:
            return False, "target_id_missing"

        bot = next(iter(bots.values()))
        normalized_target_type = (target_type or "private").strip().lower()

        try:
            if normalized_target_type == "group":
                await bot.call_api("send_group_msg", group_id=int(normalized_target_id), message=text)
            elif normalized_target_type == "private":
                await bot.call_api("send_private_msg", user_id=int(normalized_target_id), message=text)
            else:
                return False, f"unsupported_target_type:{normalized_target_type}"
            return True, "ok"
        except Exception as ex:  # noqa: BLE001
            logger.warning(f"[ff14_bridge] send message failed: {ex}")
            return False, "send_api_error"

    def mark_accepted(self) -> None:
        self.stats.accepted += 1
        self.stats.last_accepted_at = time.time()
        self.stats.last_error = ""

    def mark_rejected(self, reason: str) -> None:
        self.stats.rejected += 1
        self.stats.last_error = reason

    def snapshot(self) -> BridgeStats:
        return BridgeStats(
            accepted=self.stats.accepted,
            rejected=self.stats.rejected,
            duplicated=self.stats.duplicated,
            last_error=self.stats.last_error,
            last_accepted_at=self.stats.last_accepted_at,
            registered_clients=len(self._clients_by_key),
        )

    def _cleanup_dedup(self, now: float, ttl: int) -> None:
        expired = [event_id for event_id, ts in self._dedup_cache.items() if now - ts > ttl]
        for event_id in expired:
            self._dedup_cache.pop(event_id, None)
