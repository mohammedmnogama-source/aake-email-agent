from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # IMAP / SMTP
    imap_host: str = "mail.aqeeqkw.com"
    imap_port: int = 993
    smtp_host: str = "mail.aqeeqkw.com"
    smtp_port: int = 465
    email_address: str
    email_password: str

    # Anthropic
    anthropic_api_key: str

    # Dashboard auth
    secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24

    # Database
    database_path: str = "data/agent.db"

    # CORS — comma-separated list of allowed origins
    cors_origins: str = "http://localhost:3000"

    # Optional: plain-text password to auto-seed on first deploy (never stored plain)
    dashboard_password: str = ""

    # Zoho CRM
    zoho_client_id: str = ""
    zoho_client_secret: str = ""
    zoho_refresh_token: str = ""
    zoho_owner_id: str = "7268132000000593001"

    # ERP integration (Phase 2 — not used yet).
    # Pydantic reads these from the env vars ERP_BASE_URL / ERP_SHARED_SECRET
    # (matching is case-insensitive). Both default to "" so the app still boots
    # when they are unset. The secret is a plain str and must NEVER be logged.
    erp_base_url: str = ""
    erp_shared_secret: str = ""

    def require_erp_base_url(self) -> str:
        """Return the ERP base URL, warning (not crashing) if it is missing.
        The future ERP client should call this instead of reading the field
        directly, so a missing URL is logged loudly but safely. Never touches
        the shared secret."""
        if not self.erp_base_url:
            import logging
            logging.getLogger(__name__).warning(
                "ERP_BASE_URL is not set — ERP integration is disabled."
            )
        return self.erp_base_url


settings = Settings()
