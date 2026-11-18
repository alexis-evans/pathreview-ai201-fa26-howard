import json
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import and_, select

from agent.orchestrator import Orchestrator
from agent.tools.base import BaseTool
from agent.tools.github_tool import GitHubTool
from agent.tools.market_analyzer import MarketAnalyzer
from agent.tools.readme_scorer import ReadmeScorer
from agent.tools.skill_extractor import SkillExtractor
from agent.tools.tech_detector import TechDetector
from api.schemas.review import FeedbackSection
from core.models.ingested_source import IngestedSource
from core.models.profile import Profile
from core.models.review import Review

log = structlog.get_logger()


async def create_review(
    db,
    profile_id: UUID,
    user_id: UUID,
) -> Review:
    """
    Create a new review with status="pending".
    """
    review = Review(
        profile_id=profile_id,
        status="pending",
        sections=None,
        overall_score=None,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


async def get_review(
    db,
    review_id: UUID,
    user_id: UUID,
) -> Review | None:
    """
    Get a review by ID, checking that it belongs to the user's profile.
    """
    stmt = (
        select(Review).join(Profile).where(and_(Review.id == review_id, Profile.user_id == user_id))
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def list_reviews(
    db,
    user_id: UUID,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Review], int]:
    """
    List reviews for a user with pagination.
    Returns (reviews, total_count).
    """
    offset = (page - 1) * page_size

    # Get total count
    count_stmt = select(Review).join(Profile).where(Profile.user_id == user_id)
    count_result = await db.execute(count_stmt)
    total = len(count_result.scalars().all())

    # Get paginated results
    stmt = (
        select(Review)
        .join(Profile)
        .where(Profile.user_id == user_id)
        .order_by(Review.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    reviews = result.scalars().all()

    return reviews, total


async def process_review(
    db,
    review_id: UUID,
    profile_id: UUID,
) -> None:
    """
    Background task to process a review.
    Steps:
    1. Set status="processing"
    2. Run ingestion pipeline on profile's sources
    3. Run agent orchestration
    4. Run RAG retrieval + generation
    5. Run safety checks on output
    6. Set status="complete", store sections in review.sections
    7. On exception: set status="failed", log error
    """
    try:
        # Get the review
        stmt = select(Review).where(Review.id == review_id)
        result = await db.execute(stmt)
        review = result.scalars().first()

        if not review:
            log.error("review_not_found_for_processing", review_id=str(review_id))
            return

        # Get the profile
        stmt = select(Profile).where(Profile.id == profile_id)
        result = await db.execute(stmt)
        profile = result.scalars().first()

        if not profile:
            log.error("profile_not_found_for_processing", profile_id=str(profile_id))
            review.status = "failed"
            db.add(review)
            await db.commit()
            return

        # Step 1: Set status to processing
        review.status = "processing"
        db.add(review)
        await db.commit()

        log.info("review_processing_started", review_id=str(review_id), profile_id=str(profile_id))

        # Step 2: Run ingestion pipeline
        ingestion_results = await _run_ingestion_pipeline(db, profile)
        log.info(
            "ingestion_pipeline_completed",
            review_id=str(review_id),
            sources_count=len(ingestion_results),
        )

        # Step 3: Run agent orchestration
        agent_output = await _run_agent_orchestration(profile, ingestion_results)
        tool_failures = agent_output.get("tool_failures", [])
        log.info(
            "agent_orchestration_completed",
            review_id=str(review_id),
            sections_count=len(agent_output.get("sections", [])),
            tool_failures_count=len(tool_failures),
        )

        # Step 4: Run RAG retrieval + generation
        rag_output = await _run_rag_retrieval_generation(profile, ingestion_results, agent_output)
        log.info("rag_retrieval_completed", review_id=str(review_id))

        # Step 5: Run safety checks
        safety_checks_passed = await _run_safety_checks(rag_output)
        if not safety_checks_passed:
            log.warning("safety_checks_failed", review_id=str(review_id))
            review.status = "failed"
            db.add(review)
            await db.commit()
            return

        # Step 6: Set status to complete and store sections
        sections_data = rag_output.get("sections", [])
        sections = [
            FeedbackSection(
                section_name=s.get("section_name", ""),
                content=s.get("content", ""),
                confidence=s.get("confidence", 0.0),
                suggestions=s.get("suggestions", []),
            )
            for s in sections_data
        ]

        review.status = "complete"
        review.sections = [s.model_dump() for s in sections]
        review.overall_score = rag_output.get("overall_score", None)
        review.error_message = _format_tool_failures(tool_failures)
        review.updated_at = datetime.utcnow()

        db.add(review)
        await db.commit()

        log.info(
            "review_processing_completed",
            review_id=str(review_id),
            overall_score=review.overall_score,
            tool_failures_count=len(tool_failures),
        )

    except Exception as exc:
        log.error("review_processing_failed", review_id=str(review_id), error=str(exc))
        try:
            stmt = select(Review).where(Review.id == review_id)
            result = await db.execute(stmt)
            review = result.scalars().first()
            if review:
                review.status = "failed"
                review.updated_at = datetime.utcnow()
                db.add(review)
                await db.commit()
        except Exception as e:
            log.error("review_status_update_failed", review_id=str(review_id), error=str(e))


async def _run_ingestion_pipeline(db, profile: Profile) -> list[dict]:
    """
    Run ingestion pipeline to extract data from profile sources.
    Returns list of ingested source data.
    """
    sources = []

    # Ingest from GitHub if available
    if profile.github_username:
        try:
            # Placeholder: actual GitHub ingestion logic
            github_data = {
                "source_type": "github",
                "username": profile.github_username,
                "data": f"GitHub profile data for {profile.github_username}",
            }
            sources.append(github_data)

            # Store in database
            ingested = IngestedSource(
                profile_id=profile.id,
                source_type="github",
                raw_data=json.dumps(github_data),
            )
            db.add(ingested)
        except Exception as exc:
            log.error(
                "github_ingestion_failed",
                username=profile.github_username,
                error=str(exc),
            )

    # Ingest from portfolio URL if available
    if profile.portfolio_url:
        try:
            # Placeholder: actual portfolio ingestion logic
            portfolio_data = {
                "source_type": "portfolio",
                "url": profile.portfolio_url,
                "data": f"Portfolio data from {profile.portfolio_url}",
            }
            sources.append(portfolio_data)

            # Store in database
            ingested = IngestedSource(
                profile_id=profile.id,
                source_type="portfolio",
                raw_data=json.dumps(portfolio_data),
            )
            db.add(ingested)
        except Exception as exc:
            log.error(
                "portfolio_ingestion_failed",
                url=profile.portfolio_url,
                error=str(exc),
            )

    # Ingest from resume if available
    if profile.resume_text:
        try:
            resume_data = {
                "source_type": "resume",
                "filename": profile.resume_filename,
                "data": profile.resume_text,
            }
            sources.append(resume_data)

            # Store in database
            ingested = IngestedSource(
                profile_id=profile.id,
                source_type="resume",
                raw_data=json.dumps(resume_data),
            )
            db.add(ingested)
        except Exception as exc:
            log.error(
                "resume_ingestion_failed",
                filename=profile.resume_filename,
                error=str(exc),
            )

    await db.commit()
    return sources


def _format_tool_failures(tool_failures: list[dict]) -> str | None:
    """Build a user-facing summary of any tools that failed during analysis.

    Names only the tools that failed, not their raw error text -- a tool's
    error (e.g. an exception message) can contain internals we don't want
    to show a user. The full error is still logged server-side by
    Orchestrator.run() and kept in `tool_failures` for any caller that
    wants structured detail.

    Args:
        tool_failures: List of {"tool": str, "error": str} dicts.

    Returns:
        A one-line summary, or None if nothing failed.
    """
    if not tool_failures:
        return None

    tool_names = ", ".join(f["tool"] for f in tool_failures)
    return f"Some analysis steps couldn't complete and were skipped: {tool_names}."


def _build_tool_registry() -> dict[str, BaseTool]:
    """Build the registry of agent tools used during orchestration.

    Returns:
        Dict mapping tool name to a tool instance, keyed the way
        Orchestrator._build_plan() names them.
    """
    return {
        "github_tool": GitHubTool(),
        "tech_detector": TechDetector(),
        "readme_scorer": ReadmeScorer(),
        "skill_extractor": SkillExtractor(),
        "market_analyzer": MarketAnalyzer(),
    }


def _build_orchestrator_input(profile: Profile, ingestion_results: list[dict]) -> dict:
    """Translate a Profile and its ingested sources into orchestrator input.

    Args:
        profile: The profile being reviewed.
        ingestion_results: Output of _run_ingestion_pipeline.

    Returns:
        Dict shaped for Orchestrator._build_plan() (github_username,
        readme_content, resume_text, etc.).

    Note:
        Deliberately omits "projects", so _build_plan() never schedules
        github_tool: Profile has no stored repo list to build it from
        today. The readme_content lookup below is similarly
        forward-looking -- _run_ingestion_pipeline() only ever emits
        "github"/"portfolio"/"resume" sources, never "readme", so this
        branch has no live data to match yet.
    """
    readme_content = next(
        (s.get("data") for s in ingestion_results if s.get("source_type") == "readme"),
        None,
    )

    return {
        "github_username": profile.github_username,
        "readme_content": readme_content,
        "resume_text": profile.resume_text,
        "repo_metadata": {},
    }


async def _run_agent_orchestration(profile: Profile, ingestion_results: list[dict]) -> dict:
    """
    Run agent orchestration to analyze ingested data.
    Returns agent output with initial analysis, plus any tool_failures so
    callers can surface them instead of silently dropping them.
    """
    orchestrator = Orchestrator(tools=_build_tool_registry())
    orchestrator_output = orchestrator.run(
        str(profile.id), _build_orchestrator_input(profile, ingestion_results)
    )

    tool_results = orchestrator_output.get("tool_results", {})
    tool_failures = [
        {"tool": tool_name, "error": result.get("error", "unknown error")}
        for tool_name, result in tool_results.items()
        if isinstance(result, dict) and result.get("success") is False
    ]
    if tool_failures:
        log.warning(
            "agent_orchestration_tool_failures",
            profile_id=str(profile.id),
            failed_tools=[f["tool"] for f in tool_failures],
        )

    # Placeholder: actual section-generation logic. tool_results from the
    # orchestrator above isn't used to build these yet (see issue #16 scope);
    # only the failures are threaded through so they reach the review output.
    return {
        "sections": [
            {
                "section_name": "Technical Skills",
                "content": "Analysis of technical skills from ingested sources",
                "confidence": 0.8,
                "suggestions": ["Add more detail on AI/ML experience"],
            },
            {
                "section_name": "Project Experience",
                "content": "Analysis of project experience",
                "confidence": 0.75,
                "suggestions": ["Include measurable impact metrics"],
            },
        ],
        "overall_score": 0.75,
        "tool_failures": tool_failures,
    }


async def _run_rag_retrieval_generation(
    profile: Profile,
    ingestion_results: list[dict],
    agent_output: dict,
) -> dict:
    """
    Run RAG retrieval and generation to create detailed feedback.
    Returns enhanced review output.
    """
    # Placeholder: actual RAG logic
    # In production, this would:
    # 1. Embed ingested content
    # 2. Store in vector DB
    # 3. Retrieve relevant context
    # 4. Generate detailed feedback using LLM

    return {
        "sections": [
            {
                "section_name": "Technical Skills",
                "content": "Detailed feedback on technical skills based on portfolio analysis",
                "confidence": 0.85,
                "suggestions": [
                    "Add more detail on AI/ML experience",
                    "Include specific technologies and frameworks",
                ],
            },
            {
                "section_name": "Project Experience",
                "content": "Detailed feedback on project experience and impact",
                "confidence": 0.8,
                "suggestions": [
                    "Include measurable impact metrics",
                    "Add links to project repositories",
                ],
            },
            {
                "section_name": "Career Growth",
                "content": "Feedback on career progression and development",
                "confidence": 0.78,
                "suggestions": [
                    "Document learning from each role",
                    "Highlight growth in responsibilities",
                ],
            },
        ],
        "overall_score": 0.81,
    }


async def _run_safety_checks(output: dict) -> bool:
    """
    Run safety checks on the review output.
    Returns True if all checks pass, False otherwise.
    """
    # Placeholder: actual safety checks logic
    # In production, this would:
    # 1. Check for personally identifiable information
    # 2. Validate feedback tone and constructiveness
    # 3. Check for bias in recommendations
    # 4. Ensure compliance with guidelines

    try:
        # Basic validation
        if not output.get("sections"):
            log.warning("safety_check_failed_no_sections")
            return False

        for section in output.get("sections", []):
            if not section.get("section_name") or not section.get("content"):
                log.warning("safety_check_failed_incomplete_section", section=section)
                return False

            confidence = section.get("confidence", 0)
            if not (0 <= confidence <= 1):
                log.warning("safety_check_failed_invalid_confidence", confidence=confidence)
                return False

        log.info("safety_checks_passed")
        return True

    except Exception as exc:
        log.error("safety_checks_error", error=str(exc))
        return False
