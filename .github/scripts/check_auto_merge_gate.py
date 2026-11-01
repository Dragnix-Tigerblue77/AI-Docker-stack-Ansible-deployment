#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77
# SPDX-License-Identifier: AGPL-3.0-only

"""Run the merge step of dependabot-auto-merge.yml against a made-up GitHub, one pull request at a time.

WHY THIS CHECK EXISTS
---------------------
That step decides, with a write token and nobody watching, whether a pull request merges. It is
JavaScript inside a YAML string: yamllint reads it as text, "check_required_checks.py" reads the
names around it, and nothing else ever executes it -- so a guard that stops guarding (a comparison
turned the wrong way, a condition dropped in an edit) is seen by nobody until the day it should have
refused. This check extracts the step's script and its environment from the workflow itself, runs it
with Node over a GitHub that answers what each scenario says, and compares what it merged with what
it should have.

WHAT IT RUNS
------------
* the Dependabot updates the step has always merged or refused (a signed minor with every check
  green, a major, an unsigned commit, a signed commit by a person on the branch, no update-type);
* which pull request the step takes for the commit that was checked: one that is in a fork, against
  another branch, closed, no longer at that commit, or one of two at the same commit is not taken;
* the shape of the ruleset it reads (no rule of required checks, two, none required);
* the weekly model deletions: the ones that must merge (one entry, five, a commented-out entry, a
  diff that placed the deletion a few identical lines away from where an entry starts, the entry
  together with the cascade slots that named it) and every shape that must not (a setting, even one
  with a comment after it, or an address deleted, an entry cut short, a slot of an entry that stays,
  a line added, six entries, a body that asks for a reading, a head behind the default branch, caps
  that are not numbers, and so on);
* every check the ruleset names but "sign-off", each tried missing and red, so that widening the list
  of checks the step excuses is noticed; a check posted by another app; and the latest of several
  runs of one check, whichever order the API lists them in.

The checks the ruleset names are read from the real ".github/rulesets/main.json", and the heading of
the body from the real script that writes it, so that renaming "sign-off" or the heading in one place
only fails here. The made-up GitHub does not answer whatever it is asked: every call is compared with
what the scenario's own pull request implies (the repository, the ruleset's path and ref, the head
commit, the pull request number, the comparison, the merge method) and anything else throws, which is
how a step that reads main's checks instead of the head's, or merges another pull request, is noticed.
A refusal scenario also names the text its notice must contain, so that it cannot go on passing
because a second guard refuses what the one it is about stopped refusing. The wiring the scenarios
cannot play -- the step's HEAD_SHA, the job output that starts the job checking main after a merge,
that job's condition -- is checked in the workflow itself.

"--selftest" proves the scenarios can fail: it breaks the step's script, and its environment, one
guard at a time and requires some scenario to notice each. A guard no scenario notices is a guard
this check cannot vouch for; a guard whose text has moved fails the selftest too, so the list below
follows the script instead of rotting beside it; and a break that leaves a script which throws proves
nothing and fails.

WHAT IT DOES NOT PROVE
----------------------
That GitHub answers as the scenarios say. It does not call GitHub: the shape of its answers is
octokit's as github-script returns it, written from the documentation and the runs seen so far, not
recorded. It does not play the job that checks main afterwards, only the output that starts it. And
the checks inside the function that reads the deleted lines which no layout of the real model list
can reach are backstops without a scenario of their own. Node is needed: the workflow's own runner
has one for the action, but this check wants "node" on the PATH, which the CI job installs.
"""

import difflib
import json
import pathlib
import re
import shutil
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "dependabot-auto-merge.yml"
RULESET = ROOT / ".github" / "rulesets" / "main.json"
DRIFT_SCRIPT = ROOT / ".github" / "scripts" / "check_LiteLLM_model_drift.py"
HEAD_SHA = "0123456789abcdef0123456789abcdef01234567"

# Plays the step's script against one scenario at a time. "github", "context" and "core" are the three
# objects github-script hands a script; only what the step calls is made up. Every call is checked
# against what the scenario says it should be about -- the repository, the ruleset's path and ref, the
# head commit, the pull request number, the comparison, the merge method -- and a call that asks for
# anything else throws an "unexpected" error: a step that reads the wrong commit or merges the wrong
# pull request would otherwise be answered with the right data and look fine.
HARNESS = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const run = new AsyncFunction('github', 'context', 'core', 'process', input.script);

async function play(scenario) {
  const merges = [];
  const notices = [];
  const outputs = {};
  let failed = null;
  const pr = scenario.pr;
  const expect = (what, got, want) => {
    if (got !== want) throw new Error(`unexpected ${what}: ${JSON.stringify(got)}, expected ${JSON.stringify(want)}`);
  };
  const about = (args) => { expect('owner', args.owner, 'o'); expect('repo', args.repo, 'r'); };
  const github = {
    paginate: async (fn, args) => fn(args),
    rest: {
      repos: {
        getContent: async (args) => {
          about(args);
          expect('ruleset path', args.path, input.ruleset_path);
          expect('ruleset ref', args.ref, 'main');
          return { data: { content: Buffer.from(JSON.stringify(scenario.ruleset ?? input.ruleset)).toString('base64') } };
        },
        listPullRequestsAssociatedWithCommit: async (args) => {
          about(args);
          expect('commit_sha', args.commit_sha, input.head_sha);
          return { data: scenario.associated ?? [pr] };
        },
        compareCommitsWithBasehead: async (args) => {
          about(args);
          expect('basehead', args.basehead, `main...${input.head_sha}`);
          return { data: { behind_by: scenario.behind_by } };
        },
      },
      pulls: {
        listCommits: async (args) => { about(args); expect('pull_number', args.pull_number, pr.number); return scenario.commits; },
        listFiles: async (args) => { about(args); expect('pull_number', args.pull_number, pr.number); return scenario.files; },
        merge: async (args) => {
          about(args);
          expect('pull_number', args.pull_number, pr.number);
          expect('merge_method', args.merge_method, 'merge');
          merges.push(args);
          return {};
        },
      },
      checks: {
        listForRef: async (args) => { about(args); expect('ref', args.ref, input.head_sha); return scenario.checks; },
      },
    },
  };
  const core = {
    notice: (message) => notices.push(String(message)),
    setFailed: (message) => { failed = String(message); },
    setOutput: (name, value) => { outputs[name] = value; },
  };
  const context = { repo: { owner: 'o', repo: 'r' }, payload: { repository: { default_branch: 'main' } } };
  let crashed = null;
  try {
    await run(github, context, core, { env: { ...input.env, HEAD_SHA: input.head_sha, ...scenario.env } });
  } catch (error) {
    crashed = String(error && error.stack || error);
  }
  let result = 'not merged';
  if (merges.length === 1) {
    if (merges[0].sha !== input.head_sha) result = 'merged without the head pinned';
    else if (outputs.merged !== 'true') result = 'merged without telling the job that checks main afterwards';
    else result = 'merged';
  } else if (merges.length > 1) {
    result = 'merged twice';
  } else if (outputs.merged === 'true') {
    result = 'announced a merge that did not happen';
  }
  return { result, failed, crashed, notices };
}

(async () => {
  const out = [];
  for (const scenario of input.scenarios) out.push(await play(scenario));
  process.stdout.write(JSON.stringify(out));
})();
"""


# ---------------------------------------------------------------------------------------------------
# The model list in miniature: the shapes of the real file that matter to what the step reads.
# ---------------------------------------------------------------------------------------------------

def entry(name, address=False, key="GEMINI"):
    lines = ["  - model_name: %s" % name, "    litellm_params:", "      model: provider/%s" % name,
             '      api_key: "os.environ/%s_API_KEY"' % key]
    if address:
        lines.append("      api_base: http://gateway.invalid:1234/v1")
    return lines + [""]


# A setting with a comment after it, as the real file has several: a rule that read "#" anywhere in a
# line as a comment would let it go.
SETTING = "  turn_off_message_logging: true   # kept out of the logs"
# An entry that is commented out, which the tool deletes like any other and which counts as an entry.
COMMENTED = ["  # - model_name: gone", "  #   litellm_params:", "  #     model: provider/gone",
             '  #     api_key: "os.environ/GEMINI_API_KEY"', "  #"]


def miniature(count=8):
    names = ["m%d" % i for i in range(count)]
    lines = ["model_list:", "  # A comment above the first entry."]
    for index, name in enumerate(names):
        lines += entry(name, address=(index == 3), key="MISTRAL" if index >= 6 else "GEMINI")
        if index == 2:
            lines += COMMENTED + [""]
    lines += ["router_settings:", "  routing_strategy: simple-shuffle", "  fallbacks:",
              "    - fast: &fast_cascade"]
    lines += ["        - %s" % name for name in names]
    lines += [SETTING, "{% if has.Gemini %}", "  extra: 1", "{% endif %}", ""]
    return names, lines


def patch_between(old, new):
    """The "patch" field GitHub gives for a file: a unified diff with three lines of context."""
    body = list(difflib.unified_diff(old, new, lineterm="", n=3))[2:]
    return "\n".join(body)


def counts(patch):
    rows = patch.split("\n")
    return (sum(1 for row in rows if row.startswith("+")), sum(1 for row in rows if row.startswith("-")))


def deletion(old, remove):
    """Patch of "old" with the lines at the indexes of "remove" taken out, and the lines it leaves."""
    new = [line for index, line in enumerate(old) if index not in remove]
    return patch_between(old, new), new


def block_of(lines, name):
    """Indexes of the lines of the entry "name": its header, everything indented under it, and the
    blank line that separates it from the next one, which is how the tool deletes an entry."""
    start = lines.index("  - model_name: %s" % name)
    end = start + 1
    while end < len(lines) and lines[end].startswith("    "):
        end += 1
    if end < len(lines) and lines[end] == "":
        end += 1
    return list(range(start, end))


def slot_of(lines, name):
    return [lines.index("        - %s" % name)]


def shifted_deletion(names, base):
    """The patch that deletes a whole entry as git shows it when the entry above ends with the same key
    line: the deletion starts on that line, inside the entry above, and the entry's own is shown as kept.
    Which entry git does that for depends on its tie-breaking, so it is looked for."""
    for name in names:
        patch = deletion(base, set(block_of(base, name)))[0]
        first = next(row for row in patch.split("\n") if row.startswith("-"))
        if first.startswith("-      "):
            return patch
    raise SystemExit("no entry of the miniature file is shown by git starting inside the entry above, "
                     "so the scenario about placements would prove nothing: change the miniature file.")


# ---------------------------------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------------------------------

def contexts():
    rules = json.loads(RULESET.read_text(encoding="utf-8"))["rules"]
    return [check["context"] for rule in rules if rule["type"] == "required_status_checks"
            for check in rule["parameters"]["required_status_checks"]]


def review_heading():
    found = re.search(r'^REVIEW_HEADING = "([^"]+)"', DRIFT_SCRIPT.read_text(encoding="utf-8"), re.M)
    if not found:
        raise SystemExit("%s no longer defines REVIEW_HEADING." % DRIFT_SCRIPT.relative_to(ROOT))
    return found.group(1)


def run_of(name, conclusion="success", started="1", status="completed", app="github-actions"):
    return {"name": name, "status": status, "app": {"slug": app}, "started_at": started,
            "conclusion": conclusion}


def checks_of(names, failing=None, status="completed", app="github-actions"):
    return [run_of(name, "failure" if name == failing else "success", status=status, app=app)
            for name in names]


def removals(patch, branch=None, author="github-actions[bot]", **overrides):
    """A scenario for the weekly deletion pull request carrying "patch" in its one file."""
    added, deleted = counts(patch) if patch else (0, 0)
    file = {"filename": "templates/LiteLLM_config.yaml.j2", "status": "modified", "additions": added,
            "deletions": deleted, "patch": patch}
    scenario = {
        "pr": {"number": 7, "title": "weekly deletions", "state": "open", "draft": False,
               "base": {"ref": "main"}, "body": "Models their provider has retired.\n\n## Deleted\n\n- m1",
               "head": {"sha": HEAD_SHA, "ref": branch or "claude/LiteLLM-model-drift-removals",
                        "repo": {"full_name": "o/r"}},
               "user": {"login": author}},
        "files": [file],
        "commits": [{"sha": "c1", "author": {"login": "github-actions[bot]"}, "commit": {"message": "x"}}],
        "checks": checks_of([name for name in contexts() if name != "sign-off"]),
        "behind_by": 0,
        "env": {},
    }
    scenario.update(overrides)
    return scenario


def dependabot(update_type="semver-minor", signed=True, names=None, **overrides):
    names = contexts() if names is None else names
    scenario = {
        "pr": {"number": 8, "title": "bump", "state": "open", "draft": False, "base": {"ref": "main"},
               "body": "", "head": {"sha": HEAD_SHA, "ref": "dependabot/pip/x",
                                     "repo": {"full_name": "o/r"}},
               "user": {"login": "dependabot[bot]"}},
        "files": [],
        "commits": [{"sha": "c1", "author": {"login": "dependabot[bot]"},
                     "commit": {"message": "update-type: version-update:%s" % update_type,
                                "verification": {"verified": signed}}}],
        "checks": checks_of(names),
        "behind_by": 0,
        "env": {},
    }
    scenario.update(overrides)
    return scenario


def scenarios():
    """[(name, expected result, scenario, must fail the run, notice it must give)]. "merged" or
    "not merged"; and for a refusal, a text its notice (or failure message) must contain, so that a
    scenario cannot go on passing because another guard refuses what the one it is about stopped
    refusing."""
    names, base = miniature()
    heading = review_heading()
    out = []
    seen = set()

    def add(name, expected, scenario, failed=False, needle=None):
        assert name not in seen, "two scenarios are called %r" % name
        seen.add(name)
        out.append((name, expected, scenario, failed, needle))

    # --- Dependabot -------------------------------------------------------------------------------
    add("Dependabot: a signed minor update, every check green", "merged", dependabot())
    add("Dependabot: a signed patch update", "merged", dependabot("semver-patch"))
    add("Dependabot: a major update", "not merged", dependabot("semver-major"),
        needle="Only minor and patch updates")
    add("Dependabot: an unsigned commit", "not merged", dependabot(signed=False),
        needle="not a signed Dependabot commit")
    by_a_person = dependabot()
    by_a_person["commits"].append({"sha": "c2", "author": {"login": "someone"}, "commit": {
        "message": "update-type: version-update:semver-minor", "verification": {"verified": True}}})
    add("Dependabot: a signed commit by a person on the branch", "not merged", by_a_person,
        needle="not a signed Dependabot commit")
    no_type = dependabot()
    no_type["commits"][0]["commit"]["message"] = "Bump x"
    add("Dependabot: no update-type in the commit", "not merged", no_type, needle="no update-type found")
    add("Dependabot: sign-off has not reported", "not merged",
        dependabot(names=[name for name in contexts() if name != "sign-off"]), needle="has not reported")
    add("Dependabot: a check is red", "not merged",
        dependabot(checks=checks_of(contexts(), failing="yamllint")), needle="concluded failure")

    # The pull request is found from the commit that was checked, and only a pull request that is open,
    # against the default branch, from this repository and at that commit counts.
    fork = dependabot()
    fork["pr"]["head"]["repo"] = {"full_name": "x/r"}
    add("Dependabot: the head is in a fork", "not merged", fork, needle="not exactly one")
    other_base = dependabot()
    other_base["pr"]["base"] = {"ref": "release"}
    add("Dependabot: against another branch", "not merged", other_base, needle="not exactly one")
    closed = dependabot()
    closed["pr"]["state"] = "closed"
    add("Dependabot: already closed", "not merged", closed, needle="not exactly one")
    moved = dependabot()
    moved["pr"]["head"]["sha"] = "f" * 40
    add("Dependabot: its head is no longer the commit that was checked", "not merged", moved,
        needle="not exactly one")
    twin = dependabot()
    twin["associated"] = [twin["pr"], dict(twin["pr"], number=9)]
    add("Dependabot: two open pull requests have that head", "not merged", twin, needle="not exactly one")
    add("the ruleset holds no rule of required checks", "not merged", dependabot(ruleset={"rules": []}),
        failed=True, needle="required_status_checks rules")
    real_rule = json.loads(RULESET.read_text(encoding="utf-8"))["rules"][0]
    add("the ruleset holds two rules of required checks", "not merged",
        dependabot(ruleset={"rules": [real_rule, real_rule]}), failed=True,
        needle="required_status_checks rules")
    add("the ruleset requires no check at all", "not merged", dependabot(ruleset={"rules": [{
        "type": "required_status_checks", "parameters": {"required_status_checks": []}}]}),
        failed=True, needle="requires no check at all")

    # --- the weekly deletions that must merge -----------------------------------------------------
    whole = set(block_of(base, "m1"))
    patch = deletion(base, whole)[0]

    def file_of(**changes):
        base_file = {"filename": "templates/LiteLLM_config.yaml.j2", "status": "modified", "additions": 0,
                     "deletions": counts(patch)[1], "patch": patch}
        base_file.update(changes)
        return base_file

    add("deletion: one whole entry, every check green but sign-off, which never starts", "merged",
        removals(patch))
    five = set()
    for name in names[:5]:
        five |= set(block_of(base, name))
    add("deletion: five whole entries", "merged", removals(deletion(base, five)[0]))
    six = set(five) | set(block_of(base, names[5]))
    add("deletion: six whole entries", "not merged", removals(deletion(base, six)[0]), needle="only 1 to")
    with_slot = set(block_of(base, "m6")) | set(slot_of(base, "m6"))
    add("deletion: an entry and the cascade slot that named it", "merged",
        removals(deletion(base, with_slot)[0]))
    add("deletion: a whole entry that git shows starting inside the entry above", "merged",
        removals(shifted_deletion(names, base)))
    start = base.index(COMMENTED[0])
    add("deletion: an entry that is commented out", "merged",
        removals(deletion(base, set(range(start, start + len(COMMENTED) + 1)))[0]))

    # --- the weekly deletions that must not --------------------------------------------------------
    # Most carry a whole entry, so that "one model at least" does not refuse them and only the look
    # at the deleted lines can.
    add("deletion: a cascade slot, and nothing else", "not merged",
        removals(deletion(base, set(slot_of(base, "m6")))[0]), needle="only 1 to")
    add("deletion: an entry, and the address of one that stays", "not merged",
        removals(deletion(base, whole | {base.index("      api_base: http://gateway.invalid:1234/v1")})[0]),
        needle="starts inside an entry")
    add("deletion: an entry, and a setting that carries a comment", "not merged",
        removals(deletion(base, whole | {base.index(SETTING)})[0]), needle="is not a model entry")
    add("deletion: an entry, and the heading of a section", "not merged",
        removals(deletion(base, whole | {base.index("router_settings:")})[0]), needle="is not a model entry")
    last = set(block_of(base, "m7"))
    add("deletion: the last entry and, in the same run, the heading of the section after it", "not merged",
        removals(deletion(base, last | {base.index("router_settings:")})[0]), needle="is not a model entry")
    add("deletion: an entry, and the model line of one that stays", "not merged",
        removals(deletion(base, whole | {base.index("      model: provider/m2")})[0]),
        needle="starts inside an entry")
    add("deletion: an entry, and the cascade slot of one that stays", "not merged",
        removals(deletion(base, whole | set(slot_of(base, "m6")))[0]),
        needle="is deleted but the entry it names is not")
    add("deletion: an entry, and a line of Jinja", "not merged",
        removals(deletion(base, whole | {base.index("{% if has.Gemini %}")})[0]), needle="is not a model entry")
    add("deletion: an entry, and another cut short with its key left behind", "not merged",
        removals(deletion(base, whole | set(block_of(base, "m2")[:3]))[0]), needle="is cut short")
    add("deletion: an entry cut short, and one whole", "not merged",
        removals(deletion(base, set(block_of(base, "m1")[:3]) | set(block_of(base, "m4")))[0]),
        needle="is cut short")
    # The same lines, placed so that git shows them differently, but the file left is not what a whole
    # deletion leaves: m5 and m6 end with different keys, and m6's would end up under m5's lines.
    swapped = {base.index("  - model_name: m5") + 3, base.index("  - model_name: m5") + 4,
               base.index("  - model_name: m6"), base.index("  - model_name: m6") + 1,
               base.index("  - model_name: m6") + 2}
    add("deletion: the key of one entry and the head of the next, which leaves the wrong key in place",
        "not merged", removals(deletion(base, swapped)[0]), needle="starts inside an entry")
    add("deletion: a comment and nothing else, which names no model", "not merged",
        removals(deletion(base, {1})[0]), needle="only 1 to")
    add("deletion: a section header and what follows it", "not merged",
        removals(deletion(base, {base.index("router_settings:"),
                                 base.index("  routing_strategy: simple-shuffle")})[0]),
        needle="only 1 to")

    with_added = patch + "\n+  - model_name: evil"
    add("deletion: a line is added, and GitHub counts it", "not merged",
        removals(with_added, files=[file_of(additions=1, patch=with_added)]),
        needle="is not a deletion of lines from")
    add("deletion: GitHub counts no addition, the patch holds one", "not merged",
        removals(with_added, files=[file_of(additions=0, patch=with_added)]), needle="a line is added")
    asking = removals(patch)
    asking["pr"]["body"] = "Models their provider has retired.\n\n%s\n\n- a comment names m1" % heading
    add("deletion: the body asks for a reading", "not merged", asking,
        needle="lists what a person has to read")
    quiet = removals(patch)
    quiet["pr"]["body"] = "Models retired.\n\nThe section is called %s in the script." % heading.replace("## ", "")
    add("deletion: the heading appears only inside a sentence", "merged", quiet)
    add("deletion: a head behind the default branch", "not merged", removals(patch, behind_by=2),
        needle="behind")

    # Every check the ruleset names but "sign-off" has to have reported, and reported success: the list
    # of checks the step excuses is widened by an edit of one line, so each one is tried.
    others = [name for name in contexts() if name != "sign-off"]
    for context in others:
        add("deletion: %s has not reported" % context, "not merged",
            removals(patch, checks=checks_of([name for name in others if name != context])),
            needle="has not reported")
        add("deletion: %s is red" % context, "not merged",
            removals(patch, checks=checks_of(others, failing=context)), needle="concluded failure")
    add("deletion: a check is still running", "not merged",
        removals(patch, checks=checks_of(others, status="in_progress")), needle="is still in_progress")
    add("deletion: the right check names, posted by another app", "not merged",
        removals(patch, checks=checks_of(others, app="some-other-app")), needle="has not reported")
    add("deletion: sign-off reported red", "not merged",
        removals(patch, checks=checks_of(contexts(), failing="sign-off")), needle="concluded failure")
    # A sign-off that did report, and green, is of course fine: the excuse is for the one that never runs.
    add("deletion: sign-off reported green as well", "merged", removals(patch, checks=checks_of(contexts())))
    # The latest run of a check is the one that counts, whatever order the API lists them in.
    rest = [run_of(name) for name in others if name != "gitleaks"]
    old_green, new_red = run_of("gitleaks", "success", "1"), run_of("gitleaks", "failure", "2")
    old_red, new_green = run_of("gitleaks", "failure", "1"), run_of("gitleaks", "success", "2")
    add("deletion: a check green once and red when re-run, the older run listed first", "not merged",
        removals(patch, checks=rest + [old_green, new_red]), needle="concluded failure")
    add("deletion: a check green once and red when re-run, the newer run listed first", "not merged",
        removals(patch, checks=rest + [new_red, old_green]), needle="concluded failure")
    add("deletion: a check red once and green when re-run, the older run listed first", "merged",
        removals(patch, checks=rest + [old_red, new_green]))
    add("deletion: a check red once and green when re-run, the newer run listed first", "merged",
        removals(patch, checks=rest + [new_green, old_red]))

    add("deletion: opened by a person", "not merged", removals(patch, author="someone"),
        needle="neither a Dependabot pull request nor")
    add("deletion: a bot's pull request on another branch", "not merged", removals(patch, branch="claude/other"),
        needle="neither a Dependabot pull request nor")
    draft = removals(patch)
    draft["pr"]["draft"] = True
    add("deletion: a draft", "not merged", draft, needle="neither a Dependabot pull request nor")
    add("deletion: two commits", "not merged", removals(patch, commits=[
        {"sha": "c1", "author": {"login": "github-actions[bot]"}, "commit": {"message": "x"}},
        {"sha": "c2", "author": {"login": "github-actions[bot]"}, "commit": {"message": "merge"}}]),
        needle="the one commit the workflow made")
    add("deletion: the commit's author is a person", "not merged", removals(patch, commits=[
        {"sha": "c1", "author": {"login": "someone"}, "commit": {"message": "x"}}]),
        needle="the one commit the workflow made")
    add("deletion: another file", "not merged", removals(patch, files=[file_of(filename="tasks/main.yml")]),
        needle="is not a deletion of lines from")
    add("deletion: two files", "not merged", removals(patch, files=[file_of(), file_of(filename="x")]),
        needle="is not a deletion of lines from")
    add("deletion: the file is renamed", "not merged", removals(patch, files=[file_of(status="renamed")]),
        needle="is not a deletion of lines from")
    add("deletion: GitHub gave no patch (too large)", "not merged", removals(patch, files=[file_of(patch=None)]),
        needle="is not a deletion of lines from")
    add("deletion: GitHub's count disagrees with the patch", "not merged",
        removals(patch, files=[file_of(deletions=counts(patch)[1] + 3)]), needle="only 1 to")
    add("deletion: no entry at all in the patch", "not merged",
        removals(patch, files=[file_of(patch="@@ -1,2 +1,1 @@\n-x\n y", deletions=1)]), needle="only 1 to")
    wide = ["@@ -1,201 +0,0 @@", "-  - model_name: a", "-    litellm_params:"] + ["-      model: a"] * 199
    add("deletion: more lines than the cap", "not merged",
        removals(patch, files=[file_of(patch="\n".join(wide), deletions=len(wide) - 1)]), needle="only 1 to")
    for text in ("abc", "", "0", "-3", "5.5"):
        add("deletion: the entry cap is %r" % text, "not merged",
            removals(patch, env={"REMOVALS_MAX_ENTRIES": text}), failed=True,
            needle="must be positive whole numbers")
        add("deletion: the line cap is %r" % text, "not merged",
            removals(patch, env={"REMOVALS_MAX_LINES": text}), failed=True,
            needle="must be positive whole numbers")
    add("deletion: the cap on entries is 1 and one entry goes", "merged",
        removals(patch, env={"REMOVALS_MAX_ENTRIES": "1"}))
    add("deletion: two entries go under a cap of 1", "not merged",
        removals(deletion(base, whole | set(block_of(base, "m2")))[0], env={"REMOVALS_MAX_ENTRIES": "1"}),
        needle="only 1 to")
    return out


# ---------------------------------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------------------------------

def load_step():
    """The script and the environment of the merge step, after checking the wiring around it that the
    scenarios cannot play: the commit it reads, and the output that starts the second job."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["merge"]
    steps = [step for step in job["steps"] if step.get("id") == "merge"]
    if len(steps) != 1:
        raise SystemExit("%s: expected exactly one step with id 'merge' in job 'merge', found %d."
                         % (WORKFLOW.relative_to(ROOT), len(steps)))
    step = steps[0]
    wiring = [
        (step.get("env", {}).get("HEAD_SHA"), "${{ github.event.workflow_run.head_sha }}",
         "the step's HEAD_SHA, which the harness would otherwise supply itself"),
        (job.get("outputs", {}).get("merged"), "${{ steps.merge.outputs.merged }}",
         "the job's output 'merged', which starts the job that checks main"),
        (workflow["jobs"]["recheck-main"].get("needs"), "merge", "the job that checks main afterwards needing 'merge'"),
        (workflow["jobs"]["recheck-main"].get("if"), "needs.merge.outputs.merged == 'true'",
         "the condition on which the job that checks main runs"),
    ]
    for got, want, what in wiring:
        if got != want:
            raise SystemExit("%s: %s is %r, expected %r." % (WORKFLOW.relative_to(ROOT), what, got, want))
    env = {key: str(value) for key, value in (step.get("env") or {}).items() if "${{" not in str(value)}
    return step["with"]["script"], env


def play(script, env, cases):
    if shutil.which("node") is None:
        raise SystemExit("node is not on the PATH: this check runs the step's script with it.")
    ruleset = json.loads(RULESET.read_text(encoding="utf-8"))
    payload = {"script": script, "env": env, "ruleset": ruleset, "head_sha": HEAD_SHA,
               "ruleset_path": RULESET.relative_to(ROOT).as_posix(),
               "scenarios": [case[2] for case in cases]}
    done = subprocess.run(["node", "-e", HARNESS], input=json.dumps(payload), capture_output=True,
                          text=True, timeout=300, check=False)
    if done.returncode != 0:
        raise SystemExit("node failed:\n%s" % (done.stderr or done.stdout)[-1500:])
    results = json.loads(done.stdout)
    if len(results) != len(cases):
        raise SystemExit("node answered %d scenario(s) out of %d." % (len(results), len(cases)))
    return results


def judge(cases, results):
    """[(name, what went wrong)] for the scenarios whose outcome is not the expected one."""
    wrong = []
    for (name, expected, _scenario, failed, needle), got in zip(cases, results):
        said = " | ".join(got["notices"] + ([got["failed"]] if got["failed"] else []))
        if got["crashed"]:
            first = got["crashed"].splitlines()[0]
            if got["crashed"].startswith("Error: unexpected "):
                wrong.append((name, "the step asked the made-up GitHub for something else than it should: %s" % first))
            else:
                wrong.append((name, "the script threw: %s" % first))
        elif got["result"] != expected:
            wrong.append((name, "%s instead of %s (%s)" % (got["result"], expected, said[:300] or "no notice")))
        elif failed and not got["failed"]:
            wrong.append((name, "it should have failed the run loudly and did not"))
        elif got["failed"] and not failed:
            wrong.append((name, "it failed the run, which it should not have: %s" % got["failed"][:200]))
        elif needle and needle not in said:
            wrong.append((name, "refused for another reason than the one it is about: %s" % (said[:300] or "no notice")))
    return wrong


# One entry per guard: (what it is, [(text in the step's script, what it is replaced with)], and
# optionally {step environment variable: another value}). Every text must occur once in the script and
# every variable must exist, which is how a guard that moved is noticed here. A guard that another one
# makes redundant is not listed, since breaking it alone proves nothing: the missing patch, for one,
# would throw further down; and inside removalsPatchProblem, the checks that no layout of the real
# model list can reach (a cascade slot next to an entry's header, a comment indented under an entry)
# are backstops for a layout it does not have today.
MUTATIONS = [
    ("the shape of the deleted lines is not asked", [
        ("const shape = removalsPatchProblem(file.patch);", "const shape = null;")]),
    ("a head behind the default branch passes", [("comparison.behind_by !== 0", "false")]),
    ("the head is compared the wrong way round with the default branch", [
        ("basehead: `${defaultBranch}...${headSha}`", "basehead: `${headSha}...${defaultBranch}`")]),
    ("a line added to the file passes", [
        ("file.additions !== 0 ||", ""),
        ("if (hunks.some((each) => each.added)) return 'a line is added';", "")]),
    ("GitHub's count of deleted lines is not compared", [("deleted.length !== file.deletions ||", "")]),
    ("a patch with no model entry passes", [("entries === 0 ||", "")]),
    ("a commented-out entry is not counted as an entry", [("(?:#\\s*)?", "")]),
    ("the cap on entries is not applied", [
        ("!(entries <= maxEntries)", "false"),
        ("!Number.isInteger(maxEntries) ||", ""), ]),
    ("the cap on lines is not applied", [
        ("!(deleted.length <= maxLines)", "false"),
        ("!Number.isInteger(maxLines) ||", "")]),
    ("a cap that is not a number is a cap that never trips", [
        ("!(entries <= maxEntries)", "entries > maxEntries"),
        ("!(deleted.length <= maxLines)", "deleted.length > maxLines"),
        ("!Number.isInteger(maxEntries) ||", ""), ("!Number.isInteger(maxLines) ||", "")]),
    ("a second file passes", [("files.length !== 1 ||", "")]),
    ("another file passes", [("file.filename !== process.env.REMOVALS_FILE ||", "")]),
    ("a renamed file passes", [("file.status !== 'modified' ||", "")]),
    ("a second commit passes", [("commits.length !== 1 ||", "")]),
    ("a person's commit passes", [("commits[0].author?.login !== 'github-actions[bot]'", "false")]),
    ("the body is not read", [(".test(pr.body ?? '')", ".test('')")]),
    ("sign-off is required of the deletions", [
        ("notApplicable.add(context);", "void context;")]),
    ("any app's check of the right name counts", [("&& run.app?.slug === 'github-actions'", "")]),
    ("a check still running passes", [("latest.status !== 'completed'", "false")]),
    ("a check that is not a success passes", [("latest.conclusion !== 'success'", "false")]),
    ("the oldest run of a check counts, not the latest", [
        ("(b.started_at ?? '').localeCompare(a.started_at ?? '')", "(a.started_at ?? '').localeCompare(b.started_at ?? '')")]),
    ("the runs of a check are not put in order", [
        (".sort((a, b) => (b.started_at ?? '').localeCompare(a.started_at ?? ''))", "")]),
    ("the merge is not pinned to the head", [("sha: headSha, merge_method", "merge_method")]),
    ("the merge is made another way", [("merge_method: 'merge'", "merge_method: 'squash'")]),
    ("the job that checks main afterwards is never told", [("core.setOutput('merged', 'true');", "")]),
    ("any bot's branch is taken for the deletions", [
        ("pr.head.ref === process.env.REMOVALS_BRANCH", "true")]),
    ("a draft passes", [("|| pr.draft", "")]),
    ("a person's pull request is taken for the deletions", [
        ("pr.user.login === 'github-actions[bot]' &&", "")]),
    ("a fork's pull request is taken for this repository's", [
        ("pr.head.repo?.full_name === `${owner}/${repo}`);", "true);")]),
    ("a pull request against another branch is taken", [("pr.base.ref === defaultBranch &&", "")]),
    ("a closed pull request is taken", [("pr.state === 'open' &&", "")]),
    ("a pull request that moved since the checks is taken", [("pr.head.sha === headSha &&", "")]),
    ("two pull requests at one commit are not told apart", [("candidates.length !== 1", "candidates.length === 0")]),
    ("a Dependabot commit with no update-type passes", [("updateTypes.length === 0", "false")]),
    ("a commit by a person on a Dependabot branch passes", [("author !== 'dependabot[bot]' ||", "")]),
    ("a ruleset with no check passes", [("required.length === 0", "false")]),
    ("a ruleset with two rules of required checks passes", [("rules.length !== 1", "rules.length === 0")]),
    # the environment of the step, which is as much a part of the guard as the script
    ("the list of checks the step excuses is widened", [], {"REMOVALS_NOT_APPLICABLE": "sign-off yamllint"}),
    ("the cap on entries is raised", [], {"REMOVALS_MAX_ENTRIES": "50"}),
    ("the heading that asks for a reading is another", [], {"REMOVALS_REVIEW_HEADING": "## Elsewhere"}),
    ("the branch of the deletions is another", [], {"REMOVALS_BRANCH": "claude/other"}),
    # inside removalsPatchProblem
    ("a line added in the patch is not seen by the shape check", [
        ("if (hunks.some((each) => each.added)) return 'a line is added';", "")]),
    ("a comment is anything with a '#' in it", [("const COMMENT = /^\\s*#/;", "const COMMENT = /#/;")]),
    ("the shape check lets a deletion start inside an entry", [
        ("if (significant[0] !== 'header') return { problem: 'a run of deleted lines starts inside an entry, not at its first line' };", "")]),
    ("the shape check lets an entry be cut short", [
        ("if (next !== undefined && /^ {3,}\\S/.test(next) && !COMMENT.test(next)) {", "if (false) {")]),
    ("the shape check does not ask that a deleted slot's entry goes too", [
        ("if (!entryNames.has(name)) return", "if (false) return")]),
    ("the shape check accepts a line that is none of its kinds", [
        ("if (odd >= 0) return", "if (false) return")]),
    ("the shape check reads the placement git chose and no other", [
        ("shift <= 2 * REACH", "shift <= 0")]),
    ("the shape check accepts any placement, not only those that leave the same file", [
        ("if (move !== 0 && without(start) !== result) continue;", "")]),
]


def run_selftest():
    script, env = load_step()
    cases = scenarios()
    failures = 0
    base_wrong = judge(cases, play(script, env, cases))
    if base_wrong:
        print("selftest: FAILED -- the unmodified script already fails %d scenario(s):" % len(base_wrong))
        for name, why in base_wrong:
            print("  - %s: %s" % (name, why))
        return 1
    print("selftest: ok -- the %d scenarios hold for the unmodified script" % len(cases))
    for purpose, edits, *rest in MUTATIONS:
        changed_env = dict(env)
        for variable, value in (rest[0] if rest else {}).items():
            if variable not in env:
                print("selftest: FAILED (%s) -- the step has no variable %s" % (purpose, variable))
                failures += 1
                break
            changed_env[variable] = value
        else:
            broken = script
            missing = [old for old, _new in edits if broken.count(old) != 1]
            if missing:
                print("selftest: FAILED (%s) -- the script no longer holds exactly one: %r"
                      % (purpose, missing[0]))
                failures += 1
                continue
            for old, new in edits:
                broken = broken.replace(old, new)
            results = play(broken, changed_env, cases)
            # An "unexpected" error is the made-up GitHub noticing a wrong call, which is a catch. Any
            # other throw means the break left a script that no longer runs, which fails every
            # scenario and would count as noticing a guard nobody tested.
            crashed = [got["crashed"] for got in results
                       if got["crashed"] and not got["crashed"].startswith("Error: unexpected ")]
            if crashed:
                print("selftest: FAILED (%s) -- the broken script throws, so it proves nothing: %s"
                      % (purpose, crashed[0].splitlines()[0]))
                failures += 1
                continue
            wrong = judge(cases, results)
            if wrong:
                print("selftest: ok -- %s (caught by: %s)" % (purpose, wrong[0][0]))
            else:
                print("selftest: FAILED (%s) -- no scenario noticed" % purpose)
                failures += 1
    return 1 if failures else 0


def main():
    if "--selftest" in sys.argv[1:]:
        return run_selftest()
    script, env = load_step()
    cases = scenarios()
    results = play(script, env, cases)
    wrong = dict(judge(cases, results))
    for name, _expected, _scenario, _failed, _needle in cases:
        print("%s %s" % ("FAIL" if name in wrong else "ok  ", name))
        if name in wrong:
            print("       %s" % wrong[name])
    if wrong:
        print("%d of %d scenario(s) went otherwise than the step should have gone." % (len(wrong), len(cases)))
        return 1
    print("%d scenarios: the step merges what it should and nothing else." % len(cases))
    return 0


if __name__ == "__main__":
    sys.exit(main())
