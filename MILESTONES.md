# Milestones

M0 and M1 have full prompts. Later milestones list only acceptance criteria; their prompts are written after M1, using what M0 and M1 reveal.

**Before M0:** commit PLAN.md, AGENTS.md, MILESTONES.md, and REVIEW.md, then run `git tag base`. Every review diffs against the previous tag.

Every milestone prompt starts with:
> Read AGENTS.md and PLAN.md first. Follow AGENTS.md strictly.

---

## M0: Smoke test, data, fork assessment (Oct 28, morning)

**Prompt**

```
Read AGENTS.md and PLAN.md first. Follow AGENTS.md strictly.

Milestone M0. Goal: remove the unknowns before any pipeline code is written.
Do NOT implement pipeline logic in this milestone. Spend cap: --max-usd 2.

1. Muse API smoke test (scripts/smoke_muse.py)
   - First check the request/usage conventions in AGENTS.md against the official
     Meta Model API docs. If they differ, use the docs and report the difference.
   - Call muse-spark-1.3 via the Responses API:
       client.responses.create(model="muse-spark-1.3", input=..., reasoning={"effort": e})
     for e in [minimal, medium, high, xhigh], same short multi-step prompt, 3 repeats each.
     Record the raw usage object, input_tokens, output_tokens,
     output_tokens_details.reasoning_tokens, cached tokens if present,
     wall-clock latency, response status, and cost.
     Reasoning tokens are included in output_tokens: do not double count.
   - Test structured output via text.format with a JSON schema matching the
     iterative step contract in PLAN.md §5.2 (known_facts, next_query, action).
     Report schema adherence over the repeats.
   - Request logprobs using the documented Responses shape
     (include: ["message.output_text.logprobs"], per the docs) and record the
     exact rejection. Do not treat a top-level logprobs parameter as the test.
   - Record every incomplete response or API error as such. Never count it as a valid output.
   - Save raw responses to reports/m0_smoke_raw.jsonl and a summary to
     reports/m0_smoke.json. In PROGRESS.md, answer: does xhigh differ
     meaningfully from high in reasoning tokens and latency?

2. Data (MuSiQue answerable)
   - Clone lassebaerlandstrand/Agentic-AutoRAG-Bench and use its benchmark-prepare
     command with a pinned Hugging Face revision. Record the revision.
   - Build a pooled, deduplicated paragraph corpus. Report: #paragraphs,
     #duplicates removed, token-length distribution, and a corpus fingerprint (hash).
   - For every question, map each gold supporting paragraph to a corpus paragraph_id.
     Report the number of unmapped supports (target: 0) and how duplicates were resolved.
   - Create fixed splits with seed 42, stratified by hop count:
     pilot 100, validation 100, held-out 200. Store under eval/splits/, plus
     a file of split hashes. Verify the three splits are disjoint.
   - Select 3 golden questions from pilot (one 2-hop, one 3-hop, one 4-hop).
     Write eval/golden.json with question, answer, supporting paragraph_ids and full
     texts, so a human can verify them by eye.

3. Fork assessment (read-only; do not modify the cloned repo)
   - Clone Agentic-Systems-Lab/Agentic-AutoRAG. Answer the three fork criteria in
     PLAN.md §5.4, each with file:line evidence:
     (a) Can a multi-round execution adapter (decompose / iterative / staged-decompose)
         be added without rewriting the evaluator? Where would it hook in?
     (b) Can reasoning_effort become a per-trial dimension applied to every
         pipeline model call (AGENTS.md D1)? What changes?
     (c) Does Muse (LiteLLM meta/ route) pass its credential validation and model
         config? Try it with one real call.
     (d) Could exact request payloads be captured at one point (AGENTS.md "Request capture")?
   - Give an hour estimate for fork vs. thin runner, and a recommendation.
     The decision is mine. Do not start either path.

M0 is exempt from the shared wrapper and make check / check-live (AGENTS.md "M0 exception").
Finish per AGENTS.md "Finishing a milestone", then stop.
```

**Acceptance criteria**
- Raw and summary smoke reports exist with real numbers for all four effort levels.
- Usage fields are confirmed against the docs, with no double counting in cost.
- Structured-output adherence is reported, and the logprobs rejection is recorded verbatim.
- Incomplete responses or errors, if any, are recorded rather than dropped.
- Corpus stats and fingerprint are reported. Unmapped gold supports = 0, or each one is explained.
- Splits are disjoint and hashed. `eval/golden.json` is human-readable.
- The fork assessment answers (a)–(d) with file:line evidence and an hour estimate.

**Owner decision after M0:** fork or thin runner. Follow the owner-decision handoff in REVIEW.md: record the decision, commit, then `git tag m0-done`.

---

## M1: One question end to end (Oct 28, afternoon)

**Prompt**

```
Read AGENTS.md and PLAN.md first. Follow AGENTS.md strictly.
The fork/build decision is recorded at the top of PROGRESS.md. Use that path.

Milestone M1. Goal: run the 3 golden questions end to end through `once` and
3-hop `iterative` on muse-spark-1.3, with complete accounting. Spend cap: --max-usd 3.

Build only what this needs:
1. The LLM client wrapper with request capture (AGENTS.md "Architecture rules"),
   using the API conventions confirmed in M0.
2. Retrieval over the pooled corpus: BM25, dense (one local sentence-transformers
   model), hybrid via RRF. Only hybrid is used in M1, but all three must work.
3. Evidence admission and budget per AGENTS.md D3 and "Token quantities"
   (budget B; use B = 3000 tokens for M1, as a config value). Record
   retrieved_evidence_tokens, final_context_tokens, and model_input_tokens separately.
4. Policies: `once` and `iterative` (3 hops, stateless execution, step contract and
   information-flow table in PLAN.md §5.2). Medium effort for every pipeline call
   (D1), top-k 5. The final-answer payload includes accumulated retrieved evidence
   and excludes known_facts (I2).
5. Trace JSON + payload artifacts per run. A trusted evaluation step under eval/
   that computes, from trace and gold, the evidence metrics defined in AGENTS.md
   (admitted_support_recall, admitted_all_support_hit, partial_supports,
   raw_retrieval_recall) plus answer EM/F1. (The LLM judge comes in M2.)
6. Result cache with the full cache identity (AGENTS.md), plus --no-cache.
7. Tests: I2 partial (canary-based, on captured iterative final-answer payloads:
   evidence present, known_facts absent), I3, I6, I7, I8, I10.
   Wire up make check (no network), make check-live (one golden question,
   real API), and make check-all.

Then run all 3 golden questions under both policies, in search mode (D3). Write a
table in PROGRESS.md: per question and policy, admitted support recall,
all-support hit, partial supports, raw retrieval recall, EM/F1, model calls,
retrieval calls, input/output/reasoning tokens, latency, cost, response status.
Point me to the trace and payload files.

Finish per AGENTS.md, then stop.
```

**Acceptance criteria**
- `make check` passes offline. The `make check-live` log is committed.
- Six traces exist (3 questions × 2 policies), each with payload artifacts.
- I2 (M1 part) is verified on **real captured payloads**: `iterative` final-answer requests contain the retrieved evidence, and contain no `known_facts` field or summary. The cross-policy part of I2 is checked in M2.
- I3: the admitted evidence is ≤ B, has no duplicates, and the final-answer context equals the admitted set. Request-payload token totals are not used for this check.
- I7: every call interval lies within the end-to-end interval.
- Admitted support recall from the trace matches a hand check on one golden question, including any `partial` flag.
- **Evidence conditioning is checked in the captured payloads**, not inferred from changing query strings: each iterative planning payload after hop 1 contains the evidence admitted in earlier hops.
- The I10 test covers every entry point that exists so far.
- Spend stays within the cap.

---

## Later milestones: acceptance criteria only

**M2: All policies and dimensions (Oct 29)**
- `decompose` (≤3 sub-queries), the `staged-decompose` flag, and the closed-book baseline.
- All retrievers selectable. Per-trial `reasoning_effort` applied to all pipeline calls (D1), plus top-k and hop cap 2/3.
- Experiment 0 mode (no early stop) vs. search mode (early stop on).
- Tests I1 (canary on real staged planning payloads), I4, I5, I9 pass. I10 is extended to new entry points.
- **Full I2 across `iterative` and `staged-decompose`:** same final-answer template and structure, retrieved evidence included, `known_facts` excluded.
- I3 and I7 hold for `decompose` (concurrent retrievals, D3 admission order).
- Both D3 run modes are implemented. Experiment 0 mode fills shares of B without a top-k cap; search mode caps at `top_k` newly admitted paragraphs and over-fetches for backfill.
- **Budget verification.** Experiment 0 must verify actual admitted tokens against the assigned budget. Any material shortfall must be flagged (`budget_unmatched`), and such a run cannot be reported as budget-matched without qualification.
  - Set the shortfall tolerance from M0's paragraph-length statistics.
  - Add a test with a fixture that cannot fill its share, and assert that the run gets the flag.
- **LLM judge implemented and validated before calibrating A_min:**
  - versioned prompt, fixed model and effort (D2), deterministic output parsing
  - evaluation-score cache per AGENTS.md
  - validation on pilot: agreement with EM/F1, plus a human-read sample of at least 20 judge–EM disagreements, reported in PROGRESS.md
- Judged accuracy is the primary metric (D4). Judge cost is reported separately as evaluation cost.
- A pilot run of the fixed baselines, using judged accuracy, produces B calibration evidence and a proposed A_min. A_min is fixed only after owner approval and handoff (REVIEW.md).

**M3: Experiment 0 (Oct 30)**
- All six Experiment 0 policies on the validation split. The results table includes actual admitted tokens, the `budget_unmatched` rate per policy, and model calls.
- **Interpretation label in every Experiment 0 report and demo view:** "Experiment 0 compares retrieval policies at an equal context budget (budget-driven admission, no top-k cap). It does not measure the performance of configurations the optimizer searches (top-k ∈ {3, 5, 10}, search mode)." Experiment 0 and search-mode numbers are never shown in the same table without this distinction.
- Latency repeats use `--no-cache` on a subset; stability is reported.
- Go/no-go (owner): reproducible and interpretable results (PLAN.md §10).

**M4: Agent loop (Oct 31)**
- Diagnoser (probes capped at 10 per trial), Proposer, and the deterministic selection rule (PLAN.md §5.3). Optimizer calls use fixed model and effort (D2).
- Data access boundaries hold (AGENTS.md):
  - probe query generation runs inside the query-time guard
  - the Diagnoser receives evaluator outputs only
  - the Proposer receives summaries and metrics only
  - the I6 canary test covers Diagnoser and Proposer inputs
- Three arms runnable (random, LLM without diagnosis, full agent), with a 5-evaluation budget and shared measurements.
- Optimization overhead is logged separately from per-query cost.
- I10 is extended to optimizer and probe entry points.

**M5: Experiments A and B, export (Nov 1)**
- **Before any `--final-report` run:** save each arm's selected configuration, the full selection history, A_min, and the fixed baseline definitions to `reports/frozen_selections.json`. Commit and tag `pre-heldout`.
- Experiment B results: qualifying-run rate, trials to qualify, best qualifying latency, and overhead per arm.
- Held-out evaluation runs only through `eval/final_report.py`. It enforces I10: a committed frozen-selections file reachable from `pre-heldout`, and listed configurations only.
- Config export runs end to end from the exported file.

**M6: Demo (Nov 2)**
- Evidence trace viewer on a curated question, recommendation card, Pareto chart, search curves, and one live run.
- Every number shown is read from result files. Nothing is hardcoded.
