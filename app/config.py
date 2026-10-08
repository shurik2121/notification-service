from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://notification:notification@localhost:5432/notification"
    redis_url: str = "redis://localhost:6379/0"
    use_fake_provider: bool = True
    max_delivery_retries: int = 3
    retry_backoff_base_seconds: float = 2.0
    processing_timeout_seconds: int = 300
    outbox_batch_size: int = 100
    outbox_publish_interval_seconds: int = 1
    reaper_interval_seconds: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
