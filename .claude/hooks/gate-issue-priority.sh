#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Tigerblue77
# SPDX-License-Identifier: AGPL-3.0-only
# PreToolUse gate, matched to mcp__github__issue_write in .claude/settings.json:
# refuse a call that sets or updates an issue's Priority field.
#
# CLAUDE.md's own rule -- "Priorities are not ours to set" -- was, until #97,
# enforced only by gate-task-scope.sh (which sees a task's stated intent, not
# the tool call itself) and by each teammate's own instructions. .claude/README.md
# used to say outright that no technical mechanism could reach into a
# structured tool call this way; that was wrong, not a limit of Claude Code --
# a PreToolUse hook receives the call's tool_input as JSON on stdin, which is
# precisely specific enough to inspect for this one field.
#
# ! Refusal is signalled through hookSpecificOutput.permissionDecision, the
# documented and non-deprecated way to block a PreToolUse call -- not a bare
# exit code, which the two TaskCreated/TaskCompleted gates in this directory
# use instead because that is the correct contract for THEIR event types.
#
# ! Fails CLOSED if python3 is missing (the same "cannot verify, so do not
# report success" reasoning as gate-lint.sh) but fails OPEN on a payload that
# does not parse as expected -- deliberately, unlike a missing interpreter: a
# hook that blocked every issue_write call over a harness schema change would
# cost far more than the one field it exists to protect, and gate-task-scope.sh
# still catches the same intent stated in a task's own text regardless.
set -uo pipefail

payload="$(cat 2>/dev/null || true)"

if ! command -v python3 >/dev/null 2>&1; then
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"gate-issue-priority: python3 is missing, so this call cannot be checked for a Priority field. Refusing rather than reporting success -- install python3, or ask a human to make this GitHub write."}}\n'
  exit 0
fi

printf '%s' "$payload" | python3 -c '
import json
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

fields = (data.get("tool_input") or {}).get("issue_fields") or []
for field in fields:
    if not isinstance(field, dict):
        continue
    name = str(field.get("field_name", "")).strip().lower()
    if name == "priority" and not field.get("delete"):
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "gate-issue-priority: this call sets an issue Priority field. "
                    "Only @tigerblue77 validates that field, even when a document "
                    "already announces the change (CLAUDE.md, \"Priorities are not "
                    "ours to set\") -- propose the change in chat instead."
                ),
            }
        }))
        break
' 2>/dev/null

exit 0
