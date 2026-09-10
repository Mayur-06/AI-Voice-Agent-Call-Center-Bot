from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    cors_allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://116.202.210.102:8080",
    ]

    groq_api_key: str = ""
    google_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    hf_token: str = ""
    hf_hub_disable_symlinks_warning: bool = False
    embedding_device: str = "cpu"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/voice_agent"

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    supabase_password: str = ""

    audio_sample_rate: int = 16000
    vad_aggressiveness: int = 2
    silence_threshold_ms: int = 800
    audio_chunk_ms: int = 250

    ws_heartbeat_interval_s: int = 20
    ws_receive_timeout_s: int = 180
    ws_max_concurrent_audio_tasks: int = 32

    ws_audio_executor_workers: int = 4
    ws_embedding_executor_workers: int = 2
    ws_queue_max_size: int = 1024

    use_new_pipeline: bool = True

    pinecone_api_key: str = ""
    pinecone_index_name: str = "voice-agent-documents"

    filler_threshold_ms: int = 1500


settings = Settings()
