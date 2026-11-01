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
  green, a major, an unsigned commit, a ruleset check that never reported);
* the weekly model deletions: the ones that must merge (one entry, five, a diff that placed the
  deletion a few identical lines away from where an entry starts, the entry together with the
  cascade slots that named it) and every shape that must not (a setting or an address deleted, an
  entry cut short, a slot of an entry that stays, a line added, six entries, a body that asks for a
  reading, a head behind the default branch, a check of the right name posted by another app, caps
  that are not numbers, and so on). The checks the ruleset names are read from the real
  ".github/rulesets/main.json", and the heading of the body from the real script that writes it, so
  that renaming "sign-off" or the heading in one place only fails here.

"--selftest" proves the scenarios can fail: it breaks the step's script one guard at a time and
requires some scenario to notice each. A guard no scenario notices is a guard this check cannot
vouch for; and a guard whose text has moved fails the selftest too, so the list below follows the
script instead of rotting beside it.

WHAT IT DOES NOT PROVE
----------------------
That GitHub answers as the scenarios say. It does not call GitHub, and the answers are the ones
read off real runs of the workflow. Node is needed (the workflow's own runner has one for the
action; this check wants "node" on the PATH, which the CI job installs).
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
# objects github-script hands a script; only what the step calls is made up, so a call to anything
# else fails the scenario loudly instead of being answered.
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
  const github = {
    paginate: async (fn, args) => fn(args),
    rest: {
      repos: {
        getContent: async () => ({ data: { content: Buffer.from(JSON.stringify(input.ruleset)).toString('base64') } }),
        listPullRequestsAssociatedWithCommit: async () => ({ data: [pr] }),
        compareCommitsWithBasehead: async () => ({ data: { behind_by: scenario.behind_by } }),
      },
      pulls: {
        listCommits: async () => scenario.commits,
        listFiles: async () => scenario.files,
        merge: async (args) => { merges.push(args); return {}; },
      },
      checks: { listForRef: async () => scenario.checks },
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
  if (merges.length === 1) result = merges[0].sha === input.head_sha ? 'merged' : 'merged without the head pinned';
  else if (merges.length > 1) result = 'merged twice';
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


def miniature(count=8):
    names = ["m%d" % i for i in range(count)]
    lines = ["model_list:", "  # A comment above the first entry."]
    for index, name in enumerate(names):
        lines += entry(name, address=(index == 3), key="MISTRAL" if index >= 6 else "GEMINI")
    lines += ["router_settings:", "  routing_strategy: simple-shuffle", "  fallbacks:",
              "    - fast: &fast_cascade"]
    lines += ["        - %s" % name for name in names]
    lines += ["  turn_off_message_logging: true", "{% if has.Gemini %}", "  extra: 1", "{% endif %}", ""]
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


def checks_of(names, failing=None, status="completed", app="github-actions"):
    return [{"name": name, "status": status, "app": {"slug": app}, "started_at": "1",
             "conclusion": "failure" if name == failing else "success"} for name in names]


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
    """[(name, expected result, scenario)]: "merged", or "not merged" with the notice it must give."""
    names, base = miniature()
    heading = review_heading()
    out = []

    def add(name, expected, scenario, failed=False):
        out.append((name, expected, scenario, failed))

    # --- Dependabot -------------------------------------------------------------------------------
    add("Dependabot: a signed minor update, every check green", "merged", dependabot())
    add("Dependabot: a signed patch update", "merged", dependabot("semver-patch"))
    add("Dependabot: a major update", "not merged", dependabot("semver-major"))
    add("Dependabot: an unsigned commit", "not merged", dependabot(signed=False))
    add("Dependabot: sign-off has not reported", "not merged",
        dependabot(names=[name for name in contexts() if name != "sign-off"]))
    add("Dependabot: a check is red", "not merged", dependabot(checks=checks_of(contexts(), failing="yamllint")))

    # --- the weekly deletions that must merge -----------------------------------------------------
    add("deletion: one whole entry, every check green but sign-off, which never starts", "merged",
        removals(deletion(base, set(block_of(base, "m1")))[0]))
    five = set()
    for name in names[:5]:
        five |= set(block_of(base, name))
    add("deletion: five whole entries", "merged", removals(deletion(base, five)[0]))
    six = set(five) | set(block_of(base, names[5]))
    add("deletion: six whole entries", "not merged", removals(deletion(base, six)[0]))
    with_slot = set(block_of(base, "m6")) | set(slot_of(base, "m6"))
    add("deletion: an entry and the cascade slot that named it", "merged",
        removals(deletion(base, with_slot)[0]))
    slot_only = deletion(base, set(slot_of(base, "m6")))[0]
    add("deletion: a cascade slot whose entry stays", "not merged", removals(slot_only))
    shifted, _ = deletion(base, set(block_of(base, "m5")))
    # m4 and m5 end with the same key line: git starts the deletion on m4's, and shows m5's as kept.
    add("deletion: a whole entry that git shows starting inside the entry above", "merged",
        removals(shifted))

    # --- the weekly deletions that must not --------------------------------------------------------
    whole = set(block_of(base, "m1"))
    # Each of these carries a whole entry, so that "one model at least" does not refuse it and only
    # the look at the deleted lines can.
    add("deletion: an entry, and the address of one that stays", "not merged",
        removals(deletion(base, whole | {base.index("      api_base: http://gateway.invalid:1234/v1")})[0]))
    add("deletion: an entry, and a setting", "not merged",
        removals(deletion(base, whole | {base.index("  turn_off_message_logging: true")})[0]))
    add("deletion: an entry, and the heading of a section", "not merged",
        removals(deletion(base, whole | {base.index("router_settings:")})[0]))
    last = set(block_of(base, "m7"))
    add("deletion: the last entry and, in the same run, the heading of the section after it", "not merged",
        removals(deletion(base, last | {base.index("router_settings:")})[0]))
    add("deletion: an entry, and the model line of one that stays", "not merged",
        removals(deletion(base, whole | {base.index("      model: provider/m2")})[0]))
    add("deletion: an entry, and the cascade slot of one that stays", "not merged",
        removals(deletion(base, whole | set(slot_of(base, "m6")))[0]))
    add("deletion: an entry, and a line of Jinja", "not merged",
        removals(deletion(base, whole | {base.index("{% if has.Gemini %}")})[0]))
    add("deletion: an entry, and another cut short with its key left behind", "not merged",
        removals(deletion(base, whole | set(block_of(base, "m2")[:3]))[0]))
    add("deletion: an entry cut short, and one whole", "not merged",
        removals(deletion(base, set(block_of(base, "m1")[:3]) | set(block_of(base, "m3")))[0]))
    # The same lines, placed so that git shows them differently, but the file left is not what a whole
    # deletion leaves: m5 and m6 end with different keys, and m6's would end up under m5's lines.
    swapped = {base.index("  - model_name: m5") + 3, base.index("  - model_name: m5") + 4,
               base.index("  - model_name: m6"), base.index("  - model_name: m6") + 1,
               base.index("  - model_name: m6") + 2}
    add("deletion: the key of one entry and the head of the next, which leaves the wrong key in place",
        "not merged", removals(deletion(base, swapped)[0]))
    add("deletion: a comment and nothing else, which names no model", "not merged",
        removals(deletion(base, {1})[0]))
    add("deletion: a section header and what follows it", "not merged",
        removals(deletion(base, {base.index("router_settings:"), base.index("  routing_strategy: simple-shuffle")})[0]))

    patch = deletion(base, whole)[0]
    add("deletion: a line is added to the patch", "not merged",
        removals(patch + "\n+  - model_name: evil", files=[{
            "filename": "templates/LiteLLM_config.yaml.j2", "status": "modified", "additions": 1,
            "deletions": counts(patch)[1], "patch": patch + "\n+  - model_name: evil"}]))
    add("deletion: GitHub counts no addition, the patch holds one", "not merged",
        removals(patch + "\n+  - model_name: evil", files=[{
            "filename": "templates/LiteLLM_config.yaml.j2", "status": "modified", "additions": 0,
            "deletions": counts(patch)[1], "patch": patch + "\n+  - model_name: evil"}]))
    asking = removals(patch)
    asking["pr"]["body"] = "Models their provider has retired.\n\n%s\n\n- a comment names m1" % heading
    add("deletion: the body asks for a reading", "not merged", asking)
    quiet = removals(patch)
    quiet["pr"]["body"] = "Models retired.\n\nThe section is called %s in the script." % heading.replace("## ", "")
    add("deletion: the heading appears only inside a sentence", "merged", quiet)
    add("deletion: a head behind the default branch", "not merged", removals(patch, behind_by=2))
    add("deletion: a check is red", "not merged", removals(
        patch, checks=checks_of([n for n in contexts() if n != "sign-off"], failing="gitleaks")))
    add("deletion: a check has not reported", "not merged", removals(
        patch, checks=checks_of([n for n in contexts() if n not in ("sign-off", "gitleaks")])))
    add("deletion: a check is still running", "not merged", removals(
        patch, checks=checks_of([n for n in contexts() if n != "sign-off"], status="in_progress")))
    add("deletion: the right check names, posted by another app", "not merged", removals(
        patch, checks=checks_of([n for n in contexts() if n != "sign-off"], app="some-other-app")))
    add("deletion: sign-off reported red", "not merged", removals(
        patch, checks=checks_of(contexts(), failing="sign-off")))
    # A sign-off that did report, and green, is of course fine: the excuse is for the one that never runs.
    add("deletion: sign-off reported green as well", "merged", removals(patch, checks=checks_of(contexts())))
    add("deletion: opened by a person", "not merged", removals(patch, author="someone"))
    add("deletion: a bot's pull request on another branch", "not merged", removals(patch, branch="claude/other"))
    add("deletion: a draft", "not merged", (lambda s: (s["pr"].update(draft=True), s)[1])(removals(patch)))
    add("deletion: two commits", "not merged", removals(patch, commits=[
        {"sha": "c1", "author": {"login": "github-actions[bot]"}, "commit": {"message": "x"}},
        {"sha": "c2", "author": {"login": "github-actions[bot]"}, "commit": {"message": "merge"}}]))
    add("deletion: the commit's author is a person", "not merged", removals(patch, commits=[
        {"sha": "c1", "author": {"login": "someone"}, "commit": {"message": "x"}}]))

    def file_of(**changes):
        base_file = {"filename": "templates/LiteLLM_config.yaml.j2", "status": "modified", "additions": 0,
                     "deletions": counts(patch)[1], "patch": patch}
        base_file.update(changes)
        return base_file
    add("deletion: another file", "not merged", removals(patch, files=[file_of(filename="tasks/main.yml")]))
    add("deletion: two files", "not merged", removals(patch, files=[file_of(), file_of(filename="x")]))
    add("deletion: the file is renamed", "not merged", removals(patch, files=[file_of(status="renamed")]))
    add("deletion: GitHub gave no patch (too large)", "not merged", removals(patch, files=[file_of(patch=None)]))
    add("deletion: GitHub's count disagrees with the patch", "not merged",
        removals(patch, files=[file_of(deletions=counts(patch)[1] + 3)]))
    add("deletion: no entry at all in the patch", "not merged", removals(
        deletion(base, {1})[0].replace("-  # A comment above the first entry.", "-  # x"),
        files=[file_of(patch="@@ -1,2 +1,1 @@\n-x\n y", deletions=1)]))
    wide = ["@@ -1,201 +0,0 @@", "-  - model_name: a", "-    litellm_params:"] + ["-      model: a"] * 199
    add("deletion: more lines than the cap", "not merged",
        removals(patch, files=[file_of(patch="\n".join(wide), deletions=len(wide) - 1)]))
    for text in ("abc", "", "0", "-3", "5.5"):
        add("deletion: the entry cap is %r" % text, "not merged",
            removals(patch, env={"REMOVALS_MAX_ENTRIES": text}), failed=True)
        add("deletion: the line cap is %r" % text, "not merged",
            removals(patch, env={"REMOVALS_MAX_LINES": text}), failed=True)
    add("deletion: the cap on entries is 1 and one entry goes", "merged",
        removals(patch, env={"REMOVALS_MAX_ENTRIES": "1"}))
    add("deletion: two entries go under a cap of 1", "not merged",
        removals(deletion(base, whole | set(block_of(base, "m2")))[0], env={"REMOVALS_MAX_ENTRIES": "1"}))
    return out


# ---------------------------------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------------------------------

def load_step():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = [step for step in workflow["jobs"]["merge"]["steps"] if step.get("id") == "merge"]
    if len(steps) != 1:
        raise SystemExit("%s: expected exactly one step with id 'merge' in job 'merge', found %d."
                         % (WORKFLOW.relative_to(ROOT), len(steps)))
    step = steps[0]
    env = {key: str(value) for key, value in (step.get("env") or {}).items() if "${{" not in str(value)}
    return step["with"]["script"], env


def play(script, env, cases):
    if shutil.which("node") is None:
        raise SystemExit("node is not on the PATH: this check runs the step's script with it.")
    ruleset = json.loads(RULESET.read_text(encoding="utf-8"))
    payload = {"script": script, "env": env, "ruleset": ruleset, "head_sha": HEAD_SHA,
               "scenarios": [case[2] for case in cases]}
    done = subprocess.run(["node", "-e", HARNESS], input=json.dumps(payload), capture_output=True,
                          text=True, timeout=120, check=False)
    if done.returncode != 0:
        raise SystemExit("node failed:\n%s" % (done.stderr or done.stdout)[-1500:])
    return json.loads(done.stdout)


def judge(cases, results):
    """[(name, what went wrong)] for the scenarios whose outcome is not the expected one."""
    wrong = []
    for (name, expected, _scenario, failed), got in zip(cases, results):
        if got["crashed"]:
            wrong.append((name, "the script threw: %s" % got["crashed"].splitlines()[0]))
        elif got["result"] != expected:
            wrong.append((name, "%s instead of %s (%s)" % (
                got["result"], expected, " | ".join(got["notices"])[:300] or got["failed"] or "no notice")))
        elif failed and not got["failed"]:
            wrong.append((name, "it should have failed the run loudly and did not"))
    return wrong


# One entry per guard: (what it is, [(text in the step's script, what it is replaced with)]). Every text
# must occur once in the script, which is how a guard that moved is noticed here.
MUTATIONS = [
    ("the shape of the deleted lines is not asked", [
        ("const shape = removalsPatchProblem(file.patch);", "const shape = null;")]),
    ("a head behind the default branch passes", [("comparison.behind_by !== 0", "false")]),
    ("a line added to the file passes", [
        ("file.additions !== 0 ||", ""),
        ("if (hunks.some((each) => each.added)) return 'a line is added';", "")]),
    ("GitHub's count of deleted lines is not compared", [("deleted.length !== file.deletions ||", "")]),
    ("a patch with no model entry passes", [("entries === 0 ||", "")]),
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
    ("a missing patch passes", [("|| !file.patch", "")]),
    ("a second commit passes", [("commits.length !== 1 ||", "")]),
    ("a person's commit passes", [("commits[0].author?.login !== 'github-actions[bot]'", "false")]),
    ("the body is not read", [(".test(pr.body ?? '')", ".test('')")]),
    ("sign-off is required of the deletions", [
        ("notApplicable.add(context);", "void context;")]),
    ("any app's check of the right name counts", [("&& run.app?.slug === 'github-actions'", "")]),
    ("a check still running passes", [("latest.status !== 'completed'", "false")]),
    ("a check that is not a success passes", [("latest.conclusion !== 'success'", "false")]),
    ("the merge is not pinned to the head", [("sha: headSha, merge_method", "merge_method")]),
    ("any bot's branch is taken for the deletions", [
        ("pr.head.ref === process.env.REMOVALS_BRANCH", "true")]),
    ("a draft passes", [("|| pr.draft", "")]),
    ("a person's pull request is taken for the deletions", [
        ("pr.user.login === 'github-actions[bot]' &&", "")]),
    # inside removalsPatchProblem
    ("a line added in the patch is not seen by the shape check", [
        ("if (hunks.some((each) => each.added)) return 'a line is added';", "")]),
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
    names, base = miniature()
    shifted, _ = deletion(base, set(block_of(base, "m5")))
    first = next(row for row in shifted.split("\n") if row.startswith("-"))
    if first.startswith("-  - model_name") or first.strip() == "-":
        print("selftest: FAILED -- the 'inside the entry above' scenario no longer starts inside an "
              "entry, so it proves nothing about placements: change the miniature file.")
        failures += 1
    for purpose, edits in MUTATIONS:
        broken = script
        missing = [old for old, _new in edits if broken.count(old) != 1]
        if missing:
            print("selftest: FAILED (%s) -- the script no longer holds exactly one: %r"
                  % (purpose, missing[0]))
            failures += 1
            continue
        for old, new in edits:
            broken = broken.replace(old, new)
        wrong = judge(cases, play(broken, env, cases))
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
    for name, _expected, _scenario, _failed in cases:
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
