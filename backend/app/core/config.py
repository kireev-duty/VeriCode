from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ФСП Талант"
    environment: str = "dev"
    database_url: str = "sqlite:///./dev.db"

    jwt_secret: str = "dev-secret-change-me-in-production-0123456789"
    access_token_minutes: int = 60 * 12
    email_token_hours: int = 48

    # Public URL of the frontend: used in emails, QR codes of the PDF profile and OIDC redirects.
    public_url: str = "http://localhost:5173"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080"]

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from: str = "noreply@fsp-talent.local"
    # In dev the confirmation link is also returned in the API response, so the demo works without a mail server.
    expose_email_links: bool = True

    # FSP ID (Keycloak, OIDC). When keycloak is not running, a built-in mock provider is used.
    fsp_oidc_issuer: str = "http://localhost:8180/realms/fsp"
    fsp_oidc_public_issuer: str = "http://localhost:8180/realms/fsp"
    fsp_oidc_client_id: str = "fsp-talent"
    fsp_oidc_client_secret: str = "fsp-talent-secret"
    fsp_oidc_enabled: bool = False
    fsp_registry_url: str = "http://localhost:8090"

    # Grade policy (see docs/testing.md)
    grade_change_cooldown_days: int = 90
    same_grade_retry_days: int = 30
    invitation_weekly_quota: int = 20
    invitation_ttl_days: int = 14

    llm_provider: str = "none"  # none | anthropic | gigachat | yandex
    llm_api_key: str = ""
    llm_model: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
