"""Tests for how Orchestrator.run records tool failures.

Bug: failed tool calls are recorded in tool_results with success=False, but no
caller reads them, so they never reach the review output.
(github.com/codepath/pathreview-ai201-fa26-howard/issues/16)

Reproduction (2026-11-10):
Ran these tests locally with a tool stub that raises json.JSONDecodeError,
simulating a malformed LLM response, in place of agent/tools/readme_scorer.py.

Observed:
  $ .venv/bin/python -m pytest tests/unit/test_orchestrator_tool_failures.py -v
  test_failed_tool_is_recorded_in_tool_results PASSED
  test_failed_tool_is_logged_to_terminal PASSED
  test_healthy_tool_is_not_recorded_as_failure PASSED

Orchestrator.run() does log the failure ("tool_execution_failed") and does
store {"success": False, "error": ...} in tool_results (agent/orchestrator.py:68-69).
Confirming the other half of the bug -- that this never reaches the review
output -- required reading core/services/review_service.py directly rather
than a runtime test: _run_agent_orchestration() (review_service.py:283-305)
is a hardcoded placeholder that never constructs an Orchestrator or reads
tool_results at all, and a repo-wide grep turns up zero callers of
tool_results outside this test file. So there is currently no code path for
a tool failure to travel from the orchestrator into a review -- the feature
gap is real, and it is a missing connection rather than a crashable code path.
See PLAN.md for the fix.
"""

import json

import pytest
from structlog.testing import capture_logs

from agent.orchestrator import Orchestrator
from agent.tools.base import ToolResult

pytestmark = pytest.mark.unit


class MalformedResponseTool:
    """Simulates a tool whose LLM returns text that is not valid JSON."""

    name = "readme_scorer"
    description = "Test tool that fails on a malformed LLM response"

    def execute(self, input_data: dict) -> ToolResult:
        raw_llm_output = "Score: 8/10 (this is not JSON)"
        json.loads(raw_llm_output)  # raises json.JSONDecodeError
        return ToolResult(success=True, data={})


class HealthyTool:
    name = "readme_scorer"
    description = "Test tool that succeeds"

    def execute(self, input_data: dict) -> ToolResult:
        return ToolResult(success=True, data={"score": 8})


@pytest.fixture(autouse=True)
def no_retry_sleep(monkeypatch):
    # retry_with_backoff sleeps between attempts; skip the waits in tests.
    monkeypatch.setattr("agent.error_handling.time.sleep", lambda _seconds: None)


PROFILE = {"readme_content": "# Example readme"}


class HealthyMarketAnalyzer(HealthyTool):
    # The orchestrator always appends market_analyzer after other tools run,
    # so it must be registered or it is recorded as an unknown-tool failure.
    name = "market_analyzer"


def make_orchestrator(readme_tool):
    tools = {"readme_scorer": readme_tool, "market_analyzer": HealthyMarketAnalyzer()}
    return Orchestrator(tools=tools)


def test_failed_tool_is_recorded_in_tool_results():
    orchestrator = make_orchestrator(MalformedResponseTool())

    output = orchestrator.run("profile-1", PROFILE)

    entry = output["tool_results"]["readme_scorer"]
    assert entry["success"] is False
    assert "error" in entry


def test_failed_tool_is_logged_to_terminal():
    orchestrator = make_orchestrator(MalformedResponseTool())

    with capture_logs() as logs:
        orchestrator.run("profile-1", PROFILE)

    failures = [e for e in logs if e["event"] == "tool_execution_failed"]
    assert len(failures) == 1
    assert failures[0]["tool"] == "readme_scorer"
    assert failures[0]["log_level"] == "error"


def test_healthy_tool_is_not_recorded_as_failure():
    orchestrator = make_orchestrator(HealthyTool())

    with capture_logs() as logs:
        output = orchestrator.run("profile-1", PROFILE)

    assert output["tool_results"]["readme_scorer"].get("success") is not False
    assert not [e for e in logs if e["event"] == "tool_execution_failed"]
