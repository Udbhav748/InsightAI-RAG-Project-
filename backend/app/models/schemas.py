"""Pydantic request/response schemas for API validation and serialization."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.document import RetrievedChunk


class DocumentUploadResponse(BaseModel):
    document_id: str
    original_filename: str
    stored_filename: str
    file_size: int
    upload_timestamp: datetime
    status: str


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, description="The user's natural-language question.")
    top_k: int | None = Field(
        None, gt=0, description="Number of chunks to retrieve. Defaults to Settings.retrieval_top_k."
    )
    min_score: float | None = Field(
        None,
        ge=-1.0,
        le=1.0,
        description="Minimum similarity score to keep a chunk. Defaults to Settings.retrieval_min_score.",
    )
    history: list[dict] | None = Field(
        None,
        description="Prior conversation turns, oldest first, each shaped like "
        "{'role': 'user'|'assistant', 'content': str}. Only the most recent "
        "6 are used. Ignored if session_id is provided (server-side history takes precedence).",
    )
    session_id: str | None = Field(
        None,
        description="Session identifier for server-side chat history. If omitted on first request, "
        "a new session is created and its ID returned in the response. On subsequent requests, "
        "include this ID to continue the same conversation.",
    )
    confirm_web_search: bool = Field(
        False,
        description="Human approval for the web-search tool. When Settings.web_search_requires_approval "
        "is enabled, web search is skipped unless this is true — an explicit human-in-the-loop "
        "gate on the agent's only outbound side-effect.",
    )
    structured_response: bool = Field(
        False,
        description="Request a JSON-mode structured answer. Only takes effect when "
        "Settings.structured_output_enabled is true; otherwise ignored.",
    )


class SourceReference(BaseModel):
    number: int = Field(
        ...,
        description="The [N] bracket marker this source corresponds to in `answer`'s inline "
        "citations — 1-indexed, documents first then web results, matching the order the "
        "model was shown them in (see prompt_builder.build_prompt).",
    )
    document_id: str
    chunk_id: str
    excerpt: str = Field(..., description="First ~200 characters of the cited chunk's text.")
    url: str | None = Field(
        None,
        description="Source URL, present only for web-sourced citations (document_id='web').",
    )


class DiagnosisInfo(BaseModel):
    raw_class: str = Field(..., description="Raw class label as returned by LeafSense.")
    crop: str = Field(..., description="Plain-language crop name, e.g. 'peach'.")
    disease: str = Field(..., description="Plain-language disease name, e.g. 'bacterial spot'.")
    confidence: float = Field(..., description="Model confidence for the predicted class, in [0, 1].")
    low_confidence: bool = Field(
        ..., description="True if confidence is below Settings.vision_confidence_threshold."
    )


class ChatResponse(BaseModel):
    answer: str
    retrieved_chunks: list[RetrievedChunk]
    sources: list[SourceReference]
    processing_time: float
    tool_used: str
    steps_taken: int
    answer_source: Literal["documents", "web", "mixed"] = Field(
        "documents",
        description="Whether the answer drew on retrieved document chunks, web search "
        "results, or both. Always 'documents' for non-retrieval actions.",
    )
    diagnosis: DiagnosisInfo | None = Field(
        None,
        description="Present only for image-diagnosis requests (POST /chat/diagnose) — "
        "the LeafSense prediction that produced this response's retrieval query.",
    )
    session_id: str = Field(
        ...,
        description="Session identifier for this conversation. If this is a new session, "
        "the server generates and returns it; otherwise it echoes the incoming session_id. "
        "Client should store this (e.g. in localStorage) and send it on subsequent requests "
        "to continue the same conversation history.",
    )


class RubricScores(BaseModel):
    """A reviewer's 1-5 rating on each of the answer-quality checklist's
    seven criteria. All seven are required together — a partial rubric
    (e.g. rating correctness but not safety) isn't a meaningful data
    point for the per-criterion averages or Inter-Annotator Agreement
    computed from it (see eval/metrics_report.py)."""

    correctness: int = Field(..., ge=1, le=5, description="Is the answer factually and logically right?")
    helpfulness: int = Field(..., ge=1, le=5, description="Does it help the user complete their task?")
    completeness: int = Field(..., ge=1, le=5, description="Does it cover every required part?")
    safety: int = Field(..., ge=1, le=5, description="Does it avoid harmful, unauthorized, or risky behavior?")
    tone: int = Field(..., ge=1, le=5, description="Is the communication appropriate for the context?")
    groundedness: int = Field(..., ge=1, le=5, description="Are factual claims supported by evidence?")
    citation_quality: int = Field(..., ge=1, le=5, description="Do citations point to the correct sources?")


class FeedbackRequest(BaseModel):
    message_id: str = Field(..., min_length=1)
    rating: Literal["up", "down"]
    comment: str | None = None
    rubric: RubricScores | None = Field(
        None,
        description="Optional detailed per-criterion review (see RubricScores). The quick "
        "thumbs-up/down above (`rating`) remains valid on its own — this is an additive, "
        "opt-in deeper review, not a replacement.",
    )


class FeedbackResponse(BaseModel):
    status: str


class StructuredAnswer(BaseModel):
    """Schema the LLM's JSON-mode output is validated against.

    The prompt (see prompt_builder.build_structured_prompt) asks the model
    to emit exactly this shape; anything else is a parse failure and the
    caller falls back to the free-text path.
    """

    answer: str = Field(..., description="The final answer text.")
    sources: list[str] = Field(
        default_factory=list,
        description="Optional document ids the answer draws on, as given by the model.",
    )


class DocumentProcessingResponse(BaseModel):
    document_id: str
    original_filename: str
    total_pages: int
    total_chunks: int
    total_embeddings: int
    pages_ocred: int = Field(
        0, description="Number of pages that had no extractable text layer and were recovered via OCR."
    )
    processing_time: float
    status: str


class DocumentDeleteResponse(BaseModel):
    document_id: str
    chunks_removed: int
    status: str


class DocumentListItem(BaseModel):
    document_id: str
    original_filename: str
    stored_filename: str
    file_size: int
    total_pages: int
    total_chunks: int
    total_embeddings: int
    pages_ocred: int
    upload_timestamp: datetime


class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem]
    total: int


class SignupRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=255)
    # Literal[True], not bool — Pydantic rejects consent=false or a
    # missing field with a 422 automatically, so the route doesn't need
    # a manual check. Signup is the first place this app stores real PII
    # (email, password hash); this confirms the user was shown and
    # agreed to that before an account is created.
    consent: Literal[True] = Field(
        ...,
        description="Must be true — confirms the user agreed to how their email/password are stored.",
    )


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=255)


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    email: str
    tenant_id: int
    role: str
