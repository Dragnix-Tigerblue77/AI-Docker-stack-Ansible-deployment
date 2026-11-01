#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77
# SPDX-License-Identifier: AGPL-3.0-only

"""Refuse a Dependabot merge gate that cannot pass, misses a job, or leaves its merge unchecked.

WHY THIS CHECK EXISTS
---------------------
".github/rulesets/main.json" is the list of checks a Dependabot update has to pass before
".github/workflows/dependabot-auto-merge.yml" merges it. Nothing on GitHub's side reads that file:
the organisation's plan enforces no ruleset on a private repository, so the merge workflow reads it
itself. That makes it a file nothing else keeps honest, and it can go wrong in two directions, both
of them silent:

* A context names a job no workflow reports. GitHub matches a check by the job's display "name:" --
  never the workflow's name, never the job's key -- so renaming a job without editing the file
  leaves a context that never reports. Every Dependabot update then waits for a human, each gate run
  saying only that the check "has not reported yet", which is also what it says on every ordinary
  run while the other workflow is still going. Nothing about it looks broken.
* A job is missing from the file. The file names every job of the workflows the gate listens to,
  one by one, rather than a single aggregate job (the merge workflow's header says why). The price
  of that choice is that a job added to any of them gates nothing until somebody adds it here -- and
  meanwhile a Dependabot update that is red on that job alone merges itself, because the gate reads
  only what the file names. This check is what puts that addition in the same pull request.

A third way concerns what happens after the gate merges (#180). The merge is a push made with
GITHUB_TOKEN, which starts no workflow, so the gate dispatches every workflow it listens to on the
default branch itself -- the one event that token can cause and still get a run for. It names them
by FILE there, in the "WORKFLOW_FILES" of a step, where "on.workflow_run.workflows" names them by
"name:", and GitHub refuses a dispatch to a workflow without a "workflow_dispatch" trigger. A
workflow added to the second list and not the first, or a trigger removed, would leave every merge
commit unchecked, and would only show -- as a red job, or not at all -- after the next merge. The
one exception is a workflow that has nothing to say about the default branch, which NOT_DISPATCHED
names with its reason.

wader/postfix-relay keeps its own copy true with "tests/test_ruleset.py". This one does what that
does, plus the second direction above, which postfix-relay needs less because GitHub enforces its
file, and which this file needs because it names every job one by one rather than one aggregate job.

WHAT IT CHECKS
--------------
1. The file still gates the default branch: target "branch", enforcement "active",
   "~DEFAULT_BRANCH" with nothing excluded, no bypass actor, exactly one rule and of type
   "required_status_checks", with at least one context and none of them twice. A re-export made
   after clicking around the settings page can bring any of those back while the file still parses.
2. Every context is the display name of exactly one job in ".github/workflows/" -- its "name:", or
   its key when it has none, which is the name GitHub reports it under. Two jobs reporting one name
   would leave the gate reading whichever of them started last.
3. That job belongs to a workflow the merge workflow listens to ("on.workflow_run.workflows",
   matched against each workflow's top-level "name:"). The gate runs only when one of those
   completes, so a required job anywhere else could be the last to finish and never wake it.
4. Every job of those workflows is required, unless NOT_REQUIRED below names it with its reason.
5. The gate dispatches every one of those workflows after a merge -- its file is in the gate's
   "WORKFLOW_FILES", unless NOT_DISPATCHED excuses it -- and every file listed there exists and
   carries a "workflow_dispatch" trigger.
6. Every NOT_DISPATCHED entry still excuses something: it names a workflow file that exists, that
   the gate listens to, that has no "workflow_dispatch" trigger and that the gate does not dispatch.
   An exclusion that has stopped being true would otherwise keep waving a workflow past item 5.
7. The weekly model-drift workflow, when there is one, dispatches the very same files on the branch
   of the pull request it opens: its own "WORKFLOW_FILES" lists exactly the gate's. A pull
   request opened with GITHUB_TOKEN gets no check from GitHub either, so that list is a copy of the
   gate's, and a copy kept true by a comment is the kind that drifts: a third workflow added to the
   gate would leave the deletion pull request without it, which only shows as a check that is not
   there.

8. The branch the weekly model-drift workflow makes its deletion pull request on (REMOVALS_BRANCH)
   is the one the gate merges, and the `if:` of the gate's job lets a run on it through. The gate
   merges that pull request by itself, and a branch named differently on either side would leave
   it open for ever with every check green, which shows as nothing at all.

WHAT IT DELIBERATELY DOES NOT CHECK
-----------------------------------
Whether a required job actually RUNS on a pull request. A job that reports only on pushes to main
passes this check and then never reports on a Dependabot branch. Deciding that would mean reading
"on:" and every "if:" and guessing at expressions only GitHub evaluates; it is a decision made where
the list is edited, and the gate's own notice ("has not reported yet") is where a wrong one shows.

Whether the step carrying "WORKFLOW_FILES" really dispatches them, with the permission and the "if:"
that takes. That is a script and an expression GitHub runs, not a list; its job goes red, naming the
workflow, on the first merge it fails to follow up.

Its verification cases are Python literals rather than fixture files, for the reason CLAUDE.md
gives: a fixture on disk is reachable by "ansible-lint --fix", which has rewritten one here before.

Run it from the repository root:

    python3 .github/scripts/check_required_checks.py --selftest
    python3 .github/scripts/check_required_checks.py
"""

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RULESET = ROOT / ".github" / "rulesets" / "main.json"
WORKFLOWS = ROOT / ".github" / "workflows"
GATE = "dependabot-auto-merge.yml"
DRIFT = "LiteLLM_model_drift.yml"

# Jobs of a workflow the gate listens to that are deliberately NOT required, each with its reason --
# the same shape as the allowlist of "check_no_inventory_data.py", and for the same reason: an entry
# without one turns the list into a catch-all. Empty today, because every job of "Ansible CI",
# "gitleaks" and "sign-off" reaches a verdict on every pull request.
NOT_REQUIRED = {}

# Workflows the gate listens to that it deliberately does NOT dispatch on the default branch after a
# merge, each with its reason, under the same rule as NOT_REQUIRED. A workflow that reads the
# commits of a pull request has nothing to say about a merge commit on the default branch, and a
# dispatch there would only fail it for want of a range. An entry that stops being true is refused
# (item 6 of the docstring), so this list cannot outlive the reason written beside it.
NOT_DISPATCHED = {
    "sign-off.yml": "it reads the range of a pull request, which a dispatch on the default branch "
                    "does not have",
}

# The environment variable, on a step of the gate, whose value is the space-separated FILE names of
# the workflows that step dispatches on the default branch once the gate has merged (#180).
DISPATCH_ENV = "WORKFLOW_FILES"
# The branch of the weekly deletions, written where it is made and where it is merged.
BRANCH_ENV = "REMOVALS_BRANCH"


def triggers(workflow):
    """The "on:" mapping. YAML 1.1 reads the bare key "on" as the boolean true, as PyYAML does."""
    found = workflow.get("on", workflow.get(True))
    return found if isinstance(found, dict) else {}


def trigger_names(workflow):
    """Every event a workflow runs on, whichever of its three forms "on:" is written in."""
    found = workflow.get("on", workflow.get(True))
    if isinstance(found, str):
        return {found}
    if isinstance(found, (dict, list)):
        return set(found)
    return set()


def dispatched_files(gate):
    """The workflow files the gate dispatches after a merge: DISPATCH_ENV, on any of its steps."""
    files = []
    for job in ((gate or {}).get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            value = ((step or {}).get("env") or {}).get(DISPATCH_ENV)
            if value is not None:
                files.extend(str(value).split())
    return files


def env_values(workflow, name):
    """Every value the env variable `name` is given in a workflow, on a job or on one of its steps."""
    values = []
    for job in ((workflow or {}).get("jobs") or {}).values():
        for scope in [job or {}] + [step or {} for step in (job or {}).get("steps") or []]:
            value = (scope.get("env") or {}).get(name)
            if value is not None:
                values.append(str(value))
    return values


def filtered_on(workflow, text):
    """Whether the `if:` of a job of the workflow mentions `text`."""
    return any(text in str((job or {}).get("if") or "")
               for job in ((workflow or {}).get("jobs") or {}).values())


def workflow_name(file_name, workflow):
    """The name "workflow_run" matches on: the top-level "name:", or GitHub's fallback, the path."""
    return workflow.get("name") or ".github/workflows/" + file_name


def problems(ruleset, workflows, not_required=NOT_REQUIRED, not_dispatched=NOT_DISPATCHED):
    """Everything wrong with "ruleset" against "workflows", a {file name: parsed YAML} mapping."""
    found = []

    if ruleset.get("target") != "branch":
        found.append('"target" is %r, expected "branch".' % ruleset.get("target"))
    if ruleset.get("enforcement") != "active":
        found.append('"enforcement" is %r, expected "active".' % ruleset.get("enforcement"))
    ref_name = (ruleset.get("conditions") or {}).get("ref_name") or {}
    if ref_name.get("include") != ["~DEFAULT_BRANCH"] or ref_name.get("exclude") != []:
        found.append("it targets %r, expected the default branch and nothing excluded." % ref_name)
    if ruleset.get("bypass_actors") != []:
        found.append('"bypass_actors" is %r, expected none.' % ruleset.get("bypass_actors"))

    contexts = []
    rule_types = [rule.get("type") for rule in ruleset.get("rules") or []]
    if rule_types != ["required_status_checks"]:
        found.append("its rules are %r, expected exactly one required_status_checks." % rule_types)
    else:
        parameters = ruleset["rules"][0].get("parameters") or {}
        checks = parameters.get("required_status_checks") or []
        contexts = [check.get("context", "") for check in checks]
        if not contexts:
            found.append("it requires no check at all, which would merge unchecked updates.")
        for context in sorted({context for context in contexts if contexts.count(context) > 1}):
            found.append('required context "%s" is listed more than once.' % context)

    # Every display name a job reports under, with the workflows reporting it.
    reporters = {}
    for file_name, workflow in sorted(workflows.items()):
        for key, job in ((workflow or {}).get("jobs") or {}).items():
            display = (job or {}).get("name", key)
            reporter = (file_name, workflow_name(file_name, workflow))
            reporters.setdefault(display, []).append(reporter)
    if not reporters:
        found.append("no job was found under .github/workflows/ -- have the workflows moved?")

    listened = set()
    if GATE not in workflows:
        found.append("%s is missing, so nothing reads this file." % GATE)
    else:
        run = triggers(workflows[GATE] or {}).get("workflow_run") or {}
        listened = set(run.get("workflows") or [])
        if not listened:
            found.append("%s listens to no workflow, so it never runs." % GATE)
    named = {workflow_name(file_name, workflow or {}) for file_name, workflow in workflows.items()}
    for name in sorted(listened - named):
        found.append('%s listens to "%s", and no workflow carries that name.' % (GATE, name))

    for context in contexts:
        jobs = reporters.get(context, [])
        if not jobs:
            found.append('required context "%s" names no job, so it can never report.' % context)
        elif len(jobs) > 1:
            files = ", ".join(file_name for file_name, _ in jobs)
            found.append('required context "%s" is reported by %d jobs (%s): the gate would read '
                         "whichever started last." % (context, len(jobs), files))
        elif jobs[0][1] not in listened:
            found.append('required context "%s" comes from %s, which %s does not listen to: '
                         "finishing last, it would never wake the gate."
                         % (context, jobs[0][0], GATE))

    for display, jobs in sorted(reporters.items()):
        for file_name, name in jobs:
            if name in listened and display not in contexts and display not in not_required:
                found.append('job "%s" of %s is not required: an update red on it alone would '
                             "merge itself. Add it to main.json, or to NOT_REQUIRED with its "
                             "reason." % (display, file_name))

    # What the gate dispatches on the default branch once it has merged: every workflow it listens
    # to, since its merge starts no "push" run of any of them.
    if GATE in workflows:
        dispatched = dispatched_files(workflows[GATE])
        for file_name in dispatched:
            if file_name not in workflows:
                found.append('%s dispatches "%s" after a merge, and no workflow file has that name.'
                             % (GATE, file_name))
            elif "workflow_dispatch" not in trigger_names(workflows[file_name] or {}):
                found.append("%s dispatches %s after a merge, and %s has no workflow_dispatch "
                             "trigger: GitHub refuses the dispatch, so the merge goes unchecked."
                             % (GATE, file_name, file_name))
        for file_name, workflow in sorted(workflows.items()):
            if (workflow_name(file_name, workflow or {}) in listened and file_name not in dispatched
                    and file_name not in not_dispatched):
                found.append("%s listens to %s but does not dispatch it after a merge (%s): its "
                             "merge starts no push run, so that merge commit goes unchecked."
                             % (GATE, file_name, DISPATCH_ENV))
        for file_name in sorted(not_dispatched):
            stale = "NOT_DISPATCHED names %s, and %s: the entry excuses nothing, drop it."
            workflow = workflows.get(file_name)
            if file_name not in workflows:
                found.append(stale % (file_name, "no workflow file has that name"))
            elif workflow_name(file_name, workflow or {}) not in listened:
                found.append(stale % (file_name, "%s does not listen to it" % GATE))
            elif "workflow_dispatch" in trigger_names(workflow or {}):
                found.append("NOT_DISPATCHED names %s, which carries a workflow_dispatch trigger: "
                             "it can be dispatched after a merge, so put it in %s and drop the "
                             "entry." % (file_name, DISPATCH_ENV))
            elif file_name in dispatched:
                found.append(stale % (file_name, "%s dispatches it after a merge anyway" % GATE))

    # The same files, dispatched by the workflow that opens a pull request with the same token.
    if GATE in workflows and DRIFT in workflows:
        gate_files = dispatched_files(workflows[GATE])
        drift_files = dispatched_files(workflows[DRIFT])
        if not drift_files:
            found.append("%s dispatches nothing on the pull request it opens (%s): a pull request "
                         "opened with GITHUB_TOKEN starts no workflow, so it would go unchecked."
                         % (DRIFT, DISPATCH_ENV))
        elif sorted(set(drift_files)) != sorted(set(gate_files)):
            found.append("%s dispatches %s on its pull request, and %s dispatches %s after a "
                         "merge: the two lists name the checks a change has to pass, and must be "
                         "the same." % (DRIFT, " ".join(sorted(set(drift_files))), GATE,
                                        " ".join(sorted(set(gate_files)))))

    # The branch the weekly deletions are made on, which the gate merges: written in three places.
    if GATE in workflows and DRIFT in workflows:
        made = sorted(set(env_values(workflows[DRIFT], BRANCH_ENV)))
        merged = sorted(set(env_values(workflows[GATE], BRANCH_ENV)))
        if len(made) != 1:
            found.append("%s must give %s one value, the branch of the pull request it opens; it "
                         "gives %s." % (DRIFT, BRANCH_ENV, ", ".join(made) or "none"))
        elif merged != made:
            found.append("%s merges the pull request of the branch %s, and %s makes it on %s: "
                         "they must be the same branch, or the deletions never merge."
                         % (GATE, ", ".join(merged) or "(none)", DRIFT, made[0]))
        elif not filtered_on(workflows[GATE], made[0]):
            found.append("%s never lets a run of %s through its job filter: the `if:` of its job "
                         "does not name the branch." % (GATE, made[0]))

    return found


# The verification cases, built in memory: a baseline that passes, then one defect per case.
SELFTEST_CI = """
name: CI
on:
  pull_request:
  workflow_dispatch:
jobs:
  lint:
    name: the linter
    runs-on: ubuntu-latest
  build:
    runs-on: ubuntu-latest
"""

SELFTEST_GATE = """
name: Dependabot auto-merge
on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
jobs:
  merge:
    name: Merge
    runs-on: ubuntu-latest
    if: github.event.workflow_run.head_branch == 'removals'
    steps:
      - name: Merge
        env:
          REMOVALS_BRANCH: removals
  recheck:
    name: Recheck
    needs: merge
    runs-on: ubuntu-latest
    steps:
      - name: Dispatch
        env:
          WORKFLOW_FILES: ci.yml
"""

SELFTEST_NIGHTLY = """
name: Nightly
on:
  schedule:
    - cron: "0 3 * * *"
jobs:
  scan:
    name: scan
    runs-on: ubuntu-latest
"""

SELFTEST_PULL_REQUEST_ONLY = """
name: Range
on:
  pull_request:
jobs:
  read:
    name: the range reader
    runs-on: ubuntu-latest
"""

SELFTEST_OTHER = """
name: Other
on:
  pull_request:
  workflow_dispatch:
jobs:
  scan:
    name: the scanner
    runs-on: ubuntu-latest
"""


SELFTEST_DRIFT = """
name: Drift
on:
  schedule:
    - cron: "0 5 * * 1"
jobs:
  open:
    name: open the pull request
    runs-on: ubuntu-latest
    env:
      REMOVALS_BRANCH: removals
    steps:
      - name: Dispatch
        env:
          WORKFLOW_FILES: ci.yml
"""


def selftest_ruleset(*contexts, **overrides):
    ruleset = {
        "name": "main",
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [{
            "type": "required_status_checks",
            "parameters": {
                "required_status_checks": [{"context": context} for context in contexts],
            },
        }],
    }
    ruleset.update(overrides)
    return ruleset


def selftest_workflows(ci=SELFTEST_CI, gate=SELFTEST_GATE, extra=None, drift=None):
    workflows = {"ci.yml": yaml.safe_load(ci), "nightly.yml": yaml.safe_load(SELFTEST_NIGHTLY)}
    if gate is not None:
        workflows[GATE] = yaml.safe_load(gate)
    if extra is not None:
        workflows["extra.yml"] = yaml.safe_load(extra)
    if drift is not None:
        workflows[DRIFT] = yaml.safe_load(drift)
    return workflows


def selftest_cases():
    good = ("the linter", "build")
    rules = selftest_ruleset(*good)["rules"]
    return (
        # (what it proves, ruleset, workflows, text a problem must contain or None for no problem,
        #  and optionally the NOT_REQUIRED mapping, then the NOT_DISPATCHED one, to use)
        ("the baseline passes, and a job without a name reports under its key",
         selftest_ruleset(*good), selftest_workflows(), None),
        ("a context naming a job by its key rather than its display name is refused",
         selftest_ruleset("lint", "build"), selftest_workflows(), '"lint" names no job'),
        ("a job the file does not name is refused",
         selftest_ruleset("the linter"), selftest_workflows(),
         'job "build" of ci.yml is not required'),
        ("a job NOT_REQUIRED names, with its reason, is let through",
         selftest_ruleset("the linter"), selftest_workflows(), None, {"build": "a reason"}),
        ("a context reported by a workflow the gate does not listen to is refused",
         selftest_ruleset("the linter", "build", "scan"), selftest_workflows(),
         "does not listen to"),
        ("a gate listening to a workflow name nothing carries is refused",
         selftest_ruleset(*good), selftest_workflows(gate=SELFTEST_GATE.replace('"CI"', '"Ci"')),
         'listens to "Ci"'),
        ("a missing merge workflow is refused",
         selftest_ruleset(*good), selftest_workflows(gate=None), "is missing"),
        ("two jobs reporting one required name are refused",
         selftest_ruleset(*good), selftest_workflows(extra=SELFTEST_CI.replace("CI", "Other")),
         "is reported by 2 jobs"),
        ("a context listed twice is refused",
         selftest_ruleset("the linter", "build", "build"), selftest_workflows(), "more than once"),
        ("an empty list of checks is refused",
         selftest_ruleset(), selftest_workflows(), "requires no check"),
        ("enforcement other than active is refused",
         selftest_ruleset(*good, enforcement="evaluate"), selftest_workflows(), '"enforcement"'),
        ("a ruleset aimed at a named branch is refused",
         selftest_ruleset(*good, conditions={
             "ref_name": {"include": ["refs/heads/main"], "exclude": []},
         }),
         selftest_workflows(), "it targets"),
        ("a bypass actor is refused",
         selftest_ruleset(*good, bypass_actors=[{"actor_id": 5, "actor_type": "RepositoryRole"}]),
         selftest_workflows(), '"bypass_actors"'),
        ("a second rule is refused",
         selftest_ruleset(*good, rules=rules + [{"type": "deletion"}]), selftest_workflows(),
         "expected exactly one"),
        ("a listened workflow the gate does not dispatch after a merge is refused",
         selftest_ruleset(*good),
         selftest_workflows(gate=SELFTEST_GATE.replace("WORKFLOW_FILES: ci.yml", "OTHER: ci.yml")),
         "listens to ci.yml but does not dispatch it"),
        ("a dispatch list that leaves out one listened workflow is refused",
         selftest_ruleset(*good, "the scanner"),
         selftest_workflows(gate=SELFTEST_GATE.replace('["CI"]', '["CI", "Other"]'),
                            extra=SELFTEST_OTHER),
         "listens to extra.yml but does not dispatch it"),
        ("a dispatch list naming several files, one per listened workflow, passes",
         selftest_ruleset(*good, "the scanner"),
         selftest_workflows(gate=SELFTEST_GATE.replace('["CI"]', '["CI", "Other"]')
                            .replace("WORKFLOW_FILES: ci.yml", "WORKFLOW_FILES: ci.yml extra.yml"),
                            extra=SELFTEST_OTHER),
         None),
        ("a pull-request-only workflow the gate listens to is refused while nothing excuses it",
         selftest_ruleset(*good, "the range reader"),
         selftest_workflows(gate=SELFTEST_GATE.replace('["CI"]', '["CI", "Range"]'),
                            extra=SELFTEST_PULL_REQUEST_ONLY),
         "listens to extra.yml but does not dispatch it"),
        ("a pull-request-only workflow NOT_DISPATCHED names, with its reason, is let through",
         selftest_ruleset(*good, "the range reader"),
         selftest_workflows(gate=SELFTEST_GATE.replace('["CI"]', '["CI", "Range"]'),
                            extra=SELFTEST_PULL_REQUEST_ONLY),
         None, {}, {"extra.yml": "a reason"}),
        ("a NOT_DISPATCHED entry naming no workflow file is refused",
         selftest_ruleset(*good), selftest_workflows(), "no workflow file has that name: the entry",
         {}, {"gone.yml": "a reason"}),
        ("a NOT_DISPATCHED entry naming a workflow the gate does not listen to is refused",
         selftest_ruleset(*good), selftest_workflows(), "does not listen to it: the entry",
         {}, {"nightly.yml": "a reason"}),
        ("a NOT_DISPATCHED entry naming a workflow that gained workflow_dispatch is refused",
         selftest_ruleset(*good, "the scanner"),
         selftest_workflows(gate=SELFTEST_GATE.replace('["CI"]', '["CI", "Other"]'),
                            extra=SELFTEST_OTHER),
         "carries a workflow_dispatch trigger", {}, {"extra.yml": "a reason"}),
        ("a NOT_DISPATCHED entry naming a workflow the gate dispatches anyway is refused",
         selftest_ruleset(*good),
         selftest_workflows(ci=SELFTEST_CI.replace("  workflow_dispatch:\n", "")),
         "dispatches it after a merge anyway", {}, {"ci.yml": "a reason"}),
        ("a dispatched workflow without a workflow_dispatch trigger is refused",
         selftest_ruleset(*good),
         selftest_workflows(ci=SELFTEST_CI.replace("  workflow_dispatch:\n", "")),
         "ci.yml has no workflow_dispatch trigger"),
        ("a dispatched file no workflow carries is refused",
         selftest_ruleset(*good),
         selftest_workflows(gate=SELFTEST_GATE.replace("ci.yml", "ci.yml missing.yml")),
         '"missing.yml" after a merge, and no workflow file has that name'),
        ('"on:" written as a list is read, "workflow_dispatch" included',
         selftest_ruleset(*good),
         selftest_workflows(ci=SELFTEST_CI.replace("on:\n  pull_request:\n  workflow_dispatch:\n",
                                                   "on: [pull_request, workflow_dispatch]\n")),
         None),
        ("a drift workflow dispatching the very files the gate does passes",
         selftest_ruleset(*good), selftest_workflows(drift=SELFTEST_DRIFT), None),
        ("a drift workflow that dispatches nothing is refused",
         selftest_ruleset(*good),
         selftest_workflows(drift=SELFTEST_DRIFT.replace("WORKFLOW_FILES: ci.yml", "OTHER: ci.yml")),
         "dispatches nothing on the pull request it opens"),
        ("a drift workflow dispatching a file the gate does not is refused",
         selftest_ruleset(*good),
         selftest_workflows(drift=SELFTEST_DRIFT.replace("ci.yml", "ci.yml nightly.yml")),
         "the two lists name the checks a change has to pass, and must be the same"),
        ("a drift workflow leaving out one the gate dispatches is refused",
         selftest_ruleset(*good, "the scanner"),
         selftest_workflows(gate=SELFTEST_GATE.replace('["CI"]', '["CI", "Other"]')
                            .replace("WORKFLOW_FILES: ci.yml", "WORKFLOW_FILES: ci.yml extra.yml"),
                            extra=SELFTEST_OTHER, drift=SELFTEST_DRIFT),
         "the two lists name the checks a change has to pass, and must be the same"),
        ("a gate that merges another branch than the one the drift workflow makes is refused",
         selftest_ruleset(*good),
         selftest_workflows(gate=SELFTEST_GATE.replace("REMOVALS_BRANCH: removals",
                                                       "REMOVALS_BRANCH: other"),
                            drift=SELFTEST_DRIFT),
         "they must be the same branch"),
        ("a gate whose job filter does not name the branch is refused",
         selftest_ruleset(*good),
         selftest_workflows(gate=SELFTEST_GATE.replace("== 'removals'", "== 'other'"),
                            drift=SELFTEST_DRIFT),
         "does not name the branch"),
        ("a drift workflow that names no branch is refused",
         selftest_ruleset(*good),
         selftest_workflows(drift=SELFTEST_DRIFT.replace("REMOVALS_BRANCH: removals",
                                                         "OTHER: removals")),
         "must give REMOVALS_BRANCH one value"),
        ('"on:" written as a single event, other than "workflow_dispatch", is refused',
         selftest_ruleset(*good),
         selftest_workflows(ci=SELFTEST_CI.replace("on:\n  pull_request:\n  workflow_dispatch:\n",
                                                   "on: pull_request\n")),
         "ci.yml has no workflow_dispatch trigger"),
    )


def run_selftest():
    """Prove that the check refuses what it claims to refuse, and lets the baseline through."""
    failures = 0
    for case in selftest_cases():
        purpose, ruleset, workflows, needle = case[:4]
        not_required = case[4] if len(case) > 4 else {}
        not_dispatched = case[5] if len(case) > 5 else {}
        found = problems(ruleset, workflows, not_required, not_dispatched)
        if needle is None:
            passed = not found
        else:
            passed = any(needle in problem for problem in found)
        if passed:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s) -- expected %s, got %r"
                  % (purpose, "no problem" if needle is None else repr(needle), found))
    return 1 if failures else 0


def main():
    if "--selftest" in sys.argv[1:]:
        return run_selftest()

    ruleset = json.loads(RULESET.read_text(encoding="utf-8"))
    workflows = {
        path.name: yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(WORKFLOWS.glob("*.y*ml"))
    }
    found = problems(ruleset, workflows)
    if found:
        print("%s and the workflows no longer describe a gate that can pass and checks what it "
              "merges:" % RULESET.relative_to(ROOT))
        for problem in found:
            print("  - %s" % problem)
        return 1

    parameters = ruleset["rules"][0]["parameters"]["required_status_checks"]
    print("%d required check(s), each reported by one job of a workflow the gate listens to:"
          % len(parameters))
    for check in parameters:
        print('  "%s"' % check["context"])
    print("Dispatched on the default branch after each merge: %s"
          % ", ".join(dispatched_files(workflows[GATE])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
