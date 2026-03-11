from pydantic import BaseModel, Field


class Config(BaseModel):
    ff14_bridge_enabled: bool = Field(default=True)

    # Legacy single-client fields. They are kept for migration compatibility.
    ff14_bridge_key: str = Field(default="xsztoolbox")
    ff14_bridge_secret: str = Field(default="")
    ff14_bridge_target_type: str = Field(default="group")
    ff14_bridge_target_id: str = Field(default="")

    # Multi-tenant storage.
    ff14_bridge_clients_file: str = Field(default="data/ff14_bridge/clients.json")
    ff14_bridge_allow_self_register: bool = Field(default=True)
    ff14_bridge_admin_users: str | int | list[str | int] = Field(default="")
    ff14_bridge_public_endpoint: str = Field(default="")

    # Validation / anti-abuse.
    ff14_bridge_time_window_seconds: int = Field(default=60)
    ff14_bridge_dedup_ttl_seconds: int = Field(default=300)
    ff14_bridge_rate_limit_per_minute: int = Field(default=120)

    # QQ -> 游戏下行队列配置。
    ff14_bridge_downlink_queue_size: int = Field(default=100)
    ff14_bridge_downlink_ttl_seconds: int = Field(default=300)
    ff14_bridge_downlink_max_length: int = Field(default=180)
    ff14_bridge_pull_rate_limit_per_minute: int = Field(default=240)

    # WebSocket downlink (preferred path, pull remains as fallback).
    ff14_bridge_ws_enabled: bool = Field(default=True)
    ff14_bridge_ws_ping_interval_seconds: int = Field(default=30)
    ff14_bridge_ws_client_timeout_seconds: int = Field(default=90)
    ff14_bridge_ws_push_batch_size: int = Field(default=5)
    ff14_bridge_ws_ack_timeout_seconds: int = Field(default=15)
