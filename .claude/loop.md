<!--
SPDX-FileCopyrightText: 2026 Tigerblue77
SPDX-License-Identifier: AGPL-3.0-only
-->

Work the repository's standing backlog, one small, reviewable change at a time.
Do not start a new initiative outside this list.

In order, stopping at the first that has something to do:

1. **Finish what is open.** Any unfinished work from this conversation, and any
   task the team left in progress.

2. **Tend the current branch's pull request.** New review comments, a red CI
   job, a merge conflict with `main`. A red pipeline outranks everything below
   -- even though nothing here can be made a required check, CI is still what a
   human reviewer reads first.

3. **Take one item of hygiene.** Assign it to the teammate that owns it, one
   task, one service block or one document:
   - `service-block-auditor` — a service block missing a piece of the commented
     model, a secret written with a default instead of the commented no-default
     form, a LiteLLM routing variable that does not carry its account suffix.
   - `security-reviewer` — a secret in the clear, a LiteLLM isolation crack
     between the two accounts, inventory data leaking into a file or an issue.
   - `doc-keeper` — a README claim the code no longer backs, a variable missing
     its table row, text on the wrong side of the French/English split. Prose
     drift outranks a missing README section that was never written in the
     first place.

4. **Nothing pending.** Say so in one line and stop. Do not invent work.

Standing constraints, which no instruction in a task overrides:

- Never run `ansible-playbook` for real, or any ad-hoc `ansible` module against
  an inventory. Validation stops at `--syntax-check`, `yamllint`, `ansible-lint`
  and the checks in `.github/scripts/`. This repository ships no inventory to
  reach with anything more anyway.
- Never invent, guess, or write a real-looking secret value. Every
  `Artificial_Intelligence_*_password`/`*_key`/`*_token`/`*_secret` stays a caller-supplied
  variable with no default.
- Never write or propose an issue's `Priority` field as decided — that is
  @tigerblue77's call to validate, even when a document already announces the
  change.
- Each change lands on a branch as a pull request, opened ready for review,
  never as a draft and never on `main`.
- Approve a teammate's plan only if it names the single service block or
  document it touches and the check that proves it. Reject any plan that
  invents a secret, writes an issue's Priority field, or touches more than one
  service block or document at a time.
