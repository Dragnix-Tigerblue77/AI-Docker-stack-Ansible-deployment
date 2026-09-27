<!--
SPDX-FileCopyrightText: 2026 Tigerblue77
SPDX-License-Identifier: AGPL-3.0-only
-->

# CLAUDE.md

Ansible deployment of the **Artificial Intelligence stack**: LLM gateway, vector database, reranker,
Claude Code container, agents, connectors. It is one stack, deployed by one role, and every service
issue adds its block to the same compose template. One role, one example playbook, and the checks
that hold both to their conventions. The repository is days old: most of what it will contain is
still an issue.

**The repository root is the role.** `tasks/`, `defaults/`, `templates/` and the rest of what
`ansible-galaxy init` would scaffold under a `roles/<name>/` sit here directly instead, which is what
lets a caller install this repository as the role `deploy_Artificial_Intelligence_Docker_stack` -- through Galaxy, a git
submodule, or a plain symlink -- without a wrapper directory that exists only for this checkout. See
invariant 8.

This file says **how to work here**. `README.md` says what the repository is and does, and the two
deliberately do not overlap -- a second copy of a document drifts away from the first.

## Read these first, and do not restate them here

| Question | File |
| --- | --- |
| What the repository is, how the role is called, how to verify a template change | `README.md` |
| The contract the deployment role must meet, and every variable of the role | `README.md` |
| What a variable means and why its default is what it is | `defaults/main.yml` |
| What a service block must carry | the commented model in `templates/Artificial_Intelligence.docker-compose.yml.j2`, below the service blocks |
| Why a lint rule is waived, and which ones | `.ansible-lint`, `.yamllint` (comments) |
| Why a check exists, and what it deliberately does not flag | the docstring of the script in `.github/scripts/` |
| Which checks a Dependabot update must pass before it merges itself, and why that list has that shape | `.github/rulesets/main.json`, and the header of `.github/workflows/dependabot-auto-merge.yml` |
| How to set a clone up, what to run before pushing, and what submitting a contribution grants | `CONTRIBUTING.md` |
| What the commercial arm covers, and who actually needs one | `LICENSE-COMMERCIAL.md` |
| Who holds the copyright, and what in a checkout is not covered by the grant | `NOTICE` |

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
* **Issues are written in English, and one that is not is flagged.** Titles, bodies and comments, in
  every repository but one group: the private repositories of the `Dragnix-Tigerblue77`
  organisation, where another language is fine. **This repository is in that group**, so its issues
  are written in French, as *Language* below says, and none of them is flagged. An issue found
  breaking this, in a repository it covers, is never let pass silently: the maintainer is told,
  every time, with the link, and offered a translation, which is made once they agree
  (Tigerblue77-personal/Homelab_Ansible_deployment#1006). It is written here all the same, as every
  shared rule is, for the session that moves on from here to a sibling where it does apply.
* **An issue opened in a session comes with its pull request.** Filing the issue and stopping there
  hands the work to the maintainer, who then has to rebuild from the description the context the
  session still had in front of it -- which is the expensive half, and the half that was already
  done. So the issue is written for the record and the branch is opened against it in the same
  breath, to the same standard as any other: the checks run, the reasoning in the commit message, the
  pull request body saying what could not be verified. The issue keeps its own job, which is to state
  the problem and the options so that both survive the pull request being closed.
  An open question in the issue is not a reason to withhold the pull request. It is a reason to
  implement the reading that was actually asked for, say in the body which one was taken, and leave
  the alternatives where the issue already lists them -- a branch is cheap to redirect, and a
  question waited out is a session's context thrown away. What does stay unwritten is a fix that
  would be guesswork: there the pull request is the one thing not opened, and the issue says so.
* **Issue and pull request text runs the full width GitHub gives it.** No hard line break inside a
  paragraph, in a body or in a comment: GitHub reflows prose to the reader's own window, so a body
  wrapped at 100 columns is a narrow strip down the middle of a wide screen, and every later edit has
  to be re-wrapped by hand to match the wrapping around it. What Markdown makes line-structured keeps
  its lines -- headings, list items, table rows, fenced code, the `>` of a blockquote -- and it is the
  prose inside them that is written one line per paragraph. This is deliberately the opposite of the
  rule for files in the repository, which stay wrapped: nothing ever reflows a file.
* **A rule given in the session is written into this file, in the same session.** A rule that only
  ever lives in a conversation has to be given again in the next one, at the same cost every time --
  which is the entire reason this section exists. So when the maintainer states one it lands here, and
  in the sibling's copy when it is a shared one, as part of the work it came up in rather than as a
  follow-up nobody schedules. **When it is unclear whether an instruction is a one-off for the task at
  hand or a standing rule, ask**: that question costs one line, while guessing wrong costs either a
  rule quietly lost or a one-off frozen into this file as doctrine.
* **A question asked in the session stays open until it is answered.** Asked once and then dropped is
  the same as not asked: an unanswered question is carried into every following reply until the
  maintainer answers it, because everything built downstream of the assumption made in its place may
  have to be redone. Silence is not an answer, and proceeding without one is how a decision ends up
  made by default rather than by anybody.
* **Nothing is assumed: an ambiguity is a question, not a judgement call.** Where two readings of an
  instruction would lead to materially different work, the question is put before the work starts,
  even though asking costs a round trip -- because guessing costs the work. This is the general form
  of the two rules above it, which are the same instinct applied to one particular ambiguity each. A
  default chosen silently is a decision nobody made, and it surfaces at review, which is the most
  expensive place for it to surface. The judgement being asked for is narrow: routine calls a careful
  colleague would make alone stay made alone, and what gets asked is what changes the shape of the
  deliverable.
* **A reply is as short as the decision it carries -- short, not thin.** A wall of prose is skipped
  whole, and what gets skipped includes the question that needed an answer; so the verdict comes
  first, then what it rests on, then what is being asked. The failure in the other direction costs
  as much, and trimming is not the goal: a question the maintainer asked is answered, and what was
  done, how, and what it will cost them stay in. What comes out is the narration -- the steps in the
  order they happened, and the reasoning already written into the commit message and the pull request
  body, where it survives and where repeating it here is the second copy that drifts. Tables and
  lists over paragraphs. The measure is not length, it is whether each line is one the maintainer
  would otherwise have had to ask for.
* **A request to merge says what the pull request brings.** Merging is the maintainer's act and
  nobody else's, so the ask carries what they need in order to decide, pull request by pull request:
  what it does, which goal it serves, what it changes, and -- whenever it changes something that runs
  -- how to test it, as the command to type or the thing to watch rather than "CI is green". What in
  it could not be verified, and why, stays in. Several at once come in the order they want merging
  in: the one their dependencies impose, and where nothing imposes one, the simplest first, so that
  each review starts from a smaller diff than the last. "This is ready" makes the maintainer go and
  work all of that out from the diff, which is the work the session was supposed to have already
  done, done twice.
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

**Variables.** `Capitalised_Snake_Case` (`Artificial_Intelligence_Docker_stack_name`, `Artificial_Intelligence_published_Docker_network_name`).
Role variables are deliberately **not** prefixed with the role name -- the prefix would be
`deploy_Artificial_Intelligence_Docker_stack_`, longer than most of what it qualifies -- and they carry the *stack's*
name, `Artificial_Intelligence_`, which is what the caller has in mind. `var-naming[no-role-prefix]` is skipped for that,
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

**Dependabot's minor and patch updates merge themselves once CI is green, in every repository.** A
Dependabot pull request sitting open with every check green is a defect in that process, not a task
for a human -- `Homelab_Ansible_deployment`'s #964 was one. A public repository gets it the way
wader/postfix-relay does: the required checks recorded in `.github/rulesets/`, GitHub enforcing
them, `gh pr merge --auto`. A private one cannot, since GitHub Free enforces no ruleset on a private
repository whoever owns it, so its `dependabot-auto-merge.yml` reads the same file and does the
checking itself before merging (invariant 9). Either way the list of required checks is a file in
the tree, and what gets through is decided by CI rather than by a guess about which ecosystem is
risky: majors wait for a human, and so does anything red. This rule is shared with every repository
the maintainer owns, and a copy of it lands in each one's own agent instructions.

**Pull requests are kept level with the default branch, and never required to be, in every
repository.** "Require branches to be up to date before merging" stays off --
`.github/rulesets/main.json` records it as `strict_required_status_checks_policy: false` -- because
whatever cannot be updated automatically would be blocked rather than behind: a conflict, a fork, a
draft, and every pull request after a Dependabot merge, which starts no workflow.
`.github/workflows/auto_update_pull_request_branches.yml` does the updating instead, after every
merge and hourly, as best effort, and leaves Dependabot's own pull requests to Dependabot: a rebase
pushed by anyone else strips the signature `dependabot-auto-merge.yml` checks before it merges
(#149). A public repository runs it, its minutes costing nothing; a private one, this one included,
carries the same file switched off behind the `PULL_REQUESTS_UPDATE_ENABLED` repository variable, so
that a workflow which runs nothing here is deliberate and not dead code, and switching it on is
setting that variable and a credential (#145). Shared like the rule above
(tigerblue77/Dell_iDRAC_fan_controller_Docker#512), and for the same reason (#147).

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
instead, each with its reason: `templates/`, rendered onto the managed node where a header would end
up copied into the deployed compose file, and `**/*.json`, JSON having no comment syntax.
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
ansible-galaxy collection install -r requirements.yml       # community.docker, since #76

yamllint .
ansible-lint
ansible-playbook --syntax-check playbook.Artificial_Intelligence.example.yaml
python3 .github/scripts/check_compose_template.py --selftest
python3 .github/scripts/check_compose_template.py          # the one that matters for the template
python3 .github/scripts/check_LiteLLM_account_isolation.py --selftest
python3 .github/scripts/check_LiteLLM_account_isolation.py
python3 .github/scripts/check_no_inventory_data.py --selftest
python3 .github/scripts/check_no_inventory_data.py
python3 .github/scripts/check_required_checks.py --selftest
python3 .github/scripts/check_required_checks.py
gitleaks dir . --no-banner --redact
```

Each home-made check knows how to verify itself with `--selftest` -- a check whose failure nobody
has ever seen is a check nobody believes. `check_compose_template.py` was the last without one
(#58); its cases are Python literals rather than fixture files, because a fixture on disk is
reachable by `ansible-lint --fix` and one of the LiteLLM ones was silently rewritten by it.

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
keep only what you meant. Measured on this repository today: it strips blank lines from the
workflows and from the role's `meta/main.yml`, which no enabled rule asks for -- and it rewrites
`.github/scripts/tests/LiteLLM_account_isolation/15_fault_multiline_flow_fallback_litellm_config.yaml`,
collapsing the multi-line flow mapping that fixture exists to encode onto a single line. Its name says
`multiline_flow`; after `--fix` it no longer tests that, and the selftest still passes, so nothing
tells you.

## What blocks a pull request

**For a human's merge, nothing does, and that is worth knowing rather than discovering.** The
organisation is on a plan that allows neither a ruleset nor a branch protection on a private
repository, so no CI check can be made required before merging: the workflows **inform** the
reviewer, they do not guard the door.

**Dependabot's updates are the exception.** `dependabot-auto-merge.yml` merges a minor or patch one
only once every check `.github/rulesets/main.json` names has succeeded on its head commit -- every
job of `ansible-ci.yml` and `gitleaks.yml`, by display name (invariant 9). Renaming a job or adding
one therefore changes what gates those merges, and `check_required_checks.py` fails CI until the
file follows.

The one thing that actually refuses a human's change is `.githooks/pre-commit`, and only in a clone
where `git config core.hooksPath .githooks` has been run. The session-start hook does it for a web
session, and only when `gitleaks` is installed -- the pre-commit hook refuses every commit without
it, deliberately.

## The deployment target

The role is **parameterisable**: the caller provides the inventory, the FQDNs, the reverse proxy
labels and the network, and names the role that actually deploys the stack through
`Artificial_Intelligence_Docker_stack_deployment_role_name`. The role itself presupposes neither Swarm nor Compose, nor
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
7. **`requirements.yml` exists since #76, and it names exactly one collection.** The role used only
   `ansible.builtin.assert` and `ansible.builtin.include_role` until then; LibreChat's admin account
   (#76) needs `community.docker.docker_host_info` and `docker_container_exec` to reach the running
   container, and those are what brought the file, the `ansible-galaxy collection install` step in
   CI and in the session-start hook, and the `docker` Python SDK requirement on the managed node
   (stated in the role's own README, since it is that machine's requirement, not this repository's).
8. **The repository root doubles as the role, and `playbook.Artificial_Intelligence.example.yaml` is the one place that
   costs something.** Ansible's own role search never treats "the directory this playbook happens to
   sit in" as a candidate -- only `<playbook_dir>/roles/` and a short list of well-known locations,
   `~/.ansible/roles` among them -- so the example playbook's bare `- role: deploy_Artificial_Intelligence_Docker_stack`
   would not resolve against this checkout on its own. The `ansible-lint` and `syntax-check` jobs of
   `.github/workflows/ansible-ci.yml`, step 5 of `.claude/hooks/session-start.sh`, and
   `CONTRIBUTING.md`'s one-time-per-clone setup all symlink the checkout into
   `~/.ansible/roles/deploy_Artificial_Intelligence_Docker_stack` for exactly this reason, before anything reads the
   example playbook. Nothing else in this repository needs it: every other job lints or reads the
   role's own files directly, at their own path, with no role resolution involved.
9. **`dependabot-auto-merge.yml` merges directly, and does its own checking first.** `gh pr merge
   --auto` needs a ruleset GitHub enforces, and the organisation's plan enforces none on a private
   repository. So the workflow reads `.github/rulesets/main.json` from `main`, checks that every
   context in it concluded `success` on the pull request's exact head commit, and merges pinned to
   that SHA. Two "simplifications" undo it. Going back to `--auto` makes it inert: nothing would
   ever merge, and Dependabot's pull requests would pile up green again. A direct merge without the
   checking lands updates nothing checked: nothing else here would stop it. It runs on
   `workflow_run`, from `main`'s definition, and checks nothing out, because it is the one job
   holding a write token and no job may both hold one and run code from a pull request -- a freshly
   bumped dependency is exactly that code. `main.json` names every job of the two workflows one by
   one rather than one aggregate job (the workflow's header says why), and
   `check_required_checks.py` holds it to them in both directions. The day the repository can
   enforce a ruleset, import `main.json` and take postfix-relay's `--auto` workflow instead.

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
