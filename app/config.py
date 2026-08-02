from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Mesh API
    mesh_api_key: str = ""
    mesh_base_url: str = "https://api.meshapi.ai/v1"
    mesh_chat_model: str = "openai/gpt-4o-mini"
    mesh_embedding_model: str = "openai/text-embedding-3-small"

    # App
    secret_key: str = "dev-secret-change-me"
    database_url: str = "sqlite:///./data/smartreco.db"
    chroma_persist_dir: str = "./data/chroma"

    admin_email: str = "admin@smartreco.local"
    admin_password: str = "change-me"

    # Recommendation trigger tuning
    recommendation_event_threshold: int = 5
    recommendation_first_event_threshold: int = 3
    recommendation_cooldown_minutes: int = 5

    # Scheduler
    scheduler_refresh_minutes: int = 20
    digest_hour: int = 17
    digest_minute: int = 0

    # SMTP
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "smartreco@example.com"

    # LangSmith
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "smartreco"

    submission_token: str = ""


settings = Settings()
