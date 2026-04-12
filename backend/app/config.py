from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    jwt_secret: str = "change-me"
    jwt_issuer: str = "my-jeja-backend"
    jwt_audience: str = "my-jeja-app"
    auth_google_only: bool = False
    google_client_id: str = ""
    google_client_ids: str = ""
    google_client_secret: str = ""
    google_oauth_redirect_uri: str = ""
    google_app_redirect_default: str = "http://localhost:19006/google-oauth-callback"
    cors_allow_origins: str = ""
    allowed_hosts: str = "*"

    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/myjeja"
    redis_url: str = ""
    rate_limit_fail_closed: bool = False
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    sentry_dsn: str = ""

    @property
    def database_url_async(self) -> str:
        # Railway often provides postgresql:// URLs; SQLAlchemy async needs +asyncpg.
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.database_url

    @property
    def cors_origins_list(self) -> list[str]:
        if not self.cors_allow_origins.strip():
            return []
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def allowed_hosts_list(self) -> list[str]:
        if not self.allowed_hosts.strip():
            return ["*"]
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @property
    def google_client_id_list(self) -> list[str]:
        ids: list[str] = []
        if self.google_client_id.strip():
            ids.append(self.google_client_id.strip())
        if self.google_client_ids.strip():
            ids.extend([i.strip() for i in self.google_client_ids.split(",") if i.strip()])
        # De-duplicate while preserving order.
        seen: set[str] = set()
        result: list[str] = []
        for value in ids:
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result


settings = Settings()

