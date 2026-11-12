"""Tests for issue #16: tool failures from the orchestrator reaching the review.

_run_agent_orchestration() now builds a real Orchestrator and threads any
tool failures through to the caller; process_review() turns those into
review.error_message. See PLAN.md for the full design.
"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

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
        assert "boom" in summary


class TestRunAgentOrchestration:
    @pytest.mark.asyncio
    async def test_tool_failure_is_surfaced_in_output(self, mock_profile):
        """A broken tool should show up in tool_failures, not vanish."""
        with patch(
            "core.services.review_service.SkillExtractor.execute",
            side_effect=ValueError("malformed resume parse"),
        ):
            output = await _run_agent_orchestration(mock_profile, ingestion_results=[])

        failures = output["tool_failures"]
        assert len(failures) == 1
        assert failures[0]["tool"] == "skill_extractor"
        assert "malformed resume parse" in failures[0]["error"]

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
        review = Mock(id=uuid4(), status="pending", error_message=None)
        db = self._mock_db_with(review, mock_profile)

        with patch(
            "core.services.review_service.SkillExtractor.execute",
            side_effect=ValueError("malformed resume parse"),
        ):
            await process_review(db, review.id, mock_profile.id)

        assert review.status == "complete"
        assert review.error_message is not None
        assert "skill_extractor" in review.error_message

    @pytest.mark.asyncio
    async def test_healthy_run_leaves_error_message_none(self, mock_profile):
        review = Mock(id=uuid4(), status="pending", error_message=None)
        db = self._mock_db_with(review, mock_profile)

        await process_review(db, review.id, mock_profile.id)

        assert review.status == "complete"
        assert review.error_message is None
