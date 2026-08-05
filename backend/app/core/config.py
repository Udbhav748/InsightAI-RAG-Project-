"""Centralized application settings, loaded from environment variables / .env file.

See backend/.env.example for a description of each variable.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Required. Google Gemini API key (used by the future RAG/generation pipeline).
    gemini_api_key: str

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
    retrieval_min_score: float = 0.3

    # Gemini model used for text generation.
    gemini_model_name: str = "gemini-3.5-flash"

    # Timeout, in seconds, for Gemini API calls.
    gemini_timeout_seconds: int = 30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


settings = Settings()
