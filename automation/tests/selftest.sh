#!/usr/bin/env bash
# Dry run of the driver against a throwaway copy of this repo with a fake `claude`.
# No network, no API spend, the real repo is never touched.
set -uo pipefail
SRC="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/meta-selftest.XXXXXX")"
export CLAUDE_BIN="$SRC/automation/tests/fake_claude.py" AUTOMATION_NO_NOTIFY=1
PASS=0; FAIL=0

fresh() {  # $1 = scenario name -> cd into a clean copy tagged base
  local d="$WORK/$1"
  git clone -q "$SRC" "$d" && cd "$d" || exit 1
  git config user.email t@t; git config user.name selftest
  rsync -a --delete "$SRC/automation/" automation/ && cp "$SRC/.gitignore" .gitignore
  git add -A && git commit -qm "automation" && git tag -f base >/dev/null
}

expect() {  # $1 name, $2 expected exit, $3 expected phase, rest = env assignments
  local name=$1 want=$2 phase=$3; shift 3
  fresh "$name"
  env "$@" python3 automation/driver.py M0 base >"$WORK/$name.log" 2>&1; local got=$?
  local ph; ph=$(jq -r .phase .automation/M0/state.json 2>/dev/null)
  if [[ $got == "$want" && $ph == "$phase" ]]; then
    echo "PASS  $name (exit $got, phase $ph)"; PASS=$((PASS+1))
  else
    echo "FAIL  $name (exit $got want $want, phase $ph want $phase) -> $WORK/$name.log"; FAIL=$((FAIL+1))
  fi
}

expect approve_first         0 awaiting_human FAKE_REVIEWS=approve
expect reject_then_approve   0 awaiting_human FAKE_REVIEWS=reject,approve
expect malformed_twice       2 halted         FAKE_REVIEWS=malformed,malformed
expect unverified_is_not_ok  2 halted         FAKE_REVIEWS=unverified,unverified,unverified
expect contradiction_not_ok  2 halted         FAKE_REVIEWS=contradict,contradict
expect reviewer_crash        2 halted         FAKE_REVIEWS=crash,crash
expect max_rounds            2 halted         FAKE_REVIEWS=reject,unverified,reject,unverified
expect reviewer_dirties_tree 2 halted         FAKE_REVIEWS=dirty
expect builder_edits_plan    2 halted         FAKE_BUILDER=edit_plan
expect builder_creates_tag   2 halted         FAKE_BUILDER=tag
expect builder_dirty_fixed   0 awaiting_human FAKE_BUILDER=dirty
expect builder_crash_resumes 0 awaiting_human FAKE_BUILDER=crash
expect builder_crash_twice   2 halted         FAKE_BUILDER=crash,crash
# budget: a tiny total cap must halt
fresh budget_tiny
FAKE_REVIEWS=reject,reject,reject python3 automation/driver.py M0 base --total-budget-usd 0.025 >"$WORK/budget_tiny.log" 2>&1
[[ $? == 2 ]] && grep -q "total cap" .automation/M0/driver.log \
  && { echo "PASS  budget_tiny"; PASS=$((PASS+1)); } || { echo "FAIL  budget_tiny"; FAIL=$((FAIL+1)); }

# secret leak: fake key in .env, builder commits it
fresh secret_leak
echo "META_API_KEY=sk-fake-0123456789abcdef" > .env
FAKE_BUILDER=leak FAKE_SECRET=sk-fake-0123456789abcdef python3 automation/driver.py M0 base >"$WORK/secret.log" 2>&1
[[ $? == 2 ]] && grep -q "API key value" .automation/M0/driver.log && ! grep -q "sk-fake" .automation/M0/driver.log \
  && { echo "PASS  secret_leak (detected, key not logged)"; PASS=$((PASS+1)); } || { echo "FAIL  secret_leak"; FAIL=$((FAIL+1)); }

# resume: interrupt after build (simulate by killing state mid-way), rerun continues
fresh resume
python3 - <<'PY'
import json, pathlib, uuid
d = pathlib.Path(".automation/M0"); d.mkdir(parents=True)
import subprocess
st = dict(milestone="M0", prev="base", phase="build", round=0, spend_usd=0.0,
          builder_session=str(uuid.uuid4()), builder_started=True,
          tags_before=sorted(subprocess.run(["git","tag"],capture_output=True,text=True).stdout.split()),
          history=[], fail_streak=[], cfg={}, started="x")
(d/"state.json").write_text(json.dumps(st))
PY
python3 automation/driver.py M0 base >"$WORK/resume.log" 2>&1
[[ $? == 0 ]] && grep -q "Resuming M0" .automation/M0/driver.log && ls .automation/M0/build_resume.json >/dev/null \
  && { echo "PASS  resume_after_interrupt (used --resume)"; PASS=$((PASS+1)); } || { echo "FAIL  resume"; FAIL=$((FAIL+1)); }
# rerun after approval is idempotent
python3 automation/driver.py M0 base >/dev/null 2>&1
[[ $? == 0 ]] && { echo "PASS  rerun_after_approval_idempotent"; PASS=$((PASS+1)); } || { echo "FAIL  rerun idempotent"; FAIL=$((FAIL+1)); }

# M2 has no owner prompt yet -> refuse
fresh no_prompt
python3 automation/driver.py M2 base >"$WORK/noprompt.log" 2>&1
[[ $? != 0 ]] && grep -q "owner-written" "$WORK/noprompt.log" \
  && { echo "PASS  m2_without_prompt_refused"; PASS=$((PASS+1)); } || { echo "FAIL  m2 refusal"; FAIL=$((FAIL+1)); }

echo; echo "selftest: $PASS passed, $FAIL failed (work dir: $WORK)"
[[ $FAIL == 0 ]]
