#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77
# SPDX-License-Identifier: AGPL-3.0-only

"""Play the guard of the weekly model-drift pull request step against made-up templates.

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

"--selftest" proves the scenarios can fail: it breaks the function one guard at a time and requires
some scenario to notice each. A guard no scenario notices is one this check cannot vouch for.

WHAT IT DOES NOT PROVE
----------------------
That the step calls the function on what it reads from GitHub: the wiring is checked as text. Nor
that "the rows of the table written again" are right -- "check_compose_template.py" holds each alias
to the first member of its cascade for every set of keys. Node is needed on the PATH.
"""

import json
import pathlib
import re
import shutil
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "LiteLLM_model_drift.yml"
TEMPLATE = ROOT / "templates" / "LiteLLM_config.yaml.j2"
STEP = "Open, update or close the deletion pull request"
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
            rewritten = "  'flash': 'gemini-3-8-flash' if has.Gemini else 'gpt-oss-120b-groq' if has.Groq else 'omniroute-free-auto',\n"
            drifted_names = "  'flash': 'gemini-3-8-flash' if has.Gemini else 'nowhere' if has.Groq else 'omniroute-free-auto',\n"
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


def main(argv):
    if argv[1:] == ["--selftest"]:
        return run_selftest()
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
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
