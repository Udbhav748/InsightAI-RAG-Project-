"""Unit tests for ChatService's planner and reflection step (rag_service.py).

Uses lightweight fakes for VectorStore/LLMClient — these tests only cover
_plan and _reflect, not the full agent loop (no real FAISS index or Gemini
call involved).
"""

from app.models.document import RetrievedChunk
from app.services.prompt_builder import FALLBACK_REPLY
from app.services.rag_service import ChatService, PlanDecision


class FakeLLMClient:
    def __init__(self, response="regenerated answer"):
        self.response = response
        self.calls = []

    def generate(self, prompt):
        self.calls.append(prompt)
        return self.response


class FakeVectorStore:
    """_plan and _reflect never touch the vector store; only used to satisfy ChatService.__init__."""


def make_service(llm_client=None):
    return ChatService(FakeVectorStore(), llm_client or FakeLLMClient())


def make_chunk(document_id="doc-1", text="chunk text"):
    return RetrievedChunk(
        chunk_id="chunk-1", document_id=document_id, text=text, score=0.9, metadata={}
    )


class TestPlan:
    def test_conversational_intent_routes_to_conversational(self):
        service = make_service()
        assert service._plan("hi") == PlanDecision(action="conversational")

    def test_plain_question_routes_to_retrieve(self):
        service = make_service()
        decision = service._plan("What is a project according to the PMP document?")
        assert decision.action == "retrieve"
        assert decision.document_id is None

    def test_summarize_with_document_id_routes_to_summarize(self):
        service = make_service()
        document_id = "123e4567-e89b-12d3-a456-426614174000"
        decision = service._plan(f"please summarize {document_id} for me")
        assert decision.action == "summarize"
        assert decision.document_id == document_id

    def test_summarize_without_document_id_falls_back_to_retrieve(self):
        service = make_service()
        decision = service._plan("can you summarize this document")
        assert decision.action == "retrieve"
        assert decision.document_id is None

    def test_summarize_keyword_and_uuid_are_case_insensitive(self):
        service = make_service()
        document_id = "123e4567-e89b-12d3-a456-426614174000"
        decision = service._plan(f"SUMMARIZE {document_id.upper()}")
        assert decision.action == "summarize"
        assert decision.document_id.lower() == document_id


class TestReflect:
    def test_no_chunks_never_triggers_reflection(self):
        llm_client = FakeLLMClient()
        service = make_service(llm_client)

        answer, triggered = service._reflect("query", [], "", history=None)

        assert triggered is False
        assert answer == ""
        assert llm_client.calls == []

    def test_grounded_answer_does_not_trigger_reflection(self):
        llm_client = FakeLLMClient()
        service = make_service(llm_client)
        chunks = [make_chunk()]

        answer, triggered = service._reflect(
            "query", chunks, "A real grounded answer.", history=None
        )

        assert triggered is False
        assert answer == "A real grounded answer."
        assert llm_client.calls == []

    def test_fallback_answer_with_chunks_triggers_regeneration(self):
        llm_client = FakeLLMClient(response="better grounded answer")
        service = make_service(llm_client)
        chunks = [make_chunk()]

        answer, triggered = service._reflect("query", chunks, FALLBACK_REPLY, history=None)

        assert triggered is True
        assert answer == "better grounded answer"
        assert len(llm_client.calls) == 1

    def test_empty_answer_with_chunks_triggers_regeneration(self):
        llm_client = FakeLLMClient(response="better grounded answer")
        service = make_service(llm_client)
        chunks = [make_chunk()]

        answer, triggered = service._reflect("query", chunks, "   ", history=None)

        assert triggered is True
        assert answer == "better grounded answer"
        assert len(llm_client.calls) == 1
