# Plan: A RAG Improvement Agent That Learns When Additional Retrieval Is Worth Its Cost

## 1. TL;DR

**Value proposition**
> An AI agent that diagnoses RAG failures, discovers better configurations through experimentation, and applies validated improvements to a runnable RAG pipeline.

Instead of manually choosing how much retrieval and reasoning an application needs, a Muse-powered agent measures a baseline pipeline, diagnoses its failures, experiments with alternatives, and selects the configuration that meets your accuracy bar at the lowest latency and cost. It then applies that configuration to the reference pipeline, and one held-out comparison against the baseline shows whether the change is an improvement.

**The loop (§5.3):** Evaluate → Diagnose → Optimize → Validate → Apply.

**What it searches.** Three dimensions, to find a corpus-specific configuration:
- retrieval strategy
- retrieval frequency: single-shot, upfront decomposition, or evidence-conditioned iterative
- Muse reasoning depth (`reasoning_effort`)

**Objective.** Accuracy-constrained optimization: meet a pre-set accuracy threshold, then minimize latency, then cost within a latency tolerance band (§5.3).

**What "Apply" means (§5.5).** The selected configuration is exported as one executable config file, and this project's reference pipeline runs it through one CLI entrypoint. Search and Apply share one code path, so any before/after difference comes from the configuration, not the implementation. Adapters for external pipelines are out of scope.

**Scope of adaptivity**
- **Corpus-level.** The MVP selects one configuration per corpus. Per-query routing is out of scope.
- **Retrieval always happens.** Every candidate retrieves at least once. Closed-book is a baseline only, so the optimizer decides how much *additional* retrieval is worth it, not whether to retrieve at all.

**Why it is not just another AutoRAG**
- **Agentic AutoRAG** tunes *how* to retrieve. It searches only single-round pipelines and fixes reasoning effort per project. Latency is not an objective.
- **Adaptive-RAG** routes queries across retrieval regimes with a trained classifier. It does not run a per-corpus search, and it does not trade retrieval frequency against model reasoning effort.
- **Our contribution is the combination:** a joint search over retrieval policy and reasoning effort, with latency as an explicit target, and evidence-conditioned multi-hop execution as one of the available pipelines.
- **Apply is verified, not just exported.** Exporting a runnable configuration is not new on its own (AutoRAG does it). What we add is a check: the applied configuration is measured once against the baseline on held-out data after the selection is frozen, and the result can be "no improvement."

**What the experiments test** (hypotheses, not promised results)
1. **Experiment 0:** how complete retrieval policies compare on multi-hop questions under a matched context budget, with a call-matched control separating evidence conditioning from extra model calls.
2. **Experiment A (before/after):** on held-out data, with each configuration run once after the selection is frozen, whether the applied configuration meets the accuracy bar at lower latency or cost than the fixed baselines. The headline is the designated baseline versus the applied configuration. "The baseline is already optimal" and "no qualifying configuration was found" are valid outcomes.
3. **Experiment B:** whether diagnosis-guided search, with the same number of full evaluations, qualifies more often and finds faster qualifying configurations than random search and than an LLM proposer without diagnosis. Null or negative results are reported as such. Optimization overhead is reported separately.

---

## 2. Origin and Platform

- **Origin:** conceived for the Meta Global AI Developer Hackathon (theme *Push the Frontier*, indie developer track). The event's deadlines no longer drive this plan. Milestones are ordered by dependency (§10), and having no deadline is not a reason to grow the MVP.
- **Models:**
  - Allowed by the event: the Muse Spark series, Muse Image, and SAM 3.1 via the Meta Model API, plus Meta open-weight models.
  - This project uses Muse Spark 1.3.

---

## 3. Research Findings

### 3.1 Muse / Meta Model API (verified)

**Access**
- Endpoint: `https://api.meta.ai/v1`. It offers Chat Completions, Responses, and Messages surfaces.
- LiteLLM has a native `meta/` provider route.
- Recommended model: Muse Spark 1.3.

**Not supported**
- No logprobs.
- No `n > 1` and no `stop`.
- Internal reasoning is not readable.

**`reasoning_effort` levels**
- `minimal`, `low`, `medium`, `high`, `xhigh`, and `max` (standard 1.3). `none` is rejected.
- Reasoning tokens affect both latency and cost.
- Docs are inconsistent on whether `xhigh` exceeds `high`, so we start with `minimal`, `medium`, and `high`.

**Reasoning-state continuity**
- Only the **Responses API** carries encrypted reasoning state across calls. It cannot be read, but it can be preserved. See §5.2 for how this is handled.

**Pricing and access**
- Standard mode costs $1.25 per million input tokens and $4.25 per million output tokens.
- Access has expanded beyond the US. Account-level access and billing are confirmed by the M0 smoke test.

### 3.2 Related work

| Work | What it does | Relation to this project |
|---|---|---|
| Mallen et al., ACL 2023 | Retrieve only for low-popularity entities | Motivation. Popularity does not transfer to private corpora. |
| FLARE, EMNLP 2023 | Retrieve when token confidence is low | **Cut.** It needs logprobs, which Muse does not expose. |
| IRCoT, ACL 2023 | Interleave retrieval with chain-of-thought for multi-hop QA | Basis for `iterative`, implemented through structured actions. |
| Adaptive-RAG, NAACL 2024 | A classifier routes each query to no, single, or multi-step retrieval | Closest work on timing adaptation. Per-query routing is not claimed. |
| AutoRAG / RAGBuilder | Greedy or Bayesian search over modular RAG configurations | Non-agentic configuration search. AutoRAG can also export its best pipeline as a runnable config, so exporting alone is not a contribution. |
| FlashRAG | Toolkit implementing many adaptive and iterative methods | Reference for policy logic. |
| Agentic AutoRAG, 2026 | Diagnoser + Proposer agent optimizes RAG configurations; accuracy–cost Pareto front | Closest optimizer. Single-round only, no latency objective, fixed reasoning effort. |

### 3.3 Agentic AutoRAG: facts that matter

**Paper findings**
- Its search space has no evidence-conditioned multi-round retrieval.
- The authors attribute their low MuSiQue ceiling (judge accuracy ≈ 0.33) to that limitation.
- Latency is listed as future work.
- An LLM proposer without the knowledge base or diagnosis performed close to the full agent. Our Experiment B tests the same question for our diagnosis.

**Code (MIT license, Python 3.12+, LiteLLM-based)**
- Supports custom exams.
- `reasoning_effort` is fixed at project level, not searched per trial.

**Benchmark repo (`Agentic-AutoRAG-Bench`)**
- Contains frozen exams, stratified splits, and random-search comparisons.
- `benchmark-prepare` rebuilds the pooled MuSiQue and MultiHop-RAG corpora from pinned Hugging Face revisions. The corpora themselves are not committed.

---

## 4. Positioning and Claims

**Contribution statement**
> A corpus-specific RAG improvement agent. It jointly searches retrieval configuration, retrieval frequency, and model reasoning depth; selects the configuration that meets an accuracy bar at the lowest latency and cost; and applies it to a runnable reference pipeline. A single pre-registered held-out comparison against the baseline then shows whether the change is an improvement.

**Why an agent, and where its autonomy stops**

A benchmark measures configurations that someone else chose. A configuration search tool hands back a recommendation. This system decides what to measure next from diagnosed failures, and it carries its choice through to an executed, verified change. Its autonomy is bounded on purpose: the agent chooses experiments, but it does not define success.

- **The owner fixes, before any search:** the corpus and splits, the search space, the designated baseline (§6, Experiment A), A_min (by the pilot rule, §5.3), the selection rule and latency tolerance, the evaluation budget (5 per arm), the reproduction tolerance (§7), and spend caps. The owner also freezes the selection (the `pre-heldout` tag) before any held-out run.
- **The agent decides:** how to read failures and probe outcomes (Diagnoser), the counterfactual probe queries, and which configuration to evaluate next, with a rationale (Proposer).
- **Deterministic, with no model judgment:** metrics and failure classes (trusted evaluator), selection, export, reproduction checks, the held-out run, and the outcome label (§6, Experiment A).
- **Never done:** editing code, deploying, monitoring, per-query routing, or changing its own objective, budget, or threshold.

**We claim**
- Retrieval frequency and reasoning effort are searchable, corpus-dependent dimensions that existing optimizers leave fixed.
- Matched-budget measurements of how complete retrieval policies compare on multi-hop questions. If the call-matched control is run, we also claim whether evidence conditioning itself contributes.
- Small-budget evidence on whether diagnosis improves search over random search and over an LLM proposer without diagnosis.
- A measured before/after result for the applied configuration on held-out data, with each configuration run once after the selection is frozen, reported whatever the outcome.

**We do not claim**
- Deciding whether to retrieve at all (closed-book is not in the search space).
- Per-query routing (Adaptive-RAG), or iterative retrieval as new (IRCoT).
- Production readiness, deployment, or monitoring. Apply runs this project's reference pipeline only, and we do not claim the result transfers to other pipelines.
- An improvement, unless the pre-registered outcome rule (§6, Experiment A) yields `improved`. Even then, the label applies the selection rule to point estimates. Intervals are reported, and significance is not claimed.
- Statistical proof of search superiority without enough seeds.
- That Experiment 0 isolates evidence conditioning, **unless** the `staged-decompose` control is included.

**Hypotheses (to test, not assume)**
- Retrieval and reasoning can partly substitute for each other.
- Upfront decomposition may capture much of iterative retrieval's benefit at lower latency. If so, the optimizer should select it, and that is a valid result.
- With an equal number of full evaluations, diagnosis-guided search finds qualifying, faster configurations more often than random search. A null or negative result is reported as such.
- Per-question-type differences are analyzed after the fact to explain the corpus-level choice. They are not used for routing.

---

## 5. Design

### 5.1 Search space (MVP)

| Dimension | Values |
|---|---|
| Retriever | BM25, dense, hybrid (RRF) |
| Retrieval policy | once, decompose (≤3 sub-queries), iterative |
| Reasoning effort | minimal, medium, high |
| Top-k (per retrieval call) | 3, 5, 10 |
| Iterative hop cap | 2, 3 (iterative only) |

That gives 3 × 3 × 3 × (1 + 1 + 2) = **108 valid configurations**. The values are illustrative and are validated in the smoke test.

**Excluded from the search space**
- **Closed-book.** MuSiQue facts are likely memorized from Wikipedia, so a closed-book configuration could "qualify" through contamination and win on latency. That would be a misleading result.
- **Deferred:** model tier, chunking sweeps, rerankers.

**Fixed across trials:** model version, generation settings, answer-length target, embedding model, and infrastructure.

### 5.2 Retrieval policies and execution

| Policy | Implementation | Use |
|---|---|---|
| `closed-book` | No retrieval | Baseline only |
| `once` | One retrieval with the original question, then answer | Search + baseline |
| `decompose` | One call emits ≤3 sub-queries as structured output; retrieve in parallel; answer | Search + baseline |
| `iterative` | Evidence-conditioned loop (step contract below) up to the hop cap | Search + baseline |
| `staged-decompose` | **Same loop and number of calls as `iterative`, but query planning sees only the original question and previous queries.** No retrieved evidence and no `known_facts`. Implemented as a flag on the iterative loop. | Experiment 0 control only |

**Iterative step contract (structured output, not internal reasoning)**

```json
{
  "known_facts": ["The founder of Company X is Person Y."],
  "next_query": "Person Y university education",
  "action": "retrieve"
}
```

The loop is: question → propose query → retrieve → update `known_facts` → repeat until `"action": "answer"` or the hop cap → generate the grounded answer.

**Execution mode (same for every multi-call policy)**
- All calls go through the **Responses API**.
- **MVP default: stateless calls with explicit visible state.** No encrypted reasoning state is carried over, which keeps runs reproducible and model-agnostic. Information flow is defined per call type, because `known_facts` is derived from retrieved evidence and would otherwise leak into the control:

| Call | `iterative` receives | `staged-decompose` receives |
|---|---|---|
| Query planning (each hop) | question, previous queries, retrieved evidence so far, `known_facts` | **question and previous queries only** |
| Final answer | question + all accumulated retrieved evidence | question + all accumulated retrieved evidence |

The final-answer call is identical for both policies. `known_facts` is used only for planning, never passed to the answer step, so the answer step cannot advantage either policy.
- **Preserved reasoning state** (Responses continuity) is an optional variant, run only after the MVP is complete and reported separately. It changes both quality and token usage.
- The trace records the mode for every run.

### 5.3 The agent loop

| Step | What happens | Components | Split |
|---|---|---|---|
| **1. Evaluate** | Run the designated baseline from its config file and score it (trial 0) | `run_config`, trusted evaluator | validation |
| **2. Diagnose** | Classify failures, run capped counterfactual probes, summarize per question type | trusted evaluator, Diagnoser | validation |
| **3. Optimize** | Propose an unseen configuration, evaluate it, diagnose it; repeat until 5 evaluations are used | Proposer, `run_config`, evaluator, Diagnoser | validation |
| **4. Validate** | Apply the selection rule to the baseline and all trials, export the selection, verify reproduction (§5.5) | selection rule, exporter, CLI | validation |
| **5. Apply** | After the owner freezes the selection, run the baseline and the selection once each on held-out and compute the outcome label | `eval/final_report.py`, `run_config` | held-out |

Steps 2 and 3 are the agentic part. Steps 1, 4, and 5 are deterministic.

**Diagnoser (comparative, capped)**
- Classifies failed validation questions:
  - **Support miss:** not all annotated supporting paragraphs were retrieved.
  - **Generation failure (approximate):** all annotated supports were retrieved but the answer was wrong. Annotated supports are not proof of sufficiency, so this label is a diagnostic approximation.
  - **Timing-sensitive candidate:** after a failed `once` or `decompose` run, one follow-up query conditioned on the retrieved evidence recovers a missing support. This is conditional on the tested budget. It is evidence for the Proposer, not ground truth.
- Counterfactual probes are **capped at 10 failed questions per trial**.
- It also summarizes accuracy, latency, and tokens per question type.

**Proposer**
- Reads the diagnosis, the trial history (no configuration is repeated), the remaining budget, the threshold, and the selection rule.
- Starts from the baseline's results and diagnosis (trial 0).
- Proposes the next configuration with a rationale.
- Uses no external model-ranking knowledge base.

**Final selection (deterministic, matches the pitch)**

Candidates are the baseline (trial 0) and every evaluated trial, so on validation the selection never ranks below the baseline under this rule.
1. Keep configurations with validation accuracy ≥ **A_min**.
2. Let **L_min** be the lowest p50 latency among them. Keep those with p50 latency ≤ **1.10 × L_min**.
3. Among those, select the **lowest cost per query**.
4. If no configuration meets A_min, select the most accurate one and flag the result as non-qualifying.

The 10% tolerance is an engineering choice sized to hosted-API latency noise. It is not a statistical threshold.

**Threshold A_min** is set from the fixed baselines' results on a separate **pilot split**, fixed before any search runs, and identical for every method.
- **Use a practical value, not a fine-grained one.** For example, take the best fixed baseline's pilot accuracy rounded down to the nearest 5 points.
- **Acknowledge the uncertainty.** At n ≈ 100, one answer moves accuracy by 1 point, and the 95% interval is roughly ±10 points. A_min is an operating target, not an estimate of true accuracy.
- **Always report** actual accuracy on validation and held-out splits.

**Validate.** The selection rule is the validation verdict. If it selects the baseline, no change is applied, and the outcome is "baseline already optimal." If no candidate meets A_min, the selection is flagged non-qualifying (step 4). It is still exported and evaluated so the outcome can be reported. Validate uses the validation split only.

**Reporting.** Optimization overhead (Diagnoser, Proposer, and probe tokens, plus spend and wall-clock time) is always reported separately from deployed per-query cost.

### 5.4 Fork vs. build (decided at the M0 handoff)

**Fork Agentic AutoRAG only if all four hold without rewriting its evaluator:**
1. A multi-round execution adapter can be added (`decompose`, `iterative`, `staged-decompose`).
2. `reasoning_effort` can become a per-trial dimension.
3. Muse works through its LiteLLM credential and model configuration.
4. One configuration can be loaded from a config file and run standalone through the same code path its search uses (§5.5).

**Otherwise:**
- Keep the benchmark repo's data preparation and splits.
- Build a thin policy runner with this contract:
  `answer(question, config) -> {answer, retrieved_ids, calls, tokens (incl. reasoning), latency, trace}`
  `run_config` (§5.5) wraps it.

If forking, use Python 3.12+ and `uv`.

### 5.5 Apply: config file, CLI, and verification

**Config file (the export format)**
- One JSON file per configuration, canonically serialized (sorted keys, UTF-8). From M1 on, every run uses one: fixed baselines, Experiment 0 policies, search trials, and the selection.
- It holds every setting that affects pipeline behavior:
  - `schema_version`
  - `pipeline`: retriever, policy, `reasoning_effort`, top-k, hop cap
  - `run_mode`: search or Experiment 0, with B (and its per-call shares in Experiment 0 mode)
  - `fixed`: model ID and version, generation parameters and token limits, embedding model and version, prompt-template IDs and versions, execution-policy version
  - `fingerprints`: dataset version, corpus fingerprint, retrieval-index fingerprint
  - `provenance` (excluded from the hash): source arm, seed and trial, selection-rule trace, validation results file and its hash, git commit
- **Config hash** is the hash of the file without `provenance`. Those fields are the pipeline-result cache identity minus the question ID (AGENTS.md), so the file alone determines a run, apart from the question.
- **No hidden state.** Loading is strict. Missing or unknown fields, an unknown schema version, and fingerprint or template-version mismatches with the local corpus, index, or code are errors. Nothing is silently defaulted. Secrets come from `.env` and never appear in the file.

**CLI entrypoint (one)**
- `scripts/run_config.py --config FILE --split {pilot,validation} [--ids ID ...] --max-usd N [--no-cache]`. `--question TEXT` runs one ad-hoc question for the demo; it is not scored.
- It loads questions, runs them through the pipeline's single run function (`run_config`) inside the query-time guard, scores them with the trusted evaluator, and writes traces and a results file.
- It has no option that selects held-out data. Held-out runs go through `eval/final_report.py`, which calls the same `run_config` with the frozen config files.
- The search harness and the Experiment 0 runner call `run_config` too. No other code path executes a configuration (AGENTS.md I11).

**Applying a configuration**
1. **Export.** Selection writes the selected configuration to a config file. The applied selection (§6, Experiment B) is `configs/selected.json`. The fixed baselines are `configs/fixed_once.json` and `configs/fixed_iterative.json`.
2. **Verify on validation, before freezing.**
   - *Execution reproducibility (exact, pass/fail).* The file's hash equals the selected trial's hash. A fresh-process CLI run with the cache hits the pipeline-result cache for every validation question. Replaying the model outputs recorded in the search-time traces through the CLI reproduces their request payloads, retrieval calls, and admitted IDs exactly.
   - *Measurement stability (reported).* A `--no-cache` CLI run on validation is compared with the search-time results, metric by metric, against the reproduction tolerance (§7). A difference outside the tolerance is labeled `not_reproduced` and shown with the results. The selection never changes either way.
3. **Freeze.** The owner commits `reports/frozen_selections.json` with the config files and tags `pre-heldout`.
4. **Run on held-out.** `eval/final_report.py` runs the designated baseline and the applied selection, along with every other frozen configuration, once each (§7, "Held-out protocol"). It then computes the outcome label (§6, Experiment A). These are the only before/after numbers reported.

---

## 6. Experiments

### Experiment 0: Retrieval policy comparison (MuSiQue validation)

**Setup**
- Retriever and reasoning effort are fixed: **hybrid** retriever and **medium** effort, matching the fixed baselines in Experiment A. Execution mode is stateless, with the information flow in §5.2.
- **No early stopping in Experiment 0.** `iterative` and `staged-decompose` both run exactly **3 planning calls + 1 answer call** (3 retrievals). Early stopping stays enabled for `iterative` inside the optimization search space.
- One retrieved-context token budget **B** per question, counted across all retrieval calls. B is set from the generator's context budget, for example about 15 paragraphs' worth.
- B is enforced by truncating in tokens.

| Policy | Context budget | Model calls | Purpose |
|---|---|---|---|
| Closed-book | 0 | 1 | Memorization check |
| `once`, small | B/3 | 1 | Standard RAG |
| `once`, full | B | 1 | Does more context explain the gain? |
| `decompose` | B/3 per sub-query (≤ B) | 2 | Multiple queries, no conditioning, fewer calls |
| `staged-decompose` | B/3 per step (= B) | exactly 4 | **Call-matched control:** sequential planning without evidence |
| `iterative`, 3 hops | B/3 per hop (= B) | exactly 4 | Evidence-conditioned retrieval |

**How to read it**
- `iterative` vs. `staged-decompose` isolates **evidence conditioning** from **extra model calls**.
- If the control is cut, the claim narrows to a comparison of complete retrieval policies.

**What to report**
- Actual context tokens used and actual model calls.
- Support recall, all-support hit rate, accuracy, latency, and cost.

### Experiment A: Before/after, selected configuration vs. fixed baselines (held-out)

- Compare the predefined fixed baselines and the applied selection on untouched held-out questions. Each configuration is run once, after the selection is frozen (§7, "Held-out protocol").
- **Success** means meeting A_min at lower latency or cost. The highest accuracy is not required.
- **Before/after.** The headline is the designated baseline ("before") against the applied selection ("after"). The owner designates the baseline before any pilot result exists, either by name or by a stated rule (for example, "the fixed baseline that sets A_min").

**Fixed baselines (predefined, recorded before any optimization run)**

| Baseline | Retriever | Policy | Reasoning | Top-k | Hop cap |
|---|---|---|---|---|---|
| Fixed once | Hybrid | `once` | Medium | 5 | — |
| Fixed iterative | Hybrid | `iterative` | Medium | 5 per hop | 3 |

**Why these values.** They are the defaults a practitioner would plausibly pick, not tuned choices. Both are members of the 108-configuration space.

**If the optimizer selects one of them,** the honest result is "the default was already the best choice for this corpus." That is reported as such.

**Outcome label (pre-registered and computed, never written by hand)**

| Label | Condition, checked in order |
|---|---|
| `baseline_already_optimal` | The applied selection is the designated baseline (same config hash). |
| `no_qualifying_configuration` | No candidate met A_min on validation (§5.3, step 4). |
| `improved` | On held-out, the §5.3 selection rule applied to {baseline, selection} prefers the selection. This requires the selection to meet A_min on held-out. The report names the deciding step: accuracy bar, latency band, or cost. |
| `improvement_not_confirmed` | Any other case. |

The report always shows, for both configurations: held-out judged accuracy, EM, and F1; the paired accuracy difference with a 95% interval; p50 and p95 latency; cost per query; the three token quantities; and error counts. The validation-time numbers appear beside them, and every number is labeled with its split.

### Experiment B: Does diagnosis improve search?

This tests a hypothesis. The result is reported whatever its direction.

**Arms.** Each arm uses the same 108-configuration space, the same validation questions, the same A_min, and **5 full configuration evaluations** of its own choosing:
1. Random search (uniform, without replacement)
2. LLM proposer **without** diagnosis (sees only scores and history)
3. LLM proposer **with** diagnosis (full agent)

**Shared trial 0.** Every arm starts from the designated baseline, evaluated once and shared (§5.3, Evaluate). It is a selection candidate in every arm, is never re-proposed, and does not count toward the 5. The LLM arms see its results as their starting point, and arm 3 also sees its diagnosis.

**Search efficiency**
- Best selection-rule outcome after 5 evaluations: lowest qualifying latency, with cost inside the band.
- Fraction of seeds that found any qualifying configuration.
- Number of trials needed to first qualify.
- Fraction of seeds whose selection the selection rule prefers over the baseline (on validation).

The qualifying fraction and trials-to-qualify count only each arm's own 5 evaluations, so a baseline that already qualifies does not make them trivial. The selection-rule outcome includes trial 0.

**Optimization efficiency**
- Total optimization tokens, spend, and wall-clock time per arm, including diagnosis and probes.

**Held-out check**
- Each arm's selection is evaluated on the held-out set: does it still meet A_min, and at what latency and cost? This happens in the single held-out session (§7). Each unique configuration runs once, the results are shared with Experiment A, and they never revise any selection.

**Applied selection.** The full agent's selection from the primary seed (seed 0, fixed before any search) is exported as `configs/selected.json` and used for Apply. Other seeds feed only Experiment B statistics, so the applied configuration is never picked across seeds after the fact.

**Fair latency.** A configuration evaluated by several arms is measured once, and the shared measurement is reused.

**Seeds.** Use as many as the budget allows. Arm 2 has priority over extra seeds. With few seeds, the result is presented as a small-budget demonstration.

**Not done:** comparison under a matched total optimization-cost budget. The overhead is reported instead.

---

## 7. Evaluation Protocol

**Splits (MuSiQue)**
| Split | Size | Use |
|---|---|---|
| Pilot | ~100 | Smoke tests; calibrating B, A_min, and the reproduction tolerance (only fixed baselines run here, so the larger size is cheap) |
| Validation | ~100 | Experiment 0, all optimization, and Apply verification |
| Held-out | ~150–200 | Untouched until the single held-out session (below) |

**Evidence**
- Common interface: `{doc_id, paragraph_id, optional char_span}`.
- Metrics: **supporting-paragraph recall** and **all-support hit rate**.
- Annotated supports do not prove the retrieved passages are sufficient to answer.

**Corpus**
- A pooled, deduplicated paragraph corpus built with `benchmark-prepare` from pinned revisions.
- Never only the paragraphs packaged with each question.

**Leakage**
- No labels, gold evidence, hop counts, or correctness signals reach any query-time component.

**Latency**
- Record end-to-end wall-clock time, retrieval calls, model calls, and input, output, and reasoning tokens, plus billed cost.
- Warm up before measuring. Repeat where practical on pilot and validation; held-out runs are single-pass.
- Report p50 and p95 with sample sizes; p95 is indicative only.

**Scoring**
- A strict, fixed LLM-judge prompt, plus EM and F1.

**Held-out protocol**
- **Freeze first.** `reports/frozen_selections.json` lists the fixed baselines, the designated baseline, every arm's and seed's selection with its full history, the applied selection, A_min, the reproduction tolerance, the verification results, every config file's hash, and the estimated held-out spend. The owner commits it and tags `pre-heldout` before any held-out run.
- **One session.** `eval/final_report.py` runs each unique config hash once on held-out. Experiment A, the Experiment B held-out check, and the before/after report all read those results.
- **Fair conditions.** Configurations are interleaved by question, so API-latency drift affects all of them equally. Warm-up uses pilot questions. An interrupted session resumes only the questions with no recorded result.
- **Same code.** The execution-path code must be identical to `pre-heldout`.
- **No feedback.** Held-out results never revise a selection, A_min, a tolerance, or the outcome rule. If a defect invalidates them, the owner decides what happens next. Any rerun is reported next to the original, never in place of it.

**Reproducibility vs. measurement stability**
- **Execution reproducibility** is exact and pass/fail: the same config hash, code path, and cache keys, plus byte-identical payloads, retrieval calls, and admitted IDs when recorded model outputs are replayed. Retrieval and admission are deterministic given the queries; model outputs are not.
- **Measurement stability** is statistical. Hosted-model outputs and API latency vary between live runs, so accuracy, latency, and cost differ from run to run. No fixed tolerance is assumed. The reproduction tolerance for judged accuracy, p50 latency, and cost per query is derived from repeated `--no-cache` runs of the fixed baselines on pilot (M3). The owner approves it before any Apply verification it judges.
- Held-out runs are single-pass, so held-out numbers carry sampling intervals, not repeat variation.

---

## 8. Datasets and Demo

| Item | Status |
|---|---|
| **MuSiQue (answerable)** | **Essential.** All experiments. |
| MultiHop-RAG | Optional, after the MVP. Secondary results. |
| Custom upload + synthetic exam | Optional, after the MVP. |

**Demo: one improvement run, end to end, with measured results only**
1. **Baseline.** The designated baseline's config file and its measured validation accuracy, latency, and cost.
2. **Diagnosis.** Failure classes, probe outcomes, and the Diagnoser's summary for the baseline. An evidence trace on a curated validation question shows a support miss: each query, the retrieved and admitted IDs, and `known_facts` where present.
3. **Optimization.** Every evaluated configuration with the Proposer's rationale and its metrics, plus the Experiment B search curves against the random and no-diagnosis arms.
4. **Selection.** The selection-rule trace (which candidates qualified, L_min, the latency band, the cost tie-break) and a "why this configuration" card. The card is built from that trace and the recorded Proposer rationale, for example "decomposition matched iterative within the bar at lower latency." No model writes new claims at demo time.
5. **Apply.** The diff from the baseline config file to `configs/selected.json`, the CLI command, and the verification results (§5.5). One live CLI run on a single question is labeled as an illustration, not a measurement.
6. **Held-out before/after.** Baseline vs. selection, one run each, with intervals and the computed outcome label (§6, Experiment A).

**Every outcome has a view.** The outcome card has text for each of the four labels. Improvement language appears only under `improved`. "Baseline already optimal," "no qualifying configuration," and "improvement not confirmed" are shown as results, not errors.

Supporting views: the Pareto chart, and the Experiment 0 results with their interpretation label (MILESTONES.md M3).

All shown numbers are measured, read from result files, and labeled by split. The demo uses precomputed results plus one live pipeline execution.

**Caveat.** MuSiQue likely overlaps Muse's training data, so the closed-book baseline is always shown. Comparisons with Agentic AutoRAG's published numbers are directional only.

---

## 9. Scope (committed)

| Component | Status |
|---|---|
| MuSiQue via the benchmark repo | MVP |
| `once` / `decompose` / `iterative` + closed-book baseline | MVP |
| `staged-decompose` control (a flag on iterative) | MVP (low cost) |
| BM25 / dense / hybrid | MVP |
| `reasoning_effort` + top-k search | MVP |
| Experiments 0, A, B (three arms, small budget) | MVP |
| Diagnoser (probes capped) + Proposer | MVP |
| Config file + single CLI entrypoint (§5.5) | MVP |
| Apply: export, validation verification, held-out before/after | MVP (never cut) |
| Streamlit demo: evidence trace viewer, recommendation and outcome card, before/after view | MVP |
| MultiHop-RAG | Optional, after the MVP |
| Custom upload + synthetic exam | Optional, after the MVP |
| Preserved reasoning-state variant | Optional, after the MVP |
| `adaptive` gate, reranker, chunking, model tier | Future enhancement, not planned |
| Adapters for external pipelines, continuous monitoring, automatic deployment | Out of scope |
| Per-query routing | Cut |
| FLARE | Cut |

**MVP rule.** Optional work starts only after the MVP (M7) is accepted. If scope grows, cut optional work before expanding the MVP.

---

## 10. Milestones (dependency-based)

There is no calendar schedule. A milestone starts only when its prerequisites are tagged. MILESTONES.md defines each milestone's prerequisites, deliverables, and acceptance criteria.

M0 smoke test, data, fork assessment → M1 one question end to end, from a config file → M2 all policies and dimensions, judge, pilot calibration → M3 Experiment 0 and stability calibration → M4 agent loop → M5 Experiment B search, Apply verification, freeze → *owner tags `pre-heldout`* → M6 held-out final report → M7 demo

**Go/no-go after M3:** a reliable, repeatable comparison with interpretable metrics. A winning policy is not required.

**Cut order if effort or API spend runs over:**
1. Optional items
2. Extra Experiment B seeds
3. No-diagnosis arm (then narrow the claim to "diagnosis-guided vs. random")
4. Pareto chart polish

**Never cut:** Experiment 0's matched baselines, held-out evaluation, the random arm, the evidence trace demo, **Apply** (config export, CLI, validation verification), and the **held-out before/after comparison**.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| Fork's evaluator assumes one-pass pipelines | Decide at the M0 handoff; otherwise use the thin runner |
| Search and Apply diverge (a second code path, or settings outside the config file) | One run function; the config file is the full cache identity; strict loading; I11 tests; execution-path code frozen at `pre-heldout` |
| Selection optimism: the selected configuration's validation accuracy is biased upward, so held-out may not confirm it | Pre-registered outcome labels; "improvement not confirmed" is a reportable result; the validation re-run is shown |
| The hosted model changes or drifts between search and held-out runs | Record the model ID and response metadata in traces; interleave configurations on held-out; report the validation-to-held-out gap |
| Held-out cost grows with arms and seeds | Deduplicate by config hash; estimate held-out spend in the frozen file before tagging |
| `reasoning_effort` levels behave inconsistently | Start with minimal, medium, high; verify reasoning-token differences |
| No arm qualifies within 5 trials | Calibrate A_min on the pilot split; report qualifying-run rates and trials-to-qualify |
| Experiment B too small to be conclusive | Present it as a small-budget demonstration; prioritize the no-diagnosis arm over seeds |
| API cost | Cache by (config, question); capped probes; small splits; fixed budget at $1.25/$4.25 per million tokens |
| Latency noise | Warm-up, repeats, shared measurements, 10% tolerance band |
| Judge bias | Strict prompt; EM and F1 alongside |
| Contamination | Closed-book baseline always shown; closed-book excluded from the search space |
| Judges know Agentic AutoRAG or Adaptive-RAG | Cite both openly; claims scoped as in §4 |

---

## 12. Connection to the AI6122 Presentation

- **Once vs. Iterative:** measured in Experiment 0, including the call-matched control.
- **Active (FLARE):** a deployability lesson. Its trigger needs logprobs, which hosted reasoning APIs do not expose.
- **Adaptive-RAG:** the natural "what came next" slide.

The presentation is completed on its own terms first. Results are a bonus slide.

---

## 13. References

- Mallen et al. (ACL 2023). *When Not to Trust Language Models.*
- Jiang et al. (EMNLP 2023). *Active Retrieval Augmented Generation* (FLARE).
- Trivedi et al. (ACL 2023). *Interleaving Retrieval with Chain-of-Thought Reasoning* (IRCoT).
- Jeong et al. (NAACL 2024). *Adaptive-RAG.*
- Strand et al. (2026). *Agentic AutoRAG.* https://arxiv.org/abs/2610.08452
- Agentic AutoRAG code (MIT): https://github.com/Agentic-Systems-Lab/Agentic-AutoRAG
- Agentic-AutoRAG-Bench: https://github.com/lassebaerlandstrand/Agentic-AutoRAG-Bench
- Trivedi et al. (TACL 2022). *MuSiQue.*
- Tang & Yang (COLM 2024). *MultiHop-RAG.* https://github.com/yixuantt/MultiHop-RAG
- FlashRAG: https://github.com/RUC-NLPIR/FlashRAG
- Meta Global AI Developer Hackathon: https://dev.meta.ai/events/global-hackathon
- Meta Model API docs: https://dev.meta.ai/docs/
- LiteLLM Meta provider: https://docs.litellm.ai/docs/providers/meta

---

## Changelog

**rev 3.1 → rev 4 (RAG Improvement Agent)**
- Identity: from a configuration optimizer to an improvement agent with the loop Evaluate → Diagnose → Optimize → Validate → Apply. The limits of its autonomy are stated (§4).
- Apply (§5.5): one JSON config file per configuration, one CLI entrypoint, and one run function shared by search, the CLI, and the final-report evaluator. Exact execution-reproducibility checks and a measured stability check on validation precede the freeze.
- Experiment A carries the before/after comparison against an owner-designated baseline, with a pre-registered outcome label. Experiment B arms share a baseline trial 0. The applied selection is the full agent's primary seed.
- Held-out protocol (§7): freeze everything first, run one session with each unique configuration once, share the results across A, B, and before/after, and never feed them back.
- Execution reproducibility is separated from measurement stability. The tolerance comes from measured repeats, not a preset number.
- The calendar schedule and hackathon deadlines are replaced by dependency-based milestones (§10). The scope table separates the MVP from optional work and future enhancements.
- Experiment outcomes are phrased as hypotheses to test.

**rev 3 → rev 3.1**
- Closed the `known_facts` leak: `staged-decompose` planning sees only the question and previous queries. The final-answer call is identical for both policies and excludes `known_facts`.
- Experiment 0 runs exactly 3 planning calls + 1 answer call for both multi-call policies, with no early stopping. It uses the same hybrid retriever and medium reasoning effort as the fixed baselines.
- A_min is now a practical rounded threshold with its sampling uncertainty acknowledged. The pilot split grows to ~100 questions, since only fixed baselines run on it.
- Fixed baselines for Experiment A are predefined: hybrid retriever, medium reasoning, top-5 (per hop), hop cap 3 for iterative.

**rev 2.1 → rev 3 (frozen)**
- Title and pitch changed to "when **additional** retrieval is worth its cost." Closed-book is excluded from the search space because of contamination risk.
- Experiment 0 gains a `staged-decompose` call-matched control (a flag on the iterative loop). The causal claim is scoped to whether the control is included.
- Experiment B gains a no-diagnosis LLM arm, qualifying-run rate, trials-to-qualify, and an optimization-overhead report.
- Selection rule: A_min, then p50 latency within a 10% band, then lowest cost. Pitch, Proposer instructions, and success criteria are aligned.
- Execution mode specified: Responses API, stateless calls with visible state by default; preserved reasoning state is optional and reported separately.
- A_min calibrated on a separate pilot split. Diagnoser probes capped at 10 per trial. "Generation failure" labeled as an approximation, with support-recall and all-support-hit metrics.
- MultiHop-RAG and custom upload moved to optional. Per-query routing cut. The demo centers on the evidence trace and recommendation card.

**rev 2 → rev 2.1**
- Experiment B objective aligned with selection; corpus-level scope clarified; `decompose` capped at 3; shared context budget B in Experiment 0.

**rev 1 → rev 2**
- Official hackathon facts; FLARE cut (no logprobs); Adaptive-RAG added; expanded search space; matched baselines; counterfactual diagnosis; deterministic selection; schedule re-dated.
