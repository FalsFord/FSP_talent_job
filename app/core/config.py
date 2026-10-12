from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr


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

    # --- тестирование и конвейер заданий ---
    retake_cooldown_days: int = 7            # повтор теста на том же уровне
    expired_retry_hours: int = 24            # пауза после просроченной попытки
    session_grace_seconds: int = 60          # допуск на сетевую задержку при сдаче
    test_items_initial: int = 16
    test_items_micro: int = 6
    # Выполнение кода кандидатов (Python/Java). ВЫКЛЮЧЕНО по умолчанию: см. app/tasks/runners/code_runner.py.
    code_exec_enabled: bool = False
    knowledge_dir: str = "/data/ru-test-assignments"   # локальная копия корпуса (git clone), не входит в репозиторий
    embedding_backend: str = "hash"          # hash | fastembed (нужен пакет fastembed, см. requirements-ml.txt)
    embedding_model: str = "intfloat/multilingual-e5-small"
    llm_base_url: str = ""                   # OpenAI-совместимый endpoint (необязательно; только для черновиков заданий)
    llm_api_key: str = ""
    llm_model: str = ""
    llm_provider: str = "templates"
    gigachat_client_id: str = ""
    gigachat_client_secret: SecretStr = SecretStr("")
    gigachat_authorization_key: SecretStr = SecretStr("")
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat"
    gigachat_base_url: str = "https://api.giga.chat/v1"
    gigachat_oauth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    gigachat_ca_bundle: str = ""

    # --- приглашения ---
    invitation_ttl_days: int = 14

    # --- регистрация / почта ---
    require_email_verification: bool = False  # ТЗ п.2.2(4): включите в production
    frontend_url: str = "http://localhost:8080"
    mail_backend: str = "console"            # console | smtp
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = "no-reply@fsp-talent.local"

    background_jobs_enabled: bool = True
    git_eval_url: str = ""
    git_eval_key: str = ""
    git_eval_webhook_secret: str = ""
    git_eval_callback_base: str = "http://api:8000"
    ats_service_url: str = "http://ats:8011"
    ats_service_token: SecretStr = SecretStr("")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
