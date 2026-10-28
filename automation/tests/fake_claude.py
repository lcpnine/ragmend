#!/usr/bin/env python3
"""Stand-in for the `claude` CLI used by selftest.sh. Makes no network calls.

Builder calls (no --json-schema) commit a PROGRESS.md section, misbehaving per FAKE_BUILDER.
Reviewer calls emit the next verdict from FAKE_REVIEWS (comma-separated):
  approve | reject | malformed | contradict | unverified | dirty | crash
"""
import json
import os
import subprocess
import sys
from pathlib import Path

args = sys.argv[1:]
sys.stdin.read()
cwd = Path.cwd()
ctr = cwd / ".automation" / "fake_counter.json"
ctr.parent.mkdir(exist_ok=True)
c = json.loads(ctr.read_text()) if ctr.exists() else {"builder": 0, "reviewer": 0}
role = "reviewer" if "--json-schema" in args else "builder"
n = c[role]
c[role] += 1
ctr.write_text(json.dumps(c))


def git(*a):
    subprocess.run(["git", *a], check=True, capture_output=True)


def out(obj, code=0):
    base = {"type": "result", "subtype": "success", "is_error": False, "session_id": "fake",
            "total_cost_usd": 0.01, "result": ""}
    base.update(obj)
    print(json.dumps(base))
    sys.exit(code)


if role == "builder":
    mode = (os.environ.get("FAKE_BUILDER", "ok").split(",") + ["ok"] * 20)[n]
    if mode == "crash":
        out({"subtype": "error_during_execution", "is_error": True}, 1)
    p = cwd / "PROGRESS.md"
    text = p.read_text() if p.exists() else "# Progress\n"
    if "## M0" not in text:
        text += "\n## M0\n\n### Deviations\nnone\n\n### Open questions\n- fake question\n\n### API spend\n$0\n"
    text += f"\nbuilder pass {n}\n"
    p.write_text(text)
    if mode == "edit_plan":
        (cwd / "PLAN.md").write_text((cwd / "PLAN.md").read_text() + "\nsneaky\n")
    if mode == "leak":
        (cwd / "reports").mkdir(exist_ok=True)
        (cwd / "reports" / "leak.txt").write_text(os.environ.get("FAKE_SECRET", ""))
    git("add", "-A")
    git("commit", "-qm", f"fake builder {n}")
    if mode == "tag":
        git("tag", "m0-done")
    if mode == "dirty":
        (cwd / "untracked.txt").write_text("x")
    out({"result": "done"})

mode = (os.environ.get("FAKE_REVIEWS", "approve").split(",") + ["approve"] * 20)[n]
if mode == "crash":
    out({"subtype": "error_max_budget_usd", "is_error": True}, 1)
if mode == "malformed":
    out({"result": "I think it's fine, APPROVE"})
items = [{"id": f"criterion {i}", "status": "PASS", "evidence": "x"} for i in range(1, 8)]
verdict, md = "APPROVE", "| table |\n\nOverall: APPROVE"
if mode == "reject":
    items[2]["status"] = "FAIL"
    verdict, md = "REQUEST_CHANGES", "Overall: REQUEST CHANGES"
if mode == "unverified":   # claims approve but has an UNVERIFIED item
    items[4]["status"] = "UNVERIFIED"
if mode == "contradict":   # structured APPROVE, markdown says otherwise
    md = "Overall: REQUEST CHANGES"
if mode == "dirty":
    (cwd / "reviewer_scratch.txt").write_text("x")
out({"structured_output": {"verdict": verdict, "items": items, "defects": [], "report_markdown": md}})
