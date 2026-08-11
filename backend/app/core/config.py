"""Centralized application settings, loaded from environment variables / .env file.

See backend/.env.example for a description of each variable.
"""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_secrets_from_ssm() -> None:
    """If SECRETS_SSM_PREFIX is set (the Lambda deployment — see
    infra/lambda.tf/infra/ssm.tf), resolve GEMINI_API_KEY/API_KEY/
    GROQ_API_KEY/DATABASE_URL from SSM SecureString parameters under that
    prefix into the process environment, before Settings() below reads
    it. A no-op everywhere else (local dev, docker-compose, Render):
    SECRETS_SSM_PREFIX is never set there, so this returns immediately
    without importing boto3 or making any AWS call.

    Never overwrites a value that's already set directly (e.g. a local
    .env's GEMINI_API_KEY) — SSM only fills in what's actually missing.
    A parameter that doesn't exist under the prefix (DATABASE_URL when no
    DSN was configured, matching infra/ssm.tf's own conditional
    creation) is silently skipped, not an error — Settings.database_url's
    own default ("") applies exactly as it does everywhere else.
    """
    ssm_prefix = os.environ.get("SECRETS_SSM_PREFIX")
    if not ssm_prefix:
        return

    import boto3

    client = boto3.client("ssm")
    for env_name in ("GEMINI_API_KEY", "API_KEY", "GROQ_API_KEY", "DATABASE_URL"):
        if os.environ.get(env_name):
            continue
        parameter_name = f"{ssm_prefix}/{env_name.lower()}"
        try:
            response = client.get_parameter(Name=parameter_name, WithDecryption=True)
        except client.exceptions.ParameterNotFound:
            continue
        os.environ[env_name] = response["Parameter"]["Value"]


_load_secrets_from_ssm()


class Settings(BaseSettings):
    # Optional. PostgreSQL connection string (e.g.
    # postgresql+psycopg2://user:pass@host:5432/db). If set, the app uses
    # PostgreSQL-backed persistence (documents, sessions, API keys, usage
    # logs) via SQLAlchemy/Alembic — see app/core/database.py. If left
    # empty, the app falls back to the legacy in-memory/file stores (an
    # ephemeral deployment like Render's free tier that can't host a real
    # DB keeps working exactly as before).
    database_url: str = ""

    # Required. Google Gemini API key (used by the future RAG/generation pipeline).
    gemini_api_key: str

    # Which LLM provider generate() calls go to by default: "gemini" or
    # "groq". Both client classes implement the same LLMClient interface,
    # so switching this is the entire manual A/B-testing surface (see
    # model_routing_enabled below for automatic, per-request routing).
    llm_provider: str = "gemini"

    # Optional. If set to a different provider than llm_provider, that
    # provider is used as an automatic fallback: after the primary
    # provider's own retries are exhausted (LLMTimeoutError/LLMAPIError),
    # FallbackLLMClient retries once against this provider instead of
    # failing the request outright. Leave unset (None) to disable
    # fallback and fail after the primary's retries.
    fallback_llm_provider: str | None = None

    # When True, build_llm_client() (app/services/llm_provider.py) wraps
    # the primary client in a RoutingLLMClient that picks, per request,
    # between llm_provider (the default, "simple" path) and
    # model_routing_complex_provider (below) based on complexity/risk
    # signals already present in the built prompt — see
    # app/services/routing_llm_client.py. No new classification call: the
    # signals (has the corrective loop already retried once? is the
    # prompt unusually large?) are read straight off what the RAG
    # pipeline already assembled. Off by default — same reasoning as
    # every other routing/approval flag in this file: a deployment
    # policy, not assumed behavior.
    model_routing_enabled: bool = False

    # The provider used for requests RoutingLLMClient judges "complex"
    # when model_routing_enabled is True. Meant to be set to your
    # stronger/costlier model while llm_provider stays your cheap/fast
    # default — e.g. LLM_PROVIDER=groq + MODEL_ROUTING_COMPLEX_PROVIDER
    # left at this default. If this equals llm_provider, routing is a
    # deliberate no-op (nothing to route to) — build_llm_client() detects
    # that and skips wrapping, the same early-return shape
    # fallback_llm_provider already uses above.
    model_routing_complex_provider: str = "gemini"

    # Prompt length (characters), above which RoutingLLMClient treats a
    # request as "complex" even without a corrective-loop retry — a
    # proxy for both reasoning difficulty (more context to synthesize)
    # and cost (more tokens billed either way). A single-chunk answer
    # (one ~1000-char excerpt, chunk_size) plus instructions/query sits
    # nowhere near this; it takes several chunks, or web results stacked
    # alongside document chunks, to cross it — configurable per
    # deployment since "complex" is inherently a judgment call, not a
    # fixed property of this app.
    model_routing_complex_prompt_chars: int = 6000

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

    # Optional. JSON string mapping client identifiers to their API keys.
    # Example: '{"client-a": "key1", "client-b": "key2"}'
    # If provided, this supersedes api_key and enables per-client auth.
    # Keys are hashed at startup (SHA-256); only hashes are kept in memory.
    api_keys: str = ""

    # Optional. Comma-separated client names (the same names used as keys
    # in API_KEYS, or "default" for the single-api_key fallback) granted
    # the "admin" role — see app/services/tenant_service.py's
    # resolve_tenant(). Checked live on every request rather than baked
    # into the DB at tenant-creation time, so promoting/demoting a client
    # is just an env var change and a redeploy, not a migration or manual
    # SQL. Only takes effect when DATABASE_URL is set — without a DB there
    # is nowhere to persist per-tenant role, so role-gated actions (e.g.
    # DELETE /documents/{id}) fall back to their pre-RBAC, ungated
    # behavior, same as tenant-scoping already does.
    admin_client_names: str = ""

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

    # Chunks per encode() batch. Encoding a whole document's chunks in one
    # batch is fine on a normal machine, but on a memory-constrained
    # deployment (Render's free tier: 512MB) it's a real, measured
    # transient memory spike — confirmed against a live Render deploy that
    # OOM-killed on it. Smaller batches trade a little throughput for a
    # materially lower peak.
    embedding_batch_size: int = 8

    # Directory (relative to backend/) where the vector store is persisted.
    vector_store_dir_name: str = "vector_store"

    # Filename for the persisted FAISS index, inside vector_store_dir_name.
    vector_index_filename: str = "index.faiss"

    # Filename for the persisted chunk metadata (JSON), inside vector_store_dir_name.
    vector_metadata_filename: str = "metadata.json"

    # Default number of chunks to return from retrieval.
    retrieval_top_k: int = 5

    # When True, ChatService logs the exact prompt sent to the LLM on every
    # generation (see prompt_builder.build_prompt), not just its version —
    # closing the "prompt content not captured" debugging gap. Off by
    # default: prompts can embed retrieved document text, so capturing them
    # is a data-retention decision the deployment must make explicitly.
    log_prompt_content: bool = False

    # Upper bound on characters of the prompt logged when
    # log_prompt_content is True. Truncated with a marker, not silently
    # cut mid-word, so what's captured is unambiguously a prefix.
    log_prompt_max_chars: int = 2000

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

    # When True, the web-search tool is a human-in-the-loop action: it only
    # fires when the client explicitly sends confirm_web_search=true on the
    # /chat request (the "human approval" gate). Off by default — the
    # approval requirement is a deployment policy, not a behavior the app
    # should assume.
    web_search_requires_approval: bool = False

    # Same human-in-the-loop shape as web_search_requires_approval above,
    # applied to document deletion: when True, DELETE /documents/{id}
    # requires the caller to also send approved=true, in addition to
    # confirm=true. Distinct from both existing gates on that route:
    # confirm=true is mistake-prevention (did you mean to delete this at
    # all?) and the admin/member role check is access control (are you
    # allowed to delete anything?) — this is a deployment policy that can
    # require an explicit extra step before the action executes, on top
    # of either. Off by default, same reasoning as web search's flag: the
    # approval requirement is a deployment choice, not an assumed default.
    document_delete_requires_approval: bool = False

    # Enables JSON-mode structured output for the LLM: when True and the
    # client sends structured_response=true, ChatService asks the provider
    # for a strict JSON answer (via response_mime_type / response_format)
    # and validates it against the StructuredAnswer schema, falling back to
    # plain text if the model's output doesn't parse. Off by default so
    # the standard free-text path is unchanged.
    structured_output_enabled: bool = False

    # --- Multi-agent features (off by default) -------------------------
    # When True, intent classification uses an LLM router agent
    # (services/router_agent.py) instead of the deterministic keyword
    # planner — it can route a query to "research" (multi-step web
    # research) that the regex planner can't recognize. Deterministic
    # fast paths (small talk, "summarize <uuid>") still short-circuit
    # without an LLM call; a router failure degrades to the keyword
    # planner, so routing is a quality improvement, never a new failure
    # mode. Off by default: unchanged behavior + no extra LLM call.
    agent_routing_enabled: bool = False

    # When True, a second agent — the Research agent
    # (services/research_agent.py) — owns the weak/insufficient-retrieval
    # path: it plans search queries, runs them, reads the top pages, and
    # synthesizes a grounded answer, instead of the corrective loop's
    # single search_web() call. Only effective when WEB_SEARCH_ENABLED is
    # also true (research needs the web-search tool); otherwise it
    # degrades to the normal retrieve path. Together with the router this
    # makes the app genuinely multi-agent (planner hands off to a
    # specialist), which is what the checklist's collaboration/handoff
    # rows measure. Off by default.
    research_agent_enabled: bool = False

    # Max sub-queries the Research agent's planning step may emit for one
    # user query.
    research_max_subqueries: int = 3

    # How many of the top web results' pages the Research agent actually
    # fetches and reads (its "read" step). The rest are used as snippets
    # only. Bounded so a research pass can't balloon into an unbounded
    # scrape.
    research_read_limit: int = 2

    # Per-page character cap for content the Research agent's read step
    # pulls into context, and per-page-fetch timeout in seconds.
    research_page_max_chars: int = 1500
    research_page_timeout_seconds: int = 15

    # Wall-clock budget for the whole plan->search->read pass (the LLM plan
    # and synthesis calls aren't counted — they have their own client-level
    # timeouts). Without this, worst case is fully additive: subqueries x
    # search timeout + read_limit x page timeout, which with defaults is
    # already 30s+30s before a single LLM call. Checked between searches
    # and between page reads; once exceeded, the agent stops collecting
    # more and synthesizes from whatever it already has (degrade, not
    # fail), same as every other bound in this module.
    research_total_timeout_seconds: int = 45

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

    # Timeout, in seconds, for a single retrieval call (search + optional
    # reranking). A hung vector search or cross-encoder inference otherwise
    # blocks the whole request indefinitely, so this is the "prevent
    # indefinite waiting" timeout the tool checklist asks for. 0 = no
    # timeout (unchanged legacy behavior).
    retrieval_timeout_seconds: float = 0.0

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

    # Optional shared secret for authenticating to the LeafSense vision
    # service. When set, diagnose_image() sends it as an "X-API-Key" header
    # on every call (mirroring this app's own inbound auth convention).
    # When empty, calls are unauthenticated — fine for local dev, a
    # deployment gap if LeafSense is publicly reachable.
    vision_service_api_key: str = ""

    # Below this confidence, diagnose_image() still returns its prediction
    # but flags it low_confidence=True (see models.document.VisionPrediction)
    # rather than silently presenting an uncertain guess as settled.
    vision_confidence_threshold: float = 0.5

    # Enables S3 sync of uploads/vector_store/feedback (services/
    # s3_sync_service.py) — the persistence mechanism for the AWS Lambda
    # deployment, whose filesystem is read-only outside /tmp and wiped on
    # every cold start. Off by default: local dev, docker-compose, and any
    # non-Lambda deployment never touch S3 or need boto3 installed.
    s3_sync_enabled: bool = False

    # S3 bucket s3_sync_service.py reads/writes when s3_sync_enabled is
    # True. Required (non-empty) whenever sync is enabled.
    s3_sync_bucket_name: str = ""

    # Overrides where uploads/vector_store/feedback resolve on disk — normally
    # left empty, resolving relative to backend/ (Path(__file__).parents[2]
    # in each owning service module). Set to "/tmp" on the Lambda deployment
    # (infra/lambda.tf): Lambda's filesystem is read-only everywhere except
    # /tmp, and unlike a symlink-at-runtime approach, this doesn't require
    # deleting/replacing the on-image directories at container start —
    # impossible anyway, since deleting anything under a read-only mount
    # (including the empty directories baked into the image) fails too.
    data_dir_override: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def data_dir(self, dir_name: str) -> Path:
        """Resolve a data directory (uploads/vector_store/feedback) under
        data_dir_override when set, else relative to backend/ as before."""
        base = Path(self.data_dir_override) if self.data_dir_override else Path(__file__).resolve().parents[2]
        return base / dir_name

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def api_key_table(self) -> dict[str, str]:
        """Return a dict of sha256_hash -> client_name for all configured keys.

        If api_keys (JSON) is set, use that. Otherwise fall back to the single
        api_key with a default client name "default". Keys are hashed with SHA-256
        so plaintext keys are never stored in memory beyond initial parsing.
        The dict is keyed by hash for O(1) lookup, avoiding a linear scan.
        """
        import hashlib
        import json

        if self.api_keys:
            try:
                raw = json.loads(self.api_keys)
            except json.JSONDecodeError as exc:
                raise ValueError(f"API_KEYS must be valid JSON: {exc}") from exc
            if not isinstance(raw, dict):
                raise ValueError("API_KEYS must be a JSON object mapping client_name -> key")
            return {
                hashlib.sha256(key.encode()).hexdigest(): client
                for client, key in raw.items()
            }
        # Backward compatibility: single api_key becomes "default" client
        return {hashlib.sha256(self.api_key.encode()).hexdigest(): "default"}

    @property
    def admin_client_names_set(self) -> set[str]:
        """Parsed, whitespace-trimmed set of admin_client_names. Empty set
        (not an error) when unset — no client is admin by default."""
        return {name.strip() for name in self.admin_client_names.split(",") if name.strip()}


settings = Settings()
