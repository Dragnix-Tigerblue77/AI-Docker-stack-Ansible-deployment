<!--
SPDX-FileCopyrightText: 2026 Tigerblue77
SPDX-License-Identifier: AGPL-3.0-only
-->

# CLAUDE.md

Ansible deployment of the **AIS**. One role, one example playbook, and the checks that hold both to
their conventions. The repository is days old: most of what it will contain is still an issue.

This file says **how to work here**. `README.md` says what the repository is and does, and the two
deliberately do not overlap -- a second copy of a document drifts away from the first.

## Read these first, and do not restate them here

| Question | File |
| --- | --- |
| What the repository is, how the role is called, how to verify a template change | `README.md` |
| The contract the deployment role must meet, and every variable of the role | `roles/deploy_AIS_Docker_stack/README.md` |
| What a variable means and why its default is what it is | `roles/deploy_AIS_Docker_stack/defaults/main.yml` |
| What a service block must carry | the commented model at the top of `templates/AIS.docker-compose.yml.j2` |
| Why a lint rule is waived, and which ones | `.ansible-lint`, `.yamllint` (comments) |
| Why a check exists, and what it deliberately does not flag | the docstring of the script in `.github/scripts/` |
| How to set a clone up, and what to run before pushing | `CONTRIBUTING.md` |

## The vocabulary

**AIS** -- *Artificial Intelligence Stack*. The Docker stack this repository builds: LLM gateway,
vector database, reranker, Claude Code container, agents, connectors. It is one stack, deployed by
one role, and every service issue adds its block to the same compose template.

## How we work together

These are the rules that are about the conversation rather than about the code. They are here
because forgetting them costs the same time every session.

* **Never hand over a file to download.** Any manual step is given as a **pre-filled link**: an issue
  creation URL carrying its title and body, the GitHub settings page concerned, the direct link to
  the item to delete. Downloading a file, opening it and copying it back out is slow and tedious.
* **Proposals belong in the chat, not in an issue comment.** A comment posted to propose something is
  noise: the discussion happens in the session, and only the agreed result lands in the repository.
* **An issue's whole point lives in its description.** No essential context buried in comments. The
  fallback options considered in case the first choice fails are part of the description too.
* **One issue, one subject.** If a second subject appears, it is split off.
* **Pull requests are never opened as drafts.** Draft is the owner's call and nobody else's. Open it
  ready for review and say in the body what is not verified, rather than using draft to mean that.
* **The closing keyword is written in English**, `Closes #NN` or `Fixes #NN`, even when the rest of
  the body is in French: GitHub recognises no other form. `Ferme #31` does nothing at all, and that
  is exactly what left #31 open after #34 had merged.

## Language

The divergence with `Homelab_Ansible_deployment` is **only about what is read inside GitHub**,
because this repository is shared between two French speakers:

| | |
| --- | --- |
| **French** | issues, pull requests, `README.md`, `CONTRIBUTING.md`, issue templates |
| **English** | commit messages, code, comments, Ansible task names, error messages (`fail_msg`), PR closing keywords |

In other words: anything a third party would read in the code or in a run's output stays in English,
as in `Homelab_Ansible_deployment`. Only the conversation around the code is in French.

**This file is in English**, with the code rather than with the conversation: nearly every line of it
quotes a task name, a commit subject, a variable or an error message, and those are English. A French
sentence wrapped around an English quotation reads worse than either.

## Conventions

**Variables.** `Capitalised_Snake_Case` (`AIS_Docker_stack_name`, `AIS_published_Docker_network_name`).
Role variables are deliberately **not** prefixed with the role name -- the prefix would be
`deploy_AIS_Docker_stack_`, longer than most of what it qualifies -- and they carry the *stack's*
name, `AIS_`, which is what the caller has in mind. `var-naming[no-role-prefix]` is skipped for that,
and the pattern is widened rather than disabled, so a space, a dash or a leading digit in a name is
still an error.

**No inventory data, anywhere.** No IP address, no hostname, no domain, in the code or in an issue.
They belong to the caller's inventory: a role that carries them stops being reusable, and publishes
the homelab on the way. `check_no_inventory_data.py` is this rule, and it has a `--selftest` that checks the check itself.

**No secret in clear text, ever**, including in an example. The rendered compose file holds
everything the template interpolates, which is why the deployment role must write it `0600` and with
`diff: false`.

**Images pinned by version**, never `:latest` -- nor the implicit tag, which *is* `:latest`.

**Commits.** Subject: one sentence, imperative, sentence case, no type prefix, no trailing full stop,
with the issue number in parentheses when there is one -- `Lay down the Ansible role and compose
skeleton of the AIS (#31)`. Body: prose paragraphs explaining *why* and what it cost to find out, not
a bullet list of what changed.

**Branches.** `claude/<short-topic>` for agent work, merged through a pull request. `main` is the only
long-lived branch.

**Licence.** AGPL-3.0-only, with a commercial arm to be written (#35). Every authored source file
carries an SPDX header. `roles/*/templates/` does **not**: it is rendered onto the managed node, and
the header would end up copied into the deployed compose file. Nothing checks this yet -- `reuse lint`
is deferred for as long as the repository is unpublished, and `requirements.txt` says so -- the header
is a habit here, not a gate.

**A template change is not verified until the template has been rendered and the result parsed.**
Reading the diff is not verification, and neither is `git` reporting "Auto-merging": the conflicts
that hurt here are semantic, not textual. `check_compose_template.py` is what does it, and it renders
**both** states -- published network set and unset -- because the disabled state is the one nobody
looks at.

## Commands

There is no test suite in the unit-test sense. The checks below *are* the suite, and they are what CI
runs. None of them needs a machine of the homelab.

```bash
pip install -r requirements.txt                            # ansible-core, ansible-lint, yamllint, PyYAML (pinned)

yamllint .
ansible-lint
ansible-playbook --syntax-check playbook.AIS.example.yaml
python3 .github/scripts/check_compose_template.py          # the one that matters for the template
python3 .github/scripts/check_LiteLLM_account_isolation.py --selftest
python3 .github/scripts/check_LiteLLM_account_isolation.py
python3 .github/scripts/check_no_inventory_data.py --selftest
python3 .github/scripts/check_no_inventory_data.py
gitleaks dir . --no-banner --redact
```

Each home-made check knows how to verify itself with `--selftest` -- a check whose failure nobody has
ever seen is a check nobody believes.

**`ansible-lint --fix` works, and stays working only because `.yamllint` keeps five settings aligned
with ansible-lint's own yamllint profile** (`comments.min-spaces-from-content`, `comments-indentation`,
`braces.max-spaces-inside` and the two `octal-values`). Changing any of them is choosing to lose
`--fix`: ansible-lint refuses with "Found incompatible custom yamllint configuration", says so in a
*warning* and carries on linting, so the capability disappears with nothing failing. That is how it
went unnoticed until #48 raised the profile. The reason is written in `.yamllint` itself.

**`--fix` is not a no-op on a clean tree, though**, so run it on a clean tree, read the diff, and
keep only what you meant. Measured on this repository today: it strips a blank line from both
workflows and from the role's `meta/main.yml`, which no enabled rule asks for -- and it rewrites
`.github/scripts/tests/LiteLLM_account_isolation/15_fault_multiline_flow_fallback_litellm_config.yaml`,
collapsing the multi-line flow mapping that fixture exists to encode onto a single line. Its name says
`multiline_flow`; after `--fix` it no longer tests that, and the selftest still passes, so nothing
tells you.

## What blocks a pull request

**Nothing does, and that is worth knowing rather than discovering.** The organisation is on a plan
that allows neither a ruleset nor a branch protection on a private repository, so no CI check can be
made required before merging: the workflows **inform** the reviewer, they do not guard the door.

The one thing that actually refuses something is `.githooks/pre-commit`, and only in a clone
where `git config core.hooksPath .githooks` has been run. The session-start hook does it for a web
session, and only when `gitleaks` is installed -- the pre-commit hook refuses every commit without
it, deliberately.

## The deployment target

The role is **parameterisable**: the caller provides the inventory, the FQDNs, the reverse proxy
labels and the network, and names the role that actually deploys the stack through
`AIS_Docker_stack_deployment_role_name`. The role itself presupposes neither Swarm nor Compose, nor
any particular machine.

Today: Compose, on a test VM. Tomorrow: Swarm. What differs between the two is documented in the
role's README rather than frozen into the role.

## Invariants -- things that look wrong and are not

1. **`services: {}` is empty on purpose.** The skeleton describes what one adds *into*. It renders and
   parses, but `docker compose config` refuses a stack with no service, and that is correct until the
   first service issue lands.
2. **`false`, not `''`, means "not set".** ansible-core 2.19 rejects a bare truth test on a
   non-boolean, so the template writes `is string` to mean "set". Same idiom as the homelab
   repository's Docker and DNS roles.
3. **`restart_policy.condition: any`, never `on-failure`.** When a container turns unhealthy the
   orchestrator stops it cleanly, the process exits 0, and `on-failure` never replaces a task that
   exited cleanly: the service sits at 0 replicas and its URL answers a bare 404 with nothing logged.
4. **Everything under `deploy:`.** It is the only form *both* Compose and Swarm honour. `restart:`,
   `mem_limit:` and `cpus:` work under Compose and are ignored -- silently -- by Swarm.
5. **The commented service model lives inside a `{% raw %}` block.** Without it, its Jinja expressions
   would render their values, and an unset published network would print as `- False`.
6. **Variables reach the deployment role as `include_role` parameters**, never through a `set_fact` or
   a task-level `vars:`. Precedence 20 is the only form that beats a fact already set; that is what
   #459 cost the homelab repository.
7. **There is no `requirements.yml`.** The role uses `ansible.builtin.assert` and
   `ansible.builtin.include_role` and nothing else, so no collection is installed anywhere -- not in
   CI, not in the session-start hook. The first service issue that needs one brings it.

## Working in a Claude Code web session

`.claude/hooks/session-start.sh` installs what CI gates on: the pinned Python tooling and `gitleaks`,
and it enables `.githooks/` when both that directory and `gitleaks` are there. It is synchronous,
idempotent, best-effort, and does nothing outside a remote session. See its own header for the
detail, and its last line for which checks the session can actually be trusted to run.

One thing it has to work around, real and measured:

* **`pip install` needs `--ignore-installed` in this image.** It carries Debian's PyYAML 6.0.1 in
  `/usr/lib/python3/dist-packages`, installed by dpkg and so without the `RECORD` file pip needs to
  remove it. Without the retry, pip refuses the whole transaction -- ansible-core, ansible-lint and
  yamllint included -- over one package nobody asked to change. CI does not hit this: its
  `actions/setup-python` starts from a clean interpreter.

If a check could not be run, say so plainly rather than reporting it as passing.
