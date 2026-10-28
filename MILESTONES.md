# Milestones

Milestones are ordered by dependency, not by date. A milestone starts only when its prerequisite tags exist. Each one lists prerequisites, deliverables, and acceptance criteria. M0 and M1 also have full prompts. The owner writes later prompts after M1, using what M0 and M1 reveal.

**Before M0:** commit PLAN.md, AGENTS.md, MILESTONES.md, and REVIEW.md, then run `git tag base`. Every review diffs against the previous tag.

Every milestone prompt starts with:
> Read AGENTS.md and PLAN.md first. Follow AGENTS.md strictly.

**Dependency chain** (PLAN.md §10; workflow steps from PLAN.md §5.3)

| Milestone | Workflow step | Requires | Owner gate after it |
|---|---|---|---|
| M0 Smoke test, data, fork assessment | — | `base` | fork/build; designated baseline |
| M1 One question end to end | Evaluate (one question) | `m0-done` | — |
| M2 All policies and dimensions, judge, pilot calibration | Evaluate | `m1-done` | A_min, B |
| M3 Experiment 0 and stability calibration | Evaluate | `m2-done` | go/no-go; reproduction tolerance |
| M4 Agent loop | Diagnose, Optimize, Validate (code) | `m3-done` | — |
| M5 Experiment B search, Apply verification, freeze | Optimize, Validate, Apply (export and verify) | `m4-done` | freeze: `pre-heldout` |
| M6 Held-out final report | Apply (held-out before/after) | `m5-done` and `pre-heldout` | — |
| M7 Demo | all steps, presented | `m6-done` | — |

---

## M0: Smoke test, data, fork assessment

**Prerequisites:** the `base` tag on the commit that holds the four spec documents.

**Deliverables:** smoke-test reports, the prepared corpus and splits, `eval/golden.json`, and the fork assessment.

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
   - Clone Agentic-Systems-Lab/Agentic-AutoRAG. Answer the four fork criteria in
     PLAN.md §5.4 ((a)-(c), (e)) and the capture question (d), each with
     file:line evidence:
     (a) Can a multi-round execution adapter (decompose / iterative / staged-decompose)
         be added without rewriting the evaluator? Where would it hook in?
     (b) Can reasoning_effort become a per-trial dimension applied to every
         pipeline model call (AGENTS.md D1)? What changes?
     (c) Does Muse (LiteLLM meta/ route) pass its credential validation and model
         config? Try it with one real call.
     (d) Could exact request payloads be captured at one point (AGENTS.md "Request capture")?
     (e) Can one configuration be loaded from a single config file and run
         standalone through the same code path its search uses (PLAN.md §5.5)?
         Where would a CLI entrypoint hook in?
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
- The fork assessment answers (a)–(e) with file:line evidence and an hour estimate.

**Owner decision after M0:** fork or thin runner, and the designated baseline (PLAN.md §6, Experiment A), named or given by a stated rule before any pilot result exists. Follow the owner-decision handoff in REVIEW.md: record both decisions, commit, then `git tag m0-done`.

---

## M1: One question end to end

**Prerequisites:** `m0-done`, with the fork/build decision and the designated baseline recorded in PROGRESS.md.

**Deliverables:** the LLM wrapper, retrieval, admission, `once` and `iterative`, traces and payload artifacts, the trusted evaluator, the result cache, config files and the CLI entrypoint, `make check` / `make check-live`, and six golden traces.

**Prompt**

```
Read AGENTS.md and PLAN.md first. Follow AGENTS.md strictly.
The fork/build decision is recorded at the top of PROGRESS.md. Use that path.

Milestone M1. Goal: run the 3 golden questions end to end through `once` and
3-hop `iterative` on muse-spark-1.3, with complete accounting, executed from
config files through the CLI. Spend cap: --max-usd 3.

Build only what this needs:
1. The LLM client wrapper with request capture (AGENTS.md "Architecture rules"),
   using the API conventions confirmed in M0.
2. Retrieval over the pooled corpus: BM25, dense (one local sentence-transformers
   model), hybrid via RRF. Only hybrid is used in M1, but all three must work.
3. Evidence admission and budget per AGENTS.md D3 and "Token quantities"
   (budget B; use B = 3000 tokens for M1, as a config-file value). Record
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
7. Config files and the CLI (PLAN.md §5.5; AGENTS.md "Config files and one
   execution path"). One run function, run_config, executes a configuration
   loaded strictly from a JSON config file. scripts/run_config.py (--config,
   --split {pilot,validation}, --ids, --max-usd, --no-cache) calls it. Every
   trace records the config hash. No option selects held-out data.
   Record run_config's module path in PROGRESS.md.
8. Tests: I2 partial (canary-based, on captured iterative final-answer payloads:
   evidence present, known_facts absent), I3, I6, I7, I8, I10, and I11 (M1 part:
   round-trip, strict loading, CLI cache keys match the cache identity).
   Wire up make check (no network), make check-live (one golden question,
   real API), and make check-all.

Then run all 3 golden questions under both policies, in search mode (D3), through
scripts/run_config.py with two config files (configs/m1_once.json,
configs/m1_iterative.json). Write a table in PROGRESS.md:
per question and policy, admitted support recall, all-support hit, partial
supports, raw retrieval recall, EM/F1, model calls, retrieval calls,
input/output/reasoning tokens, latency, cost, response status.
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
- All six runs went through `scripts/run_config.py` from the two config files. Each trace's config hash equals its file's hash. The I11 round-trip and strict-loading tests pass.
- Spend stays within the cap.

---

## M2: All policies and dimensions, judge, pilot calibration

**Prerequisites:** `m1-done`.

**Deliverables:** every policy, retriever, and searched dimension, runnable from config files; both D3 run modes; the LLM judge; the fixed baselines as config files; and a pilot calibration report for B and A_min.

**Acceptance criteria**
- `decompose` (≤3 sub-queries), the `staged-decompose` flag, and the closed-book baseline, each run end to end on the golden questions through the CLI.
- All retrievers selectable from the config file. Per-trial `reasoning_effort` applied to all pipeline calls (D1), plus top-k and hop cap 2/3.
- Experiment 0 mode (no early stop) vs. search mode (early stop on).
- Tests I1 (canary on real staged planning payloads), I4, I5, I9 pass. I10 is extended to new entry points.
- **Full I2 across `iterative` and `staged-decompose`:** same final-answer template and structure, retrieved evidence included, `known_facts` excluded.
- I3 and I7 hold for `decompose` (concurrent retrievals, D3 admission order).
- Both D3 run modes are implemented. Experiment 0 mode fills shares of B without a top-k cap; search mode caps at `top_k` newly admitted paragraphs and over-fetches for backfill.
- **Budget verification.** Experiment 0 must verify actual admitted tokens against the assigned budget. Any material shortfall must be flagged (`budget_unmatched`), and such a run cannot be reported as budget-matched without qualification.
  - Set the shortfall tolerance from M0's paragraph-length statistics.
  - Add a test with a fixture that cannot fill its share, and assert that the run gets the flag.
- **Config coverage (I11).** All 108 search configurations, both fixed baselines, and closed-book are expressible as config files. The round-trip and strict-loading tests cover all of them offline. The fixed baselines are committed as `configs/fixed_once.json` and `configs/fixed_iterative.json`.
- **LLM judge implemented and validated before calibrating A_min:**
  - versioned prompt, fixed model and effort (D2), deterministic output parsing
  - evaluation-score cache per AGENTS.md
  - validation on pilot: agreement with EM/F1, plus a human-read sample of at least 20 judge–EM disagreements, reported in PROGRESS.md
- Judged accuracy is the primary metric (D4). Judge cost is reported separately as evaluation cost.
- A pilot run of the fixed baselines, through the CLI from their config files, using judged accuracy, produces B calibration evidence and a proposed A_min. A_min is fixed only after owner approval and handoff (REVIEW.md).

**Owner decision after M2:** approve A_min and B (REVIEW.md handoff).

---

## M3: Experiment 0 and stability calibration

**Prerequisites:** `m2-done`, with A_min and B recorded in PROGRESS.md.

**Deliverables:** Experiment 0 results on validation, a repeat-measurement report on pilot, and a proposed reproduction tolerance.

**Acceptance criteria**
- All six Experiment 0 policies on the validation split, each run through `run_config` from a config file. The results table includes actual admitted tokens, the `budget_unmatched` rate per policy, and model calls.
- **Interpretation label in every Experiment 0 report and demo view:** "Experiment 0 compares retrieval policies at an equal context budget (budget-driven admission, no top-k cap). It does not measure the performance of configurations the optimizer searches (top-k ∈ {3, 5, 10}, search mode)." Experiment 0 and search-mode numbers are never shown in the same table without this distinction.
- Latency repeats use `--no-cache` on a subset; stability is reported.
- **Stability calibration (pilot).** Both fixed baselines are re-run through the CLI with `--no-cache`, at least once beyond the M2 run. For each baseline and pair of runs, the report gives per-question answer agreement, the judged-accuracy difference, the p50 latency ratio, and the cost-per-query ratio.
- A proposed reproduction tolerance for judged accuracy, p50 latency, and cost per query, each with its derivation from the repeat data shown (PLAN.md §7). It is fixed only after owner approval and handoff (REVIEW.md), before any Apply verification.
- Go/no-go (owner): reproducible and interpretable results (PLAN.md §10).

**Owner decision after M3:** go/no-go, and approve the reproduction tolerance.

---

## M4: Agent loop (Evaluate → Diagnose → Optimize → Validate)

**Prerequisites:** `m3-done`, with a go decision and the reproduction tolerance recorded.

**Deliverables:** the Diagnoser, the Proposer, the selection rule, the outcome-label rule, three search arms with a shared trial 0, and export of selected configurations.

**Acceptance criteria**
- Diagnoser (probes capped at 10 per trial), Proposer, and the deterministic selection rule (PLAN.md §5.3). Optimizer calls use fixed model and effort (D2).
- Data access boundaries hold (AGENTS.md):
  - probe query generation runs inside the query-time guard
  - the Diagnoser receives evaluator outputs only
  - the Proposer receives summaries and metrics only
  - the I6 canary test covers Diagnoser and Proposer inputs
- Three arms runnable (random, LLM without diagnosis, full agent), with a 5-evaluation budget and shared measurements.
- **Trial 0** of every arm is the designated baseline: evaluated once, shared by all arms, a selection candidate in each, never re-proposed, and not counted in the 5. A test checks each arm's trial count from its trial log.
- Every trial executes through `run_config` from a config file. The I11 spy test covers the search harness.
- Selection writes the selected configuration's config file with `provenance`, and the round-trip test passes on it.
- The selection rule and the outcome-label rule (PLAN.md §6, Experiment A) are deterministic functions. Fixture tests cover every branch: a qualifying selection, the latency band, the cost tie-break, no qualifying configuration, and each of the four outcome labels with its deciding step (I12).
- Optimization overhead is logged separately from per-query cost.
- I10 is extended to optimizer and probe entry points.
- A live smoke run of all three arms on the golden questions, with a reduced budget of 2 trials per arm.

---

## M5: Experiment B search, Apply verification, freeze

**Prerequisites:** `m4-done`.

**Deliverables:** Experiment B runs on validation; every arm's and seed's selection exported; the applied selection (`configs/selected.json`) verified on validation; `eval/final_report.py` with offline tests; and `reports/frozen_selections.json`.

**Acceptance criteria**
- Experiment B results on validation: qualifying-run rate, trials to qualify, best qualifying latency, and overhead per arm. The trial logs show that every arm and seed used the shared trial 0 plus exactly 5 evaluations.
- The applied selection is the full agent's primary-seed (seed 0) selection, exported to `configs/selected.json`.
- **Execution reproducibility (PLAN.md §5.5, exact).** The file's hash equals the selected trial's hash. A fresh-process CLI run with the cache hits the pipeline-result cache for 100% of validation questions and reproduces the search-time metrics exactly. Replaying the model outputs recorded in the search-time traces reproduces their request-payload hashes, retrieval calls, and admitted IDs for every validation question. The logs are committed under `reports/`.
- **Measurement stability (PLAN.md §5.5, reported).** A `--no-cache` CLI run of `configs/selected.json` on validation is compared with the search-time results. Each metric's difference is reported against the owner-approved tolerance and labeled `reproduced` or `not_reproduced`. The selection is unchanged either way.
- `eval/final_report.py` exists, and its offline tests pass on a fixture split. They cover the I10 refusals (frozen file missing, uncommitted, or unreachable from the tag; an unlisted configuration; a second run of a config hash), the I11 execution-path code check, interleaving by question, and resuming without re-running. It has not been run on held-out data.
- `reports/frozen_selections.json` lists every arm's and seed's selection with its full history, A_min, the designated baseline, the fixed baseline definitions, the applied selection, every config file with its hash, the reproduction tolerance, the verification results, and the estimated held-out spend. It is committed together with `configs/`.

**Owner decision after M5:** freeze. After review, tag `m5-done` and `pre-heldout` on the same commit (REVIEW.md handoff).

---

## M6: Held-out final report (Apply)

**Prerequisites:** `m5-done` and `pre-heldout` on the same commit. No execution-path code has changed since `pre-heldout`.

**Deliverables:** one held-out session through `eval/final_report.py`, its run ledger and results, the Experiment A table, the Experiment B held-out check, and the before/after report with its outcome label.

**If a defect invalidates held-out results:** record it under Open questions and stop for the owner. Any rerun is reported next to the original, never in place of it.

**Acceptance criteria**
- `pre-heldout` predates every held-out run (commit order and report timestamps).
- Every unique config hash in `reports/frozen_selections.json` was run on held-out exactly once, in one session, interleaved by question, with warm-up on pilot questions only. The run ledger is committed.
- Execution-path code at the run commit is identical to `pre-heldout`, and `reports/frozen_selections.json` and `configs/` are unchanged since `pre-heldout`.
- The before/after report compares the designated baseline with `configs/selected.json` on held-out. It shows judged accuracy, EM, and F1; the paired accuracy difference with a 95% interval; p50 and p95 latency; cost per query; the three token quantities; and error and incomplete counts. Validation-time numbers appear beside them, and every number is labeled with its split.
- The outcome label is computed by the M4 function from the held-out results (I12), and the report names its deciding step. No text claims an improvement unless the label is `improved`.
- The Experiment A table and the Experiment B held-out check read the same held-out results. No configuration has two held-out results.
- Spend stays within the cap, split into pipeline, evaluation, and optimization.

---

## M7: Demo

**Prerequisites:** `m6-done`.

**Deliverables:** a Streamlit demo that reads result files only (PLAN.md §8).

**Acceptance criteria**
- Views, in workflow order: the baseline config and its measured validation performance; the diagnosis (failure classes, probe outcomes, Diagnoser summary) for the baseline and each trial; the optimization history (each evaluated config with the Proposer's rationale and metrics) and the Experiment B search curves; the selected config with its selection-rule trace and rationale; the Apply view (the config diff from baseline to selection, the CLI command, and the verification results); and the held-out before/after with its outcome label.
- Supporting views: the evidence trace viewer on a curated validation question, and the Pareto chart.
- Every number shown is read from result files and labeled with its split. Nothing is hardcoded.
- The outcome card renders each of the four outcome labels from fixtures (I12). The rationale card is built from the selection-rule trace and the recorded Proposer rationale. No model writes new claims at demo time.
- One live CLI run of an exported config on a single question, labeled "illustration, not a measurement." Its numbers never appear in a results table.
- Every Experiment 0 view carries the M3 interpretation label.

---

## After the MVP (optional, not milestones)

Start only after `m7-done`, in the order of PLAN.md §9: MultiHop-RAG, custom upload + synthetic exam, then the preserved reasoning-state variant. Each needs its own owner-written prompt and acceptance criteria. None may change frozen selections or reported held-out results.
