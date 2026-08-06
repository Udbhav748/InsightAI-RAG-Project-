"""Shared pytest helpers for the backend test suite.

SCHEMA_COMPLIANCE is a tiny shared counter: assert_matches_schema() bumps
it every time a test validates a response body against one of the app's
Pydantic response models, and pytest_terminal_summary prints the
resulting compliance rate in the final test report.
"""

SCHEMA_COMPLIANCE = {"total": 0, "passed": 0}


def assert_matches_schema(model_cls, payload: dict):
    """Validate payload against a Pydantic response model.

    Raises (failing the calling test) if payload doesn't conform. Only
    counts toward SCHEMA_COMPLIANCE once validation has actually run.
    """
    SCHEMA_COMPLIANCE["total"] += 1
    model_cls.model_validate(payload)
    SCHEMA_COMPLIANCE["passed"] += 1


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    total = SCHEMA_COMPLIANCE["total"]
    passed = SCHEMA_COMPLIANCE["passed"]
    rate = (passed / total * 100) if total else 0.0
    terminalreporter.write_sep("=", f"Schema Compliance Rate: {passed}/{total} ({rate:.1f}%)")
