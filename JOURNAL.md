## Unit 7 — Issue selection

**Issue link:** https://github.com/codepath/pathreview-ai201-fa26-howard/issues/16

**Issue title:** Failed tool calls recorded in tool_results never reach the review output

**Tier:** [ ] Tier 1  [x] Tier 2  [ ] Tier 3

**Problem summary:**
The orchestrator in `orchestrator.py` controls the calling of different tools during the AI portion of the review generation. `run()` returns a list of all the tool results (whether they were a success or failure). Currently, `tool_results` logs which tools during execution fail, but those results are not read anywhere. This fix would add the tool failure results in the review output, letting the user know which tools (if any), failed during the generation of the review.

**Branch name:** fix/16-tool-failure-review-output

**Setup confirmation:** [x] App runs locally at localhost:5173

**Cohort ledger:** [x] Issue added to cohort ledger

### "Is this issue right for me?" checklist

#### Part 1

* [X] I can explain the problem and the expected behavior in 2–3 sentences without reading the issue.
* [X] I've located the relevant files and confirmed they exist in the codebase.
* [X] I can describe a concrete before-and-after: what the user sees before the fix and what they see after.

#### Part 2

* [X] If I've contributed to large codebases before: Tier 2 or 3 is fair game.
* [X] I'm not choosing a Tier 3 issue to "challenge myself" if I haven't completed a Tier 1 or 2 first — scope surprises in Unit 9 don't have a safety net.

#### Part 3

* [X] I've found and read the specific code the issue references (not just the file — the function or section).
* [X] I've read enough surrounding context that I can write a rough plan for the fix without looking anything up.
* [X] I've found the test file for my module and read at least one test end-to-end.

#### Part 4

* [X] I've checked the issue comments and the ledger's Claims count, and I'm fine with how many others are on this issue.
* [X] I've estimated the time this will take and I'm confident I can complete it before the Unit 9 deadline.
  * [x] I have contributed to a large codebase before, and think that, with the assistance of Claude and other AI tools, that I can complete this in a reasonable amount of time.
* [X] This issue has no open blockers or dependencies on other unresolved issues.

## Unit 8 — Reproduction & solution planning

**Reproduction commit link:** https://github.com/alexis-evans/pathreview-ai201-fa26-howard/commit/8abb335

**Reproduction summary:**
Added `tests/unit/test_orchestrator_tool_failures.py`, which breaks a tool with a simulated malformed LLM response and confirms `Orchestrator.run()` logs the failure and records it in `tool_results` with `success: False`. Reading `core/services/review_service.py` confirmed the other half: `_run_agent_orchestration()` is a hardcoded placeholder that never constructs an `Orchestrator`, so `tool_results` has no reader anywhere in the app — the failure has no path into the review output.

**PLAN.md link:** https://github.com/alexis-evans/pathreview-ai201-fa26-howard/blob/fix/16-tool-failure-review-output/PLAN.md

**Blockers or open questions:**
Where exactly a tool failure should surface in the review response (a new `tool_failures` field on `FeedbackSection`/`ReviewResponse`, vs. folded into an existing section) isn't decided yet — I want to check the frontend's `ReviewSection` component before settling the schema. Also unclear whether a partial tool failure should still allow `review.status == "complete"`, or if there's a failure threshold that should mark it `"failed"` instead.

## Unit 9 — Solution building & PR submission

### Check-in 1 (mid-week)

**Current progress:**
All sub-tasks from `PLAN.md` are done. In order:
1. Reproduced the bug (`tests/unit/test_orchestrator_tool_failures.py`, from Unit 8) and wrote `PLAN.md`.
2. Wired `_run_agent_orchestration()` in `core/services/review_service.py` to build a real `Orchestrator` with the production tool registry (`_build_tool_registry()`) and translate `Profile` + ingestion results into orchestrator input (`_build_orchestrator_input()`), instead of the old hardcoded placeholder that never touched the orchestrator at all.
3. Collected any tool failures out of `tool_results` into a `tool_failures` list and summarized them (`_format_tool_failures()`); `process_review()` now stores that summary on `review.error_message` (a field that already existed but was never populated). A partial tool failure still lets the review complete.
4. Added `tests/unit/test_review_service_tool_failures.py`: unit tests for the three new helpers, plus an end-to-end `process_review()` check that a failing tool sets `review.error_message` while a healthy run leaves it `None`.
5. Wrote and ran a manual verification script (not committed — scratchpad only) that breaks a tool, runs the real `process_review()`, and prints `review.status`/`review.error_message` to confirm the fix visually, end to end, outside of pytest assertions.
6. `make check` and `make test-unit` both pass locally; opened a draft PR and requested feedback.

**Next steps:**
Address draft PR feedback from Madeline Gilmore (see below) before marking the PR ready for review.

**Blockers:**
N/A

---

### Check-in 2 (end of week)

**PR link:** https://github.com/codepath/pathreview-ai201-fa26-howard/pull/94

**Branch:** fix/16-tool-failure-review-output

**What you built:**
`_run_agent_orchestration()` in `core/services/review_service.py` now builds a real `Orchestrator` with the production tool registry and runs it against the profile's data, instead of returning hardcoded placeholder sections with no connection to the orchestrator. Any tool failures it collects from `tool_results` are summarized and stored on `review.error_message` by `process_review()`, so a failed tool is visible on the review instead of being silently dropped. A partial tool failure still lets the review complete; only a safety-check failure or unhandled exception marks it `"failed"`.

**Tests added or updated:**
Added `tests/unit/test_orchestrator_tool_failures.py` (reproduction, Unit 8): confirms `Orchestrator.run()` logs and records a tool failure in `tool_results`. Added `tests/unit/test_review_service_tool_failures.py` (Unit 9): covers the new `_build_tool_registry`/`_build_orchestrator_input`/`_format_tool_failures` helpers, confirms `_run_agent_orchestration()` surfaces a broken tool in `tool_failures`, and an end-to-end `process_review()` check that a failing tool sets `review.error_message` (naming the tool) while `review.status` still becomes `"complete"`, and that a healthy run leaves `error_message` as `None`.

**Self-review confirmation:** [x] make check passes  [x] make test-unit passes

**Draft PR feedback received from:** Madeline Gilmore

## Unit 10 — Iteration & reflection

### Reviewer feedback

**Feedback received:** [ ] Yes  [ ] No — still awaiting review

**Summary of feedback:**
[What did reviewers comment on? Or note that no review came in.]

**How you responded:**
[What changes did you make, or what did you reply? If no feedback,
leave blank.]

---

### Reflection

**What was harder than you expected?**
[Be specific — what part of the process, codebase, or workflow
surprised you?]

**What did you learn about working in a large codebase?**
[What's different about contributing to someone else's production code
vs. building your own project?]

**How did AI tools help — and where did they fall short?**
[Where was AI assistance most useful this module? Where did you need
to go beyond what AI could give you?]

**What would you do differently if you started over?**
[Issue selection, planning, implementation, or process — anything
you'd change?]

**What are you most proud of from this module?**
[One thing — it doesn't have to be the PR itself.]