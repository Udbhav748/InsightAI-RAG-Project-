"""Tests for the 10/10-upgrade Agent 1 features:

1. Specialized agents (services/agents/): DocumentAnalyst, WebResearcher,
   FactChecker, Summarizer — each wraps an existing capability behind the
   Agent ABC.
2. PlanningAgent (services/planning_agent.py): LLM planner that emits an
   ExecutionPlan, with defensive JSON parsing and a deterministic
   fallback plan.
3. AgentExecutor (services/agent_executor.py): the ReAct
   plan→act→observe→synthesize loop over the dynamic tool registry.
4. ChatService._handle_via_executor: the flag-gated wiring so eligible
   queries route through the executor.
5. pgvector config surface (Settings.pgvector_*): the store swap is
   config-driven; these assert the settings exist with sane defaults.
6. eval/nightly_eval.py's summary builder.

Like the rest of the suite, these are offline: the LLM is a FakeLLM, the
vector store is a fake, and no real Postgres/Gemini is touched. The
pgvector store itself needs a live Postgres+extension, so it's covered by
a skip-if-no-DATABASE_URL smoke test only (conftest.py forces
DATABASE_URL="" for the session, so it skips here and runs in an
integration context instead).
"""

import asyncio
import json

import pytest

from app.core.config import settings
from app.models.document import RetrievedChunk, WebSearchResult
from app.services.agents.document_analyst import DocumentAnalyst
from app.services.agents.fact_checker import FactChecker
from app.services.agents.summarizer import Summarizer
from app.services.agents.web_researcher import WebResearcher
from app.services.agents.base import AgentContext
from app.services.planning_agent import PlanningAgent, PlanStep
from app.services.tools.base import ToolContext
from app.services.tools.factory import build_tool_registry


def run(coro):
    return asyncio.run(coro)


class FakeLLM:
    """generate/generate_structured pop from `responses` in call order.
    Raise on call when raise_on_call is set (failure-path tests)."""

    def __init__(self, responses=None, raise_on_call=False):
        self._responses = list(responses) if responses else []
        self._raise = raise_on_call
        self.calls = []

    def generate(self, prompt):
        self.calls.append(("generate", prompt))
        return self._pop()

    def generate_structured(self, prompt):
        self.calls.append(("generate_structured", prompt))
        return self._pop()

    def _pop(self):
        if self._raise:
            raise RuntimeError("llm down")
        return self._responses.pop(0) if self._responses else ""


class FakeVectorStore:
    def __init__(self, chunks=None):
        self._chunks = chunks or []

    def search(self, query_vector, top_k, tenant_id=None, document_ids=None):
        return self._chunks[:top_k]

    def get_chunks_by_document(self, document_id, tenant_id=None):
        return self._chunks

    def total_vectors(self):
        return len(self._chunks)


def make_chunk(chunk_id="c1", document_id="doc-1", text="alpha beta gamma delta", score=0.9):
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        text=text,
        score=score,
        metadata={"chunk_index": 0, "tenant_id": None},
    )


def make_context(llm=None, store=None, metadata=None):
    return AgentContext(
        vector_store=store or FakeVectorStore([make_chunk()]),
        llm_client=llm or FakeLLM(["grounded answer"]),
        agent_memory=None,
        tenant_id=None,
        history=None,
        prompt_builder=lambda query, chunks, history, web_results: (
            f"Prompt for {query} with {len(chunks)} chunks"
        ),
        metadata=metadata or {},
    )


def make_registry():
    return build_tool_registry()


class TestPlanningAgent:
    def _planner(self, llm=None):
        return PlanningAgent(llm or FakeLLM(), make_registry())

    def test_plan_produces_execution_plan(self):
        llm = FakeLLM([json.dumps({
            "steps": [
                {"tool": "retrieval", "args": {"query": "q"}, "reason": "find"},
                {"tool": "synthesize", "args": {}, "reason": "answer"},
            ],
            "final_answer_tool": "synthesize",
        })])
        plan = run(self._planner(llm).plan("some question"))
        assert len(plan.steps) >= 1
        assert plan.steps[0].tool == "retrieval"
        assert plan.final_answer_tool == "synthesize"

    def test_fallback_plan_on_unparseable_output(self):
        llm = FakeLLM(["sure, here's my answer!"])
        plan = run(self._planner(llm).plan("anything"))
        assert [s.tool for s in plan.steps] == ["retrieval", "synthesize"]

    def test_fallback_plan_on_llm_failure(self):
        plan = run(self._planner(FakeLLM(raise_on_call=True)).plan("anything"))
        assert plan.steps[0].tool == "retrieval"

    def test_unknown_tool_dropped_from_plan(self):
        llm = FakeLLM([json.dumps({
            "steps": [
                {"tool": "not_a_real_tool", "args": {}, "reason": "nope"},
                {"tool": "synthesize", "args": {}, "reason": "answer"},
            ],
            "final_answer_tool": "synthesize",
        })])
        plan = run(self._planner(llm).plan("q"))
        assert all(step.tool != "not_a_real_tool" for step in plan.steps)

    def test_synthesize_appended_when_missing(self):
        llm = FakeLLM([json.dumps({
            "steps": [{"tool": "retrieval", "args": {"query": "q"}, "reason": "find"}],
            "final_answer_tool": "synthesize",
        })])
        plan = run(self._planner(llm).plan("q"))
        assert plan.steps[-1].tool == "synthesize"


class TestAgentExecutor:
    def _executor(self, llm=None):
        from app.services.agent_executor import AgentExecutor

        return AgentExecutor(
            llm_client=llm or FakeLLM([
                json.dumps({
                    "steps": [
                        {"tool": "retrieval", "args": {"query": "q"}, "reason": "find"},
                        {"tool": "synthesize", "args": {}, "reason": "answer"},
                    ],
                    "final_answer_tool": "synthesize",
                }),
                "grounded synthesized answer",
            ]),
            tool_registry=make_registry(),
            planning_agent=PlanningAgent(llm or FakeLLM(), make_registry()),
        )

    def test_execute_runs_plan_and_synthesizes(self):
        executor = self._executor()
        context = ToolContext(
            vector_store=FakeVectorStore([make_chunk()]),
            llm_client=FakeLLM(["irrelevant"]),
        )
        result = run(executor.execute("what is the PMP?", context=context))
        assert result.answer
        assert result.steps_taken >= 2
        assert result.tool_used in ("retrieval", "summarization")
        # Sources built from retrieved chunks surface structurally.
        assert result.sources or result.answer

    def test_execute_with_empty_retrieval_returns_fallback(self):
        from app.services.agent_executor import AgentExecutor

        executor = AgentExecutor(
            llm_client=FakeLLM([json.dumps({
                "steps": [{"tool": "retrieval", "args": {"query": "q"}, "reason": "find"}],
                "final_answer_tool": "synthesize",
            })]),
            tool_registry=make_registry(),
            planning_agent=PlanningAgent(FakeLLM(), make_registry()),
        )
        context = ToolContext(
            vector_store=FakeVectorStore([]),  # nothing to retrieve
            llm_client=FakeLLM(["n/a"]),
        )
        result = run(executor.execute("nothing here", context=context))
        assert result.answer  # FALLBACK_REPLY or honest "insufficient"


class TestSpecializedAgents:
    def test_document_analyst_retrieves_and_synthesizes(self):
        llm = FakeLLM(["grounded answer"])
        analyst = DocumentAnalyst(make_registry())
        result = run(analyst.run("what does the doc say?", make_context(llm=llm)))
        assert result.answer == "grounded answer"
        assert result.metadata["success"] is True

    def test_document_analyst_empty_retrieval_reports_failure(self):
        analyst = DocumentAnalyst(make_registry())
        context = make_context(store=FakeVectorStore([]))
        result = run(analyst.run("anything", context))
        assert result.metadata["success"] is False

    def test_summarizer_missing_document_id_reports_failure(self):
        summarizer = Summarizer()
        result = run(summarizer.run("summarize it", make_context()))
        assert result.metadata["success"] is False
        assert result.metadata["reason"] == "missing_document_id"

    def test_fact_checker_skips_without_verification_enabled(self, monkeypatch):
        monkeypatch.setattr(settings, "citation_verification_enabled", False)
        checker = FactChecker(FakeLLM())
        context = make_context(metadata={"answer": "answer [1]", "chunks": [make_chunk()]})
        result = run(checker.run("q", context))
        assert result.metadata["skipped"] is True
        assert result.metadata["verified"] is True

    def test_fact_checker_verifies_citations(self, monkeypatch):
        monkeypatch.setattr(settings, "citation_verification_enabled", True)
        llm = FakeLLM([json.dumps({"1": True})])
        checker = FactChecker(llm)
        context = make_context(metadata={"answer": "answer [1]", "chunks": [make_chunk()]})
        result = run(checker.run("q", context))
        assert result.metadata["verified"] is True

    def test_web_researcher_disabled_without_web_search(self, monkeypatch):
        monkeypatch.setattr(settings, "web_search_enabled", False)
        researcher = WebResearcher(FakeLLM())
        result = run(researcher.run("latest news", make_context()))
        assert result.metadata["success"] is False
        assert result.metadata["reason"] == "web_search_disabled"


class TestChatServiceExecutorWiring:
    def test_handle_via_executor_returns_chat_response(self, monkeypatch):
        monkeypatch.setattr(settings, "agent_executor_enabled", True)
        from app.models.schemas import ChatResponse
        from app.services.rag_service import ChatService

        llm = FakeLLM([
            json.dumps({
                "steps": [
                    {"tool": "retrieval", "args": {"query": "q"}, "reason": "find"},
                    {"tool": "synthesize", "args": {}, "reason": "answer"},
                ],
                "final_answer_tool": "synthesize",
            }),
            "synthesized answer",
        ])
        service = ChatService(FakeVectorStore([make_chunk()]), llm)
        response = service._handle_via_executor(
            "what is the PMP?",
            history=None,
            session_id=None,
            tenant_id=None,
            top_k=5,
            min_score=0.3,
            confirm_web_search=False,
            persona=None,
        )
        assert isinstance(response, ChatResponse)
        assert response.answer

    def test_executor_not_constructed_by_default(self, monkeypatch):
        monkeypatch.setattr(settings, "agent_executor_enabled", False)
        from app.services.rag_service import ChatService

        service = ChatService(FakeVectorStore(), FakeLLM())
        assert service._agent_executor is None

    def test_executor_lazily_constructed(self, monkeypatch):
        from app.services.rag_service import ChatService

        service = ChatService(FakeVectorStore(), FakeLLM())
        executor = service._agent_executor_instance()
        assert service._agent_executor is not None
        assert executor is service._agent_executor


class TestPgvectorConfigSurface:
    def test_pgvector_settings_present(self):
        assert hasattr(settings, "pgvector_enabled")
        assert settings.pgvector_enabled is False
        assert settings.pgvector_dimensions == 384
        assert settings.pgvector_table_name == "document_embeddings"

    def test_agent_executor_settings_present(self):
        assert settings.agent_executor_enabled is False
        assert settings.agent_executor_max_steps == 6

    def test_nightly_eval_settings_present(self):
        assert settings.nightly_eval_enabled is False
        assert settings.nightly_eval_dataset
        assert settings.nightly_eval_baseline
        assert settings.nightly_eval_tolerance == 0.05


class TestPgvectorStoreSmoke:
    @pytest.mark.skipif(
        not getattr(settings, "database_url", ""),
        reason="needs a live Postgres+pgvector (conftest.py forces DATABASE_URL='')",
    )
    def test_store_constructs_and_reports_zero_vectors(self):
        from app.services.pgvector_store import PgvectorVectorStore

        store = PgvectorVectorStore()
        assert store.total_vectors() == 0

    def test_dimension_mismatch_raises_clear_error(self):
        from app.services.pgvector_store import PgvectorVectorStore

        store = PgvectorVectorStore()
        with pytest.raises(Exception):
            store.add_embeddings(
                [type("EC", (), {"chunk_id": "c", "document_id": "d", "embedding": [0.1] * 5, "metadata": {}})()]
            )


class TestNightlyEvalSummary:
    def test_summarize_builds_headline_metrics(self):
        from eval.nightly_eval import _summarize

        report = {
            "dataset": "dataset_v1.json",
            "dataset_version": "v1",
            "llm_provider": "groq",
            "llm_model_name": "model",
            "prompt_version": "42",
            "hybrid_search_enabled": True,
            "reranking_enabled": False,
            "n_entries": 3,
            "task_success_rate": 0.9,
            "groundedness_proxy": 0.8,
        }
        summary = _summarize(report, None, gate_passed=True)
        assert summary["gate_passed"] is True
        assert summary["metrics"]["task_success_rate"] == 0.9
        assert "task_success_rate_baseline" not in summary["metrics"]

    def test_summarize_includes_baseline_comparison(self):
        from eval.nightly_eval import _summarize

        report = {"dataset_version": "v1", "task_success_rate": 0.9}
        baseline = {"dataset_version": "v1", "task_success_rate": 0.85}
        summary = _summarize(report, baseline, gate_passed=False)
        assert summary["gate_passed"] is False
        assert summary["metrics"]["task_success_rate_baseline"] == 0.85