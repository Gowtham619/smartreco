from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# pydantic-settings' env_file only populates *our* Settings fields below — it
# never touches the real process environment. Libraries that read os.environ
# directly (LangSmith's tracing, which activates purely off LANGSMITH_*/
# LANGCHAIN_* env vars, not anything we pass it) would silently see nothing
# without this. override=False so already-exported shell/CI env vars win.
load_dotenv(override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Mesh API
    mesh_api_key: str = ""
    mesh_base_url: str = "https://api.meshapi.ai/v1"
    mesh_chat_model: str = "openai/gpt-4o-mini"
    mesh_embedding_model: str = "openai/text-embedding-3-small"
    mesh_embedding_dim: int = 1536  # must match mesh_embedding_model's output size

    # App
    secret_key: str = "dev-secret-change-me"
    database_url: str = "sqlite:///./data/smartreco.db"

    # Vector store (Qdrant). Leave qdrant_url empty for local embedded mode
    # (pure Python, no server needed) — set it to use a real Qdrant server/
    # Qdrant Cloud instance instead (required for hosts like Render where a
    # native vector-index extension can crash — see vector_store.py).
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_local_path: str = "./data/qdrant"

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

    submission_token: str = ""


settings = Settings()
