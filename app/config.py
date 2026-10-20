from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'database.db'}"
    dns_parser_url: str = "http://127.0.0.1:8101"
    citilink_parser_url: str = "http://127.0.0.1:8102"
    onlinetrade_parser_url: str = "http://127.0.0.1:8103"

    parser_callback_url: str = "http://127.0.0.1:8001/api/parser-callback"


settings = Settings()