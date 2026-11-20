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

**Feedback received:** [x] Yes  [ ] No — still awaiting review

**Summary of feedback:**
After submitting my assignment for Unit 9, the person reviewing my PR flagged three things. First, the common failure path wasn't actually being caught: `Orchestrator.run()` only treated a raised exception as a failure, but every real tool (`GitHubTool`, `TechDetector`, `ReadmeScorer`, `SkillExtractor`, `MarketAnalyzer`) catches its own errors internally and returns `ToolResult(success=False, ...)` instead of raising — so the realistic failure shape was logged as a success and never reached `tool_results` as a failure at all. Second, `_format_tool_failures()` was interpolating the raw tool error string directly into `review.error_message`, which `PLAN.md` had already flagged as a risk during planning but the implementation didn't follow through on — internal error details were leaking straight to the end user. Third, the fix only touched the backend: `review.error_message` was being populated correctly, but `ReviewPage.tsx` only rendered it when `status === 'failed'`, so a partial failure on a `'complete'` review was stored but never shown to the user.

A second round of feedback came back after those changes. The main note was that I hadn't closed the loop on the edge cases `PLAN.md` itself raised. The plan asks whether `ContextManager` caches a failed result and serves it back on a retry, but looking at `_execute_tool()`, `store_tool_result` runs regardless of whether the result succeeded — and neither the journal nor the tests say whether I checked that, or decided it was out of scope. The same gap applies to the "all tools fail" and "empty plan" cases: there's no test confirming that an empty `tool_results` leaves `error_message` as `None`. The reviewer suggested going back through the "Edge cases" list before marking a PR ready and marking each one tested, verified by reading, or deliberately out of scope. There was also a smaller maintainability note: `error_message` now carries two different meanings — a fatal error when `status == "failed"`, and a partial-success warning when `status == "complete"` — and while the frontend handles that correctly by branching on `status`, nothing in the backend model or schema documents that the field is overloaded this way.

**How you responded:**
`agent/orchestrator.py` now checks `result.success` explicitly in addition to catching exceptions, so both failure shapes are recorded and logged consistently (commit `e0f4434`). `_format_tool_failures()` now names only the failed tool(s) in `review.error_message`, keeping the raw error text confined to the `tool_failures` list and the server-side log (commit `b951b8c`). `ReviewPage.tsx` got a new amber banner — styled off the existing "processing" yellow in `StatusBadge.tsx` rather than the red "failed" styling — that renders whenever a `complete` review carries an `error_message`, plus a new `ReviewPage.test.tsx` since that page had no prior test coverage (commit `1d7dea9`). I also went back and corrected `PLAN.md` to note that the real root cause was in `orchestrator.py`'s exception-only detection, not in `review_service.py` as I'd originally scoped it.

For the second round, here's the plan I'd follow without having implemented it yet. First, I'd go read `_execute_tool()` and `ContextManager.store_tool_result()` directly, since the reviewer pointed out `store_tool_result` runs unconditionally — I'd confirm whether a failed result that gets cached is ever re-served to a later tool in the same run (e.g. a second tool depending on the first one's cached output) and, if a single `Orchestrator` instance only ever runs its plan once, document that the retry concern is out of scope for this fix rather than leaving it unresolved. Then I'd update the "Edge cases" section of `PLAN.md` so each item is marked tested, verified by reading, or deliberately out of scope, instead of leaving the list as open questions. For "all tools fail" and "empty plan," I'd add a unit test to `test_review_service_tool_failures.py` that runs `process_review()` with an empty `tool_results` and asserts `review.error_message is None`, since right now that behavior is only implied, not verified. Finally, for the dual meaning of `error_message`, I'd add a short comment on the model field itself (in whatever ORM/schema file defines `Review.error_message`) stating plainly that the field means a fatal error when `status == "failed"` and a partial-success warning when `status == "complete"`, and call that out explicitly in the PR description too, so a future contributor who only reads the model doesn't have to reverse-engineer the convention from `ReviewPage.tsx`.

---

### Reflection

**What was harder than you expected?**
Getting the failure detection actually right was harder than the initial fix made it look. My first pass made `tool_results` reachable from `review_service.py` and called it done, but my reviewer caught that I'd only tested the raise-based failure path, not the `ToolResult(success=False, ...)` path every real tool actually uses. The bug I shipped first wasn't "tool failures don't reach the review," it was "tool failures that raise exceptions don't reach the review" — a narrower and less realistic case. Realizing the fix I was proud of hadn't addressed the actual failure mode was a harder moment than any of the implementation itself.

**What did you learn about working in a large codebase?**
The biggest difference from solo projects is that correctness isn't just "does my test pass," it's "does my test match how the rest of the system actually behaves." I wrote `test_orchestrator_tool_failures.py` against a tool that raises, which was a reasonable guess in isolation, but every real tool in this codebase (`GitHubTool`, `TechDetector`, `SkillExtractor`, etc.) swallows its own errors and returns a failed `ToolResult` instead. I only found that mismatch because a reviewer who knew the tool layer pointed it out — in a solo project there's no one to catch that kind of blind spot, so I had to get more disciplined about reading how existing code actually behaves instead of trusting my own mental model of it.

**How did AI tools help — and where did they fall short?**
Claude was most useful for the mechanical half of iterating on review feedback: once I knew `Orchestrator.run()` needed to check `result.success` as well as catching exceptions, it helped me update the logging and the test suite consistently across both the raise-based and success=False paths without missing a case. It was also useful for writing the new `ReviewPage.test.tsx` from scratch, since that page had no existing test patterns to follow. Where it fell short was judgment: it didn't catch that my original fix only handled the exception-based failure shape, and it wouldn't have caught the error-string leak into `review.error_message` either — both of those came from my reviewer who knew the tool implementations and saw the PLAN.md risk note I'd written and then not followed through on. AI was good at extending a correct understanding; it didn't substitute for someone else checking that understanding against the real code.

**What would you do differently if you started over?**
I'd go verify how the real tools fail before writing the reproduction test, instead of writing a plausible-looking failure (a tool that raises) and treating it as representative. If I'd grepped `GitHubTool`/`TechDetector`/etc. for how they return errors during Unit 8, I'd have caught the success=False gap myself instead of needing a reviewer to find it, which would have saved a full round of PR feedback.

**What are you most proud of from this module?**
Catching my own leak risk and then actually following through on it. `PLAN.md` already noted, during planning, that raw tool errors shouldn't leak into `review.error_message` — but the first implementation didn't honor that note. Going back during review and fixing `_format_tool_failures()` so only the tool name reaches the user, while keeping the raw error in the server-side log and the `tool_failures` list for debugging, felt like the module where "write it down in the plan" actually turned into "hold myself to it later," which hadn't always been true for me before.