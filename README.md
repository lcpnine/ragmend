# RAG Improvement Agent

An AI agent that diagnoses RAG failures, discovers better configurations through experimentation, and applies validated improvements to a runnable RAG pipeline.

**Loop:** Evaluate → Diagnose → Optimize → Validate → Apply

The agent measures a baseline multi-hop RAG pipeline (Muse Spark on MuSiQue), diagnoses its failures, and searches over retrieval strategy, retrieval frequency, and `reasoning_effort`. It selects the configuration that meets a fixed accuracy bar at the lowest latency, then cost. The selection is exported as one config file and run through the reference pipeline's CLI. After the selection is frozen, it is compared once against the baseline on held-out data. "No improvement" is a valid result.

## Status

Planning. No pipeline code yet; work starts at milestone M0.

## Documents

| File | Contents |
|---|---|
| [PLAN.md](PLAN.md) | The spec: design, experiments, evaluation protocol, scope |
| [MILESTONES.md](MILESTONES.md) | Milestones M0–M7 with prerequisites and acceptance criteria |
| [AGENTS.md](AGENTS.md) | Rules for coding agents: design decisions, data boundaries, invariants |
| [REVIEW.md](REVIEW.md) | Review gates every milestone passes before it is tagged |
| [automation/](automation/README.md) | Builder/reviewer driver that runs a milestone through review |

## Setup

Copy `.env.example` to `.env` and set `META_API_KEY`. Setup and run commands are added as milestones land.
