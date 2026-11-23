#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Tigerblue77 and the AI Docker stack Ansible deployment contributors
# SPDX-License-Identifier: AGPL-3.0-only
# TaskCreated gate: refuse tasks whose stated intent is outside what an agent may
# do in this repository, before any work starts.
#
# The permission layer already denies most of the matching tool calls (see
# permissions.deny in .claude/settings.json). This gate exists one level earlier,
# on intent: a task reading "invente une vraie clé LiteLLM pour tester" would
# otherwise be claimed and worked on before collapsing at the first denied or
# missing command.
#
# ! Matching is on the whole payload rather than a named field, so it keeps
# working if the TaskCreated schema gains or renames one.
set -uo pipefail

payload="$(cat 2>/dev/null || true)"

deny() {
  echo "gate-task-scope: refused -- $1" >&2
  echo "Rewrite the task within what CLAUDE.md allows, or raise it in chat instead." >&2
  exit 2
}

# A real ansible-playbook run. --syntax-check is the one form a session validates
# with, so it alone is not refused. CI goes one step further, and only CI: its two
# "role run" jobs run the example playbook against a stand-in deployer and
# ".github/role_run/inventory.ini", on a runner that has Docker. Anything else is a
# real run against whatever the caller passes as -i, and this repository ships no
# inventory of its own to reach with it ("No inventory data, anywhere", CLAUDE.md).
if printf '%s' "$payload" | grep -Eqi 'ansible-playbook' \
  && ! printf '%s' "$payload" | grep -Eqi -- '--syntax-check'; then
  deny "this task runs ansible-playbook for real. A session validates with --syntax-check; the one real run is CI's two role run jobs, against a stand-in deployer."
fi

# An ad-hoc Ansible module run, or an explicit inventory/limit flag on anything.
if printf '%s' "$payload" | grep -Eqi 'ansible[[:space:]]+-[mia][[:space:]]|--limit[[:space:]=]|--inventory[[:space:]=]'; then
  deny "this task points Ansible at an inventory or limits it to a host. This repository ships no inventory of its own -- that is the caller's, by design."
fi

# Anything aimed at ansible-vault. Nothing in this repository is vaulted: every
# secret the role interpolates is a variable with no default, supplied by the
# caller from ITS OWN vault, never read from one here.
if printf '%s' "$payload" | grep -Eqi 'ansible-vault'; then
  deny "this task touches ansible-vault. Nothing in this repository is vaulted -- a secret here is a role variable with no default, not a vaulted file."
fi

# Fabricating or revealing a real secret value, rather than treating every
# Artificial_Intelligence_*_password / _key / _token / _secret variable as mandatory-with-no-default.
if printf '%s' "$payload" | grep -Eqi '(the real|the actual|a genuine|a working|an actual)[^.!?]{0,40}(API[-_ ]?key|master key|password|token|secret)'; then
  deny "this task asks for a real secret value. Every secret this role interpolates is a variable with no default, supplied by the caller -- never invented or looked up here."
fi

# A literal IPv4 address. FQDNs and hostnames are check_no_inventory_data.py's own
# job (it renders and parses, which a regex on task text cannot do reliably) --
# this catches the one shape that is unambiguous in plain text.
if printf '%s' "$payload" | grep -Eqi '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b'; then
  deny "this task names an IP address. 'No inventory data, anywhere' (CLAUDE.md) holds for a task description too, not only for committed code."
fi

# Setting or changing an issue's Priority field. Only @tigerblue77 validates that
# field -- even when a roadmap document already announces the change (CLAUDE.md's
# own worked example: #33 carried a change for a day before it was reverted as
# unvalidated).
if printf '%s' "$payload" | grep -Eqi '\b(set|change|update|bump|raise|lower)\b[^.!?]{0,30}\bpriority\b|\bpriority\b[^.!?]{0,20}\b(field|label)\b[^.!?]{0,20}\b(to|as)\b'; then
  deny "this task sets or changes an issue's Priority field. That is @tigerblue77's call to validate, never an agent's -- propose the change in chat instead."
fi

# Pushing to, or merging into, the protected branch.
if printf '%s' "$payload" | grep -Eqi 'push[^.!?]{0,40}\bmain\b|merge[^.!?]{0,40}\binto[[:space:]]+main\b|force[- ]push'; then
  deny "work lands on main through a reviewed pull request, never from a task."
fi

# Opening a pull request as a draft. Draft is the owner's call, nobody else's.
if printf '%s' "$payload" | grep -Eqi '\bdraft\b[^.!?]{0,25}\b(pull request|PR)\b|\b(pull request|PR)\b[^.!?]{0,25}\bdraft\b|\bopen\b[^.!?]{0,20}\bas\b[^.!?]{0,10}\bdraft\b'; then
  deny "pull requests are never opened as draft here. Open it ready for review and say in the body what is not verified."
fi

exit 0
