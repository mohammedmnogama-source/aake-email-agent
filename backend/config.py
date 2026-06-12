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

    # Zoho CRM
    zoho_client_id: str = ""
    zoho_client_secret: str = ""
    zoho_refresh_token: str = ""
    zoho_owner_id: str = "7268132000000593001"


settings = Settings()
