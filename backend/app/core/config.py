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

    # DPI used to rasterize a page for OCR (document_service.py), when the
    # page has no extractable text layer (scanned/image-only PDFs).
    # Higher improves OCR accuracy at the cost of extraction time; 200 is
    # tesseract's usual sweet spot.
    ocr_dpi: int = 200

    # Minimum characters PyMuPDF's own extraction must yield for a page to
    # be trusted as-is. Below this (including zero), OCR is attempted —
    # not just on truly blank pages. Real scans routinely carry a thin
    # native text layer (a header, a page number, a few garbled characters
    # from a prior bad OCR pass) that would otherwise pass the old
    # "any text at all" check and ship a near-useless chunk to the index.
    ocr_min_chars_per_page: int = 100

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

    # Enables hybrid search: fuse FAISS semantic search with a BM25 lexical
    # index (services/hybrid_search.py) instead of semantic search alone.
    # Defaults on: the ablation in docs/OPERATIONS.md's "Retrieval
    # ablation" showed it improving Precision@5/Recall@5/MRR over the
    # semantic-only baseline with no measured downside, and BM25 adds no
    # extra model/network dependency — cheap enough to ship as the
    # default rather than leave as an unproven opt-in. Still config-gated
    # so it can be A/B'd against the baseline (or turned off) via the
    # eval harness.
    hybrid_search_enabled: bool = True

    # Weight given to the (min-max normalized) semantic score in hybrid
    # fusion; BM25's weight is 1 - this value. Both scores are normalized
    # to [0, 1] before combining, so these weights are directly comparable.
    hybrid_semantic_weight: float = 0.6

    # Enables cross-encoder re-ranking (services/reranking_service.py) of
    # retrieval's candidate pool. Off by default — unlike hybrid search,
    # this stays opt-in: the ablation showed a real Precision@5 gain
    # (0.37 -> 0.40) but only at n=7 queries, and re-ranking has a real
    # operational cost hybrid search doesn't (a second model load, plus
    # cross-encoder inference on every retrieve-action request) — not
    # enough evidence yet to default every request into paying that cost.
    # See docs/OPERATIONS.md's "Retrieval ablation" before flipping this.
    reranking_enabled: bool = False

    # Cross-encoder model used for re-ranking.
    reranking_model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Candidate pool size for hybrid search (per retriever, before fusion)
    # and for reranking (before narrowing back to retrieval_top_k). A
    # wider pool than the final top_k gives fusion/reranking real material
    # to work with instead of just re-ordering an already-narrow shortlist.
    retrieval_candidate_k: int = 20

    # Gemini model used for text generation.
    gemini_model_name: str = "gemini-3.5-flash"

    # Timeout, in seconds, for Gemini API calls.
    gemini_timeout_seconds: int = 30

    # Estimated USD cost per 1,000 tokens (prompt + completion combined),
    # used only to log a rough cost estimate per generation — not actual
    # billed usage. Default is a placeholder; set to your model's real
    # blended rate.
    cost_per_1k_tokens: float = 0.00025

    # Base URL of the LeafSense vision service (a separate FastAPI process,
    # its own TensorFlow/Keras stack — see services/vision_client.py).
    # Defaults to 8001, NOT LeafSense's own default of 8000: LeafSense's
    # backend/main.py hardcodes port 8000 when run directly, which collides
    # with this backend's own default port. Start LeafSense with
    # `uvicorn main:app --port 8001` when running both services locally.
    vision_service_url: str = "http://localhost:8001"

    # Timeout, in seconds, for calls to the vision service.
    vision_service_timeout_seconds: int = 15

    # Below this confidence, diagnose_image() still returns its prediction
    # but flags it low_confidence=True (see models.document.VisionPrediction)
    # rather than silently presenting an uncertain guess as settled.
    vision_confidence_threshold: float = 0.5

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


settings = Settings()
