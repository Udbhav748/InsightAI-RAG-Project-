"""Unit tests for the tool hardening layer:

- tool_registry.py's @track_tool decorator: input-schema validation
  (valid args pass, invalid args raise ToolInputError), the structured
  tool_invocation log event on success and on failure, and that the
  wrapped function's real return value / raised exceptions pass through
  unchanged.
- usage_tracking.py's per-request LLM usage rollup: reset_usage(),
  record_usage(), current_usage(), and the no-op behavior when no request
  scope is active.
"""

import pytest

from app.core import usage_tracking
from app.core.usage_tracking import current_usage, record_usage, reset_usage
from app.services.tool_registry import ToolInputError, track_tool


@track_tool("retrieval")
def _fake_retrieve(query, vector_store=None, top_k=None, min_score=None):
    return [query, top_k, min_score]


@track_tool("web_search")
def _fake_search(query, max_results=None):
    raise ValueError("web provider exploded")


@track_tool("diagnose")
def _fake_diagnose(contents, filename, content_type):
    return "ok"


class TestTrackToolSuccess:
    def test_valid_args_pass_through_and_return_unchanged(self):
        result = _fake_retrieve("how much does it cost", top_k=4)
        assert result == ["how much does it cost", 4, None]

    def test_logs_tool_invocation_success(self, caplog):
        with caplog.at_level("INFO", logger="app.services.tool_registry"):
            _fake_retrieve("question here")
        assert caplog.records
        event = caplog.records[-1]
        fields = event.extra_fields
        assert event.message == "tool_invocation"
        assert fields["tool"] == "retrieval"
        assert fields["success"] is True
        assert "latency_ms" in fields
        assert fields["input"]["query"] == "question here"
        assert fields["output"] == {"count": 3, "ids": []}


class TestTrackToolValidation:
    def test_empty_query_raises_tool_input_error(self):
        with pytest.raises(ToolInputError):
            _fake_retrieve("")

    def test_negative_top_k_raises(self):
        with pytest.raises(ToolInputError):
            _fake_retrieve("query", top_k=-3)


class TestTrackToolFailure:
    def test_logs_failure_and_propagates_original_exception(self, caplog):
        with caplog.at_level("WARNING", logger="app.services.tool_registry"):
            with pytest.raises(ValueError, match="web provider exploded"):
                _fake_search("anything")
        event = caplog.records[-1]
        fields = event.extra_fields
        assert event.message == "tool_invocation"
        assert fields["success"] is False
        assert fields["error_type"] == "ValueError"


class TestTrackToolInputSummarization:
    def test_long_query_truncated_and_bytes_replaced(self, caplog):
        with caplog.at_level("INFO", logger="app.services.tool_registry"):
            _fake_diagnose(contents=b"\x00" * 5000, filename="leaf.jpg", content_type="image/jpeg")
        fields = caplog.records[-1].extra_fields
        assert fields["input"]["contents"] == "<5000 bytes>"
        assert fields["input"]["filename"] == "leaf.jpg"
        assert fields["output"] == "ok"


class TestTrackToolOutputSummarization:
    def test_long_string_output_truncated(self, caplog):
        @track_tool("summarization")
        def _fake_summarize(document_id):
            return "A" * 500

        with caplog.at_level("INFO", logger="app.services.tool_registry"):
            _fake_summarize("doc-1")
        fields = caplog.records[-1].extra_fields
        assert fields["output"].startswith("A" * 120)
        assert fields["output"].endswith("...")

    def test_list_output_returns_count_and_ids(self, caplog):
        from types import SimpleNamespace

        @track_tool("retrieval")
        def _fake_retrieve_with_ids(query, top_k=None, min_score=None):
            return [SimpleNamespace(chunk_id="c1"), SimpleNamespace(chunk_id="c2")]

        with caplog.at_level("INFO", logger="app.services.tool_registry"):
            _fake_retrieve_with_ids("query")
        fields = caplog.records[-1].extra_fields
        assert fields["output"] == {"count": 2, "ids": ["c1", "c2"]}


class TestUsageTracking:
    def test_no_scope_is_noop(self):
        # Other tests in the same process may have left a request scope
        # active on the thread; force the contextvar back to its default
        # so this test exercises the true no-scope path.
        usage_tracking._scope.set(None)
        assert current_usage()["llm_calls"] == 0
        record_usage(prompt_tokens=1, completion_tokens=1, total_tokens=2, estimated_cost_usd=0.0001)
        assert current_usage()["total_tokens"] == 0

    def test_reset_then_record_accumulates(self):
        reset_usage()
        record_usage(prompt_tokens=10, completion_tokens=5, total_tokens=15, estimated_cost_usd=0.0002)
        record_usage(prompt_tokens=100, completion_tokens=50, total_tokens=150, estimated_cost_usd=0.002)
        usage = current_usage()
        assert usage["llm_calls"] == 2
        assert usage["total_tokens"] == 165
        assert usage["prompt_tokens"] == 110
        assert usage["completion_tokens"] == 55
        assert usage["estimated_cost_usd"] == pytest.approx(0.0022, abs=1e-6)

    def test_reset_clears_previous_request(self):
        reset_usage()
        record_usage(prompt_tokens=99, completion_tokens=1, total_tokens=100, estimated_cost_usd=0.001)
        reset_usage()
        usage = current_usage()
        assert usage["llm_calls"] == 0
        assert usage["total_tokens"] == 0
