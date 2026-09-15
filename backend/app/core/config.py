from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FrameByFrame API"
    api_v1_prefix: str = "/api/v1"
    database_url: str = Field(alias="DATABASE_URL")
    admin_enabled: bool = Field(default=False, alias="ADMIN_ENABLED")
    admin_token: str = Field(default="local-development-admin", alias="ADMIN_TOKEN")
    asset_root: Path = Field(default=Path("assets/scenes"), alias="ASSET_ROOT")
    upload_max_bytes: int = Field(default=12 * 1024 * 1024, alias="UPLOAD_MAX_BYTES")
    upload_rate_limit_per_minute: int = Field(default=10, alias="UPLOAD_RATE_LIMIT_PER_MINUTE")
    upload_webp_quality: int = Field(default=86, alias="UPLOAD_WEBP_QUALITY")
    guest_cookie_secret: str = Field(default="local-development-only-change-me", alias="GUEST_COOKIE_SECRET")
    guest_cookie_secure: bool = Field(default=False, alias="GUEST_COOKIE_SECURE")
    game_timezone: str = Field(default="Asia/Kolkata", alias="GAME_TIMEZONE")
    albumnesia_room_ttl_days: int = Field(default=14, alias="ALBUMNESIA_ROOM_TTL_DAYS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
