# Milestone automation

`automation/run <M> <prev-tag>` runs: builder → driver Gate 1 precheck → independent reviewer → fix → … until
the reviewer approves (fail-closed) or a safeguard trips. Then it stops and notifies the owner. Gate 3,
owner decisions and all git tags stay manual (REVIEW.md).

- Prompts: read verbatim from MILESTONES.md (builder) and REVIEW.md (reviewer). M2+ builder prompts are
  owner-written in `automation/prompts/build_<M>.md`.
- Sessions: builder = one persistent session (`--session-id`, resumed for fixes); reviewer = fresh,
  non-persisted session per round, different model, Edit/Write disabled.
- Approval requires ALL of: reviewer run succeeded; schema-valid JSON; verdict APPROVE; every item PASS;
  items ≥ acceptance criteria count; no validity/measurement/scope defect; markdown overall line says APPROVE
  and not REQUEST CHANGES; repo state unchanged by reviewer.
- Driver precheck: clean tree, new commits, protected files (spec docs, automation/, .gitignore) untouched,
  tags unchanged, PROGRESS.md section exists, no API key value in committed history; M1+: `make check`
  passes and a check-live log is committed.
- Safeguards: per-call `--max-budget-usd`, total Claude Code spend cap, max rounds, no-progress detection,
  two-strikes on builder/reviewer crashes. Model API spend is capped by each milestone's own `--max-usd`.
- State/logs: `.automation/<M>/` (gitignored): `state.json`, `driver.log`, raw `*.json` outputs,
  `review_rN.md`, `HUMAN_ACTION.md`.

Options: `--print-prompts`, `--reset-rounds`, `--max-rounds`, `--builder-model`, `--reviewer-model`,
`--builder-budget-usd`, `--reviewer-budget-usd`, `--total-budget-usd`, `--max-no-progress`.

Offline dry run (fake CLI, temp copy of repo, no spend): `automation/tests/selftest.sh`
