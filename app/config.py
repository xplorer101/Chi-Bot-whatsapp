from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "ChiBot"
    env: str = "dev"
    debug: bool = False
    log_level: str = "INFO"
    session_secret: str = "change-me"

    database_url: str = "postgresql+asyncpg://chibot:chibot@localhost:5432/chibot"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    ai_mock: bool = False
    ai_max_tokens: int = 400

    order_draft_ttl_minutes: int = 30

    graph_api_base: str = "https://graph.facebook.com/v22.0"
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = ""
    meta_app_secret: str = ""
    whatsapp_dry_run: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()