"""End-to-end API tests using FastAPI's TestClient.

The vector store is an in-memory FAISSVectorStore backed by a tmp_path
(never the real backend/vector_store/), and both the LLM and the
embedding call are stubbed out — no real Gemini or sentence-transformers
calls happen here, so this suite runs fast and offline.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models.document import EmbeddedChunk
from app.models.schemas import ChatResponse, DocumentDeleteResponse, FeedbackResponse
from app.services.faiss_vector_store import FAISSVectorStore
from tests.conftest import assert_matches_schema

VALID_HEADERS = {"X-API-Key": settings.api_key}
INVALID_HEADERS = {"X-API-Key": "not-the-real-key"}

# Small toy embedding — real dimensionality doesn't matter since embed_query
# is stubbed to always return this, and the seeded chunk uses it too, so
# retrieval always finds an exact (cosine similarity 1.0) match.
FAKE_EMBEDDING_DIM = 8
FAKE_EMBEDDING = [1.0] + [0.0] * (FAKE_EMBEDDING_DIM - 1)

SEEDED_DOCUMENT_ID = "11111111-1111-1111-1111-111111111111"
SEEDED_CHUNK_TEXT = "Project scope defines the boundaries of what work is included."

MINIMAL_PDF_BYTES = b"%PDF-1.4\n%fake-pdf-for-tests\n"


class FakeLLMClient:
    """Stands in for GeminiClient: no network call, fixed answer text."""

    def __init__(self, response_text: str = "This is a stubbed grounded answer about scope."):
        self.response_text = response_text
        self.calls: list[str] = []

    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.response_text


@pytest.fixture
def seeded_vector_store(tmp_path):
    """A FAISSVectorStore living entirely under tmp_path, pre-seeded with
    one chunk so retrieval and delete-by-id both have something to find."""
    store = FAISSVectorStore(
        index_path=tmp_path / "index.faiss",
        metadata_path=tmp_path / "metadata.json",
    )
    store.create_index(dimension=FAKE_EMBEDDING_DIM)
    store.add_embeddings(
        [
            EmbeddedChunk(
                chunk_id="chunk-1",
                document_id=SEEDED_DOCUMENT_ID,
                embedding=FAKE_EMBEDDING,
                metadata={
                    "chunk_index": 0,
                    "total_chunks": 1,
                    "source": "pdf",
                    "text": SEEDED_CHUNK_TEXT,
                },
            )
        ]
    )
    return store


@pytest.fixture
def client(monkeypatch, seeded_vector_store, tmp_path):
    """A TestClient wired to the seeded, tmp_path-backed vector store and
    stubbed LLM/embedding calls — never touches the real vector store,
    Gemini, or the sentence-transformers model."""
    fake_llm = FakeLLMClient()

    # get_vector_store is imported by name into documents.py (`from
    # app.api.v1.routes.query import get_vector_store`), so both bindings
    # need patching — patching only query.get_vector_store would leave
    # documents.py still pointing at the original.
    monkeypatch.setattr("app.api.v1.routes.query.get_vector_store", lambda: seeded_vector_store)
    monkeypatch.setattr(
        "app.api.v1.routes.documents.get_vector_store", lambda: seeded_vector_store
    )
    monkeypatch.setattr("app.api.v1.routes.query.get_llm_client", lambda: fake_llm)
    monkeypatch.setattr("app.services.retrieval_service.embed_query", lambda query: FAKE_EMBEDDING)

    # Feedback events go to a tmp_path file, never the real
    # backend/feedback/feedback.jsonl. record_feedback() looks these up as
    # module globals at call time, so patching them here (rather than
    # passing a path in) is enough even though query.py imported the
    # function by name.
    feedback_path = tmp_path / "feedback.jsonl"
    monkeypatch.setattr("app.services.feedback_service.FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr("app.services.feedback_service.FEEDBACK_PATH", feedback_path)

    with TestClient(app) as test_client:
        test_client.fake_llm = fake_llm
        test_client.feedback_path = feedback_path
        yield test_client


class TestHealth:
    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestUpload:
    def test_rejects_wrong_mime_type(self, client):
        response = client.post(
            "/upload",
            headers=VALID_HEADERS,
            files={"file": ("notes.txt", b"just some text", "text/plain")},
        )
        assert response.status_code == 415

    def test_rejects_oversized_file(self, client, monkeypatch):
        # Zero out the limit so any non-empty upload exceeds it, instead of
        # constructing a real multi-megabyte payload.
        monkeypatch.setattr(settings, "max_upload_size_mb", 0)
        response = client.post(
            "/upload",
            headers=VALID_HEADERS,
            files={"file": ("doc.pdf", MINIMAL_PDF_BYTES, "application/pdf")},
        )
        assert response.status_code == 413

    def test_missing_api_key_returns_401(self, client):
        response = client.post(
            "/upload",
            files={"file": ("doc.pdf", MINIMAL_PDF_BYTES, "application/pdf")},
        )
        assert response.status_code == 401


class TestChat:
    def test_rejects_empty_query(self, client):
        response = client.post("/chat", headers=VALID_HEADERS, json={"query": ""})
        assert response.status_code == 422

    def test_happy_path_returns_valid_chat_response(self, client):
        response = client.post(
            "/chat",
            headers=VALID_HEADERS,
            json={"query": "What does the document say about project scope?"},
        )
        assert response.status_code == 200

        payload = response.json()
        assert_matches_schema(ChatResponse, payload)

        assert payload["answer"] == client.fake_llm.response_text
        assert payload["tool_used"] == "retrieval"
        assert payload["answer_source"] == "documents"
        assert payload["sources"] == [
            {
                "document_id": SEEDED_DOCUMENT_ID,
                "chunk_id": "chunk-1",
                "excerpt": SEEDED_CHUNK_TEXT,
                "url": None,
            }
        ]
        assert payload["steps_taken"] >= 4  # plan + retrieve + grade + generate
        assert len(client.fake_llm.calls) == 1  # no reflection retry needed


class TestChatFeedback:
    def test_valid_feedback_is_recorded(self, client):
        response = client.post(
            "/chat/feedback",
            headers=VALID_HEADERS,
            json={"message_id": "msg-1-123", "rating": "up", "comment": "Spot on."},
        )
        assert response.status_code == 200

        payload = response.json()
        assert_matches_schema(FeedbackResponse, payload)
        assert payload == {"status": "recorded"}

        lines = client.feedback_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["message_id"] == "msg-1-123"
        assert event["rating"] == "up"
        assert event["comment"] == "Spot on."

    def test_comment_is_optional(self, client):
        response = client.post(
            "/chat/feedback",
            headers=VALID_HEADERS,
            json={"message_id": "msg-2-456", "rating": "down"},
        )
        assert response.status_code == 200
        assert json.loads(client.feedback_path.read_text(encoding="utf-8"))["comment"] is None

    def test_invalid_rating_returns_422(self, client):
        response = client.post(
            "/chat/feedback",
            headers=VALID_HEADERS,
            json={"message_id": "msg-3-789", "rating": "sideways"},
        )
        assert response.status_code == 422
        assert not client.feedback_path.exists()

    def test_missing_api_key_returns_401(self, client):
        response = client.post(
            "/chat/feedback",
            json={"message_id": "msg-4-000", "rating": "up"},
        )
        assert response.status_code == 401
        assert not client.feedback_path.exists()


class TestDeleteDocument:
    def test_without_confirm_returns_400(self, client):
        response = client.delete(f"/documents/{SEEDED_DOCUMENT_ID}", headers=VALID_HEADERS)
        assert response.status_code == 400

    def test_unknown_document_returns_404(self, client):
        response = client.delete(
            "/documents/does-not-exist", params={"confirm": "true"}, headers=VALID_HEADERS
        )
        assert response.status_code == 404

    def test_existing_document_deletes_successfully(self, client):
        response = client.delete(
            f"/documents/{SEEDED_DOCUMENT_ID}", params={"confirm": "true"}, headers=VALID_HEADERS
        )
        assert response.status_code == 200

        payload = response.json()
        assert_matches_schema(DocumentDeleteResponse, payload)
        assert payload["document_id"] == SEEDED_DOCUMENT_ID
        assert payload["chunks_removed"] == 1
