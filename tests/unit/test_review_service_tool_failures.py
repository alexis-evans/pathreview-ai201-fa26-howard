"""Tests for issue #16: tool failures from the orchestrator reaching the review.

_run_agent_orchestration() now builds a real Orchestrator and threads any
tool failures through to the caller; process_review() turns those into
review.error_message. See PLAN.md for the full design.

Review feedback (2026-11-18): the original version of this file only
simulated a tool that *raises*. Every real tool actually catches its own
error and returns ToolResult(success=False, ...) instead (confirmed by
grep across agent/tools/*.py), so that's the path these tests need to
exercise -- the raise-based tests are kept alongside it as a secondary,
defensive case, not the primary one.
"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from agent.tools.base import ToolResult
from core.services.review_service import (
    _build_orchestrator_input,
    _format_tool_failures,
    _run_agent_orchestration,
    process_review,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def no_retry_sleep(monkeypatch):
    # retry_with_backoff sleeps between attempts; skip the waits in tests.
    monkeypatch.setattr("agent.error_handling.time.sleep", lambda _seconds: None)


@pytest.fixture
def mock_profile():
    """A profile with just enough data to put skill_extractor on the plan."""
    profile = Mock()
    profile.id = uuid4()
    profile.github_username = None
    profile.resume_text = "Built services in Python and TypeScript."
    return profile


class TestBuildOrchestratorInput:
    def test_maps_profile_fields(self, mock_profile):
        result = _build_orchestrator_input(mock_profile, ingestion_results=[])

        assert result["resume_text"] == mock_profile.resume_text
        assert result["github_username"] is None
        assert result["readme_content"] is None

    def test_picks_up_readme_from_ingestion_results(self, mock_profile):
        ingestion_results = [{"source_type": "readme", "data": "# My Project"}]

        result = _build_orchestrator_input(mock_profile, ingestion_results)

        assert result["readme_content"] == "# My Project"


class TestFormatToolFailures:
    def test_returns_none_when_no_failures(self):
        assert _format_tool_failures([]) is None

    def test_summarizes_each_failed_tool(self):
        failures = [{"tool": "skill_extractor", "error": "boom"}]

        summary = _format_tool_failures(failures)

        assert summary is not None
        assert "skill_extractor" in summary

    def test_does_not_leak_the_raw_error_text(self):
        """PLAN.md flagged this as a risk: don't show internals to the user."""
        failures = [{"tool": "github_tool", "error": "Traceback: KeyError at line 42"}]

        summary = _format_tool_failures(failures)

        assert summary is not None
        assert "Traceback" not in summary
        assert "KeyError" not in summary


class TestRunAgentOrchestration:
    @pytest.mark.asyncio
    async def test_tool_that_returns_failure_result_is_surfaced(self, mock_profile):
        """The realistic case: a tool that catches its own error and returns
        ToolResult(success=False, ...) instead of raising."""
        with patch(
            "core.services.review_service.SkillExtractor.execute",
            return_value=ToolResult(success=False, data={}, error="malformed resume parse"),
        ):
            output = await _run_agent_orchestration(mock_profile, ingestion_results=[])

        failures = output["tool_failures"]
        assert len(failures) == 1
        assert failures[0]["tool"] == "skill_extractor"
        assert failures[0]["error"] == "malformed resume parse"

    @pytest.mark.asyncio
    async def test_tool_that_raises_is_also_surfaced(self, mock_profile):
        """Defensive case: an uncaught bug in a tool should still be caught."""
        with patch(
            "core.services.review_service.SkillExtractor.execute",
            side_effect=ValueError("unexpected bug"),
        ):
            output = await _run_agent_orchestration(mock_profile, ingestion_results=[])

        failures = output["tool_failures"]
        assert len(failures) == 1
        assert failures[0]["tool"] == "skill_extractor"
        assert "unexpected bug" in failures[0]["error"]

    @pytest.mark.asyncio
    async def test_no_failures_when_tools_succeed(self, mock_profile):
        output = await _run_agent_orchestration(mock_profile, ingestion_results=[])

        assert output["tool_failures"] == []


class TestProcessReviewSurfacesToolFailures:
    """End-to-end: a failing tool should leave a trace on the stored review."""

    def _mock_db_with(self, review, profile):
        db = AsyncMock()
        db.add = Mock()
        db.commit = AsyncMock()

        # db.execute() is async, but the Result it returns is not: match
        # the real SQLAlchemy interface (and the codebase's convention from
        # test_review_service.py) with plain Mocks here.
        review_result = Mock()
        review_result.scalars.return_value.first.return_value = review
        profile_result = Mock()
        profile_result.scalars.return_value.first.return_value = profile

        db.execute = AsyncMock(side_effect=[review_result, profile_result])
        return db

    @pytest.mark.asyncio
    async def test_failed_tool_sets_review_error_message(self, mock_profile):
        """The realistic case: a tool returns ToolResult(success=False, ...)."""
        review = Mock(id=uuid4(), status="pending", error_message=None)
        db = self._mock_db_with(review, mock_profile)

        with patch(
            "core.services.review_service.SkillExtractor.execute",
            return_value=ToolResult(success=False, data={}, error="malformed resume parse"),
        ):
            await process_review(db, review.id, mock_profile.id)

        assert review.status == "complete"
        assert review.error_message is not None
        assert "skill_extractor" in review.error_message
        assert "malformed resume parse" not in review.error_message

    @pytest.mark.asyncio
    async def test_tool_that_raises_also_sets_review_error_message(self, mock_profile):
        """Defensive case: an uncaught bug in a tool should still be caught."""
        review = Mock(id=uuid4(), status="pending", error_message=None)
        db = self._mock_db_with(review, mock_profile)

        with patch(
            "core.services.review_service.SkillExtractor.execute",
            side_effect=ValueError("unexpected bug"),
        ):
            await process_review(db, review.id, mock_profile.id)

        assert review.status == "complete"
        assert review.error_message is not None
        assert "skill_extractor" in review.error_message
        assert "unexpected bug" not in review.error_message

    @pytest.mark.asyncio
    async def test_healthy_run_leaves_error_message_none(self, mock_profile):
        review = Mock(id=uuid4(), status="pending", error_message=None)
        db = self._mock_db_with(review, mock_profile)

        await process_review(db, review.id, mock_profile.id)

        assert review.status == "complete"
        assert review.error_message is None
