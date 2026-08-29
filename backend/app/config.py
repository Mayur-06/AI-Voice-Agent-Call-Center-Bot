from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str = ""
    google_api_key: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    chromadb_url: str = "http://localhost:8001"
    gemini_model: str = "gemini-3.6-flash"
    hf_token: str = ""
    hf_hub_disable_symlinks_warning: bool = False
    embedding_device: str = "cpu"

    audio_sample_rate: int = 16000
    vad_aggressiveness: int = 2
    silence_threshold_ms: int = 1500
    audio_chunk_ms: int = 250


settings = Settings()
