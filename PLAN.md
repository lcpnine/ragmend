# Meta Hackathon Plan: A RAG Optimizer That Learns When Additional Retrieval Is Worth Its Cost

## 1. TL;DR

**Pitch**
> A RAG optimizer that learns when additional retrieval is worth its cost.
> Instead of manually choosing how much retrieval and reasoning an application needs, a Muse-powered agent evaluates candidate pipelines, diagnoses their failures, and discovers the configuration that meets your accuracy bar at the lowest latency and cost.

**What it does.** A Muse-powered agent searches three dimensions to find a corpus-specific configuration:
- retrieval strategy
- retrieval frequency: single-shot, upfront decomposition, or evidence-conditioned iterative
- Muse reasoning depth (`reasoning_effort`)

**Objective.** Accuracy-constrained optimization: meet a pre-set accuracy threshold, then minimize latency, then cost within a latency tolerance band (§5.3).

**Scope of adaptivity**
- **Corpus-level.** The MVP selects one configuration per corpus. Per-query routing is out of scope.
- **Retrieval always happens.** Every candidate retrieves at least once. Closed-book is a baseline only, so the optimizer decides how much *additional* retrieval is worth it, not whether to retrieve at all.

**Why it is not just another AutoRAG**
- **Agentic AutoRAG** tunes *how* to retrieve. It searches only single-round pipelines and fixes reasoning effort per project. Latency is not an objective.
- **Adaptive-RAG** routes queries across retrieval regimes with a trained classifier. It does not run a per-corpus search, and it does not trade retrieval frequency against model reasoning effort.
- **Our contribution is the combination:** a joint search over retrieval policy and reasoning effort, with latency as an explicit target, and evidence-conditioned multi-hop execution as one of the available pipelines.

**What must be shown**
1. **Experiment 0:** how complete retrieval policies compare on multi-hop questions under a matched context budget, with a call-matched control separating evidence conditioning from extra model calls.
2. **Experiment A:** on held-out data, the selected configuration meets the accuracy bar at lower latency or cost than fixed baselines.
3. **Experiment B:** with five full evaluations each, diagnosis-guided search qualifies more often and finds faster qualifying configurations than random search and than an LLM proposer without diagnosis. Optimization overhead is reported alongside.

---

## 2. Hackathon Context (official, verified)

- **Event:** Meta Global AI Developer Hackathon. Virtual, worldwide, 10 days, $1M prize pool.
- **Theme:** *Push the Frontier.* It could also be framed as *Build for Your World*, since RAG pipelines are a problem I know firsthand from industry.
- **Track:** Indie developer. Judged on creativity, technical ambition, and whether it works.
- **Models:**
  - Allowed: the Muse Spark series, Muse Image, and SAM 3.1 via the Meta Model API, plus Meta open-weight models.
  - This project uses Muse Spark 1.3.
- **Deadline:** Nov 4, 9:00 PM ET, which is **Nov 5, 10:00 AM SGT**.
- **Internal target:** feature freeze Nov 3, submit Nov 4 (SGT).

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
- Access has expanded beyond the US. Account-level access and billing are confirmed by the Day 1 smoke test.

### 3.2 Related work

| Work | What it does | Relation to this project |
|---|---|---|
| Mallen et al., ACL 2023 | Retrieve only for low-popularity entities | Motivation. Popularity does not transfer to private corpora. |
| FLARE, EMNLP 2023 | Retrieve when token confidence is low | **Cut.** It needs logprobs, which Muse does not expose. |
| IRCoT, ACL 2023 | Interleave retrieval with chain-of-thought for multi-hop QA | Basis for `iterative`, implemented through structured actions. |
| Adaptive-RAG, NAACL 2024 | A classifier routes each query to no, single, or multi-step retrieval | Closest work on timing adaptation. Per-query routing is not claimed. |
| AutoRAG / RAGBuilder | Greedy or Bayesian search over modular RAG configurations | Non-agentic configuration search. |
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
> An autonomous, corpus-specific RAG optimizer that jointly searches retrieval configuration, retrieval frequency, and model reasoning depth, and selects the configuration that meets an accuracy bar at the lowest latency and cost, producing an evaluated, runnable configuration without manual tuning.

**We claim**
- Retrieval frequency and reasoning effort are searchable, corpus-dependent dimensions that existing optimizers leave fixed.
- Matched-budget measurements of how complete retrieval policies compare on multi-hop questions. If the call-matched control is run, we also claim whether evidence conditioning itself contributes.
- Small-budget evidence on whether diagnosis improves search over random search and over an LLM proposer without diagnosis.

**We do not claim**
- Deciding whether to retrieve at all (closed-book is not in the search space).
- Per-query routing (Adaptive-RAG), or iterative retrieval as new (IRCoT).
- Production readiness. The output is an evaluated, runnable configuration.
- Statistical proof of search superiority without enough seeds.
- That Experiment 0 isolates evidence conditioning, **unless** the `staged-decompose` control is included.

**Hypotheses (to test, not assume)**
- Retrieval and reasoning can partly substitute for each other.
- Upfront decomposition may capture much of iterative retrieval's benefit at lower latency. If so, the optimizer should select it, and that is a valid result.
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
- **Preserved reasoning state** (Responses continuity) is an optional variant, run only if time permits and reported separately. It changes both quality and token usage.
- The trace records the mode for every run.

### 5.3 The agent

**Diagnoser (comparative, capped)**
- Classifies failed validation questions:
  - **Support miss:** not all annotated supporting paragraphs were retrieved.
  - **Generation failure (approximate):** all annotated supports were retrieved but the answer was wrong. Annotated supports are not proof of sufficiency, so this label is a diagnostic approximation.
  - **Timing-sensitive candidate:** after a failed `once` or `decompose` run, one follow-up query conditioned on the retrieved evidence recovers a missing support. This is conditional on the tested budget. It is evidence for the Proposer, not ground truth.
- Counterfactual probes are **capped at 10 failed questions per trial**.
- It also summarizes accuracy, latency, and tokens per question type.

**Proposer**
- Reads the diagnosis, the trial history (no configuration is repeated), the remaining budget, the threshold, and the selection rule.
- Proposes the next configuration with a rationale.
- Uses no external model-ranking knowledge base.

**Final selection (deterministic, matches the pitch)**
1. Keep configurations with validation accuracy ≥ **A_min**.
2. Let **L_min** be the lowest p50 latency among them. Keep those with p50 latency ≤ **1.10 × L_min**.
3. Among those, select the **lowest cost per query**.
4. If no configuration meets A_min, select the most accurate one and flag the result as non-qualifying.

The 10% tolerance is an engineering choice sized to hosted-API latency noise. It is not a statistical threshold.

**Threshold A_min** is set from the fixed baselines' results on a separate **pilot split**, fixed before any search runs, and identical for every method.
- **Use a practical value, not a fine-grained one.** For example, take the best fixed baseline's pilot accuracy rounded down to the nearest 5 points.
- **Acknowledge the uncertainty.** At n ≈ 100, one answer moves accuracy by 1 point, and the 95% interval is roughly ±10 points. A_min is an operating target, not an estimate of true accuracy.
- **Always report** actual accuracy on validation and held-out splits.

**Reporting.** Optimization overhead (Diagnoser, Proposer, and probe tokens, plus spend and wall-clock time) is always reported separately from deployed per-query cost.

### 5.4 Fork vs. build (decide Oct 28)

**Fork Agentic AutoRAG only if all three hold without rewriting its evaluator:**
1. A multi-round execution adapter can be added (`decompose`, `iterative`, `staged-decompose`).
2. `reasoning_effort` can become a per-trial dimension.
3. Muse works through its LiteLLM credential and model configuration.

**Otherwise:**
- Keep the benchmark repo's data preparation and splits.
- Build a thin policy runner with this contract:
  `answer(question, config) -> {answer, retrieved_ids, calls, tokens (incl. reasoning), latency, trace}`

If forking, use Python 3.12+ and `uv`.

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
- If the control is dropped for time, the claim narrows to a comparison of complete retrieval policies.

**What to report**
- Actual context tokens used and actual model calls.
- Support recall, all-support hit rate, accuracy, latency, and cost.

### Experiment A: Selected configuration vs. fixed baselines (held-out)

- Compare the predefined fixed baselines and the optimizer's selection on untouched held-out questions.
- **Success** means meeting A_min at lower latency or cost. The highest accuracy is not required.

**Fixed baselines (predefined, recorded before any optimization run)**

| Baseline | Retriever | Policy | Reasoning | Top-k | Hop cap |
|---|---|---|---|---|---|
| Fixed once | Hybrid | `once` | Medium | 5 | — |
| Fixed iterative | Hybrid | `iterative` | Medium | 5 per hop | 3 |

**Why these values.** They are the defaults a practitioner would plausibly pick, not tuned choices. Both are members of the 108-configuration space.

**If the optimizer selects one of them,** the honest result is "the default was already the best choice for this corpus." That is reported as such.

### Experiment B: Does diagnosis improve search?

**Arms.** Each arm uses the same 108-configuration space, the same validation questions, the same A_min, and **5 full configuration evaluations**:
1. Random search
2. LLM proposer **without** diagnosis (sees only scores and history)
3. LLM proposer **with** diagnosis (full agent)

**Search efficiency**
- Best selection-rule outcome after 5 evaluations: lowest qualifying latency, with cost inside the band.
- Fraction of seeds that found any qualifying configuration.
- Number of trials needed to first qualify.

**Optimization efficiency**
- Total optimization tokens, spend, and wall-clock time per arm, including diagnosis and probes.

**Held-out check**
- Each arm's selection is evaluated on the held-out set: does it still meet A_min, and at what latency and cost?

**Fair latency.** A configuration evaluated by several arms is measured once, and the shared measurement is reused.

**Seeds.** Use as many as the budget allows. Arm 2 has priority over extra seeds. With few seeds, the result is presented as a small-budget demonstration.

**Not done:** comparison under a matched total optimization-cost budget. The overhead is reported instead.

---

## 7. Evaluation Protocol

**Splits (MuSiQue)**
| Split | Size | Use |
|---|---|---|
| Pilot | ~100 | Smoke tests; calibrating B and A_min (only fixed baselines run here, so the larger size is cheap) |
| Validation | ~100 | Experiment 0 and all optimization |
| Held-out | ~150–200 | Untouched until final reporting |

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
- Warm up before measuring, and repeat where practical.
- Report p50 and p95 with sample sizes; p95 is indicative only.

**Scoring**
- A strict, fixed LLM-judge prompt, plus EM and F1.

---

## 8. Datasets and Demo

| Item | Status |
|---|---|
| **MuSiQue (answerable)** | **Essential.** All experiments. |
| MultiHop-RAG | Optional. Secondary results if time remains. |
| Custom upload + synthetic exam | Optional. Out of the main schedule. |

**Demo centerpiece: an evidence trace on a curated MuSiQue question**
1. `once` misses a supporting paragraph and answers wrongly.
2. `iterative` issues a second query, finds the missing paragraph, and answers correctly. The trace shows each query, the retrieved IDs, and `known_facts`.
3. The optimizer's recommendation card shows the selected configuration, its measured accuracy, latency, and cost, and a one-paragraph "why this configuration," for example "decomposition matched iterative within the bar at lower latency."
4. Supporting views: the Pareto chart, the Experiment B search curves, and config export.

All shown numbers are measured. The demo uses precomputed results plus one live pipeline execution.

**Caveat.** MuSiQue likely overlaps Muse's training data, so the closed-book baseline is always shown. Comparisons with Agentic AutoRAG's published numbers are directional only.

---

## 9. Scope (committed)

| Component | Status |
|---|---|
| MuSiQue via the benchmark repo | Essential |
| `once` / `decompose` / `iterative` + closed-book baseline | Essential |
| `staged-decompose` control (a flag on iterative) | Essential (low cost) |
| BM25 / dense / hybrid | Keep |
| `reasoning_effort` + top-k search | Essential |
| Experiments 0, A, B (three arms, small budget) | Essential |
| Diagnoser (probes capped) + Proposer | Essential |
| Evidence trace viewer + recommendation card | Essential |
| Config export | Keep |
| MultiHop-RAG | Optional |
| Custom upload + synthetic exam | Optional |
| Preserved reasoning-state variant | Optional |
| `adaptive` gate, reranker, chunking, model tier | Stretch |
| Per-query routing | Cut |
| FLARE | Cut |

---

## 10. Schedule (Oct 28 – Nov 4, SGT)

| Date | Deliverable |
|---|---|
| **Oct 28** | **Milestone 1:** one MuSiQue question end to end through `once` and 3-hop `iterative` on Muse Spark 1.3. Requires correct evidence IDs, token accounting (including reasoning tokens), full-call latency, and a complete execution trace. Also: API smoke test (`reasoning_effort` levels, Responses API, billing), benchmark data prepared, and the **fork/build decision**. |
| Oct 29 | All policies, including the `staged-decompose` flag; all retrievers; per-trial `reasoning_effort`; pilot-split calibration of B and A_min |
| Oct 30 | Experiment 0 on validation; logging hardened. **Go/no-go:** a reliable, repeatable comparison with interpretable metrics. A winning policy is not required. |
| Oct 31 | Diagnoser (capped probes), Proposer, selection rule, 5-trial loop; random and no-diagnosis arms |
| Nov 1 | Experiments A and B; config export |
| Nov 2 | Streamlit demo: evidence trace viewer, recommendation card, Pareto chart, search curves |
| Nov 3 | Feature freeze; held-out runs; optional MultiHop-RAG; README; demo recording |
| Nov 4 | Submission buffer (hard deadline Nov 5, 10:00 AM SGT) |

**Cut order if behind schedule:**
1. Optional items
2. Extra Experiment B seeds
3. No-diagnosis arm (then narrow the claim to "diagnosis-guided vs. random")
4. Pareto chart polish

**Never cut:** Experiment 0's matched baselines, held-out evaluation, the random arm, and the evidence trace demo.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| Fork's evaluator assumes one-pass pipelines | Decide on Oct 28 after Milestone 1; otherwise use the thin runner |
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
