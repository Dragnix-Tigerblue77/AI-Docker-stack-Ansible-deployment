#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77
# SPDX-License-Identifier: AGPL-3.0-only

"""Hold LiteLLM's model list to its rule, and report where it has drifted from the providers.

WHY THIS CHECK EXISTS
---------------------
CLAUDE.md, "The model list keeps only what can be called": in "templates/LiteLLM_config.yaml.j2" a
model its provider has retired is deleted, entry and cascade slots alike; a model still served but
deliberately not routed to stays commented out, with its reason above it; new models are added as
providers publish them. Every part of that rule decays in silence:

* A retired model breaks nothing anyone sees. LiteLLM only finds out at call time, and inside a
  cascade a refused call just moves the request on to the next entry -- the cascade quietly gets
  shorter. September 2026 alone saw Groq shut three models down, OpenRouter's catalogue lose
  the ":free" ids of three routed models and DeepSeek rename its models for the second time
  that year.
* A cascade slot left behind by a deleted or commented-out entry is not an error LiteLLM reports at
  start-up either. "main" carried one: "code" still named "glm-5-2-free" after its entry
  had been commented out.
* A reason nobody wrote has to be rediscovered by the next audit, which is the cost the rule's
  "commented WITH its reason" exists to stop paying.
* A new model is, by definition, one nobody here has heard of yet.

Nothing else in this CI can see any of that: the file is valid YAML either way. This check, and
the weekly issue it feeds, exist to see it.

HOW THE FILE IS READ
--------------------
The file is a Jinja template: a provider's block is written only when its key is given, and the
cascades and the aliases follow. This check reads it RENDERED, with all five provider keys given --
a placeholder for each of the variables "Artificial_Intelligence_LiteLLM_<Provider>_API_key" -- in
a sandboxed environment with "trim_blocks" on and an undefined variable an error, as Ansible's
"template" module sets one up. What it holds the file to is therefore the union of every case: each
entry present, each cascade member present, and the aliases of the branch that has a Gemini key. It
needs PyYAML and Jinja2, both pinned in requirements.txt, and nothing else outside the standard
library.

That environment is plain Jinja2, not Ansible's: only Jinja's own filters and tests exist in it.
One that only Ansible provides ("to_json", "regex_replace", "ternary", the "match", "search" and
"version" tests) makes this check exit 2 although Ansible renders the file. The weekly job installs
PyYAML and Jinja2 alone, so the check cannot lean on ansible-core. The day the template needs such
a filter, add it to this check explicitly, as "check_compose_template.py" does for "to_json", keep
the pull-request and the weekly environments identical, and install ansible-core in the weekly job
in the same change.

* The YAML parse AND the comment scan (reasons, "drift-ignore:" lines) both run on the rendering,
  so a commented-out entry inside an "{% if %}" block is found, and a statement line between a
  reason and its entry takes nothing away from the reason.
* The branch written only when a key is MISSING -- the aliases of the routers that have no entry of
  their own without Gemini -- is not rendered, so nothing that would only fail there is seen; the
  names it reads are still held to the five keys, since that check reads the template without
  rendering it. Rendering every other set of keys and holding each alias to the first member of its
  cascade is "check_compose_template.py"'s job.
* A template that does not render -- a Jinja syntax error, a variable that is none of the five
  keys, however the template reads it -- is a finding that names the problem, and ends the run with
  status 2 like a file that is not YAML. Only Jinja2's own filters and tests exist here (the weekly
  job installs no ansible-core), so a template that uses one that only Ansible provides, "to_json"
  for instance, is reported as unreadable even though Ansible would render it; such a template has
  to be handled deliberately, either by not using the filter in this file or by teaching this check
  about it.
* A finding names an entry, or quotes the text of a line, rather than numbering a line of the
  rendering: that is a number no file contains. A YAML error quotes the line where the parser
  stopped and, when it was parsing something that began higher up, the line that began it; it names
  the nearest "model_name" above them, inside "model_list" only. The entry is where to start
  looking, not a diagnosis. The one number a finding carries is the line Jinja was reading when it
  gave up, in the template as written: for a block left open that is the end of the file, so the
  message names the block's opener instead.

TWO MODES
---------
Offline, the default, run on every pull request. It reads the file and nothing else:

  (a) every fallback cascade member (source and targets, under the four fallback keys of both
      "router_settings" and "litellm_settings") and every "model_group_alias" target names an
      ACTIVE "model_name" -- a commented-out entry is not one;
  (b) no "model_name" is declared twice, counting commented-out entries: uncommenting one is the
      documented way back, and would then create the duplicate. LiteLLM itself accepts duplicates
      -- it is how it load-balances -- so the day this file wants one, this rule is the line to
      change, knowingly;
  (c) every commented-out entry carries its reason (defined below);
  (d) every "# drift-ignore:" line is well formed and gives its reason.

"--online" reads each provider's model catalogue as well, and reports the drift, without ever
editing the file: it prints a plain-text report and, with "--issue-body PATH", writes the body of
the rolling issue ".github/workflows/LiteLLM_model_drift.yml" keeps up to date. That body is in
French, since an issue is read by the maintainers (CLAUDE.md, "Language"); the report is English,
like any run's output. Exit status: 0 no drift, 1 drift, 2 a provider, or the file itself, could
not be read (an error outranks drift, since it means the report is incomplete). The offline
rules are applied in this mode too: nothing blocks a human's merge here, so a red pull request can
still land on main, and the weekly run is the next place it shows.

WHAT COUNTS AS A REASON
-----------------------
A commented-out entry is a comment line whose text, once its "#" and one space are removed, starts
with "- model_name:", together with the comment lines under it that are indented further. Its
reason is the prose of the comment block directly above it: every comment line walking upwards,
up to the first blank or non-comment line, skipping bare "#" lines. That prose has to say the
entry is "not routed" -- "not route", "not routed" or "not routing", case and line breaks
ignored -- and why. Every reason the file carried when this check was written already used that
phrase ("Served, but not routed to: paid only", "SambaNova -- not routed to: ..."), and requiring
it is what keeps a section banner that merely happens to sit above an entry from passing for its
reason.

Several commented-out entries separated only by bare "#" lines form a run, and share the reason
above the first of them -- the SambaNova block is seven entries under one reason. An entry after a
blank line starts a new run and needs its own; one with its own prose above it is judged on that
prose alone, and does not inherit the reason of the entry before.

HOW EACH PROVIDER IS READ
-------------------------
An entry belongs to a provider by the prefix of its "model:", which is how LiteLLM itself routes it:
"gemini/<id>", "groq/<id>", "mistral/<id>", "deepseek/<id>", "cerebras/<id>", "openrouter/<id>",
and SambaNova as "openai/<id>" with an "api_base" on "api.sambanova.ai". An entry of no provider
below -- OmniRoute, local and keyless -- is left out, and the report says how many.

  provider    catalogue, and how its key is sent       what counts as a chat model, for NEW
  openrouter  openrouter.ai/api/v1/models              ":free", both prices "0", and text its
              ?output_modalities=all -- no key         only output modality
  cerebras    api.cerebras.ai/public/v1/models         not "deprecated"
              -- no key
  sambanova   api.sambanova.ai/v1/models -- no key     not "deprecated"
  gemini      generativelanguage.googleapis.com/       "generateContent" among its
              v1beta/models, paginated -- header       "supportedGenerationMethods"
  groq        api.groq.com/openai/v1/models -- Bearer  "active" not false
  mistral     api.mistral.ai/v1/models -- Bearer       "completion_chat", no "deprecation",
                                                       no "ft:" (a fine-tune)
  deepseek    api.deepseek.com/models -- Bearer        every model

On top of each provider's own filter, an id naming a non-chat use (NON_CHAT_MARKERS: "tts",
"whisper", "embed", "guard"...) is never a NEW candidate: Gemini's "generateContent" alone lets its
speech and image models through, and Groq, SambaNova and DeepSeek say nothing about capability at
all. The filter narrows NEW only. Whether a model is RETIRED is decided against everything the
provider lists, so that no filter can ever make a served model look retired -- which is also why
OpenRouter is read with "output_modalities=all", its default being "text" only.

The keys are read from MODEL_DRIFT_GEMINI_API_KEY, MODEL_DRIFT_GROQ_API_KEY,
MODEL_DRIFT_MISTRAL_API_KEY and MODEL_DRIFT_DEEPSEEK_API_KEY. An unset or empty one leaves its
provider "not covered (no key)", which the report says every time rather than skipping it. Gemini's
goes in the "x-goog-api-key" header rather than the "?key=" parameter its examples use, so that no
URL this script builds, prints or reports ever carries a key.

WHAT IS REPORTED
----------------
RETIRED    an active entry whose id the catalogue no longer lists: delete it and its cascade slots.
GONE       a commented-out entry whose id the catalogue no longer lists: delete it too -- the rule
           keeps no commented-out corpse of a retired model.
NOTICE     an active entry the provider marks for removal: OpenRouter's "expiration_date",
           Mistral's "deprecation" (with "deprecation_replacement_model"), the "deprecated" flag of
           Cerebras and SambaNova, Groq's "active": false.
BACK       OpenRouter only: a commented-out id without ":free" whose ":free" twin is now free. A
           commented-out ":free" id is never BACK: it is free whenever it exists, so it cannot have
           been commented out for its price, and its being free again is no news -- that is the
           guardrail "nemotron-3.5-content-safety:free", commented out for being no generator.
NEW        an id the file does not know. Known ids are those of the active and the commented-out
           entries, and those a "# drift-ignore: <provider>/<id> -- <reason>" line names, which is
           how a model examined and turned down stops being reported without an entry of its own.
           <provider> is one of the seven names above: "sambanova/<id>" for SambaNova, where the
           entry itself reads "openai/<id>". A Mistral id is known when one of its "aliases" is.

Free-tier eligibility is machine-readable on OpenRouter alone, as ":free" and a price of "0". Every
other provider publishes it only in prose, on a pricing page, so a NEW model there is listed as one
to examine, never claimed free.

A catalogue that could not be read is an error for that provider, reported with the HTTP status and
nothing else: the answer's body is never printed, because a provider may echo the key back in it
(DeepSeek does: "Your api key: ****ogus is invalid", measured with a bogus key). Above all, a failed
read never turns into "every model retired".

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
* It never edits the file, and never opens a pull request. Every claim in the list cites the
  provider's own page and the date it was checked; a machine reading a catalogue has neither, so
  what it produces is where a human's check starts, not a substitute for it.
* It does not call any model. A listed model can still refuse a given key -- Google restricts
  Gemini 2.5 to accounts that used it before -- and only LiteLLM's own health check on the node
  would see that.
* It does not read OpenRouter's "/api/v1/models/<id>/endpoints". A removed slug answers there with
  200 and "endpoints": [] -- and so does "openrouter/free", the free router "flash" falls back on,
  measured 2026-09-27. The route cannot tell the two apart; the catalogue can.
* It does not report a commented-out entry's deprecation: nothing routes to it. The week it is
  actually retired, it comes back as GONE.
* It does not cover what a key cannot see. A keyed provider's catalogue is the one of the account
  behind the key, so a model reserved to another tier or region is invisible to it.
* It does not read the rate limits, the prices outside OpenRouter, or whether a provider still
  offers a free tier at all -- those live in prose only.

Its verification cases are Python literals rather than fixture files, for the reason CLAUDE.md
gives: a fixture on disk is reachable by "ansible-lint --fix", which has rewritten one here before.
The online cases are fed canned catalogues, so "--selftest" needs no network and no key.

Run it from the repository root:

    python3 .github/scripts/check_LiteLLM_model_drift.py --selftest
    python3 .github/scripts/check_LiteLLM_model_drift.py
    python3 .github/scripts/check_LiteLLM_model_drift.py --online --issue-body /tmp/body.md
"""

import argparse
import datetime
import http.client
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "PyYAML is required by this check (see requirements.txt): pip install -r requirements.txt\n"
    )
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "templates" / "LiteLLM_config.yaml.j2"

# ".github/workflows/LiteLLM_model_drift.yml" finds its rolling issue by its exact title AND this
# marker in the body, and writes the same string: a change here goes there in the same commit. The
# workflow refuses a body without its marker rather than open a second issue.
ISSUE_MARKER = "<!-- LiteLLM-model-drift -->"

# LiteLLM's four fallback keys, read under both sections, as "check_LiteLLM_account_isolation.py"
# does: the three besides "fallbacks" name model groups just as well.
FALLBACK_KEYS = (
    "fallbacks",
    "default_fallbacks",
    "context_window_fallbacks",
    "content_policy_fallbacks",
)
SETTINGS_SECTIONS = ("router_settings", "litellm_settings")

COMMENT = re.compile(r"^[ \t]*#(?P<text>.*)$")
COMMENTED_ENTRY = re.compile(r"^-\s+model_name\s*:")
# An entry of the rendered model list, to name the one a YAML error sits in.
ENTRY_NAME = re.compile(r"^\s*-\s+model_name\s*:\s*(?P<name>\S.*?)\s*$")
REASON = re.compile(r"\bnot\s+rout(?:e|ed|ing)\b", re.IGNORECASE)
DRIFT_IGNORE_START = re.compile(r"^\s*drift-ignore\s*:")
DRIFT_IGNORE = re.compile(r"^\s*drift-ignore\s*:\s*(?P<target>\S+)\s+--\s+(?P<reason>\S.*?)\s*$")

# The variables "templates/LiteLLM_config.yaml.j2" reads: a provider's block is written when its
# variable is a non-empty string, and the template reads nothing else.
PROVIDER_KEY_VARIABLES = tuple(
    "Artificial_Intelligence_LiteLLM_%s_API_key" % provider
    for provider in ("Gemini", "Mistral", "Groq", "OpenRouter", "DeepSeek")
)

# Substrings of an id that name a use other than chat. They narrow NEW only, never RETIRED.
NON_CHAT_MARKERS = (
    "audio", "embed", "guard", "image", "imagen", "lyria", "moderation", "ocr", "orpheus",
    "playai", "rerank", "speech", "transcribe", "tts", "veo", "whisper",
)

TIMEOUT = 30
MAX_PAGES = 20
MAX_LISTED = 150  # per section of the issue body, which GitHub caps at 65536 characters
USER_AGENT = "check_LiteLLM_model_drift (AI-Docker-stack-Ansible-deployment)"


# ------------------------------------------------------------------------------------------------
# Reading the file
# ------------------------------------------------------------------------------------------------

class RenderError(Exception):
    """The template does not render. Its message names the problem and is reported as a finding."""


def ansible_only_hint(message):
    """What to add to a Jinja message that is probably a filter or test only Ansible provides."""
    if message.startswith(("No filter named '", "No test named '")):
        return (" -- probably a filter or test that only Ansible provides: only Jinja2's own are "
                "available to this check (see HOW THE FILE IS READ in the docstring of this "
                "script)")
    return ""


def open_block_line(environment, text):
    """The template line of the innermost "if" or "for" never closed, or None when none is found."""
    opened = []
    expecting_tag = False
    try:
        for lineno, kind, value in environment.lex(text):
            if kind == "block_begin":
                expecting_tag = True
            elif kind == "whitespace" or not expecting_tag:
                continue
            else:
                expecting_tag = False
                if kind != "name":
                    continue
                if value in ("if", "for"):
                    opened.append(lineno)
                elif value in ("endif", "endfor") and opened:
                    opened.pop()
    except Exception:  # the lexer failing is for Jinja's own message to say, not for this helper
        return None
    return opened[-1] if opened else None


def jinja_syntax_finding(environment, text, error):
    """The finding for a Jinja error raised before the template could be rendered."""
    hint = ansible_only_hint(error.message)
    if hint:
        return RenderError("the file cannot be rendered with plain Jinja2 (template line %s): %s%s"
                           % (error.lineno, error.message, hint))
    if error.message.startswith("Unexpected end of template"):
        # The line Jinja reports is the one it was reading when the file ran out: a correct
        # "endif" near the end, not the block left open.
        opener = open_block_line(environment, text)
        if opener is not None:
            return RenderError("the file is not valid Jinja (the block opened at template line %s "
                               "is never closed): %s" % (opener, error.message))
        return RenderError("the file is not valid Jinja (a block is still open at the end of the "
                           "file, template line %s): %s" % (error.lineno, error.message))
    return RenderError("the file is not valid Jinja (template line %s): %s"
                       % (error.lineno, error.message))


def render_every_key(text):
    """The file as this check's plain Jinja2 sandbox renders it with all five keys given."""
    # Imported here and not above, so that the message can name the file that pins it.
    try:
        import jinja2
        import jinja2.meta
        from jinja2 import nodes
        from jinja2.sandbox import SandboxedEnvironment
    except ImportError:  # pragma: no cover
        sys.stderr.write("Jinja2 is required by this check (see requirements.txt): "
                         "pip install -r requirements.txt\n")
        raise SystemExit(2)
    # Ansible's own environment is a sandbox, and the weekly run holds the providers' keys.
    environment = SandboxedEnvironment(undefined=jinja2.StrictUndefined, trim_blocks=True,
                                       keep_trailing_newline=True)
    # A variable the template reads and this check does not supply would be "not given" without a
    # word: the template tests each key with "is string", and that test is false on an undefined
    # name instead of raising. So the names are read off the parse, not found out by rendering.
    try:
        tree = environment.parse(text)
        # This compiles the tree, which is where an unknown filter or test outside an "if" fails.
        read = jinja2.meta.find_undeclared_variables(tree)
    except jinja2.TemplateSyntaxError as error:
        raise jinja_syntax_finding(environment, text, error) from None
    # A name the template assigns itself is not an input, whatever branch the assignment sits in:
    # Jinja counts a "set" inside an "if" as undeclared.
    assigned = {name.name for name in tree.find_all(nodes.Name) if name.ctx == "store"}
    unknown = sorted(read - assigned - set(PROVIDER_KEY_VARIABLES))
    if unknown:
        raise RenderError("the file reads %s, which is none of the five provider keys"
                          % ", ".join(unknown))
    context = {variable: "placeholder" for variable in PROVIDER_KEY_VARIABLES}
    try:
        return environment.from_string(text).render(context)
    except jinja2.TemplateSyntaxError as error:  # which an unknown filter outside an "if" is too
        raise jinja_syntax_finding(environment, text, error) from None
    except Exception as error:  # whatever the template's own code raised is a finding, not a crash
        hint = ansible_only_hint(str(error))  # an unknown filter inside an "if" is raised here
        if hint:
            raise RenderError("the file cannot be rendered with plain Jinja2: %s%s"
                              % (error, hint)) from None
        raise RenderError("the file could not be rendered with every provider key given: %s: %s"
                          % (error.__class__.__name__, error)) from None


def entry_around(lines, number):
    """The model_name of the entry that line `number` sits in, or None outside "model_list"."""
    while number >= 0:
        line = lines[number]
        if line.strip() and not line.lstrip().startswith("#"):
            match = ENTRY_NAME.match(line)
            if match:
                return match.group("name").strip("\"'")
            if not line[0].isspace():  # a top-level key: this is not the model list
                return None
        number -= 1
    return None


def yaml_error_text(error, lines):
    """What PyYAML objected to, the text of the lines it points at rather than their number, and
    the entry nearest above them."""
    parts = [part for part in (getattr(error, "context", None), getattr(error, "problem", None))
             if part]
    text = "; ".join(parts) or (str(error).splitlines() or [error.__class__.__name__])[0]

    def line_of(name):
        mark = getattr(error, name, None)
        return mark.line if mark is not None and 0 <= mark.line < len(lines) else None

    problem, context = line_of("problem_mark"), line_of("context_mark")
    # The problem mark is where the parser gave up. For an error "while parsing a ..." the line that
    # is wrong is the one it was parsing from, the context mark, which can be well above it.
    if context is not None and context != problem:
        text += " (from: %s)" % lines[context].strip()
    if problem is not None:
        text += " (at: %s)" % lines[problem].strip()
    anchor = context if context is not None else problem
    entry = entry_around(lines, anchor) if anchor is not None else None
    if entry is not None:
        text += ' [entry "%s"]' % entry
    return text


def comment_content(line):
    """The text of a comment line without its "#" and one space, or None for any other line."""
    match = COMMENT.match(line)
    if not match:
        return None
    text = match.group("text")
    return text[1:] if text.startswith(" ") else text


def attribute(model, api_base):
    """(provider, id) for a LiteLLM "model:" value, or None when no catalogue here covers it."""
    if not isinstance(model, str) or "/" not in model:
        return None
    prefix, identifier = model.split("/", 1)
    if prefix in ("gemini", "groq", "mistral", "deepseek", "cerebras", "openrouter"):
        return prefix, identifier
    if prefix == "openai" and isinstance(api_base, str) and "api.sambanova.ai" in api_base:
        return "sambanova", identifier
    return None


def entry_of(item):
    parameters = item.get("litellm_params") if isinstance(item, dict) else None
    parameters = parameters if isinstance(parameters, dict) else {}
    return {
        "name": item.get("model_name") if isinstance(item, dict) else None,
        "model": parameters.get("model"),
        "api_base": parameters.get("api_base"),
    }


def read_template(text):
    """Parse the file as render_every_key renders it, with every provider key given.

    Returns (template, problems); template is None when it cannot be read.
    """
    try:
        rendered = render_every_key(text)
    except RenderError as error:
        return None, [str(error)]
    lines = rendered.splitlines()
    try:
        document = yaml.safe_load(rendered)
    except yaml.YAMLError as error:
        return None, ["the file, rendered with every provider key given, is not valid YAML: %s"
                      % yaml_error_text(error, lines)]
    if not isinstance(document, dict) or not isinstance(document.get("model_list"), list):
        return None, ['the file, rendered with every provider key given, has no "model_list" list, '
                      "so there is nothing to check"]

    problems = []
    active = [entry_of(item) for item in document["model_list"] if isinstance(item, dict)]

    # Commented-out entries: each block is uncommented and parsed like any other entry.
    commented = []
    owner = {}
    index = 0
    while index < len(lines):
        content = comment_content(lines[index])
        if content is None or not COMMENTED_ENTRY.match(content):
            index += 1
            continue
        start = index
        block = [content]
        index += 1
        while index < len(lines):
            following = comment_content(lines[index])
            if following is None or not following.strip() or not following.startswith(" "):
                break
            block.append(following)
            index += 1
        for number in range(start, index):
            owner[number] = len(commented)
        try:
            parsed = yaml.safe_load("\n".join(block))
        except yaml.YAMLError:
            parsed = None
        if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
            entry = entry_of(parsed[0])
        else:
            entry = entry_of({})
            problems.append(
                'the commented-out entry "%s" is not valid YAML once uncommented. It is\n'
                "    meant to be the way back to routing that model: keep it an entry that would\n"
                "    parse." % block[0]
            )
        # What the messages call it: its name, or failing that the line that opens it.
        entry["shown"] = entry["name"] if isinstance(entry["name"], str) else block[0]
        entry["start"] = start
        commented.append(entry)

    # (c) Every commented-out entry has its reason. Entries are judged top-down, so that one which
    # shares the run of the entry above it can inherit that entry's verdict.
    for entry in commented:
        prose = []
        inherited = None
        number = entry["start"] - 1
        while number >= 0:
            if number in owner:
                if not prose:
                    inherited = commented[owner[number]]["reasoned"]
                break
            content = comment_content(lines[number])
            if content is None:
                break
            if content.strip() and not DRIFT_IGNORE_START.match(content):
                prose.append(content.strip())
            number -= 1
        if prose:
            entry["reasoned"] = bool(REASON.search(" ".join(reversed(prose))))
        else:
            entry["reasoned"] = bool(inherited)
        if not entry["reasoned"]:
            problems.append(
                'the commented-out entry "%s" gives no reason for not being routed to.\n'
                "    Write it in the comment block directly above the entry, or above the run of\n"
                '    commented-out entries it belongs to: say that it is "not routed" and why --\n'
                "    paid only, bank card required, enterprise only... If its provider no longer\n"
                "    serves it, delete it instead: that is the rule of CLAUDE.md, \"The model list\n"
                '    keeps only what can be called".' % entry["shown"]
            )

    # (d) "# drift-ignore:" lines.
    ignored = []
    for line in lines:
        content = comment_content(line)
        if content is None or not DRIFT_IGNORE_START.match(content):
            continue
        match = DRIFT_IGNORE.match(content)
        if not match:
            problems.append(
                '"# %s" is malformed: a "drift-ignore:" line must read "drift-ignore:\n'
                "    <provider>/<id> -- <reason>\": the reason is what tells the next audit the\n"
                "    model was looked at and turned down, rather than forgotten." % content.strip()
            )
            continue
        provider, _, identifier = match.group("target").partition("/")
        if provider not in PROVIDER_NAMES or not identifier:
            problems.append(
                '"drift-ignore: %s" names no provider this check reads. Write\n'
                "    <provider>/<id>, <provider> being one of: %s."
                % (match.group("target"), ", ".join(PROVIDER_NAMES))
            )
            continue
        ignored.append((provider, identifier))

    # (b) No model_name twice, commented-out entries included.
    seen = {}
    for kind, entries in (("active", active), ("commented out", commented)):
        for entry in entries:
            if isinstance(entry["name"], str):
                seen.setdefault(entry["name"], []).append(kind)
    for name, kinds in sorted(seen.items()):
        if len(kinds) > 1:
            problems.append(
                'the model_name "%s" is declared %d times (%s).\n'
                "    LiteLLM would make one group of them and spread the load across: give each\n"
                "    entry its own name, or delete the one that should not be there."
                % (name, len(kinds), ", ".join("%d %s" % (kinds.count(kind), kind)
                                               for kind in dict.fromkeys(kinds)))
            )

    # (a) Every cascade member and alias target is an active model_name.
    names = {entry["name"] for entry in active if isinstance(entry["name"], str)}
    commented_names = {entry["name"] for entry in commented if isinstance(entry["name"], str)}

    def require(name, where):
        if isinstance(name, str) and name in names:
            return
        state = ("only a commented-out entry" if name in commented_names
                 else "no entry at all")
        problems.append(
            '%s names "%s", which is no active model_name (%s).\n'
            "    A model deleted or commented out takes its cascade slots and aliases with it, in\n"
            "    the same change." % (where, name, state)
        )

    for section_name in SETTINGS_SECTIONS:
        section = document.get(section_name)
        if not isinstance(section, dict):
            continue
        for key in FALLBACK_KEYS:
            if key not in section:
                continue
            value = section[key]
            where = '"%s.%s"' % (section_name, key)
            if key == "default_fallbacks":
                for target in value if isinstance(value, list) else [value]:
                    require(target, where)
                continue
            for mapping in value if isinstance(value, list) else [value]:
                if not isinstance(mapping, dict):
                    problems.append("%s holds %r, where a {model: [fallbacks]} mapping was "
                                    "expected." % (where, mapping))
                    continue
                for source, targets in mapping.items():
                    require(source, '%s, the cascade "%s" itself,' % (where, source))
                    for target in targets if isinstance(targets, list) else [targets]:
                        require(target, '%s, in the cascade "%s",' % (where, source))
        aliases = section.get("model_group_alias")
        if isinstance(aliases, dict):
            for alias, target in aliases.items():
                if isinstance(target, dict):
                    target = target.get("model")
                require(target,
                        '"%s.model_group_alias", for the alias "%s",' % (section_name, alias))

    template = {"active": active, "commented": commented, "ignored": ignored}
    return template, problems


# ------------------------------------------------------------------------------------------------
# Reading the catalogues
# ------------------------------------------------------------------------------------------------

class FetchError(Exception):
    """A catalogue that could not be read. Its message never carries a key nor a response body."""


def urllib_opener(url, headers):
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def fetch_json(opener, url, headers):
    try:
        raw = opener(url, headers)
    except urllib.error.HTTPError as error:
        # The body is never read: a provider may echo the key back in it.
        raise FetchError("HTTP %d %s" % (error.code, error.reason)) from None
    except urllib.error.URLError as error:
        raise FetchError("network error: %s" % (error.reason,)) from None
    except (OSError, ValueError, http.client.HTTPException) as error:
        raise FetchError("network error: %s" % error.__class__.__name__) from None
    try:
        return json.loads(raw)
    except ValueError:
        raise FetchError("the answer is not JSON") from None


def is_zero(price):
    try:
        return float(price) == 0
    except (TypeError, ValueError):
        return False


def chat_like(identifier):
    lowered = identifier.lower()
    return not any(marker in lowered for marker in NON_CHAT_MARKERS)


def listed(payload, key="data"):
    items = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise FetchError('the answer holds no "%s" list' % key)
    return [item for item in items if isinstance(item, dict) and isinstance(item.get("id"), str)]


def new_catalogue():
    return {"members": set(), "candidates": {}, "notices": {}, "aliases": {}}


def read_openrouter(pages):
    catalogue = new_catalogue()
    for model in listed(pages[0]):
        identifier = model["id"]
        catalogue["members"].add(identifier)
        if model.get("expiration_date"):
            catalogue["notices"][identifier] = {"what": "expiration",
                                                "date": str(model["expiration_date"])}
        pricing = model.get("pricing") if isinstance(model.get("pricing"), dict) else {}
        architecture = model.get("architecture")
        architecture = architecture if isinstance(architecture, dict) else {}
        if (identifier.endswith(":free")
                and is_zero(pricing.get("prompt")) and is_zero(pricing.get("completion"))
                and architecture.get("output_modalities") == ["text"]
                and chat_like(identifier)):
            catalogue["candidates"][identifier] = model.get("name") or ""
    return catalogue


def read_flagged(pages):
    """Cerebras and SambaNova: an OpenAI-style list, with a "deprecated" flag where there is one."""
    catalogue = new_catalogue()
    for model in listed(pages[0]):
        identifier = model["id"]
        catalogue["members"].add(identifier)
        if model.get("deprecated") is True:
            catalogue["notices"][identifier] = {"what": "deprecation"}
        elif chat_like(identifier):
            catalogue["candidates"][identifier] = model.get("name") or ""
    return catalogue


def read_gemini(pages):
    catalogue = new_catalogue()
    for page in pages:
        models = page.get("models") if isinstance(page, dict) else None
        if not isinstance(models, list):
            raise FetchError('the answer holds no "models" list')
        for model in models:
            name = model.get("name") if isinstance(model, dict) else None
            if not isinstance(name, str):
                continue
            identifier = name[len("models/"):] if name.startswith("models/") else name
            catalogue["members"].add(identifier)
            methods = model.get("supportedGenerationMethods") or []
            if "generateContent" in methods and chat_like(identifier):
                catalogue["candidates"][identifier] = model.get("displayName") or ""
    return catalogue


def read_groq(pages):
    catalogue = new_catalogue()
    for model in listed(pages[0]):
        identifier = model["id"]
        catalogue["members"].add(identifier)
        if model.get("active") is False:
            catalogue["notices"][identifier] = {"what": "inactive"}
        elif chat_like(identifier):
            catalogue["candidates"][identifier] = model.get("owned_by") or ""
    return catalogue


def read_mistral(pages):
    catalogue = new_catalogue()
    for model in listed(pages[0]):
        identifier = model["id"]
        aliases = {alias for alias in model.get("aliases") or [] if isinstance(alias, str)}
        catalogue["members"].add(identifier)
        catalogue["members"].update(aliases)
        catalogue["aliases"].setdefault(identifier, set()).update(aliases)
        deprecation = model.get("deprecation")
        if deprecation:
            notice = {"what": "deprecation", "date": str(deprecation),
                      "replacement": model.get("deprecation_replacement_model")}
            for name in {identifier} | aliases:
                catalogue["notices"][name] = notice
            continue
        capabilities = model.get("capabilities")
        capabilities = capabilities if isinstance(capabilities, dict) else {}
        if (capabilities.get("completion_chat") is True and not identifier.startswith("ft:")
                and chat_like(identifier)):
            catalogue["candidates"][identifier] = model.get("name") or ""
    return catalogue


def read_plain(pages):
    """DeepSeek: an OpenAI-style list and nothing else."""
    catalogue = new_catalogue()
    for model in listed(pages[0]):
        catalogue["members"].add(model["id"])
        if chat_like(model["id"]):
            catalogue["candidates"][model["id"]] = ""
    return catalogue


def gemini_next(url, page):
    token = page.get("nextPageToken") if isinstance(page, dict) else None
    return url.split("&pageToken=")[0] + "&pageToken=" + token if token else None


def bearer(key):
    return {"Authorization": "Bearer " + key}


def google_header(key):
    return {"x-goog-api-key": key}


# name, catalogue URL, key variable, how the key is sent, how the answer is read, next page.
PROVIDERS = (
    ("openrouter", "https://openrouter.ai/api/v1/models?output_modalities=all", None, None,
     read_openrouter, None),
    ("cerebras", "https://api.cerebras.ai/public/v1/models", None, None, read_flagged, None),
    ("sambanova", "https://api.sambanova.ai/v1/models", None, None, read_flagged, None),
    ("gemini", "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
     "MODEL_DRIFT_GEMINI_API_KEY", google_header, read_gemini, gemini_next),
    ("groq", "https://api.groq.com/openai/v1/models", "MODEL_DRIFT_GROQ_API_KEY", bearer,
     read_groq, None),
    ("mistral", "https://api.mistral.ai/v1/models", "MODEL_DRIFT_MISTRAL_API_KEY", bearer,
     read_mistral, None),
    ("deepseek", "https://api.deepseek.com/models", "MODEL_DRIFT_DEEPSEEK_API_KEY", bearer,
     read_plain, None),
)
PROVIDER_NAMES = tuple(provider[0] for provider in PROVIDERS)
FREE_READABLE = {"openrouter"}


def read_catalogue(opener, url, headers, reader, next_page):
    pages = []
    while url and len(pages) < MAX_PAGES:
        page = fetch_json(opener, url, headers)
        pages.append(page)
        url = next_page(url, page) if next_page else None
    return reader(pages)


# ------------------------------------------------------------------------------------------------
# The diff
# ------------------------------------------------------------------------------------------------

def known_ids(entries, provider):
    """{id: [model_name, ...]} of the entries belonging to "provider"."""
    found = {}
    for entry in entries:
        attributed = attribute(entry["model"], entry["api_base"])
        if attributed and attributed[0] == provider:
            found.setdefault(attributed[1], []).append(entry["name"])
    return found


def diff(provider, catalogue, active, commented, ignored):
    """The findings for one provider: dicts with a "kind", an "id" and what explains it."""
    members = catalogue["members"]
    findings = []
    for identifier, names in sorted(active.items()):
        if identifier not in members:
            findings.append({"kind": "retired", "id": identifier, "names": names})
        elif identifier in catalogue["notices"]:
            findings.append({"kind": "notice", "id": identifier, "names": names,
                             "notice": catalogue["notices"][identifier]})
    for identifier, names in sorted(commented.items()):
        if identifier not in members and identifier not in active:
            findings.append({"kind": "gone", "id": identifier, "names": names})

    back = set()
    if provider == "openrouter":
        for identifier, names in sorted(commented.items()):
            twin = identifier + ":free"
            if (not identifier.endswith(":free") and twin in catalogue["candidates"]
                    and twin not in active):
                findings.append({"kind": "back", "id": twin, "names": names})
                back.add(twin)

    known = set(active) | set(commented) | set(ignored)
    for identifier, label in sorted(catalogue["candidates"].items()):
        if identifier in known or identifier in back:
            continue
        if catalogue["aliases"].get(identifier, set()) & known:
            continue
        findings.append({"kind": "new", "id": identifier, "label": label,
                         "free": provider in FREE_READABLE})
    return findings


def run_online(text, environment, opener, today):
    """Read every catalogue and diff it against the file. Returns the result the renderers read."""
    template, problems = read_template(text)
    result = {"date": today, "rules": problems, "providers": [], "unattributed": [],
              "unreadable": template is None}
    if template is None:
        return result
    result["unattributed"] = sorted({
        entry["model"] for entry in template["active"]
        if attribute(entry["model"], entry["api_base"]) is None and isinstance(entry["model"], str)
    })
    for name, url, key_variable, send_key, reader, next_page in PROVIDERS:
        active = known_ids(template["active"], name)
        commented = known_ids(template["commented"], name)
        ignored = {identifier for provider, identifier in template["ignored"] if provider == name}
        report = {"name": name, "active": len(active), "commented": len(commented),
                  "key": key_variable, "status": "read", "findings": []}
        result["providers"].append(report)
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if key_variable:
            key = (environment.get(key_variable) or "").strip()
            if not key:
                report["status"] = "no key"
                continue
            headers.update(send_key(key))
        try:
            catalogue = read_catalogue(opener, url, headers, reader, next_page)
        except FetchError as error:
            report["status"] = "error"
            report["error"] = str(error)
            continue
        report["members"] = len(catalogue["members"])
        report["candidates"] = len(catalogue["candidates"])
        report["findings"] = diff(name, catalogue, active, commented, ignored)
    return result


def exit_status(result):
    if result["unreadable"] or any(p["status"] == "error" for p in result["providers"]):
        return 2
    if result["rules"] or any(p["findings"] for p in result["providers"]):
        return 1
    return 0


# ------------------------------------------------------------------------------------------------
# The two renderings: the run's report in English, the issue's body in French
# ------------------------------------------------------------------------------------------------

KINDS = ("retired", "gone", "notice", "back", "new")


def notice_text(notice, french=False):
    what = notice.get("what")
    date = notice.get("date")
    replacement = notice.get("replacement")
    if french:
        text = {"expiration": "expiration annoncée", "deprecation": "déprécié",
                "inactive": "marqué inactif"}.get(what, what)
        if date:
            text += " (%s)" % date
        if replacement:
            text += ", remplaçant désigné : `%s`" % replacement
        return text
    text = {"expiration": "expires", "deprecation": "deprecated",
            "inactive": "listed as inactive"}.get(what, what)
    if date:
        text += " on %s" % date
    if replacement:
        text += ", replacement: %s" % replacement
    return text


def litellm_id(provider, identifier):
    """The id as the file writes it in "model:"; SambaNova's is the one that needs its provider."""
    if provider == "sambanova":
        return "openai/%s" % identifier, " on SambaNova"
    return "%s/%s" % (provider, identifier), ""


def render_text(result, config_name):
    out = ["LiteLLM model drift: %s against each provider's catalogue, %s"
           % (config_name, result["date"]), ""]
    if result["unreadable"]:
        out += ["ERROR: the file could not be read:"] + ["  " + p for p in result["rules"]]
        return "\n".join(out) + "\n"
    for report in result["providers"]:
        known = "%d active, %d commented-out id(s) here" % (report["active"], report["commented"])
        if report["status"] == "no key":
            state = "not covered (no key): %s is unset" % report["key"]
        elif report["status"] == "error":
            state = "ERROR, not read: %s" % report["error"]
        else:
            state = "read, %d model(s), %d chat candidate(s)" % (report["members"],
                                                                  report["candidates"])
        out.append("%-11s %s; %s" % (report["name"], state, known))
    if result["unattributed"]:
        count = len(result["unattributed"])
        out.append("%-11s %d active entr%s of no catalogue read here: %s"
                   % ("(none)", count, "y" if count == 1 else "ies",
                      ", ".join(result["unattributed"])))
    out.append("")

    labels = {
        "retired": "RETIRED  active here, no longer listed -- delete it and its cascade slots",
        "gone": "GONE     commented out here, no longer listed -- delete the commented-out entry",
        "notice": "NOTICE   active here, marked for removal upstream",
        "back": "BACK     commented out here, free again on OpenRouter -- reconsider its reason",
        "new": "NEW      listed upstream, unknown here",
    }
    count = 0
    for kind in KINDS:
        lines = []
        for report in result["providers"]:
            for finding in report["findings"]:
                if finding["kind"] != kind:
                    continue
                line = "  %s%s" % litellm_id(report["name"], finding["id"])
                if finding.get("names"):
                    line += " (%s)" % ", ".join(str(name) for name in finding["names"])
                if kind == "notice":
                    line += ": " + notice_text(finding["notice"])
                if kind == "new":
                    line += (": free" if finding["free"]
                             else ": to examine, its free tier is not machine-readable")
                lines.append(line)
        if lines:
            out += [labels[kind]] + lines + [""]
            count += len(lines)
    if result["rules"]:
        out.append("RULES    the file breaks the rules the offline mode holds it to")
        out += ["  " + problem for problem in result["rules"]] + [""]
        count += len(result["rules"])

    errors = sum(1 for report in result["providers"] if report["status"] == "error")
    uncovered = sum(1 for report in result["providers"] if report["status"] == "no key")
    out.append("%d finding(s), %d provider(s) in error, %d not covered (no key)."
               % (count, errors, uncovered))
    return "\n".join(out) + "\n"


def run_link():
    server = os.environ.get("GITHUB_SERVER_URL")
    repository = os.environ.get("GITHUB_REPOSITORY")
    run = os.environ.get("GITHUB_RUN_ID")
    if server and repository and run:
        return "%s/%s/actions/runs/%s" % (server, repository, run)
    return None


def capped(lines):
    if len(lines) <= MAX_LISTED:
        return lines
    return lines[:MAX_LISTED] + ["- … et %d de plus, voir le journal de l'exécution" %
                                 (len(lines) - MAX_LISTED)]


def render_issue_body(result, config_name, link=None):
    out = [ISSUE_MARKER, ""]
    out.append(
        "Rapport hebdomadaire de `.github/workflows/LiteLLM_model_drift.yml` : il compare "
        "`%s` sur `main` au catalogue que publie chaque fournisseur. **Ce texte est réécrit à "
        "chaque exécution** : ce qu'on y modifierait à la main serait perdu. L'issue se ferme "
        "d'elle-même à la première exécution sans dérive, et c'est elle qui se rouvre la fois "
        "suivante." % config_name
    )
    out.append("")
    out.append(
        "Rien n'est modifié automatiquement. La règle (`CLAUDE.md`, « The model list keeps only "
        "what can be called ») demande qu'un humain vérifie chaque constat sur la page du "
        "fournisseur, et en cite la date, avant de toucher à la liste."
    )
    out.append("")
    run = "Exécution du %s" % result["date"]
    out.append(run + (" : %s" % link if link else "") + ".")
    out.append("")

    if result["unreadable"]:
        out += ["## Fichier illisible", ""]
        out += ["- " + problem.replace("\n", " ") for problem in result["rules"]]
        return "\n".join(out) + "\n"

    sections = {
        "retired": ("Retirés : à supprimer",
                    "Entrées actives dont l'identifiant n'est plus au catalogue du fournisseur. "
                    "Supprimer l'entrée **et** ses places dans les cascades."),
        "gone": ("Entrées commentées retirées : à supprimer",
                 "Le fournisseur ne les sert plus : la règle ne garde pas de modèle retiré en "
                 "commentaire, git en garde la trace."),
        "notice": ("Retraits annoncés",
                   "Entrées actives que le fournisseur marque pour retrait : prévoir leur "
                   "remplacement dans les cascades."),
        "back": ("De nouveau gratuits sur OpenRouter",
                 "Entrées commentées dont la variante `:free` est au catalogue, à 0 $ : relire la "
                 "raison écrite au-dessus, et décommenter si elle ne tient plus."),
        "new_free": ("Nouveaux modèles gratuits sur OpenRouter",
                     "`:free` et à 0 $, sortie texte uniquement. À ajouter, ou à commenter avec "
                     "sa raison, ou à écarter par une ligne `# drift-ignore: <fournisseur>/<id> -- "
                     "<raison>` dans le fichier."),
        "new_examine": ("Nouveaux modèles à examiner",
                        "Leur gratuité ne se lit pas dans l'API du fournisseur : la vérifier sur "
                        "sa page de tarifs avant de les router, et sinon les écarter comme "
                        "ci-dessus."),
    }
    for kind in ("retired", "gone", "notice", "back", "new_free", "new_examine"):
        lines = []
        for report in result["providers"]:
            for finding in report["findings"]:
                finding_kind = finding["kind"]
                if finding_kind == "new":
                    finding_kind = "new_free" if finding["free"] else "new_examine"
                if finding_kind != kind:
                    continue
                identifier, where = litellm_id(report["name"], finding["id"])
                line = "- `%s`%s" % (identifier, where.replace(" on ", " chez "))
                if finding.get("names"):
                    line += " (%s)" % ", ".join("`%s`" % name for name in finding["names"])
                if kind == "notice":
                    line += " : " + notice_text(finding["notice"], french=True)
                if kind.startswith("new") and finding.get("label"):
                    line += " : %s" % finding["label"]
                lines.append(line)
        if lines:
            title, explanation = sections[kind]
            out += ["## %s" % title, "", explanation, ""] + capped(lines) + [""]

    if result["rules"]:
        out += ["## Règles du fichier", "",
                "Ce que le mode hors ligne du contrôle refuse, et qui est pourtant sur `main` : "
                "rien ne bloque la fusion d'un humain ici.", ""]
        out += capped(["- " + " ".join(problem.split()) for problem in result["rules"]]) + [""]

    errors = [report for report in result["providers"] if report["status"] == "error"]
    if errors:
        out += ["## Erreurs", "",
                "Catalogues qui n'ont pas pu être lus : leurs modèles ne sont ni confirmés ni "
                "déclarés retirés. Un `401` ou un `403` désigne en général une clé invalide, "
                "expirée ou révoquée, et Gemini répond `400` à une clé invalide.", ""]
        out += ["- %s : %s" % (report["name"], report["error"]) for report in errors] + [""]

    out += ["## Couverture", "",
            "| Fournisseur | État | Modèles au catalogue | Identifiants actifs ici "
            "| Commentés ici |",
            "| --- | --- | --- | --- | --- |"]
    for report in result["providers"]:
        if report["status"] == "no key":
            state = "non couvert (pas de clé : secret `%s`)" % report["key"]
            members = "—"
        elif report["status"] == "error":
            state = "erreur"
            members = "—"
        else:
            state = "lu"
            members = str(report["members"])
        out.append("| %s | %s | %s | %d | %d |" % (report["name"], state, members,
                                                    report["active"], report["commented"]))
    out.append("")
    if result["unattributed"]:
        out.append("Entrées actives d'aucun catalogue lu ici : %s."
                   % ", ".join("`%s`" % model for model in result["unattributed"]))
        out.append("")
    if exit_status(result) == 0:
        out += ["Aucune dérive.", ""]
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------------------------------------
# Verification cases, built in memory
# ------------------------------------------------------------------------------------------------

SELFTEST_TEMPLATE = """\
model_list:
  - model_name: flash
    litellm_params:
      model: gemini/gemini-9-flash
      api_key: "os.environ/GEMINI_API_KEY_SELFTEST"

  - model_name: free-one
    litellm_params:
      model: openrouter/vendor/one:free
      api_key: "os.environ/OPENROUTER_API_KEY_SELFTEST"

  - model_name: large
    litellm_params:
      model: mistral/mistral-large-latest
      api_key: "os.environ/MISTRAL_API_KEY_SELFTEST"

  - model_name: fast
    litellm_params:
      model: groq/vendor/fast
      api_key: "os.environ/GROQ_API_KEY_SELFTEST"

  - model_name: paid-direct
    litellm_params:
      model: deepseek/deepseek-v9
      api_key: "os.environ/DEEPSEEK_API_KEY_SELFTEST"

  # Served, but not routed to: paid only.
  # - model_name: paid-one
  #   litellm_params:
  #     model: openrouter/vendor/paid-one
  #     api_key: "os.environ/OPENROUTER_API_KEY_SELFTEST"
  #
  # - model_name: paid-two
  #   litellm_params:
  #     model: openrouter/vendor/paid-two
  #     api_key: "os.environ/OPENROUTER_API_KEY_SELFTEST"

  # Served at $0, but not routed to: a guardrail, not a generator.
  # - model_name: guardrail-free
  #   litellm_params:
  #     model: openrouter/vendor/guardrail:free
  #     api_key: "os.environ/OPENROUTER_API_KEY_SELFTEST"

  # ============================================================================
  # SambaNova -- not routed to: a payment method comes first.
  # ============================================================================
  # - model_name: sn-one
  #   litellm_params:
  #     model: openai/SN-One
  #     api_base: "https://api.sambanova.ai/v1"
  #     api_key: "os.environ/SAMBANOVA_API_KEY_SELFTEST"

  # drift-ignore: openrouter/vendor/noise:free -- selftest: looked at and turned down

  - model_name: local
    litellm_params:
      model: openai/auto/best-free
      api_base: "http://omniroute:20128/v1"
      api_key: "no-key-needed"

router_settings:
  fallbacks:
    - flash:
        - free-one
        - large
        - local
  model_group_alias:
    "auto": "flash"
    "auto-hidden": {"model": "free-one", "hidden": true}
"""

def holds(needle, problem):
    """Whether a problem satisfies one needle: it contains it, or with a leading "!" it does not."""
    return needle[1:] not in problem if needle.startswith("!") else needle in problem


# (what the case proves, the change made to SELFTEST_TEMPLATE as (old, new) or None, the text a
# problem must contain, or None when none is expected). A case that proves several things gives its
# text as a tuple, and one problem has to satisfy all of it -- what a YAML error quotes and the
# entry it names, say; a needle written with a leading "!" is text the problem must NOT contain.
OFFLINE_CASES = (
    ("the baseline passes, a run of commented-out entries sharing one reason included",
     None, None),
    ("a cascade target that is no entry at all is refused",
     ("        - local\n", "        - local\n        - gone\n"), 'names "gone"'),
    ("a cascade target that is only commented out is refused",
     ("        - local\n", "        - paid-one\n"), "only a commented-out entry"),
    ("a cascade whose own name is no entry is refused",
     ("    - flash:\n", "    - vanished:\n"), 'the cascade "vanished" itself'),
    ("an alias pointing nowhere is refused",
     ('"auto": "flash"', '"auto": "gone"'), 'the alias "auto"'),
    ("an alias written as a mapping is read too",
     ('{"model": "free-one"', '{"model": "gone"'), 'the alias "auto-hidden"'),
    ("a fallback under litellm_settings is read too",
     ('"hidden": true}\n', '"hidden": true}\nlitellm_settings:\n  default_fallbacks: ["gone"]\n'),
     '"litellm_settings.default_fallbacks"'),
    ("a model_name declared twice is refused",
     ("  - model_name: large\n", "  - model_name: flash\n"), 'model_name "flash" is declared 2'),
    ("a commented-out entry reusing an active name is refused",
     ("  # - model_name: paid-two\n", "  # - model_name: flash\n"), "(1 active, 1 commented out)"),
    ("a commented-out entry with no comment above it is refused",
     ("  # Served, but not routed to: paid only.\n", ""), 'entry "paid-one" gives no reason'),
    ("the entry after it in the same run is refused with it",
     ("  # Served, but not routed to: paid only.\n", ""), 'entry "paid-two" gives no reason'),
    ("a section banner is not a reason",
     ("SambaNova -- not routed to: a payment method comes first.", "SambaNova"),
     'entry "sn-one" gives no reason'),
    ("a blank line ends a run, and the entry after it needs its own reason",
     ("  #\n  # - model_name: paid-two", "\n  # - model_name: paid-two"),
     'entry "paid-two" gives no reason'),
    ("an entry with its own prose is judged on it, and inherits nothing",
     ("  #\n  # - model_name: paid-two",
      "  # A remark, and no reason.\n  # - model_name: paid-two"),
     'entry "paid-two" gives no reason'),
    ("a reason split over two lines still counts",
     ("# Served, but not routed to: paid only.", "# Served, but not\n  # routed to: paid only."),
     None),
    ("a commented-out entry that no longer parses is refused",
     ("  #     model: openrouter/vendor/paid-one\n", "  #     model: [unclosed\n"),
     "not valid YAML once uncommented"),
    ("a file that is no YAML once rendered is refused, quoting the line it was parsing from and "
     "the line it stopped at, and naming the entry",
     ("      model: openai/auto/best-free\n", "      model: [unclosed\n"),
     ("(from: model: [unclosed", "(at: ", '[entry "local"]')),
    ("an error in router_settings is quoted, and attributed to no entry",
     ("router_settings:\n", "router_settings: [x\n"),
     ("(from: router_settings: [x", "(at: ", "![entry ")),
    ("a file whose rendering has no model_list is refused",
     ("model_list:\n", "models:\n"), 'has no "model_list" list'),
    ("a drift-ignore without its reason is refused",
     (" -- selftest: looked at and turned down", ""), '"drift-ignore:" line must read'),
    ("a drift-ignore naming no known provider is refused",
     ("drift-ignore: openrouter/", "drift-ignore: nowhere/"), "names no provider"),
)


# The shape of "templates/LiteLLM_config.yaml.j2" in miniature: a "set" table of heads, provider blocks under
# "if", a cascade whose members are conditional, and an alias section with a branch for a missing Gemini
# key. Rendered with every key given it is a plain configuration that passes.
SELFTEST_JINJA_TEMPLATE = """\
{% set has = {
  'Gemini': Artificial_Intelligence_LiteLLM_Gemini_API_key is string and Artificial_Intelligence_LiteLLM_Gemini_API_key | length > 0,
  'Groq': Artificial_Intelligence_LiteLLM_Groq_API_key is string and Artificial_Intelligence_LiteLLM_Groq_API_key | length > 0,
  'OpenRouter': Artificial_Intelligence_LiteLLM_OpenRouter_API_key is string and Artificial_Intelligence_LiteLLM_OpenRouter_API_key | length > 0
} %}
{% set head = {
  'flash': 'fast' if has.Groq else 'free-one' if has.OpenRouter else 'local'
} %}
{% set to = {
  'flash': 'flash' if has.Gemini else head['flash']
} %}
model_list:
{% if has.Gemini %}
  - model_name: flash
    litellm_params:
      model: gemini/gemini-9-flash
      api_key: "os.environ/GEMINI_API_KEY_SELFTEST"

{% endif %}
{% if has.Groq %}
  - model_name: fast
    litellm_params:
      model: groq/vendor/fast
      api_key: "os.environ/GROQ_API_KEY_SELFTEST"

  # Served, but not routed to: paid only.
  # - model_name: paid-fast
  #   litellm_params:
  #     model: groq/vendor/paid-fast
  #     api_key: "os.environ/GROQ_API_KEY_SELFTEST"

{% endif %}
{% if has.OpenRouter %}
  - model_name: free-one
    litellm_params:
      model: openrouter/vendor/one:free
      api_key: "os.environ/OPENROUTER_API_KEY_SELFTEST"

{% endif %}
  - model_name: local
    litellm_params:
      model: openai/auto/best-free
      api_base: "http://omniroute:20128/v1"
      api_key: "no-key-needed"

router_settings:
  fallbacks:
{% if to['flash'] %}
    - flash:
{% if has.Groq %}
        - fast
{% endif %}
{% if has.OpenRouter %}
        - free-one
{% endif %}
        - local
{% endif %}
  model_group_alias:
{% if not has.Gemini %}
{% for router in ['flash'] if head[router] %}
    "{{ router }}": "{{ head[router] }}"
{% endfor %}
{% endif %}
{% if to['flash'] %}
    "auto": "{{ to['flash'] }}"
{% endif %}
"""

# Same shape as OFFLINE_CASES, applied to SELFTEST_JINJA_TEMPLATE.
JINJA_CASES = (
    ("a template rendered with every key given passes: blocks under \"if\", a table of heads, a "
     "cascade of conditional members, and an alias section with a branch for a missing key",
     None, None),
    ("the branch written only when a Gemini key is missing is not read",
     ('"{{ router }}": "{{ head[router] }}"', '"{{ router }}": "nowhere"'), None),
    ("an alias target that names no entry of the rendering is refused",
     ("'flash': 'flash' if has.Gemini", "'flash': 'vanished' if has.Gemini"), 'names "vanished"'),
    ("a cascade member that is a commented-out entry inside an \"if\" block is refused",
     ("        - fast\n", "        - paid-fast\n"), "only a commented-out entry"),
    ("a commented-out entry inside an \"if\" block is held to its reason",
     ("  # Served, but not routed to: paid only.\n", ""), 'entry "paid-fast" gives no reason'),
    ("a statement line between a reason and its commented-out entry takes nothing from the reason",
     ("not routed to: paid only.\n  # - model_name: paid-fast",
      "not routed to: paid only.\n{% set unused = 1 %}\n  # - model_name: paid-fast"), None),
    ("a Jinja syntax error is a finding that names the template line",
     ("{% endif %}\n  - model_name: local", "{% endiff %}\n  - model_name: local"),
     "not valid Jinja (template line "),
    ("a Jinja syntax error in a block left open names the block's opener, not the end of the file",
     ("{% endif %}\n  - model_name: local", "  - model_name: local"),
     "the block opened at template line %d is never closed"
     % (SELFTEST_JINJA_TEMPLATE.split("\n").index("{% if has.OpenRouter %}") + 1)),
    ("a variable that is none of the five keys is a finding",
     ("\"auto\": \"{{ to['flash'] }}\"",
      '"auto": "{{ Artificial_Intelligence_LiteLLM_Cerebras_API_key }}"'), "none of the five"),
    ("a sixth key read the way the template reads the five is a finding too, though \"is string\" "
     "would take it for a key that is not given",
     ("  'OpenRouter': Artificial_Intelligence_LiteLLM_OpenRouter_API_key is string and "
      "Artificial_Intelligence_LiteLLM_OpenRouter_API_key | length > 0\n} %}",
      "  'OpenRouter': Artificial_Intelligence_LiteLLM_OpenRouter_API_key is string and "
      "Artificial_Intelligence_LiteLLM_OpenRouter_API_key | length > 0,\n"
      "  'Cerebras': Artificial_Intelligence_LiteLLM_Cerebras_API_key is string and "
      "Artificial_Intelligence_LiteLLM_Cerebras_API_key | length > 0\n} %}"), "none of the five"),
    ("a filter only Ansible provides, outside any conditional, is refused as a limit of this "
     "check's plain Jinja2, and the message says so",
     ("router_settings:\n", "router_settings:\n  # {{ 1 | to_json }}\n"),
     ("cannot be rendered with plain Jinja2 (template line ", "only Ansible provides")),
    ("a filter only Ansible provides, inside an \"if\", is refused the same way",
     ("\"{{ to['flash'] }}\"", "\"{{ 1 | to_json }}\""),
     ("cannot be rendered with plain Jinja2", "only Ansible provides")),
    ("a test only Ansible provides is refused the same way",
     ("\"{{ to['flash'] }}\"", "\"{{ 'x' is match('x') }}\""),
     ("cannot be rendered with plain Jinja2", "only Ansible provides")),
    ("a template that fails while it renders is a finding",
     ("\"auto\": \"{{ to['flash'] }}\"", '"auto": "{{ 1 // 0 }}"'), "ZeroDivisionError"),
    ("a template is rendered in a sandbox, out of reach of Python's internals",
     ("\"auto\": \"{{ to['flash'] }}\"", "\"auto\": \"{{ ''.__class__ }}\""), "unsafe"),
)


def openrouter_model(identifier, price="0", outputs=("text",), expiration=None):
    return {"id": identifier, "name": identifier,
            "pricing": {"prompt": price, "completion": price},
            "architecture": {"output_modalities": list(outputs)},
            "expiration_date": expiration}


def selftest_answers():
    """Canned catalogues matching SELFTEST_TEMPLATE exactly: no drift at all."""
    return {
        "openrouter": {"data": [
            openrouter_model("vendor/one:free"),
            openrouter_model("vendor/paid-one", price="0.000001"),
            openrouter_model("vendor/paid-two", price="0.000001"),
            openrouter_model("vendor/guardrail:free"),
            openrouter_model("vendor/noise:free"),
            openrouter_model("vendor/painter:free", outputs=("image",)),
            openrouter_model("vendor/zero-but-not-free"),
            openrouter_model("vendor/voice-tts:free"),
        ]},
        "cerebras": {"object": "list", "data": []},
        "sambanova": {"data": [{"id": "SN-One"}]},
        "gemini": [
            {"models": [{"name": "models/gemini-9-flash",
                         "supportedGenerationMethods": ["generateContent"]}],
             "nextPageToken": "second"},
            {"models": [{"name": "models/text-embedding-9",
                         "supportedGenerationMethods": ["embedContent"]}]},
        ],
        "groq": {"data": [{"id": "vendor/fast", "active": True},
                          {"id": "whisper-large-v9", "active": True}]},
        "mistral": {"data": [
            {"id": "mistral-large-2609", "aliases": ["mistral-large-latest"],
             "capabilities": {"completion_chat": True}},
            {"id": "mistral-large-latest", "aliases": ["mistral-large-2609"],
             "capabilities": {"completion_chat": True}},
            {"id": "mistral-embed", "capabilities": {"completion_chat": False}},
        ]},
        "deepseek": {"data": [{"id": "deepseek-v9"}]},
    }


SELFTEST_KEYS = {
    "MODEL_DRIFT_GEMINI_API_KEY": "selftest-gemini-key-SECRET",
    "MODEL_DRIFT_GROQ_API_KEY": "selftest-groq-key-SECRET",
    "MODEL_DRIFT_MISTRAL_API_KEY": "selftest-mistral-key-SECRET",
    "MODEL_DRIFT_DEEPSEEK_API_KEY": "selftest-deepseek-key-SECRET",
}


def canned_opener(answers, calls):
    """An opener serving "answers" by provider. An answer that is an exception is raised."""
    urls = {name: url for name, url, _, _, _, _ in PROVIDERS}

    def opener(url, headers):
        calls.append((url, dict(headers)))
        for name, base in urls.items():
            if not url.startswith(base):
                continue
            answer = answers[name]
            if isinstance(answer, Exception):
                raise answer
            if name == "gemini":
                answer = answer[1] if "&pageToken=second" in url else answer[0]
            return json.dumps(answer).encode()
        raise AssertionError("unexpected URL in selftest: %s" % url)
    return opener


def leaky_401(provider):
    """A 401 whose body echoes the key back, the way DeepSeek's does."""
    body = io.BytesIO(b'{"error": {"message": "Your api key: selftest-%s-key-SECRET is invalid"}}'
                      % provider.encode())
    return urllib.error.HTTPError("https://selftest.invalid/", 401, "Unauthorized", None, body)


def online_cases():
    """(what the case proves, template, environment, answers, the (kind, id) findings expected,
    the exit status expected, and a check on (result, calls, report, body) returning None when it
    holds, and why not otherwise)."""
    base = selftest_answers()

    def changed(provider, value):
        answers = selftest_answers()
        answers[provider] = value
        return answers

    def openrouter_with(*extra, without=()):
        data = [model for model in base["openrouter"]["data"] if model["id"] not in without]
        return {"data": data + list(extra)}

    def no_secret(result, calls, report, body):
        leaked = [text for text in (report, body) if "SECRET" in text]
        return "a key or an echoed key reached the output" if leaked else None

    def keys_in_headers_only(result, calls, report, body):
        for url, headers in calls:
            if "SECRET" in url:
                return "a key was put in a URL: %s" % url
        if not any("SECRET" in value for _, headers in calls for value in headers.values()):
            return "no key was sent at all"
        return None

    def no_groq_call(result, calls, report, body):
        if any("groq" in url for url, _ in calls):
            return "a provider with no key was called anyway"
        if "not covered (no key): MODEL_DRIFT_GROQ_API_KEY" not in report:
            return "the report does not say which key is missing"
        if "MODEL_DRIFT_GROQ_API_KEY" not in body:
            return "the issue body does not name the missing secret"
        return None

    def french_body(result, calls, report, body):
        for needle in (ISSUE_MARKER, "## Retirés : à supprimer", "`openrouter/vendor/one:free`",
                       "## Couverture"):
            if needle not in body:
                return "the issue body lacks %r" % needle
        return None

    def second_page_read(result, calls, report, body):
        if not any("&pageToken=second" in url for url, _ in calls):
            return "the second page was never asked for"
        return None

    def rewritten(old, new):
        """SELFTEST_TEMPLATE with one change, which must apply: else the case proves nothing."""
        assert old in SELFTEST_TEMPLATE, "%r is not in SELFTEST_TEMPLATE" % old
        return SELFTEST_TEMPLATE.replace(old, new, 1)

    # The same file, with the id of "flash" computed and its entry under a statement: it only
    # compares equal to the catalogue once rendered.
    needs_rendering = "{% set flash_id = 'gemini-9-flash' %}\n" + rewritten(
        "model: gemini/gemini-9-flash", "model: gemini/{{ flash_id }}")

    def unreadable(result, calls, report, body):
        if not result["unreadable"]:
            return "a template that does not render was not reported as unreadable"
        if "## Fichier illisible" not in body or "not valid Jinja" not in body:
            return "the issue body does not say the file could not be read, nor why"
        if calls:
            return "a catalogue was read although the file could not be"
        return None

    no_drift = []
    return (
        ("the baseline reports nothing: an alias, a filtered model, a drift-ignore, a commented "
         "free guardrail and a $0 id without \":free\" are all quiet",
         SELFTEST_TEMPLATE, SELFTEST_KEYS, base, no_drift, 0, keys_in_headers_only),
        ("an active id the catalogue no longer lists is RETIRED, and the French body says so",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         changed("openrouter", openrouter_with(without=("vendor/one:free",))),
         [("retired", "vendor/one:free")], 1, french_body),
        ("a commented-out id the catalogue no longer lists is GONE",
         SELFTEST_TEMPLATE, SELFTEST_KEYS, changed("sambanova", {"data": []}),
         [("gone", "SN-One")], 1, None),
        ("a commented-out paid id whose :free twin appears is BACK, and not NEW as well",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         changed("openrouter", openrouter_with(openrouter_model("vendor/paid-one:free"))),
         [("back", "vendor/paid-one:free")], 1, None),
        ("a new :free text model is NEW, a new image one is not",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         changed("openrouter", openrouter_with(openrouter_model("vendor/fresh:free"),
                                               openrouter_model("vendor/other-painter:free",
                                                                outputs=("text", "image")))),
         [("new", "vendor/fresh:free")], 1, None),
        ("an expiration date on an active OpenRouter id is a NOTICE",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         changed("openrouter", openrouter_with(
             openrouter_model("vendor/one:free", expiration="2026-12-01"),
             without=("vendor/one:free",))),
         [("notice", "vendor/one:free")], 1, None),
        ("a Mistral deprecation on an active alias is a NOTICE",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         changed("mistral", {"data": [
             {"id": "mistral-large-2609", "aliases": ["mistral-large-latest"],
              "capabilities": {"completion_chat": True}, "deprecation": "2026-12-31",
              "deprecation_replacement_model": "mistral-large-2612"},
         ]}),
         [("notice", "mistral-large-latest")], 1, None),
        ("a new Mistral chat model is NEW, and never claimed free",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         changed("mistral", {"data": base["mistral"]["data"] + [
             {"id": "magistral-9", "capabilities": {"completion_chat": True}}]}),
         [("new", "magistral-9")], 1,
         lambda result, calls, report, body: (
             None if "## Nouveaux modèles à examiner" in body and "gratuits" not in
             body.split("## Nouveaux modèles à examiner")[1].split("##")[0]
             else "a NEW Mistral model was not listed as one to examine")),
        ("Gemini's second page is read, and a chat model found there is NEW",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         changed("gemini", [base["gemini"][0], {"models": [
             {"name": "models/gemini-10-pro", "supportedGenerationMethods": ["generateContent"]},
             {"name": "models/gemini-10-flash-tts",
              "supportedGenerationMethods": ["generateContent"]}]}]),
         [("new", "gemini-10-pro")], 1, second_page_read),
        ("a Groq model listed as inactive is a NOTICE",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         changed("groq", {"data": [{"id": "vendor/fast", "active": False}]}),
         [("notice", "vendor/fast")], 1, None),
        ("a provider with no key is not covered, never called, and no drift",
         SELFTEST_TEMPLATE, dict(SELFTEST_KEYS, MODEL_DRIFT_GROQ_API_KEY="  "), base, no_drift,
         0, no_groq_call),
        ("a 401 is an error: its body is never shown, and nothing is declared retired",
         SELFTEST_TEMPLATE, SELFTEST_KEYS, changed("deepseek", leaky_401("deepseek")),
         no_drift, 2, no_secret),
        ("a network failure is an error, not a catalogue of zero models",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         changed("openrouter", urllib.error.URLError("selftest: no route")), no_drift, 2, None),
        ("an answer of the wrong shape is an error",
         SELFTEST_TEMPLATE, SELFTEST_KEYS, changed("cerebras", {"unexpected": 1}), no_drift, 2,
         None),
        ("an error outranks another provider's drift in the exit status",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         dict(changed("deepseek", leaky_401("deepseek")),
              openrouter=openrouter_with(without=("vendor/one:free",))),
         [("retired", "vendor/one:free")], 2, no_secret),
        ("a file that needs rendering is compared with the catalogue once rendered, not as written",
         needs_rendering, SELFTEST_KEYS, base, no_drift, 0, keys_in_headers_only),
        ("a template that does not render is unreadable: exit 2, no catalogue read, and the French "
         "body says why",
         SELFTEST_TEMPLATE + "{% if %}\n", SELFTEST_KEYS, base, no_drift, 2, unreadable),
        ("a rule broken on main is reported online too",
         SELFTEST_TEMPLATE.replace("        - local\n", "        - gone\n"), SELFTEST_KEYS, base,
         no_drift, 1,
         lambda result, calls, report, body: (
             None if "## Règles du fichier" in body and result["rules"]
             else "the broken rule is not in the issue body")),
    )


def run_selftest():
    """Prove that every rule refuses what it claims to refuse, and lets the baseline through."""
    failures = 0

    for base, cases in ((SELFTEST_TEMPLATE, OFFLINE_CASES), (SELFTEST_JINJA_TEMPLATE, JINJA_CASES)):
        for purpose, change, needle in cases:
            text = base
            if change is not None:
                old, new = change
                if old not in text:
                    failures += 1
                    print("selftest: BROKEN CASE (%s) -- %r is not in the template"
                          % (purpose, old))
                    continue
                text = text.replace(old, new, 1)
            template, problems = read_template(text)
            needles = needle if isinstance(needle, tuple) else (needle,)
            if needle is None:
                passed = template is not None and not problems
            else:
                passed = any(all(holds(each, problem) for each in needles) for problem in problems)
            if passed:
                print("selftest: ok -- %s" % purpose)
            else:
                failures += 1
                print("selftest: FAILED (%s) -- expected %s, got %r"
                      % (purpose, "no problem" if needle is None else repr(needle), problems))

    for purpose, text, environment, answers, expected, status, check in online_cases():
        calls = []
        result = run_online(text, environment, canned_opener(answers, calls), "2026-01-01")
        found = sorted((finding["kind"], finding["id"])
                       for report in result["providers"] for finding in report["findings"])
        report = render_text(result, "selftest")
        body = render_issue_body(result, "selftest", link=None)
        why = None
        if found != sorted(expected):
            why = "findings %r, expected %r" % (found, sorted(expected))
        elif exit_status(result) != status:
            why = "exit status %d, expected %d" % (exit_status(result), status)
        elif check is not None:
            why = check(result, calls, report, body)
        if why is None:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s) -- %s" % (purpose, why))

    return 1 if failures else 0


# ------------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true",
                        help="verify the check against its in-memory cases, with no network")
    parser.add_argument("--online", action="store_true",
                        help="read every provider's catalogue and report the drift")
    parser.add_argument("--issue-body", metavar="PATH",
                        help="with --online, write the rolling issue's body (French) to PATH")
    parser.add_argument("--config", metavar="PATH", default=str(CONFIG),
                        help="the LiteLLM configuration to read (default: %(default)s)")
    arguments = parser.parse_args()

    if arguments.selftest:
        return run_selftest()
    if arguments.issue_body and not arguments.online:
        parser.error("--issue-body needs --online")

    path = Path(arguments.config)
    try:
        shown = str(path.resolve().relative_to(ROOT))
    except ValueError:
        shown = str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print("%s: unreadable (%s)." % (shown, error.__class__.__name__))
        return 2

    if not arguments.online:
        template, problems = read_template(text)
        if template is None:
            print("%s: %s" % (shown, problems[0]))
            return 2
        if problems:
            print("LiteLLM model list: %d problem(s) in %s.\n" % (len(problems), shown))
            for problem in problems:
                print(problem + "\n")
            return 1
        print("LiteLLM model list: %s, rendered with every provider key given, holds %d active and "
              "%d commented-out entries, every cascade and alias names an active one, no name "
              "twice, every commented-out entry gives its reason."
              % (shown, len(template["active"]), len(template["commented"])))
        return 0

    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    result = run_online(text, os.environ, urllib_opener, today)
    sys.stdout.write(render_text(result, shown))
    if arguments.issue_body:
        Path(arguments.issue_body).write_text(render_issue_body(result, shown, link=run_link()),
                                              encoding="utf-8")
    return exit_status(result)


if __name__ == "__main__":
    sys.exit(main())
