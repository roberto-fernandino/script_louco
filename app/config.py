from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    app_name: str = "Transactions Query API"
    debug: bool = False
    default_page_size: int = 50
    max_page_size: int = 200
    cors_origins: str = "http://localhost:5173"
    querybuscas_base_url: str = "https://querybuscas.com"
    querybuscas_username: str = ""
    querybuscas_password: str = ""
    querybuscas_timeout_seconds: float = 15.0
    querybuscas_max_retries: int = 2
    querybuscas_retry_delay_seconds: float = 2.0

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
