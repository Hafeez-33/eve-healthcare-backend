from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "EVE Healthcare API"
    DEBUG: bool = False

    # Database Configuration (PostgreSQL)
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/eve_healthcare"

    # Security & JWT Configuration
    SECRET_KEY: str = "change-this-to-a-secure-random-secret-key-in-production-min-32-chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Webhook Configuration
    WEBHOOK_SECRET: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
