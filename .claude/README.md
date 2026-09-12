<!--
SPDX-FileCopyrightText: 2026 Tigerblue77
SPDX-License-Identifier: AGPL-3.0-only
-->

# `.claude/` — the agent team that works this repository

`settings.json` is JSON and cannot carry comments, so the reasoning behind each
choice lives here, in the register the rest of the repository uses. This
configuration is modelled on `Homelab_Ansible_deployment`'s own `.claude/` --
the two repositories share a maintainer and several working conventions -- but
it is not a copy: this repository has one role instead of eighty-odd, ships no
inventory at all, and carries risks of its own (a dual licence, an isolation
property between two LiteLLM accounts, a Priority field only one person
validates) that the homelab has no equivalent of. Where a choice differs from
the homelab repository's, the difference is explained below rather than left
for a reader to wonder whether it was noticed.

## What this configures

An [agent team](https://code.claude.com/docs/en/agent-teams): one lead session
you talk to, and three teammates defined in `agents/`, each a full Claude Code
instance with its own context window. They coordinate through a shared task
list and message each other directly.

| Teammate | Owns |
| --- | --- |
| `service-block-auditor` | The compose template's service blocks against the commented model; secrets kept as no-default variables; the LiteLLM account-suffix naming |
| `security-reviewer` | Secrets in the clear, LiteLLM isolation between the two accounts, inventory-data leakage, the licensing gate's one hole |
| `doc-keeper` | Prose that contradicts the code, the French/English split, the two READMEs staying non-overlapping |

Start one by asking the lead for it -- the teammates are spawned from these
definitions by name.

There is no `role-auditor` here. The homelab repository has eighty-seven roles
to sweep for idempotence and skeleton drift; this repository has exactly one,
and the unit that actually repeats -- one issue at a time -- is the service
block inside `templates/AIS.docker-compose.yml.j2`. `service-block-auditor`
owns that unit instead.

## Why these settings

- **`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`** — agent teams are off by
  default. Without it, no teammate is ever spawned and the `agents/`
  definitions are only used as ordinary subagents.
- **`CLAUDE_CODE_SUBAGENT_MODEL=claude-sonnet-5`** — each teammate carries its
  own context window, so a team costs several times a single session. The lead
  keeps the stronger model for judgement; the teammates do the volume on
  Sonnet.
- **`ansible-playbook` is narrowed, not denied outright, unlike the homelab
  repository's own blanket deny.** There the whole family is refused, including
  the harmless `--syntax-check`, because CI already runs it on every pull
  request and being structurally unable to deploy against a real household
  machine is worth more than running one check locally. Neither half of that
  trade-off holds here the same way: `--syntax-check` is not merely harmless,
  `CONTRIBUTING.md` asks every contributor to run it themselves before
  pushing, and this repository ships no inventory of its own to deploy
  against in the first place -- `playbook.AIS.example.yaml` targets a group
  name (`AIS_servers`) the caller has to supply. So `allow` keeps the existing
  `ansible-playbook --syntax-check:*` entry, and `deny` narrows to the flags
  that would actually point it at a host: `-i`, `--inventory`, `--limit`, plus
  `ansible-vault` (nothing here is vaulted, but a stray decrypt attempt against
  a caller's own vault file has no legitimate reason to happen from this
  repository either) and ad-hoc `ansible -m`/`-i`/`-a`. This is the same lesson
  the homelab repository's own `git push` deny already paid for once (#833,
  #834): a blanket deny over a family that has one legitimate, required member
  just gets routed around or blocks real delivery, so the deny is narrowed to
  the dangerous forms instead of covering the whole command.
- **`git push` is narrowed the same way the homelab repository settled on**:
  `deny` covers `git push origin main` and its `-u`/`--set-upstream`
  spellings, `HEAD:main`, and any `--force`/`--force-with-lease`/`-f` push;
  `allow` names the one legitimate shape, `git push ... origin claude/<topic>`.
  `main` is this repository's only long-lived branch too (CLAUDE.md,
  Conventions), so the reasoning transfers directly.
- **No deny on `.vault_pass` or on `roles/**/files/**`, unlike the homelab
  repository.** Both are deliberate omissions, not oversights. This repository
  has no `.vault_pass` and nothing vaulted at all -- every secret arrives as a
  caller-supplied role variable, so there is no vault file to protect from a
  read. And `roles/deploy_AIS_Docker_stack/files/` holds exactly one file,
  `librechat/librechat.yaml`: a configuration template this repository authors
  and reads secrets into only through `${VAR}` substitution LibreChat itself
  performs, not a backup of a running production database the way the homelab
  repository's `roles/*/files/*.sql` dumps are. A deny modelled on that one
  would block legitimate work on the one file it exists to protect nothing on
  today. If a role ever ships a real data dump under `files/`, add the deny
  then, for the reason the homelab repository's own comment gives.
- **`ssh`, `scp` and `rsync` are denied.** This repository presupposes no
  machine at all -- there is nothing for an agent here to legitimately reach
  over any of the three.
- **`reuse:*` and `ansible-galaxy:*` are added to `allow`.** Both were already
  run by CI and asked of every contributor (`CONTRIBUTING.md`) but were missing
  from the pre-existing allow list, which otherwise only had `ansible-lint`,
  `--syntax-check`, `gitleaks` and the three home-made checks. `git add`,
  `git commit`, `git checkout`, `git stash` and the narrowed `git push` are
  added for the same reason: without them, this repository's `.claude/`
  configuration could check a change but never actually deliver one.
- **No `defaultMode`.** The permission mode is the one knob that decides how
  much runs without you, so it is not checked into the repository. Choose it
  per run.

## The three gates

Hooks are the deterministic half of the guardrails -- they are the harness
running a script, not the model deciding to behave.

- **`hooks/gate-task-scope.sh`** on `TaskCreated`. Refuses a task whose stated
  intent is a real Ansible run, a touch on `ansible-vault`, a fabricated or
  revealed secret value, a hardcoded IP address, setting or changing an
  issue's `Priority` field, landing on `main`, or opening a pull request as a
  draft -- before a teammate claims it and spends a context window discovering
  that the command it needs is denied.
- **`hooks/gate-lint.sh`** on `TaskCompleted`. Runs `yamllint`, `reuse lint`,
  `ansible-lint`, `ansible-playbook --syntax-check`, all three home-made checks
  in `.github/scripts/` (`--selftest` then plain, same as CI's own
  `home-made-checks` job), and `gitleaks` -- exactly what
  `.github/workflows/ansible-ci.yml` and `gitleaks.yml` gate a pull request
  on -- and refuses the completion while any of them is red.
- **`hooks/gate-issue-priority.sh`** on `PreToolUse`, matched to
  `mcp__github__issue_write` (#97). Reads the call's `tool_input.issue_fields`
  and refuses -- via `hookSpecificOutput.permissionDecision: "deny"`, the
  documented, non-deprecated way to block a `PreToolUse` call -- any entry
  naming the `Priority` field that is not itself a deletion. This is a second,
  independent layer on top of `gate-task-scope.sh`'s phrasing match: that one
  sees a task's stated intent, this one sees the structured call itself, after
  a teammate has decided to make it anyway.

! All three gates exit 2 (`gate-task-scope.sh`, `gate-lint.sh`) or answer
`"deny"` (`gate-issue-priority.sh`) when their own tooling is missing rather
than passing. A gate that cannot run its checks must not report success.

`TeammateIdle` is deliberately **not** wired, for the same reason the homelab
repository leaves it unwired: exit 2 there would keep a teammate working
forever, which is the one hook shape that can build a loop that never settles.

## What this does not protect against

The Priority-field rule and the "no fabricated secret" rule are enforced by
`gate-task-scope.sh` matching on phrasing, and by every teammate's own
instructions -- not by anything that inspects a GitHub API call. There is no
practical way to intercept "which field did this `issue_write` call change" at
the permission layer the way a `Bash` command prefix can be denied; a task
that never says what it is about to do is not caught by a gate that matches on
what a task says. The same limit applies to every enumerated `deny` above: a
force-push spelled with the flag in an order these prefixes do not anticipate,
or a secret asked for in phrasing the regex does not match, is not stopped
here. The real containment is that no task here has a legitimate reason to do
any of this, which each teammate's own hard-boundary section states directly
-- a model instruction, not an enforced gate.

## `loop.md`

The prompt a bare `/loop` runs, replacing Claude Code's built-in maintenance
prompt. It is the heartbeat: what the lead does each time it wakes with
nothing else pending. Edits take effect on the next iteration.
