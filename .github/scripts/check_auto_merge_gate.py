#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77 and the AI Docker stack Ansible deployment contributors
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
* the model deletions: the ones that must merge (one entry, five, a commented-out entry, a
  diff that placed the deletion a few identical lines away from where an entry starts, the entry
  together with the cascade slots that named it) and every shape that must not (a setting, even one
  with a comment after it, or an address deleted, an entry cut short, a slot of an entry that stays,
  a line added, six entries, a body that asks for a reading, a head behind the default branch, caps
  that are not numbers, and so on);
* the two files generated beside the template, the catalogue and the figures file it shows, which a deletion and a
  sheet correction rewrite: each merges rewritten whatever lines it gains or loses, together or alone beside the template, in
  any order of the three; a file that is added, removed or renamed, one with no changed line (a binary or a
  mode alone), one past the cap, two entries of one, a catalogue or a figures file with no template, a fourth file,
  a line added to the template beside them, and the three files on a branch of additions do not; the same cases are
  played for the sheet corrections, whose template is read as ever, the counts and the lines of the patch being its
  alone: the files beside it count for nothing against the cap on values, and a change of the template that is no
  sheet value, a line added to it or a sheet line outside a "model_info" is refused with them as without them;
* the same deletions opened by the workflow's GitHub App, whose bot the step accepts as author beside
  the Actions bot only while the repository variable holding its slug is a slug: with the variable
  unset, empty, another App's or no slug, and with an author that is not exactly that App's bot, they
  wait for a human, and every other condition holds for the App's pull request as for the Actions
  bot's (a wrong branch, a second commit, a commit that is not the Actions bot's, a draft, a line
  added, a check red or missing, a sign-off that never started or started and is not green);
* the sheet corrections, which merge themselves, alone or with the two generated files beside the template: one value rewritten, an image flag turned over, a value
  before its comment, as many values as the cap allows, and, opened by the workflow's GitHub App as by the
  Actions bot, every shape that must not: a pull request opened by a person or on another branch, in a fork
  or as a draft, a second commit or one that is not the Actions bot's, another file or a second one, a line
  added, a line removed, a changed line that is no sheet line, a changed key, indentation, spacing or
  comment, a value that is no positive whole number or flag (or no such number for that key), a sheet line
  outside the "model_info" of an entry, one value over the cap or a cap that is no number, a head holding a
  change the patch does not show, a body with a section left to a person, a head behind the default branch,
  and every check missing or red. They are read in the two whole files, the merge base and the head, which
  the made-up GitHub serves, since a patch shows too few lines to tell which entry a line is in;
* the two pull requests of additions, on the branches the workflow names for them: as it opens them, lines
  added, or one line of a sheet rewritten as the sheet corrections are, and as the worst they could be, a
  deletion that would merge on the deletions' branch, by either bot, every check green, which only their
  branch keeps from merging; and, the other way, a deletion on the sheets' branch and a rewritten sheet on
  the deletions' one;
* every check the ruleset names, "sign-off" included, each tried missing and red, so that excusing
  one is noticed; a check posted by another app; and the latest of several runs of one check,
  whichever order the API lists them in.

The checks the ruleset names are read from the real ".github/rulesets/main.json", and the heading of
the body from the real script that writes it, so that renaming the heading in one place only fails
here. The made-up GitHub does not answer whatever it is asked: every call is compared with
what the scenario's own pull request implies (the repository, the ruleset's path and ref, the head
commit, the pull request number, the comparison, the merge method) and anything else throws, which is
how a step that reads main's checks instead of the head's, or merges another pull request, is noticed.
A refusal scenario also names the text its notice must contain, so that it cannot go on passing
because a second guard refuses what the one it is about stopped refusing. The wiring the scenarios
cannot play -- the step's HEAD_SHA, the job output that starts the job checking main after a merge,
that job's condition -- is checked in the workflow itself.

The block of the step that tells a sheet line from another is a copy of the one the job that writes the sheet
corrections holds, which "check_drift_publish_guard.py" plays on its own cases and refuses to see differ;
the scenarios here play the gate's use of it, and break its pieces in the selftest.

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
DRIFT_WORKFLOW = ROOT / ".github" / "workflows" / "LiteLLM_model_drift.yml"
HEAD_SHA = "0123456789abcdef0123456789abcdef01234567"
MERGE_BASE = "89abcdef0123456789abcdef0123456789abcdef"
DRIFT_FILE = "templates/LiteLLM_config.yaml.j2"

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
          if (args.path === input.ruleset_path) {
            expect('ruleset ref', args.ref, 'main');
            return { data: { content: Buffer.from(JSON.stringify(scenario.ruleset ?? input.ruleset)).toString('base64') } };
          }
          // The template, whole and raw, at the merge base and at the head: the texts of the sheet corrections.
          if (!scenario.texts) throw new Error('unexpected read of ' + args.path + ': this scenario has no whole files');
          expect('file path', args.path, input.drift_file);
          expect('media type', args.mediaType && args.mediaType.format, 'raw');
          if (args.ref === input.merge_base) return { data: scenario.texts.base };
          expect('file ref', args.ref, input.head_sha);
          return { data: scenario.texts.head };
        },
        listPullRequestsAssociatedWithCommit: async (args) => {
          about(args);
          expect('commit_sha', args.commit_sha, input.head_sha);
          return { data: scenario.associated ?? [pr] };
        },
        compareCommitsWithBasehead: async (args) => {
          about(args);
          expect('basehead', args.basehead, `main...${input.head_sha}`);
          return { data: { behind_by: scenario.behind_by, merge_base_commit: { sha: input.merge_base } } };
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

def entry(name, address=False, key="GEMINI", header=None):
    lines = ["  - model_name: %s" % name, "    model_info:", '      access_groups: ["LLM", "Public-Data-Only"]', "    litellm_params:",
             "      model: provider/%s" % name, '      litellm_credential_name: "%s"' % key.lower()]
    if address:
        lines.append("      api_base: http://gateway.invalid:1234/v1")
    if header is not None:
        # A keyless gateway's entry blanks the Authorization header, with a value only in the scenario that refuses one.
        lines += ["      extra_headers:", '        Authorization: "%s"' % header]
    return lines + [""]


# A setting with a comment after it, as the real file has several: a rule that read "#" anywhere in a
# line as a comment would let it go.
SETTING = "  turn_off_message_logging: true   # kept out of the logs"
# An entry that is commented out, which the tool deletes like any other and which counts as an entry.
COMMENTED = ["  # - model_name: gone", "  #   litellm_params:", "  #     model: provider/gone",
             '  #     litellm_credential_name: "gemini"', "  #"]


def miniature(count=8):
    names = ["m%d" % i for i in range(count)]
    lines = ["model_list:", "  # A comment above the first entry."]
    for index, name in enumerate(names):
        lines += entry(name, address=(index == 3), key="MISTRAL" if index >= 6 else "GEMINI",
                       header="" if index == 7 else None)
        if index == 2:
            lines += COMMENTED + [""]
    lines += ["router_settings:", "  routing_strategy: simple-shuffle", "  fallbacks:",
              "    - fast: &fast_cascade"]
    lines += ["        - %s" % name for name in names]
    lines += [SETTING, "{% if has.Gemini %}", "  extra: 1", "{% endif %}", ""]
    return names, lines


# The two generated files in miniature: a catalogue (a heading, a table and a row per entry) and a figures file.
# What is played here is the gate's reading of the shapes a file can take, whatever the generator writes.
CATALOG_LINES = ["# Catalogue", "", "| Groupe | Entrées |", "| --- | --- |", "| `LLM` | 8 |", "| `STT` | 1 |", "",
                 "| 1 | `m1` | Gemini |", "| 2 | `m2` | Gemini |", "| 3 | `m3` | Gemini |", ""]
CATALOG = "docs/CATALOG.md"
SCORES_LINES = ["{", ' "artificial_analysis_read": "2026-11-17",', ' "epoch_read": "2026-11-17",', ' "entries": {',
                '  "m1": {', '   "aa_index": 10.5', "  },", '  "m2": {', '   "aa_index": 20.5', "  }", " }", "}", ""]
SCORES = "docs/catalog_scores.json"


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


def generated_file(name, lines, remove=(), add=(), **changes):
    """A generated file as GitHub lists it in a pull request that takes the lines of "lines" at the indexes of "remove"
    out and puts "add" in their place at the end."""
    new = [line for index, line in enumerate(lines) if index not in remove] + list(add)
    patch = patch_between(lines, new)
    added, deleted = counts(patch)
    file = {"filename": name, "status": "modified", "additions": added, "deletions": deleted,
            "changes": added + deleted, "patch": patch}
    file.update(changes)
    return file


def catalog_file(remove=(), add=(), **changes):
    return generated_file(CATALOG, CATALOG_LINES, remove, add, **changes)


def scores_file(remove=(), add=(), **changes):
    return generated_file(SCORES, SCORES_LINES, remove, add, **changes)


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


def drift_env():
    workflow = yaml.safe_load(DRIFT_WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["publish"].get("env") or {}


def sheet_branch():
    """The branch the workflow makes the sheet corrections on, which the gate merges."""
    branch = drift_env().get("SHEETS_BRANCH")
    if not isinstance(branch, str) or not branch:
        raise SystemExit("%s names no branch of sheet corrections in its publish job." % DRIFT_WORKFLOW.relative_to(ROOT))
    return branch


def person_branches():
    """The branches of the pull requests only a person merges, the two of additions, as the drift workflow names
    them: they must be neither the branch of the deletions nor that of the sheet corrections, nor one the gate
    takes for Dependabot's or lets through its job filter."""
    env = drift_env()
    branches = [env.get("ADDITIONS_BRANCH"), env.get("ADDITIONS_TO_VERIFY_BRANCH")]
    gate = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["merge"]
    for branch in branches:
        if not isinstance(branch, str) or not branch:
            raise SystemExit("%s names no branch of additions in its publish job." % DRIFT_WORKFLOW.relative_to(ROOT))
        if (branch in (env.get("REMOVALS_BRANCH"), sheet_branch()) or branch.startswith("dependabot/")
                or branch in str(gate.get("if"))):
            raise SystemExit("%s: the branch %r of a pull request only a person merges is one the gate may take for "
                             "a pull request it merges." % (DRIFT_WORKFLOW.relative_to(ROOT), branch))
    if len(set(branches)) != len(branches):
        raise SystemExit("%s gives the two pull requests of additions one branch." % DRIFT_WORKFLOW.relative_to(ROOT))
    return branches


def run_of(name, conclusion="success", started="1", status="completed", app="github-actions"):
    return {"name": name, "status": status, "app": {"slug": app}, "started_at": started,
            "conclusion": conclusion}


def checks_of(names, failing=None, status="completed", app="github-actions"):
    return [run_of(name, "failure" if name == failing else "success", status=status, app=app)
            for name in names]


def removals(patch, branch=None, author="github-actions[bot]", **overrides):
    """A scenario for the deletion pull request carrying "patch" in its one file."""
    added, deleted = counts(patch) if patch else (0, 0)
    file = {"filename": "templates/LiteLLM_config.yaml.j2", "status": "modified", "additions": added,
            "deletions": deleted, "patch": patch}
    scenario = {
        "pr": {"number": 7, "title": "deletions", "state": "open", "draft": False,
               "base": {"ref": "main"}, "body": "Models their provider has retired.\n\n## Deleted\n\n- m1",
               "head": {"sha": HEAD_SHA, "ref": branch or "claude/LiteLLM-model-drift-removals",
                        "repo": {"full_name": "o/r"}},
               "user": {"login": author}},
        "files": [file],
        "commits": [{"sha": "c1", "author": {"login": "github-actions[bot]"}, "commit": {"message": "x"}}],
        "checks": checks_of(contexts()),
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


# The sheet of an entry as the real file writes it, with a comment after one value, which a rule that read the
# value as the rest of the line would take along.
SHEET_LINES = ["      max_input_tokens: 131072", "      max_output_tokens: 8192  # read on the page",
               "      supports_vision: false"]


def sheeted(lines):
    """The miniature file with the sheet of an entry in each "model_info", and a sheet line of the same shape
    in the "litellm_params" of the first entry, which is no sheet."""
    out = []
    for line in lines:
        out.append(line)
        if line == "    model_info:":
            out += SHEET_LINES
    at = out.index("      model: provider/m0")
    out.insert(at + 1, "      max_input_tokens: 5")
    return out


def sheets(base, new, branch=None, author="github-actions[bot]", **overrides):
    """A scenario for the sheet-correction pull request that turns the text "base" into "new": the patch GitHub
    gives for it, and the two whole files the step reads."""
    patch = patch_between(base, new)
    added, deleted = counts(patch) if patch else (0, 0)
    file = {"filename": DRIFT_FILE, "status": "modified", "additions": added, "deletions": deleted, "patch": patch}
    scenario = removals(patch, branch=branch or sheet_branch(), author=author, files=[file],
                        texts={"base": "\n".join(base), "head": "\n".join(new)})
    scenario["pr"]["title"] = "sheets"
    scenario["pr"]["body"] = "Corrections de fiches.\n\n## Corrections\n\n| Entrée | Champ |"
    scenario.update(overrides)
    return scenario


def rewrite(lines, old, new):
    """"lines" with the one line "old" replaced by "new" (a line or several)."""
    assert lines.count(old) >= 1, old
    at = lines.index(old)
    return lines[:at] + ([new] if isinstance(new, str) else list(new)) + lines[at + 1:]


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

    # --- the deletions that must merge -----------------------------------------------------
    whole = set(block_of(base, "m1"))
    patch = deletion(base, whole)[0]

    def file_of(**changes):
        base_file = {"filename": "templates/LiteLLM_config.yaml.j2", "status": "modified", "additions": 0,
                     "deletions": counts(patch)[1], "patch": patch}
        base_file.update(changes)
        return base_file

    add("deletion: one whole entry, every check green, sign-off included", "merged",
        removals(patch))
    five = set()
    for name in names[:5]:
        five |= set(block_of(base, name))
    add("deletion: five whole entries", "merged", removals(deletion(base, five)[0]))
    # A Cloudflare entry reads "cloudflare/@cf/<vendor>/<model>": an "@" and slashes in the model line, which
    # no other provider's has, and a key of its own.
    at = base.index("  - model_name: m1")
    cloudflare = list(base)
    cloudflare[at + 4] = "      model: cloudflare/@cf/vendor/m1"
    cloudflare[at + 5] = '      litellm_credential_name: "cloudflare"'
    add("deletion: a whole Cloudflare entry, whose model starts with \"@cf/\"", "merged",
        removals(deletion(cloudflare, set(block_of(cloudflare, "m1")))[0]))
    add("deletion: a Cloudflare entry and the model line of one that stays", "not merged",
        removals(deletion(cloudflare, set(block_of(cloudflare, "m1")) | {cloudflare.index("      model: provider/m2")})[0]),
        needle="starts inside an entry")
    six = set(five) | set(block_of(base, names[5]))
    add("deletion: six whole entries", "not merged", removals(deletion(base, six)[0]), needle="only 1 to")
    with_slot = set(block_of(base, "m6")) | set(slot_of(base, "m6"))
    add("deletion: an entry and the cascade slot that named it", "merged",
        removals(deletion(base, with_slot)[0]))
    add("deletion: a whole entry that git shows starting inside the entry above", "merged",
        removals(shifted_deletion(names, base)))
    add("deletion: a whole entry of a keyless gateway, the header that blanks Authorization included", "merged",
        removals(deletion(base, set(block_of(base, "m7")))[0]))
    start = base.index(COMMENTED[0])
    add("deletion: an entry that is commented out", "merged",
        removals(deletion(base, set(range(start, start + len(COMMENTED) + 1)))[0]))

    # --- the deletions that must not --------------------------------------------------------
    # Most carry a whole entry, so that "one model at least" does not refuse them and only the look
    # at the deleted lines can.
    add("deletion: a cascade slot, and nothing else", "not merged",
        removals(deletion(base, set(slot_of(base, "m6")))[0]), needle="only 1 to")
    add("deletion: an entry, and the address of one that stays", "not merged",
        removals(deletion(base, whole | {base.index("      api_base: http://gateway.invalid:1234/v1")})[0]),
        needle="starts inside an entry")
    add("deletion: an entry, and the header lines of one that stays", "not merged",
        removals(deletion(base, whole | {base.index("      extra_headers:"), base.index('        Authorization: ""')})[0]),
        needle="starts inside an entry")
    valued = [line.replace('Authorization: ""', 'Authorization: "Bearer x"') for line in base]
    add("deletion: an entry of a keyless gateway whose header carries a value", "not merged",
        removals(deletion(valued, set(block_of(valued, "m7")))[0]), needle="is not a model entry")
    other_group = [line.replace('access_groups: ["LLM", "Public-Data-Only"]', 'access_groups: ["STT", "Public-Data-Only"]')
                   for line in base]
    add("deletion: an entry in an access group other than LLM", "not merged",
        removals(deletion(other_group, set(block_of(other_group, "m1")))[0]), needle="is not a model entry")
    private = [line.replace('"Public-Data-Only"', '"Private-Data"') for line in base]
    add("deletion: an entry of a provider that is Private-Data", "merged",
        removals(deletion(private, set(block_of(private, "m1")))[0]))
    agent = [line.replace('["LLM", "Public-Data-Only"]', '["LLM", "Public-Data-Only", "Claude-Code"]') for line in base]
    add("deletion: an entry of the agent's cascade, in its three groups", "merged",
        removals(deletion(agent, set(block_of(agent, "m1")))[0]))
    for what, groups in (("with no data group", '["LLM"]'),
                         ("with its agent group before its data group", '["LLM", "Claude-Code", "Public-Data-Only"]'),
                         ("with its agent group and no data group", '["LLM", "Claude-Code"]'), ("with a data group of its own making", '["LLM", "Public"]'),
                         ("with its data group first", '["Public-Data-Only", "LLM"]'),
                         ("with both data groups", '["LLM", "Private-Data", "Public-Data-Only"]')):
        odd = [line.replace('["LLM", "Public-Data-Only"]', groups) for line in base]
        add("deletion: an entry %s" % what, "not merged",
            removals(deletion(odd, set(block_of(odd, "m1")))[0]), needle="is not a model entry")
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

    # Every check the ruleset names has to have reported, and reported success, "sign-off" included: it
    # never starts on a pull request opened with the workflow's own token, and the ruleset keeps such a
    # pull request from merging, so the step must not merge it either.
    others = [name for name in contexts() if name != "sign-off"]
    for context in contexts():
        add("deletion: %s has not reported" % context, "not merged",
            removals(patch, checks=checks_of([name for name in contexts() if name != context])),
            needle="has not reported")
        add("deletion: %s is red" % context, "not merged",
            removals(patch, checks=checks_of(contexts(), failing=context)), needle="concluded failure")
    add("deletion: every check green but sign-off, which never starts", "not merged",
        removals(patch, checks=checks_of(others)), needle='"sign-off" has not reported')
    add("deletion: a check is still running", "not merged",
        removals(patch, checks=checks_of(contexts(), status="in_progress")), needle="is still in_progress")
    add("deletion: the right check names, posted by another app", "not merged",
        removals(patch, checks=checks_of(contexts(), app="some-other-app")), needle="has not reported")
    # The latest run of a check is the one that counts, whatever order the API lists them in.
    rest = [run_of(name) for name in contexts() if name != "gitleaks"]
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
    # --- the deletions opened by the workflow's GitHub App -----------------------------------
    # The pull request's author is then "<slug>[bot]", and the step knows the slug from a variable
    # that is empty until the App is configured. The commit stays the Actions bot's.
    app = "drift-app-2"

    def by_app(slug=app, author=None, **overrides):
        env = dict(overrides.pop("env", {}))
        if slug is not None:
            env["MODEL_DRIFT_APP_SLUG"] = slug
        return removals(patch, author=app + "[bot]" if author is None else author, env=env, **overrides)

    add("App: its bot opens the deletions, its slug is set", "merged", by_app())
    add("App: the Actions bot still opens them with the slug set", "merged",
        by_app(author="github-actions[bot]"))
    add("App: the Actions bot still opens them with no slug", "merged",
        removals(patch, author="github-actions[bot]", env={"MODEL_DRIFT_APP_SLUG": ""}))
    gone = "neither a Dependabot pull request nor"
    add("App: its bot opens them and the slug variable is not set at all", "not merged",
        by_app(slug=None), needle=gone)
    add("App: its bot opens them and the slug variable is empty", "not merged", by_app(slug=""), needle=gone)
    add("App: its bot opens them and the slug is another App's", "not merged",
        by_app(slug="other-app"), needle=gone)
    add("App: another App's bot opens them", "not merged", by_app(author="other-app[bot]"), needle=gone)
    add("App: a person of the slug's name opens them", "not merged", by_app(author=app), needle=gone)
    add("App: a person whose name only starts with the slug opens them", "not merged",
        by_app(author=app + "x[bot]"), needle=gone)
    add("App: nobody is named by an empty slug", "not merged", by_app(slug="", author="[bot]"), needle=gone)
    add("App: nobody is named by a slug variable that is not set", "not merged",
        by_app(slug=None, author="undefined[bot]"), needle=gone)
    # A bot of exactly the name the variable gives is refused when the variable is no slug: "a b"
    # and "app\n" each hold a valid slug at one end only, which a pattern missing one of its
    # anchors would let through.
    for slug in ("my app", "My-App", "my_app", "my.app", "app\n", "a b", "../x", "app*", "ab\nevil"):
        add("App: the slug %r is no slug, and a bot of that name opens them" % slug, "not merged",
            by_app(slug=slug, author=slug + "[bot]"), needle=gone)
    add("App: its bot opens a pull request on another branch", "not merged",
        by_app(branch="claude/other"), needle=gone)
    app_draft = by_app()
    app_draft["pr"]["draft"] = True
    add("App: its bot opens a draft", "not merged", app_draft, needle=gone)
    add("App: two commits", "not merged", by_app(commits=[
        {"sha": "c1", "author": {"login": "github-actions[bot]"}, "commit": {"message": "x"}},
        {"sha": "c2", "author": {"login": "github-actions[bot]"}, "commit": {"message": "merge"}}]),
        needle="the one commit the workflow made")
    add("App: the one commit is the App's own, not the Actions bot's", "not merged", by_app(commits=[
        {"sha": "c1", "author": {"login": app + "[bot]"}, "commit": {"message": "x"}}]),
        needle="the one commit the workflow made")
    add("App: the one commit is a person's", "not merged", by_app(commits=[
        {"sha": "c1", "author": {"login": "someone"}, "commit": {"message": "x"}}]),
        needle="the one commit the workflow made")
    add("App: a line is added", "not merged",
        by_app(files=[file_of(additions=1, patch=with_added)]), needle="is not a deletion of lines from")
    asked = by_app()
    asked["pr"]["body"] = "Models their provider has retired.\n\n%s\n\n- a comment names m1" % heading
    add("App: the body asks for a reading", "not merged", asked, needle="lists what a person has to read")
    add("App: a head behind the default branch", "not merged", by_app(behind_by=1), needle="behind")
    add("App: a check is red", "not merged", by_app(checks=checks_of(contexts(), failing="yamllint")),
        needle="concluded failure")
    add("App: a check has not reported", "not merged",
        by_app(checks=checks_of([name for name in contexts() if name != "gitleaks"])), needle="has not reported")
    add("App: sign-off has not started", "not merged", by_app(checks=checks_of(others)),
        needle='"sign-off" has not reported')
    add("App: sign-off started and is red", "not merged",
        by_app(checks=checks_of(contexts(), failing="sign-off")), needle="concluded failure")
    add("App: sign-off started and is still running", "not merged",
        by_app(checks=checks_of(others) + [run_of("sign-off", status="in_progress", conclusion=None)]),
        needle="is still in_progress")
    two = deletion(base, whole | set(block_of(base, "m2")))[0]
    add("App: two entries under a cap of 1", "not merged",
        by_app(env={"REMOVALS_MAX_ENTRIES": "1"}, files=[file_of(patch=two, deletions=counts(two)[1])]),
        needle="only 1 to")
    add("App: Dependabot is judged as ever with the slug set", "merged",
        dependabot(env={"MODEL_DRIFT_APP_SLUG": app}))
    add("App: a Dependabot major is refused as ever with the slug set", "not merged",
        dependabot("semver-major", env={"MODEL_DRIFT_APP_SLUG": app}), needle="Only minor and patch updates")

    # --- the two files generated beside the deletions ----------------------------------------
    # GitHub lists the files of a pull request by path, so the catalogue and the figures file come before the template.
    lost = catalog_file(remove={7, 8})
    gains = catalog_file(remove={7}, add=["| 1 | `m1` | Gemini |"])
    figures = scores_file(remove={5, 8}, add=['   "aa_index": 11.5'])
    with_template = file_of()
    needle = "is not a deletion of lines from"
    rewrites = "does not rewrite"
    add("generated: the catalogue loses lines beside the template", "merged", removals(patch, files=[lost, with_template]))
    add("generated: the template listed first, as no listing does", "merged", removals(patch, files=[with_template, lost]))
    add("generated: the catalogue gains lines, as a figure that changed would make it", "merged",
        removals(patch, files=[gains, with_template]))
    add("generated: only lines added to the catalogue", "merged",
        removals(patch, files=[catalog_file(add=["| 4 | `m4` | Gemini |"]), with_template]))
    add("generated: the figures file is rewritten beside the template", "merged",
        removals(patch, files=[figures, with_template]))
    add("generated: the catalogue, the figures file and the template, as the workflow opens them", "merged",
        removals(patch, files=[lost, figures, with_template]))
    add("generated: the three, the other way round", "merged", removals(patch, files=[with_template, figures, lost]))
    add("generated: the three, opened by the App", "merged", by_app(files=[lost, figures, with_template]))
    add("generated: neither, as for a deletion that changes nothing they state", "merged", removals(patch))
    many = catalog_file(remove=set(range(1, len(CATALOG_LINES))))
    add("generated: lines taken out of the catalogue past the cap on the template's lines, which does not count them",
        "merged", removals(patch, files=[many, with_template], env={"REMOVALS_MAX_LINES": str(counts(patch)[1])}))
    add("generated: a file that changes exactly as many lines as the cap", "merged",
        removals(patch, files=[lost, figures, with_template],
                 env={"DRIFT_GENERATED_MAX_CHANGES": str(max(lost["changes"], figures["changes"]))}))
    add("generated: the catalogue changes one line more than the cap", "not merged",
        removals(patch, files=[lost, with_template], env={"DRIFT_GENERATED_MAX_CHANGES": str(lost["changes"] - 1)}),
        needle=rewrites)
    add("generated: the figures file changes one line more than the cap", "not merged",
        removals(patch, files=[lost, figures, with_template],
                 env={"DRIFT_GENERATED_MAX_CHANGES": str(figures["changes"] - 1)}), needle=rewrites)
    huge = dict(lost, additions=3000, deletions=1001, changes=4001, patch=None)
    add("generated: the catalogue changes 4001 lines, one more than the cap the step carries", "not merged",
        removals(patch, files=[huge, with_template]), needle=rewrites)
    add("generated: the catalogue changes 4000 lines, the cap the step carries", "merged",
        removals(patch, files=[dict(huge, additions=2999, changes=4000), with_template]))
    for status in ("added", "removed", "renamed"):
        add("generated: the catalogue is %s" % status, "not merged",
            removals(patch, files=[dict(lost, status=status), with_template]), needle=rewrites)
        add("generated: the figures file is %s" % status, "not merged",
            removals(patch, files=[lost, dict(figures, status=status), with_template]), needle=rewrites)
    add("generated: the catalogue is a binary or a mode change, no line of it changed", "not merged",
        removals(patch, files=[dict(lost, additions=0, deletions=0, changes=0, patch=None), with_template]),
        needle=rewrites)
    add("generated: the figures file is a mode change, no line of it changed", "not merged",
        removals(patch, files=[lost, dict(figures, additions=0, deletions=0, changes=0, patch=None), with_template]),
        needle=rewrites)
    add("generated: two entries for the catalogue", "not merged", removals(patch, files=[lost, lost, with_template]),
        needle=rewrites)
    add("generated: two entries for the figures file", "not merged",
        removals(patch, files=[figures, figures, with_template]), needle=rewrites)
    add("generated: the catalogue alone, with no template", "not merged", removals(patch, files=[lost]),
        needle=needle)
    add("generated: the figures file alone, with no template", "not merged", removals(patch, files=[figures]),
        needle=needle)
    add("generated: both, with no template", "not merged", removals(patch, files=[lost, figures]), needle=needle)
    add("generated: a third file beside the two", "not merged",
        removals(patch, files=[lost, figures, file_of(filename="docs/ROUTAGE.md"), with_template]), needle=needle)
    add("generated: a third file beside the catalogue", "not merged",
        removals(patch, files=[lost, file_of(filename="docs/ROUTAGE.md"), with_template]), needle=needle)
    add("generated: a line added to the template beside them", "not merged",
        removals(with_added, files=[lost, figures, file_of(additions=1, patch=with_added)]), needle=needle)
    add("generated: lines taken out of the three, and the entry of the template cut short", "not merged",
        removals(deletion(base, set(block_of(base, "m1")[:3]))[0], files=[lost, figures, file_of(
            patch=deletion(base, set(block_of(base, "m1")[:3]))[0], deletions=3)]), needle="is cut short")
    add("generated: the three, and a check red", "not merged",
        removals(patch, files=[lost, figures, with_template], checks=checks_of(contexts(), failing="yamllint")),
        needle="concluded failure")
    add("generated: the three, and the check of the repository's rules red", "not merged",
        removals(patch, files=[lost, figures, with_template],
                 checks=checks_of(contexts(), failing="Repository rules")), needle="concluded failure")
    for text in ("abc", "", "0", "-3", "5.5"):
        add("generated: the cap on the lines they change is %r" % text, "not merged",
            removals(patch, files=[lost, figures, with_template], env={"DRIFT_GENERATED_MAX_CHANGES": text}),
            failed=True, needle="must be a positive whole number")

    # --- the sheet corrections, which merge themselves ----------------------------------------------
    sheet_base = sheeted(base)
    first = "      max_input_tokens: 131072"
    value_lines = [at for at, line in enumerate(sheet_base) if line in SHEET_LINES]
    windows = [at for at, line in enumerate(sheet_base) if line == first]

    def rewritten_values(count):
        """The text with the window of the first "count" entries rewritten."""
        new = list(sheet_base)
        for at in windows[:count]:
            new[at] = "      max_input_tokens: %d" % (200000 + at)
        return new

    def changed(old, new_line):
        return rewrite(sheet_base, old, new_line)

    add("sheets: a window rewritten, every check green, sign-off included", "merged",
        sheets(sheet_base, rewritten_values(1)))
    add("sheets: an image flag turned over", "merged",
        sheets(sheet_base, changed("      supports_vision: false", "      supports_vision: true")))
    add("sheets: a longest answer rewritten before its comment", "merged",
        sheets(sheet_base, changed(SHEET_LINES[1], "      max_output_tokens: 16384  # read on the page")))
    add("sheets: as many values as the cap allows", "merged", sheets(sheet_base, rewritten_values(8)))
    add("sheets: the cap is 1 and one value goes", "merged",
        sheets(sheet_base, rewritten_values(1), env={"SHEETS_MAX_VALUES": "1"}))
    add("sheets: two values under a cap of 1", "not merged",
        sheets(sheet_base, rewritten_values(2), env={"SHEETS_MAX_VALUES": "1"}), needle="sheet values merge themselves")
    # Nine entries with a window, one more than the cap of the step as it is written.
    cap = int(re.search(r"^\s*SHEETS_MAX_VALUES: '(\d+)'", WORKFLOW.read_text(encoding="utf-8"), re.M).group(1))
    many_names, many_base = miniature(cap + 1)
    many_base = sheeted(many_base)
    many_new = list(many_base)
    many_windows = [at for at, line in enumerate(many_base) if line == first]
    for at in many_windows[:cap]:
        many_new[at] = "      max_input_tokens: 1"
    add("sheets: as many values as the step's own cap allows", "merged", sheets(many_base, many_new))
    many_new[many_windows[cap]] = "      max_input_tokens: 1"
    add("sheets: one value more than the step's own cap", "not merged", sheets(many_base, many_new),
        needle="sheet values merge themselves")
    # The patch GitHub gives holds three lines around a change: the entry a line belongs to is further up.
    deep = rewrite(sheet_base, "    model_info:", ["    model_info:"] + ["      mode_%d: chat" % n for n in range(8)])
    far = deep.index("      supports_vision: false")
    add("sheets: a value many lines below its model_info, out of the patch's reach", "merged",
        sheets(deep, deep[:far] + ["      supports_vision: true"] + deep[far + 1:]))
    out_of_reach = deep[:far] + ["      supports_vision: true"] + deep[far + 1:]
    assert "model_info:" not in patch_between(deep, out_of_reach), "the patch must not show the model_info"
    add("sheets: a value out of the patch's reach, in a file whose model_info is no entry's", "not merged",
        sheets([line if line != "  - model_name: m0" else "  - model_key: m0" for line in deep],
               [line if line != "  - model_name: m0" else "  - model_key: m0" for line in out_of_reach]),
        needle="is in a model_info that is no entry's")
    # --- the same, opened by the workflow's GitHub App
    sheet_app = "drift-app-2"

    def sheets_by_app(base_text, new_text, slug=sheet_app, author=None, **overrides):
        env = dict(overrides.pop("env", {}))
        if slug is not None:
            env["MODEL_DRIFT_APP_SLUG"] = slug
        return sheets(base_text, new_text, author=sheet_app + "[bot]" if author is None else author, env=env, **overrides)

    add("sheets, App: its bot opens the correction, its slug is set", "merged",
        sheets_by_app(sheet_base, rewritten_values(1)))
    add("sheets, App: its bot opens it and the slug variable is empty", "not merged",
        sheets_by_app(sheet_base, rewritten_values(1), slug=""), needle=gone)
    add("sheets, App: a person whose name only starts with the slug opens it", "not merged",
        sheets_by_app(sheet_base, rewritten_values(1), author=sheet_app + "x[bot]"), needle=gone)
    add("sheets, App: its bot opens it and the slug is no slug", "not merged",
        sheets_by_app(sheet_base, rewritten_values(1), slug="my app", author="my app[bot]"), needle=gone)
    add("sheets, App: another App's bot opens it", "not merged",
        sheets_by_app(sheet_base, rewritten_values(1), author="other-app[bot]"), needle=gone)
    add("sheets, App: a sheet line is changed otherwise", "not merged",
        sheets_by_app(sheet_base, changed(first, "      max_output_tokens: 131072")), needle="changes more than the value")
    add("sheets, App: sign-off started and is red", "not merged",
        sheets_by_app(sheet_base, rewritten_values(1), checks=checks_of(contexts(), failing="sign-off")),
        needle="concluded failure")

    # --- what must not merge
    add("sheets: opened by a person", "not merged", sheets(sheet_base, rewritten_values(1), author="someone"), needle=gone)
    add("sheets: a bot's pull request on another branch", "not merged",
        sheets(sheet_base, rewritten_values(1), branch="claude/other"), needle=gone)
    as_draft = sheets(sheet_base, rewritten_values(1))
    as_draft["pr"]["draft"] = True
    add("sheets: a draft", "not merged", as_draft, needle=gone)
    in_fork = sheets(sheet_base, rewritten_values(1))
    in_fork["pr"]["head"]["repo"] = {"full_name": "x/r"}
    add("sheets: the head is in a fork", "not merged", in_fork, needle="not exactly one")
    two_commits = [{"sha": "c1", "author": {"login": "github-actions[bot]"}, "commit": {"message": "x"}},
                   {"sha": "c2", "author": {"login": "github-actions[bot]"}, "commit": {"message": "merge"}}]
    add("sheets: two commits", "not merged", sheets(sheet_base, rewritten_values(1), commits=two_commits),
        needle="the one commit the workflow made")
    add("sheets: the commit's author is a person", "not merged", sheets(sheet_base, rewritten_values(1), commits=[
        {"sha": "c1", "author": {"login": "someone"}, "commit": {"message": "x"}}]),
        needle="the one commit the workflow made")
    add("sheets: the commit's author is the App, not the Actions bot", "not merged",
        sheets_by_app(sheet_base, rewritten_values(1), commits=[
            {"sha": "c1", "author": {"login": sheet_app + "[bot]"}, "commit": {"message": "x"}}]),
        needle="the one commit the workflow made")
    good = sheets(sheet_base, rewritten_values(1))

    def good_file(**changes):
        return dict(good["files"][0], **changes)

    shape = "is not a rewrite of sheet values in"
    add("sheets: another file", "not merged", sheets(sheet_base, rewritten_values(1), files=[good_file(filename="tasks/main.yml")]),
        needle=shape)
    add("sheets: two files", "not merged", sheets(sheet_base, rewritten_values(1), files=[good_file(), good_file(filename="x")]),
        needle=shape)
    add("sheets: the file is renamed", "not merged", sheets(sheet_base, rewritten_values(1), files=[good_file(status="renamed")]),
        needle=shape)
    add("sheets: GitHub gave no patch (too large)", "not merged", sheets(sheet_base, rewritten_values(1), files=[good_file(patch=None)]),
        needle=shape)
    add("sheets: GitHub's count of added lines disagrees with the patch", "not merged",
        sheets(sheet_base, rewritten_values(1), files=[good_file(additions=good["files"][0]["additions"] + 3)]),
        needle="sheet values merge themselves")
    add("sheets: GitHub's count of deleted lines disagrees with the patch", "not merged",
        sheets(sheet_base, rewritten_values(1), files=[good_file(deletions=good["files"][0]["deletions"] + 3)]),
        needle="sheet values merge themselves")
    add("sheets: a line added", "not merged",
        sheets(sheet_base, rewrite(sheet_base, first, [first, "      max_input_tokens: 7"])),
        needle="sheet values merge themselves")
    add("sheets: a line removed", "not merged", sheets(sheet_base, rewrite(sheet_base, first, [])),
        needle="sheet values merge themselves")
    add("sheets: a value rewritten and a line added", "not merged",
        sheets(sheet_base, rewrite(rewritten_values(1), "      max_input_tokens: %d" % (200000 + windows[0]),
                                   ["      max_input_tokens: %d" % (200000 + windows[0]), "      max_input_tokens: 7"])),
        needle="sheet values merge themselves")
    add("sheets: a line taken out and another put in elsewhere", "not merged",
        sheets(sheet_base, rewrite(sheet_base, first, []) + ["# elsewhere"]), needle="changes more than the value")
    add("sheets: a changed line that is no sheet line", "not merged",
        sheets(sheet_base, changed("      model: provider/m1", "      model: provider/m1-rewritten")),
        needle="is changed and is not a sheet line")
    add("sheets: a sheet line and the address of an entry", "not merged",
        sheets(sheet_base, changed("      api_base: http://gateway.invalid:1234/v1", "      api_base: http://elsewhere.invalid/v1")),
        needle="is changed and is not a sheet line")
    add("sheets: a key changed to another sheet key", "not merged",
        sheets(sheet_base, changed(first, "      max_output_tokens: 131072")), needle="changes more than the value")
    add("sheets: an indentation changed", "not merged",
        sheets(sheet_base, changed(first, "    max_input_tokens: 131072")), needle="changes more than the value")
    add("sheets: a spacing changed", "not merged",
        sheets(sheet_base, changed(first, "      max_input_tokens:  7")), needle="changes more than the value")
    add("sheets: a comment after the value changed", "not merged",
        sheets(sheet_base, changed(SHEET_LINES[1], "      max_output_tokens: 8192  # elsewhere")),
        needle="changes more than the value")
    add("sheets: a comment after the value dropped", "not merged",
        sheets(sheet_base, changed(SHEET_LINES[1], "      max_output_tokens: 8192")), needle="changes more than the value")
    add("sheets: a value that is no number", "not merged",
        sheets(sheet_base, changed(first, "      max_input_tokens: lots")), needle="is changed and is not a sheet line")
    add("sheets: a value written through Jinja", "not merged",
        sheets(sheet_base, changed(first, "      max_input_tokens: {{ window }}")), needle="is changed and is not a sheet line")
    add("sheets: a value of zero", "not merged",
        sheets(sheet_base, changed(first, "      max_input_tokens: 0")), needle="no positive whole number")
    add("sheets: a flag in a count", "not merged",
        sheets(sheet_base, changed(first, "      max_input_tokens: true")), needle="no positive whole number")
    add("sheets: a number in the image flag", "not merged",
        sheets(sheet_base, changed("      supports_vision: false", "      supports_vision: 1")),
        needle="no positive whole number")
    add("sheets: a value too long to be a count", "not merged",
        sheets(sheet_base, changed(first, "      max_input_tokens: 1%s" % ("0" * 12))), needle="no positive whole number")
    add("sheets: a window rewritten in litellm_params", "not merged",
        sheets(sheet_base, changed("      max_input_tokens: 5", "      max_input_tokens: 6")), needle="is not in a model_info")
    add("sheets: a window under a model_info that is no entry's", "not merged",
        sheets(sheet_base[:1] + ["router_settings:", "  model_info:", "    max_input_tokens: 5"] + sheet_base[1:],
               sheet_base[:1] + ["router_settings:", "  model_info:", "    max_input_tokens: 6"] + sheet_base[1:]),
        needle="is in a model_info that is no entry's")
    # The patch says one sheet value and the file holds more: only the texts show it.
    hidden = sheets(sheet_base, rewritten_values(1))
    hidden["texts"]["head"] = hidden["texts"]["head"].replace("      model: provider/m4", "      model: provider/evil")
    add("sheets: the head holds a change the patch does not show", "not merged", hidden,
        needle="is changed and is not a sheet line")
    for text in ("abc", "", "0", "-3", "5.5"):
        add("sheets: the cap on values is %r" % text, "not merged",
            sheets(sheet_base, rewritten_values(1), env={"SHEETS_MAX_VALUES": text}), failed=True,
            needle="must be a positive whole number")
    asking = sheets(sheet_base, rewritten_values(1))
    asking["pr"]["body"] = "Corrections.\n\n%s\n\nCette pull request ne se fusionne pas seule.\n\n### Écarts" % heading
    add("sheets: the body holds a section left to a person", "not merged", asking, needle="lists what a person has to read")
    quiet = sheets(sheet_base, rewritten_values(1))
    quiet["pr"]["body"] = "Corrections.\n\nThe section is called %s in the script." % heading.replace("## ", "")
    add("sheets: the heading appears only inside a sentence", "merged", quiet)
    add("sheets: a head behind the default branch", "not merged", sheets(sheet_base, rewritten_values(1), behind_by=1),
        needle="behind")
    for context in contexts():
        add("sheets: %s has not reported" % context, "not merged",
            sheets(sheet_base, rewritten_values(1), checks=checks_of([name for name in contexts() if name != context])),
            needle="has not reported")
        add("sheets: %s is red" % context, "not merged",
            sheets(sheet_base, rewritten_values(1), checks=checks_of(contexts(), failing=context)), needle="concluded failure")
    add("sheets: every check green but sign-off, which never starts", "not merged",
        sheets(sheet_base, rewritten_values(1), checks=checks_of(others)), needle='"sign-off" has not reported')
    add("sheets: a check is still running", "not merged",
        sheets(sheet_base, rewritten_values(1), checks=checks_of(contexts(), status="in_progress")),
        needle="is still in_progress")
    add("sheets: the right check names, posted by another app", "not merged",
        sheets(sheet_base, rewritten_values(1), checks=checks_of(contexts(), app="some-other-app")), needle="has not reported")
    add("sheets: a deletion of whole entries on the sheets' branch", "not merged",
        removals(patch, branch=sheet_branch(), texts={"base": "\n".join(base), "head": "\n".join(deletion(base, whole)[1])}),
        needle="sheet values merge themselves")
    add("sheets: a sheet rewritten on the deletions' branch", "not merged",
        sheets(sheet_base, rewritten_values(1), branch=removals(patch)["pr"]["head"]["ref"]), needle="is not a deletion of lines from")

    # --- the sheet corrections with the two files generated beside them -----------------------------
    # The workflow carries the regenerated catalogue and figures file in the pull request of the sheet corrections
    # as in the others; the gate lets them through as it does for the deletions, whatever lines they change, and
    # reads the template alone as a sheet correction: its counts, its lines, its whole files.
    def with_generated(scenario, *extra):
        """The scenario with the files "extra" listed before the template, as GitHub lists them by path."""
        scenario["files"] = list(extra) + scenario["files"]
        return scenario

    one_value = rewritten_values(1)
    add("sheets, generated: the catalogue and the figures file beside the template, as the workflow opens them", "merged",
        with_generated(sheets(sheet_base, one_value), lost, figures))
    add("sheets, generated: the template listed first, as no listing does", "merged",
        sheets(sheet_base, one_value, files=[sheets(sheet_base, one_value)["files"][0], figures, lost]))
    add("sheets, generated: the catalogue alone beside the template", "merged",
        with_generated(sheets(sheet_base, one_value), lost))
    add("sheets, generated: the figures file alone beside the template, which gains lines", "merged",
        with_generated(sheets(sheet_base, one_value), figures))
    add("sheets, generated: the catalogue gains lines, as a figure that changed would make it", "merged",
        with_generated(sheets(sheet_base, one_value), gains, figures))
    add("sheets, generated: the three, opened by the App", "merged",
        with_generated(sheets_by_app(sheet_base, one_value), lost, figures))
    add("sheets, generated: neither, as for a correction that changes no figure", "merged", sheets(sheet_base, one_value))
    add("sheets, generated: lines of the catalogue beyond the cap on sheet values, which does not count them", "merged",
        with_generated(sheets(sheet_base, one_value, env={"SHEETS_MAX_VALUES": "1"}), lost, figures))
    add("sheets, generated: two values beside the files under a cap of 1", "not merged",
        with_generated(sheets(sheet_base, rewritten_values(2), env={"SHEETS_MAX_VALUES": "1"}), lost, figures),
        needle="sheet values merge themselves")
    add("sheets, generated: a file that changes exactly as many lines as the cap", "merged",
        with_generated(sheets(sheet_base, one_value, env={
            "DRIFT_GENERATED_MAX_CHANGES": str(max(lost["changes"], figures["changes"]))}), lost, figures))
    add("sheets, generated: the catalogue changes one line more than the cap", "not merged",
        with_generated(sheets(sheet_base, one_value, env={"DRIFT_GENERATED_MAX_CHANGES": str(lost["changes"] - 1)}), lost),
        needle=rewrites)
    add("sheets, generated: the figures file changes one line more than the cap", "not merged",
        with_generated(sheets(sheet_base, one_value, env={"DRIFT_GENERATED_MAX_CHANGES": str(figures["changes"] - 1)}),
                       lost, figures), needle=rewrites)
    for status in ("added", "removed", "renamed"):
        add("sheets, generated: the catalogue is %s" % status, "not merged",
            with_generated(sheets(sheet_base, one_value), dict(lost, status=status)), needle=rewrites)
        add("sheets, generated: the figures file is %s" % status, "not merged",
            with_generated(sheets(sheet_base, one_value), lost, dict(figures, status=status)), needle=rewrites)
    add("sheets, generated: the catalogue is a binary or a mode change, no line of it changed", "not merged",
        with_generated(sheets(sheet_base, one_value), dict(lost, additions=0, deletions=0, changes=0, patch=None)),
        needle=rewrites)
    add("sheets, generated: two entries for the catalogue", "not merged",
        with_generated(sheets(sheet_base, one_value), lost, lost), needle=rewrites)
    add("sheets, generated: two entries for the figures file", "not merged",
        with_generated(sheets(sheet_base, one_value), figures, figures), needle=rewrites)
    for text in ("abc", "", "0", "-3", "5.5"):
        add("sheets, generated: the cap on the lines they change is %r" % text, "not merged",
            with_generated(sheets(sheet_base, one_value, env={"DRIFT_GENERATED_MAX_CHANGES": text}), lost, figures),
            failed=True, needle="must be a positive whole number")
    add("sheets, generated: the catalogue alone, with no template", "not merged",
        sheets(sheet_base, one_value, files=[lost]), needle=shape)
    add("sheets, generated: the figures file alone, with no template", "not merged",
        sheets(sheet_base, one_value, files=[figures]), needle=shape)
    add("sheets, generated: both, with no template", "not merged",
        sheets(sheet_base, one_value, files=[lost, figures]), needle=shape)
    other_file = dict(lost, filename="docs/ROUTAGE.md")
    add("sheets, generated: another file beside the two", "not merged",
        with_generated(sheets(sheet_base, one_value), lost, figures, other_file), needle=shape)
    add("sheets, generated: another file beside the catalogue", "not merged",
        with_generated(sheets(sheet_base, one_value), lost, other_file), needle=shape)
    add("sheets, generated: another file instead of the figures file, which the step names", "not merged",
        with_generated(sheets(sheet_base, one_value), lost, dict(figures, filename="docs/other_scores.json")), needle=shape)
    non_sheet = changed("      model: provider/m1", "      model: provider/m1-rewritten")
    add("sheets, generated: a line of the template that is no sheet line changes, and the catalogue with it", "not merged",
        with_generated(sheets(sheet_base, non_sheet), lost, figures), needle="is changed and is not a sheet line")
    add("sheets, generated: a sheet line and the address of an entry, beside the three", "not merged",
        with_generated(sheets(sheet_base, changed("      api_base: http://gateway.invalid:1234/v1",
                                                 "      api_base: http://elsewhere.invalid/v1")), lost, figures),
        needle="is changed and is not a sheet line")
    hidden_with = with_generated(sheets(sheet_base, one_value), lost, figures)
    hidden_with["texts"]["head"] = hidden_with["texts"]["head"].replace("      model: provider/m4", "      model: provider/evil")
    add("sheets, generated: the head holds a change the patch does not show, beside the three", "not merged",
        hidden_with, needle="is changed and is not a sheet line")
    add("sheets, generated: a line added to the template beside them", "not merged",
        with_generated(sheets(sheet_base, rewrite(sheet_base, first, [first, "      max_input_tokens: 7"])), lost, figures),
        needle="sheet values merge themselves")
    add("sheets, generated: a sheet line outside a model_info beside them", "not merged",
        with_generated(sheets(sheet_base, changed("      max_input_tokens: 5", "      max_input_tokens: 6")), lost, figures),
        needle="is not in a model_info")
    add("sheets, generated: the three, and a check red", "not merged",
        with_generated(sheets(sheet_base, one_value, checks=checks_of(contexts(), failing="yamllint")), lost, figures),
        needle="concluded failure")
    add("sheets, generated: the three, and the check of the repository's rules red", "not merged",
        with_generated(sheets(sheet_base, one_value, checks=checks_of(contexts(), failing="Repository rules")), lost, figures),
        needle="concluded failure")
    asking_with = with_generated(sheets(sheet_base, one_value), lost, figures)
    asking_with["pr"]["body"] = "Corrections.\n\n%s\n\nCette pull request ne se fusionne pas seule." % heading
    add("sheets, generated: the body holds a section left to a person, beside the three", "not merged", asking_with,
        needle="lists what a person has to read")
    add("sheets, generated: a head behind the default branch, beside the three", "not merged",
        with_generated(sheets(sheet_base, one_value, behind_by=1), lost, figures), needle="behind")
    add("sheets, generated: the three on a branch that is no sheets', a person's pull request", "not merged",
        with_generated(sheets(sheet_base, one_value, author="someone"), lost, figures), needle=gone)

    # --- the additions, which nothing but a person merges ------------------------------------------
    # Each is tried as the workflow opens it, lines added, or a line of a sheet rewritten, and as the worst it
    # could be: a deletion that would merge on the deletions' branch, by the Actions bot or the App, every check
    # green, and a clean correction of sheets that would merge on the sheets' branch. Only the branch tells them
    # apart, and it must.
    rewritten = list(base)
    at = rewritten.index("      model: provider/m1")
    rewritten[at] = "      model: provider/m1-rewritten"
    rewriting = patch_between(base, rewritten)
    added = list(base)
    added[base.index("router_settings:"):base.index("router_settings:")] = entry("fresh")
    adding = patch_between(base, added)
    for branch in person_branches():
        tag = "additions on %s: " % branch
        add(tag + "a line rewritten", "not merged",
            removals(rewriting, branch=branch, files=[file_of(additions=1, deletions=1, patch=rewriting)]),
            needle=gone)
        add(tag + "a line rewritten, opened by the App", "not merged",
            by_app(branch=branch, files=[file_of(additions=1, deletions=1, patch=rewriting)]), needle=gone)
        add(tag + "a sheet value rewritten, which would merge on the sheets' branch", "not merged",
            sheets(sheet_base, rewritten_values(1), branch=branch), needle=gone)
        add(tag + "a sheet value rewritten, opened by the App", "not merged",
            sheets_by_app(sheet_base, rewritten_values(1), branch=branch), needle=gone)
        add(tag + "entries added, as the workflow opens it", "not merged",
            removals(adding, branch=branch, files=[file_of(additions=counts(adding)[0], deletions=0, patch=adding)]),
            needle=gone)
        add(tag + "entries added, opened by the App", "not merged",
            by_app(branch=branch, files=[file_of(additions=counts(adding)[0], deletions=0, patch=adding)]),
            needle=gone)
        add(tag + "a deletion that would merge on the deletions' branch", "not merged",
            removals(patch, branch=branch), needle=gone)
        add(tag + "a deletion that would merge, opened by the App", "not merged", by_app(branch=branch), needle=gone)
        as_draft = removals(patch, branch=branch)
        as_draft["pr"]["draft"] = True
        add(tag + "a draft", "not merged", as_draft, needle=gone)
        add(tag + "the template, its catalogue and its figures, as the workflow opens them", "not merged",
            removals(adding, branch=branch, files=[
                catalog_file(add=["| 4 | `m4` | Gemini |"]), scores_file(add=['  "m4": {', '   "aa_index": 1', "  }"]),
                file_of(additions=counts(adding)[0], deletions=0, patch=adding)]), needle=gone)
        add(tag + "a deletion with the three files that would merge on the deletions' branch", "not merged",
            removals(patch, branch=branch, files=[lost, figures, with_template]), needle=gone)

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
        (step.get("env", {}).get("MODEL_DRIFT_APP_SLUG"), "${{ vars.MODEL_DRIFT_APP_SLUG }}",
         "the step's MODEL_DRIFT_APP_SLUG, which the scenarios would otherwise supply themselves"),
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
    payload = {"script": script, "env": env, "ruleset": ruleset, "head_sha": HEAD_SHA, "merge_base": MERGE_BASE,
               "drift_file": DRIFT_FILE,
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
        ("(removals && file.additions !== 0) ||", ""),
        ("if (hunks.some((each) => each.added)) return 'a line is added';", "")]),
    ("GitHub's count of deleted lines is not compared", [("deleted.length !== file.deletions ||", "")]),
    ("a patch with no model entry passes", [("entries === 0 ||", "")]),
    ("the header lines of a keyless gateway's entry are not part of an entry", [
        (' {6}extra_headers:| {8}Authorization:\\s*"")', ')')]),
    ("any value of the Authorization header is part of an entry", [
        ('{8}Authorization:\\s*"")', '{8}Authorization:.*)')]),
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
    ("a second file passes", [("others.length !== 1 ||", "")]),
    ("another file passes", [("file.filename !== process.env.DRIFT_FILE ||", "")]),
    ("a second entry for a generated file passes", [("same.length > 1 ||", "")]),
    ("a generated file that is added, removed or renamed passes", [("each.status !== 'modified' ||", "")]),
    ("a generated file with no changed line passes", [("!(each.changes >= 1) ||", "")]),
    ("a generated file past the cap passes", [("|| !(each.changes <= maxGenerated)", "")]),
    ("a cap on the generated files that is not a number never trips", [
        ("!(each.changes <= maxGenerated)", "each.changes > maxGenerated"),
        ("!Number.isInteger(maxGenerated) ||", ""), ("|| maxGenerated < 1", "")]),
    ("the figures file is not told from another file", [
        ("const generatedNames = [process.env.DRIFT_CATALOG_FILE, process.env.DRIFT_SCORES_FILE];",
         "const generatedNames = [process.env.DRIFT_CATALOG_FILE];")]),
    ("a renamed file passes", [("file.status !== 'modified' ||", "")]),
    ("a second commit passes", [("commits.length !== 1 ||", "")]),
    ("a person's commit passes", [("commits[0].author?.login !== 'github-actions[bot]'", "false")]),
    ("the body is not read", [(".test(pr.body ?? '')", ".test('')")]),
    ("a check that never started is excused", [
        ("if (runs.length === 0) {", "if (runs.length === 0 && context === 'sign-off') continue;\n              if (runs.length === 0) {")]),
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
    ("a branch that only starts like the deletions' is taken for them", [
        ("pr.head.ref === process.env.REMOVALS_BRANCH", "pr.head.ref.startsWith('claude/LiteLLM-model-')")]),
    ("any bot's branch is taken for the sheet corrections", [
        ("pr.head.ref === process.env.SHEETS_BRANCH", "true")]),
    ("a branch that only starts like the sheet corrections' is taken for them", [
        ("pr.head.ref === process.env.SHEETS_BRANCH", "pr.head.ref.startsWith('claude/LiteLLM-model-')")]),
    ("a draft passes", [("|| pr.draft", "")]),
    ("a person's pull request is taken for the deletions", [
        ("const removals = driftAuthors.includes(pr.user.login) &&", "const removals =")]),
    ("a person's pull request is taken for the sheet corrections", [
        ("const sheets = driftAuthors.includes(pr.user.login) &&", "const sheets =")]),
    ("any bot's pull request is taken for the deletions", [
        ("const removals = driftAuthors.includes(pr.user.login)", "const removals = pr.user.login.endsWith('[bot]')")]),
    ("any bot's pull request is taken for the sheet corrections", [
        ("const sheets = driftAuthors.includes(pr.user.login)", "const sheets = pr.user.login.endsWith('[bot]')")]),
    ("the Actions bot's pull request is taken for the deletions and the sheets only with the App's slug set", [
        ("const driftAuthors = ['github-actions[bot]'];", "const driftAuthors = [];")]),
    ("a person whose name starts with the App's slug is taken for its bot, for the deletions", [
        ("const removals = driftAuthors.includes(pr.user.login)",
         "const removals = driftAuthors.some((name) => pr.user.login.startsWith(name.replace('[bot]', '')))")]),
    ("a person whose name starts with the App's slug is taken for its bot, for the sheet corrections", [
        ("const sheets = driftAuthors.includes(pr.user.login)",
         "const sheets = driftAuthors.some((name) => pr.user.login.startsWith(name.replace('[bot]', '')))")]),
    ("the App's bot is taken for the drift pull requests whatever the slug variable says", [
        ("if (/^[a-z0-9-]+$/.test(appSlug)) driftAuthors.push(`${appSlug}[bot]`);",
         "driftAuthors.push(`${appSlug}[bot]`);")]),
    ("a person of the slug's name is taken for the App's bot", [
        ("driftAuthors.push(`${appSlug}[bot]`)", "driftAuthors.push(appSlug)")]),
    ("a slug variable that is not set names a bot of the name 'undefined'", [
        ("process.env.MODEL_DRIFT_APP_SLUG ?? ''", "process.env.MODEL_DRIFT_APP_SLUG")]),
    ("the slug pattern is not anchored at its start", [("/^[a-z0-9-]+$/", "/[a-z0-9-]+$/")]),
    ("the slug pattern is not anchored at its end", [("/^[a-z0-9-]+$/", "/^[a-z0-9-]+/")]),
    ("the slug pattern accepts an empty slug", [("/^[a-z0-9-]+$/", "/^[a-z0-9-]*$/")]),
    ("the slug pattern accepts capitals", [("/^[a-z0-9-]+$/", "/^[a-zA-Z0-9-]+$/")]),
    ("the slug pattern accepts any word character", [("/^[a-z0-9-]+$/", "/^[\\w-]+$/")]),
    ("the slug pattern accepts a dot", [("/^[a-z0-9-]+$/", "/^[a-z0-9.-]+$/")]),
    ("the slug pattern accepts a space", [("/^[a-z0-9-]+$/", "/^[a-z0-9 -]+$/")]),
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
    # the sheet corrections
    ("the sheet corrections are not read in the two whole files", [
        ("const problem = sheetProblem(await read(comparison.merge_base_commit.sha), await read(headSha));",
         "const problem = null;")]),
    ("the head of the sheet corrections is read as main is", [
        ("await read(headSha))", "await read(comparison.merge_base_commit.sha))")]),
    ("GitHub's count of lines put in is not compared with the patch", [("put !== file.additions ||", "")]),
    ("the lines put in are counted over every file of the pull request, not the template's", [
        ("put !== file.additions ||", "put !== files.reduce((sum, each) => sum + each.additions, 0) ||")]),
    ("the lines taken out are counted over every file of the pull request, not the template's", [
        ("taken !== file.deletions ||", "taken !== files.reduce((sum, each) => sum + each.deletions, 0) ||")]),
    ("GitHub's count of lines taken out is not compared with the patch", [("taken !== file.deletions ||", "")]),
    ("the cap on values is not applied", [
        ("!(taken <= maxValues)", "false"), ("!Number.isInteger(maxValues) ||", "")]),
    ("a cap on values that is not a number is a cap that never trips", [
        ("!(taken <= maxValues)", "taken > maxValues"), ("!Number.isInteger(maxValues) ||", "")]),
    ("the sheet guard lets a changed key pass", [("|| was[2] !== now[2] ||", "||")]),
    ("the sheet guard lets a changed indentation pass", [("was[1] !== now[1] ||", "")]),
    ("the sheet guard lets a changed spacing pass", [("|| was[3] !== now[3] ||", "||")]),
    ("the sheet guard lets a changed comment pass", [("|| was[5] !== now[5]) return", ") return")]),
    ("the sheet guard lets a changed line that is no sheet line pass", [
        ("if (!was || !now) return", "if (!was || !now) continue; if (false) return")]),
    ("the sheet guard lets a value that is no positive whole number pass", [
        ("if (!sheetValueFits(was[2], was[4]) || !sheetValueFits(now[2], now[4])) return", "if (false) return")]),
    ("the sheet guard lets a line outside a model_info pass", [
        ("if (!info || !/^\\s*model_info:\\s*(?:#.*)?$/.test(info.line)) return", "if (!info) return")]),
    ("the sheet guard lets a model_info that is no entry's pass", [
        ("if (!entry || !/^\\s*-\\s+model_name:\\s*\\S+\\s*$/.test(entry.line)) return", "if (!entry) return")]),
    # the environment of the step, which is as much a part of the guard as the script
    ("the cap on entries is raised", [], {"REMOVALS_MAX_ENTRIES": "50"}),
    ("the cap on sheet values is raised", [], {"SHEETS_MAX_VALUES": "50"}),
    ("the catalogue is another file", [], {"DRIFT_CATALOG_FILE": "docs/elsewhere.md"}),
    ("the figures file is another file", [], {"DRIFT_SCORES_FILE": "docs/elsewhere.json"}),
    ("the cap on the generated files is raised", [], {"DRIFT_GENERATED_MAX_CHANGES": "1000000"}),
    ("the heading that asks for a reading is another", [], {"REMOVALS_REVIEW_HEADING": "## Elsewhere"}),
    ("the heading that asks for a reading of the sheet corrections is another", [], {"SHEETS_REVIEW_HEADING": "## Elsewhere"}),
    ("the branch of the deletions is another", [], {"REMOVALS_BRANCH": "claude/other"}),
    ("the branch of the sheet corrections is another", [], {"SHEETS_BRANCH": "claude/other"}),
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
