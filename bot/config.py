from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, field_validator


class Settings(BaseSettings):
    # Bot
    BOT_TOKEN: SecretStr
    ADMIN_IDS_RAW: str = ""

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/screening.db"

    # App
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    @field_validator("ADMIN_IDS_RAW", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v: str | list[int]) -> str:
        if isinstance(v, list):
            return ",".join(str(x) for x in v)
        return v or ""

    @property
    def ADMIN_IDS(self) -> list[int]:
        if not self.ADMIN_IDS_RAW:
            return []
        return [int(x.strip()) for x in self.ADMIN_IDS_RAW.split(",") if x.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        frozen=True,
    )


settings = Settings()