from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    jwt_secret: str = "change-me"
    cors_allow_origins: str = ""

    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/myjeja"
    anthropic_api_key: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        if not self.cors_allow_origins.strip():
            return []
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


settings = Settings()

