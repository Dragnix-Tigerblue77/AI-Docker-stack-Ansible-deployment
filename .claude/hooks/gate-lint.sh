#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Tigerblue77 and the AI Docker stack Ansible deployment contributors
# SPDX-License-Identifier: AGPL-3.0-only
# TaskCompleted gate: refuse to let a task be marked done while the repository
# does not pass the checks CI will run on it.
#
# ! Exit 2 is the blocking code -- Claude Code feeds stderr back to the agent and
# the task stays open. Exit 0 lets the completion through. Any other code is
# treated as a hook error and does NOT block, which is why every failure path
# below exits 2 deliberately, including "the tooling is missing": a gate that
# cannot run its checks must not report success.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT" || { echo "gate-lint: cannot reach the repository root" >&2; exit 2; }

# Drain stdin. The hook payload is not needed -- the gate is about the tree, not
# about which task closed -- but leaving it unread can hand the caller an EPIPE.
cat >/dev/null 2>&1 || true

missing=()
command -v yamllint     >/dev/null 2>&1 || missing+=("yamllint")
command -v reuse        >/dev/null 2>&1 || missing+=("reuse")
command -v ansible-lint >/dev/null 2>&1 || missing+=("ansible-lint")
command -v python3      >/dev/null 2>&1 || missing+=("python3")
command -v gitleaks     >/dev/null 2>&1 || missing+=("gitleaks")

if [ ${#missing[@]} -gt 0 ]; then
  echo "gate-lint: missing tooling: ${missing[*]}" >&2
  echo "Install it with: pip install -r requirements.txt (gitleaks is installed separately by .claude/hooks/session-start.sh)" >&2
  echo "The gate cannot verify this task, so it is not being marked complete." >&2
  exit 2
fi

failures=()

run_check() {
  local label="$1"; shift
  local output
  if ! output="$("$@" 2>&1)"; then
    failures+=("$label")
    echo "--- ${label} ---" >&2
    printf '%s\n' "$output" | tail -n 40 >&2
  fi
}

run_check "yamllint"                                yamllint .
run_check "REUSE compliance"                         reuse lint
run_check "ansible-lint"                             ansible-lint
run_check "ansible-playbook --syntax-check"          ansible-playbook --syntax-check playbook.Artificial_Intelligence.example.yaml
run_check "compose template (selftest)"              python3 .github/scripts/check_compose_template.py --selftest
run_check "compose template"                         python3 .github/scripts/check_compose_template.py
run_check "LiteLLM account isolation (selftest)"     python3 .github/scripts/check_LiteLLM_account_isolation.py --selftest
run_check "LiteLLM account isolation"                python3 .github/scripts/check_LiteLLM_account_isolation.py
run_check "no inventory data (selftest)"             python3 .github/scripts/check_no_inventory_data.py --selftest
run_check "no inventory data"                        python3 .github/scripts/check_no_inventory_data.py
run_check "sign-off (selftest)"                      python3 .github/scripts/check_sign_off.py --selftest
run_check "required checks (selftest)"               python3 .github/scripts/check_required_checks.py --selftest
run_check "required checks"                          python3 .github/scripts/check_required_checks.py
run_check "gitleaks"                                 gitleaks dir . --no-banner --redact

if [ ${#failures[@]} -gt 0 ]; then
  echo "" >&2
  echo "gate-lint: ${#failures[@]} check(s) failed: ${failures[*]}" >&2
  echo "Fix them, then mark the task complete again. CI runs these same checks." >&2
  exit 2
fi

exit 0
