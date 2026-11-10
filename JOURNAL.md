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

**Walkthrough video (recommended):** [not recorded yet]

**Blockers or open questions:**
Where exactly a tool failure should surface in the review response (a new `tool_failures` field on `FeedbackSection`/`ReviewResponse`, vs. folded into an existing section) isn't decided yet — I want to check the frontend's `ReviewSection` component before settling the schema. Also unclear whether a partial tool failure should still allow `review.status == "complete"`, or if there's a failure threshold that should mark it `"failed"` instead.