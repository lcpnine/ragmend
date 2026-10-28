# Agent Instructions

Standing rules for any coding agent working in this repo. Read this file and PLAN.md before every task.
(If your tool reads `CLAUDE.md` instead, it is a symlink to this file.)

## Source of truth

- **PLAN.md is frozen. Never edit it.** Only the owner revises it, as a new changelog revision.
- If a plan item turns out to be infeasible, ambiguous, or contradicted by real API or data behavior:
  1. Stop.
  2. Record it under **Open questions** in PROGRESS.md, with evidence (error output, file:line, numbers).
  3. Do not improvise a substitute design.
- Work only within the scope of the current milestone prompt. No extra features, no speculative abstractions, no refactoring of unrelated code.

### M0 exception

M0 makes direct API calls for its smoke test, so it is **exempt** from:
- the shared LLM-wrapper requirement
- `make check` and `make check-live`
- trace and payload capture

Its raw smoke-test artifacts and the M0-specific independent review serve as the equivalent gates. All standard requirements apply from M1 onward.

## Design decisions (owner-approved clarifications of PLAN.md)

- **D1. Scope of `reasoning_effort`.** The searched `reasoning_effort` applies to every model call inside the RAG pipeline: query planning, decomposition, and final answer. One value per configuration.
- **D2. Fixed settings outside the search.** Optimizer and evaluation calls are outside the searched config. The Diagnoser, Proposer, counterfactual-probe query generation, and the LLM judge use a fixed model and effort, defined once in config and logged.
- **D3. Evidence admission.** Admission works differently in the two run modes:

| | Experiment 0 mode | Search mode |
|---|---|---|
| What limits admission | **Budget-driven.** Each retrieval call admits new paragraphs until its share of B is filled. top-k is not applied. | **top-k-driven.** Each retrieval call admits at most `top_k` *newly admitted* paragraphs. B is only a safety ceiling. |
| Why | Matched budgets must actually be filled. MuSiQue paragraphs are short (~100 tokens), so a top-k cap would bind long before B. | top-k is a searched dimension. |

  Rules common to both modes:
  - **Backfill.** Paragraphs already admitted for the same question are skipped. To make backfill possible, the retriever over-fetches: `fetch_n = top_k + (number already admitted)` in search mode, and enough candidates to fill the share in Experiment 0 mode, capped at 50.
  - **Truncation.** The last admitted paragraph may be truncated in tokens, and is then marked `partial`.
  - **Ordering.** `decompose` admits its parallel sub-query results in sub-query order, so the result is deterministic.
  - **B is an upper bound**, not a guarantee. Always report the tokens actually admitted.
  - **Budget shortfall (Experiment 0 mode).** For each retrieval call and each run, record `shortfall = assigned share − admitted tokens`. If the shortfall exceeds the tolerance (set in M2 from M0's paragraph-length statistics), flag the run `budget_unmatched`. Flagged runs cannot be reported as budget-matched without qualification.
- **D4. Primary metric (from M2).** LLM-judged accuracy is the primary metric for A_min, selection, and all experiments. EM and F1 are secondary.

## Token quantities (never mix these)

| Quantity | Meaning | Used for |
|---|---|---|
| `retrieved_evidence_tokens` | Tokens of newly admitted, deduplicated evidence (D3) | Budget B (I3) |
| `final_context_tokens` | Evidence tokens assembled into the final-answer request | Reporting; must equal the admitted set |
| `model_input_tokens` | Billed input tokens across all model calls, including evidence repeated in planning calls | Pipeline cost |

Evaluation cost (judge) and optimization cost (Diagnoser, Proposer, probes) are accounted **separately** from pipeline cost.

## Evidence metrics

Primary metrics are computed on the evidence actually **admitted** and given to the answer generator. Evidence that was returned by the retriever but not admitted does not count.

| Metric | Definition |
|---|---|
| `admitted_support_recall` | Fraction of gold supporting paragraphs that were admitted **in full** |
| `admitted_all_support_hit` | 1 if every gold support was admitted in full, else 0 |
| `partial_supports` | Gold supports admitted only in truncated form. Counted as **not** available in the two metrics above, and reported separately. |
| `raw_retrieval_recall` | *Secondary.* Gold supports appearing among the returned candidates, admitted or not. |

## Data access boundaries

| Zone | Who | Gold access | Held-out access |
|---|---|---|---|
| **Query time** | Query planning, decomposition, retrieval, admission, answer generation, *and* counterfactual-probe query generation and retrieval | **None.** A runtime guard is active, and gold loaders raise. | None |
| **Trusted evaluator** | Scoring (metrics, judge), probe-recovery checks | Reads gold answers and support annotations | Only via the final-report evaluator |
| **Optimizer** | Diagnoser | Receives **evaluator outputs only**: per-question failure class, support-hit flags, which hop's support was missing, correctness, model answer. No gold answer text and no gold passages. | None |
| | Proposer | Receives diagnostic summaries and trial metrics only | None |

- Gold labels live under `eval/`. Code under `pipeline/` must never import from `eval/`.
- No query-time, optimizer, or probe prompt template may reference answer labels, support IDs, or hop counts.
- The **LLM judge prompt** (trusted evaluator) is the only template allowed to include the gold answer.
- **Counterfactual probes:** the probe's follow-up query is generated and retrieved inside the query-time guard. The trusted evaluator then checks, outside the guard, whether it recovered a missing support.

**Held-out**
- Only the dedicated final-report evaluator (`eval/final_report.py`) can load held-out questions or labels. No optimizer, probe, pipeline, or CLI entry point has any option to select held-out data.
- The final-report evaluator refuses to run unless `reports/frozen_selections.json` exists, is committed, and is reachable from the `pre-heldout` tag.
- It evaluates **only** the predefined baselines and the configurations listed in that file, **each unique config hash at most once**, in one session (PLAN.md §7, "Held-out protocol"). An interrupted session resumes only questions with no recorded result. Recorded results, including errors, are never re-run.
- It refuses to run if execution-path code (`pipeline/`, prompt templates, the lockfile) differs from `pre-heldout`.
- Held-out results never feed back into selection, A_min, any tolerance, or the outcome rule.

## Architecture rules

**One LLM client wrapper (from M1).** All pipeline, optimizer, and judge model calls go through it.

Muse Responses API conventions (verify in M0; if reality differs, report it):
- Request: `client.responses.create(model=..., input=..., reasoning={"effort": ...})`. Structured output goes through `text.format`.
- Usage fields: `usage.input_tokens`, `usage.output_tokens`, `usage.output_tokens_details.reasoning_tokens`, and cached input tokens if reported.
- `reasoning_tokens` is **already included** in `output_tokens`. Never add it again.

Per call, the wrapper records:
- the call's role (pipeline / optimizer / judge)
- model ID, effort, and API surface
- token counts, cost (USD), and response status
- request ID, prompt-template ID and version
- start and end timestamps relative to the run start, from a monotonic clock

Incomplete responses and API errors are recorded as such and **never** scored as valid answers.

**Request capture**
- The wrapper writes the **exact application-level request payload** (the final request body handed to the SDK) to a payload artifact: gzipped JSONL, keyed by request hash.
- If capturing the outbound HTTP body at the transport layer is easy, prefer it. Either way, state in PROGRESS.md which level is captured.
- Leak tests inspect captured payloads, not code paths.

**Traces.** Every pipeline run emits a JSON trace with:
- the config, its config hash, the run mode (Experiment 0 / search), and the git commit
- every model call: payload hash, component summary, parsed output (so a run can be replayed, I11), usage, timestamps
- every retrieval call: query, returned IDs, admitted IDs with tokens and full/partial flag, timestamps
- the final answer
- totals: calls, the three token quantities, latency, cost

**Config files and one execution path (from M1)** (PLAN.md §5.5)
- Every pipeline run is defined by one JSON config file. Its config hash (excluding `provenance`) covers every field of the pipeline-result cache identity except the question ID.
- Loading is strict. Missing or unknown fields, unknown schema versions, and fingerprint or template-version mismatches are errors. No behavior-affecting setting may come from defaults, environment variables, or globals outside the file. Only secrets come from `.env`.
- One run function, `run_config`, executes configurations. M1 records its module path in PROGRESS.md. The CLI (`scripts/run_config.py`), the search harness, the Experiment 0 runner, and `eval/final_report.py` all call it. No other code path executes a configuration. Counterfactual probes reuse the retriever, but they are diagnostics, not configuration runs.
- Selected configurations are written by selection code and never edited after export.

**Caches (two, kept separate)**

*Pipeline-result cache.* Keyed by a hash of:
- the full pipeline configuration and run mode
- question ID and dataset version
- model ID and version
- corpus and retrieval-index fingerprint
- embedding model and version
- prompt-template versions
- generation parameters and token limits
- execution-policy version

The config file holds every field above except the question ID.

*Evaluation-score cache.* Keyed by:
- the pipeline-result hash (a hash of the result content, so a re-run that produces a different answer is re-scored)
- judge model and version, effort
- judge prompt version and scoring rubric version

**Cache use**
- Reusing a cached pipeline result across Experiment B arms is intended; the measurement is shared on purpose. This includes the shared trial-0 baseline.
- Latency repeats and Apply's live re-run use `--no-cache`, which neither reads nor overwrites the pipeline-result cache.
- API-side prompt caching is measured through the cached-token count.

**Splits.** Pilot, validation, and held-out are fixed files created once with a fixed seed. Held-out access follows "Data access boundaries" above.

**Spend guard.** Every API-calling command takes `--max-usd` and aborts at the cap.

**Secrets.** Keys live in `.env`. Never log keys or write them into payload artifacts.

## Plan invariants

Each invariant must have an automated test once the relevant code exists.

| ID | Invariant | How it is tested |
|---|---|---|
| I1 | `staged-decompose` **planning** payloads contain only the original question + previous queries. No retrieved text, no `known_facts`. | Canary test: fixture paragraphs contain unique canary strings; assert no canary appears in any staged planning payload. |
| I2 | The **final-answer** payload has the same structure for `iterative` and `staged-decompose`: question + admitted evidence, **no `known_facts`**. Evidence must be present. | Evidence canaries present, `known_facts` content absent, same template ID across the two policies. |
| I3 | `retrieved_evidence_tokens` ≤ B under D3. The final-answer context equals the admitted set. No paragraph is admitted twice. | Sum the admitted spans recorded in the trace (not request-payload tokens). Check uniqueness and that the final-answer request contains exactly the admitted spans. |
| I4 | In Experiment 0 mode, `iterative` and `staged-decompose` make exactly 3 planning calls + 1 answer call. No early stop. | Count calls in the trace. |
| I5 | `decompose` emits ≤ 3 sub-queries. | Schema + trace check. |
| I6 | No query-time component, including probe query generation, can read gold data. | Gold loaders raise inside the guard, both directly and through a utility wrapper. Template scan for gold field names in every template except the judge's. Diagnoser and Proposer inputs contain no gold answer text or passages (canary on gold fields). |
| I7 | Reported latency = end-to-end wall clock from a monotonic timer that wraps the whole run. | Every call interval lies within [0, total]. Do **not** require total ≥ sum of call latencies; calls may overlap. |
| I8 | Both caches include every field of their identities. | Changing any single field produces a cache miss. |
| I9 | Retrieval runs over the pooled, deduplicated corpus. | Index size = corpus size. Retrieved IDs can lie outside the question's packaged paragraphs. |
| I10 | Held-out data is loadable only by the final-report evaluator, only with a committed frozen-selections file reachable from `pre-heldout`, only for the listed configurations, and at most once per config hash. | Every other entry point, including the CLI, fails to load held-out data. The final evaluator refuses when the file is missing, uncommitted, or not reachable from the tag. It also refuses any unlisted configuration and a second run of a config hash already in its ledger. |
| I11 | One execution path, and the config file is complete. Search, Experiment 0, the CLI, and the final-report evaluator execute configurations only through `run_config`. Apart from the question, the config file alone determines a run. | Round-trip: load → re-export is byte-identical, and the hash is unchanged. The CLI computes the same pipeline-result cache keys as the harness, so a fresh-process cached run hits 100%. Replaying recorded model outputs reproduces request-payload hashes, retrieval calls, and admitted IDs. A spy test shows every caller reaches `run_config`. Strict loading rejects each missing field, unknown field, and fingerprint mismatch. The final evaluator refuses when execution-path code differs from `pre-heldout`. |
| I12 | Improvement claims are computed. The outcome label comes only from applying the pre-registered rule (PLAN.md §6, Experiment A) to recorded results. No report or demo view uses improvement language unless the label is `improved`. | Fixture tests for each of the four labels and each deciding step (accuracy bar, latency band, cost). The demo's outcome card renders each label from fixtures. |

## Testing rules (from M1)

| Command | Contents | Network |
|---|---|---|
| `make check` | Unit tests, invariant tests, deterministic golden regression (fixtures or recorded responses) | None |
| `make check-live` | Real Muse API integration tests on golden questions, with a small `--max-usd` | Yes |
| `make check-all` | Both | Yes |

- Every milestone from M1 that touches model calls includes at least one live test. The builder runs `make check-live` once per milestone and commits its log under `reports/`.
- The golden regression checks **structure**: IDs, metric calculations, call counts, budget compliance, and trace and payload completeness. It does not assert that the model succeeds.
- Never skip, delete, or loosen an existing test to make a milestone pass. If a test is wrong, explain why in PROGRESS.md and leave the change for review.

## Finishing a milestone

1. Complete the implementation and tests.
2. Append a section to **PROGRESS.md** with:
   - what was built (files, entry points)
   - how to run it (exact commands)
   - the `make check` result and the path to the `make check-live` log
   - acceptance criteria, each PASS/FAIL with evidence
   - deviations from PLAN.md (if any) and why
   - open questions
   - API spend, split into pipeline, evaluation, and optimization
3. Commit all changes, including PROGRESS.md and reports.
4. Verify that `git status --short` is clean.
5. **Stop and request independent review.** Do not start the next milestone. Do not create tags. Owner decisions and tags follow REVIEW.md.
