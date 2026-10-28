#!/usr/bin/env python3
"""Milestone driver: build -> gate-1 precheck -> independent review -> fix, until
the reviewer explicitly approves or a safeguard trips. Then it stops for the human
gate (REVIEW.md Gate 3). It never creates tags and never edits the spec documents.

Prompts are extracted verbatim from MILESTONES.md / REVIEW.md at run time, so those
files remain the single source of truth. Milestones without a prompt block in
MILESTONES.md (M2+) need an owner-written automation/prompts/build_<M>.md.

State lives in .automation/<M>/ (gitignored). Re-running the same command resumes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTO = ROOT / "automation"
STATE_ROOT = ROOT / ".automation"

PROTECTED = ["PLAN.md", "AGENTS.md", "MILESTONES.md", "REVIEW.md", "automation", ".claude", ".gitignore"]
SECRET_FILES = [".env", ".env.local"]
BLOCKING_SEVERITIES = {"validity-breaking", "measurement", "scope"}

DEFAULTS = dict(
    builder_model="opus",
    reviewer_model="sonnet",
    max_rounds=4,              # review rounds (each failed round triggers one fix)
    builder_budget_usd=25.0,   # Claude Code spend cap per builder invocation
    reviewer_budget_usd=10.0,  # per reviewer invocation
    total_budget_usd=100.0,    # Claude Code spend cap for the whole milestone
    max_no_progress=2,         # identical failure sets in a row -> stop
)


# ----------------------------------------------------------------------------- utils

def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def sh(cmd: list[str], check=False, **kw) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, **kw)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed:\n{p.stdout}\n{p.stderr}")
    return p


def git(*args) -> str:
    return sh(["git", *args], check=True).stdout.strip()


class Log:
    def __init__(self, path: Path):
        self.path = path

    def __call__(self, msg: str):
        line = f"[{now()}] {msg}"
        print(line, flush=True)
        with self.path.open("a") as f:
            f.write(line + "\n")


def code_block_after(text: str, marker: str) -> str | None:
    i = text.find(marker)
    if i < 0:
        return None
    m = re.search(r"```[^\n]*\n(.*?)\n```", text[i:], re.S)
    return m.group(1).strip() if m else None


def milestone_section(text: str, m: str) -> str:
    """Text of '## M0: ...' section, or the '**M2: ...**' paragraph block."""
    h = re.search(rf"^## {m}:.*?(?=^## |\Z)", text, re.S | re.M)
    if h:
        return h.group(0)
    b = re.search(rf"^\*\*{m}:.*?(?=^\*\*M\d+:|\Z)", text, re.S | re.M)
    return b.group(0) if b else ""


def acceptance_criteria(m: str) -> list[str]:
    sec = milestone_section((ROOT / "MILESTONES.md").read_text(), m)
    if "**Acceptance criteria**" in sec:
        sec = sec.split("**Acceptance criteria**", 1)[1]
        sec = re.split(r"^\*\*Owner decision|^---", sec, flags=re.M)[0]
    return [l[2:].strip() for l in sec.splitlines() if l.startswith("- ")]


def owner_decision_text(m: str) -> str:
    sec = milestone_section((ROOT / "MILESTONES.md").read_text(), m)
    lines = [l.strip() for l in sec.splitlines()
             if re.search(r"owner decision|\(owner\)|owner approval", l, re.I)]
    return "\n".join(lines)


# --------------------------------------------------------------------------- prompts

BUILDER_SYSTEM = """You are the BUILDER, running non-interactively under an automation driver.
- Nobody can answer questions mid-run. If something is infeasible or ambiguous, follow AGENTS.md:
  record it under Open questions in PROGRESS.md with evidence and stop. Do not improvise designs.
- Never edit PLAN.md, AGENTS.md, MILESTONES.md, REVIEW.md, .gitignore, automation/ or .claude/.
- Never create, move or delete git tags. Never push. Never amend or rewrite existing commits.
- Never print, copy or commit API keys. Code may load them from .env at runtime; you must not read .env files.
- Respect every --max-usd spend cap in the milestone prompt.
- When done: commit everything and leave `git status --short` empty, then stop."""

REVIEWER_SYSTEM = """You are the INDEPENDENT REVIEWER, running non-interactively under an automation driver.
You must not modify, create or delete any file in the repository, or change git state.
Write any scratch output only under $TMPDIR. Your final answer must conform to the provided JSON schema:
- items: one entry per acceptance criterion AND per invariant/check you assessed. status is exactly
  PASS, FAIL or UNVERIFIED. UNVERIFIED is not PASS. Owner waivers are not yours to grant: list them as UNVERIFIED.
- defects: ordered by severity, using the severities from REVIEW.md.
- verdict: APPROVE only if every item is PASS and no defect is validity-breaking, measurement or scope.
  Otherwise REQUEST_CHANGES.
- report_markdown: the full human-readable report in the format REVIEW.md requests."""

REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "items", "defects", "report_markdown"],
    "properties": {
        "verdict": {"type": "string", "enum": ["APPROVE", "REQUEST_CHANGES"]},
        "items": {"type": "array", "minItems": 1, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["id", "status", "evidence"],
            "properties": {
                "id": {"type": "string"},
                "status": {"type": "string", "enum": ["PASS", "FAIL", "UNVERIFIED"]},
                "evidence": {"type": "string"}}}},
        "defects": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["severity", "description"],
            "properties": {
                "severity": {"type": "string",
                             "enum": ["validity-breaking", "measurement", "scope", "quality"]},
                "description": {"type": "string"}}}},
        "report_markdown": {"type": "string"},
    },
}


def build_prompt(m: str) -> str:
    override = AUTO / "prompts" / f"build_{m}.md"
    if override.exists():
        return override.read_text().strip()
    sec = milestone_section((ROOT / "MILESTONES.md").read_text(), m)
    p = code_block_after(sec, "**Prompt**")
    if not p:
        raise SystemExit(f"No prompt for {m} in MILESTONES.md and no {override.relative_to(ROOT)}. "
                         "Per MILESTONES.md, later prompts are owner-written after M1.")
    return p


def review_prompt(m: str, prev: str) -> str:
    text = (ROOT / "REVIEW.md").read_text()
    marker = "**Reviewer prompt (M0 variant)**" if m == "M0" else "**Reviewer prompt (M1 onward)**"
    p = code_block_after(text, marker)
    if not p:
        raise SystemExit(f"Reviewer prompt '{marker}' not found in REVIEW.md")
    p = p.replace("<MN>", m).replace("<previous-tag>", prev).replace("base..HEAD", f"{prev}..HEAD")
    crit = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(acceptance_criteria(m)))
    return p + f"\n\nFor reference, the {m} acceptance criteria in MILESTONES.md are:\n{crit}\n"


# ---------------------------------------------------------------------------- claude

def claude_bin() -> str:
    return os.environ.get("CLAUDE_BIN", "claude")


def child_env() -> dict:
    env = dict(os.environ)
    for k in list(env):  # don't hand project API keys to the agent processes
        if k.startswith("META_") or k.endswith("_API_KEY") and k != "ANTHROPIC_API_KEY":
            env.pop(k)
    return env


def run_claude(role: str, args: list[str], prompt: str, out: Path, log: Log) -> dict:
    cmd = [claude_bin(), "-p", "--output-format", "json", *args]
    log(f"{role}: launching ({' '.join(a for a in args if not a.startswith('{'))[:200]})")
    p = subprocess.run(cmd, input=prompt, cwd=ROOT, text=True, capture_output=True, env=child_env())
    out.write_text(p.stdout)
    (out.with_suffix(".stderr")).write_text(p.stderr)
    try:
        res = json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else {}
    except (json.JSONDecodeError, IndexError):
        res = {}
    res.setdefault("_exit", p.returncode)
    log(f"{role}: exit={p.returncode} subtype={res.get('subtype')} "
        f"cost=${res.get('total_cost_usd', 0) or 0:.2f} -> {out.relative_to(ROOT)}")
    return res


# ------------------------------------------------------------------------ gate checks

def tree_snapshot() -> str:
    return git("rev-parse", "HEAD") + "\n" + git("status", "--porcelain", "--untracked-files=all")


def secret_values() -> list[str]:
    vals = []
    for f in SECRET_FILES:
        p = ROOT / f
        if p.exists():
            for line in p.read_text().splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    v = line.split("=", 1)[1].strip().strip("'\"")
                    if len(v) >= 12 and "your_" not in v:
                        vals.append(v)
    return vals


def precheck(m: str, prev: str, tags_before: list[str]) -> list[str]:
    """Driver-side mechanical Gate 1 checks. Any returned string is a failure."""
    fails = []
    if git("status", "--porcelain", "--untracked-files=all"):
        fails.append("Working tree is not clean (`git status --short` non-empty).")
    if git("rev-parse", "HEAD") == git("rev-parse", prev):
        fails.append(f"No commits since {prev}.")
    changed = git("diff", "--name-only", prev, "HEAD", "--", *PROTECTED)
    if changed:
        fails.append(f"Protected files changed since {prev}: {changed.split()}")
    if sorted(git("tag").split()) != tags_before:
        fails.append("Git tags changed during the run; tagging is owner-only.")
    prog = ROOT / "PROGRESS.md"
    if not prog.exists() or not re.search(rf"^#+ .*\b{m}\b", prog.read_text(), re.M):
        fails.append(f"PROGRESS.md has no section heading for {m}.")
    secrets = secret_values()
    if secrets:
        diff = sh(["git", "log", "-p", f"{prev}..HEAD"]).stdout
        if any(s in diff for s in secrets):
            fails.append("An API key value appears in committed history since the previous tag. "
                         "STOP: rotate the key; history must be rewritten by the owner.")
    if m != "M0":
        mk = sh(["make", "check"])
        (STATE_ROOT / m / "driver_make_check.log").write_text(mk.stdout + mk.stderr)
        if mk.returncode != 0:
            fails.append(f"`make check` failed (exit {mk.returncode}); see .automation/{m}/driver_make_check.log")
        live = git("ls-files", "reports").split()
        if not any(re.search(r"check[-_]?live", f) for f in live):
            fails.append("No committed `make check-live` log under reports/.")
    return fails


def assess_review(res: dict, n_criteria: int) -> tuple[bool, list[str], dict | None]:
    """Fail-closed: returns (approved, reasons_not_approved, parsed_review)."""
    r = []
    if res.get("_exit") != 0 or res.get("is_error") or res.get("subtype") != "success":
        r.append(f"Reviewer run did not succeed (exit={res.get('_exit')}, subtype={res.get('subtype')}).")
    rv = res.get("structured_output")
    if rv is None and isinstance(res.get("result"), str):
        try:
            rv = json.loads(res["result"])
        except json.JSONDecodeError:
            rv = None
    if not isinstance(rv, dict):
        return False, r + ["Review output missing or not a JSON object."], None
    items, defects = rv.get("items"), rv.get("defects")
    if rv.get("verdict") not in ("APPROVE", "REQUEST_CHANGES"):
        r.append(f"Malformed verdict: {rv.get('verdict')!r}.")
    if not isinstance(items, list) or not items:
        r.append("No assessed items.")
        items = []
    if not isinstance(defects, list):
        r.append("Malformed defects list.")
        defects = []
    bad = [i for i in items if not isinstance(i, dict) or i.get("status") != "PASS"]
    for i in bad:
        r.append(f"{i.get('status', '?') if isinstance(i, dict) else '?'}: "
                 f"{i.get('id', '?') if isinstance(i, dict) else i}")
    if len(items) < n_criteria:
        r.append(f"Only {len(items)} items assessed; MILESTONES.md lists {n_criteria} acceptance criteria.")
    for d in defects:
        if not isinstance(d, dict) or d.get("severity") in BLOCKING_SEVERITIES or "severity" not in d:
            r.append(f"Blocking defect: {d}")
    md = rv.get("report_markdown", "")
    if not isinstance(md, str) or not md.strip():
        r.append("Empty report_markdown.")
    else:
        overall = [l for l in md.splitlines() if re.search(r"overall|verdict", l, re.I)]
        if any(re.search(r"REQUEST[ _]CHANGES", l) for l in overall):
            r.append("report_markdown's overall verdict says REQUEST CHANGES (contradicts structured verdict).")
        if not any("APPROVE" in l for l in overall):
            r.append("report_markdown has no explicit overall APPROVE line.")
    if rv.get("verdict") != "APPROVE":
        r.append("Verdict is not APPROVE.")
    return (not r), r, rv


# ----------------------------------------------------------------------------- notify

def notify(title: str, msg: str):
    if os.environ.get("AUTOMATION_NO_NOTIFY"):
        return
    safe = msg.replace('"', "'")[:200]
    subprocess.run(["osascript", "-e", f'display notification "{safe}" with title "{title}" sound name "Glass"'],
                   capture_output=True)


def human_handoff(m: str, st: dict, reason: str, outstanding: list[str], approved: bool, log: Log):
    sdir = STATE_ROOT / m
    prog = ROOT / "PROGRESS.md"
    section = ""
    if prog.exists():
        mm = re.search(rf"^(#+) .*\b{m}\b.*?(?=^\1 |\Z)", prog.read_text(), re.S | re.M)
        section = mm.group(0) if mm else ""

    def sub(name):
        mm = re.search(rf"^#+ *{name}.*?(?=^#+ |\Z)", section, re.S | re.M | re.I)
        return mm.group(0).strip() if mm else f"(no '{name}' subsection found in PROGRESS.md {m})"

    last_review = sdir / f"review_r{st['round']}.md"
    nxt = f"m{m[1:]}-done"
    body = f"""# {m}: human action required

**Status:** {"REVIEWER APPROVED — Gate 3 (human) pending" if approved else "HALTED — not approved"}
**Reason:** {reason}
**Rounds:** {st['round']} / {st['cfg']['max_rounds']}   **Claude Code spend:** ${st['spend_usd']:.2f}
**HEAD:** {git('rev-parse', '--short', 'HEAD')}   **Previous tag:** {st['prev']}
**Last review:** {last_review.relative_to(ROOT) if last_review.exists() else '(none)'}
**Driver log:** .automation/{m}/driver.log

## Outstanding issues
{chr(10).join('- ' + o for o in outstanding) if outstanding else '- none reported by reviewer'}

## Owner decisions for this milestone
{owner_decision_text(m) or '- none listed in MILESTONES.md'}

## From PROGRESS.md: Deviations
{sub('Deviations')}

## From PROGRESS.md: Open questions
{sub('Open questions')}

## From PROGRESS.md: API spend
{sub('API spend')}

## Your next steps (REVIEW.md Gate 3 — not automated by design)
1. Read one trace by eye (M0: read eval/golden.json questions and supports).
2. Approve or revert every deviation; answer open questions.
3. Recompute one number in PROGRESS.md from raw data.
4. Record decisions/waivers in PROGRESS.md, commit, check `git status --short` is clean.
5. `git tag {nxt}` — then start the next milestone with `automation/run M{int(m[1:])+1} {nxt}`.
{"" if approved else "If you fixed things by hand or waived items, rerun the same command with --reset-rounds to review again."}
"""
    out = sdir / "HUMAN_ACTION.md"
    out.write_text(body)
    log(f"Handoff written: {out.relative_to(ROOT)}")
    print("\n" + body)
    notify(f"meta {m}: {'ready for Gate 3' if approved else 'needs you'}", reason)


# ------------------------------------------------------------------------------ main

def save(st: dict, path: Path):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=2))
    tmp.replace(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("milestone", help="e.g. M0")
    ap.add_argument("prev_tag", help="tag the review diffs against, e.g. base or m0-done")
    for k, v in DEFAULTS.items():
        ap.add_argument("--" + k.replace("_", "-"), type=type(v), default=None)
    ap.add_argument("--print-prompts", action="store_true", help="show extracted prompts and exit")
    ap.add_argument("--reset-rounds", action="store_true", help="after a halt, allow another review cycle")
    a = ap.parse_args()
    m = a.milestone.upper()
    if not re.fullmatch(r"M\d+", m):
        raise SystemExit("milestone must look like M0")

    if a.print_prompts:
        print("=== BUILDER (user prompt) ===\n" + build_prompt(m))
        print("\n=== BUILDER (appended system) ===\n" + BUILDER_SYSTEM)
        print("\n=== REVIEWER ===\n" + review_prompt(m, a.prev_tag))
        print(f"\n=== {len(acceptance_criteria(m))} acceptance criteria parsed ===")
        return

    sdir = STATE_ROOT / m
    sdir.mkdir(parents=True, exist_ok=True)
    spath = sdir / "state.json"
    log = Log(sdir / "driver.log")

    if spath.exists():
        st = json.loads(spath.read_text())
        if st["prev"] != a.prev_tag:
            raise SystemExit(f"State for {m} uses prev tag {st['prev']}; delete {spath} to restart.")
        log(f"Resuming {m}: phase={st['phase']} round={st['round']}")
    else:
        if sh(["git", "rev-parse", "-q", "--verify", f"refs/tags/{a.prev_tag}"]).returncode != 0:
            raise SystemExit(f"Tag {a.prev_tag} does not exist.")
        if git("status", "--porcelain", "--untracked-files=all"):
            raise SystemExit("Working tree must be clean before starting a milestone.")
        drift = git("diff", "--name-only", a.prev_tag, "HEAD", "--", *PROTECTED)
        if drift:
            raise SystemExit(f"Protected files differ between {a.prev_tag} and HEAD: {drift.split()}.\n"
                             f"Commit tooling/spec changes before tagging {a.prev_tag}.")
        build_prompt(m)  # fail early if there's no prompt
        st = dict(milestone=m, prev=a.prev_tag, phase="build", round=0, spend_usd=0.0,
                  builder_session=str(uuid.uuid4()), builder_started=False,
                  tags_before=sorted(git("tag").split()), history=[], fail_streak=[],
                  cfg=dict(DEFAULTS), started=now())
        log(f"Starting {m} against {a.prev_tag}; builder session {st['builder_session']}")
    st["cfg"] = {**DEFAULTS, **st.get("cfg", {})}
    for k in DEFAULTS:
        v = getattr(a, k)
        if v is not None:
            st["cfg"][k] = v
    cfg = st["cfg"]
    if a.reset_rounds and st["phase"] == "halted":
        st.update(phase="review", fail_streak=[])
        cfg["max_rounds"] = st["round"] + 1
        log("Reset: one more review round granted.")
    save(st, spath)

    builder_settings = str(AUTO / "settings.builder.json")
    reviewer_settings = str(AUTO / "settings.reviewer.json")

    def spend(res):
        st["spend_usd"] += float(res.get("total_cost_usd") or 0)

    def over_budget() -> bool:
        return st["spend_usd"] >= cfg["total_budget_usd"]

    def guard_budget():
        if over_budget():
            halt(f"Claude Code spend ${st['spend_usd']:.2f} reached total cap ${cfg['total_budget_usd']}.", [])

    def builder(prompt: str, label: str) -> dict:
        guard_budget()
        args =["--model", cfg["builder_model"], "--settings", builder_settings,
                "--permission-mode", "acceptEdits", "--append-system-prompt", BUILDER_SYSTEM,
                "--max-budget-usd", str(min(cfg["builder_budget_usd"],
                                            cfg["total_budget_usd"] - st["spend_usd"]))]
        args += (["--resume", st["builder_session"]] if st["builder_started"]
                 else ["--session-id", st["builder_session"]])
        st["builder_started"] = True
        save(st, spath)
        res = run_claude("builder", args, prompt, sdir / f"{label}.json", log)
        spend(res)
        st["history"].append(dict(t=now(), step=label, subtype=res.get("subtype"),
                                  cost=res.get("total_cost_usd")))
        save(st, spath)
        return res

    def halt(reason: str, outstanding: list[str]):
        st["phase"] = "halted"
        save(st, spath)
        log(f"HALT: {reason}")
        human_handoff(m, st, reason, outstanding, False, log)
        sys.exit(2)

    while True:
        if st["phase"] in ("awaiting_human",):
            log("Already approved by reviewer; awaiting Gate 3.")
            human_handoff(m, st, "Reviewer approved. Complete Gate 3.", [], True, log)
            return
        if st["phase"] == "halted":
            log("Milestone is halted. Use --reset-rounds after addressing the handoff, or delete state.")
            print((sdir / "HUMAN_ACTION.md").read_text() if (sdir / "HUMAN_ACTION.md").exists() else "")
            sys.exit(2)
        if over_budget():
            halt(f"Claude Code spend ${st['spend_usd']:.2f} reached total cap ${cfg['total_budget_usd']}.", [])

        if st["phase"] in ("build", "fix"):
            if st["phase"] == "build" and not st["builder_started"]:
                prompt, label = build_prompt(m), "build"
            elif st["phase"] == "build":
                prompt, label = ("You were interrupted. Re-read AGENTS.md, inspect `git status` and "
                                 "PROGRESS.md, and finish the milestone task from where you stopped. "
                                 "Finish per AGENTS.md, then stop."), "build_resume"
            else:
                prompt = st["pending_fix_prompt"]
                label = f"fix_r{st['round']}_p{st.get('precheck_fixes', 0)}"
            res = builder(prompt, label)
            if res.get("_exit") != 0 or res.get("is_error"):
                st.setdefault("builder_errors", 0)
                st["builder_errors"] += 1
                save(st, spath)
                if st["builder_errors"] >= 2:
                    halt(f"Builder failed twice in a row (last subtype={res.get('subtype')}).",
                         [f"See .automation/{m}/{label}.stderr"])
                log("Builder errored; retrying once by resuming the session.")
                st["phase"] = "build" if st["phase"] == "build" else "fix"
                continue
            st["builder_errors"] = 0
            st["phase"] = "precheck"
            save(st, spath)

        if st["phase"] == "precheck":
            fails = precheck(m, st["prev"], st["tags_before"])
            if fails:
                for f in fails:
                    log(f"precheck FAIL: {f}")
                if any("STOP:" in f or "Protected" in f or "tags changed" in f for f in fails):
                    halt("Driver safeguard tripped (protected files, tags, or secrets).", fails)
                st["precheck_fixes"] = st.get("precheck_fixes", 0) + 1
                if st["precheck_fixes"] > cfg["max_rounds"]:
                    halt("Max rounds reached while failing driver precheck.", fails)
                st["pending_fix_prompt"] = ("The automation driver's Gate 1 precheck failed:\n"
                                            + "\n".join("- " + f for f in fails)
                                            + "\nFix these, commit, leave a clean tree, then stop.")
                st["phase"] = "fix"
                save(st, spath)
                continue
            log("precheck PASS")
            st["phase"] = "review"
            save(st, spath)

        if st["phase"] == "review":
            st["round"] += 1 if not st.get("review_pending") else 0
            st["review_pending"] = True
            save(st, spath)
            if st["round"] > cfg["max_rounds"]:
                halt("Max review rounds reached without approval.", st.get("last_outstanding", []))
            guard_budget()
            before = tree_snapshot()
            args = ["--model", cfg["reviewer_model"], "--settings", reviewer_settings,
                    "--append-system-prompt", REVIEWER_SYSTEM,
                    "--json-schema", json.dumps(REVIEW_SCHEMA),
                    "--max-budget-usd", str(min(cfg["reviewer_budget_usd"],
                                                cfg["total_budget_usd"] - st["spend_usd"])),
                    "--disallowedTools", "Edit", "Write", "NotebookEdit",
                    "--no-session-persistence"]
            res = run_claude("reviewer", args, review_prompt(m, st["prev"]),
                             sdir / f"review_r{st['round']}.json", log)
            spend(res)
            st["review_pending"] = False
            if tree_snapshot() != before:
                halt("Reviewer changed repository state (HEAD or working tree). Review is void; "
                     "inspect `git status` and restore manually.", [])
            ok, reasons, rv = assess_review(res, len(acceptance_criteria(m)))
            (sdir / f"review_r{st['round']}.md").write_text(
                (rv or {}).get("report_markdown", "(no report)") + "\n\n## Driver assessment\n"
                + ("APPROVED" if ok else "NOT APPROVED:\n" + "\n".join("- " + x for x in reasons)))
            st["history"].append(dict(t=now(), step=f"review_r{st['round']}", approved=ok,
                                      cost=res.get("total_cost_usd"), reasons=reasons[:30]))
            st["last_outstanding"] = reasons
            if ok:
                st["phase"] = "awaiting_human"
                save(st, spath)
                log("Reviewer APPROVED (fail-closed checks passed).")
                continue
            log(f"Review round {st['round']}: NOT APPROVED ({len(reasons)} reasons)")
            sig = sorted(reasons)
            st["fail_streak"] = (st["fail_streak"] + [sig])[-cfg["max_no_progress"]:]
            if len(st["fail_streak"]) == cfg["max_no_progress"] and all(
                    s == sig for s in st["fail_streak"]):
                halt("No progress: identical review failures in consecutive rounds.", reasons)
            if rv is None:
                # Malformed reviewer output is the reviewer's failure, not the builder's: retry review once.
                if st.get("malformed_reviews", 0) >= 1:
                    halt("Reviewer output malformed twice.", reasons)
                st["malformed_reviews"] = st.get("malformed_reviews", 0) + 1
                st["phase"] = "review"
                save(st, spath)
                continue
            if st["round"] >= cfg["max_rounds"]:
                halt("Max review rounds reached without approval.", reasons)
            st["pending_fix_prompt"] = (
                "Independent reviewer findings (verbatim) follow. Fix every FAIL and UNVERIFIED item and "
                "every blocking defect. Never skip, delete or loosen tests (AGENTS.md). If an item cannot "
                "be fixed within PLAN.md, record it under Open questions with evidence instead of "
                "improvising. Rerun Gate 1, update PROGRESS.md, commit, leave a clean tree, then stop.\n\n"
                + json.dumps(rv, indent=1))
            st["phase"] = "fix"
            save(st, spath)


if __name__ == "__main__":
    main()
