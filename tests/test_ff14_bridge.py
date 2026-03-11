import asyncio
import hashlib
import hmac
import json

from nonebot_plugin_ff14bot_bridge.config import Config
from nonebot_plugin_ff14bot_bridge.service import FF14BridgeService


def test_verify_signature_ok():
    cfg = Config(ff14_bridge_secret="test-secret")
    service = FF14BridgeService(cfg)

    body = json.dumps({"event_id": "1", "content": "hello"}).encode("utf-8")
    timestamp = "1700000000"
    signature = service.verify_signature(body, timestamp, "", cfg.ff14_bridge_secret)
    assert signature is False


def test_signature_and_timestamp():
    cfg = Config(ff14_bridge_secret="test-secret", ff14_bridge_time_window_seconds=999999999)
    service = FF14BridgeService(cfg)

    body = json.dumps({"event_id": "1", "content": "hello"}).encode("utf-8")
    timestamp = "1700000000"
    expected = "7e20fd861db54a7abe10bb4a6f848b9ac9d21929b036cc18aede6cd9b4a71592"
    real = service.verify_signature(body, timestamp, expected, cfg.ff14_bridge_secret)
    assert real is True

    assert service.check_timestamp(str(1700000000)) is True


def test_dedup():
    cfg = Config(ff14_bridge_dedup_ttl_seconds=300)
    service = FF14BridgeService(cfg)

    first = asyncio.run(service.check_and_mark_duplicate("k1", "evt-1"))
    second = asyncio.run(service.check_and_mark_duplicate("k1", "evt-1"))
    third = asyncio.run(service.check_and_mark_duplicate("k2", "evt-1"))
    assert first is False
    assert second is True
    assert third is False


def test_rate_limit():
    cfg = Config(ff14_bridge_rate_limit_per_minute=1)
    service = FF14BridgeService(cfg)

    first = asyncio.run(service.check_rate_limit("k", "127.0.0.1"))
    second = asyncio.run(service.check_rate_limit("k", "127.0.0.1"))
    assert first is True
    assert second is False


def test_register_and_rotate_user(tmp_path):
    cfg = Config(ff14_bridge_clients_file=str(tmp_path / "clients.json"))
    service = FF14BridgeService(cfg)

    client, created = asyncio.run(service.register_user("123456"))
    assert created is True
    assert client.owner_user_id == "123456"
    assert client.target_type == "private"
    assert client.target_id == "123456"

    existed, created_again = asyncio.run(service.register_user("123456"))
    assert created_again is False
    assert existed.bridge_key == client.bridge_key

    old_secret = existed.secret
    rotated = asyncio.run(service.rotate_user_secret("123456"))
    assert rotated is not None
    assert rotated.secret != old_secret


def test_legacy_config_migration(tmp_path):
    cfg = Config(
        ff14_bridge_key="xsztoolbox",
        ff14_bridge_secret="test-secret",
        ff14_bridge_target_type="private",
        ff14_bridge_target_id="123456",
        ff14_bridge_clients_file=str(tmp_path / "clients.json"),
    )
    service = FF14BridgeService(cfg)
    client = service.get_client_by_key("xsztoolbox")
    assert client is not None
    assert client.secret == "test-secret"
    assert client.owner_user_id == "123456"


def test_downlink_enqueue_and_dequeue(tmp_path):
    cfg = Config(
        ff14_bridge_clients_file=str(tmp_path / "clients.json"),
        ff14_bridge_downlink_queue_size=2,
        ff14_bridge_downlink_ttl_seconds=60,
        ff14_bridge_downlink_max_length=10,
    )
    service = FF14BridgeService(cfg)
    client, _ = asyncio.run(service.register_user("123456"))

    ok, reason, _ = asyncio.run(service.enqueue_user_downlink("123456", "hello world 123"))
    assert ok is True
    assert reason == "ok"

    queue_size = asyncio.run(service.get_bridge_downlink_queue_size(client.bridge_key))
    assert queue_size == 1

    pulled = asyncio.run(service.dequeue_downlink(client.bridge_key, 5))
    assert len(pulled) == 1
    assert pulled[0]["content"] == "hello worl"

    queue_size_after = asyncio.run(service.get_bridge_downlink_queue_size(client.bridge_key))
    assert queue_size_after == 0


def test_ws_auth_signature_body():
    cfg = Config(ff14_bridge_secret="test-secret")
    service = FF14BridgeService(cfg)
    body = service.build_ws_auth_body("ff14_x1", "nonce-1")
    timestamp = "1700000000"
    payload = timestamp.encode("utf-8") + b"." + body
    expected = hmac.new(b"test-secret", payload, hashlib.sha256).hexdigest()
    assert service.verify_signature(body, timestamp, expected, "test-secret") is True


def test_ws_downlink_ack_and_requeue(tmp_path):
    cfg = Config(
        ff14_bridge_clients_file=str(tmp_path / "clients.json"),
        ff14_bridge_downlink_queue_size=10,
        ff14_bridge_downlink_ttl_seconds=60,
        ff14_bridge_ws_ack_timeout_seconds=1,
    )
    service = FF14BridgeService(cfg)
    client, _ = asyncio.run(service.register_user("123456"))

    ok = asyncio.run(service.enqueue_downlink_for_client(client.bridge_key, "hello", "u1"))
    assert ok is True

    pushed = asyncio.run(service.acquire_downlink_for_ws(client.bridge_key, 5))
    assert len(pushed) == 1
    message_id = pushed[0]["message_id"]

    acked = asyncio.run(service.ack_downlink(client.bridge_key, message_id))
    assert acked is True
    size_after_ack = asyncio.run(service.get_bridge_downlink_queue_size(client.bridge_key))
    assert size_after_ack == 0

    asyncio.run(service.enqueue_downlink_for_client(client.bridge_key, "again", "u1"))
    pushed2 = asyncio.run(service.acquire_downlink_for_ws(client.bridge_key, 5))
    assert len(pushed2) == 1
    restored = asyncio.run(service.requeue_pending_downlink(client.bridge_key))
    assert restored == 1
    pulled = asyncio.run(service.dequeue_downlink(client.bridge_key, 5))
    assert len(pulled) == 1
    assert pulled[0]["content"] == "again"


def test_admin_users_accept_int_and_list():
    cfg_int = Config(ff14_bridge_admin_users=419827274)
    service_int = FF14BridgeService(cfg_int)
    assert service_int.is_admin("419827274") is True

    cfg_list = Config(ff14_bridge_admin_users=[111, "222", " 333 "])
    service_list = FF14BridgeService(cfg_list)
    assert service_list.is_admin("111") is True
    assert service_list.is_admin("222") is True
    assert service_list.is_admin("333") is True
