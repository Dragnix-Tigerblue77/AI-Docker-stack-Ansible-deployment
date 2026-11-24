#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77 and the AI Docker stack Ansible deployment contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Play the guards of the model-drift workflow against made-up templates, days and issues.

WHY THIS CHECK EXISTS
---------------------
"LiteLLM_model_drift.yml" has two jobs, and the one that writes holds the only token that can: it
takes the template the other job made, which ran a script and two libraries nobody has reviewed yet,
and pushes it only if it is the template on main with lines taken out and the rows of its "head"
table written again, in one form that names only entries and providers the file already has. That
rule is JavaScript inside a YAML string. Nothing else ever runs it, so a comparison turned the wrong
way would be found on the day it should have refused. This extracts the function between the
"BEGIN/END template guard" markers of the workflow itself and runs it with Node on templates that
must pass and templates that must not.

WHAT IT RUNS
------------
A miniature template, and the real one, each with: nothing changed; lines deleted; a row written
again; a row written again together with a deletion; and every change the guard must refuse -- a line
added or changed, a row naming something that is no entry of the file, one testing a provider the
template does not declare, one with a condition the form does not have, one with Jinja in it, rows
exchanged, a row moved, a row repeated, a table the base did not have.

The same step keeps the two pull requests of additions, and builds the template each carries from a
provider, an id and a name per model, between the "BEGIN/END additions builder" markers. That builder
is played on the real template and on a miniature one: what it must build -- every provider, active
and commented-out anchors, a run shared by two providers -- has to be, character for character, what
the drift script's own build_additions() builds, and has to read back as the file plus those entries;
a keyless gateway's entry, written with its literal marker and the header that blanks Authorization,
active or commented out; the tables of the issue step and of the builder naming exactly the providers the
script reads, as text, since a table missing one fails only on the day it is needed;
what it must refuse -- an id or a name of another spelling (a newline, a quote, Jinja, a trailing
colon), a name that is a word of the file, a provider that is no key of its table ("__proto__"
included), an item of another shape, an id already an entry or set aside, an entry with a literal key
or an "http" base to model one on, a date, a kind or a number of items out of bounds -- the script
must refuse too. Then the whole step is played against a made-up GitHub: both opened, the one to
verify as a draft and ready for review where drafts are refused; a run with the same proposals that
writes nothing; a run with others that rewrites both, keeping a ticked box and the draft; closing
when nothing is left, and not when a catalogue was not read, a provider failed or the report was not
trusted; a run that changes nothing but the days of the comments, which pushes nothing; a person's
commit with the pull request open (left alone) and without (the step fails); the script's template
differing from the one built; proposals of another shape or a status the step does not know; a failing
deletion that leaves the additions done; a commit of the other job that is not on main. The deletions,
which share the step's code with them, are played the same way: pushed and opened ready for review, a
line added refused, a person's commit failing the step, closed when nothing is left.

The workflow keeps an issue for one thing, a catalogue still unreadable at the day's last attempt, and
two more scripts decide it. The gate's, between "BEGIN/END gate", is played on made-up days: a run
started by hand and the first attempt read without asking anything; a retry reads only when the latest
earlier scheduled attempt of the same day that left an outcome left "unreadable", passing over one that
left none, a run started by hand, a run of another day, a run listed after it, an artifact of another
outcome and a run with two; the third attempt alone is the last, with the times of the earlier ones in
order; a cron it does not number fails. Its SCHEDULES are held to the crons of "on.schedule", in their
order. The issue step's, between "BEGIN/END issue", is played on made-up issues: opened at the last
attempt only, with the providers, the class of each failure and the earlier times; nothing written at an
earlier attempt or by a run started by hand; the issue the workflow kept while it reported every drift
taken over rather than doubled; closed, with a comment, by any run that reads every catalogue, a day of
deletions or of additions alone included; somebody else's issue, or one without the marker or under
another title, never written; and what the "read" job hands over refused, with nothing written, when a
word is no provider and class it knows, when the status and the catalogues named disagree, or when an
earlier time is no time.

"--selftest" proves the scenarios can fail: it breaks the function one guard at a time and requires
some scenario to notice each, then does the same to the builder and the step, to the gate and to the
issue step, and reorders the crons without the gate. A guard no scenario notices is one this check
cannot vouch for.

WHAT IT DOES NOT PROVE
----------------------
That the step calls the function on what it reads from GitHub: the wiring is checked as text. Nor that
GitHub fires a cron with "github.event.schedule" spelt as "on.schedule" writes it, holds a retry behind
the attempt before it, or lists the runs and artifacts as the made-up one does; no scheduled run can be
played here. Nor
that "the rows of the table written again" are right -- "check_compose_template.py" holds each alias
to the first member of its cascade for every set of keys. Nor that GitHub answers as the made-up one
does: its answers are octokit's as the documentation gives them, not recorded, and the refusal of a
draft is matched on its status and the word "draft" alone. Node is needed on the PATH, and PyYAML
and Jinja2, since the drift script is imported to compare its build with the step's.
"""

import base64
import hashlib
import importlib.util
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "LiteLLM_model_drift.yml"
TEMPLATE = ROOT / "templates" / "LiteLLM_config.yaml.j2"
STEP = "Open, update or close the drift pull requests"
BEGIN, END = "// BEGIN template guard", "// END template guard"

HARNESS = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const templateProblem = new Function(input.guard + '\nreturn templateProblem;')();
process.stdout.write(JSON.stringify(input.cases.map((c) => templateProblem(c.base, c.new))));
"""

MINIATURE = """\
{% set has = {
  'Gemini': Artificial_Intelligence_LiteLLM_Gemini_API_key is string,
  'Groq': Artificial_Intelligence_LiteLLM_Groq_API_key is string,
  'OpenRouter': Artificial_Intelligence_LiteLLM_OpenRouter_API_key is string
} %}
{% set head = {
  'router': 'alpha' if has.Gemini else 'beta' if has.Groq else 'omega',
  'lite': 'tiny' if has.OpenRouter else false
} %}
model_list:
  - model_name: alpha
    litellm_params:
      model: gemini/one
  - model_name: beta
    litellm_params:
      model: groq/two
  - model_name: gamma
    litellm_params:
      model: groq/three
  - model_name: tiny
    litellm_params:
      model: openrouter/four
  - model_name: omega
    litellm_params:
      model: openai/auto/five
router_settings:
  fallbacks:
    - router:
        - alpha
        - beta
        - gamma
        - omega
"""

ROUTER_ROW = "  'router': 'alpha' if has.Gemini else 'beta' if has.Groq else 'omega',\n"
LITE_ROW = "  'lite': 'tiny' if has.OpenRouter else false\n"


def real_rows():
    text = TEMPLATE.read_text(encoding="utf-8")
    flash = next(line for line in text.splitlines(keepends=True) if line.startswith("  'flash':"))
    pro = next(line for line in text.splitlines(keepends=True) if line.startswith("  'pro':"))
    return text, flash, pro


def scenarios():
    """[(name, base, new, expected)], expected being None (accepted) or a text the reason contains."""
    real, flash, pro = real_rows()
    out = []

    def add(name, base, new, expected):
        out.append((name, base, new, expected))

    def swap(text, old, new):
        assert text.count(old) == 1, old
        return text.replace(old, new, 1)

    for label, base, router_row, lite_row, deletable in (
            ("miniature", MINIATURE, ROUTER_ROW, LITE_ROW, "  - model_name: gamma\n    litellm_params:\n      model: groq/three\n"),
            ("real template", real, flash, pro, None)):
        if deletable is None:
            deletable = "\n".join(real.split("\n")[real.split("\n").index("  - model_name: gemma-4-26b-gemini"):][:5]) + "\n"
        gone = swap(base, deletable, "")
        router = router_row.split("'")[1]
        # A row that uses only names and providers the file has.
        if label == "miniature":
            rewritten = "  'router': 'alpha' if has.Gemini else 'omega',\n"
            drifted_names = "  'router': 'alpha' if has.Gemini else 'nowhere',\n"
            other_provider = "  'router': 'alpha' if has.Cerebras else 'omega',\n"
            extra_condition = "  'router': 'alpha' if has.Gemini and 1 else 'omega',\n"
            jinja = "  'router': '{{ 1 }}',\n"
        else:
            rewritten = "  'flash': 'gemini-3-8-flash' if has.Gemini else 'mistral-small' if has.Mistral else 'omniroute-free-auto',\n"
            drifted_names = "  'flash': 'gemini-3-8-flash' if has.Gemini else 'nowhere' if has.Mistral else 'omniroute-free-auto',\n"
            other_provider = "  'flash': 'gemini-3-8-flash' if has.Cerebras else 'omniroute-free-auto',\n"
            extra_condition = "  'flash': 'gemini-3-8-flash' if has.Gemini and 1 else 'omniroute-free-auto',\n"
            jinja = "  'flash': '{{ 1 }}',\n"
        tag = label + ": "
        add(tag + "nothing changed", base, base, None)
        add(tag + "lines deleted", base, gone, None)
        add(tag + "a row written again with names and providers the file has", base,
            swap(base, router_row, rewritten), None)
        add(tag + "a row written again, and lines deleted", base,
            swap(swap(base, router_row, rewritten), deletable, ""), None)
        add(tag + "a line added", base, swap(base, router_row, router_row + "  # a new comment\n"),
            "does not hold")
        add(tag + "a line changed outside the table", base,
            swap(base, "model_list:\n", "model_list:  # changed\n"), "does not hold")
        add(tag + "a row naming something that is no entry of the file", base,
            swap(base, router_row, drifted_names), "is no entry of the file")
        add(tag + "a row testing a provider the template does not declare", base,
            swap(base, router_row, other_provider), "does not declare")
        add(tag + "a row with a condition the form does not have", base,
            swap(base, router_row, extra_condition), "does not hold")
        add(tag + "a row with Jinja in it, which is no name of an entry", base,
            swap(base, router_row, jinja), "is no entry of the file")
        add(tag + "a row for a router the table does not have", base,
            swap(base, router_row, router_row.replace("'%s'" % router, "'elsewhere'", 1)), "does not hold")
        add(tag + "a row written again, then repeated", base,
            swap(base, router_row, rewritten + rewritten), "does not hold")
        add(tag + "a row written again, then moved to the end of the file", base,
            swap(base, router_row, "") + rewritten, "does not hold")
    add("miniature: rows exchanged", MINIATURE,
        swap(swap(MINIATURE, ROUTER_ROW, "@@ROUTER@@"), LITE_ROW, ROUTER_ROW.rstrip(",\n") + "\n")
        .replace("@@ROUTER@@", LITE_ROW.rstrip("\n") + ",\n"), "does not hold")
    add("a table the base did not have", swap(MINIATURE, ROUTER_ROW, "").replace(LITE_ROW, ""),
        MINIATURE.replace(ROUTER_ROW + LITE_ROW, ROUTER_ROW + LITE_ROW), "does not hold")
    return out


def load_guard():
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = document["jobs"]["publish"]["steps"]
    script = next((step["with"]["script"] for step in steps if step.get("name") == STEP), None)
    if script is None:
        raise SystemExit("the step %r is not in %s" % (STEP, WORKFLOW.name))
    if script.count(BEGIN) != 1 or script.count(END) != 1:
        raise SystemExit("the step's script must hold the markers %r and %r once each" % (BEGIN, END))
    guard = script.split(BEGIN, 1)[1].split(END, 1)[0]
    # The wiring: the step calls the function on what it reads, and a problem stops the push.
    if not re.search(r"const problem = templateProblem\(\s*Buffer\.from\(original\.content", script):
        raise SystemExit("the step does not call templateProblem on the base it read from GitHub")
    if not re.search(r"if \(problem\) \{\s*core\.setFailed\([^;]*\);\s*return;\s*\}", script):
        raise SystemExit("the step does not stop when templateProblem finds a problem")
    return guard


def play(guard, cases):
    if shutil.which("node") is None:
        raise SystemExit("node is not on the PATH: this check runs the guard with it.")
    payload = {"guard": guard, "cases": [{"base": base, "new": new} for _, base, new, _ in cases]}
    done = subprocess.run(["node", "-e", HARNESS], input=json.dumps(payload), capture_output=True,
                          text=True, check=False)
    if done.returncode != 0:
        raise SystemExit("node failed:\n%s" % (done.stderr or done.stdout)[-1500:])
    results = json.loads(done.stdout)
    if len(results) != len(cases):
        raise SystemExit("node answered %d scenario(s) out of %d." % (len(results), len(cases)))
    return results


def judge(cases, results):
    wrong = []
    for (name, _, _, expected), got in zip(cases, results):
        if expected is None and got is not None:
            wrong.append((name, "refused, and it should have been accepted: %s" % got))
        elif expected is not None and got is None:
            wrong.append((name, "accepted, and it should have been refused (%r)" % expected))
        elif expected is not None and expected not in got:
            wrong.append((name, "refused for another reason: %s" % got))
    return wrong


# What breaks, one guard at a time: (what it stops doing, the text of the function, its replacement).
MUTATIONS = [
    ("check that a row names entries of the file",
     'if (!names.has(term[1])) return', 'if (false) return'),
    ("check that a row tests declared providers",
     "if (term[2] !== undefined && !providers.has(term[2])) return", "if (false) return"),
    ("refuse a line the base does not hold",
     "if (at === baseLines.length) return", "if (false) return"),
    ("keep a rewritten row at the place of the original",
     "wanted = original;", "wanted = line;"),
    ("read a row in the one form only",
     "(?:'[^']+'[ \\t]+if[ \\t]+has\\.\\w+[ \\t]+else[ \\t]+)*(?:'[^']+'|false))", ".*)"),
]


def run_selftest():
    guard = load_guard()
    cases = scenarios()
    wrong = judge(cases, play(guard, cases))
    if wrong:
        print("the guard fails its own scenarios before anything is broken:")
        for name, why in wrong:
            print("  %s: %s" % (name, why))
        return 1
    failures = 0
    for label, old, new in MUTATIONS:
        if guard.count(old) != 1:
            failures += 1
            print("selftest: the text of the guard that should %s has moved: %r" % (label, old))
            continue
        broken = guard.replace(old, new, 1)
        try:
            noticed = bool(judge(cases, play(broken, cases)))
        except SystemExit as error:
            failures += 1
            print("selftest: breaking the guard that should %s left a script that does not run: %s"
                  % (label, str(error)[:200]))
            continue
        if noticed:
            print("selftest: ok -- some scenario notices a guard that stops: %s" % label)
        else:
            failures += 1
            print("selftest: FAILED -- no scenario notices a guard that stops: %s" % label)
    if failures:
        return 1
    print("check_drift_publish_guard selftest: %d scenario(s) judged as expected, %d broken guard(s) noticed."
          % (len(cases), len(MUTATIONS)))
    return 0


# ---------------------------------------------------------------------------------------------------
# The additions: the builder of the template, and the step's handling of the two pull requests
# ---------------------------------------------------------------------------------------------------

DRIFT_SCRIPT = ROOT / ".github" / "scripts" / "check_LiteLLM_model_drift.py"
DRIFT_SELFTEST = ROOT / ".github" / "scripts" / "check_LiteLLM_model_drift_selftest.py"
BUILDER_BEGIN, BUILDER_END = "// BEGIN additions builder", "// END additions builder"
BASE_SHA = "0123456789abcdef0123456789abcdef01234567"

BUILDER_HARNESS = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const { additionsTemplate } = new Function(input.builder + '\nreturn { additionsTemplate };')();
process.stdout.write(JSON.stringify(input.cases.map((c) => {
  const built = additionsTemplate(c.base, c.date, c.kind, c.items);
  return built.problem !== undefined ? { problem: String(built.problem) } : { text: built.text };
})));
"""

# Plays the whole step against a made-up GitHub, which keeps the branches and the pull requests a
# scenario starts from and records every call: the same objects github-script hands a script.
STEP_HARNESS = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const crypto = require('crypto');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const fail = (message, status) => Object.assign(new Error(message), { status });

async function play(scenario) {
  const run = new AsyncFunction('github', 'context', 'core', 'process', 'require', input.script);
  const calls = [];
  const notices = [];
  const warnings = [];
  const failures = [];
  const outputs = {};
  const refs = JSON.parse(JSON.stringify(scenario.refs));
  const pulls = JSON.parse(JSON.stringify(scenario.pulls));
  let next = 101;
  let commits = 1;
  const record = (name, args) => calls.push({ name, args });
  const tree = (base64) => 'tree-' + crypto.createHash('sha1').update(base64).digest('hex');
  const github = { rest: {
    pulls: {
      list: async (args) => {
        record('pulls.list', args);
        const branch = args.head.split(':')[1];
        if (scenario.broken === branch) throw fail('made-up failure', 500);
        return { data: pulls.filter((pull) => pull.state === 'open' && pull.head.ref === branch) };
      },
      create: async (args) => {
        record('pulls.create', args);
        if (args.draft && scenario.noDrafts) throw fail('Validation Failed: Draft pull requests are not supported in this repository.', 422);
        const pull = { number: next++, title: args.title, body: args.body, draft: args.draft, state: 'open', head: { ref: args.head } };
        pulls.push(pull);
        return { data: pull };
      },
      update: async (args) => {
        record('pulls.update', args);
        const pull = pulls.find((each) => each.number === args.pull_number);
        for (const key of ['title', 'body', 'state']) if (args[key] !== undefined) pull[key] = args[key];
        return { data: pull };
      },
    },
    issues: { createComment: async (args) => { record('issues.createComment', args); return { data: {} }; } },
    git: {
      getRef: async (args) => {
        record('git.getRef', args);
        const ref = refs[args.ref.replace(/^heads\//, '')];
        if (!ref) throw fail('Not Found', 404);
        return { data: { object: { sha: ref.sha } } };
      },
      getCommit: async (args) => {
        record('git.getCommit', args);
        if (args.commit_sha === input.base) return { data: { tree: { sha: 'base-tree' } } };
        const ref = Object.values(refs).find((each) => each.sha === args.commit_sha);
        if (!ref) throw fail('unexpected commit ' + args.commit_sha, 500);
        return { data: { tree: { sha: ref.tree } } };
      },
      createBlob: async (args) => { record('git.createBlob', args); return { data: { sha: tree(args.content) } }; },
      createTree: async (args) => {
        record('git.createTree', args);
        const sha = args.tree.length === 1 ? args.tree[0].sha
          : 'tree-' + crypto.createHash('sha1').update(args.tree.map((entry) => entry.sha).join('+')).digest('hex');
        return { data: { sha } };
      },
      createCommit: async (args) => { record('git.createCommit', args); return { data: { sha: 'commit-' + commits++ } }; },
      updateRef: async (args) => { record('git.updateRef', args); refs[args.ref.replace(/^heads\//, '')].sha = args.sha; return { data: {} }; },
      createRef: async (args) => { record('git.createRef', args); refs[args.ref.replace(/^refs\/heads\//, '')] = { sha: args.sha, tree: null, commits: [] }; return { data: {} }; },
    },
    repos: {
      compareCommitsWithBasehead: async (args) => {
        record('repos.compare', args);
        const [left, right] = args.basehead.split('...');
        if (left === 'main') {
          const ref = Object.values(refs).find((each) => each.sha === right);
          const commits = (ref?.commits ?? []).map((each) => ({ sha: each.sha, commit: { author: { name: each.author } }, parents: each.parents }));
          return { data: { commits, total_commits: commits.length } };
        }
        return { data: { status: scenario.ancestry } };
      },
      getContent: async (args) => {
        record('repos.getContent', args);
        const ref = Object.values(refs).find((each) => each.sha === args.ref);
        if (!ref && args.ref !== input.base) throw fail('unexpected ref ' + args.ref, 500);
        return { data: { type: 'file', encoding: 'base64', content: Buffer.from(ref ? ref.text : scenario.baseText ?? input.baseText).toString('base64') } };
      },
    },
    actions: {
      listWorkflowRuns: async (args) => { record('actions.listWorkflowRuns', args); return { data: { total_count: 0 } }; },
      createWorkflowDispatch: async (args) => { record('actions.createWorkflowDispatch', args); return {}; },
    },
  } };
  const core = {
    notice: (message) => notices.push(String(message)),
    warning: (message) => warnings.push(String(message)),
    error: (message) => failures.push(String(message)),
    setFailed: (message) => failures.push(String(message)),
    setOutput: (name, value) => { outputs[name] = value; },
  };
  const context = { repo: { owner: 'o', repo: 'r' } };
  let crashed = null;
  try {
    await run(github, context, core, { env: scenario.env }, require);
  } catch (error) {
    crashed = String(error && error.stack || error);
  }
  return { calls, notices, warnings, failures, outputs, refs, pulls, crashed };
}

(async () => {
  const out = [];
  for (const scenario of input.scenarios) out.push(await play(scenario));
  process.stdout.write(JSON.stringify(out));
})();
"""


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def drift_module():
    """The drift script, imported: its build_additions is what the builder of the step must agree with."""
    return load_module("check_LiteLLM_model_drift", DRIFT_SCRIPT)


def drift_selftest_module():
    """The module of the drift script's verification cases, imported: it holds the miniature template."""
    return load_module("check_LiteLLM_model_drift_selftest", DRIFT_SELFTEST)


def step_document():
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = document["jobs"]["publish"]["steps"]
    step = next((step for step in steps if step.get("name") == STEP), None)
    if step is None:
        raise SystemExit("the step %r is not in %s" % (STEP, WORKFLOW.name))
    return document, step


def load_builder():
    _, step = step_document()
    script = step["with"]["script"]
    if script.count(BUILDER_BEGIN) != 1 or script.count(BUILDER_END) != 1:
        raise SystemExit("the step's script must hold the markers %r and %r once each"
                         % (BUILDER_BEGIN, BUILDER_END))
    # The wiring: the step builds the template from the items, and pushes only that text, and only
    # when the script's own build is the same.
    for pattern, what in (
            (r"const built = additionsTemplate\(baseText, proposals\.date, kind, part\.items\);",
             "build the template from the validated items"),
            (r"if \(handed !== built\.text\) \{\s*core\.setFailed\([^;]*\);\s*return;\s*\}",
             "stop when the script's build is another text"),
            (r"const content = kept !== null && onlyDaysDiffer\(kept, built\) \? kept : built\.text;",
             "push the text it built, or the branch's own where only the days differ"),
            (r"publish\(spec\.branch, head, \[\[template, content\], \[catalog, handedCatalog\], \[scores, handedScores\]\], message,",
             "push that text, the catalogue generated from it and the figures it shows")):
        if not re.search(pattern, script):
            raise SystemExit("the step does not %s" % what)
    return script.split(BUILDER_BEGIN, 1)[1].split(BUILDER_END, 1)[0]


def node(harness, payload):
    if shutil.which("node") is None:
        raise SystemExit("node is not on the PATH: this check runs the step's script with it.")
    done = subprocess.run(["node", "-e", harness], input=json.dumps(payload), capture_output=True,
                          text=True, check=False, timeout=300)
    if done.returncode != 0:
        raise SystemExit("node failed:\n%s" % (done.stderr or done.stdout)[-1500:])
    return json.loads(done.stdout)


def item(provider, identifier, name, usage=None):
    return dict({"provider": provider, "id": identifier, "name": name}, **({"usage": usage} if usage else {}))


# Kilo's free ids are flagged by its catalogue, and some are spelt without ":free": both are written.
READY_ITEMS = [item("openrouter", "vendor/fresh-one:free", "fresh-one-free"),
            item("openrouter", "vendor/fresh-two.5:free", "fresh-two-5-free"),
            item("kilo", "vendor/fresh-three:free", "fresh-three-kilo"),
            item("kilo", "vendor/fresh-four", "fresh-four-kilo"),
            item("requesty", "vendor/fresh-six", "fresh-six-requesty")]
TO_VERIFY = [item("gemini", "gemini-9-pro", "gemini-9-pro"), item("groq", "vendor/fast-9", "fast-9-groq"),
             item("mistral", "magistral-9", "magistral-9"), item("deepseek", "deepseek-v9", "deepseek-v9-direct"),
             item("cerebras", "zai-glm-9", "zai-glm-9-cerebras"),
             item("sambanova", "DeepSeek-V9", "deepseek-v9-sambanova"),
             item("cloudflare", "@cf/vendor/model-9", "model-9-cloudflare"),
             item("kilo", "vendor/fresh-five:free", "fresh-five-kilo"),
             item("nvidia", "vendor/fresh-seven", "fresh-seven-nvidia"),
             item("ovhcloud", "Fresh-Eight.1", "fresh-eight-1-ovh"),
             item("requesty", "vendor/fresh-nine", "fresh-nine-requesty"),
             item("zai", "glm-9-flash", "glm-9-flash-zai"),
             item("centai", "hy9-flash:free", "hy9-flash-cent-ai"),
             item("aionlabs", "aion-labs/aion-9", "aion-9-aion-labs")]


# One model of every usage other than chat, each of a provider that can have it and none of which has to be
# first of its kind: the real template has entries of each mode.
USAGE_ITEMS = [item("gemini", "gemini-9-embed", "gemini-9-embed", "embeddings"),
               item("mistral", "voxtral-9-transcribe", "voxtral-9-transcribe", "transcription"),
               item("groq", "whisper-9", "whisper-9-groq", "transcription"),
               item("gemini", "gemini-9-tts", "gemini-9-tts", "speech"),
               item("gemini", "gemini-9-transcribe", "gemini-9-transcribe", "transcription"),
               item("mistral", "mistral-embed-9", "mistral-embed-9", "embeddings"),
               item("cloudflare", "@cf/cloudflare/clef-9", "clef-9-cloudflare", "decision"),
               item("cloudflare", "@cf/cloudflare/clairic-9", "clairic-9-cloudflare", "extraction"),
               item("cloudflare", "@cf/vendor/embed-8", "embed-8-cloudflare", "embeddings"),
               item("openrouter", "vendor/embed-two:free", "embed-two-free", "embeddings"),
               item("nvidia", "vendor/embed-nine", "embed-nine-nvidia", "embeddings"),
               item("openrouter", "vendor/paint-nine:free", "paint-nine-free", "image"),
               item("gemini", "gemini-9-video", "gemini-9-video", "video"),
               item("mistral", "mistral-rerank-9", "mistral-rerank-9", "rerank"),
               item("groq", "vendor/guard-nine", "guard-nine-groq", "moderation"),
               item("mistral", "mistral-ocr-9", "mistral-ocr-9", "ocr"),
               item("cloudflare", "@cf/vendor/paint-8", "paint-8-cloudflare", "image")]


def builder_scenarios(real, drift):
    """[(name, base, date, kind, items, expected)], "expected" None for a file both builders must write
    alike, or a text the step's reason for refusing contains (the script must refuse it too)."""
    out = []
    date = "2026-11-23"
    miniature = drift_selftest_module().ADDITIONS_TEMPLATE

    def add(name, items, expected=None, base=real, kind="ready", day=date):
        out.append((name, base, day, kind, items, expected))

    add("real template: models of which everything is known", READY_ITEMS)
    add("real template: one model of every other provider", TO_VERIFY, kind="to_verify")
    add("real template: a model of every usage other than chat, each after the last entry of its mode",
        USAGE_ITEMS, kind="to_verify")
    add("real template: an embedding model free on OpenRouter is ready, with the mode and the group of its usage",
        [item("openrouter", "vendor/embed-one:free", "embed-one-free", "embeddings")])
    add("real template: Cloudflare's embedding goes through the OpenAI-compatible endpoint, its base read from the "
        "environment", [item("cloudflare", "@cf/vendor/embed-9", "embed-9-cloudflare", "embeddings")],
        kind="to_verify")
    add("real template: a chat model of Cloudflare is not written after its embedding entry or a typed one",
        [item("cloudflare", "@cf/vendor/chat-9", "chat-9-cloudflare")], kind="to_verify")
    add("miniature: an embedding model of a provider with no entry of the mode follows its chat entry",
        [item("gemini", "gem-embed", "gem-embed", "embeddings")], base=miniature, kind="to_verify")
    add("miniature: a speech model of a provider with commented-out entries only is followed commented out",
        [item("cerebras", "cb-voice", "cb-voice-cerebras", "speech")], base=miniature, kind="to_verify")
    for usage, provider, identifier, router in (
            ("decision", "gemini", "gemini-9-decide", "Auto-Decision"), ("extraction", "groq", "vendor/extract-9", "Auto-Extraction"),
            ("speech", "cloudflare", "@cf/vendor/say-9", "Auto-TTS"), ("speech", "groq", "vendor/say-9", "Auto-TTS"),
            ("speech", "openrouter", "vendor/say-9:free", "Auto-TTS"),
            ("transcription", "cloudflare", "@cf/vendor/hear-9", "Auto-STT")):
        add("a %s model of %s is refused: the %s router does not route to it" % (usage, provider, router),
            [item(provider, identifier, "fresh-" + provider, usage)], "is not one of the providers of the %s router" % router,
            kind="to_verify")
    add("a typed model of Aion Labs with no router is written in the group of its own",
        [item("aionlabs", "aion-labs/embed-9", "embed-9-aion-labs", "embeddings")], kind="to_verify")
    cascaded = miniature.replace("    - flash:\n", "    - Auto-Flash-Lite:\n")
    assert cascaded != miniature
    add("miniature: a text model is written at the tail of the Auto-Flash-Lite cascade, under its provider's key",
        [item("openrouter", "vendor/tail:free", "tail-free"), item("gemini", "gem-tail", "gem-tail")],
        base=cascaded, kind="to_verify")
    add("miniature: a keyless gateway's entry is written at the tail with no condition",
        [item("kilo", "vendor/tail:free", "tail-kilo")], base=cascaded)
    add("miniature: a cascade closed by its own block is written at its tail, inside the block",
        [item("gemini", "gem-tail", "gem-tail")], kind="to_verify",
        base=cascaded.replace("router_settings:\n  fallbacks:\n    - Auto-Flash-Lite:\n",
                              "router_settings:\n  fallbacks:\n{% if has.OpenRouter %}\n    - Auto-Flash-Lite:\n")
        .replace("        - free-one\n", "        - free-one\n{% endif %}\n    - other:\n        - gem-one\n"))
    add("miniature: a cascade with an else branch is refused, since a slot would land in one branch only",
        [item("gemini", "gem-tail", "gem-tail")], "has an else branch", kind="to_verify",
        base=cascaded.replace("        - gem-one\n", "{% if has.Gemini %}\n        - gem-one\n{% else %}\n        - free-one\n{% endif %}\n", 1))
    add("a typed model of a router whose cascade the template lacks is written with no slot",
        [item("gemini", "gem-voice", "gem-voice", "speech")], base=miniature, kind="to_verify")
    add("an embedding model of Cloudflare is refused where the template has no embedding entry of it",
        [item("cloudflare", "@cf/vendor/embed-9", "embed-9-cloudflare", "embeddings")],
        "has no embedding entry of cloudflare", kind="to_verify",
        base=real.replace("os.environ/CLOUDFLARE_EMBEDDINGS_API_BASE", "https://upstream-host/v1"))
    plain_base = real.replace('      model: openai/@cf/baai/bge-m3\n      api_base: "os.environ/CLOUDFLARE_EMBEDDINGS_API_BASE"',
                              '      model: cloudflare/@cf/baai/bge-m3\n      api_base: "https://upstream-host/v1"')
    assert plain_base != real
    add("an embedding model of Cloudflare modelled on an entry whose base is a plain address is refused",
        [item("cloudflare", "@cf/vendor/embed-9", "embed-9-cloudflare", "embeddings")],
        "has no embedding entry of cloudflare", kind="to_verify", base=plain_base)
    for usage in ("chat", "unclassified", "audio", "", "Embeddings", "embedding", None, ["speech"]):
        add("a usage the template has no mode for is refused: %r" % (usage,),
            [dict(item("openrouter", "vendor/a:free", "a-free"), usage=usage)], "usage is none")
    add("a typed item with a key more is refused",
        [dict(item("openrouter", "vendor/a:free", "a-free", "embeddings"), api_base="https://x")], "an item is not")
    add("a ready typed model of a provider whose API does not state its free tier is refused",
        [item("gemini", "gemini-9-embed", "gemini-9-embed", "embeddings")], "free tier, and only")
    add("a typed id already an entry is refused",
        [item("cloudflare", "@cf/baai/bge-m3", "fresh-embed-cloudflare", "embeddings")], "is already an entry",
        kind="to_verify")
    add("a typed id set aside is refused", [item("openrouter", "vendor/set-aside:free", "fresh-free", "embeddings")],
        "set aside by a drift-ignore line", base=miniature)
    add("miniature: a provider with commented-out entries only is followed commented out, after its run",
        [item("cerebras", "cb-three", "cb-three-cerebras")], base=miniature, kind="to_verify")
    add("miniature: a commented-out entry with a base is followed with that base",
        [item("sambanova", "sn-two", "sn-two-sambanova")], base=miniature, kind="to_verify")
    add("miniature: a provider with both follows its last active entry",
        [item("gemini", "gem-two", "gem-two")], base=miniature, kind="to_verify")
    add("miniature: a keyless gateway's entries follow its last one, with the literal marker and the blanked header",
        [item("kilo", "vendor/gw-two:free", "gw-two-kilo"), item("kilo", "vendor/gw-three", "gw-three-kilo")],
        base=miniature)
    kilo_commented = miniature.replace(
        "  - model_name: gw-one\n    litellm_params:\n      model: openai/vendor/gw-one:free\n"
        '      api_base: "https://ai-gateway.kilo.ai/api/v1"\n      api_key: "gw-no-key"\n'
        '      extra_headers:\n        Authorization: ""\n',
        "  # Served, but not routed to: a test.\n  # - model_name: gw-one\n  #   litellm_params:\n"
        '  #     model: openai/vendor/gw-one:free\n  #     api_base: "https://ai-gateway.kilo.ai/api/v1"\n'
        '  #     api_key: "gw-no-key"\n  #     extra_headers:\n  #       Authorization: ""\n')
    assert kilo_commented != miniature
    add("miniature: a keyless gateway with a commented-out entry only is followed commented out, header and all",
        [item("kilo", "vendor/gw-two:free", "gw-two-kilo")], base=kilo_commented, kind="to_verify")
    add("a keyless gateway's entry modelled on a key read from the environment is refused",
        [item("kilo", "vendor/gw-two:free", "gw-two-kilo")], "is not a plain marker",
        base=miniature.replace('api_key: "gw-no-key"', 'api_key: "os.environ/KILO_API_KEY"'))
    add("miniature: two models of one provider follow each other",
        [item("openrouter", "vendor/a:free", "a-free"), item("openrouter", "vendor/b:free", "b-free")],
        base=miniature)
    hostile_ids = ("vendor/a b:free", "vendor/x:free\n  - model_name: evil", "{{ 7 * 7 }}:free",
                   "vendor/a::b:free", "vendor//a:free", "vendor/a:free:", "vendor/\"a:free",
                   "vendor/#a:free", "-vendor/a:free", "vendor/a:free'", "x" * 200 + ":free",
                   "vendor/a:free\r", "vendor/a:free`", "@evil/a:free", "x@cf/a:free", "@cf/@cf/a:free",
                   "vendor/@cf/a:free", "@cf/", "@@cf/a:free")
    for identifier in hostile_ids:
        add("an id spelt otherwise is refused: %r" % identifier[:40],
            [item("openrouter", identifier, "a-free")], "an id is not spelt like one")
    for name in ("Evil", "a_b", "-a", "a-", "a--b", "a b", "a\nb", "a" * 81, "", "a.b"):
        add("a name spelt otherwise is refused: %r" % name[:20], [item("openrouter", "vendor/a:free", name)],
            "a name is not spelt like the file's")
    add("a name that is a word of the template is refused (a router)", [item("openrouter", "vendor/a:free", "flash")],
        "already a word of the template")
    add("a name that is a word of the template is refused (an entry)",
        [item("openrouter", "vendor/a:free", "gemma-4-31b-free")], "already a word of the template")
    add("two items of one name are refused", [item("openrouter", "vendor/a:free", "same-free"),
                                              item("openrouter", "vendor/b:free", "same-free")],
        "already a word of the template or another item's")
    for provider in ("__proto__", "constructor", "toString", "hasOwnProperty", "openai", "OpenRouter", ""):
        add("a provider this does not read is refused: %r" % provider,
            [item(provider, "vendor/a:free", "a-free")], "names no provider")
    add("a provider that is no text is refused", [{"provider": ["openrouter"], "id": "vendor/a:free", "name": "a-free"}],
        "names no provider")
    add("an item with a key more is refused", [dict(item("openrouter", "vendor/a:free", "a-free"), api_base="https://x")],
        "an item is not")
    add("an item with a key less is refused", [{"provider": "openrouter", "id": "vendor/a:free"}], "an item is not")
    add("an item that is a list is refused", [["openrouter", "vendor/a:free", "a-free"]], "an item is not")
    add("an item that is nothing is refused", [None], "an item is not")
    add("an id that is no text is refused", [{"provider": "openrouter", "id": 7, "name": "a-free"}], "an id is not")
    add("a ready model of a provider whose API does not state its free tier is refused",
        [item("gemini", "gemini-9", "gemini-9")], "free tier, and only")
    add("a ready Cloudflare model is refused too: its free tier is prose on a pricing page",
        [item("cloudflare", "@cf/vendor/model-9", "model-9-cloudflare")], "free tier, and only")
    for identifier in ("@evil/model-9", "@cf/", "@cf/@cf/model-9", "vendor/@cf/model-9", "@cf/model-9@x"):
        add("a Cloudflare id spelt otherwise is refused: %r" % identifier,
            [item("cloudflare", identifier, "model-9-cloudflare")], "an id is not spelt like one", kind="to_verify")
    add("a Cloudflare id that is already an entry is refused",
        [item("cloudflare", "@cf/openai/gpt-oss-120b", "fresh-cloudflare")], "is already an entry", kind="to_verify")
    add("an OpenRouter model to verify, a fact of it missing, is built alike",
        [item("openrouter", "vendor/a:free", "a-free"), item("gemini", "gemini-9", "gemini-9")], kind="to_verify")
    add('an OpenRouter id without ":free" is refused when ready', [item("openrouter", "vendor/a", "a-free")],
        'does not end in ":free"')
    add('an OpenRouter id without ":free" is refused when to verify too', [item("openrouter", "vendor/a", "a-free")],
        'does not end in ":free"', kind="to_verify")
    add("an id already an entry is refused", [item("openrouter", "google/gemma-4-31b-it:free", "fresh-free")],
        "is already an entry")
    add("a Kilo id already an entry is refused", [item("kilo", "nvidia/nemotron-3-ultra-550b-a55b:free", "fresh-kilo")],
        "is already an entry")
    add("an OVHcloud id already an entry is refused", [item("ovhcloud", "gpt-oss-120b", "fresh-ovh")],
        "is already an entry", kind="to_verify")
    add("an NVIDIA id already an entry is refused", [item("nvidia", "moonshotai/kimi-k3.1-pro", "fresh-nvidia")],
        "is already an entry", kind="to_verify")
    add("a Requesty id already an entry is refused", [item("requesty", "nvidia/nemotron-3-ultra-550b-a55b", "fresh-requesty")],
        "is already an entry")
    add("a ready model of a provider whose API states a price and no free tier is refused",
        [item("ovhcloud", "Fresh-Eight.1", "fresh-eight-1-ovh")], "free tier, and only")
    add("a ready model of a provider that states nothing is refused",
        [item("nvidia", "vendor/fresh-seven", "fresh-seven-nvidia")], "free tier, and only")
    add("a Kilo id set aside by drift-ignore is refused", [item("kilo", "kilo-auto/free", "auto-kilo")],
        "set aside by a drift-ignore line")
    add("an id already a commented-out entry is refused", [item("cerebras", "cb-two", "fresh-cerebras")],
        "is already an entry", base=miniature, kind="to_verify")
    add("an id set aside by drift-ignore is refused", [item("openrouter", "vendor/set-aside:free", "fresh-free")],
        "set aside by a drift-ignore line", base=miniature)
    add("a provider without an entry to model one on is refused", [item("mistral", "magistral-9", "magistral-9")],
        "no entry of mistral", base=miniature, kind="to_verify")
    add("an entry whose key is not read through a credential is not modelled on",
        [item("groq", "vendor/fresh", "fresh-groq")], "does not read its key through a credential",
        base=miniature, kind="to_verify")
    add("an entry whose credential is spelt otherwise is not modelled on",
        [item("groq", "vendor/fresh", "fresh-groq")], "does not read its key through a credential",
        base=miniature.replace('api_key: "not-from-the-environment"', 'litellm_credential_name: "Groq_Key"'),
        kind="to_verify")
    add("an entry whose base is not https is not modelled on",
        [item("deepseek", "fresh", "fresh-direct")], "is not a plain https address",
        base=miniature, kind="to_verify")
    commented_only = miniature.replace(
        "  - model_name: free-one\n    litellm_params:\n      model: openrouter/vendor/one:free\n"
        '      litellm_credential_name: "openrouter"\n',
        "  # Not routed to: a guardrail.\n  # - model_name: free-one\n  #   litellm_params:\n"
        '  #     model: openrouter/vendor/one:free\n  #     litellm_credential_name: "openrouter"\n')
    assert commented_only != miniature
    add("a ready model of a provider with commented-out entries only is refused",
        [item("openrouter", "vendor/b:free", "b-free")], "follows an active entry", base=commented_only)
    add("a date that is no date is refused", READY_ITEMS, "the date is no date", day="2026-11-23\n")
    add("an unknown kind is refused", READY_ITEMS, "neither ready nor to_verify", kind="both")
    add("no item at all is refused", [], "there are no items")
    add("more items than a pull request carries are refused",
        [item("openrouter", "vendor/m%d:free" % number, "m%d-free" % number) for number in range(26)],
        "more than 25")
    add("a base with carriage returns is refused", READY_ITEMS, "plain line feeds", base=real.replace("\n", "\r\n"))
    add("a base without a model list is refused", READY_ITEMS, 'no "model_list:" line',
        base=real.replace("model_list:", "models:"))
    return out


def judge_builder(cases, results, drift):
    """[(name, why)] of the builder scenarios that went wrong, the script's build_additions judged on
    each beside the step's."""
    wrong = []
    for (name, base, date, kind, items, expected), got in zip(cases, results):
        text, problem = drift.build_additions(base, date, kind, items)
        if expected is None:
            if "problem" in got:
                wrong.append((name, "the step refused it: %s" % got["problem"]))
            elif problem is not None:
                wrong.append((name, "the script refused it: %s" % problem))
            elif got["text"] != text:
                wrong.append((name, "the step and the script do not build the same text"))
            elif drift.addition_problem(base, text, items) is not None:
                wrong.append((name, "the file built does not read back: %s"
                              % drift.addition_problem(base, text, items)))
        elif "problem" not in got:
            wrong.append((name, "the step accepted it, and should have refused it (%r)" % expected))
        elif expected not in got["problem"]:
            wrong.append((name, "the step refused it for another reason: %s" % got["problem"]))
        elif problem is None:
            wrong.append((name, "the script accepted what the step refuses"))
    return wrong


def tree_of(text):
    return "tree-" + hashlib.sha1(base64.b64encode(text.encode("utf-8"))).hexdigest()


def tree_of_files(texts):
    """The tree the made-up GitHub gives a commit of these files, written in this order."""
    if len(texts) == 1:
        return tree_of(texts[0])
    return "tree-" + hashlib.sha1("+".join(tree_of(text) for text in texts).encode("utf-8")).hexdigest()


def step_scenarios(real, drift, folder):
    """[(name, scenario, check)]: what the step is given, and a function of what it did that says what
    went wrong, or None. Each scenario's files are written under "folder"."""
    document, step = step_document()
    job_env = document["jobs"]["publish"]["env"]
    branches = {"ready": job_env["ADDITIONS_BRANCH"], "to_verify": job_env["ADDITIONS_TO_VERIFY_BRANCH"]}
    date = "2026-11-23"
    built = {"ready": drift.build_additions(real, date, "ready", READY_ITEMS)[0],
             "to_verify": drift.build_additions(real, date, "to_verify", TO_VERIFY)[0]}
    body = {"ready": "Ajouts prêts.\n\n- [ ] une case\n",
            "to_verify": "À vérifier.\n\n- [ ] **Gratuité.** une case\n- [ ] **Catalogue.** une autre\n"}
    out = []
    count = [0]
    empty_parts = {"ready": {"complete": True, "items": []}, "to_verify": {"complete": True, "items": []}}
    # The catalogue and the figures each proposal is handed with: the step commits them with the template and reads
    # nothing of them but their size, and that the figures are a JSON object.
    catalogs = {"ready": "# Catalogue des ajouts prêts\n", "to_verify": "# Catalogue des ajouts à vérifier\n"}
    figures = {"ready": '{\n "entries": {"a": 1}\n}\n', "to_verify": '{\n "entries": {"b": 2}\n}\n'}
    removal_catalog = "# Catalogue après suppression\n"
    removal_figures = '{\n "entries": {"c": 3}\n}\n'
    files_of_a_commit = ["templates/LiteLLM_config.yaml.j2", "docs/CATALOG.md", "docs/catalog_scores.json"]

    def scenario(name, check, parts=None, refs=None, pulls=None, env=None, files=None, env_files=None,
                 without=(), without_figures=(), **extra):
        count[0] += 1
        where = pathlib.Path(folder) / ("s%d" % count[0])
        where.mkdir()
        parts = {"ready": {"complete": True, "items": READY_ITEMS},
                 "to_verify": {"complete": True, "items": TO_VERIFY}} if parts is None else parts
        (where / "proposals.json").write_text(json.dumps(dict({"date": date}, **parts)), encoding="utf-8")
        for kind in ("ready", "to_verify"):
            if parts.get(kind, {}).get("items"):
                (where / ("%s_template.j2" % kind)).write_text(built[kind], encoding="utf-8")
                if kind not in without:
                    (where / ("%s_catalog.md" % kind)).write_text(catalogs[kind], encoding="utf-8")
                if kind not in without_figures:
                    (where / ("%s_scores.json" % kind)).write_text(figures[kind], encoding="utf-8")
                (where / ("%s_body.md" % kind)).write_text(body[kind], encoding="utf-8")
                (where / ("%s_commit.txt" % kind)).write_text("Propose them\n", encoding="utf-8")
        for name_of, text in (files or {}).items():
            (where / name_of).write_text(text, encoding="utf-8")
        environment = {key: str(value) for key, value in step["env"].items() if "${{" not in str(value)}
        environment.update({key: str(value) for key, value in job_env.items()})
        environment.update(NATIVE_CHECKS="false", DRIFT_STATUS="1", COVERED="complete", ISSUE_OUTCOME="success",
                           CHANGED="false", UNDELETED="0", BASE_SHA=BASE_SHA, PROPOSALS=str(where),
                           PR_BODY=str(where / "none"), COMMIT_MESSAGE=str(where / "none"),
                           TEMPLATE_FILE=str(where / "none"), CATALOG_FILE=str(where / "none"),
                           SCORES_FILE=str(where / "none"))
        environment.update(env or {})
        environment.update(env_files(str(where)) if env_files else {})
        play = {"env": environment, "refs": refs or {}, "pulls": pulls or [], "ancestry": "ahead"}
        play.update(extra)
        out.append((name, play, check))

    def calls(result, name):
        return [call["args"] for call in result["calls"] if call["name"] == name]

    def created(result, branch):
        return [args for args in calls(result, "pulls.create") if args["head"] == branch]

    def first(*checks):
        return next((why for ok, why in checks if not ok), None)

    def pushed(result, branch):
        return [args for args in calls(result, "git.createRef") + calls(result, "git.updateRef")
                if args["ref"].endswith("heads/" + branch)]

    def blob_texts(result):
        return [base64.b64decode(args["content"]).decode("utf-8") for args in calls(result, "git.createBlob")]

    def ours(branch, text, catalog=None, scores=None):
        """A branch the workflow made, holding "text" as the template, "catalog" as the catalogue and "scores" as the
        figures, which are the ones the proposals of its kind come with unless others are given."""
        kind = {branches["ready"]: "ready", branches["to_verify"]: "to_verify"}.get(branch)
        catalog = catalogs.get(kind, removal_catalog) if catalog is None else catalog
        scores = figures.get(kind, removal_figures) if scores is None else scores
        return {branch: {"sha": "head-" + branch, "tree": tree_of_files([text, catalog, scores]), "text": text,
                         "commits": [{"sha": "c1", "author": "github-actions[bot]", "parents": ["p"]}]}}

    def pull(number, branch, text, draft=False):
        kind = {branches["ready"]: "ready", branches["to_verify"]: "to_verify"}.get(branch)
        return {"number": number, "title": titles.get(kind, "x"), "body": text, "draft": draft, "state": "open",
                "head": {"ref": branch}}

    script = step["with"]["script"]
    titles = {"ready": re.search(r"ready: '([^']+)'", script).group(1),
              "to_verify": re.search(r'to_verify: "([^"]+)"', script).group(1)}

    scenario("nothing open yet: both are opened, the one to verify as a draft, and their checks dispatched",
             lambda r: first(
                 (not r["failures"], "it failed: %s" % r["failures"][:1]),
                 (len(created(r, branches["ready"])) == 1 and created(r, branches["ready"])[0]["draft"] is False,
                  "the ready pull request was not opened ready for review"),
                 (len(created(r, branches["to_verify"])) == 1 and created(r, branches["to_verify"])[0]["draft"] is True,
                  "the pull request to verify was not opened as a draft"),
                 (sorted(blob_texts(r)) == sorted(list(built.values()) + list(catalogs.values()) + list(figures.values())),
                  "it pushed another text than the template built and the catalogue and figures handed over"),
                 (all([entry["path"] for entry in args["tree"]] == files_of_a_commit
                      for args in calls(r, "git.createTree")) and len(calls(r, "git.createTree")) == 2,
                  "a commit does not hold the template, the catalogue and the figures, in one tree"),
                 (all(args["parents"] == [BASE_SHA] for args in calls(r, "git.createCommit")),
                  "a commit is not on the commit the other job worked on"),
                 (all("Signed-off-by: github-actions[bot]" in args["message"] for args in calls(r, "git.createCommit")),
                  "a commit is not signed off"),
                 (r["outputs"].get("numbers") == "101 102", "the numbers to assign are %r" % r["outputs"].get("numbers")),
                 (len(calls(r, "actions.createWorkflowDispatch")) == 4, "the checks of both were not dispatched")))
    scenario("with the App's token, no check is dispatched",
             lambda r: first((not calls(r, "actions.createWorkflowDispatch"), "a check was dispatched"),
                             (len(calls(r, "pulls.create")) == 2, "the two were not opened")),
             env={"NATIVE_CHECKS": "true"})
    scenario("a repository that refuses drafts gets the one to verify ready for review, and a warning",
             lambda r: first(
                 (not r["failures"], "it failed: %s" % r["failures"][:1]),
                 ([args["draft"] for args in created(r, branches["to_verify"])] == [True, False],
                  "it did not try a draft, then a pull request ready for review"),
                 (any("refused a draft" in warning for warning in r["warnings"]), "it did not say so")),
             noDrafts=True)
    refs = dict(ours(branches["ready"], built["ready"]), **ours(branches["to_verify"], built["to_verify"]))
    scenario("a run with the same proposals rewrites nothing, and keeps the draft and the ticked boxes",
             lambda r: first(
                 (not r["failures"], "it failed: %s" % r["failures"][:1]),
                 (not calls(r, "git.createCommit") and not pushed(r, branches["ready"]), "a commit was pushed"),
                 (not calls(r, "pulls.update"), "a pull request was updated"),
                 (not calls(r, "pulls.create"), "a pull request was opened")),
             refs=refs, pulls=[pull(7, branches["ready"], body["ready"]),
                               pull(8, branches["to_verify"], body["to_verify"].replace("- [ ] **Gratuité.**", "- [x] **Gratuité.**"), draft=True)])
    stale = dict(ours(branches["ready"], "an older file"), **ours(branches["to_verify"], "an older file"))
    scenario("a run with other proposals moves both branches and rewrites both bodies, keeping a ticked box",
             lambda r: first(
                 (not r["failures"], "it failed: %s" % r["failures"][:1]),
                 (len(calls(r, "git.updateRef")) == 2 and all(args["force"] for args in calls(r, "git.updateRef")),
                  "the branches were not moved"),
                 (not calls(r, "pulls.create"), "a pull request was opened beside the open one"),
                 (any(args["pull_number"] == 8 and "- [x] **Gratuité.** une case" in args.get("body", "")
                      and "- [ ] **Catalogue.** une autre" in args.get("body", "") for args in calls(r, "pulls.update")),
                  "the ticked box was lost, or a box nobody ticked was ticked"),
                 (all("draft" not in args for args in calls(r, "pulls.update")), "an update touched the draft")),
             refs=stale, pulls=[pull(7, branches["ready"], "an older body"),
                                pull(8, branches["to_verify"], "Avant.\n\n- [x] **Gratuité.** une case\n", draft=True)])
    earlier = {kind: drift.build_additions(real, "2026-11-16", kind, items)[0]
               for kind, items in (("ready", READY_ITEMS), ("to_verify", TO_VERIFY))}
    scenario("a later run with the same proposals: the days the entries were proposed are kept, nothing is pushed",
             lambda r: first(
                 (not r["failures"], "it failed: %s" % r["failures"][:1]),
                 (not calls(r, "git.createCommit"), "a commit was made over the days alone"),
                 (not calls(r, "actions.createWorkflowDispatch") or all(
                     args["ref"] in branches.values() for args in calls(r, "actions.createWorkflowDispatch")),
                  "a check was dispatched elsewhere")),
             refs=dict(ours(branches["ready"], earlier["ready"]), **ours(branches["to_verify"], earlier["to_verify"])),
             pulls=[pull(7, branches["ready"], body["ready"]), pull(8, branches["to_verify"], body["to_verify"], True)])
    moved = earlier["ready"].replace("model_list:\n", "model_list:\n# a line main no longer has\n", 1)
    scenario("a branch whose other lines differ is built again, with this run's days",
             lambda r: first(
                 (blob_texts(r) == [built["ready"], catalogs["ready"], figures["ready"]],
                  "it did not push the new build: %d blob(s)" % len(blob_texts(r))),
                 (len(pushed(r, branches["ready"])) == 1, "the branch was not moved")),
             parts={"ready": {"complete": True, "items": READY_ITEMS}, "to_verify": {"complete": True, "items": []}},
             refs=ours(branches["ready"], moved), pulls=[pull(7, branches["ready"], body["ready"])])
    dated = real.replace("model_list:\n", "model_list:\n  # Proposed by the drift run on 2026-11-23: x\n", 1)
    scenario("a day on a line the base holds is no day of a proposal: the branch is built again",
             lambda r: first((len(pushed(r, branches["ready"])) == 1, "a base line was taken for a proposal's")),
             parts={"ready": {"complete": True, "items": READY_ITEMS}, "to_verify": {"complete": True, "items": []}},
             refs=ours(branches["ready"], built["ready"].replace(
                 "model_list:\n", "model_list:\n  # Proposed by the drift run on 2026-11-16: x\n", 1)),
             pulls=[pull(7, branches["ready"], body["ready"])], baseText=dated,
             files={"ready_template.j2": drift.build_additions(dated, date, "ready", READY_ITEMS)[0]})
    # An entry merged from a proposal of the same day and source carries the very line a new
    # proposal's comment is: the base holding it must not make that comment a line of the base.
    note = next(line for line in built["ready"].split("\n") if line.startswith("  # Proposed by") and date in line)
    merged = real.replace("model_list:\n", "model_list:\n%s\n" % note, 1)
    scenario("a proposal's day on a line the base holds too, from an entry merged that day: nothing is pushed",
             lambda r: first(
                 (not r["failures"], "it failed: %s" % r["failures"][:1]),
                 (not calls(r, "git.createCommit"), "a commit was made over the days alone")),
             parts={"ready": {"complete": True, "items": READY_ITEMS}, "to_verify": {"complete": True, "items": []}},
             refs=ours(branches["ready"], drift.build_additions(merged, "2026-11-16", "ready", READY_ITEMS)[0]),
             pulls=[pull(7, branches["ready"], body["ready"])], baseText=merged,
             files={"ready_template.j2": drift.build_additions(merged, date, "ready", READY_ITEMS)[0]})
    empty = {"ready": {"complete": True, "items": []}, "to_verify": {"complete": True, "items": []}}
    scenario("nothing left to propose, every catalogue read: both are closed, with a comment",
             lambda r: first(
                 (sorted(args["pull_number"] for args in calls(r, "pulls.update") if args.get("state") == "closed") == [7, 8],
                  "they were not both closed"),
                 (len(calls(r, "issues.createComment")) == 2, "no comment says why"),
                 (not calls(r, "git.createCommit"), "something was pushed")),
             parts=empty, refs=refs, pulls=[pull(7, branches["ready"], "b"), pull(8, branches["to_verify"], "b", True)])
    partial = {"ready": {"complete": True, "items": []}, "to_verify": {"complete": False, "items": []}}
    scenario("nothing left to propose but a catalogue not read: the one that draws on it stays open",
             lambda r: first(
                 ([args["pull_number"] for args in calls(r, "pulls.update") if args.get("state") == "closed"] == [7],
                  "the wrong pull requests were closed: %r" % calls(r, "pulls.update"))),
             parts=partial, refs=refs, pulls=[pull(7, branches["ready"], "b"), pull(8, branches["to_verify"], "b", True)])
    for env, why in (({"DRIFT_STATUS": "2"}, "a provider could not be read"),
                     ({"ISSUE_OUTCOME": "failure"}, "the report was not trusted")):
        scenario("nothing left to propose, but %s: both stay open" % why,
                 lambda r: first((not calls(r, "pulls.update") and not calls(r, "issues.createComment"),
                                  "a pull request was closed")),
                 parts=empty, refs=refs, pulls=[pull(7, branches["ready"], "b"), pull(8, branches["to_verify"], "b", True)],
                 env=env)
    scenario("a status the step does not know: nothing is closed",
             lambda r: first((not calls(r, "pulls.update") and not calls(r, "issues.createComment"), "it closed one"),
                             (any("does not know" in failure for failure in r["failures"]), "it did not fail")),
             parts=empty, refs=refs, pulls=[pull(7, branches["ready"], "b"), pull(8, branches["to_verify"], "b", True)],
             env={"DRIFT_STATUS": "9"})
    scenario("nothing to propose and nothing open: nothing is done",
             lambda r: first((not [c for c in r["calls"] if c["name"] != "pulls.list"], "something was done"),
                             (not r["failures"], "it failed")),
             parts=empty)
    person = {branches["ready"]: {"sha": "head-v", "tree": "t", "commits": [
        {"sha": "c1", "author": "github-actions[bot]", "parents": ["p"]},
        {"sha": "c2", "author": "Somebody", "parents": ["c1"]}]}}
    scenario("a person's commit on a branch whose pull request is open: left as it is, and no failure",
             lambda r: first(
                 (not pushed(r, branches["ready"]), "the person's branch was overwritten"),
                 (not [a for a in calls(r, "pulls.update") if a["pull_number"] == 7], "their pull request was touched"),
                 (not r["failures"], "it failed: %s" % r["failures"][:1]),
                 (len(created(r, branches["to_verify"])) == 1, "the other one was not opened")),
             refs=person, pulls=[pull(7, branches["ready"], "b")])
    scenario("a person's commit on a branch with no pull request open: the step fails and pushes nothing there",
             lambda r: first(
                 (not pushed(r, branches["ready"]), "the person's branch was overwritten"),
                 (any("delete the branch" in failure for failure in r["failures"]), "it did not fail to say so"),
                 (len(created(r, branches["to_verify"])) == 1, "the other one was not opened")),
             refs=person)
    scenario("a person's commit, nothing left to propose: the open pull request is not closed",
             lambda r: first((not calls(r, "issues.createComment"), "it was closed")),
             parts=empty, refs=person, pulls=[pull(7, branches["ready"], "b")])
    scenario("the script's template differs from the one built here: nothing is pushed",
             lambda r: first(
                 (not pushed(r, branches["ready"]) and not created(r, branches["ready"]), "it was pushed"),
                 (any("is not the one the drift check built" in failure for failure in r["failures"]), "it did not fail")),
             files={"ready_template.j2": built["ready"] + "\n  # one line more\n"})
    hostile = {"ready": {"complete": True, "items": [item("openrouter", "vendor/x:free\n- evil", "x-free")]},
               "to_verify": {"complete": True, "items": TO_VERIFY}}
    scenario("an item spelt otherwise: nothing is pushed for its pull request, the other one is opened",
             lambda r: first(
                 (not pushed(r, branches["ready"]), "it was pushed"),
                 (any("are refused" in failure for failure in r["failures"]), "it did not fail"),
                 (len(created(r, branches["to_verify"])) == 1, "the other one was not opened")),
             parts=hostile)
    for shape, parts in (("no part to verify", {"ready": {"complete": True, "items": READY_ITEMS}}),
                         ("a coverage that is no boolean",
                          {"ready": {"complete": "yes", "items": READY_ITEMS},
                           "to_verify": {"complete": True, "items": TO_VERIFY}})):
        scenario("proposals of another shape (%s) are refused" % shape,
                 lambda r: first((any("The proposals are refused" in failure for failure in r["failures"]),
                                  "it did not fail")),
                 parts=parts)
    scenario("the deletions fail, and the additions are still done",
             lambda r: first(
                 (any("the deletion pull request" in failure for failure in r["failures"]), "the failure is not said"),
                 (len(calls(r, "pulls.create")) == 2, "the additions were not opened")),
             broken=job_env["REMOVALS_BRANCH"])
    # The deletions share the step's code since the additions came: they are played too.
    removals_branch = job_env["REMOVALS_BRANCH"]
    deleted = real.replace("\n".join(real.split("\n")[real.split("\n").index("  - model_name: gemma-4-26b-gemini"):][:5])
                           + "\n", "", 1)
    removal_files = {"removed.j2": deleted, "removal_body.md": "Suppressions.\n", "removal_commit.txt": "Delete\n",
                     "removed_catalog.md": removal_catalog, "removed_scores.json": removal_figures}

    def removal_env(where_files):
        return {"CHANGED": "true", "TEMPLATE_FILE": where_files + "/removed.j2",
                "CATALOG_FILE": where_files + "/removed_catalog.md", "SCORES_FILE": where_files + "/removed_scores.json",
                "PR_BODY": where_files + "/removal_body.md", "COMMIT_MESSAGE": where_files + "/removal_commit.txt"}

    scenario("the deletions: a template with lines deleted is pushed, and its pull request opened ready for review",
             lambda r: first(
                 (not r["failures"], "it failed: %s" % r["failures"][:1]),
                 (blob_texts(r) == [deleted, removal_catalog, removal_figures],
                  "it pushed another text than the template, its catalogue and its figures"),
                 ([[entry["path"] for entry in args["tree"]] for args in calls(r, "git.createTree")]
                  == [files_of_a_commit], "the commit does not hold the template, the catalogue and the figures, in one tree"),
                 ([args["draft"] for args in created(r, removals_branch)] == [False], "it was not opened ready"),
                 (r["outputs"].get("numbers") == "101", "the number to assign is %r" % r["outputs"].get("numbers"))),
             parts=empty_parts, files=removal_files, env_files=removal_env)
    scenario("the deletions: a template with a line added is not pushed",
             lambda r: first((not calls(r, "git.createCommit"), "it was pushed"),
                             (any("nothing is pushed" in failure for failure in r["failures"]), "it did not fail")),
             parts=empty_parts, files=dict(removal_files, **{"removed.j2": deleted + "  # added\n"}),
             env_files=removal_env)
    scenario("the deletions: a person's commit fails the step, and nothing is touched",
             lambda r: first((not calls(r, "git.createCommit") and not calls(r, "pulls.update"), "it was touched"),
                             (any("Delete the branch" in failure for failure in r["failures"]), "it did not fail")),
             parts=empty_parts, files=removal_files, env_files=removal_env,
             refs={removals_branch: {"sha": "head-r", "tree": "t", "text": real, "commits": [
                 {"sha": "c9", "author": "Somebody", "parents": ["p"]}]}},
             pulls=[pull(9, removals_branch, "b")])
    scenario("the deletions: nothing left to delete, every catalogue read: closed with a comment",
             lambda r: first(([args["pull_number"] for args in calls(r, "pulls.update") if args.get("state") == "closed"]
                              == [9], "it was not closed")),
             parts=empty_parts, pulls=[pull(9, removals_branch, "b")],
             refs={removals_branch: {"sha": "head-r", "tree": "t", "text": real, "commits": [
                 {"sha": "c9", "author": "github-actions[bot]", "parents": ["p"]}]}})
    scenario("the deletions: a catalogue that is empty is not pushed, and nothing is opened",
             lambda r: first((not calls(r, "git.createCommit"), "it was pushed"),
                             (not calls(r, "pulls.create"), "a pull request was opened"),
                             (any("catalogue the other job handed over is refused" in failure for failure in r["failures"]),
                              "it did not fail")),
             parts=empty_parts, files=dict(removal_files, **{"removed_catalog.md": ""}), env_files=removal_env)
    scenario("the deletions: a catalogue larger than a catalogue is is not pushed",
             lambda r: first((not calls(r, "git.createCommit"), "it was pushed"),
                             (any("longer than" in failure for failure in r["failures"]), "it did not fail")),
             parts=empty_parts, files=dict(removal_files, **{"removed_catalog.md": "x" * 1000001}),
             env_files=removal_env)
    scenario("the deletions: a template handed over with no catalogue is not pushed",
             lambda r: first((not calls(r, "git.createCommit"), "it was pushed"),
                             (any("the deletion pull request" in failure for failure in r["failures"]), "it did not fail")),
             parts=empty_parts, files=removal_files,
             env_files=lambda where_files: dict(removal_env(where_files), CATALOG_FILE=where_files + "/missing.md"))
    scenario("the deletions: a branch whose catalogue is the old one is moved, whatever its template",
             lambda r: first((len(pushed(r, removals_branch)) == 1, "the branch was not moved"),
                             (blob_texts(r) == [deleted, removal_catalog, removal_figures], "it pushed another text")),
             parts=empty_parts, files=removal_files, env_files=removal_env,
             refs=ours(removals_branch, deleted, "# Catalogue avant\n"), pulls=[pull(9, removals_branch, "b")])
    scenario("the deletions: a branch whose figures are the old ones is moved, whatever its template and catalogue",
             lambda r: first((len(pushed(r, removals_branch)) == 1, "the branch was not moved"),
                             (blob_texts(r) == [deleted, removal_catalog, removal_figures], "it pushed another text")),
             parts=empty_parts, files=removal_files, env_files=removal_env,
             refs=ours(removals_branch, deleted, scores='{\n "entries": {}\n}\n'), pulls=[pull(9, removals_branch, "b")])
    scenario("the deletions: a branch that holds the template, the catalogue and the figures is left as it is",
             lambda r: first((not calls(r, "git.createCommit"), "a commit was made")),
             parts=empty_parts, files=removal_files, env_files=removal_env,
             refs=ours(removals_branch, deleted), pulls=[pull(9, removals_branch, "Suppressions.\n")])
    scenario("a proposal handed no catalogue: nothing is pushed for it, the other one is opened",
             lambda r: first(
                 (not pushed(r, branches["ready"]) and not created(r, branches["ready"]), "it was pushed"),
                 (any("without the files that go with them" in failure for failure in r["failures"]), "it did not fail"),
                 (len(created(r, branches["to_verify"])) == 1, "the other one was not opened")),
             without=("ready",))
    scenario("a proposal's catalogue that is empty: nothing is pushed for it",
             lambda r: first(
                 (not pushed(r, branches["ready"]) and not created(r, branches["ready"]), "it was pushed"),
                 (any("catalogue handed over for" in failure for failure in r["failures"]), "it did not fail"),
                 (len(created(r, branches["to_verify"])) == 1, "the other one was not opened")),
             files={"ready_catalog.md": ""})
    scenario("a proposal's catalogue larger than a catalogue is: nothing is pushed for it",
             lambda r: first(
                 (not pushed(r, branches["ready"]) and not created(r, branches["ready"]), "it was pushed"),
                 (any("longer than" in failure for failure in r["failures"]), "it did not fail")),
             files={"ready_catalog.md": "x" * 1000001})
    scenario("a branch with the template of the build and a stale catalogue is moved",
             lambda r: first(
                 (len(pushed(r, branches["ready"])) == 1, "the branch was not moved"),
                 (blob_texts(r) == [built["ready"], catalogs["ready"], figures["ready"]], "it pushed another text")),
             parts={"ready": {"complete": True, "items": READY_ITEMS}, "to_verify": {"complete": True, "items": []}},
             refs=ours(branches["ready"], built["ready"], "# Catalogue d'hier\n"),
             pulls=[pull(7, branches["ready"], body["ready"])])
    scenario("a branch with the template of the build and the figures of yesterday is moved",
             lambda r: first(
                 (len(pushed(r, branches["ready"])) == 1, "the branch was not moved"),
                 (blob_texts(r) == [built["ready"], catalogs["ready"], figures["ready"]], "it pushed another text")),
             parts={"ready": {"complete": True, "items": READY_ITEMS}, "to_verify": {"complete": True, "items": []}},
             refs=ours(branches["ready"], built["ready"], scores='{\n "entries": {}\n}\n'),
             pulls=[pull(7, branches["ready"], body["ready"])])
    # The figures file is bounded as a catalogue is, and must be a JSON object; its shape is the generator's.
    for what, text in (("empty", ""), ("larger than a figures file is", "x" * 1000001), ("not JSON", "not json"),
                       ("an array", "[1]"), ("null", "null")):
        scenario("the deletions: figures that are %s are not pushed, and nothing is opened" % what,
                 lambda r: first((not calls(r, "git.createCommit"), "it was pushed"),
                                 (not calls(r, "pulls.create"), "a pull request was opened"),
                                 (any("figures file the other job handed over is refused" in failure
                                      for failure in r["failures"]), "it did not fail")),
                 parts=empty_parts, files=dict(removal_files, **{"removed_scores.json": text}), env_files=removal_env)
        scenario("a proposal's figures that are %s: nothing is pushed for it, the other one is opened" % what,
                 lambda r: first(
                     (not pushed(r, branches["ready"]) and not created(r, branches["ready"]), "it was pushed"),
                     (any("figures file handed over for" in failure for failure in r["failures"]), "it did not fail"),
                     (len(created(r, branches["to_verify"])) == 1, "the other one was not opened")),
                 files={"ready_scores.json": text})
    scenario("the deletions: a template handed over with no figures is not pushed",
             lambda r: first((not calls(r, "git.createCommit"), "it was pushed"),
                             (any("the deletion pull request" in failure for failure in r["failures"]), "it did not fail")),
             parts=empty_parts, files=removal_files,
             env_files=lambda where_files: dict(removal_env(where_files), SCORES_FILE=where_files + "/missing.json"))
    scenario("a proposal handed no figures: nothing is pushed for it, the other one is opened",
             lambda r: first(
                 (not pushed(r, branches["ready"]) and not created(r, branches["ready"]), "it was pushed"),
                 (any("without the files that go with them" in failure for failure in r["failures"]), "it did not fail"),
                 (len(created(r, branches["to_verify"])) == 1, "the other one was not opened")),
             without_figures=("ready",))
    scenario("a commit of the other job that is not on main: nothing is pushed",
             lambda r: first((not calls(r, "git.createCommit"), "a commit was made"),
                             (any("is not on main" in failure for failure in r["failures"]), "it did not fail")),
             ancestry="diverged")
    return out


def judge_step(cases, results):
    wrong = []
    for (name, _scenario, check), got in zip(cases, results):
        if got["crashed"]:
            wrong.append((name, "the script threw: %s" % got["crashed"].splitlines()[0]))
            continue
        why = check(got)
        if why:
            wrong.append((name, why))
    return wrong


# The tables of the workflow that name the providers, and how to read the names off each: a provider the
# script reads and a table lacks only fails on the day it is needed, an unreadable catalogue or an addition.
PROVIDER_TABLES = {
    "issue": (r"const PROVIDERS = \{(.*?)\};", r"\b([a-z]+):\s*'"),
    "additions": (r"const ADDITION_PROVIDERS = \{(.*?)\n\};", r"^\s+([a-z]+): \{"),
}


def table_problem(script, which, drift):
    """Why the table of "which" ("issue" or "additions") in the step's "script" does not name exactly the
    providers the drift script reads, or None."""
    block, name = PROVIDER_TABLES[which]
    found = re.search(block, script, re.S)
    if not found:
        return "the table of providers of the %s step is not where this reads it" % which
    named = re.findall(name, found.group(1), re.M)
    if sorted(named) != sorted(drift.PROVIDER_NAMES):
        return "the %s step names %s, and the drift script reads %s" % (
            which, ", ".join(sorted(named)), ", ".join(sorted(drift.PROVIDER_NAMES)))
    return None


def additions_cases():
    real = TEMPLATE.read_text(encoding="utf-8")
    drift = drift_module()
    return real, drift, builder_scenarios(real, drift)


def play_builder(builder, cases):
    payload = {"builder": builder, "cases": [{"base": base, "date": date, "kind": kind, "items": items}
                                             for _, base, date, kind, items, _ in cases]}
    results = node(BUILDER_HARNESS, payload)
    if len(results) != len(cases):
        raise SystemExit("node answered %d builder scenario(s) out of %d." % (len(results), len(cases)))
    return results


def play_step(script, real, cases):
    payload = {"script": script, "base": BASE_SHA, "baseText": real,
               "scenarios": [scenario for _, scenario, _ in cases]}
    results = node(STEP_HARNESS, payload)
    if len(results) != len(cases):
        raise SystemExit("node answered %d step scenario(s) out of %d." % (len(results), len(cases)))
    return results


def additions_wrong(script=None, builder=None):
    """[(name, why)] of every addition scenario that went wrong, for the step's script and builder as they
    are, or as given."""
    real, drift, cases = additions_cases()
    if builder is None:
        builder = load_builder()
    if script is None:
        script = step_document()[1]["with"]["script"]
    wrong = judge_builder(cases, play_builder(builder, cases), drift)
    problem = table_problem(script, "additions", drift)
    if problem:
        wrong.append(("the providers of the additions are the ones the script reads", problem))
    with tempfile.TemporaryDirectory() as folder:
        steps = step_scenarios(real, drift, folder)
        wrong += judge_step(steps, play_step(script, real, steps))
    return wrong, len(cases)


# Breaks of the builder and of the step, one at a time: (what stops being done, text, replacement).
ADDITION_MUTATIONS = [
    ("refuse an id spelt otherwise", "!ADDITION_ID.test(id)", "false"),
    ("anchor the id at its end", "[A-Za-z0-9]$/;\n", "[A-Za-z0-9]/;\n"),
    ("refuse two colons in an id", "(?!.*(?:::|\\/\\/))", "(?!.*(?:\\/\\/))"),
    ("refuse a name spelt otherwise", "!ADDITION_NAME.test(name)", "false"),
    ("cap the length of a name", "name.length > 80 ||", ""),
    ("refuse a name that is a word of the template", "words.has(name) ||", ""),
    ("refuse two items of one name", "|| names.has(name)", ""),
    ("refuse a provider this does not read", "!Object.hasOwn(ADDITION_PROVIDERS, provider)",
     "!(provider in ADDITION_PROVIDERS)"),
    ("keep a ready addition to a provider whose API states its free tier", "if (kind === 'ready' && spec.free === undefined)",
     "if (false)"),
    ("keep a ready addition active", "if (kind === 'ready' && anchor.commented)", "if (false)"),
    ("ask an id of such a provider for its suffix, where it has one", "spec.freeSuffix !== undefined && !id.endsWith(spec.freeSuffix)", "false"),
    ("refuse an item of another shape",
     "!['id,name,provider', 'id,name,provider,usage'].includes(Object.keys(item).sort().join(','))", "false"),
    ("refuse a usage the template has no mode for", "!Object.hasOwn(ADDITION_USAGES, item.usage)", "false"),
    ("write the mode of a typed entry", "if (usage) block.push(`${lead}    mode: ${usage.mode}`);", ""),
    ("write a typed entry in the group of its usage", "spec.group ?? (usage ? usage.group : 'LLM')", "spec.group ?? 'LLM'"),
    ("model a typed entry on the last entry of its mode",
     "const anchor = same.length > 0 ? lastOf(same) : lastOf(modeless.length > 0 ? modeless : usable);",
     "const anchor = lastOf(usable);"),
    ("model a text entry on an entry of no mode first", "lastOf(modeless.length > 0 ? modeless : usable)", "lastOf(usable)"),
    ("write Cloudflare's embeddings through its OpenAI-compatible endpoint",
     "const prefix = embedsThroughEnv ? 'openai/' : spec.prefix;", "const prefix = spec.prefix;"),
    ("refuse an embedding of Cloudflare with no entry to read its base from",
     "!Object.hasOwn(ADDITION_ENV_BASES, envBase)", "false"),
    ("attribute the entries whose base is read from the environment to Cloudflare",
     "Object.hasOwn(ADDITION_ENV_BASES, apiBase)) return ADDITION_ENV_BASES[apiBase];", "false) return null;"),
    ("refuse a provider that the router of the mode does not route to",
     "if (providers !== undefined && !providers.includes(provider)) return `", "if (false) return `"),
    ("give an entry a slot at the tail of its router", "if (tail !== null) slotsBefore.set(tail, written);", ""),
    ("write a slot under the key of its provider",
     "return [`{% if ${condition} %}`, `        - ${name}`, '{% endif %}'];", "return [`        - ${name}`];"),
    ("write a slot inside the block that closes the cascade", "if (depth === 0) return index;", "if (depth === 99) return index;"),
    ("refuse a cascade with an else branch", r"if (/^\{%-?\s*(else|elif)\b.*%\}$/.test(line)) return -1;", ""),
    ("give an embedding no slot", "chat: 'flash-lite', speech: 'tts'", "chat: 'flash-lite', embeddings: 'flash-lite', speech: 'tts'"),
    ("give Aion Labs' text models the slot of their own router", "if (provider === 'aionlabs') return usage === 'chat' ? 'fiction' : null;", ""),
    ("write a slot only for an active entry", "if (!anchor.commented) {\n      const refusal", "if (true) {\n      const refusal"),
    ("refuse an id already an entry", "if (known.has(prefix + id))", "if (false)"),
    ("refuse an id set aside by drift-ignore", "if (ignored.has(`${provider}/${id}`))", "if (false)"),
    ("model an entry on a credential", "!ADDITION_CREDENTIAL.test(credential)", "false"),
    ("model a keyless gateway's entry on a plain marker", "!ADDITION_MARKER.test(key)", "false"),
    ("blank the Authorization header of a keyless gateway's entry", "if (spec.keyless) block.push(", "if (false) block.push("),
    ("attribute the entries served through Kilo's gateway to it", "apiBase.includes('ai-gateway.kilo.ai')) return 'kilo';",
     "apiBase.includes('ai-gateway.kilo.ai')) return null;"),
    ("attribute the entries served through OVHcloud to it",
     "apiBase.includes('oai.endpoints.kepler.ai.cloud.ovh.net')) return 'ovhcloud';",
     "apiBase.includes('oai.endpoints.kepler.ai.cloud.ovh.net')) return null;"),
    ("attribute the entries served through Requesty to it", "apiBase.includes('requesty.ai')) return 'requesty';",
     "apiBase.includes('requesty.ai')) return null;"),
    ("blank the Authorization header of OVHcloud's entries", "label: 'OVHcloud', keyless: true", "label: 'OVHcloud'"),
    ("state Requesty's free tier from its catalogue", "label: 'Requesty', free: 'router.eu.requesty.ai/v1/models'",
     "label: 'Requesty'"),
    ("attribute the entries served through Aion Labs' endpoint to it", "apiBase.includes('api.aionlabs.ai')) return 'aionlabs';",
     "apiBase.includes('api.aionlabs.ai')) return null;"),
    ("write the entry of a provider kept out of LLM in the group of its own",
     "[\"${spec.group ?? (usage ? usage.group : 'LLM')}\", \"${spec.data}\"]",
     "[\"${usage ? usage.group : 'LLM'}\", \"${spec.data}\"]"),
    ("write the entry of a usage in the group of its own",
     "[\"${spec.group ?? (usage ? usage.group : 'LLM')}\", \"${spec.data}\"]",
     "[\"${spec.group ?? 'LLM'}\", \"${spec.data}\"]"),
    ("write the entry of a provider in the data group of its own",
     "[\"${spec.group ?? (usage ? usage.group : 'LLM')}\", \"${spec.data}\"]",
     "[\"${spec.group ?? (usage ? usage.group : 'LLM')}\", \"Public-Data-Only\"]"),
    ("write the data group after the type group",
     "[\"${spec.group ?? (usage ? usage.group : 'LLM')}\", \"${spec.data}\"]",
     "[\"${spec.data}\", \"${spec.group ?? (usage ? usage.group : 'LLM')}\"]"),
    ("name every provider the script reads in the table of additions",
     "  kilo: { prefix: 'openai/', label: 'Kilo Gateway', free: 'ai-gateway.kilo.ai/api/v1/models', keyless: true, data: 'Public-Data-Only' },\n", ""),
    ("model an entry on an https base", "apiBase !== undefined && !ADDITION_BASE.test(apiBase)", "false"),
    ("follow the last active entry first", "find((entry) => !entry.commented)", "find(() => false)"),
    ("follow a commented-out entry after its run", "while (commented && at < end", "while (false && at < end"),
    ("refuse a date that is no date", "!ADDITION_DATE.test(date)", "false"),
    ("cap the number of items", "|| items.length > ADDITION_LIMIT", ""),
    ("refuse carriage returns", "|| baseText.includes('\\r')", ""),
    ("push only the text the script built too", "if (handed !== built.text) {", "if (false) {"),
    ("commit the catalogue and the figures of an addition with its template",
     "[[template, content], [catalog, handedCatalog], [scores, handedScores]]", "[[template, content]]"),
    ("commit the figures of an addition with its template",
     "[[template, content], [catalog, handedCatalog], [scores, handedScores]]",
     "[[template, content], [catalog, handedCatalog]]"),
    ("commit the catalogue and the figures of the deletions with their template",
     "[[template, content], [catalog, catalogText], [scores, scoresText]]", "[[template, content]]"),
    ("commit the figures of the deletions with their template",
     "[[template, content], [catalog, catalogText], [scores, scoresText]]",
     "[[template, content], [catalog, catalogText]]"),
    ("read the figures each proposal is handed with", "fs.readFileSync(`${folder}/${kind}_scores.json`, 'utf8')", "''"),
    ("refuse figures that are not JSON", "JSON.parse(text);", "{};"),
    ("refuse figures that are not an object", "parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)",
     "false"),
    ("refuse the figures of an addition that are refused", "const scoresFlaw = scoresProblem(handedScores);",
     "const scoresFlaw = null;"),
    ("refuse the figures of the deletions that are refused", "const scoresFlaw = scoresProblem(scoresText);",
     "const scoresFlaw = null;"),
    ("read the catalogue each proposal is handed with", "fs.readFileSync(`${folder}/${kind}_catalog.md`, 'utf8')",
     "''"),
    ("refuse a catalogue that is empty", "text.length === 0", "false"),
    ("refuse a catalogue larger than a catalogue is", "Buffer.byteLength(text, 'utf8') > CATALOG_MAX_BYTES",
     "false"),
    ("refuse the catalogue of an addition that is refused", "const catalogFlaw = catalogProblem(handedCatalog);",
     "const catalogFlaw = null;"),
    ("refuse the catalogue of the deletions that is refused", "const catalogFlaw = catalogProblem(catalogText);",
     "const catalogFlaw = null;"),
    ("write both files in one tree", "owner, repo, base_tree: baseCommit.tree.sha, tree: entries,",
     "owner, repo, base_tree: baseCommit.tree.sha, tree: entries.slice(0, 1),"),
    ("open the one to verify as a draft", "branch: process.env.ADDITIONS_TO_VERIFY_BRANCH, draft: true",
     "branch: process.env.ADDITIONS_TO_VERIFY_BRANCH, draft: false"),
    ("keep the title", "title: ADDITION_TITLES[kind],", "title: 'x',"),
    ("fall back on a pull request ready for review when drafts are refused",
     "if (!draft || error.status !== 422 || !/draft/i.test(error.message)) throw error;", "throw error;"),
    ("rewrite a body only when it changed", "if (existing.title !== title || !same(existing.body, body)) {", "if (true) {"),
    ("keep a ticked box", "body: keepTicks(body, existing?.body),", "body,"),
    ("leave a pull request a person is working on", "if (foreign && existing)", "if (false)"),
    ("close only when every catalogue the kind draws on was read", "|| !part.complete ||", "||"),
    ("close only on a trusted report", "!part.complete || process.env.ISSUE_OUTCOME !== 'success'", "!part.complete"),
    ("keep open when a provider could not be read", "if (status === '2' || !part.complete", "if (!part.complete"),
    ("hand the numbers to the step that assigns", "numbers.push(pr.number);", ""),
    ("do the additions when the deletions fail", "core.setFailed(`${what}: ${error.message}`);", "throw error;"),
    ("refuse proposals of another shape", "typeof part.complete !== 'boolean' ||", ""),
    ("open the deletions ready for review", "{ title, body, existing, draft: false }", "{ title, body, existing, draft: true }"),
    ("push the deletions only when the template is the base with lines deleted",
     "const problem = templateProblem(Buffer.from(original.content, 'base64').toString('utf8'), content.toString('utf8'));",
     "const problem = null;"),
    ("leave the deletions of a person's branch alone", "core.setFailed(`${branch} holds ${foreign}, so neither",
     "if (false) core.setFailed(`${branch} holds ${foreign}, so neither"),
    ("refuse a status it does not know", "if (!['0', '1', '2'].includes(status)) {\n", "if (false) {\n"),
    ("build on main only", "if (!['ahead', 'identical'].includes(ancestry.status))", "if (false)"),
    ("keep a branch whose days alone differ", "kept !== null && onlyDaysDiffer(kept, built) ? kept : built.text",
     "built.text"),
    ("keep only where the days alone differ", "keptLines.length === builtLines.length && keptLines.every(", "true || ("),
    ("tell a proposal's day from a line of the base", "(notes.has(index) &&", "(true &&"),
]


def run_additions_selftest():
    wrong, _ = additions_wrong()
    if wrong:
        print("the additions fail their own scenarios before anything is broken:")
        for name, why in wrong:
            print("  %s: %s" % (name, why))
        return 1
    script = step_document()[1]["with"]["script"]
    failures = 0
    for label, old, new in ADDITION_MUTATIONS:
        if script.count(old) != 1:
            failures += 1
            print("selftest: the text of the step that should %s has moved: %r" % (label, old))
            continue
        broken = script.replace(old, new, 1)
        builder = broken.split(BUILDER_BEGIN, 1)[1].split(BUILDER_END, 1)[0]
        try:
            noticed = bool(additions_wrong(broken, builder)[0])
        except SystemExit as error:
            failures += 1
            print("selftest: breaking the step that should %s left a script that does not run: %s"
                  % (label, str(error)[:200]))
            continue
        if noticed:
            print("selftest: ok -- some scenario notices a step that stops: %s" % label)
        else:
            failures += 1
            print("selftest: FAILED -- no scenario notices a step that stops: %s" % label)
    if failures:
        return 1
    print("check_drift_publish_guard selftest: the additions as expected, %d broken guard(s) of the "
          "builder and the step noticed." % len(ADDITION_MUTATIONS))
    return 0


# ---------------------------------------------------------------------------------------------------
# The gate that decides whether an attempt runs, and the step that keeps the issue
# ---------------------------------------------------------------------------------------------------

GATE_STEP = "Find what the earlier attempts of the day ended with"
ISSUE_STEP = "Open, update or close the issue of the unreadable catalogues"
LEGACY_TITLE = "Dérive de la liste de modèles LiteLLM"
MARKER = "<!-- LiteLLM-model-drift -->"
DAY = "2026-11-25"
SCHEDULES = ["17 4 * * *", "17 6 * * *", "17 8 * * *"]

# Plays one step's script against a made-up GitHub that knows runs, their artifacts and issues. It
# filters nothing the real API would filter for the script ("event", "created"), so that the filters
# the script applies itself are what is tested.
ACTIONS_HARNESS = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

async function play(scenario) {
  const run = new AsyncFunction('github', 'context', 'core', 'process', 'require', input.script);
  const calls = [];
  const notices = [];
  const warnings = [];
  const failures = [];
  const outputs = {};
  const record = (name, args) => calls.push({ name, args });
  let next = 500;
  const github = {
    paginate: async (method, args) => (await method(args)).data,
    rest: {
      actions: {
        getWorkflowRun: async (args) => {
          record('actions.getWorkflowRun', args);
          return { data: scenario.runs.find((each) => each.id === args.run_id) };
        },
        listWorkflowRuns: async (args) => {
          record('actions.listWorkflowRuns', args);
          return { data: { workflow_runs: scenario.runs.filter((each) => each.workflow_id === args.workflow_id) } };
        },
        listWorkflowRunArtifacts: async (args) => {
          record('actions.listWorkflowRunArtifacts', args);
          return { data: { artifacts: (scenario.artifacts[String(args.run_id)] ?? []).map((name) => ({ name })) } };
        },
      },
      issues: {
        listForRepo: async (args) => { record('issues.listForRepo', args); return { data: scenario.issues }; },
        create: async (args) => { record('issues.create', args); return { data: { number: next++ } }; },
        update: async (args) => { record('issues.update', args); return { data: {} }; },
        addAssignees: async (args) => { record('issues.addAssignees', args); return { data: {} }; },
        createComment: async (args) => { record('issues.createComment', args); return { data: {} }; },
      },
    },
  };
  const core = {
    notice: (message) => notices.push(String(message)),
    warning: (message) => warnings.push(String(message)),
    error: (message) => failures.push(String(message)),
    setFailed: (message) => failures.push(String(message)),
    setOutput: (name, value) => { outputs[name] = value; },
  };
  const context = Object.assign({ repo: { owner: 'o', repo: 'r' }, serverUrl: 'https://github.com', runId: 4 },
                                scenario.context);
  let crashed = null;
  try {
    await run(github, context, core, { env: scenario.env }, require);
  } catch (error) {
    crashed = String(error && error.stack || error);
  }
  return { calls, notices, warnings, failures, outputs, crashed };
}

(async () => {
  const out = [];
  for (const scenario of input.scenarios) out.push(await play(scenario));
  process.stdout.write(JSON.stringify(out));
})();
"""


def named_step(job, name):
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    step = next((step for step in document["jobs"][job]["steps"] if step.get("name") == name), None)
    if step is None:
        raise SystemExit("the step %r is not in the job %r of %s" % (name, job, WORKFLOW.name))
    return document, step


def schedule_problem(document):
    """Why the gate would number the attempts wrongly, or None: its SCHEDULES must be the crons of
    "on.schedule", in their order, and the day's last attempt the last of them."""
    on = document.get("on", document.get(True)) or {}
    crons = [entry.get("cron") for entry in on.get("schedule") or []]
    gate = next((step for step in document["jobs"]["gate"]["steps"] if step.get("name") == GATE_STEP), None)
    if gate is None:
        return "the gate has no step %r" % GATE_STEP
    listed = [line.strip() for line in gate["env"]["SCHEDULES"].splitlines() if line.strip()]
    if listed != crons:
        return "the gate's SCHEDULES (%s) are not the crons of on.schedule (%s), in their order" % (
            ", ".join(listed), ", ".join(crons))
    # The gate counts the attempts of one day by their date in UTC, which only crons of one time zone keep in order.
    zones = {entry.get("timezone") for entry in on.get("schedule") or []}
    if len(zones) > 1:
        return "the crons of on.schedule are in different time zones (%s)" % ", ".join(sorted(map(str, zones)))
    if "workflow_dispatch" not in on:
        return "the workflow cannot be started by hand any more"
    return None


def workflow_run(identifier, time, event="schedule"):
    """A run of the workflow as the API lists it: GitHub's times carry no fraction, but a start may."""
    return {"id": identifier, "workflow_id": 77, "event": event, "created_at": time,
            "run_started_at": time.replace("Z", ".123Z")}


def gate_scenarios():
    """[(name, scenario, check)] for the gate, on a day whose current run is the one of id 4."""
    out = []
    env = named_step("gate", GATE_STEP)[1]["env"]
    # 04:17, 06:17 and 08:17 in Paris in winter, as GitHub lists them, in UTC.
    times = {1: DAY + "T03:17:31Z", 2: DAY + "T05:17:12Z", 3: DAY + "T07:18:02Z"}

    def scenario(name, attempt, artifacts, check, extra_runs=(), event="schedule", schedule=None):
        current = {2: times[2], 3: times[3]}.get(attempt, times[3])
        runs = [workflow_run(number, times[number]) for number in range(1, 3) if times[number] < current]
        runs += [workflow_run(4, current)] + list(extra_runs)
        context = {"eventName": event, "runId": 4,
                   "payload": {"schedule": schedule or SCHEDULES[attempt - 1]} if event == "schedule" else {}}
        out.append((name, {"context": context, "runs": runs, "artifacts": artifacts, "issues": [],
                           "env": {key: str(value) for key, value in env.items()}}, check))

    def outputs(run, attempt=None, last="false", earlier=""):
        def check(result):
            got = result["outputs"]
            wanted = {"run": run, "last": last, "earlier": earlier}
            if attempt is not None:
                wanted["attempt"] = attempt
            wrong = {key: got.get(key) for key, value in wanted.items() if got.get(key) != value}
            if result["failures"]:
                return "it failed: %s" % result["failures"][:1]
            return "the outputs are %r, not %r" % (wrong, {key: wanted[key] for key in wrong}) if wrong else None
        return check

    def unread(*numbers):
        return " ".join(times[number] for number in numbers)

    def calls_nothing(check):
        def both(result):
            if result["calls"]:
                return "it asked the API although nothing needs to be read: %r" % result["calls"][:1]
            return check(result)
        return both

    out_of = "LiteLLM-model-drift-outcome-"
    scenario("a run started by hand reads, once, and is no last attempt", 1, {},
             calls_nothing(outputs("true", "1")), event="workflow_dispatch")
    scenario("the first attempt of the day reads, without asking anything", 1, {}, calls_nothing(outputs("true", "1")))
    scenario("a retry after an attempt that could not read a catalogue reads, and is not the last", 2,
             {"1": [out_of + "unreadable", "LiteLLM-model-drift"]}, outputs("true", "2", earlier=unread(1)))
    scenario("a retry after an attempt that read everything does nothing", 2, {"1": [out_of + "read"]},
             outputs("false", "2"))
    scenario("a retry after a retry that did nothing does nothing", 3, {"1": [out_of + "read"]}, outputs("false", "3"))
    scenario("an attempt that left no outcome is passed over, and the one before decides", 3,
             {"1": [out_of + "unreadable"]}, outputs("true", "3", last="true", earlier=unread(1)))
    scenario("the third attempt after two that could not read is the last, with their times in order", 3,
             {"1": [out_of + "unreadable"], "2": [out_of + "unreadable"]},
             outputs("true", "3", last="true", earlier=unread(1, 2)))
    scenario("the third attempt after a second that read everything does nothing", 3,
             {"1": [out_of + "unreadable"], "2": [out_of + "read"]}, outputs("false", "3"))
    scenario("a retry with no earlier attempt of the day does nothing", 2, {}, outputs("false", "2"))
    scenario("a run started by hand is no attempt of the chain", 2,
             {"1": [out_of + "read"], "9": [out_of + "unreadable"]}, outputs("false", "2"),
             extra_runs=[workflow_run(9, DAY + "T04:00:00Z", event="workflow_dispatch")])
    scenario("an attempt of another day is no attempt of this one", 2, {"8": [out_of + "unreadable"]},
             outputs("false", "2"), extra_runs=[workflow_run(8, "2026-11-24T07:18:00Z")])
    scenario("a run listed after this one is no attempt before it", 2,
             {"1": [out_of + "read"], "5": [out_of + "unreadable"]}, outputs("false", "2"),
             extra_runs=[workflow_run(5, DAY + "T05:50:00Z")])
    scenario("an artifact of another outcome is no outcome", 3,
             {"1": [out_of + "unreadable"], "2": [out_of + "maybe"]},
             outputs("true", "3", last="true", earlier=unread(1)))
    scenario("a run with two outcomes has none", 3,
             {"1": [out_of + "unreadable"], "2": [out_of + "read", out_of + "unreadable"]},
             outputs("true", "3", last="true", earlier=unread(1)))

    def refused(result):
        if not any("none of SCHEDULES" in failure for failure in result["failures"]):
            return "it did not fail"
        return None if result["outputs"].get("run") == "false" else "it runs: %r" % result["outputs"]
    scenario("a cron the gate does not number fails, and runs nothing", 1, {}, refused, schedule="17 5 * * 1")
    return out


def issue_scenarios():
    """[(name, scenario, check)] for the step that keeps the issue."""
    out = []
    earlier = " ".join((DAY + "T03:17:31Z", DAY + "T05:17:12Z"))

    def issue(number, title, state="open", login="github-actions[bot]", body=MARKER + "\nx"):
        return {"number": number, "title": title, "state": state, "body": body, "user": {"login": login}}

    def scenario(name, check, unreadable="", status=None, last="true", issues=(), event="schedule", times=earlier):
        status = status if status is not None else ("2" if unreadable else "1")
        env = {"DRIFT_STATUS": status, "UNREADABLE": unreadable, "LAST_ATTEMPT": last, "EARLIER": times}
        out.append((name, {"context": {"eventName": event}, "runs": [], "artifacts": {}, "issues": list(issues),
                           "env": env}, check))

    def calls(result, name):
        return [call["args"] for call in result["calls"] if call["name"] == name]

    def writes(result):
        return [call for call in result["calls"] if call["name"] != "issues.listForRepo"]

    def first(*checks):
        return next((why for ok, why in checks if not ok), None)

    def nothing_written(result):
        return first((not result["failures"], "it failed: %s" % result["failures"][:1]),
                     (not writes(result), "it wrote: %r" % writes(result)[:1]))

    def refused(result):
        return first((bool(result["failures"]), "it did not fail"),
                     (not writes(result), "it wrote: %r" % writes(result)[:1]))

    def opened(result, title=None):
        made = calls(result, "issues.create")
        body = made[0]["body"] if made else ""
        return first((not result["failures"], "it failed: %s" % result["failures"][:1]),
                     (len(made) == 1 and not calls(result, "issues.update"), "it did not open one issue: %r" % writes(result)),
                     (made and made[0].get("assignees") == ["tigerblue77"], "it is not assigned"),
                     (made and made[0]["title"] != LEGACY_TITLE and "illisible" in made[0]["title"], "the title is wrong"),
                     (body.startswith(MARKER), "the body does not start with the marker"),
                     ("| Groq | HTTP 4xx :" in body and "| Mistral | aucune réponse" in body, "the providers are not named with their class"),
                     (all("`%s`" % time in body for time in earlier.split()), "the earlier attempts' times are missing"),
                     ("/actions/runs/4" in body, "the run is not linked"))

    def taken_over(result):
        updated = calls(result, "issues.update")
        return first((not result["failures"], "it failed: %s" % result["failures"][:1]),
                     (not calls(result, "issues.create"), "a second issue was opened"),
                     (len(updated) == 1 and updated[0]["issue_number"] == 3 and updated[0].get("state") == "open"
                      and updated[0].get("title") != LEGACY_TITLE and MARKER in updated[0].get("body", ""),
                      "the issue was not reopened under its title: %r" % updated),
                     ([args["assignees"] for args in calls(result, "issues.addAssignees")] == [["tigerblue77"]],
                      "it was not assigned"))

    def closed(result):
        updated = calls(result, "issues.update")
        return first((not result["failures"], "it failed: %s" % result["failures"][:1]),
                     ([(args["issue_number"], args.get("state")) for args in updated] == [(3, "closed")],
                      "it was not closed: %r" % updated),
                     (len(calls(result, "issues.createComment")) == 1, "no comment says why"),
                     (not calls(result, "issues.create"), "an issue was opened"))

    def warned(word):
        def check(result):
            return first((not writes(result), "it wrote: %r" % writes(result)[:1]),
                         (any(word in warning for warning in result["warnings"]), "it did not say why: %r" % result["warnings"]))
        return check

    def opened_beside(result):
        return first((len(calls(result, "issues.create")) == 1, "no issue of its own was opened"),
                     (not calls(result, "issues.update") and not calls(result, "issues.addAssignees"),
                      "somebody else's issue was written"))

    legacy_closed = issue(3, LEGACY_TITLE, state="closed")
    legacy_open = issue(3, LEGACY_TITLE)
    scenario("the last attempt that still cannot read opens the issue, naming the providers, their class and the times",
             opened, unreadable="groq:4xx mistral:network")
    scenario("Cloudflare is a provider the issue names, with its class", lambda result: first(
        (not result["failures"], "it failed: %s" % result["failures"][:1]),
        ("| Cloudflare | HTTP 4xx :" in (calls(result, "issues.create") or [{"body": ""}])[0]["body"], "it is not named")),
             unreadable="cloudflare:4xx")
    scenario("the providers read since are named with their class too", lambda result: first(
        (not result["failures"], "it failed: %s" % result["failures"][:1]),
        (all(row in (calls(result, "issues.create") or [{"body": ""}])[0]["body"]
             for row in ("| Cent AI | HTTP 4xx :", "| Z AI | HTTP 5xx :", "| NVIDIA | aucune réponse")), "one is not named")),
             unreadable="centai:4xx zai:5xx nvidia:network")
    scenario("a catalogue of a provider the table does not name is refused", refused, unreadable="cloudflare2:4xx")
    scenario("an earlier attempt that cannot read opens nothing, and says the next one reads again",
             warned("two hours"), unreadable="groq:4xx", last="false")
    scenario("a run started by hand that cannot read opens nothing, and says so", warned("by hand"),
             unreadable="groq:4xx", last="false", event="workflow_dispatch")
    scenario("the issue of the drift reports, closed, is reopened under the new title rather than doubled", taken_over,
             unreadable="groq:4xx mistral:network", issues=[legacy_closed])
    scenario("a run that reads every catalogue closes the open issue, with a comment", closed, issues=[legacy_open])
    scenario("a run of deletions only opens no issue", nothing_written, status="1")
    scenario("a run of additions only, the issue open: the run reads every catalogue and closes it", closed,
             status="1", issues=[issue(3, "Catalogue de fournisseur illisible pour la liste de modèles LiteLLM")])
    scenario("a run with nothing opens no issue", nothing_written, status="0")
    scenario("a run started by hand that reads everything closes the issue too", closed, last="false",
             event="workflow_dispatch", issues=[legacy_open])
    scenario("somebody else's issue under the title, with the marker, is never written", opened_beside,
             unreadable="groq:4xx mistral:network", issues=[issue(3, LEGACY_TITLE, login="somebody")])
    scenario("an issue of the bot under another title is never taken over", opened_beside,
             unreadable="groq:4xx mistral:network", issues=[issue(3, "Another report")])
    scenario("an issue of the bot under the title, without the marker, is never taken over", opened_beside,
             unreadable="groq:4xx mistral:network", issues=[issue(3, LEGACY_TITLE, body="no marker")])
    for word, why in (("acme:4xx", "a provider it does not know"), ("__proto__:4xx", "a key of every object"),
                      ("groq:401", "a status rather than a class"), ("groq:4xx groq:5xx", "a provider twice"),
                      ("groq:4xx<img>", "a word with more after it"), ("x groq:4xx", "a word of no shape")):
        scenario("what names %s is refused, and nothing is written" % why, refused, unreadable=word)
    scenario("a status 2 without a catalogue named is refused", refused, status="2")
    scenario("a catalogue named under a status other than 2 is refused", refused, unreadable="groq:4xx", status="1")
    scenario("a status it does not know is refused", refused, status="9")
    scenario("a time of an earlier attempt that is no time is refused", refused, unreadable="groq:4xx",
             times="yesterday")
    return out


def play_actions(script, cases):
    payload = {"script": script, "scenarios": [scenario for _, scenario, _ in cases]}
    results = node(ACTIONS_HARNESS, payload)
    if len(results) != len(cases):
        raise SystemExit("node answered %d scenario(s) out of %d." % (len(results), len(cases)))
    return results


def attempts_wrong(gate=None, issue=None):
    """[(name, why)] of every scenario of the gate and of the issue step that went wrong, for the
    scripts as they are or as given, and the number of scenarios."""
    if gate is None:
        gate = named_step("gate", GATE_STEP)[1]["with"]["script"]
    if issue is None:
        issue = named_step("publish", ISSUE_STEP)[1]["with"]["script"]
    gates, issues = gate_scenarios(), issue_scenarios()
    wrong = judge_step(gates, play_actions(gate, gates)) + judge_step(issues, play_actions(issue, issues))
    problem = table_problem(issue, "issue", drift_module())
    if problem:
        wrong.append(("the providers of the issue are the ones the script reads", problem))
    problem = schedule_problem(named_step("gate", GATE_STEP)[0])
    if problem:
        wrong.append(("the gate numbers the attempts as on.schedule lists them", problem))
    return wrong, len(gates) + len(issues)


# Breaks of the gate and of the issue step, one at a time: (which step, what stops being done, text,
# replacement).
ATTEMPT_MUTATIONS = [
    ("gate", "treat a run started by hand as one attempt", "if (context.eventName !== 'schedule') {", "if (false) {"),
    ("gate", "fail on a cron it does not number", "if (attempt === 0) {", "if (false) {"),
    ("gate", "read on the first attempt without asking", "if (attempt === 1) {", "if (false) {"),
    ("gate", "leave out a run started by hand", "run.event === 'schedule' &&", ""),
    ("gate", "leave out another day", "run.created_at.slice(0, 10) === day &&", ""),
    ("gate", "leave out a run after this one", "&& run.created_at < current.created_at)", ")"),
    ("gate", "take the latest outcome first", "(a.created_at < b.created_at ? 1 : -1)", "(a.created_at < b.created_at ? -1 : 1)"),
    ("gate", "take an artifact of one outcome only", "names.length === 1 ?", "names.length > 0 ?"),
    ("gate", "know the two outcomes only", "['read', 'unreadable'].includes(outcome)", "outcome !== null"),
    ("gate", "do nothing without an earlier outcome", "if (outcomes.length === 0) {", "if (false) {"),
    ("gate", "do nothing after an attempt that read everything", "if (outcomes[0].outcome !== 'unreadable') {",
     "if (false) {"),
    ("gate", "call the third attempt alone the last", "attempt === schedules.length, earlier", "true, earlier"),
    ("gate", "give the earlier times in order", ".replace(/\\.[0-9]+Z$/, 'Z')).reverse();", ".replace(/\\.[0-9]+Z$/, 'Z'));"),
    ("gate", "give the earlier times without a fraction", ".replace(/\\.[0-9]+Z$/, 'Z')", ""),
    ("issue", "open the issue at the last attempt only", "if (process.env.LAST_ATTEMPT !== 'true') {", "if (false) {"),
    ("issue", "write only the issues of the workflow's own token", "issue.user?.login === 'github-actions[bot]' &&", ""),
    ("issue", "take over an issue under its titles only", "titles.includes(issue.title) &&", ""),
    ("issue", "take over the issue of the drift reports", "const titles = [title, 'Dérive de la liste de modèles LiteLLM'];",
     "const titles = [title];"),
    ("issue", "take over an issue with the marker only", "(issue.body ?? '').includes(marker))", "true)"),
    ("issue", "refuse a provider it does not know", "!Object.hasOwn(PROVIDERS, match[1]) ||", ""),
    ("issue", "name every provider the script reads in the issue's table", "cloudflare: 'Cloudflare', kilo: 'Kilo Gateway',",
     "cloudflare: 'Cloudflare',"),
    ("issue", "refuse a class it does not know", "!Object.hasOwn(CLASSES, match[2]) ||", ""),
    ("issue", "refuse a provider named twice", "unread.some((each) => each.provider === match[1])", "false"),
    ("issue", "read a word whole", "/^([a-z]+):([0-9a-z]+)$/", "/([a-z]+):([0-9a-z]+)/"),
    ("issue", "hold the status to the catalogues named", "|| (status === '2') !== (unread.length > 0)", ""),
    ("issue", "refuse a status it does not know", "!['0', '1', '2'].includes(status) || ", ""),
    ("issue", "refuse a time that is no time", "if (earlier.some((time) =>", "if (false && earlier.some((time) =>"),
    ("issue", "close the open issue when every catalogue is read", "if (existing && existing.state === 'open') {",
     "if (false) {"),
    ("issue", "reopen the issue it takes over", "title, body, state: 'open',", "title, body,"),
    ("issue", "assign the issue it takes over", "await github.rest.issues.addAssignees({", "await (async () => {})({"),
    ("issue", "assign the issue it opens", "owner, repo, title, body, assignees: [assignee],", "owner, repo, title, body,"),
]


def run_attempts_selftest():
    wrong, _ = attempts_wrong()
    if wrong:
        print("the gate and the issue step fail their own scenarios before anything is broken:")
        for name, why in wrong:
            print("  %s: %s" % (name, why))
        return 1
    scripts = {"gate": named_step("gate", GATE_STEP)[1]["with"]["script"],
               "issue": named_step("publish", ISSUE_STEP)[1]["with"]["script"]}
    failures = 0
    for which, label, old, new in ATTEMPT_MUTATIONS:
        if scripts[which].count(old) != 1:
            failures += 1
            print("selftest: the text of the %s step that should %s has moved: %r" % (which, label, old))
            continue
        broken = dict(scripts, **{which: scripts[which].replace(old, new, 1)})
        try:
            noticed = bool(attempts_wrong(broken["gate"], broken["issue"])[0])
        except SystemExit as error:
            failures += 1
            print("selftest: breaking the %s step that should %s left a script that does not run: %s"
                  % (which, label, str(error)[:200]))
            continue
        if noticed:
            print("selftest: ok -- some scenario notices a %s step that stops: %s" % (which, label))
        else:
            failures += 1
            print("selftest: FAILED -- no scenario notices a %s step that stops: %s" % (which, label))
    document = named_step("gate", GATE_STEP)[0]
    moved = yaml.safe_load(yaml.safe_dump(document))
    on = moved.get("on", moved.get(True))
    on["schedule"] = list(reversed(on["schedule"]))
    if schedule_problem(moved) is None:
        failures += 1
        print("selftest: FAILED -- crons reordered without the gate's SCHEDULES go unnoticed")
    else:
        print("selftest: ok -- crons reordered without the gate's SCHEDULES are noticed")
    if failures:
        return 1
    print("check_drift_publish_guard selftest: the gate and the issue step as expected, %d broken guard(s) "
          "of theirs noticed, and a schedule out of step with the gate." % len(ATTEMPT_MUTATIONS))
    return 0


def main(argv):
    if argv[1:] == ["--selftest"]:
        return run_selftest() or run_additions_selftest() or run_attempts_selftest()
    if argv[1:]:
        print("usage: check_drift_publish_guard.py [--selftest]", file=sys.stderr)
        return 2
    cases = scenarios()
    wrong = judge(cases, play(load_guard(), cases))
    if wrong:
        print("%d of %d scenario(s) of the drift pull request guard went the wrong way:\n" % (len(wrong), len(cases)))
        for name, why in wrong:
            print("  %s: %s" % (name, why))
        return 1
    print("Drift pull request guard: %d scenario(s) judged as expected." % len(cases))
    wrong, built = additions_wrong()
    if wrong:
        print("%d scenario(s) of the additions went the wrong way:\n" % len(wrong))
        for name, why in wrong:
            print("  %s: %s" % (name, why))
        return 1
    print("Additions: %d template(s) built alike by the step and the script, or refused by both, and the "
          "step's handling of the three pull requests as expected." % built)
    wrong, played = attempts_wrong()
    if wrong:
        print("%d scenario(s) of the gate and the issue went the wrong way:\n" % len(wrong))
        for name, why in wrong:
            print("  %s: %s" % (name, why))
        return 1
    print("Attempts: %d scenario(s) of the gate and of the issue step as expected, and the gate numbers the "
          "attempts as on.schedule lists them." % played)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
