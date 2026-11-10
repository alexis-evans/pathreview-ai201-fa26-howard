## Solution plan

**Issue:** [#16 — Failed tool calls recorded in tool_results never reach the review output](https://github.com/codepath/pathreview-ai201-fa26-howard/issues/16)

### Understand

The root cause isn't a crash — it's a missing connection between two pieces of code that were never wired together.

`Orchestrator.run()` already does the right thing on its own: when a tool raises, it logs `tool_execution_failed` and stores `{"success": False, "error": str(e)}` for that tool in the `tool_results` dict it returns (`agent/orchestrator.py:60-69`). That part works correctly today, as confirmed in `tests/unit/test_orchestrator_tool_failures.py`.

The gap is that nothing ever calls `Orchestrator.run()` in the actual review flow, and nothing reads `tool_results` afterward. `core/services/review_service.py`'s `_run_agent_orchestration()` (lines 283-305) is a hardcoded placeholder: it returns two fixed sections and never constructs an `Orchestrator` or touches `tool_results` at all. A repo-wide grep for `tool_results` turns up only the orchestrator's own write and my test file — zero callers.

**Expected behavior:** if `github_tool` fails while `readme_scorer` and `skill_extractor` succeed, the review the user sees should say which tool failed (e.g. a "Note: GitHub analysis unavailable" line or section), while still showing feedback from the tools that worked.

**Actual behavior:** a tool failure is logged to the terminal and recorded in `tool_results`, but the review the user receives never mentions it — it silently proceeds as if everything succeeded, because `_run_agent_orchestration()` doesn't produce real output in the first place.

### Map

- `agent/orchestrator.py` — `Orchestrator.run()` (produces `tool_results`, no change expected beyond maybe exposing it more clearly) and `_build_plan()` (decides which tools run, needed to call it from the service).
- `core/services/review_service.py` — `_run_agent_orchestration()` (currently the placeholder; needs to construct and call `Orchestrator` and propagate `tool_results`) and `process_review()` (the caller, around lines 137-167, needs to pass tool failures into the sections it builds).
- `api/schemas/review.py` — `FeedbackSection` (may need an optional field, e.g. `tool_failures: list[str] | None`, or failures could be folded into an existing section's `content`/`suggestions` — see Risks).
- `tests/unit/test_review_service.py` — existing test file for this service; I'll extend it rather than duplicate it.
- `tests/unit/test_orchestrator_tool_failures.py` — already covers the orchestrator half; may need a small addition once the service reads `tool_results`.

### Plan

1. Wire `_run_agent_orchestration()` to actually build an `Orchestrator` (with the real tool registry) and call `.run(profile_id, profile_data)` instead of returning the hardcoded dict, passing through whatever `profile_data` the function needs (currently it only receives `profile` and `ingestion_results`, so I need to check what shape `profile_data` the orchestrator expects and adapt).
2. Extract tool failures out of the returned `tool_results` (entries where `success` is `False`) into a small, explicit structure (e.g. `list[dict]` with `tool_name` and `error`) that `process_review()` can pass forward.
3. Decide how a failure surfaces in the review (see Risks — likely a `tool_failures` field on the review/response schema, not silently dropped by `_run_safety_checks` or folded into a section's prose), and update `FeedbackSection`/`ReviewResponse` accordingly.
4. Update `process_review()` in `core/services/review_service.py` to pass tool failures through `_run_rag_retrieval_generation()` (or alongside it) and into the final `review.sections` / response so the user sees them.
5. Add/extend tests: a `test_review_service.py` case where one tool raises and the resulting review includes a visible failure notice, plus a regression test confirming a fully-successful run has no such notice.

### Inputs & outputs

- **Input:** a `profile_data`/`Profile` + `ingestion_results` where at least one tool invocation is set up to fail (e.g. a malformed LLM response causing a `json.JSONDecodeError`, a tool timeout, or a missing dependency raising inside `tool.execute()`).
- **Output change:** `process_review()`'s stored `review.sections` (and the `ReviewResponse` the API returns) should include a human-readable indication of which tool(s) failed, without changing the shape or values of sections produced by tools that succeeded. `review.status` should still become `"complete"` for partial failures (not `"failed"`) unless no tools succeeded at all — that threshold needs a decision.

### Risks & unknowns

- **Where exactly failures should surface** — a new `tool_failures` list on `ReviewResponse`/`FeedbackSection` (api/schemas/review.py) vs. a synthetic "section" vs. plain text appended to an existing section's `content`. This changes the API contract, so I want to confirm the expected shape (maybe by checking the frontend's `ReviewSection` component) before touching the schema.
- **`_run_agent_orchestration()`'s current signature** (`profile: Profile, ingestion_results: list[dict]`) doesn't match what `Orchestrator.run()` expects (`profile_id: str, profile_data: dict`) — I'll need to build `profile_data` from `profile` and `ingestion_results`, and I haven't traced where `profile.projects`, `github_username`, etc. actually live on the `Profile` model yet.
- **`_run_safety_checks()`** (review_service.py:355-385) currently fails the whole review if any section is "incomplete" — I need to make sure a tool-failure notice doesn't accidentally get validated as a malformed section and flip the review to `status="failed"`.
- **Retry/timeout interaction** — `Orchestrator._execute_with_timeout()` retries failed tools twice with backoff (`agent/error_handling.py`), so an integration test that doesn't mock `time.sleep` will be slow; I already handle this in the existing orchestrator-level test and need to repeat the pattern in the service-level test.
- **Partial vs. total failure** — unclear whether the review should still be marked `"complete"` when some but not all tools fail, or whether there's a threshold (e.g. "market_analyzer" failing is cosmetic, "github_tool" failing on a GitHub-focused review is more severe). Need to confirm with the issue author/mentor or make a documented judgment call.

### Edge cases

- **All tools fail:** `tool_results` has every entry at `success: False` — the review should probably still complete with a clear "we couldn't analyze this profile" message rather than silently returning empty sections or crashing `_run_safety_checks`.
- **One tool fails, others succeed:** the most common case from the issue — sections from successful tools render normally, plus a visible note identifying the failed tool (not a raw stack trace or exception string, which could leak internals).
- **A tool fails on retry but succeeds on a later profile in the same session:** confirm `ContextManager`'s caching (`agent/memory/context_manager.py`) doesn't cache the failed result and serve it back for a retried/subsequent run with the same input hash.
- **`market_analyzer` always runs last and depends on other tools' output** (`_build_plan()`, `agent/orchestrator.py:127-130`) — if an earlier tool fails, `market_analyzer` still runs with an empty `detected_skills` dict; this shouldn't be reported as a second, misleading "failure" if it's actually tolerating missing input.
- **No tools in the plan at all** (e.g. `profile_data` has none of `github_username`, `files`, `readme_content`, `resume_text`) — `tool_results` is empty, and the fix shouldn't report a phantom failure for an empty run.
