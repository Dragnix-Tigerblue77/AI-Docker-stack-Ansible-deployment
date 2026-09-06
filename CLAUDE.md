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
| What a service block must carry | the commented model in `roles/deploy_AIS_Docker_stack/templates/AIS.docker-compose.yml.j2`, below the service blocks |
| Why a lint rule is waived, and which ones | `.ansible-lint`, `.yamllint` (comments) |
| Why a check exists, and what it deliberately does not flag | the docstring of the script in `.github/scripts/` |
| How to set a clone up, what to run before pushing, and what submitting a contribution grants | `CONTRIBUTING.md` |
| What the commercial arm covers, and who actually needs one | `LICENSE-COMMERCIAL.md` |
| Who holds the copyright, and what in a checkout is not covered by the grant | `NOTICE` |

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
* **Priorities are not ours to set.** An issue's `Priority` field is agreed between @tigerblue77 and
  @Dragnix-23. A session may *propose* a change, with its argument -- in the chat, or as a row in the
  roadmap's proposal table (#33) -- but it never writes the field itself. Only @tigerblue77 validating
  it does. This holds **even when a document already announces the change**: #33 carried "Remontée de
  Low à High" for #12 for a day, and the session that dutifully applied it to the field was still
  wrong, because the announcement was a proposal nobody had validated. A roadmap records decisions; it
  does not make them.

## Language

The divergence with `Homelab_Ansible_deployment` is **only about what is read inside GitHub**,
because this repository is shared between two French speakers:

| | |
| --- | --- |
| **French** | issues, pull requests, `README.md`, `CONTRIBUTING.md`, issue templates |
| **English** | commit messages, code, comments, Ansible task names, error messages (`fail_msg`), PR closing keywords, `NOTICE`, `LICENSE-COMMERCIAL.md` |

`NOTICE` and `LICENSE-COMMERCIAL.md` sit on the English side while `CONTRIBUTING.md` sits on the
French one, and the split is not an oversight: the first two address a prospective licensee and stand
beside the English licence text, whereas the third addresses the two people who work here. That is
the same test as everywhere else -- who reads it -- applied to three files that look alike.

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

**No `.env` file, ever -- a secret a service needs is a variable passed to the role, interpolated by
Ansible straight into the compose template, same as everything else in it.** A `.env` read by Compose
through `${VAR}` is a second file to secure, a second path to keep in sync with the first, and a
migration question at the Swarm switch that interpolating at render time never raises: Ansible renders
the file the same way regardless of which one reads it next. #1 wrote one anyway, on its first pass --
the issue's own example config used `${POSTGRES_PASSWORD}`, and that was read as licence rather than as
an illustration to translate. It cost a second commit to undo.

**Images pinned by version**, never `:latest` -- nor the implicit tag, which *is* `:latest`.

**Commits.** Subject: one sentence, imperative, sentence case, no type prefix, no trailing full stop,
with the issue number in parentheses when there is one -- `Lay down the Ansible role and compose
skeleton of the AIS (#31)`. Body: prose paragraphs explaining *why* and what it cost to find out, not
a bullet list of what changed.

**Branches.** `claude/<short-topic>` for agent work, merged through a pull request. `main` is the only
long-lived branch.

**Licence.** Dual, and both arms exist since #35: AGPL-3.0-only for everyone, or a separately
negotiated commercial licence. Do not re-explain either here -- `LICENSE-COMMERCIAL.md` says what the
second arm covers and when it is needed, `NOTICE` carries the attribution and the third-party
material, and the licensing clause in `CONTRIBUTING.md` is what keeps a contribution offerable under
both. What is worth knowing in this file is the trap: a contribution merged without that clause
cannot be offered under the commercial arm afterwards without going back to its author, one by one.

Every authored source file carries an SPDX header, and **`reuse lint` checks it in CI** (#52) -- the
header is a gate here, not a habit. Two families cannot carry one and are declared in `REUSE.toml`
instead, each with its reason: `roles/*/templates/`, rendered onto the managed node where a header
would end up copied into the deployed compose file, and `**/*.json`, JSON having no comment syntax.
`LICENSE` is a symlink to `LICENSES/AGPL-3.0-only.txt`, so the file REUSE requires and the file
GitHub reads for the repository's licence badge are the same bytes.

**The gate has one hole, and it is the one that matters for #35.** `reuse lint` does not ask a
root file named `LICENSE*` for a header at all -- it reads those as licence texts. Measured: a
`LICENSE-COMMERCIAL.md` passes identically with a header and without one. So when the commercial arm
lands, nothing will check *its* header; that one stays a matter of review.

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
python3 .github/scripts/check_compose_template.py --selftest
python3 .github/scripts/check_compose_template.py          # the one that matters for the template
python3 .github/scripts/check_LiteLLM_account_isolation.py --selftest
python3 .github/scripts/check_LiteLLM_account_isolation.py
python3 .github/scripts/check_no_inventory_data.py --selftest
python3 .github/scripts/check_no_inventory_data.py
gitleaks dir . --no-banner --redact
```

Each of the three home-made checks knows how to verify itself with `--selftest` -- a check whose
failure nobody has ever seen is a check nobody believes. `check_compose_template.py` was the last
without one (#58); its cases are Python literals rather than fixture files, because a fixture on disk
is reachable by `ansible-lint --fix` and one of the LiteLLM ones was silently rewritten by it.

**`ansible-lint --fix` works, and stays working only because `.yamllint` agrees with ansible-lint's
own yamllint profile on six settings**: `comments.min-spaces-from-content`, `comments-indentation`,
`braces.max-spaces-inside`, the two `octal-values`, and `braces.min-spaces-inside`. Only the first
five are written out in `.yamllint`; the sixth holds because `extends: default` already supplies the
required 0, which is exactly why it is easy to break by overriding it without noticing.

Changing any of the six is choosing to lose `--fix`. On a plain run ansible-lint says so in a
*warning* -- "Found incompatible custom yamllint configuration" -- and carries on linting, so CI stays
green and the capability disappears with nothing failing. `--fix` itself is louder: it logs the same
thing as an ERROR and exits 3 without fixing anything. That is how it went unnoticed until #48 raised
the profile. The reason is written in `.yamllint` itself.

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

1. **`services:` carries the gateway since #1, and the empty-mapping rule still applies to whoever
   empties it.** `postgres` and `litellm` are the first two blocks; the rendered file passes
   `docker compose config`, and `litellm` publishes `4000` -- a reversal of #1's own original call,
   behind `UI_USERNAME` / `UI_PASSWORD`, made so an account can add its own provider keys from `/ui`
   on the LAN (see the role's README, "La passerelle et sa base"). What has not changed is the
   spelling trap the skeleton was written around: a bare `services:` with no value fails at `config`
   with `services must be a mapping`, which is why the empty state is spelled `{}` and not left blank.
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

**A session runs the same toolchain CI does, and the work to get there is #57.** The hook installs
the five pins into a virtual environment built on the interpreter the CI workflow names, so
`ansible-lint` here reports `using ansible-core:2.21.3` -- the pinned one. Trust a green lint in a
session; it is the same run.

Three things had to be got right for that, all measured, and none of them visible to CI, which gets
a clean 3.12 interpreter from `actions/setup-python` and never meets any of them:

* **The default interpreter is the wrong one.** `python3` is 3.11 here while the CI uses 3.12, and
  `ansible-core` has declared `Requires-Python >= 3.12` since 2.20 -- so it was simply refused, and a
  session started with no `ansible-core` and no `--syntax-check`. The image already carries 3.10,
  3.11, 3.12 and 3.13: nothing needs provisioning, the default is just wrong. The version is read
  from the workflow rather than written in the hook, so the two cannot drift.
* **A virtual environment, not `pip install`.** 3.12 here is a distribution package and PEP 668
  marks it externally managed, so a plain install is refused and `--break-system-packages` would
  write into an interpreter apt also uses.
* **The venv also settles the PyYAML problem** that once needed an `--ignore-installed` retry. The
  image carries Debian's PyYAML 6.0.1 without the `RECORD` file pip needs to remove it; a venv
  created without `--system-site-packages` never sees it, so the pinned 6.0.3 installs normally.

The pins are still installed one at a time rather than as a file, and that guard keeps its value:
pip resolves a requirements file as one unit, so one pin it cannot satisfy would take the other four
down with it. The hook also reads the installed versions back and names any drift from the file --
if a future pin is refused, the session loses that one tool and says so, rather than everything.

If a check could not be run, say so plainly rather than reporting it as passing.
