from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    jwt_secret: str = "change-me"
    jwt_issuer: str = "my-jeja-backend"
    jwt_audience: str = "my-jeja-app"
    cors_allow_origins: str = ""
    allowed_hosts: str = "*"

    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/myjeja"
    redis_url: str = ""
    rate_limit_fail_closed: bool = False
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-latest"
    sentry_dsn: str = ""

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


settings = Settings()

