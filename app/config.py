from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MIEL Consultation"
    app_env: str = "development"
    public_base_url: str = "http://localhost:8000"

    intrum_base_url: str = "https://ml22.intrumnet.com"
    intrum_leads_api_key: str | None = None
    intrum_request_type_id: int | None = None
    intrum_employee_id: int | None = None
    intrum_contact_marktype_id: int | None = None
    intrum_timeout_seconds: int = 15

    consultation_timezone: str = "Asia/Barnaul"
    consultation_source: str = "QR_мероприятие_женщины_бизнес"
    consultation_location: str = "Барнаул, БЦ GALAXY, пр. Строителей, 45"
    telegram_url: str | None = None
    max_url: str | None = None

    rate_limit_requests: int = 5
    rate_limit_window_seconds: int = 600

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def normalized_intrum_base_url(self) -> str:
        return self.intrum_base_url.rstrip("/")

    @property
    def static_dir(self) -> Path:
        return Path(__file__).with_name("static")


@lru_cache
def get_settings() -> Settings:
    return Settings()

