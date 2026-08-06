"""Centralized application settings, loaded from environment variables / .env file.

See backend/.env.example for a description of each variable.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Required. Google Gemini API key (used by the future RAG/generation pipeline).
    gemini_api_key: str

    # Which LLM provider generate() calls go to by default: "gemini" or
    # "groq". Both client classes implement the same LLMClient interface,
    # so switching this is the entire A/B-testing/model-routing surface.
    llm_provider: str = "gemini"

    # Optional. If set to a different provider than llm_provider, that
    # provider is used as an automatic fallback: after the primary
    # provider's own retries are exhausted (LLMTimeoutError/LLMAPIError),
    # FallbackLLMClient retries once against this provider instead of
    # failing the request outright. Leave unset (None) to disable
    # fallback and fail after the primary's retries.
    fallback_llm_provider: str | None = None

    # Groq API key. Only required if llm_provider or fallback_llm_provider
    # is "groq".
    groq_api_key: str = ""

    # Groq model used for text generation.
    groq_model_name: str = "llama-3.3-70b-versatile"

    # Timeout, in seconds, for Groq API calls.
    groq_timeout_seconds: int = 30

    # Estimated USD cost per 1,000 tokens for Groq, used the same way as
    # cost_per_1k_tokens below but with Groq's (much cheaper) pricing.
    groq_cost_per_1k_tokens: float = 0.0006

    # Required. Shared secret clients must send in the X-API-Key header to
    # reach the documents/query routers. See core/auth.py.
    api_key: str

    # Origin of the frontend app; used to configure CORS.
    frontend_url: str = "http://localhost:5173"

    # Application metadata, surfaced in the FastAPI docs.
    app_name: str = "InsightAI-RAG"
    app_version: str = "0.1.0"

    # Enables debug behavior (e.g. verbose errors).
    debug: bool = False

    # Directory (relative to backend/) where uploaded files are stored.
    upload_dir_name: str = "uploads"

    # Directory (relative to backend/) where chat feedback events are appended.
    feedback_dir_name: str = "feedback"

    # Filename for the feedback JSONL file, inside feedback_dir_name.
    feedback_filename: str = "feedback.jsonl"

    # Maximum accepted upload size, in megabytes.
    max_upload_size_mb: int = 20

    # MIME types accepted by the upload endpoint.
    allowed_upload_mime_types: list[str] = ["application/pdf"]

    # Target size of each document chunk, in characters.
    chunk_size: int = 1000

    # Character overlap between consecutive chunks.
    chunk_overlap: int = 200

    # Sentence Transformers model used to generate chunk embeddings.
    embedding_model_name: str = "all-MiniLM-L6-v2"

    # Directory (relative to backend/) where the vector store is persisted.
    vector_store_dir_name: str = "vector_store"

    # Filename for the persisted FAISS index, inside vector_store_dir_name.
    vector_index_filename: str = "index.faiss"

    # Filename for the persisted chunk metadata (JSON), inside vector_store_dir_name.
    vector_metadata_filename: str = "metadata.json"

    # Default number of chunks to return from retrieval.
    retrieval_top_k: int = 5

    # Default minimum similarity score a chunk must meet to be returned.
    # Chunks from a genuinely relevant match typically score ~0.45-0.55 with
    # all-MiniLM-L6-v2; 0.3 let weakly-related chunks through for off-topic/
    # conversational-ish queries that don't match any canned phrase in
    # rag_service.py, producing technically-grounded but irrelevant answers.
    retrieval_min_score: float = 0.4

    # Minimum top-chunk similarity score for retrieval to be graded "good"
    # (see ChatService._grade_retrieval). Between retrieval_min_score and
    # this threshold, retrieval is graded "weak" — chunks cleared the score
    # floor but aren't confidently on-topic, which is what triggers the web
    # search fallback (if enabled).
    retrieval_grade_threshold: float = 0.5

    # Enables the web-search fallback tool (services/web_search_service.py)
    # for "weak"/"insufficient" retrieval grades. Off by default so existing
    # behavior — and the lack of any outbound network call beyond Gemini —
    # is unchanged unless explicitly opted in.
    web_search_enabled: bool = False

    # Number of web results fetched when the fallback fires.
    web_search_result_count: int = 3

    # Timeout, in seconds, for the web search call.
    web_search_timeout_seconds: int = 10

    # Gemini model used for text generation.
    gemini_model_name: str = "gemini-3.5-flash"

    # Timeout, in seconds, for Gemini API calls.
    gemini_timeout_seconds: int = 30

    # Estimated USD cost per 1,000 tokens (prompt + completion combined),
    # used only to log a rough cost estimate per generation — not actual
    # billed usage. Default is a placeholder; set to your model's real
    # blended rate.
    cost_per_1k_tokens: float = 0.00025

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


settings = Settings()
