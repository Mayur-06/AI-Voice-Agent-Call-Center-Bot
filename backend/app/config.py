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
    # gemini-3.6-flash is a thinking model: measured 8.6-13.2s before its
    # first streamed token, which dominated every turn. flash-lite reaches
    # first token in ~0.9s, which is what a phone call needs.
    gemini_model: str = "gemini-3.1-flash-lite"
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
    # Consecutive trailing silence that ends a turn. Safe at this value now
    # that silence is measured as a trailing run rather than a cumulative
    # count of every unvoiced frame in the utterance.
    silence_threshold_ms: int = 500

    ws_audio_executor_workers: int = 4
    ws_embedding_executor_workers: int = 2
    ws_queue_max_size: int = 1024

    pinecone_api_key: str = ""
    pinecone_index_name: str = "voice-agent-documents"
    # Cosine floor for a retrieved chunk to be worth injecting. Without one,
    # top_k always returned something, so an off-topic question pulled in
    # unrelated documents and the agent answered from them. Measured on the
    # live index with MiniLM: genuinely on-topic questions score 0.24-0.40,
    # clearly unrelated ones 0.10 and below. The floor is deliberately loose -
    # borderline chunks are cheap, and the prompt tells the model to ignore
    # context that does not answer the question.
    rag_min_score: float = 0.20

    filler_threshold_ms: int = 1500

    # Spoken replies are capped so the agent does not monologue for 25s.
    max_response_tokens: int = 300


settings = Settings()
