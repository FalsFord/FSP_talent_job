from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "FSP Talent Platform"
    debug: bool = False
    database_url: str = "postgresql+asyncpg://fsp:fsp@db:5432/fsp"
    secret_key: str = "change-me-in-production-use-openssl-rand"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    cors_origins: str = "http://localhost:8080,http://localhost:5173,http://127.0.0.1:8080"
    grade_change_cooldown_days: int = 90
    embedding_dim: int = 384
    fsp_mock_mode: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
