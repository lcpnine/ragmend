# Review Protocol

Every milestone passes three gates before it is tagged `mN-done`. The builder never grades its own work.

The bugs that would sink this project are not crashes. They are **silent validity bugs**:
- information leaking into the control
- a budget that isn't enforced
- mis-mapped evidence IDs
- a stale cache
- latency that misses a call

The review is designed around catching these.

---

## Gate 1: Automated

| Milestone | Gate 1 |
|---|---|
| **M0** | No `make check` yet. The reviewer verifies M0 artifacts directly (see the M0 variant below). |
| **M1+** | `make check` (offline, deterministic) must pass. The builder's committed `make check-live` log must exist and show passing live tests from this milestone. |

A FAIL here stops the review. The reviewer does not rerun `make check-live` by default, to avoid repeated spend. It may run it once if the live log looks suspicious.

---

## Gate 2: Independent reviewer agent

Run the reviewer in a **fresh session** with no builder context. It is read-only, except for running commands. If convenient, use a different model than the builder.

**Reviewer prompt (M1 onward)**

```
You are an independent reviewer. You did not write this code. Do not modify any files.

Inputs:
- PLAN.md (frozen spec), AGENTS.md (rules, decisions D1–D2, invariants I1–I10)
- MILESTONES.md: milestone <MN> acceptance criteria
- The builder's report: the <MN> section of PROGRESS.md
- The change set: `git diff <previous-tag>..HEAD` AND `git status --short`
  (untracked files are not in the diff; any uncommitted file is itself a defect)

Do not trust the builder's report. Verify every claim yourself.

1. Run `make check` and record the actual output. Read the committed make check-live log.
2. For each acceptance criterion of <MN>: PASS / FAIL / UNVERIFIED, with evidence
   (command output, file:line, trace or payload excerpt). UNVERIFIED is not PASS.
3. For each invariant touched by this diff: is there a test, and does it exercise
   real behavior? Flag tests that only exercise mocks for behavior that depends on
   the real API, tests that assert nothing meaningful, and tests skipped, deleted,
   or loosened in this diff.
4. Open at least one trace AND its captured request payloads from this milestone.
   Check against PLAN.md §5.2 and AGENTS.md:
   - retrieved evidence or known_facts reaching staged-decompose PLANNING payloads (I1)
   - known_facts reaching either policy's FINAL-ANSWER payload (I2)
   - retrieved evidence MISSING from a final-answer payload (I2; evidence is required there)
   - different final-answer templates between iterative and staged-decompose (I2)
   - admitted evidence exceeding B, duplicate admissions, or a final-answer context
     differing from the admitted set (I3). Use the trace's admitted spans,
     NOT request-payload token totals.
   - call counts (I4)
   - any call interval falling outside the end-to-end interval (I7). Overlapping
     calls are expected; total < sum of call latencies is NOT a defect.
   - cost computed from model_input_tokens/output_tokens (not from evidence tokens)
   - which capture level the payload artifacts represent (application vs transport)
5. Hunt specifically for:
   - gold data reachable from pipeline/ code, including indirectly through utility
     functions, or gold fields (answers, support IDs, hop counts) in any prompt template (I6)
   - held-out data reachable without --final-report (I10)
   - cache keys missing any field of "Cache identity" (I8)
   - reasoning tokens added on top of output_tokens in cost (double counting)
   - incomplete responses or API errors scored as valid answers
   - hardcoded numbers or results that should come from runs
   - scope creep, or deviations from PLAN.md not listed in PROGRESS.md
6. Check that the reported API spend is plausible against the token counts in the traces.

7. Data access boundaries (AGENTS.md): any gold or held-out data reaching
   query-time code, probe query generation, or Diagnoser/Proposer inputs beyond
   what the boundary table allows.
8. Evidence metrics: are primary metrics computed on ADMITTED evidence, with
   partial (truncated) supports counted as not available?
9. M5 only: does the `pre-heldout` tag predate every final-report run (check
   commit order and report timestamps)? Does every evaluated selection match
   reports/frozen_selections.json exactly?

Output:
- A verdict table: criterion / invariant -> PASS | FAIL | UNVERIFIED -> evidence
- Defects ordered by severity (validity-breaking first)
- Overall: APPROVE only if no required item is FAIL or UNVERIFIED. Otherwise
  REQUEST CHANGES, unless the owner has formally waived the item in PROGRESS.md.
Be concise. No praise.
```

**Reviewer prompt (M0 variant)**

```
You are an independent reviewer. You did not write this work. Do not modify any files.
Inputs: PLAN.md, AGENTS.md, MILESTONES.md (M0 criteria), the M0 section of
PROGRESS.md, `git diff base..HEAD`, and `git status --short`.

Verify directly, do not trust the report:
1. Smoke test: open reports/m0_smoke_raw.jsonl. Are these real API responses
   (request IDs, real usage objects)? Do the summary numbers match the raw data?
   Is cost computed without double counting reasoning tokens? Are incomplete
   responses or errors recorded rather than dropped? Is the logprobs rejection
   recorded verbatim?
2. Structured output: is schema adherence computed from the raw responses?
3. Data: recompute #paragraphs and the unmapped-support count from the files.
   Verify the splits are disjoint (recompute hashes and intersections) and
   stratified by hop count. Check that the gold support texts in eval/golden.json
   actually support the answers, for at least one question.
4. Fork assessment: spot-check at least two file:line citations in the cloned repo.
   Do they show what the report claims? Is criterion (c) backed by a real call?
5. Confirm no pipeline logic was implemented (scope).

Output: verdict table (criterion -> PASS | FAIL | UNVERIFIED -> evidence),
defects by severity. APPROVE only if no required item is FAIL or UNVERIFIED;
otherwise REQUEST CHANGES. Be concise.
```

**Fix loop:** paste the reviewer's FAIL and UNVERIFIED items into the builder session. Fix them, rerun Gate 1, then repeat Gate 2 on the new diff only.

---

## Gate 3: Human check (10–15 min)

1. **Read one trace by eye.** From M1 onward, pick a golden question and follow the queries, the retrieved paragraphs, and the answer. For M0, read the golden questions and their supports.
2. **Read Deviations and Open questions** in PROGRESS.md. Every deviation needs explicit approval or a revert.
3. **Spot-check one number:** recompute one metric in PROGRESS.md from the raw trace, raw response, or data file.
4. **Owner decisions:** fork/build (M0), A_min (M2), go/no-go (M3).

**Owner-decision handoff (every milestone)**
1. The builder commits its work and requests review (clean tree).
2. The independent reviewer approves (Gate 2).
3. The owner completes Gate 3, records any decision or waiver in PROGRESS.md, and commits it.
4. Verify `git status --short` is clean, then run `git tag mN-done`.
5. Start the next milestone from that tag.

---

## Golden questions

The three MuSiQue questions (2-, 3-, and 4-hop) are selected from the pilot split and hand-verified in M0 (`eval/golden.json`).

- **Offline regression (`make check`)** uses fixtures or recorded responses. It checks structure: correct IDs, metric calculations, call counts, budget compliance, and trace and payload completeness.
- **Live run (`make check-live`)** checks that the real pipeline works end to end on at least one golden question.
- Neither asserts that the model retrieves every support or answers correctly. That is what the experiments measure.

---

## Severity guide

| Severity | Examples | Action |
|---|---|---|
| **Validity-breaking** | Information leak into the control, evidence missing from the final answer, gold or held-out data reachable, budget not enforced, wrong evidence mapping | Block; fix first |
| **Measurement** | Latency misses a call, reasoning tokens double counted, errors scored as answers, stale cache | Block |
| **Scope / deviation** | An unlisted PLAN.md change, an extra feature, uncommitted files | Revert or approve explicitly |
| **Quality** | Messy code, missing docstring | Note it; fix only if cheap |
