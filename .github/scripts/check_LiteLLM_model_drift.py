#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77
# SPDX-License-Identifier: AGPL-3.0-only

"""Hold LiteLLM's model list to its rule, report where it has drifted, and delete what is retired.

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
the weekly issue it feeds, exist to see it; the deletion of what a provider has retired, which nobody
should have to do by hand, is its third mode.

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
* "--apply" edits the file AS WRITTEN, and has to know which line is which, which the rendering
  cannot say. So it reads the file a second time with its Jinja made parsable -- comments and
  statements blanked, expressions turned into a word, every line left on its own number -- and
  holds that reading to say the same as the rendering: the same entries in the same order, the
  same commented-out entries. If it does not (a branch written only for some of the keys, an
  "else", a loop that repeats an entry), nothing is edited. A model named inside a statement or an
  expression is not deleted either, since nothing here can edit what a statement computes -- except
  the rows of the template's "head" table, which name the model each router is an alias of: they
  copy the order of the cascades, are written again from them after a deletion, and only when
  writing them that way gives the table as it stands (see "THE HEAD TABLE" below). A statement
  that opens or closes a block wider than the entry it sits next to is not part of that entry, and
  stays; the block is left empty, which Jinja renders as nothing.

THREE MODES
-----------
Offline, the default, run on every pull request. It reads the file and nothing else:

  (a) every fallback cascade member (source and targets, under the four fallback keys of both
      "router_settings" and "litellm_settings") and every "model_group_alias" target names an
      ACTIVE "model_name" -- a commented-out entry is not one. A cascade's SOURCE may also be a
      "model_group_alias" key of the same section: LiteLLM looks for fallbacks under the name that was
      asked for, so an alias has a cascade of its own (#300), and the proxy accepts an alias as a name;
  (b) no "model_name" is declared twice, counting commented-out entries: uncommenting one is the
      documented way back, and would then create the duplicate. LiteLLM itself accepts duplicates
      -- it is how it load-balances -- so the day this file wants one, this rule is the line to
      change, knowingly;
  (c) every commented-out entry carries its reason (defined below);
  (d) every "# drift-ignore:" line is well formed and gives its reason.

"--online" reads each provider's model catalogue as well, and reports the drift: it prints a
plain-text report and, with "--issue-body PATH", writes the body of the rolling issue
".github/workflows/LiteLLM_model_drift.yml" keeps up to date. That body is in French, since an issue
is read by the maintainers (CLAUDE.md, "Language"); the report is English, like any run's output.
Exit status: 0 no drift, 1 drift, 2 a provider, or the file itself, could not be read (an error outranks
drift, since it means the report is incomplete), 70 a crash: the script's own bug, or an
answer it could not read at all, which prints the kind of error and where and never its message.
An uncaught exception would exit 1 and be read as drift, which is why a crash has a status of its
own. The offline rules are applied in this mode too: nothing blocks a human's merge here, so a red
pull request can still land on main, and the weekly run is the next place it shows.
"--coverage PATH" writes "complete" or "partial" to PATH: "partial" when a provider was not read
(no key, or an error), whatever the exit status says, since a provider that is not covered yields
no finding and a run can exit 0 having seen only some of the catalogues. "--undeleted PATH" writes
how many RETIRED and GONE findings the run did not delete (all of them without "--apply"), and no
file at all when the model list could not be read: a deletion pull request is closed over "nothing
left to delete" only when that is 0, since a run that changed nothing may also have refused
everything, and a model it refused to delete is still retired.

"--online --apply" is the same run, and then deletes what can be deleted (see below). It rewrites
the file given by "--config" IN PLACE, so it is run on a checkout that can be thrown away, as the
workflow does. The exit status is the one "--online" gives: a deletion made is still a drift until
it is merged. "--pr-body PATH" and "--commit-message PATH" write the body of the pull request
(French) and the message of the commit (English) that carry the deletions, and only when something
was deleted; a file left at that path by an earlier run is removed first.

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
above the first of them -- the SambaNova block is one such run. An entry after a
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

In the issue, every NEW id comes with an entry to complete, ready to paste: the "model:" with its
provider prefix, a model_name proposed the way the file's own names are made (the id with its dots
turned to dashes, and the provider's name as a suffix for the providers whose names carry one, a
name already taken getting it anyway), and the "api_key" and "api_base" most of that provider's
existing entries use, the first being the name of the environment variable the key is read from. A
provider with no entry yet gets a placeholder for the key. Pasted as it is, it is an active entry;
for one that is not routed to, a "# " goes in after the two spaces of indentation of each line, as
the file's other commented-out entries have it (a "# " in front of the indentation is a comment
this check does not read as an entry), and the reason goes above, with the provider's page and the
date, which only a person can write. The snippets are left out when they would take the issue past
the size GitHub accepts.

DELETING WHAT A PROVIDER HAS RETIRED
------------------------------------
RETIRED and GONE are the one kind of finding that needs no judgment: the provider's own catalogue
no longer lists the id, so the model cannot be called, and CLAUDE.md says what becomes of such a
model. "--apply" deletes, for each such id, in a single pass over the file:

* every entry attributed to it, active or commented out, and the model_name's slot in each of the
  four fallback keys of both sections. The blank line that separated an active entry from the next
  goes with it, unless the entry had prose above it.
* of a commented-out entry, the reason prose that belongs to it alone. A run of entries shares the
  reason above its first (see above), so the reason stays while an entry of the run does, now over
  the first that stays, and goes when the last one does. A section banner goes with a run only when
  the banner is itself the reason ("SambaNova -- not routed to: ..."); one that is a heading over
  entries that may stay ("Cerebras & Groq") is kept, and so is a "# drift-ignore:" line, which is a
  statement about an id and not about the run.

What it leaves where it is, because only a person can tell, is every comment: none is rewritten, and
a comment can say what is no longer so. Verification reads the structure of the file, not its
prose, so the pull request body lists under "À relire", by their line numbers in the new file,
the places a deletion may have made false:

* the comment above a deleted ACTIVE entry, which may describe that entry or the group it opens;
* the reason over a run of commented-out entries some of which are gone, kept over the ones that
  stay, which may count them ("All seven ids below") or name one that is gone;
* a section banner left over no entry at all;
* any other comment line naming a deleted model_name, or a deleted id that no entry that stays
  carries (a word match, so "gemini-3-8-flash" is found and "gemini-3-8-flash-lite" is not).

That list is what the tool can find, not everything a deletion may have made false. It does not
see a heading that names a provider none of whose entries is left ("Cerebras & Groq" over the
Groq entries alone), nor a provider-qualified mention ("distinct from Groq's qwen3.8-27b") of an
id that a surviving entry of another provider carries too, which the bare-id match leaves alone.
The pull request is read by a person, whose job this is.

What it refuses to delete, leaving the finding in the issue with the reason, and writing nothing
for that model (all of its entries or none):

* a model_name that a cascade starts from (the virtual routers: "pro", "flash"...), or that a
  "model_group_alias" points at, since what should answer for that name is a choice;
* the last target of a cascade, decided on the whole set at once and for each set of provider keys
  separately, not on the union: the cascade that holds the members of a single provider is empty
  for every set of keys that leaves that provider out. Two models that are each the other's only
  companion in a cascade are neither of them deleted;
* a cascade slot that is not a line of its own (a flow list, "- flash: free-one"), which this does
  not edit, and a name that is used anywhere else in the file, which it knows nothing about: in a
  Jinja statement or expression (the rows of a "head" table it can write back apart), or in a place
  the YAML reading does not declare;
* a deletion that would take part of a Jinja block, or a line of a Jinja statement that runs over
  several lines. The statements that open or close a block wider than the entry they sit next to --
  the "{% endif %}" after the last entry of a provider's block, the "{% if %}" of the next block --
  are not part of that entry: they stay, and the block is left empty, which renders as nothing. What
  the net behind that does refuse is a set of lines that takes a statement of a block and leaves
  another part of the same block behind: the "else" branch re-parented under the "if" condition,
  the entry after an "{% endif %}{% if %}" handed the condition of the one deleted. A statement
  that opens no block ("set x = 1", "include") is never taken, and a file whose blocks do not pair
  up is not edited at all;
* anything whose result fails verification, whatever the reason: each deletion is tried alone and
  read back, then all of them together. The result must parse; it must break no offline rule the
  original did not already break; it must have as many Jinja blocks opened as closed, as a second
  net behind the check above; and it must be, parsed, the original model list without the deleted
  entries and the original cascades without their slots, with the commented-out entries and the
  "drift-ignore:" lines the original had besides -- and the same for the file rendered with each
  set of provider keys, none of which may be left with an empty cascade. That comparison is written
  apart from the editing, so that the one is not wrong in the way of the other;
* a commented-out entry whose body goes on past a bare "#" line, which cannot be told from prose;
* every id of a provider whose catalogue lists no model at all: an empty answer is a failed read,
  not a provider that retired everything. A catalogue that could not be read (an HTTP error, a
  wrong shape) yields no finding to begin with, as ever;
* every id of a provider whose catalogue omits more than half of the ids the file holds for it,
  once that is three or more: a short but valid answer (a key that sees another tier, a truncated
  page, a provider in an incident) is what a mass retirement looks like too, and a deletion pull
  request of a hundred lines rewritten every week on its word is not worth the risk. The issue
  lists them, and a person decides.

THE HEAD TABLE
--------------
A router is an alias of the first model of its cascade whose provider has a key, and the template
says which in a "set head" table, one row per router: "'flash': 'a' if has.Groq else 'b' if
has.Mistral else 'c'". That is a copy of the order of the cascades, and a deletion that takes a
model a row names has to write the row again. It is written FROM THE CASCADES and never patched: the
file is rendered for every set of providers, the first member of each router's cascade is read, and
the row is made of the providers in the order their first member comes in the cascade, with the
model that is there whatever the keys as its last term (or "false" when there is none). The row is
checked against every set of providers before it is kept. Taking a provider's first model out can
move the provider behind another, which is why a name is not simply replaced.

A row is written again only when the same writing gives exactly the row as it stands in the
untouched file: a row tuned by hand, or already out of step with its cascade, is not trusted, and
its models are refused as before. The result must also leave every alias on the first member of the
cascade kept under its name, for every set of providers. A pull request that rewrites a row ADDS
lines, so `dependabot-auto-merge.yml` does not merge it by itself: a person reads the rows, which
the pull request lists. And the job of "LiteLLM_model_drift.yml" that pushes it, which holds the
token that writes, accepts a changed line only if it is such a row, naming entries of the file and
providers the template declares ("check_drift_publish_guard.py" plays that rule).

THE RANKINGS
------------
Where a NEW model would go in a cascade is a question of figures, which someone used to look up by
hand: the report now carries them. With MODEL_DRIFT_ARTIFICIAL_ANALYSIS_API_KEY set, the run reads
Artificial Analysis's free API (GET https://artificialanalysis.ai/api/v2/data/llms/models, the key in
the "x-api-key" header, 1,000 requests a day, one made per run) and the issue gains a table of each
NEW model's intelligence index, coding index, output speed and blended price, then a suggested place
per router: before the first member of that router's cascade the ranking scores lower on the figure
that decides it (intelligence for "pro", "flash" and "claude-code", coding for "code", speed for
"flash-lite"), or after the last one. The source is named in the issue with its day, as the terms of
use of that API ask, and the figures are shown as published.

* It is optional the way a provider's key is, and no more than that: without the key the report says
  "not covered" and the run is the same; a failed read is reported, with the HTTP status and nothing
  else, and changes neither the exit status, nor what the run covers, nor what it deletes. The
  ranking is not a catalogue of a provider, so it is kept out of "result[providers]" for this.
* The matching is a guess and is shown as one. A NEW model is matched to an entry of the ranking
  only when the last segment of its id, or the provider's name for it, equals that entry's slug or
  name once squashed to lower-case letters and digits, of four characters at least ("o3" says too
  little), and only when exactly one entry does: two is no answer. Every matched row says by which
  of the two it was matched, and is to be checked before a place is taken from it. The members of a
  cascade are matched the same way, the ones the ranking does not know being left out of the count,
  which the place states ("3 membre(s) classé(s) sur 5").
* A place is a suggestion, never applied by anything: it compares one figure. The one eligibility it
  does judge is speed, for "flash" and "flash-lite", the routers whose cascade is chosen for it: a
  model slower than the slowest member the ranking knows a speed of is given no place, and one whose
  speed is unknown (or against which no member has a speed) is said not evaluated. A speed of zero or
  less is read as unknown, since the real answer gave 0.0 to models that serve (an inference from what
  was observed: the API's reference does not say what it sends for a speed it did not measure). It says
  nothing of the rest of what makes a model eligible (tool calls and context for "claude-code", the
  free tier, the reasoning-effort variant a match can land on) nor of how a cascade also groups its
  models by provider.
* The answer is untrusted text like a catalogue's: names are cut to plain words, a figure that is
  not a finite number is none, and the key is replaced by "***" wherever an error could carry it. The
  job that writes holds no such key, as with the others.

UNTRUSTED TEXT
--------------
What a catalogue says -- an id, a name, a date -- ends up in the log, in an issue, in a pull request
and in a snippet someone pastes, and is read as untrusted. An id is offered as NEW only when it is
spelt the way ids are (letters, digits and "._:/+~-", no "::", no "//", so that no address and no
workflow command can be one); any other piece of an answer that is shown is cut to plain words, in
which no newline, backtick, "@", angle bracket, square bracket or "::" survives, and is shown in a
code span. The catalogue's members are never filtered, since an id is retired by not being among
ALL of them. No key and no response body is ever printed: a failed read says its HTTP status and
nothing else (the reason phrase can carry a key as the body can, and HTTP/2 has none), whatever
else of an error is shown has every key of the run replaced by "***", and the issue shows it in a
code span. A redirect is never followed, since the keys travel in the
headers of the request, which urllib sends again to wherever the redirect points: it is reported
as the HTTP status it is.

A catalogue that could not be read is an error for that provider, reported with the HTTP status and
nothing else: the answer's body is never printed, because a provider may echo the key back in it
(DeepSeek does: "Your api key: ****ogus is invalid", measured with a bogus key). Above all, a failed
read never turns into "every model retired".

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
* It never adds a model, and never writes a reason. Every claim in the list cites the provider's
  own page and the date it was checked. A deletion can cite the catalogue it read and the day it
  read it, and the pull request body does; an addition is a choice, and a reason is somebody's
  statement, so what the check produces for those -- NEW, BACK, NOTICE -- is where a person's
  check starts, not a substitute for it.
* It opens no pull request and pushes nothing: it edits a file and writes the texts it is given
  a path for (the issue, the pull request, the commit message, the coverage and the count of what
  it did not delete). The workflow that runs it does the rest.
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
* It does not decide where a model goes. The rankings give a number and a suggested place; the order
  of a cascade stays a choice made by a person, with the router's other constraints in mind.

Its verification cases are Python literals rather than fixture files, for the reason CLAUDE.md
gives: a fixture on disk is reachable by "ansible-lint --fix", which has rewritten one here before.
The online cases are fed canned catalogues, so "--selftest" needs no network and no key.

Run it from the repository root:

    python3 .github/scripts/check_LiteLLM_model_drift.py --selftest
    python3 .github/scripts/check_LiteLLM_model_drift.py
    python3 .github/scripts/check_LiteLLM_model_drift.py --online --issue-body /tmp/body.md

and, on a checkout you can throw away, what the workflow runs:

    python3 .github/scripts/check_LiteLLM_model_drift.py --online --apply --issue-body /tmp/body.md \\
        --pr-body /tmp/pull_request.md --commit-message /tmp/commit.txt \\
        --coverage /tmp/coverage.txt --undeleted /tmp/undeleted.txt
"""

import argparse
import collections
import contextlib
import copy
import datetime
import difflib
import http.client
import http.server
import io
import itertools
import json
import os
import re
import runpy
import sys
import tempfile
import textwrap
import threading
import traceback
import urllib.error
import urllib.parse
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
JINJA_EXPRESSION = re.compile(r"\{\{.*?\}\}", re.DOTALL)
JINJA_STATEMENT = re.compile(r"\{%.*?%\}", re.DOTALL)
JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)
JINJA_COMMENT_LINE = re.compile(r"^\s*\{#.*#\}\s*$")
JINJA_TAG = re.compile(r"\{%-?\s*(end)?(\w+)(.*?)-?%\}", re.DOTALL)
# The Jinja statements that open a block and the "end..." that closes it.
JINJA_BLOCKS = ("if", "for", "macro", "call", "filter", "block", "with", "raw", "autoescape")

# Substrings of an id that name a use other than chat. They narrow NEW only, never RETIRED.
NON_CHAT_MARKERS = (
    "antigravity", "audio", "banana", "computer-use", "deep-research", "embed", "guard", "image",
    "imagen", "lyria", "moderation", "ocr", "orpheus", "playai", "rerank", "robotics", "speech",
    "transcribe", "tts", "veo", "voxtral", "whisper",
)

# The title of the section of the pull request body that lists what a person has to read.
# "dependabot-auto-merge.yml" lets the pull request merge itself only when the body has no section
# of this title, and "check_auto_merge_gate.py" holds the two to the same text.
REVIEW_HEADING = "## À relire"

# The exit status of a crash: 0, 1 and 2 mean something, and the status of an uncaught exception
# (1) would be read as drift.
CRASH_STATUS = 70

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
    return render_with_keys(text, None)


def render_with_keys(text, given):
    """The file as the sandbox renders it with the provider keys of "given" (a collection of the
    variables of PROVIDER_KEY_VARIABLES) given and the others empty, which the template reads as
    not given; every key when "given" is None."""
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
    context = {variable: "placeholder" if given is None or variable in given else ""
               for variable in PROVIDER_KEY_VARIABLES}
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


def neutralise_jinja(text):
    """The file with its Jinja made parsable and every line still on its own line number: a comment
    or a statement goes, an expression becomes a word, and the newlines inside either are kept.
    Deleting lines has to be done on the file as written, so this is how it is located -- the
    rendering that every other rule reads has no line numbers of the file's."""
    def keep_lines(replacement):
        return lambda match: replacement + "\n" * match.group(0).count("\n")

    text = JINJA_COMMENT.sub(keep_lines(""), text)
    text = JINJA_STATEMENT.sub(keep_lines(""), text)
    return JINJA_EXPRESSION.sub(keep_lines("JINJA"), text)


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
        "api_key": parameters.get("api_key"),
        "item": item,
    }


def fallback_lists(document):
    """{(section.key, source): [targets]} of every fallback list of a parsed file, "source" being
    None for "default_fallbacks". A cascade with nothing under it is an empty list."""
    found = {}
    if not isinstance(document, dict):
        return found
    for section_name in SETTINGS_SECTIONS:
        section = document.get(section_name)
        if not isinstance(section, dict):
            continue
        for key in FALLBACK_KEYS:
            if key not in section:
                continue
            value = section[key]
            where = "%s.%s" % (section_name, key)
            if key == "default_fallbacks":
                found[(where, None)] = [name for name in (value if isinstance(value, list) else [value])
                                        if isinstance(name, str)]
                continue
            for mapping in value if isinstance(value, list) else [value]:
                if not isinstance(mapping, dict):
                    continue
                for source, targets in mapping.items():
                    found[(where, source)] = [name for name in (
                        targets if isinstance(targets, list) else [targets]) if isinstance(name, str)]
    return found


def keyset_documents(text):
    """[(given, parsed document)] of the file rendered for each non-empty set of the provider keys
    it reads, "given" being a tuple of the names of the keys given; the document is None for a set
    that does not render. A file that reads no key renders once. The rest of this check reads the
    file with all five keys given, and a cascade that holds only the members of one provider is empty
    for the sets that leave that provider out: what is judged here is each of them."""
    try:
        import jinja2
        import jinja2.meta
        from jinja2.sandbox import SandboxedEnvironment
        tree = SandboxedEnvironment().parse(text)
        read = jinja2.meta.find_undeclared_variables(tree) & set(PROVIDER_KEY_VARIABLES)
    except Exception:  # the file is not valid Jinja: read_template has said so
        return []
    names = [variable for variable in PROVIDER_KEY_VARIABLES if variable in read]
    sets = [tuple(chosen) for size in range(1, len(names) + 1)
            for chosen in itertools.combinations(names, size)] or [tuple()]
    return [(given, render_keyset(text, given)) for given in sets]


def render_keyset(text, given):
    """The parsed file rendered with the keys of "given" given, or None when it does not render."""
    try:
        return yaml.safe_load(render_with_keys(text, frozenset(given)))
    except (RenderError, yaml.YAMLError):
        return None


def given_text(given):
    """The providers of a set of key variables, for a message."""
    names = [variable.split("_")[-3] for variable in given]
    return ", ".join(names) if names else "no key"


def commented_blocks(lines):
    """[(start, end, content)] of the commented-out entries: "end" is exclusive, "content" the
    block's lines with their "#" and one space removed, which is what parses as an entry."""
    blocks = []
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
        blocks.append((start, index, block))
    return blocks


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
    for start, end, block in commented_blocks(lines):
        for number in range(start, end):
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
        entry["end"] = end
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
        alias_names = section.get("model_group_alias")
        alias_names = set(alias_names) if isinstance(alias_names, dict) else set()
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
                    if source not in alias_names:
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

    template = {"active": active, "commented": commented, "ignored": ignored, "document": document}
    return template, problems


# ------------------------------------------------------------------------------------------------
# Reading the catalogues
# ------------------------------------------------------------------------------------------------

class FetchError(Exception):
    """A catalogue that could not be read. Its message never carries a key nor a response body."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse to follow a redirect. urllib sends the request's headers again to wherever the
    "Location" names, host included, and the keys travel in those headers: a catalogue that
    redirects is an error to report (HTTP 302...), never a place to send a key to."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def urllib_opener(url, headers):
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.build_opener(NoRedirect).open(request, timeout=TIMEOUT) as response:
        return response.read()


def fetch_json(opener, url, headers):
    try:
        raw = opener(url, headers)
    except urllib.error.HTTPError as error:
        # Neither the body nor the reason phrase is read: a provider may echo the key back in
        # either, and the status says all a person needs to know (HTTP/2 has no phrase at all).
        raise FetchError("HTTP %d" % error.code) from None
    except urllib.error.URLError as error:
        raise FetchError("network error: %s" % safe_text(error.reason)) from None
    except (OSError, ValueError, http.client.HTTPException) as error:
        raise FetchError("network error: %s" % error.__class__.__name__) from None
    try:
        return json.loads(raw)
    except ValueError:
        raise FetchError("the answer is not JSON") from None
    except RecursionError:
        raise FetchError("the answer is nested too deeply to read") from None


def scrub(text, environment):
    """"text" with every key of the run replaced by "***". No message here is meant to carry one,
    and this is what stands between a surprise and the log, the issue and the pull request."""
    for variable in [provider[2] for provider in PROVIDERS if provider[2]] + [RANKING_KEY]:
        key = (environment.get(variable) or "").strip()
        if key:
            text = text.replace(key, "***")
    return text


def is_zero(price):
    try:
        return float(price) == 0
    except (TypeError, ValueError, OverflowError):
        return False


def chat_like(identifier):
    lowered = identifier.lower()
    return not any(marker in lowered for marker in NON_CHAT_MARKERS)


def listed(payload, key="data"):
    items = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise FetchError('the answer holds no "%s" list' % key)
    return [item for item in items if isinstance(item, dict) and isinstance(item.get("id"), str)]


# Everything a provider's answer says is untrusted text, and ends up in a run's log, an issue, a pull
# request and a YAML snippet someone pastes. An id is therefore offered as NEW only when it is spelt
# the way ids are (SAFE_ID), and every other piece of the answer that is shown -- a name, a date, a
# replacement, a reason phrase -- is cut down to plain words by safe_text(): no newline, no
# backtick, no "@", no angle bracket, so that it can neither start a workflow command at the head
# of a log line, nor mention somebody, nor close a code span and write markup of its own. The
# catalogue's "members" are never filtered: an id is retired by not being among ALL of them.
SAFE_ID = re.compile(r"(?!.*(?:::|//))[A-Za-z0-9~][A-Za-z0-9._:/+~-]{0,199}")
UNSAFE_TEXT = re.compile(r"[^\w .,:;+()/'-]")


def safe_text(value, limit=80):
    text = " ".join(str(value).split())
    # No two colons side by side either: "::" is how a workflow command starts.
    return re.sub(r":(?=:)", ": ", UNSAFE_TEXT.sub("?", text))[:limit]


def new_catalogue():
    return {"members": set(), "candidates": {}, "notices": {}, "aliases": {}, "unsafe": 0}


def offer(catalogue, identifier, label=""):
    """Put "identifier" up as a NEW candidate, unless it is not spelt like an id."""
    if SAFE_ID.fullmatch(identifier):
        catalogue["candidates"][identifier] = safe_text(label)
    else:
        catalogue["unsafe"] += 1


def read_openrouter(pages):
    catalogue = new_catalogue()
    for model in listed(pages[0]):
        identifier = model["id"]
        catalogue["members"].add(identifier)
        if model.get("expiration_date"):
            catalogue["notices"][identifier] = {"what": "expiration",
                                                "date": safe_text(model["expiration_date"])}
        pricing = model.get("pricing") if isinstance(model.get("pricing"), dict) else {}
        architecture = model.get("architecture")
        architecture = architecture if isinstance(architecture, dict) else {}
        if (identifier.endswith(":free")
                and is_zero(pricing.get("prompt")) and is_zero(pricing.get("completion"))
                and architecture.get("output_modalities") == ["text"]
                and chat_like(identifier)):
            offer(catalogue, identifier, model.get("name") or "")
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
            offer(catalogue, identifier, model.get("name") or "")
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
            methods = model.get("supportedGenerationMethods")
            methods = methods if isinstance(methods, list) else []
            if "generateContent" in methods and chat_like(identifier):
                offer(catalogue, identifier, model.get("displayName") or "")
    return catalogue


def read_groq(pages):
    catalogue = new_catalogue()
    for model in listed(pages[0]):
        identifier = model["id"]
        catalogue["members"].add(identifier)
        if model.get("active") is False:
            catalogue["notices"][identifier] = {"what": "inactive"}
        elif chat_like(identifier):
            offer(catalogue, identifier, model.get("owned_by") or "")
    return catalogue


def read_mistral(pages):
    catalogue = new_catalogue()
    for model in listed(pages[0]):
        identifier = model["id"]
        aliases = model.get("aliases")
        aliases = {alias for alias in aliases if isinstance(alias, str)} if isinstance(
            aliases, list) else set()
        catalogue["members"].add(identifier)
        catalogue["members"].update(aliases)
        catalogue["aliases"].setdefault(identifier, set()).update(aliases)
        deprecation = model.get("deprecation")
        if deprecation:
            replacement = model.get("deprecation_replacement_model")
            notice = {"what": "deprecation", "date": safe_text(deprecation),
                      "replacement": safe_text(replacement) if replacement else None}
            for name in {identifier} | aliases:
                catalogue["notices"][name] = notice
            continue
        capabilities = model.get("capabilities")
        capabilities = capabilities if isinstance(capabilities, dict) else {}
        if (capabilities.get("completion_chat") is True and not identifier.startswith("ft:")
                and chat_like(identifier)):
            offer(catalogue, identifier, model.get("name") or "")
    return catalogue


def read_plain(pages):
    """DeepSeek: an OpenAI-style list and nothing else."""
    catalogue = new_catalogue()
    for model in listed(pages[0]):
        catalogue["members"].add(model["id"])
        if chat_like(model["id"]):
            offer(catalogue, model["id"])
    return catalogue


def gemini_next(url, page):
    token = page.get("nextPageToken") if isinstance(page, dict) else None
    if not (isinstance(token, str) and token):
        return None
    return url.split("&pageToken=")[0] + "&pageToken=" + token


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
    try:
        return reader(pages)
    except (TypeError, AttributeError, KeyError, IndexError, ValueError):
        # The readers are written for the shapes the providers document and guard the ones they
        # have thought of. An answer of a shape nobody thought of is that provider's error to
        # report, status 2, and not a crash of the whole run, which would leave every other
        # provider unread as well.
        raise FetchError("the answer has a shape this check does not read") from None


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


# ------------------------------------------------------------------------------------------------
# The rankings: figures and a suggested place for each NEW model
# ------------------------------------------------------------------------------------------------
# The order of a cascade follows the intelligence and the speed of its models, which someone looked
# up by hand for each. For a NEW model the report now carries the figures Artificial Analysis publishes
# and where they would put it among the models already in each router's cascade -- a suggestion with
# its source and its day, never applied. It is not a catalogue of a provider, so it is read apart
# from them: without its key the run says "not covered" like for any key it lacks, and a failed
# read is reported and changes neither the exit status nor what the run may delete.

RANKING_KEY = "MODEL_DRIFT_ARTIFICIAL_ANALYSIS_API_KEY"
RANKING_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"
RANKING_SITE = "https://artificialanalysis.ai/"
# The router and the figure that decides its place. "claude-code" is held to strict tool calls and
# a long context besides, which a score does not say: the report says so, and nothing here applies.
RANKING_ROUTERS = (("pro", "intelligence"), ("flash", "intelligence"), ("flash-lite", "speed"),
                   ("code", "coding"), ("claude-code", "intelligence"))
# The routers whose cascade is chosen for its speed: a model slower than the slowest of the members
# the ranking knows is not placed there, however high it would rank on the figure above. The template's
# ordering rule makes eligibility a question apart from rank, and a slow model has no place in these.
RANKING_SPEED_ROUTERS = ("flash", "flash-lite")
RANKING_FIGURES = {
    "intelligence": ("indice d'intelligence", "intelligence index"),
    "coding": ("indice de code", "coding index"),
    "speed": ("jetons par seconde", "output tokens per second"),
}
RANKING_MIN_KEY = 4  # a shorter spelling ("o3") says too little to be taken for a model
RANKING_LISTED = 25  # models in the table and the places: each takes up to six lines of a body GitHub caps


def squash(text):
    """Letters and digits only, in lower case: "Gemini 3.1 Flash-Lite" and "gemini-3-1-flash-lite" are
    the same model to anyone, and are the same string here."""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def figure(value):
    """A finite number, or None: a boolean, a string and "NaN" are not figures."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value == value and abs(value) != float("inf") else None


def speed_figure(value):
    """A speed in tokens per second, or None. Zero or less is no speed of a model that answers: the
    real answer gave 0.0 to models that serve, so it is read as "not measured". The API's reference
    does not say what it sends for those, this is read off what it did send."""
    speed = figure(value)
    return speed if speed is not None and speed > 0 else None


def read_ranking_models(payload):
    """The models of the LLMs endpoint, as documented on its API reference: a "data" list of objects
    with "name", "slug", "evaluations" (the intelligence and coding indexes), "pricing" and
    "median_output_tokens_per_second". Anything else in an object is ignored and a missing figure is
    None; what is shown of it is cut to plain words, since the answer is untrusted text."""
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise FetchError('the answer holds no "data" list')
    models = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        evaluations = item.get("evaluations") if isinstance(item.get("evaluations"), dict) else {}
        pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
        creator = item.get("model_creator") if isinstance(item.get("model_creator"), dict) else {}
        slug = item.get("slug") if isinstance(item.get("slug"), str) else ""
        models.append({
            "name": safe_text(item["name"], 80),
            "creator": safe_text(creator.get("name") or "", 40),
            "keys": {key for key in (squash(slug), squash(item["name"])) if len(key) >= RANKING_MIN_KEY},
            "intelligence": figure(evaluations.get("artificial_analysis_intelligence_index")),
            "coding": figure(evaluations.get("artificial_analysis_coding_index")),
            "speed": speed_figure(item.get("median_output_tokens_per_second")),
            "price": figure(pricing.get("price_1m_blended_3_to_1")),
        })
    return models


def read_rankings(opener, environment, today):
    """The state of the ranking source: {"status": "no key" | "read" | "error", "key", "date", ...}."""
    ranking = {"status": "read", "key": RANKING_KEY, "date": today, "models": []}
    key = (environment.get(RANKING_KEY) or "").strip()
    if not key:
        ranking["status"] = "no key"
        return ranking
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json", "x-api-key": key}
    try:
        payload = fetch_json(opener, RANKING_URL, headers)
        ranking["models"] = read_ranking_models(payload)
    except FetchError as error:
        ranking["status"] = "error"
        ranking["error"] = scrub(str(error), environment)
    return ranking


def match_ranking(provider, identifier, label, models):
    """(model, how) for the ranking entry that spells like this model, or (None, why not). The spelling
    of the id's last segment, then the provider's own name for the model, must equal an entry's
    slug or name once squashed; two entries that do are no answer. It is a guess, and shown as one."""
    tails = [("identifiant", squash(re.sub(r":free$", "", identifier.rsplit("/", 1)[-1])))]
    if label:
        tails.append(("nom", squash(re.sub(r"\s*\(free\)\s*$", "", label.split(": ", 1)[-1]))))
    ambiguous = False
    for how, key in tails:
        if len(key) < RANKING_MIN_KEY:
            continue
        found = [model for model in models if key in model["keys"]]
        if len(found) == 1:
            return found[0], how
        ambiguous = ambiguous or len(found) > 1
    return None, "ambigu" if ambiguous else "inconnu"


def suggest_places(model, template, models):
    """{router: {...}} where the figure that decides a router's place puts "model" among the members of
    that router's cascade the ranking knows: before the first of them it beats, or after the last. A
    router whose cascade has no ranked member, or a model with no such figure, is left out. In the
    routers of RANKING_SPEED_ROUTERS the model must first be as fast as the slowest member whose speed
    is known: a slower one gets {"ineligible": "slower", ...} and no place, one whose speed is unknown
    (or against which no member has a speed) gets {"ineligible": "model" | "members"}. A model with no
    figure at all is left out everywhere, not said unevaluated."""
    lists = fallback_lists(template["document"])
    entries = {entry["name"]: entry for entry in template["active"] if isinstance(entry["name"], str)}
    has_figures = any(model.get(key) is not None for key in ("intelligence", "coding", "speed"))
    places = {}
    for router, metric in RANKING_ROUTERS:
        members = lists.get(("router_settings.fallbacks", router))
        if not members or not has_figures:
            continue
        known_members = []
        for name in members:
            entry = entries.get(name)
            attributed = attribute(entry["model"], entry["api_base"]) if entry else None
            known = match_ranking(attributed[0], attributed[1], "", models)[0] if attributed else None
            if known is not None:
                known_members.append((name, known))
        if router in RANKING_SPEED_ROUTERS:
            speeds = [(name, known["speed"]) for name, known in known_members if known.get("speed") is not None]
            if model.get("speed") is None:
                places[router] = {"ineligible": "model"}
                continue
            if not speeds:
                places[router] = {"ineligible": "members"}
                continue
            slowest = min(speeds, key=lambda member: member[1])
            if model["speed"] < slowest[1]:
                places[router] = {"ineligible": "slower", "speed": model["speed"], "slowest": slowest}
                continue
        value = model.get(metric)
        scored = [(name, known[metric]) for name, known in known_members if known.get(metric) is not None]
        if value is None or not scored:
            continue
        places[router] = {"metric": metric, "value": value, "ranked": len(scored), "of": len(members),
                          "before": next(((name, score) for name, score in scored if score < value), None),
                          "last": scored[-1]}
    return places


def rank_new_models(result, template):
    """One row per NEW finding: what the ranking source says of it and where it would go."""
    ranking = result["rankings"]
    rows = []
    if ranking["status"] != "read":
        return rows
    for report in result["providers"]:
        for finding in report["findings"]:
            if finding["kind"] != "new":
                continue
            model, how = match_ranking(report["name"], finding["id"], finding.get("label", ""),
                                       ranking["models"])
            rows.append({"provider": report["name"], "id": finding["id"], "model": model, "how": how,
                         "places": suggest_places(model, template, ranking["models"]) if model else {}})
    return rows


def run_online(text, environment, opener, today):
    """Read every catalogue and diff it against the file. Returns the result the renderers read."""
    template, problems = read_template(text)
    result = {"date": today, "rules": problems, "providers": [], "unattributed": [],
              "unreadable": template is None}
    if template is None:
        return result
    result["names"] = sorted({entry["name"] for entry in template["active"] + template["commented"]
                              if isinstance(entry["name"], str)})
    result["unattributed"] = sorted({
        entry["model"] for entry in template["active"]
        if attribute(entry["model"], entry["api_base"]) is None and isinstance(entry["model"], str)
    })
    for name, url, key_variable, send_key, reader, next_page in PROVIDERS:
        active = known_ids(template["active"], name)
        commented = known_ids(template["commented"], name)
        ignored = {identifier for provider, identifier in template["ignored"] if provider == name}
        report = {"name": name, "active": len(active), "commented": len(commented),
                  "known": len(set(active) | set(commented)),
                  "key": key_variable, "status": "read", "findings": [],
                  "basis": provider_basis(template["active"] + template["commented"], name)}
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
            report["error"] = scrub(str(error), environment)
            continue
        report["members"] = len(catalogue["members"])
        report["candidates"] = len(catalogue["candidates"])
        report["unsafe"] = catalogue["unsafe"]
        report["findings"] = diff(name, catalogue, active, commented, ignored)
    result["rankings"] = read_rankings(opener, environment, today)
    result["ranked"] = rank_new_models(result, template)
    return result


def exit_status(result):
    if result["unreadable"] or any(p["status"] == "error" for p in result["providers"]):
        return 2
    if result["rules"] or any(p["findings"] for p in result["providers"]):
        return 1
    return 0


def is_complete(result):
    """True when every provider's catalogue was read. Not the same as the exit status: a provider
    whose key is missing is reported "not covered" and is no error, so a run that read nothing of it
    can still exit 0 -- and "nothing to delete" then only means "nothing seen" for that provider."""
    return not result["unreadable"] and all(p["status"] == "read" for p in result["providers"])


def undeleted_count(result):
    """How many RETIRED and GONE findings the run did not delete: those it refused to, and all of
    them when it was not asked to delete anything. A deletion pull request is closed over "nothing
    left to delete" only when this is 0 -- "changed nothing" also means "refused everything"."""
    return sum(1 for report in result["providers"] for finding in report["findings"]
               if finding["kind"] in ("retired", "gone")
               and finding.get("removal", {}).get("status") != "applied")


# ------------------------------------------------------------------------------------------------
# Deleting what a provider has retired
# ------------------------------------------------------------------------------------------------

BANNER_RULE = re.compile(r"^\s*#\s*={8,}\s*$")

# Why a deletion is left to a human: (the run's report, in English; the issue, in French). The %s is
# the place the reason is about, which is always a name or a position read from the file itself.
REFUSALS = {
    "source": (
        "it is the entry point of %s, and choosing what answers for that name is not mechanical",
        "c'est le point d'entrée de %s : choisir ce qui répond à ce nom n'a rien de mécanique",
    ),
    "alias": (
        "the alias %s points at it and would be left with no active target",
        "l'alias %s pointe vers lui et n'aurait plus de cible active",
    ),
    "emptied": (
        "it is the last target of %s, which would be left with none",
        "c'est la dernière cible de %s, qui n'en aurait plus",
    ),
    "form": (
        "its place in %s is not a plain list line, which this tool does not edit",
        "sa place dans %s n'est pas une ligne de liste simple, que cet outil ne sait pas modifier",
    ),
    "stray": (
        "its name is also used at line %s, in a Jinja statement or a place of the file this tool does "
        "not edit (a \"head\" table it cannot write back from the cascades, for instance)",
        "son nom est aussi utilisé à la ligne %s, dans une instruction Jinja ou un endroit du fichier "
        "que cet outil ne modifie pas (une table `head` qu'il ne sait pas réécrire à partir des "
        "cascades, par exemple)",
    ),
    "verification": (
        "deleting it makes the result fail verification: %s",
        "sa suppression ne passe pas la vérification du résultat : %s",
    ),
    "unlocated": (
        "it could not be located in the file reliably: %s",
        "il n'a pas pu être localisé de façon fiable dans le fichier : %s",
    ),
    "empty": (
        "its catalogue lists no model at all, which reads as a failed fetch and not as everything "
        "retired",
        "son catalogue ne liste aucun modèle, ce qui se lit comme une lecture ratée et non comme "
        "un retrait de tout",
    ),
    "implausible": (
        "its catalogue omits %d of the %d ids this file holds for that provider, which reads as a "
        "partial answer and not as that many retirements at once",
        "son catalogue ne liste pas %d des %d identifiants que ce fichier compte pour ce "
        "fournisseur, ce qui se lit comme une réponse partielle et non comme autant de retraits "
        "d'un coup",
    ),
}


def refusal_text(removal, french=False):
    code, detail = removal["reason"]
    template = REFUSALS[code][1 if french else 0]
    return template % detail if "%" in template else template


def is_comment(line):
    return comment_content(line) is not None


def indentation(line):
    return len(line) - len(line.lstrip())


def is_bare(line):
    """A comment line with nothing after its "#": what separates the entries of a run."""
    content = comment_content(line)
    return content is not None and not content.strip()


def place(group):
    """How a cascade or an alias is named in a message: the section and key, then its source."""
    where, source = group
    return '"%s"%s' % (where, ', cascade "%s"' % source if source else "")


def find_references(neutral, names):
    """Every place the settings name a model group, with the line it sits on, the lines where one
    of "names" turns up in a place nothing here knows about, and the first and last line of each
    entry of the model list. Read from the YAML nodes rather than the parsed values, since a node
    knows its line and a value does not -- and knows where a mapping ends, comments inside it
    included, which indentation does not."""
    root = yaml.compose(neutral)
    rows = neutral.splitlines()
    references = []
    spans = []
    known = set()

    def after(mark):
        """The index of the first line a node that ends at "mark" does not cover. A node ends where
        the next token begins, which is at the start of the line it is on -- unless the file ends
        on no newline, when the node ends after the content of its own last line."""
        if mark.line < len(rows) and rows[mark.line][:mark.column].strip():
            return mark.line + 1
        return mark.line

    def add(role, node, group):
        if isinstance(node, yaml.ScalarNode):
            known.add(id(node))
            references.append({"role": role, "name": node.value, "line": node.start_mark.line,
                               "group": group})

    def sequence_of(node):
        return node.value if isinstance(node, yaml.SequenceNode) else [node]

    for section_key, section in root.value if isinstance(root, yaml.MappingNode) else []:
        if section_key.value == "model_list" and isinstance(section, yaml.SequenceNode):
            for item in section.value:
                if isinstance(item, yaml.MappingNode):
                    spans.append([item.start_mark.line, after(item.end_mark), None])
                for key, value in item.value if isinstance(item, yaml.MappingNode) else []:
                    if key.value == "model_name":
                        known.add(id(value))
                        spans[-1][2] = value.value
        if section_key.value not in SETTINGS_SECTIONS or not isinstance(section, yaml.MappingNode):
            continue
        for key_node, value in section.value:
            key = key_node.value
            where = "%s.%s" % (section_key.value, key)
            if key == "default_fallbacks":
                for item in sequence_of(value):
                    add("default", item, (where, None))
            elif key in FALLBACK_KEYS:
                for mapping in sequence_of(value):
                    for source_node, targets in mapping.value if isinstance(
                            mapping, yaml.MappingNode) else []:
                        add("source", source_node, (where, source_node.value))
                        for target in sequence_of(targets):
                            add("target", target, (where, source_node.value))
            elif key == "model_group_alias" and isinstance(value, yaml.MappingNode):
                for alias_node, target in value.value:
                    if isinstance(target, yaml.MappingNode):
                        target = next((inner for name, inner in target.value
                                       if name.value == "model"), target)
                    add("alias", target, (where, alias_node.value))

    strays = {}
    seen = set()

    def walk(node):
        if id(node) in seen:
            return
        seen.add(id(node))
        if isinstance(node, yaml.ScalarNode):
            if id(node) not in known and node.value in names:
                strays.setdefault(node.value, []).append(node.start_mark.line + 1)
        elif isinstance(node, yaml.SequenceNode):
            for item in node.value:
                walk(item)
        elif isinstance(node, yaml.MappingNode):
            for key, value in node.value:
                walk(key)
                walk(value)

    walk(root)
    return references, strays, spans


# ------------------------------------------------------------------------------------------------
# The "head" table: which model a router stands for
# ------------------------------------------------------------------------------------------------
# The template says it twice: the order of a router's cascade, and, in a "set head" table, the first
# model of that cascade whose provider has a key, which is what the router is an alias of. The second
# is a copy of the first, so a deletion that takes a model a row names has to write the row again,
# and it is written FROM THE CASCADES, never patched: removing the first model of a provider can move
# that provider behind another one, which no edit of a name can express.

HEAD_STATEMENT = re.compile(r"\{%-?\s*set\s+head\s*=\s*\{(?P<body>.*?)\}\s*-?%\}", re.DOTALL)
HEAD_ROW = re.compile(r"(?P<lead>[ \t]*)'(?P<router>[^']+)'[ \t]*:[ \t]*(?P<chain>[^,\n]*?)"
                      r"(?P<comma>,?)[ \t]*")
HEAD_CHAIN = re.compile(r"(?:'[^']+'[ \t]+if[ \t]+has\.\w+[ \t]+else[ \t]+)*(?:'[^']+'|false)")
HEAD_PLACEHOLDER = "'head-placeholder'"
HEAD_PROVIDERS = tuple(variable.split("_")[-3] for variable in PROVIDER_KEY_VARIABLES)


def read_head(text):
    """{router: {"line", "lead", "chain", "comma"}} for the rows of the "head" table, "line" counting
    from 0 in "text"; None when there is no such table or a row of it is not
    "'router': 'name' if has.Provider else ... else 'name' (or false)", which is all this reads."""
    match = HEAD_STATEMENT.search(text)
    if not match:
        return None
    first = text.count("\n", 0, match.start("body"))
    rows = {}
    for offset, row in enumerate(match.group("body").split("\n")):
        if not row.strip():
            continue
        parsed = HEAD_ROW.fullmatch(row)
        if not parsed or not HEAD_CHAIN.fullmatch(parsed.group("chain")):
            return None
        rows[parsed.group("router")] = {"line": first + offset, "lead": parsed.group("lead"),
                                        "chain": parsed.group("chain"), "comma": parsed.group("comma")}
    return rows or None


def head_row_text(router, row, chain):
    return "%s'%s': %s%s" % (row["lead"], router, chain, row["comma"])


def head_fallbacks(text, rows):
    """{frozenset of providers: {router: [members]}} of the fallback cascades for EVERY set of
    providers, empty set included, read from "text" with each row of the table replaced by a name that
    is always set: a router whose row is empty would have no cascade to read, and the row is what is
    being worked out. None when a set does not render."""
    lines = text.split("\n")
    for router, row in rows.items():
        lines[row["line"]] = head_row_text(router, row, HEAD_PLACEHOLDER)
    probe = "\n".join(lines)
    found = {}
    for size in range(len(HEAD_PROVIDERS) + 1):
        for chosen in itertools.combinations(HEAD_PROVIDERS, size):
            document = render_keyset(
                probe, ["Artificial_Intelligence_LiteLLM_%s_API_key" % provider for provider in chosen])
            if not isinstance(document, dict):
                return None
            found[frozenset(chosen)] = {
                source: members for (where, source), members in fallback_lists(document).items()
                if where == "router_settings.fallbacks" and source is not None}
    return found


def head_chains(text, rows):
    """{router: the row's chain, written from the cascades} for each router of "rows" that has a
    cascade; None when a row cannot be written so that it gives, for every set of providers, the
    first member of the cascade -- the table is a decision list over providers, and a cascade that
    is not one is not something to rewrite."""
    fallbacks = head_fallbacks(text, rows)
    if fallbacks is None:
        return None
    everything = frozenset(HEAD_PROVIDERS)
    chains = {}
    for router in rows:
        if not any(router in cascades for cascades in fallbacks.values()):
            continue

        def first(chosen):
            members = fallbacks[frozenset(chosen)].get(router)
            return members[0] if members else None

        full = fallbacks[everything].get(router) or []
        default = first(())
        if default is not None and default not in full:
            return None
        terms = []
        for provider in HEAD_PROVIDERS:
            name = first((provider,))
            if name is None or name == default:
                continue
            if name not in full:
                return None
            terms.append((full.index(name), provider, name))
        if default is not None:
            terms = [term for term in terms if term[0] < full.index(default)]
        terms.sort()
        for chosen in fallbacks:
            written = next((name for _, provider, name in terms if provider in chosen), default)
            if written != first(chosen):
                return None
        chains[router] = "".join("'%s' if has.%s else " % (name, provider)
                                 for _, provider, name in terms) + (
                                     "'%s'" % default if default is not None else "false")
    return chains


def trusted_heads(text):
    """{router: row} of the rows this tool may write again: those that are exactly what writing
    them from the cascades gives. A row that is not -- tuned by hand, or out of step with its
    cascade already -- is not touched and its models stay out of reach of a deletion, as before."""
    rows = read_head(text)
    chains = head_chains(text, rows) if rows else None
    if not chains:
        return {}
    return {router: rows[router] for router, chain in chains.items()
            if chain == rows[router]["chain"]}


def rewrite_heads(text, trusted):
    """"text" with each row of "trusted" written again from the cascades "text" holds, and what
    changed as [(router, before, after)]. The text as it was when a row cannot be written."""
    rows = read_head(text)
    chains = head_chains(text, rows) if rows else None
    if not chains:
        return text, []
    lines = text.split("\n")
    changes = []
    for router in trusted:
        if router in chains and router in rows and chains[router] != rows[router]["chain"]:
            lines[rows[router]["line"]] = head_row_text(router, rows[router], chains[router])
            changes.append((router, rows[router]["chain"], chains[router]))
    return "\n".join(lines), changes


def changed_heads(before, after):
    """[(router, before, after)] of the rows of the "head" table that differ between two texts."""
    old, new = read_head(before) or {}, read_head(after) or {}
    return [(router, old[router]["chain"], row["chain"]) for router, row in new.items()
            if router in old and old[router]["chain"] != row["chain"]]


def repoint_aliases(document, gone):
    """"document" with each alias that pointed at a deleted model pointing at the first member left
    in its own cascade, which is what the table is meant to say: the oracle of verify_removal for the
    aliases, written from the cascades and not from the rows that were written."""
    fixed = copy.deepcopy(document)
    lists = fallback_lists(fixed)
    for section_name in SETTINGS_SECTIONS:
        section = fixed.get(section_name)
        aliases = section.get("model_group_alias") if isinstance(section, dict) else None
        if not isinstance(aliases, dict):
            continue
        for alias, target in list(aliases.items()):
            members = lists.get(("%s.fallbacks" % section_name, alias))
            if isinstance(target, str) and target in gone and members:
                aliases[alias] = members[0]
    return fixed


def alias_drift(document):
    """{alias: (target, first member of its cascade)} for the aliases of a rendering that do not
    point at the first member of the cascade kept under their own name."""
    drifted = {}
    if not isinstance(document, dict):
        return drifted
    lists = fallback_lists(document)
    for section_name in SETTINGS_SECTIONS:
        section = document.get(section_name)
        aliases = section.get("model_group_alias") if isinstance(section, dict) else None
        for alias, target in (aliases.items() if isinstance(aliases, dict) else []):
            members = lists.get(("%s.fallbacks" % section_name, alias))
            if members and target != members[0]:
                drifted[alias] = (target, members[0])
    return drifted


def read_layout(text, template):
    """Where everything a deletion has to touch sits in "text". Returns (layout, None), or
    (None, why) when the file cannot be located reliably, in which case nothing is edited.

    "template" is what read_template made of the RENDERED file, which has no line numbers of the
    file's: the lines are found in the file as written, Jinja made parsable, and the two are held
    to say the same thing before a line is trusted."""
    lines = text.splitlines()
    neutral = neutralise_jinja(text)
    if len(neutral.splitlines()) != len(lines):
        return None, "the file with its Jinja made parsable does not keep its line numbers"
    structure = jinja_structure(lines)
    if structure is None:
        return None, "the Jinja statements of the file do not pair up, so a block cannot be told"
    names = {entry["name"] for entry in template["active"] + template["commented"]
             if isinstance(entry["name"], str)}
    try:
        references, strays, spans = find_references(neutral, names)
    except yaml.YAMLError as error:
        return None, "the file does not compose: %s" % str(error).splitlines()[0]
    # The entries read from the file as written are the entries of the rendering, in the same
    # order: a block written only for some of the keys, or a loop, would break that.
    if [name for _, _, name in spans] != [entry["name"] for entry in template["active"]]:
        return None, ("the entries of the model list, read without rendering the file, are not "
                      "those of the rendering")
    # What the Jinja statements and expressions name is read by the template, not by the settings
    # above: "head" says which model a router stands for when it has no entry of its own.
    for match in list(JINJA_STATEMENT.finditer(text)) + list(JINJA_EXPRESSION.finditer(text)):
        first = text.count("\n", 0, match.start())
        for offset, row in enumerate(match.group(0).split("\n")):
            for name in names:
                if re.search(r"[\"']%s[\"']" % re.escape(name), row):
                    strays.setdefault(name, []).append(first + offset + 1)
    # The rows of the "head" table are written again after a deletion (rewrite_heads), so a name that
    # only they hold is not out of reach: every other place a Jinja statement names it still is.
    heads = trusted_heads(text)
    written = {row["line"] + 1 for row in heads.values()}
    for name in list(strays):
        strays[name] = [number for number in strays[name] if number not in written]
        if not strays[name]:
            del strays[name]
    entries = []
    for entry, (start, end, _) in zip(template["active"], spans):
        # A node ends where the next token begins: the blank lines and the comments between two
        # entries are before that, and belong to neither. A comment indented deeper than the
        # entry's dash is the entry's own, though: nothing but its body is written that far in.
        dash = indentation(lines[start])

        def of_a_block_beyond(number):
            """A statement of a block that does not lie wholly within the entry: the "endif" that
            closes the provider's block the last entry sits in, the "if" that opens the next."""
            return any(number in block and (min(block) < start or max(block) >= end)
                       for block in structure[0])

        while end > start + 1 and (
                not lines[end - 1].strip() or JINJA_COMMENT_LINE.match(lines[end - 1])
                or (is_comment(lines[end - 1]) and indentation(lines[end - 1]) <= dash)
                or of_a_block_beyond(end - 1)):
            end -= 1
        entries.append(dict(entry, state="active", start=start, end=end))
    # The commented-out entries, where the file as written has them: the rendering numbers its own
    # lines, so what it found is kept as it is and only the position is replaced.
    blocks = commented_blocks(lines)
    if len(blocks) != len(template["commented"]):
        return None, ("the commented-out entries of the file as written are not those of the "
                      "rendering")
    commented = []
    for entry, (start, end, _) in zip(template["commented"], blocks):
        commented.append(dict(entry, state="commented", rendered_start=entry["start"],
                              start=start, end=end))
    for entry in commented:
        # A bare "#" ends a commented-out entry, as it separates two of a run. An entry whose body
        # goes on past one -- indented comment lines after it -- would be cut short, and what it has
        # left would be mistaken for prose: this tool does not delete such an entry.
        following = entry["end"]
        while following < len(lines) and is_bare(lines[following]):
            following += 1
        content = comment_content(lines[following]) if following < len(lines) else None
        entry["continues"] = bool(following > entry["end"] and content and content.strip()
                                  and content.startswith(" "))
    entries += commented
    by_key = {}
    for entry in entries:
        entry["key"] = attribute(entry["model"], entry["api_base"])
        if entry["key"]:
            by_key.setdefault(entry["key"], []).append(entry)

    owner = {number: index for index, entry in enumerate(commented)
             for number in range(entry["start"], entry["end"])}
    # A run is what the offline rules call one: commented-out entries with nothing but bare "#"
    # lines between them, which share the reason written above the first.
    runs = []
    for index, entry in enumerate(commented):
        previous = commented[index - 1] if index else None
        if previous and all(is_bare(lines[number])
                            for number in range(previous["end"], entry["start"])):
            runs[-1].append(index)
        else:
            runs.append([index])

    groups = {}
    for reference in references:
        name = reference["name"]
        line = lines[reference["line"]] if reference["line"] < len(lines) else ""
        # A slot is deletable as a line when that line holds the slot and nothing else.
        reference["editable"] = bool(re.fullmatch(
            r"\s*-\s+(?:\"%s\"|'%s'|%s)\s*(?:#.*)?" % ((re.escape(name),) * 3), line))
        if reference["role"] in ("target", "default"):
            groups.setdefault(reference["group"], []).append(reference)
    # The lines a Jinja statement runs over when it takes more than one: jinja_structure reads a
    # line at a time and cannot see it, and a deletion that took one of its lines would leave half of
    # a statement behind.
    spanning = set()
    for match in JINJA_STATEMENT.finditer(text):
        first, last = text.count("\n", 0, match.start()), text.count("\n", 0, match.end())
        if last > first:
            spanning.update(range(first, last + 1))
    return {"lines": lines, "raw": text.splitlines(keepends=True), "entries": entries,
            "commented": commented, "owner": owner, "runs": runs, "by_key": by_key,
            "references": references, "groups": groups, "strays": strays, "heads": heads,
            "jinja": structure[0], "jinja_single": structure[1], "jinja_spanning": spanning,
            "keysets": keyset_documents(text)}, None


def comments_above(layout, start, entry=None):
    """The comment lines directly above line "start", top to bottom, up to the first blank line, the
    first line that is not a comment, or the first line of a commented-out entry. With the active
    "entry" that starts there, the one statement line that opens a block closing right after it is
    stepped over: prose written above "{% if x %}" and the entry it wraps is about that entry."""
    found = []
    number = start - 1
    while number >= 0 and number not in layout["owner"]:
        line = layout["lines"][number]
        if comment_content(line) is not None:
            found.append(number)
        elif entry is not None and number == start - 1 and any(
                min(block) == number and max(block) - entry["end"] <= 2
                for block in layout["jinja"]):
            pass
        else:
            break
        number -= 1
    return found[::-1]


def left_behind(layout, entry):
    """The comment lines above an active entry that a deletion leaves where they are: the prose
    about it, which may as well be about its neighbours, and which only a person can tell. A section
    banner is none of that, so everything up to the last banner rule is cut off."""
    found = comments_above(layout, entry["start"], entry)
    cut = max((position for position, number in enumerate(found)
               if BANNER_RULE.match(layout["lines"][number])), default=-1)
    found = found[cut + 1:]
    while found and is_bare(layout["lines"][found[0]]):
        found.pop(0)
    return found


def reason_lines(layout, prose):
    """Which of the comment lines above a run that is deleted whole go with it: the free prose, and
    a section banner only when the banner is itself the reason ("SambaNova -- not routed to: ...").
    A banner that is merely a heading -- "Cerebras & Groq" -- may head entries that stay, and a
    "drift-ignore:" line is a declaration about an id, not about the run."""
    lines = layout["lines"]
    keep = set()
    opened = None
    spans = []
    for position, number in enumerate(prose):
        if BANNER_RULE.match(lines[number]):
            if opened is None:
                opened = position
            else:
                spans.append((opened, position))
                opened = None
    if opened is not None:
        spans.append((opened, len(prose) - 1))
    for first, last in spans:
        text = " ".join(comment_content(lines[number]).strip() for number in prose[first:last + 1])
        if not REASON.search(text):
            keep.update(prose[first:last + 1])
    for number in prose:
        if DRIFT_IGNORE_START.match(comment_content(lines[number])):
            keep.add(number)
    kept_text = [number for number in keep if not is_bare(lines[number])]
    for number in prose:
        # A bare line stays only between two lines that stay.
        if is_bare(lines[number]) and any(k < number for k in kept_text) \
                and any(k > number for k in kept_text):
            keep.add(number)
    return [number for number in prose if number not in keep]


def plan_lines(layout, keys):
    """The line numbers to delete so that every entry attributed to a key of "keys" is gone with
    its cascade slots, and what was done for each key. Nothing is edited here."""
    lines = layout["lines"]
    entries = [entry for entry in layout["entries"] if entry["key"] in keys]
    surviving = {entry["name"] for entry in layout["entries"] if entry["key"] not in keys}
    owners = {entry["name"]: entry["key"] for entry in entries if isinstance(entry["name"], str)}
    slot_names = {name for name in owners if name not in surviving}
    marks = set()
    notes = {key: {"entries": [], "slots": [], "prose": [], "left": []} for key in keys}

    for entry in entries:
        note = notes[entry["key"]]
        note["entries"].append({"name": entry["name"], "state": entry["state"],
                                "line": entry["start"] + 1})
        if entry["state"] != "active":
            continue
        marks.update(range(entry["start"], entry["end"]))
        left = left_behind(layout, entry)
        if left:
            note["left"].append(left)
        elif entry["end"] < len(lines) and not lines[entry["end"]].strip():
            marks.add(entry["end"])

    for run in layout["runs"]:
        members = [layout["commented"][index] for index in run]
        gone = [member for member in members if member["key"] in keys]
        if not gone:
            continue
        if len(gone) == len(members):
            marks.update(range(members[0]["start"], members[-1]["end"]))
            prose = reason_lines(layout, comments_above(layout, members[0]["start"]))
            marks.update(prose)
            if prose:
                text = [comment_content(lines[number]).strip() for number in prose]
                first = next((line for line in text if re.search(r"[A-Za-z]", line)), "")
                notes[members[0]["key"]]["prose"].append({"lines": len(prose), "first": first})
            continue
        for member in gone:
            marks.update(range(member["start"], member["end"]))
        # Of the separators, a run keeps one between two entries that stay, and no other.
        for position in range(len(members) - 1):
            stays = members[position]["key"] not in keys and \
                any(later["key"] not in keys for later in members[position + 1:])
            if not stays:
                marks.update(range(members[position]["end"], members[position + 1]["start"]))

    for reference in layout["references"]:
        if reference["role"] in ("target", "default") and reference["name"] in slot_names:
            marks.add(reference["line"])
            notes[owners[reference["name"]]]["slots"].append(reference["group"])
    return marks, notes, slot_names


def assemble(layout, marks):
    """The text without the marked lines, and without the double blank line a deletion would have
    left where it took out what lay between two blank lines, nor the blank line it would have left
    at the end of a file that did not end on one. A file's last line keeps the ending it had: with
    none, the file still has none."""
    raw = layout["raw"]
    kept = []
    for number in range(len(raw)):
        if number in marks:
            continue
        if kept and not raw[number].strip() and not raw[kept[-1]].strip() and number != kept[-1] + 1:
            continue
        kept.append(number)
    if raw and raw[-1].strip():
        while kept and not raw[kept[-1]].strip():
            kept.pop()
    text = "".join(raw[number] for number in kept)
    if raw and not raw[-1].endswith(("\n", "\r")) and kept and kept[-1] != len(raw) - 1:
        text = re.sub(r"\r?\n\Z", "", text)
    return text, kept


def strip_names(document, names):
    """"document" without "names" in its cascades: the oracle of verify_removal, written apart from
    the code that edits the text, so that the one cannot be wrong in the way of the other."""
    stripped = copy.deepcopy(document)
    for section_name in SETTINGS_SECTIONS:
        section = stripped.get(section_name)
        if not isinstance(section, dict):
            continue
        for key in FALLBACK_KEYS:
            value = section.get(key)
            if key == "default_fallbacks" and isinstance(value, list):
                section[key] = [target for target in value if target not in names]
            elif isinstance(value, list):
                for mapping in value:
                    if isinstance(mapping, dict):
                        for source, targets in list(mapping.items()):
                            if isinstance(targets, list):
                                mapping[source] = [t for t in targets if t not in names]
    return stripped


def normalised(problems):
    return [re.sub(r"\bline (?:\d+|\?)", "line N", " ".join(problem.split()))
            for problem in problems]


def jinja_structure(lines):
    """(blocks, single) of the Jinja statements of "lines", or None when they do not pair up.
    "blocks" holds, for each block, the set of the line indexes of its opening statement, of each
    "else" and "elif" of it, and of its "end"; "single" the line indexes of the statements that
    open no block and are not an "else" ("set x = 1", "include", "import"...). Statements and
    comments that span lines are not read: read_layout has refused the file by then."""
    blocks = []
    single = set()
    stack = []
    for number, line in enumerate(lines):
        for match in JINJA_TAG.finditer(JINJA_COMMENT.sub("", line)):
            closing, tag, rest = match.groups()
            if stack and stack[-1][0] == "raw" and not (closing and tag == "raw"):
                continue
            if closing:
                if not stack or stack[-1][0] != tag:
                    return None
                stack[-1][1].add(number)
                blocks.append(frozenset(stack.pop()[1]))
            elif tag in JINJA_BLOCKS or (tag == "set" and "=" not in rest):
                stack.append((tag, {number}))
            elif tag in ("else", "elif"):
                if not stack or stack[-1][0] not in (("if", "for") if tag == "else" else ("if",)):
                    return None
                stack[-1][1].add(number)
            else:
                single.add(number)
    return None if stack else (blocks, single)


def jinja_refusal(layout, marks):
    """None, or why the lines "marks" cannot be deleted from a file with Jinja statements in it.
    A statement is part of the block it belongs to, and a block's parts hold each other up: an
    "{% endif %}" taken with the entry above it while its "{% if %}" stays, an "{% else %}" taken
    with the entry of the branch before it (which re-parents the branch after it), an "{% endif %}"
    and the "{% if %}" of the next block taken together (which hands the next entry the condition
    of the one deleted) all leave a template that still parses as YAML, and renders another model
    list. So a block is taken whole -- its statements and everything between -- or not at all, and
    a statement that opens no block is not taken, since nothing here knows what it set."""
    lines = layout["lines"]
    for block in layout["jinja"]:
        if not block & marks:
            continue
        # Some statement of the block goes: so must every line from its first statement to its last,
        # the other statements and what they enclose.
        first, last = min(block), max(block)
        left = [number for number in range(first, last + 1)
                if number not in marks and lines[number].strip()]
        if left:
            return ("it would take a statement of the Jinja block that runs from line %d to line %d "
                    "and leave line %d, which is part of it or inside it, behind"
                    % (first + 1, last + 1, left[0] + 1))
    spanning = layout["jinja_spanning"] & marks
    if spanning:
        return ("it would take a line of the Jinja statement that runs over several lines at line "
                "%d, whose effect on the rest of the file this tool cannot read" % (min(spanning) + 1))
    statement = layout["jinja_single"] & marks
    if statement:
        return ("it would take the Jinja statement at line %d, whose effect on the rest of the "
                "file this tool cannot read" % (min(statement) + 1))
    return None


def jinja_balance(text):
    """{block statement: opened minus closed} of the Jinja in "text", the statements that balance
    left out. The YAML check cannot see Jinja -- the statements are blanked before the parse -- so
    an "{% endif %}" taken with the entry above it, its "{% if %}" left behind, reads as fine."""
    balance = collections.Counter()
    for match in JINJA_TAG.finditer(JINJA_COMMENT.sub("", text)):
        closing, tag, rest = match.groups()
        # "{% set x %}" opens a block, "{% set x = 1 %}" does not.
        if tag in JINJA_BLOCKS or (tag == "set" and "=" not in rest):
            balance[tag] += -1 if closing else 1
    return {tag: count for tag, count in balance.items() if count}


def verify_removal(text, keys, new_text, original=None):
    """None when "new_text" is "text" minus the entries of "keys" and their cascade slots, and
    breaks no rule "text" did not already break; otherwise why not. The deletion is edited text, and
    text can be wrong in ways its author cannot see: this reads the result back, and compares what it
    says with what it should say. "original" is (template, problems, layout) of "text" when the
    caller has them, since each deletion is verified on its own and the original does not change."""
    if original is None:
        template, problems = read_template(text)
        layout = read_layout(text, template)[0] if template else None
        original = (template, problems, layout)
    template, problems, layout = original
    if layout is None:
        return "the original could not be read back"
    result, result_problems = read_template(new_text)
    if result is None:
        return "the result is not readable: %s" % result_problems[0]
    worse = collections.Counter(normalised(result_problems)) - collections.Counter(
        normalised(problems))
    if worse:
        return "the offline rules fail on the result: %s" % next(iter(worse))
    if jinja_balance(text) != jinja_balance(new_text):
        return ("the deletion takes a Jinja block statement and leaves the other end of its block "
                "behind, so the template would no longer render")
    deleted = [entry for entry in layout["entries"] if entry["key"] in keys]
    surviving = {entry["name"] for entry in layout["entries"] if entry["key"] not in keys}
    slot_names = {entry["name"] for entry in deleted} - surviving
    removed = {id(entry["item"]) for entry in deleted if entry["state"] == "active"}
    deleted_active = {entry["name"] for entry in deleted if entry["state"] == "active"}
    expected = dict(template["document"])
    expected["model_list"] = [item for item in template["document"]["model_list"]
                              if id(item) not in removed]
    if repoint_aliases(strip_names(expected, slot_names), slot_names | deleted_active) != result["document"]:
        return "the result is not the original without the deleted entries and their cascade slots"

    # And on every set of keys, which is where a cascade is emptied: the model list is the original's
    # without the deleted entries, each fallback list the original's without the deleted slots, and
    # none that had members has none left.
    deleted_names = {entry["name"] for entry in deleted if entry["state"] == "active"}
    for given, before in layout["keysets"]:
        if not isinstance(before, dict):
            continue
        after = render_keyset(new_text, given)
        if not isinstance(after, dict):
            return "the result does not render when only %s given" % given_text(given)
        names = [item.get("model_name") for item in before.get("model_list") or []
                 if isinstance(item, dict)]
        left_names = [item.get("model_name") for item in after.get("model_list") or []
                      if isinstance(item, dict)]
        if left_names != [name for name in names if name not in deleted_names]:
            return "the model list of the result is not the original's without the deleted entries " \
                   "when only %s given" % given_text(given)
        lists_before, lists_after = fallback_lists(before), fallback_lists(after)
        # An alias of a router stands for the first member of the cascade kept under its name: a
        # deletion that leaves one on a model that is gone, or on another than the first, is the
        # "head" table written wrong. Only what the original did right is held against the result.
        for alias, (target, first) in alias_drift(after).items():
            if alias not in alias_drift(before):
                return "the alias %s points at %s but its cascade starts at %s when only %s given" \
                       % (alias, target, first, given_text(given))
        if set(lists_after) - set(lists_before):
            return "the result has a fallback list the original did not when only %s given" \
                   % given_text(given)
        for group, targets in lists_before.items():
            wanted = [name for name in targets if name not in slot_names]
            if lists_after.get(group, []) != wanted:
                return "%s is not the original's without the deleted slots when only %s given" \
                       % (place(group), given_text(given))
            if targets and not wanted:
                return "%s is left with no member when only %s given" % (place(group),
                                                                         given_text(given))

    def summary(entries):
        return [(entry["name"], entry["model"], entry["api_base"]) for entry in entries]

    gone = {entry["rendered_start"] for entry in deleted if entry["state"] == "commented"}
    left = [entry for entry in template["commented"] if entry["start"] not in gone]
    if summary(result["commented"]) != summary(left):
        return "the commented-out entries of the result are not the original ones minus the deleted"
    if result["ignored"] != template["ignored"]:
        return 'the "drift-ignore:" lines of the result are not the original ones'
    return None


def refuse(outcome, code, detail=""):
    outcome["status"] = "refused"
    outcome["reason"] = (code, detail)


def static_refusals(layout, keys):
    """{key: (code, detail)} for every key of "keys" whose deletion would leave the settings
    pointing at nothing, or at a place this tool cannot edit. Decided on the whole set together: two
    models that are each one of a cascade's two targets are not deletable one after the other."""
    surviving = {entry["name"] for entry in layout["entries"] if entry["key"] not in keys}
    owners = {}
    for entry in layout["entries"]:
        if entry["key"] in keys and isinstance(entry["name"], str) and entry["name"] not in surviving:
            owners.setdefault(entry["name"], set()).add(entry["key"])
    found = {}
    for entry in layout["commented"]:
        if entry["key"] in keys and entry["continues"]:
            found.setdefault(entry["key"], (
                "unlocated", "the commented-out entry at line %d goes on after a bare # line, "
                "which cannot be told from prose" % (entry["start"] + 1)))

    def refuse_name(name, code, detail):
        for key in owners[name]:
            found.setdefault(key, (code, detail))

    for reference in layout["references"]:
        name = reference["name"]
        if name not in owners:
            continue
        if reference["role"] == "source":
            refuse_name(name, "source", place(reference["group"]))
        elif reference["role"] == "alias":
            refuse_name(name, "alias", '"%s"' % reference["group"][1])
        elif not reference["editable"]:
            refuse_name(name, "form", place(reference["group"]))
    for group, members in layout["groups"].items():
        gone = [member for member in members if member["name"] in owners]
        if gone and len(gone) == len(members):
            for member in gone:
                refuse_name(member["name"], "emptied", place(group))
    for name in owners:
        if layout["strays"].get(name):
            refuse_name(name, "stray", str(layout["strays"][name][0]))
    # A cascade that is left with nothing is judged for each set of keys, not on the union: the one
    # that holds the members of a single provider is empty for every set that leaves it out.
    for given, document in layout["keysets"]:
        for group, targets in fallback_lists(document).items():
            if targets and all(target in owners for target in targets):
                for target in targets:
                    refuse_name(target, "emptied", "%s, when only %s given" % (place(group),
                                                                               given_text(given)))
    return found


def banner_blocks(layout):
    """[(first, last)] of the comment blocks that open with a banner rule: the contiguous comment
    lines from a rule that follows a blank or a non-comment line, up to the first blank line, the
    first line that is no comment, or the first line of a commented-out entry. A banner that is
    closed by a second rule is one block with whatever prose follows it, and so is one that is not
    (the DeepSeek one), which is why a rule is not paired with the next."""
    lines = layout["lines"]
    blocks = []
    number = 0
    while number < len(lines):
        if BANNER_RULE.match(lines[number]) and (number == 0 or not is_comment(lines[number - 1])):
            last = number
            while last + 1 < len(lines) and is_comment(lines[last + 1]) \
                    and last + 1 not in layout["owner"]:
                last += 1
            blocks.append((number, last))
            number = last
        number += 1
    return blocks


def mention_pattern(token):
    """A regular expression for "token" standing alone in prose: not inside a longer id, though the
    full stop or the colon that ends a clause does not make it part of one."""
    return re.compile(r"(?<![A-Za-z0-9_.-])%s(?![A-Za-z0-9_-]|[.:][A-Za-z0-9])" % re.escape(token))


def review_items(layout, accepted, notes, slot_names, position):
    """{key: [item]} of the places in the NEW file a person has to read after the deletions of
    "accepted", since a comment can say what is no longer so and no edit here could tell. Each
    item is {"line", "last", "first", "why", "subject"}, "why" being one of:

    left     prose above a deleted active entry, left where it was
    kept     the reason over a run of commented-out entries some of which are gone, kept over the
             ones that stay: it may count them, or name one that is gone
    banner   a section heading, now over no entry at all
    mention  a comment line naming a deleted model_name or id, the "subject"

    "position" maps a kept line's index in the old file to its number in the new one."""
    lines = layout["lines"]
    old_index = {new: old for old, new in position.items()}
    items = {key: [] for key in accepted}
    pointed = set()

    def point(key, numbers, why, subject=None):
        spans = []
        for number in sorted(position[n] for n in numbers if n in position):
            if spans and number == spans[-1][1] + 1:
                spans[-1][1] = number
            else:
                spans.append([number, number])
        for first, last in spans:
            if pointed & set(range(first, last + 1)):
                continue
            pointed.update(range(first, last + 1))
            prose = [comment_content(lines[old_index[number]]) or ""
                     for number in range(first, last + 1)
                     if not BANNER_RULE.match(lines[old_index[number]])]
            items[key].append({"line": first, "last": last, "why": why, "subject": subject,
                               "first": next((text.strip() for text in prose
                                              if re.search(r"[A-Za-z]", text)), "")})

    for key in sorted(accepted):
        for group in notes[key]["left"]:
            point(key, group, "left")

    for run in layout["runs"]:
        members = [layout["commented"][index] for index in run]
        gone = [member for member in members if member["key"] in accepted]
        if gone and len(gone) < len(members):
            point(gone[0]["key"], comments_above(layout, members[0]["start"]), "kept")

    blocks = banner_blocks(layout)
    for index, (first, last) in enumerate(blocks):
        until = blocks[index + 1][0] if index + 1 < len(blocks) else len(lines)
        section = [entry for entry in layout["entries"] if last < entry["start"] < until]
        if section and all(entry["key"] in accepted for entry in section):
            point(section[0]["key"], range(first, last + 1), "banner")

    # What each deleted model is called in prose: its provider-qualified id, its bare id unless a
    # surviving entry carries the same one (the same name at another provider is not a stale
    # mention), and its model_name unless a surviving entry carries that.
    survivors = [entry["model"] for entry in layout["entries"]
                 if entry["key"] not in accepted and isinstance(entry["model"], str)]
    names = {}
    for provider, identifier in accepted:
        called = [litellm_id(provider, identifier)[0]]
        if not any(mention_pattern(identifier).search(model) for model in survivors):
            called.append(identifier)
        called += [entry["name"] for entry in layout["entries"]
                   if entry["key"] == (provider, identifier) and entry["name"] in slot_names]
        names[(provider, identifier)] = [(token, mention_pattern(token))
                                         for token in dict.fromkeys(called)]
    for number in sorted(position):
        content = comment_content(lines[number])
        if content is None:
            continue
        for key in sorted(names):
            hit = next((token for token, pattern in names[key] if pattern.search(content)), None)
            if hit:
                point(key, [number], "mention", hit)
                break
    return items


def finished(layout, marks):
    """What "assemble" gives, with the rows of the "head" table written again from the cascades the
    deletion leaves, so that a router never stands for a model that is gone. The file keeps its
    line numbers: a row is replaced by a row."""
    text, kept = assemble(layout, marks)
    if layout["heads"]:
        text = rewrite_heads(text, layout["heads"])[0]
    return text, kept


def apply_removals(text, wanted):
    """Delete from "text" every entry the providers have retired that can be deleted without
    anybody's judgment. "wanted" is a list of (provider, id, kind). Returns (new_text, outcomes),
    one outcome per wanted item, in order: "status" is "applied" or "refused", and a refusal
    carries its "reason" -- a deletion that is not safe on its own terms is not made, and the
    finding stays where a person reads it. Nothing is written anywhere here."""
    # One outcome per (provider, id): a finding asked for twice is one deletion.
    wanted = list({(provider, identifier): (provider, identifier, kind)
                   for provider, identifier, kind in wanted}.values())
    outcomes = [{"provider": provider, "id": identifier, "kind": kind, "status": "refused",
                 "reason": None, "entries": [], "slots": [], "prose": [], "review": []}
                for provider, identifier, kind in wanted]
    by_key = {(o["provider"], o["id"]): o for o in outcomes}
    template, problems = read_template(text)
    layout, why = read_layout(text, template) if template else (None, problems[0])
    if layout is None:
        for outcome in outcomes:
            refuse(outcome, "unlocated", why)
        return text, outcomes

    accepted = set()
    for key, outcome in by_key.items():
        if layout["by_key"].get(key):
            accepted.add(key)
        else:
            refuse(outcome, "unlocated", "no entry of the file is attributed to it")
    while accepted:
        refusals = static_refusals(layout, accepted)
        if not refusals:
            break
        for key, (code, detail) in refusals.items():
            refuse(by_key[key], code, detail)
            accepted.discard(key)

    # Each deletion is also tried alone, and read back: what fails does so under its own name, and
    # the others still go through.
    for key in sorted(accepted):
        marks, _, _ = plan_lines(layout, {key})
        problem = jinja_refusal(layout, marks) or verify_removal(
            text, {key}, finished(layout, marks)[0], (template, problems, layout))
        if problem:
            refuse(by_key[key], "verification", problem)
            accepted.discard(key)
    if not accepted:
        return text, outcomes

    marks, notes, slot_names = plan_lines(layout, accepted)
    new_text, kept = finished(layout, marks)
    problem = jinja_refusal(layout, marks) or verify_removal(
        text, accepted, new_text, (template, problems, layout))
    if problem:
        for key in accepted:
            refuse(by_key[key], "verification", "taken together, " + problem)
        return text, outcomes
    # Positions in the new file, for the places a person is asked to look at.
    position = {number: index + 1 for index, number in enumerate(kept)}
    reviews = review_items(layout, accepted, notes, slot_names, position)
    for key in accepted:
        outcome = by_key[key]
        outcome["status"] = "applied"
        outcome.update({name: notes[key][name] for name in ("entries", "slots", "prose")})
        outcome["review"] = reviews[key]
    return new_text, outcomes


# A catalogue that omits MORE than this share of the ids the file holds for its provider, and at
# least this many of them, is not believed either: a key that sees another tier, a truncated page or
# a provider in the middle of an incident all answer 200 with a short list, and a short list is
# exactly what a mass retirement looks like. Such a week is a person's to read, in the issue.
IMPLAUSIBLE_SHARE = 0.5
IMPLAUSIBLE_FLOOR = 3


def refused_outcome(report, finding, code, detail=""):
    return {"provider": report["name"], "id": finding["id"], "kind": finding["kind"],
            "status": "refused", "reason": (code, detail), "entries": [], "slots": [],
            "prose": [], "review": []}


def apply_to_result(text, result):
    """Apply the RETIRED and GONE findings of "result" to "text". Each finding gets a "removal"
    outcome, and the new text is returned. A provider whose catalogue lists nothing is not believed:
    a fetch that answers 200 with an empty list is a failed read, not a provider with no model. Nor
    is one whose catalogue omits most of what the file holds for it (IMPLAUSIBLE_SHARE)."""
    wanted = []
    for report in result["providers"]:
        deletable = [finding for finding in report["findings"]
                     if finding["kind"] in ("retired", "gone")]
        omitted = len({finding["id"] for finding in deletable})
        implausible = (omitted >= IMPLAUSIBLE_FLOOR
                       and omitted > IMPLAUSIBLE_SHARE * report.get("known", 0))
        for finding in deletable:
            if report.get("members") == 0:
                finding["removal"] = refused_outcome(report, finding, "empty")
            elif implausible:
                finding["removal"] = refused_outcome(report, finding, "implausible",
                                                     (omitted, report["known"]))
            else:
                wanted.append((report["name"], finding["id"], finding["kind"]))
    new_text, outcomes = apply_removals(text, wanted)
    by_key = {(outcome["provider"], outcome["id"]): outcome for outcome in outcomes}
    for report in result["providers"]:
        for finding in report["findings"]:
            if (report["name"], finding["id"]) in by_key and "removal" not in finding:
                finding["removal"] = by_key[(report["name"], finding["id"])]
    result["removals"] = {
        "outcomes": [finding["removal"] for report in result["providers"]
                     for finding in report["findings"] if "removal" in finding],
        "changed": new_text != text,
        "heads": changed_heads(text, new_text),
    }
    return new_text


# ------------------------------------------------------------------------------------------------
# The renderings: the run's report in English, the issue, pull request and commit in the language
# the people who read each of them write in
# ------------------------------------------------------------------------------------------------

KINDS = ("retired", "gone", "notice", "back", "new")

PROVIDER_LABELS = {
    "openrouter": "OpenRouter", "cerebras": "Cerebras", "sambanova": "SambaNova",
    "gemini": "Gemini", "groq": "Groq", "mistral": "Mistral", "deepseek": "DeepSeek",
}
# GitHub refuses an issue or pull request body past 65536 characters.
BODY_LIMIT = 60000


def notice_text(notice, french=False):
    what = notice.get("what")
    date = notice.get("date")
    replacement = notice.get("replacement")
    if french:
        text = {"expiration": "expiration annoncée", "deprecation": "déprécié",
                "inactive": "marqué inactif"}.get(what, what)
        if date:
            text += " (`%s`)" % date
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


def removals_of(result, status):
    """[(report, finding)] of the RETIRED and GONE findings a run deleted, or left to a person."""
    return [(report, finding) for report in result["providers"] for finding in report["findings"]
            if finding.get("removal", {}).get("status") == status]


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
            if report.get("unsafe"):
                state += ", %d id(s) of an unusual spelling left out" % report["unsafe"]
        out.append("%-11s %s; %s" % (report["name"], state, known))
    if result["unattributed"]:
        count = len(result["unattributed"])
        out.append("%-11s %d active entr%s of no catalogue read here: %s"
                   % ("(none)", count, "y" if count == 1 else "ies",
                      ", ".join(result["unattributed"])))
    ranking = result.get("rankings")
    if ranking:
        if ranking["status"] == "no key":
            state = "not covered (no key): %s is unset" % ranking["key"]
        elif ranking["status"] == "error":
            state = "ERROR, not read: %s" % ranking["error"]
        else:
            rows = result.get("ranked") or []
            state = ("read, %d model(s), %d of the %d NEW model(s) matched; source: Artificial "
                     "Analysis, %s" % (len(ranking["models"]), sum(1 for row in rows if row["model"]),
                                       len(rows), RANKING_SITE))
        out.append("%-11s %s" % ("rankings", state))
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
                removal = finding.get("removal")
                if removal and removal["status"] == "applied":
                    line += " -- DELETED from the file"
                elif removal:
                    line += " -- NOT DELETED, left to a person: " + refusal_text(removal)
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
    summary = ("%d finding(s), %d provider(s) in error, %d not covered (no key)."
               % (count, errors, uncovered))
    if "removals" in result:
        summary += (" %d deletion(s) made, %d left to a person."
                    % (len(removals_of(result, "applied")), len(removals_of(result, "refused"))))
    out.append(summary)
    return "\n".join(out) + "\n"


def run_link():
    server = os.environ.get("GITHUB_SERVER_URL")
    repository = os.environ.get("GITHUB_REPOSITORY")
    run = os.environ.get("GITHUB_RUN_ID")
    if server and repository and run:
        return "%s/%s/actions/runs/%s" % (server, repository, run)
    return None


def pulls_link():
    """Where the deletion pull request is, found by its branch, which the workflow names in
    REMOVALS_BRANCH: the number is not known when the issue body is written."""
    server = os.environ.get("GITHUB_SERVER_URL")
    repository = os.environ.get("GITHUB_REPOSITORY")
    branch = os.environ.get("REMOVALS_BRANCH")
    if server and repository and branch:
        return "%s/%s/pulls?q=is%%3Apr+is%%3Aopen+head%%3A%s" % (
            server, repository, urllib.parse.quote(branch, safe=""))
    return None


def capped(lines):
    if len(lines) <= MAX_LISTED:
        return lines
    return lines[:MAX_LISTED] + ["- … et %d de plus, voir le journal de l'exécution" %
                                 (len(lines) - MAX_LISTED)]


# What a NEW entry is modelled on. The model_name follows the file's own habit (the id, dots turned
# to dashes, the provider's name as a suffix where the provider's names carry one -- not Mistral's
# nor Gemini's, which only name the entries another provider's model is hosted by or a Gemma by it,
# and a name already taken gets the provider's name anyway), the key and the api_base are those
# most of the provider's existing entries use. Only a spelling the file itself
# could hold is copied: a snippet is something a person pastes, and the file is trusted more than
# a catalogue.
NAME_SUFFIXES = {"openrouter": "", "gemini": "", "groq": "-groq", "mistral": "",
                 "cerebras": "-cerebras", "sambanova": "-sambanova", "deepseek": "-direct"}
DEFAULT_BASES = {"sambanova": "https://api.sambanova.ai/v1"}
SAFE_KEY = re.compile(r"os\.environ/[A-Z0-9_]+")
SAFE_BASE = re.compile(r"https?://[A-Za-z0-9._:/-]+")


def provider_basis(entries, provider):
    keys = collections.Counter()
    bases = collections.Counter()
    for entry in entries:
        attributed = attribute(entry["model"], entry["api_base"])
        if attributed and attributed[0] == provider:
            keys[entry["api_key"]] += 1
            bases[entry["api_base"]] += 1
    key = next((k for k, _ in keys.most_common() if isinstance(k, str) and SAFE_KEY.fullmatch(k)),
               None)
    base = bases.most_common(1)[0][0] if bases else DEFAULT_BASES.get(provider)
    if not (isinstance(base, str) and SAFE_BASE.fullmatch(base)):
        base = None
    # The entries of a provider do not all agree on the "api_base" (Gemini's Gemma ones have none):
    # the snippet gets the majority's, and the issue says the choice is open.
    return {"api_key": key, "api_base": base, "mixed": len(bases) > 1}


def propose_name(provider, identifier, taken):
    stem = identifier.split("/")[-1].lower().replace(":free", "-free")
    stem = re.sub(r"[^a-z0-9]+", "-", stem).strip("-") or "model"
    name = stem + ("" if stem.endswith("-free") else NAME_SUFFIXES.get(provider, ""))
    for suffix in ("", "-" + provider, "-new"):
        if name + suffix not in taken:
            name += suffix
            break
    taken.add(name)
    return name


def snippet(provider, identifier, basis, name):
    lines = ["  - model_name: %s" % name,
             "    litellm_params:",
             "      model: %s" % litellm_id(provider, identifier)[0]]
    if basis["api_base"]:
        lines.append('      api_base: "%s"' % basis["api_base"])
    lines.append('      api_key: "%s"' % (basis["api_key"]
                                         or "os.environ/%s_API_KEY_<ACCOUNT>" % provider.upper()))
    return lines


def figure_text(value):
    return "—" if value is None else "%.1f" % value


def place_text(router, place):
    if place.get("ineligible") == "slower":
        return ("`%s` : pas suggéré, plus lent que la liste (%s jetons par seconde contre %s pour %s, le plus "
                "lent des membres dont la vitesse est connue)"
                % (router, figure_text(place["speed"]), figure_text(place["slowest"][1]),
                   code_span(place["slowest"][0], 60)))
    if place.get("ineligible") == "model":
        return "`%s` : pas évalué : vitesse inconnue pour ce modèle, et ce routeur n'accepte pas un modèle sans elle" % router
    if place.get("ineligible") == "members":
        return ("`%s` : pas évalué : vitesse inconnue pour tous les membres de la liste, il n'y a aucune "
                "vitesse à laquelle comparer ce modèle" % router)
    label = RANKING_FIGURES[place["metric"]][0]
    if place["before"]:
        where = "avant %s (%s : %s contre %s pour ce modèle)" % (
            code_span(place["before"][0], 60), label, figure_text(place["before"][1]),
            figure_text(place["value"]))
    else:
        where = "après %s, le dernier classé (%s : %s contre %s pour ce modèle)" % (
            code_span(place["last"][0], 60), label, figure_text(place["last"][1]),
            figure_text(place["value"]))
    return "`%s` : %s, %d membre(s) classé(s) sur %d" % (router, where, place["ranked"], place["of"])


def ranking_section(result):
    """The table of figures of the NEW models and the place each would take, in French: a suggestion
    with its source and its day, whose every row is to be checked, and which nothing applies."""
    ranking, rows = result.get("rankings"), result.get("ranked") or []
    if not ranking or ranking["status"] != "read" or not rows:
        return []
    out = ["## Classement des nouveaux modèles", "",
           "Chiffres lus le %s dans l'API gratuite d'Artificial Analysis, <%s> (source à citer ; "
           "ses « Terms of Use » et « Data Platform Terms » s'appliquent). Le rapprochement entre "
           "l'identifiant du fournisseur et le nom du classement est **approximatif** : chaque ligne "
           "est à vérifier avant d'en tirer une place. La place suggérée compare le chiffre "
           "qui compte pour le routeur (indice d'intelligence pour `pro`, `flash` et `claude-code`, "
           "indice de code pour `code`, vitesse pour `flash-lite`) à celui des membres déjà classés "
           "de sa liste. Pour `flash` et `flash-lite`, un modèle plus lent que le plus lent de ces "
           "membres n'a pas de place suggérée, et un modèle dont la vitesse est inconnue n'est pas "
           "évalué : une vitesse nulle est lue comme non mesurée. Elle ne juge pas le reste de "
           "l'éligibilité (la gratuité, les appels d'outils et le contexte pour `claude-code`, la "
           "variante d'effort de raisonnement sur laquelle un rapprochement peut tomber, comme "
           "« Gemini 4 Argon (High) ») ni la façon dont la liste regroupe aussi les modèles par "
           "fournisseur : ce n'est jamais une décision, et rien ne l'applique."
           % (ranking["date"], RANKING_SITE), "",
           "| Modèle | Rapprochement | Intelligence | Code | Vitesse (jetons/s) | Prix mixte ($/M jetons) |",
           "| --- | --- | --- | --- | --- | --- |"]
    # The matched ones first, since they are the ones with figures to read.
    rows = sorted(rows, key=lambda row: row["model"] is None)
    unlisted, rows = len(rows) - min(len(rows), RANKING_LISTED), rows[:RANKING_LISTED]
    for row in rows:
        identifier, where = litellm_id(row["provider"], row["id"])
        name = "`%s`%s" % (safe_text(identifier, 120), where.replace(" on ", " chez "))
        model = row["model"]
        if model:
            out.append("| %s | %s, par %s : à vérifier | %s | %s | %s | %s |" % (
                name, safe_text(model["name"], 80), "l'identifiant" if row["how"] == "identifiant"
                else "le nom", figure_text(model["intelligence"]), figure_text(model["coding"]),
                figure_text(model["speed"]), figure_text(model["price"])))
        else:
            out.append("| %s | %s | — | — | — | — |" % (
                name, "plusieurs entrées portent ce nom, aucune retenue" if row["how"] == "ambigu"
                else "inconnu de la source"))
    out.append("")
    if unlisted:
        out += ["… et %d autre(s) nouveau(x) modèle(s) sans chiffres ici, à voir dans « Nouveaux modèles à "
                "examiner »." % unlisted, ""]
    places = []
    for row in rows:
        if row["places"]:
            identifier, where = litellm_id(row["provider"], row["id"])
            places.append(["- `%s`%s :" % (safe_text(identifier, 120), where.replace(" on ", " chez "))]
                          + ["  - " + place_text(router, row["places"][router])
                             for router, _ in RANKING_ROUTERS if router in row["places"]])
    if places:
        out += ["Places suggérées, routeur par routeur :", ""] + [line for block in places for line in block] + [""]
    return out


def render_issue_body(result, config_name, link=None):
    body = issue_body(result, config_name, link, snippets=True)
    if len(body) > BODY_LIMIT:
        body = issue_body(result, config_name, link, snippets=False)
    return body


def issue_body(result, config_name, link, snippets):
    applying = "removals" in result
    out = [ISSUE_MARKER, ""]
    out.append(
        "Rapport hebdomadaire de `.github/workflows/LiteLLM_model_drift.yml` : il compare "
        "`%s` sur `main` au catalogue que publie chaque fournisseur. **Ce texte est réécrit à "
        "chaque exécution** : ce qu'on y modifierait à la main serait perdu. L'issue se ferme "
        "d'elle-même à la première exécution sans dérive, et c'est elle qui se rouvre la fois "
        "suivante." % config_name
    )
    out.append("")
    if applying:
        out.append(
            "Une seule sorte de constat se traite sans jugement : un modèle que son fournisseur ne "
            "liste plus. Le workflow le supprime lui-même, sans IA, dans une pull request, en "
            "citant le catalogue lu et la date ; ce qu'il ne peut pas supprimer sans risque reste "
            "ici avec sa raison. Tout le reste se décide ici, après vérification sur la page du "
            "fournisseur (`CLAUDE.md`, « The model list keeps only what can be called » : chaque "
            "affirmation de la liste cite la page du fournisseur et la date) : ajouter un modèle "
            "est un choix, et un retrait annoncé n'est pas encore un retrait."
        )
    else:
        out.append(
            "Rien n'est modifié automatiquement. La règle (`CLAUDE.md`, « The model list keeps "
            "only what can be called ») demande qu'un humain vérifie chaque constat sur la page du "
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

    pulls = pulls_link()
    branch = os.environ.get("REMOVALS_BRANCH")
    help_text = ("Chaque identifiant vient avec une entrée à compléter : le nom de modèle est une "
                 "proposition, la clé et l'`api_base` sont ceux de la plupart des entrées "
                 "existantes du même fournisseur. La coller telle quelle l'active ; pour la "
                 "laisser inactive, insérer `# ` après les deux espaces d'indentation de chaque "
                 "ligne (`  # - model_name: ...`, comme les autres entrées commentées du "
                 "fichier) et écrire au-dessus « Served, but not routed to: <raison> », avec la "
                 "page du fournisseur et la date de la vérification.")
    mixed = sorted(report["name"] for report in result["providers"]
                   if report["basis"].get("mixed") and any(
                       finding["kind"] == "new" for finding in report["findings"]))
    if mixed:
        help_text += (" Les entrées existantes de %s ne s'accordent pas toutes sur l'`api_base` : "
                      "l'entrée proposée a celle de la majorité, à retirer si le modèle ressemble "
                      "à celles qui n'en ont pas." % ", ".join("`%s`" % name for name in mixed))
    sections = {
        "removed": ("Supprimés par la pull request",
                    "Le fournisseur ne les liste plus : le workflow en propose la suppression sur "
                    "%s, entrée, places dans les cascades et commentaire de raison qui ne servait "
                    "qu'à elles. Il ouvre la pull request quand le réglage « Allow GitHub Actions "
                    "to create and approve pull requests » le permet%s ; sinon la branche est là "
                    "et la pull request est à ouvrir. Ils disparaissent de ce rapport une fois la "
                    "suppression fusionnée." % (
                        "la branche %s" % code_span(branch) if branch else "sa branche",
                        " ([la pull request, si elle est ouverte](%s))" % pulls if pulls else ""),),
        "retired": ("Retirés : à supprimer" if not applying
                    else "Retirés : à supprimer à la main",
                    "Entrées actives dont l'identifiant n'est plus au catalogue du fournisseur. "
                    "Supprimer l'entrée **et** ses places dans les cascades."
                    + (" Le workflow ne l'a pas fait, pour la raison donnée à chaque ligne."
                       if applying else "")),
        "gone": ("Entrées commentées retirées : à supprimer" if not applying
                 else "Entrées commentées retirées : à supprimer à la main",
                 "Le fournisseur ne les sert plus : la règle ne garde pas de modèle retiré en "
                 "commentaire, git en garde la trace."
                 + (" Le workflow ne l'a pas fait, pour la raison donnée à chaque ligne."
                    if applying else "")),
        "notice": ("Retraits annoncés",
                   "Entrées actives que le fournisseur marque pour retrait : prévoir leur "
                   "remplacement dans les cascades."),
        "back": ("De nouveau gratuits sur OpenRouter",
                 "Entrées commentées dont la variante `:free` est au catalogue, à 0 $ : relire la "
                 "raison écrite au-dessus, et décommenter si elle ne tient plus."),
        "new_free": ("Nouveaux modèles gratuits sur OpenRouter",
                     "`:free` et à 0 $, sortie texte uniquement. À ajouter, ou à commenter avec "
                     "sa raison, ou à écarter par une ligne `# drift-ignore: <fournisseur>/<id> -- "
                     "<raison>` dans le fichier." + (" " + help_text if snippets else "")),
        "new_examine": ("Nouveaux modèles à examiner",
                        "Leur gratuité ne se lit pas dans l'API du fournisseur : la vérifier sur "
                        "sa page de tarifs avant de les router, et sinon les écarter comme "
                        "ci-dessus." + (" " + help_text if snippets else "")),
    }
    taken = set(result.get("names", ()))
    for kind in ("removed", "retired", "gone", "notice", "back", "new_free", "new_examine"):
        lines = []
        for report in result["providers"]:
            for finding in report["findings"]:
                finding_kind = finding["kind"]
                removal = finding.get("removal")
                if finding_kind == "new":
                    finding_kind = "new_free" if finding["free"] else "new_examine"
                elif removal and removal["status"] == "applied":
                    finding_kind = "removed"
                if finding_kind != kind:
                    continue
                identifier, where = litellm_id(report["name"], finding["id"])
                line = "- `%s`%s" % (identifier, where.replace(" on ", " chez "))
                if finding.get("names"):
                    line += " (%s)" % ", ".join("`%s`" % name for name in finding["names"])
                if kind == "notice":
                    line += " : " + notice_text(finding["notice"], french=True)
                if kind.startswith("new") and finding.get("label"):
                    line += " : `%s`" % finding["label"]
                if removal and removal["status"] == "refused":
                    line += " : **non supprimé par le workflow** : " + refusal_text(removal, True)
                if kind.startswith("new") and snippets:
                    name = propose_name(report["name"], finding["id"], taken)
                    block = snippet(report["name"], finding["id"], report["basis"], name)
                    line += "\n" + "\n".join(
                        ["  ```yaml"] + ["  " + code for code in block] + ["  ```"])
                lines.append(line)
        if lines:
            title, explanation = sections[kind][0], sections[kind][1]
            out += ["## %s" % title, "", explanation, ""] + capped(lines) + [""]

    out += ranking_section(result)

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
        out += ["- %s : %s" % (report["name"], code_span(report["error"]))
                for report in errors] + [""]

    ranking = result.get("rankings")
    if ranking and ranking["status"] == "error":
        out += ["## Classements non lus", "",
                "La source des classements n'a pas pu être lue : aucune place n'est suggérée cette "
                "semaine pour les nouveaux modèles. Rien d'autre n'en dépend, ni les suppressions ni "
                "la fermeture de cette issue.", "", "- Artificial Analysis : %s"
                % code_span(ranking["error"]), ""]

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
    if ranking:
        if ranking["status"] == "no key":
            state, members = "non couvert (pas de clé : secret `%s`)" % ranking["key"], "—"
        elif ranking["status"] == "error":
            state, members = "erreur", "—"
        else:
            state, members = "lu", str(len(ranking["models"]))
        out.append("| Artificial Analysis (classements) | %s | %s | — | — |" % (state, members))
    out.append("")
    if result["unattributed"]:
        out.append("Entrées actives d'aucun catalogue lu ici : %s."
                   % ", ".join("`%s`" % model for model in result["unattributed"]))
        out.append("")
    if exit_status(result) == 0:
        out += ["Aucune dérive.", ""]
    return "\n".join(out) + "\n"


def code_span(text, limit=100):
    """"text" as a markdown code span, which shows it as it is and makes nothing of it: no link, no
    mention, no markup. The one character that could end the span is replaced, and a text longer
    than "limit" is cut between two words and says so."""
    flat = " ".join(str(text).split()).replace("`", "'")
    if len(flat) > limit:
        head = flat[:limit]
        flat = (head.rsplit(" ", 1)[0] if " " in head else head).rstrip(" ,;:") + "…"
    return "`%s`" % flat


def slots_text(slots):
    """Where an entry's cascade slots were, for a person: the cascades, grouped by section."""
    by_where = {}
    for where, source in slots:
        sources = by_where.setdefault(where, [])
        if source and source not in sources:
            sources.append(source)
    parts = []
    for where, sources in by_where.items():
        if not sources:
            parts.append("`%s`" % where)
        else:
            quoted = ["`%s`" % source for source in sources]
            parts.append("%s %s de `%s`" % (
                "la cascade" if len(quoted) == 1 else "les cascades",
                ", ".join(quoted[:-1]) + (" et " if len(quoted) > 1 else "") + quoted[-1], where))
    return "; ".join(parts)


def count_phrase(count, singular, plural):
    return "%d %s" % (count, singular if count == 1 else plural)


def catalogue_url(provider):
    return next(url for name, url, _, _, _, _ in PROVIDERS if name == provider)


def render_pr_body(result, link=None):
    """The body of the pull request that carries the deletions, in French: for every deletion the
    provider, the id, the catalogue that was read and the day it was read."""
    applied = removals_of(result, "applied")
    refused = removals_of(result, "refused")
    out = [
        "Suppressions faites **sans IA** par `.github/workflows/LiteLLM_model_drift.yml`, à "
        "l'exécution du %s%s. Chaque modèle ci-dessous est absent du catalogue que son fournisseur "
        "publie ce jour-là, et la règle de `CLAUDE.md` (« The model list keeps only what can be "
        "called ») veut qu'un modèle retiré soit **supprimé**, entrée et places de cascade "
        "ensemble : git en garde la trace." % (result["date"], " (%s)" % link if link else ""),
        "",
        "Cette pull request est réécrite à chaque exécution à partir de `main`, titre et corps "
        "compris (une modification à la main de l'un ou de l'autre est perdue à la suivante), tant "
        "que sa branche ne porte que des commits du workflow ou des commits de fusion (celui du "
        "bouton « Update branch » en est un). Un commit ajouté par quelqu'un d'autre la fige : le "
        "workflow n'y touche plus, même s'il n'y a plus rien à supprimer, et son exécution "
        "échoue chaque semaine pour le dire, jusqu'à ce que la branche soit supprimée. "
        "Fermée sans être fusionnée, elle est remplacée par une nouvelle à l'exécution suivante si "
        "les fournisseurs ne listent toujours pas ces modèles ; fusionnée, ces modèles "
        "disparaissent de l'issue hebdomadaire à l'exécution d'après.",
        "",
        "Elle se fusionne seule quand aucune section « À relire » n'y figure, que les lignes "
        "supprimées sont uniquement des entrées entières, les places de cascade qui les nomment, "
        "des commentaires ou des lignes vides, qu'elle reste sous les plafonds d'entrées et de "
        "lignes fixés par `.github/workflows/dependabot-auto-merge.yml`, que sa branche contient "
        "tout `main` et que les contrôles que ce workflow attend sont verts. Sinon elle attend "
        "une personne.",
        "",
        "## %s" % ("Suppression" if len(applied) == 1 else "Suppressions"),
        "",
    ]
    lines = []
    for report, finding in applied:
        removal = finding["removal"]
        identifier = safe_text(litellm_id(report["name"], finding["id"])[0], 120)
        names = ", ".join("`%s`" % safe_text(entry["name"], 80) for entry in removal["entries"])
        states = {entry["state"] for entry in removal["entries"]}
        what = ("entrée active" if states == {"active"} else
                "entrée commentée" if states == {"commented"} else "entrées")
        line = "- `%s` chez %s : %s %s supprimée" % (
            identifier, PROVIDER_LABELS[report["name"]], what, names)
        if removal["slots"]:
            line += ", avec ses places dans " + slots_text(removal["slots"])
        line += ". Absent du catalogue <%s>, lu le %s." % (catalogue_url(report["name"]),
                                                          result["date"])
        lines.append(line)
    out += capped(lines) + [""]

    heads = (result.get("removals") or {}).get("heads") or []
    if heads:
        out += ["## Table `head` réécrite", "",
                "La table `head` du template dit quel modèle répond à chaque routeur selon les clés "
                "fournisseurs données : elle recopie l'ordre des listes de secours. Une suppression "
                "qui retire le premier modèle d'un fournisseur la change, et le workflow a **réécrit "
                "les lignes concernées à partir des listes qui restent**, puis relu le résultat pour "
                "chaque ensemble de clés. Cette pull request ajoute donc des lignes : elle ne se "
                "fusionne pas seule, une personne relit celles-ci.", "", "```diff"]
        for router, before, after in heads:
            out += ["-  '%s': %s" % (router, before), "+  '%s': %s" % (router, after)]
        out += ["```", ""]

    prose = [(report, finding) for report, finding in applied if finding["removal"]["prose"]]
    if prose:
        out += ["## Commentaires supprimés avec elles", "",
                "La raison d'un groupe d'entrées commentées (le « not routed to: » que le contrôle "
                "exige) ne motive que ce groupe : elle part avec lui quand toutes ses entrées "
                "partent, et reste au-dessus de celles qui restent sinon.", ""]
        for report, finding in prose:
            for removed in finding["removal"]["prose"]:
                out.append("- avec `%s` : %s, dont la première est %s." % (
                    safe_text(litellm_id(report["name"], finding["id"])[0], 120),
                    count_phrase(removed["lines"], "ligne de commentaire", "lignes de commentaire"),
                    code_span(removed["first"])))
        out.append("")

    review = sorted(((report, finding, item) for report, finding in applied
                     for item in finding["removal"]["review"]), key=lambda row: row[2]["line"])
    if review:
        # "dependabot-auto-merge.yml" lets the pull request merge itself only when its body has no
        # section of this exact title: a person has to read what this lists.
        out += [REVIEW_HEADING, "",
                "Le workflow ne réécrit aucune prose, et le contrôle ne lit pas les commentaires : "
                "un commentaire peut dire ce qui n'est plus vrai une fois ces entrées parties, ou "
                "décrire une entrée voisine, et seule une personne le voit. Ces lignes du nouveau "
                "fichier sont celles à relire :", ""]
        lines = []
        for report, finding, item in review:
            where = ("ligne %d" % item["line"] if item["line"] == item["last"]
                     else "lignes %d à %d" % (item["line"], item["last"]))
            deleted = safe_text(litellm_id(report["name"], finding["id"])[0], 120)
            text = {
                "left": "restées au-dessus de l'entrée supprimée `%s`" % deleted,
                "kept": "la raison d'un groupe d'entrées commentées dont `%s` a été retirée, "
                        "gardée au-dessus de celles qui restent : elle peut les compter, ou "
                        "nommer une entrée qui n'est plus là" % deleted,
                "banner": "l'en-tête d'une section qui n'a plus aucune entrée depuis la "
                          "suppression de `%s`" % deleted,
                "mention": "cite `%s`, supprimé" % safe_text(item["subject"] or "", 120),
            }[item["why"]]
            lines.append("- %s (%s) : %s." % (where, code_span(item["first"]), text))
        out += capped(lines) + [""]

    if refused:
        out += ["## Non supprimé par le workflow", "",
                "Ces modèles sont retirés eux aussi, mais les supprimer demande un choix : ils "
                "restent dans l'issue hebdomadaire, avec la raison.", ""]
        out += capped(["- `%s` : %s." % (safe_text(litellm_id(report["name"], finding["id"])[0],
                                                    120),
                                           refusal_text(finding["removal"], True))
                       for report, finding in refused]) + [""]

    unread = [report["name"] for report in result["providers"] if report["status"] != "read"]
    if unread:
        out += ["## Catalogues non lus", "",
                "Ces catalogues n'ont pas été lus à cette exécution (pas de clé, ou erreur) : %s. "
                "Cette pull request ne dit rien de leurs modèles, et une suppression qui les "
                "concerne n'y viendra qu'à une exécution qui les lira." % ", ".join(
                    "`%s`" % name for name in unread), ""]

    out += ["## Vérification", "",
            "Le résultat est relu avant d'être écrit : il doit se lire comme le fichier d'origine "
            "moins ces entrées et leurs places de cascade, et ne casser aucune règle du mode hors "
            "ligne que le fichier d'origine ne cassait pas déjà. Cette relecture porte sur la "
            "structure du fichier, pas sur ses commentaires : ce qui peut avoir changé de sens "
            "est listé plus haut. Une pull request ouverte avec le jeton du workflow ne lance "
            "aucun contrôle : le workflow relance `ansible-ci.yml` et `gitleaks.yml` sur la "
            "branche, leurs résultats s'affichent ici.",
            ""]
    return "\n".join(out)


def wrapped(text):
    return textwrap.fill(text, width=100)


def render_commit_message(result):
    """The commit that carries the deletions, in English like every commit here."""
    applied = removals_of(result, "applied")
    counts = collections.Counter(PROVIDER_LABELS[report["name"]] for report, _ in applied)
    by_provider = ", ".join("%s (%d)" % (label, count) for label, count in sorted(counts.items()))
    heads = (result.get("removals") or {}).get("heads") or []
    written_again = ("\n\n" + wrapped(
        "The head table of the template repeats the order of the cascades and names the model each "
        "router is an alias of. A deletion took a model it names, so its rows were written again "
        "from the cascades that are left, and the result was read back for every set of provider "
        "keys.")) if heads else ""
    return (
        "Delete the models their provider has retired from the LiteLLM model list (#243)\n\n"
        + wrapped("The weekly drift check read each provider's own model catalogue on %s "
                  "and found %s it no longer lists, from %s. The pull request that carries this "
                  "commit names each of them and the catalogue it was missing from."
                  % (result["date"], count_phrase(len(applied), "id", "ids"), by_provider))
        + "\n\n"
        + wrapped("Their entries, their slots in the fallback cascades and the comment that gave "
                  "a commented-out group its reason, where every entry of the group is going, are "
                  "deleted, which is what the rule of CLAUDE.md asks of a model its provider has "
                  "retired.")
        + "\n\n"
        + wrapped("Nothing here was a judgment, which is why no person and no model made it: "
                  "check_LiteLLM_model_drift.py --apply deletes a model only when the catalogue "
                  "no longer lists it, only when the cascades and aliases it leaves behind still "
                  "name an active entry, and only after reading the result back against the "
                  "original. What it could not delete without choosing stays in the weekly "
                  "issue, with the reason; so do additions and announced retirements, which are "
                  "choices.")
        + written_again
        + "\n")


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
    ("a cascade keyed on an alias is accepted",
     ("    - flash:\n", "    - auto:\n"), None),
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


def answers_listing(text, without=()):
    """Canned catalogues that list exactly the ids "text" holds, active or commented out, less the
    (provider, id) pairs of "without": the answers to retire models from."""
    template, _ = read_template(text)
    ids = collections.defaultdict(set)
    for entry in template["active"] + template["commented"]:
        attributed = attribute(entry["model"], entry["api_base"])
        if attributed and attributed not in without:
            ids[attributed[0]].add(attributed[1])
    return {
        "openrouter": {"data": [openrouter_model(i) for i in sorted(ids["openrouter"])]},
        "cerebras": {"data": [{"id": i} for i in sorted(ids["cerebras"])]},
        "sambanova": {"data": [{"id": i} for i in sorted(ids["sambanova"])]},
        "gemini": [{"models": [{"name": "models/" + i, "supportedGenerationMethods":
                                ["generateContent"]} for i in sorted(ids["gemini"])]}],
        "groq": {"data": [{"id": i, "active": True} for i in sorted(ids["groq"])]},
        "mistral": {"data": [{"id": i, "capabilities": {"completion_chat": True}}
                             for i in sorted(ids["mistral"])]},
        "deepseek": {"data": [{"id": i} for i in sorted(ids["deepseek"])]},
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
        if url == RANKING_URL:
            answer = answers["rankings"]
            if isinstance(answer, Exception):
                raise answer
            return answer if isinstance(answer, bytes) else json.dumps(answer).encode()
        for name, base in urls.items():
            if not url.startswith(base):
                continue
            answer = answers[name]
            if isinstance(answer, Exception):
                raise answer
            if name == "gemini" and isinstance(answer, list):
                answer = answer[1] if "&pageToken=second" in url else answer[0]
            return answer if isinstance(answer, bytes) else json.dumps(answer).encode()
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
        ("a reason phrase that carries a key and an address reaches neither the report nor the "
         "issue: the status is all that is shown",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         changed("deepseek", urllib.error.HTTPError(
             "https://selftest.invalid/", 500,
             "Invalid key selftest-deepseek-key-SECRET see https://evil.example/login", None,
             io.BytesIO(b"{}"))),
         no_drift, 2,
         lambda result, calls, report, body: (
             "the reason phrase was shown"
             if any(needle in report + body for needle in ("SECRET", "evil", "Invalid"))
             else None if "HTTP 500" in report and "`HTTP 500`" in body
             else "the status is not shown")),
        ("a key that a network error carries is replaced before the error is shown",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         changed("groq", urllib.error.URLError("refused for selftest-groq-key-SECRET")),
         no_drift, 2,
         lambda result, calls, report, body: (
             "a key reached the output" if "SECRET" in report + body
             else None if "refused for ***" in report and "`network error: refused for ***`" in body
             else "the key was not replaced")),
        ("a model whose fields have a type nobody documented is skipped, not a crash",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         dict(changed("gemini", [{"models": base["gemini"][0]["models"] + [
             {"name": "models/gemini-odd", "supportedGenerationMethods": 5}],
              "nextPageToken": 5}]),
              mistral={"data": base["mistral"]["data"] + [
                  {"id": "mistral-odd", "aliases": 5, "capabilities": {"completion_chat": False}}]}),
         no_drift, 0, None),
        ("a catalogue nested too deeply to parse is that provider's error, not a crash",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         changed("groq", b"[" * 100000 + b"]" * 100000), no_drift, 2,
         lambda result, calls, report, body: (
             None if "groq" in report and "nested too deeply" in report
             else "the report does not say that the Groq answer could not be read")),
        ("a rule broken on main is reported online too",
         SELFTEST_TEMPLATE.replace("        - local\n", "        - gone\n"), SELFTEST_KEYS, base,
         no_drift, 1,
         lambda result, calls, report, body: (
             None if "## Règles du fichier" in body and result["rules"]
             else "the broken rule is not in the issue body")),
    )


# A file with every structure a deletion has to take apart: virtual routers that cascades start
# from, an alias in each of its two spellings, prose above an active entry, a run of three
# commented-out entries under one reason, a banner that is itself a reason, a banner that is only a
# heading over entries which stay, a model id two entries share, a cascade with a single target.
APPLY_TEMPLATE = """\
model_list:
  # ============================================================================
  # Virtual routers
  # ============================================================================
  - model_name: router
    litellm_params:
      model: gemini/gemini-9-pro
      api_key: "os.environ/GEMINI_API_KEY_SELFTEST"

  - model_name: router-two
    litellm_params:
      model: gemini/gemini-9-flash
      api_key: "os.environ/GEMINI_API_KEY_SELFTEST"

  - model_name: router-solo
    litellm_params:
      model: gemini/gemini-9-lite
      api_key: "os.environ/GEMINI_API_KEY_SELFTEST"

  # ============================================================================
  # Groq
  # ============================================================================
  # Prose about alpha, which may as well be about its neighbours.
  - model_name: alpha-groq
    litellm_params:
      model: groq/vendor/alpha
      api_key: "os.environ/GROQ_API_KEY_SELFTEST"

  - model_name: beta-groq
    litellm_params:
      model: groq/vendor/beta
      api_key: "os.environ/GROQ_API_KEY_SELFTEST"

  - model_name: gamma-groq
    litellm_params:
      model: groq/vendor/gamma
      api_key: "os.environ/GROQ_API_KEY_SELFTEST"

  - model_name: solo-groq
    litellm_params:
      model: groq/vendor/solo
      api_key: "os.environ/GROQ_API_KEY_SELFTEST"

  - model_name: shared-one
    litellm_params:
      model: groq/vendor/shared
      api_key: "os.environ/GROQ_API_KEY_SELFTEST"

  - model_name: shared-two
    litellm_params:
      model: groq/vendor/shared
      api_key: "os.environ/GROQ_API_KEY_SELFTEST"

  - model_name: aliased-groq
    litellm_params:
      model: groq/vendor/aliased
      api_key: "os.environ/GROQ_API_KEY_SELFTEST"

  # ============================================================================
  # OpenRouter (":free" entries only)
  # ============================================================================
  - model_name: free-a
    litellm_params:
      model: openrouter/vendor/a:free
      api_key: "os.environ/OPENROUTER_API_KEY_SELFTEST"

  - model_name: free-b
    litellm_params:
      model: openrouter/vendor/b:free
      api_key: "os.environ/OPENROUTER_API_KEY_SELFTEST"

  # Served, but not routed to: paid only.
  # - model_name: paid-a
  #   litellm_params:
  #     model: openrouter/vendor/paid-a
  #     api_key: "os.environ/OPENROUTER_API_KEY_SELFTEST"
  #
  # - model_name: paid-b
  #   litellm_params:
  #     model: openrouter/vendor/paid-b
  #     api_key: "os.environ/OPENROUTER_API_KEY_SELFTEST"
  #
  # - model_name: paid-c
  #   litellm_params:
  #     model: openrouter/vendor/paid-c
  #     api_key: "os.environ/OPENROUTER_API_KEY_SELFTEST"

  # ============================================================================
  # SambaNova -- not routed to: a payment method comes first.
  # ============================================================================
  # - model_name: sn-a
  #   litellm_params:
  #     model: openai/SN-A
  #     api_base: "https://api.sambanova.ai/v1"
  #     api_key: "os.environ/SAMBANOVA_API_KEY_SELFTEST"
  #
  # - model_name: sn-b
  #   litellm_params:
  #     model: openai/SN-B
  #     api_base: "https://api.sambanova.ai/v1"
  #     api_key: "os.environ/SAMBANOVA_API_KEY_SELFTEST"

  # ============================================================================
  # Cerebras and Groq, a heading over entries which stay
  # ============================================================================
  # Cerebras: both models below are not routed to, because a bank card is required.
  # drift-ignore: openrouter/vendor/noise:free -- selftest: looked at and turned down
  # - model_name: cb-a
  #   litellm_params:
  #     model: cerebras/cb-a
  #     api_key: "os.environ/CEREBRAS_API_KEY_SELFTEST"
  #
  # - model_name: cb-b
  #   litellm_params:
  #     model: cerebras/cb-b
  #     api_key: "os.environ/CEREBRAS_API_KEY_SELFTEST"

  - model_name: later-groq
    litellm_params:
      model: groq/vendor/later
      api_key: "os.environ/GROQ_API_KEY_SELFTEST"

router_settings:
  fallbacks:
    - router:
        - alpha-groq
        - beta-groq
        - free-a
        - shared-one
    - router-two:
        - beta-groq
        - gamma-groq
    - router-solo:
        - solo-groq
        - shared-two
  context_window_fallbacks:
    - router:
        - free-b
        - alpha-groq
  content_policy_fallbacks:
    - router-two:
        - gamma-groq
  model_group_alias:
    "auto": "router"
    "hidden": {"model": "aliased-groq", "hidden": true}

litellm_settings:
  default_fallbacks:
    - free-a
    - alpha-groq
  per_model_timeout:
    "later-groq": 30
"""


def groq_entry(name, identifier):
    return ('  - model_name: %s\n    litellm_params:\n      model: groq/vendor/%s\n'
            '      api_key: "os.environ/GROQ_API_KEY_SELFTEST"\n' % (name, identifier))


def commented_entry(name, model, key, base=False):
    return ("  # - model_name: %s\n  #   litellm_params:\n  #     model: %s\n%s"
            '  #     api_key: "os.environ/%s_API_KEY_SELFTEST"\n'
            % (name, model, '  #     api_base: "https://api.sambanova.ai/v1"\n' if base else "", key))


PAID_REASON = "  # Served, but not routed to: paid only.\n"
OPENROUTER_BANNER = (
    "  # ============================================================================\n"
    '  # OpenRouter (":free" entries only)\n'
    "  # ============================================================================\n")
SAMBANOVA_BANNER = (
    "  # ============================================================================\n"
    "  # SambaNova -- not routed to: a payment method comes first.\n"
    "  # ============================================================================\n")
CEREBRAS_PROSE = ("  # Cerebras: both models below are not routed to, because a bank card is "
                  "required.\n")
DRIFT_IGNORE_LINE = ("  # drift-ignore: openrouter/vendor/noise:free -- selftest: looked at and "
                     "turned down\n")

# (what the case proves, a change made to APPLY_TEMPLATE first as (old, new) pairs, the
# (provider, id, kind) deletions asked for, the changes the result must show against the changed
# template as (old, new) pairs, and the refusals expected as {(provider, id): code}). A refused
# deletion changes nothing, so a case that only refuses expects no change at all.
APPLY_CASES = (
    ("an active entry goes with its slot in every cascade, the prose above it is left where it "
     "is, and so is the blank line after it",
     (), [("groq", "vendor/alpha", "retired")],
     [(groq_entry("alpha-groq", "alpha"), ""),
      ("    - router:\n        - alpha-groq\n        - beta-groq\n",
       "    - router:\n        - beta-groq\n"),
      ("        - free-b\n        - alpha-groq\n", "        - free-b\n"),
      ("    - free-a\n    - alpha-groq\n", "    - free-a\n")],
     {}),
    ("an active entry with no prose above it takes the blank line after it too",
     (), [("groq", "vendor/beta", "retired")],
     [(groq_entry("beta-groq", "beta") + "\n", ""),
      ("        - alpha-groq\n        - beta-groq\n        - free-a\n",
       "        - alpha-groq\n        - free-a\n"),
      ("    - router-two:\n        - beta-groq\n        - gamma-groq\n",
       "    - router-two:\n        - gamma-groq\n")],
     {}),
    ("the first entry under a banner goes with the blank line after it, and the banner stays "
     "over the next",
     (), [("openrouter", "vendor/a:free", "retired")],
     [(OPENROUTER_BANNER + "  - model_name: free-a\n    litellm_params:\n"
       "      model: openrouter/vendor/a:free\n"
       '      api_key: "os.environ/OPENROUTER_API_KEY_SELFTEST"\n\n',
       OPENROUTER_BANNER),
      ("        - beta-groq\n        - free-a\n        - shared-one\n",
       "        - beta-groq\n        - shared-one\n"),
      ("    - free-a\n    - alpha-groq\n", "    - alpha-groq\n")],
     {}),
    ("an id two entries share takes both entries, and a slot in each of their cascades",
     (), [("groq", "vendor/shared", "retired")],
     [(groq_entry("shared-one", "shared") + "\n", ""),
      (groq_entry("shared-two", "shared") + "\n", ""),
      ("        - free-a\n        - shared-one\n", "        - free-a\n"),
      ("        - solo-groq\n        - shared-two\n", "        - solo-groq\n")],
     {}),
    ("the last target of a cascade is not deleted: the cascade would answer nothing",
     (), [("groq", "vendor/gamma", "retired")], [],
     {("groq", "vendor/gamma"): "emptied"}),
    ("two models that are each deletable alone are not when they are the whole of a cascade",
     (), [("groq", "vendor/solo", "retired"), ("groq", "vendor/shared", "retired")], [],
     {("groq", "vendor/solo"): "emptied", ("groq", "vendor/shared"): "emptied"}),
    ("one of those two goes alone, and the cascade keeps the other",
     (), [("groq", "vendor/solo", "retired")],
     [(groq_entry("solo-groq", "solo") + "\n", ""),
      ("        - solo-groq\n        - shared-two\n", "        - shared-two\n")],
     {}),
    ("a model an alias points at is not deleted, whichever way the alias is written",
     (), [("groq", "vendor/aliased", "retired")], [],
     {("groq", "vendor/aliased"): "alias"}),
    ("a virtual router, the entry point of a cascade, is not deleted",
     (), [("gemini", "gemini-9-pro", "retired")], [],
     {("gemini", "gemini-9-pro"): "source"}),
    ("a name used somewhere this tool does not know is not deleted",
     (), [("groq", "vendor/later", "retired")], [],
     {("groq", "vendor/later"): "stray"}),
    ("a slot written inside a flow list is not edited, and its model is not deleted",
     (("    - router-two:\n        - beta-groq\n        - gamma-groq\n",
       "    - router-two: [beta-groq, gamma-groq]\n"),),
     [("groq", "vendor/beta", "retired")], [],
     {("groq", "vendor/beta"): "form"}),
    ("a comment inside an entry, even at the indentation of its dash, goes with the entry",
     (("      model: groq/vendor/solo\n      api_key:",
       "      model: groq/vendor/solo\n  # a remark at the dash's indentation\n      api_key:"),),
     [("groq", "vendor/solo", "retired")],
     [("  - model_name: solo-groq\n    litellm_params:\n      model: groq/vendor/solo\n"
       "  # a remark at the dash's indentation\n"
       '      api_key: "os.environ/GROQ_API_KEY_SELFTEST"\n\n', ""),
      ("        - solo-groq\n        - shared-two\n", "        - shared-two\n")],
     {}),
    ("the first entry of a run goes, and the reason stays above the next one",
     (), [("openrouter", "vendor/paid-a", "gone")],
     [(commented_entry("paid-a", "openrouter/vendor/paid-a", "OPENROUTER") + "  #\n", "")],
     {}),
    ("a middle entry goes with the separator after it",
     (), [("openrouter", "vendor/paid-b", "gone")],
     [(commented_entry("paid-b", "openrouter/vendor/paid-b", "OPENROUTER") + "  #\n", "")],
     {}),
    ("the last entry goes with the separator before it, which would hang from the one above",
     (), [("openrouter", "vendor/paid-c", "gone")],
     [("  #\n" + commented_entry("paid-c", "openrouter/vendor/paid-c", "OPENROUTER"), "")],
     {}),
    ("the two ends of a run go and the middle one keeps the reason",
     (), [("openrouter", "vendor/paid-a", "gone"), ("openrouter", "vendor/paid-c", "gone")],
     [(commented_entry("paid-a", "openrouter/vendor/paid-a", "OPENROUTER") + "  #\n", ""),
      ("  #\n" + commented_entry("paid-c", "openrouter/vendor/paid-c", "OPENROUTER"), "")],
     {}),
    ("a run deleted whole takes its reason with it, and leaves one blank line, not two",
     (), [("openrouter", "vendor/paid-%s" % letter, "gone") for letter in "abc"],
     [(PAID_REASON
       + commented_entry("paid-a", "openrouter/vendor/paid-a", "OPENROUTER") + "  #\n"
       + commented_entry("paid-b", "openrouter/vendor/paid-b", "OPENROUTER") + "  #\n"
       + commented_entry("paid-c", "openrouter/vendor/paid-c", "OPENROUTER") + "\n", "")],
     {}),
    ("a banner that is itself the reason goes with the run it heads",
     (), [("sambanova", "SN-A", "gone"), ("sambanova", "SN-B", "gone")],
     [(SAMBANOVA_BANNER
       + commented_entry("sn-a", "openai/SN-A", "SAMBANOVA", base=True) + "  #\n"
       + commented_entry("sn-b", "openai/SN-B", "SAMBANOVA", base=True) + "\n", "")],
     {}),
    ("a banner that is only a heading stays, and so does a drift-ignore line",
     (), [("cerebras", "cb-a", "gone"), ("cerebras", "cb-b", "gone")],
     [(CEREBRAS_PROSE, ""),
      (commented_entry("cb-a", "cerebras/cb-a", "CEREBRAS") + "  #\n"
       + commented_entry("cb-b", "cerebras/cb-b", "CEREBRAS"), "")],
     {}),
    ("a reason that a drift-ignore line lets the next entry lean on is not deleted from under it",
     (("  #\n  # - model_name: paid-b", DRIFT_IGNORE_LINE + "  # - model_name: paid-b"),),
     [("openrouter", "vendor/paid-a", "gone")], [],
     {("openrouter", "vendor/paid-a"): "verification"}),
    ("a deletion that fails verification does not hold back one that passes",
     (("  #\n  # - model_name: paid-b", DRIFT_IGNORE_LINE + "  # - model_name: paid-b"),),
     [("openrouter", "vendor/paid-a", "gone"), ("groq", "vendor/solo", "retired")],
     [(groq_entry("solo-groq", "solo") + "\n", ""),
      ("        - solo-groq\n        - shared-two\n", "        - shared-two\n")],
     {("openrouter", "vendor/paid-a"): "verification"}),
    ("an id the file has no entry for is not invented",
     (), [("groq", "vendor/nowhere", "retired")], [],
     {("groq", "vendor/nowhere"): "unlocated"}),
    ("deletions of several kinds at once come out as the sum of each alone",
     (), [("groq", "vendor/alpha", "retired"), ("openrouter", "vendor/paid-b", "gone"),
          ("sambanova", "SN-A", "gone"), ("groq", "vendor/solo", "retired")],
     [(groq_entry("alpha-groq", "alpha"), ""),
      ("    - router:\n        - alpha-groq\n        - beta-groq\n",
       "    - router:\n        - beta-groq\n"),
      ("        - free-b\n        - alpha-groq\n", "        - free-b\n"),
      ("    - free-a\n    - alpha-groq\n", "    - free-a\n"),
      (commented_entry("paid-b", "openrouter/vendor/paid-b", "OPENROUTER") + "  #\n", ""),
      (commented_entry("sn-a", "openai/SN-A", "SAMBANOVA", base=True) + "  #\n", ""),
      (groq_entry("solo-groq", "solo") + "\n", ""),
      ("        - solo-groq\n        - shared-two\n", "        - shared-two\n")],
     {}),
    ("the last entry of a file takes the blank line before it, which would end the file",
     ((APPLY_TEMPLATE[APPLY_TEMPLATE.index("\nrouter_settings:\n"):], ""),),
     [("groq", "vendor/later", "retired")],
     [("\n" + groq_entry("later-groq", "later"), "")],
     {}),
    ("and a file that ended on no newline still ends on none",
     ((APPLY_TEMPLATE[APPLY_TEMPLATE.index("\nrouter_settings:\n"):], ""),
      (groq_entry("later-groq", "later"), groq_entry("later-groq", "later").rstrip("\n"))),
     [("groq", "vendor/later", "retired")],
     [('  #     model: cerebras/cb-b\n  #     api_key: "os.environ/CEREBRAS_API_KEY_SELFTEST"\n\n'
       + groq_entry("later-groq", "later").rstrip("\n"),
       '  #     model: cerebras/cb-b\n  #     api_key: "os.environ/CEREBRAS_API_KEY_SELFTEST"')],
     {}),
    ("a finding asked for twice is one deletion, not a refusal and a deletion",
     (), [("groq", "vendor/alpha", "retired"), ("groq", "vendor/alpha", "gone")],
     [(groq_entry("alpha-groq", "alpha"), ""),
      ("    - router:\n        - alpha-groq\n        - beta-groq\n",
       "    - router:\n        - beta-groq\n"),
      ("        - free-b\n        - alpha-groq\n", "        - free-b\n"),
      ("    - free-a\n    - alpha-groq\n", "    - free-a\n")],
     {}),
    ("Jinja written out literally in a raw block is not a statement of the file",
     (("model_list:\n", "model_list:\n{% raw %}\n# the template writes {% if x %} literally\n"
       "{% endraw %}\n"),),
     [("groq", "vendor/alpha", "retired")],
     [(groq_entry("alpha-groq", "alpha"), ""),
      ("    - router:\n        - alpha-groq\n        - beta-groq\n",
       "    - router:\n        - beta-groq\n"),
      ("        - free-b\n        - alpha-groq\n", "        - free-b\n"),
      ("    - free-a\n    - alpha-groq\n", "    - free-a\n")],
     {}),
    ("an entry wrapped in a Jinja block is deleted alone: the block it sits in is not its own, and "
     "stays, empty",
     ((groq_entry("solo-groq", "solo"),
       "{% if Artificial_Intelligence_LiteLLM_Groq_API_key %}\n" + groq_entry("solo-groq", "solo") + "{% endif %}\n"),),
     [("groq", "vendor/solo", "retired")],
     [(groq_entry("solo-groq", "solo"), ""),
      ("        - solo-groq\n        - shared-two\n", "        - shared-two\n")],
     {}),
    ("nor is a loop it sits in taken",
     ((groq_entry("solo-groq", "solo"),
       "{% for account in ['main'] %}\n" + groq_entry("solo-groq", "solo") + "{% endfor %}\n"),),
     [("groq", "vendor/solo", "retired")],
     [(groq_entry("solo-groq", "solo"), ""),
      ("        - solo-groq\n        - shared-two\n", "        - shared-two\n")],
     {}),
    ("nor is the closing tag that follows a blank line",
     ((groq_entry("solo-groq", "solo"),
       "{% if Artificial_Intelligence_LiteLLM_Groq_API_key %}\n" + groq_entry("solo-groq", "solo") + "\n{% endif %}\n"),),
     [("groq", "vendor/solo", "retired")],
     [(groq_entry("solo-groq", "solo") + "\n", ""),
      ("        - solo-groq\n        - shared-two\n", "        - shared-two\n")],
     {}),
    ("an entry whose branch is closed by an else is not deleted: the rendering shows one of the two "
     "branches, so the file as written is not read",
     ((groq_entry("beta-groq", "beta") + "\n" + groq_entry("gamma-groq", "gamma"),
       "{% if Artificial_Intelligence_LiteLLM_Groq_API_key %}\n" + groq_entry("beta-groq", "beta") + "{% else %}\n"
       + groq_entry("gamma-groq", "gamma") + "{% endif %}\n"),),
     [("groq", "vendor/beta", "retired")], [],
     {("groq", "vendor/beta"): "unlocated"}),
    ("nor one whose branch is closed by an elif",
     ((groq_entry("beta-groq", "beta") + "\n" + groq_entry("gamma-groq", "gamma"),
       "{% if Artificial_Intelligence_LiteLLM_Groq_API_key %}\n" + groq_entry("beta-groq", "beta") + "{% elif Artificial_Intelligence_LiteLLM_Mistral_API_key %}\n"
       + groq_entry("gamma-groq", "gamma") + "{% endif %}\n"),),
     [("groq", "vendor/beta", "retired")], [],
     {("groq", "vendor/beta"): "unlocated"}),
    ("an entry that ends a block when the next entry opens another is deleted without either: the "
     "next one keeps its own condition",
     ((groq_entry("solo-groq", "solo") + "\n" + groq_entry("shared-one", "shared"),
       "{% if Artificial_Intelligence_LiteLLM_Groq_API_key %}\n" + groq_entry("solo-groq", "solo") + "{% endif %}\n\n"
       "{% if Artificial_Intelligence_LiteLLM_Mistral_API_key %}\n" + groq_entry("shared-one", "shared") + "{% endif %}\n"),),
     [("groq", "vendor/solo", "retired")],
     [(groq_entry("solo-groq", "solo"), ""),
      ("        - solo-groq\n        - shared-two\n", "        - shared-two\n")],
     {}),
    ("two entries of one id around an entry that stays are deleted, and the block around that one "
     "is left as it was",
     ((groq_entry("shared-one", "shared") + "\n" + groq_entry("shared-two", "shared") + "\n"
       + groq_entry("aliased-groq", "aliased"),
       groq_entry("shared-one", "shared") + "{% if Artificial_Intelligence_LiteLLM_Groq_API_key %}\n"
       + groq_entry("aliased-groq", "aliased") + "\n"
       + groq_entry("shared-two", "shared") + "{% endif %}\n"),),
     [("groq", "vendor/shared", "retired")],
     [(groq_entry("shared-one", "shared"), ""),
      (groq_entry("shared-two", "shared"), ""),
      ("        - free-a\n        - shared-one\n", "        - free-a\n"),
      ("        - solo-groq\n        - shared-two\n", "        - solo-groq\n")],
     {}),
    ("nor one followed by a Jinja statement that opens no block: nothing here knows what it set",
     ((groq_entry("solo-groq", "solo"),
       groq_entry("solo-groq", "solo") + "{% set account = 'main' %}\n"),),
     [("groq", "vendor/solo", "retired")], [],
     {("groq", "vendor/solo"): "verification"}),
    ("a block the deletion does not touch stays as it is, a loop with an else included",
     ((groq_entry("shared-one", "shared"),
       "{% if Artificial_Intelligence_LiteLLM_Groq_API_key %}\n" + groq_entry("shared-one", "shared") + "{% endif %}\n"),
      (groq_entry("shared-two", "shared"),
       "{% for account in ['main'] %}\n" + groq_entry("shared-two", "shared")
       + "{% else %}\n{% endfor %}\n")),
     [("groq", "vendor/alpha", "retired")],
     [(groq_entry("alpha-groq", "alpha"), ""),
      ("    - router:\n        - alpha-groq\n        - beta-groq\n",
       "    - router:\n        - beta-groq\n"),
      ("        - free-b\n        - alpha-groq\n", "        - free-b\n"),
      ("    - free-a\n    - alpha-groq\n", "    - free-a\n")],
     {}),
    ("a file whose Jinja blocks do not pair up is not edited at all: an endif with no if",
     (("model_list:\n", "model_list:\n{% endif %}\n"),),
     [("groq", "vendor/solo", "retired")], [],
     {("groq", "vendor/solo"): "unlocated"}),
    ("an if that is never closed",
     (("model_list:\n", "model_list:\n{% if Artificial_Intelligence_LiteLLM_Groq_API_key %}\n"),),
     [("groq", "vendor/solo", "retired")], [],
     {("groq", "vendor/solo"): "unlocated"}),
    ("an else with no if or for to belong to",
     (("model_list:\n", "model_list:\n{% else %}\n"),),
     [("groq", "vendor/solo", "retired")], [],
     {("groq", "vendor/solo"): "unlocated"}),
    ("an else in a block that has none",
     (("model_list:\n", "model_list:\n{% with account = 1 %}\n{% else %}\n{% endwith %}\n"),),
     [("groq", "vendor/solo", "retired")], [],
     {("groq", "vendor/solo"): "unlocated"}),
    ("an elif in a loop",
     (("model_list:\n", "model_list:\n{% for account in ['main'] %}\n{% elif Artificial_Intelligence_LiteLLM_Mistral_API_key %}\n"
       "{% endfor %}\n"),),
     [("groq", "vendor/solo", "retired")], [],
     {("groq", "vendor/solo"): "unlocated"}),
    ("an if that is closed as a loop",
     (("model_list:\n", "model_list:\n{% if Artificial_Intelligence_LiteLLM_Groq_API_key %}\n{% endfor %}\n"),),
     [("groq", "vendor/solo", "retired")], [],
     {("groq", "vendor/solo"): "unlocated"}),
    ("a Jinja block that opens and closes inside the entry goes with it",
     (("      model: groq/vendor/solo\n      api_key: \"os.environ/GROQ_API_KEY_SELFTEST\"\n",
       "      model: groq/vendor/solo\n{% if Artificial_Intelligence_LiteLLM_Groq_API_key %}\n"
       "      api_key: \"os.environ/GROQ_API_KEY_SELFTEST\"\n{% endif %}\n"),),
     [("groq", "vendor/solo", "retired")],
     [("  - model_name: solo-groq\n    litellm_params:\n      model: groq/vendor/solo\n"
       "{% if Artificial_Intelligence_LiteLLM_Groq_API_key %}\n      api_key: \"os.environ/GROQ_API_KEY_SELFTEST\"\n{% endif %}\n\n", ""),
      ("        - solo-groq\n        - shared-two\n", "        - shared-two\n")],
     {}),
    ("a model named inside a Jinja statement is not deleted: the statement computes with its name",
     (("model_list:\n", "{% set head = {'x': 'solo-groq'} %}\nmodel_list:\n"),),
     [("groq", "vendor/solo", "retired")], [],
     {("groq", "vendor/solo"): "stray"}),
    ("nor one named inside a Jinja expression",
     (("model_list:\n", "# {{ 'solo-groq' }}\nmodel_list:\n"),),
     [("groq", "vendor/solo", "retired")], [],
     {("groq", "vendor/solo"): "stray"}),
    ("nor one followed by a Jinja statement that runs over two lines: half of it would stay",
     ((groq_entry("solo-groq", "solo"),
       groq_entry("solo-groq", "solo") + "{% set account =\n 'main' %}\n"),),
     [("groq", "vendor/solo", "retired")], [],
     {("groq", "vendor/solo"): "verification"}),
    ("a file whose block opens over two lines and closes on one is not edited at all",
     ((groq_entry("solo-groq", "solo"),
       "{% if\n Artificial_Intelligence_LiteLLM_Groq_API_key %}\n" + groq_entry("solo-groq", "solo") + "{% endif %}\n"),),
     [("groq", "vendor/solo", "retired")], [],
     {("groq", "vendor/solo"): "unlocated"}),
    ("a Jinja comment line after an entry is not the entry's, and stays",
     ((groq_entry("solo-groq", "solo"),
       groq_entry("solo-groq", "solo") + "{# the next entry is the shared one #}\n"),),
     [("groq", "vendor/solo", "retired")],
     [(groq_entry("solo-groq", "solo"), ""),
      ("        - solo-groq\n        - shared-two\n", "        - shared-two\n")],
     {}),
    ("a comment indented deeper than the dash, after the last key, is the entry's own",
     ((groq_entry("solo-groq", "solo"),
       groq_entry("solo-groq", "solo") + "      # rotated monthly\n"),),
     [("groq", "vendor/solo", "retired")],
     [(groq_entry("solo-groq", "solo") + "      # rotated monthly\n\n", ""),
      ("        - solo-groq\n        - shared-two\n", "        - shared-two\n")],
     {}),
    ("one at the dash's indentation is the next entry's, and stays",
     ((groq_entry("solo-groq", "solo"),
       groq_entry("solo-groq", "solo") + "  # describes the shared pair\n"),),
     [("groq", "vendor/solo", "retired")],
     [(groq_entry("solo-groq", "solo"), ""),
      ("        - solo-groq\n        - shared-two\n", "        - shared-two\n")],
     {}),
    ("a commented-out entry that goes on past a bare line is not deleted: the rest would be taken "
     "for prose",
     ((commented_entry("paid-c", "openrouter/vendor/paid-c", "OPENROUTER"),
       commented_entry("paid-c", "openrouter/vendor/paid-c", "OPENROUTER")
       + "  #\n  #   model_info:\n  #     id: c\n"),),
     [("openrouter", "vendor/paid-c", "gone")], [],
     {("openrouter", "vendor/paid-c"): "unlocated"}),
)


def edited(text, changes, purpose):
    """"text" with each (old, new) applied once, or None when an "old" is not there exactly once:
    a case that cannot be built is a broken case, not a passing one."""
    for old, new in changes:
        if text.count(old) != 1:
            print("selftest: BROKEN CASE (%s) -- %r is in the template %d times, expected 1"
                  % (purpose, old[:70], text.count(old)))
            return None
        text = text.replace(old, new, 1)
    return text


def is_subsequence(shorter, longer):
    remaining = iter(longer)
    return all(any(line == other for other in remaining) for line in shorter)


def run_apply_cases():
    failures = 0
    for purpose, setup, wanted, changes, refusals in APPLY_CASES:
        text = edited(APPLY_TEMPLATE, setup, purpose)
        expected = edited(text, changes, purpose) if text is not None else None
        if expected is None:
            failures += 1
            continue
        new_text, outcomes = apply_removals(text, wanted)
        got = {(o["provider"], o["id"]): o["reason"][0] for o in outcomes if o["status"] == "refused"}
        applied = sorted((o["provider"], o["id"]) for o in outcomes if o["status"] == "applied")
        should_apply = sorted({(p, i) for p, i, _ in wanted if (p, i) not in refusals})
        before_template, before = read_template(text)
        after_template, after = read_template(new_text)
        why = None
        if new_text != expected:
            why = "the result is not the expected text:\n%s" % "\n".join(difflib.unified_diff(
                expected.splitlines(), new_text.splitlines(), "expected", "got", lineterm="", n=1))
        elif got != refusals:
            why = "refusals %r, expected %r" % (got, refusals)
        elif applied != should_apply:
            why = "applied %r, expected %r" % (applied, should_apply)
        elif (after_template is None) != (before_template is None) or len(after) > len(before):
            why = "the result breaks a rule the original did not: %r" % after
        elif not is_subsequence(new_text.splitlines(), text.splitlines()):
            why = "the result holds a line the original did not"
        elif "\n\n\n" in new_text and "\n\n\n" not in text:
            why = "the result holds a double blank line the original did not"
        if why is None:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s) -- %s" % (purpose, why))
    return failures


# A template with a "head" table, as the real one has: two routers, four providers, a cascade that
# starts on one provider and puts another's models twice, and two models that answer whatever the keys.
HEAD_TEMPLATE = """\
{% set has = {
  'Gemini': Artificial_Intelligence_LiteLLM_Gemini_API_key is string and Artificial_Intelligence_LiteLLM_Gemini_API_key | length > 0,
  'Mistral': Artificial_Intelligence_LiteLLM_Mistral_API_key is string and Artificial_Intelligence_LiteLLM_Mistral_API_key | length > 0,
  'Groq': Artificial_Intelligence_LiteLLM_Groq_API_key is string and Artificial_Intelligence_LiteLLM_Groq_API_key | length > 0,
  'OpenRouter': Artificial_Intelligence_LiteLLM_OpenRouter_API_key is string and Artificial_Intelligence_LiteLLM_OpenRouter_API_key | length > 0
} %}
{% set head = {
  'router': 'gem-one' if has.Gemini else 'free-one' if has.OpenRouter else 'large' if has.Mistral else 'local-a',
  'lite': 'gem-lite' if has.Gemini else 'small' if has.Mistral else false
} %}
model_list:
{% if has.Gemini %}
  - model_name: gem-one
    litellm_params:
      model: gemini/gemini-9-one
      api_key: "os.environ/GEMINI_API_KEY_SELFTEST"

  - model_name: gem-lite
    litellm_params:
      model: gemini/gemini-9-lite
      api_key: "os.environ/GEMINI_API_KEY_SELFTEST"

{% endif %}
{% if has.OpenRouter %}
  - model_name: free-one
    litellm_params:
      model: openrouter/vendor/one:free
      api_key: "os.environ/OPENROUTER_API_KEY_SELFTEST"

  - model_name: free-two
    litellm_params:
      model: openrouter/vendor/two:free
      api_key: "os.environ/OPENROUTER_API_KEY_SELFTEST"

{% endif %}
{% if has.Mistral %}
  - model_name: large
    litellm_params:
      model: mistral/vendor/large
      api_key: "os.environ/MISTRAL_API_KEY_SELFTEST"

  - model_name: small
    litellm_params:
      model: mistral/vendor/small
      api_key: "os.environ/MISTRAL_API_KEY_SELFTEST"

{% endif %}
  - model_name: local-a
    litellm_params:
      model: groq/vendor/local-a
      api_key: "os.environ/GROQ_API_KEY_SELFTEST"

  - model_name: local-b
    litellm_params:
      model: openai/auto/local-b
      api_base: "http://stand-in.invalid/v1"
      api_key: "stand-in"

router_settings:
  fallbacks:
{% if head['router'] %}
    - router:
{% if has.Gemini %}
        - gem-one
{% endif %}
{% if has.OpenRouter %}
        - free-one
{% endif %}
{% if has.Mistral %}
        - large
{% endif %}
{% if has.OpenRouter %}
        - free-two
{% endif %}
        - local-a
        - local-b
{% endif %}
{% if head['lite'] %}
    - lite:
{% if has.Gemini %}
        - gem-lite
{% endif %}
{% if has.Mistral %}
        - small
{% endif %}
{% endif %}
  model_group_alias:
{% if head['router'] %}
    "router": "{{ head['router'] }}"
{% endif %}
{% if head['lite'] %}
    "lite": "{{ head['lite'] }}"
{% endif %}
"""

HEAD_ROW_ROUTER = ("  'router': 'gem-one' if has.Gemini else 'free-one' if has.OpenRouter else "
                   "'large' if has.Mistral else 'local-a',\n")


def head_entry(name, model, key):
    return ('  - model_name: %s\n    litellm_params:\n      model: %s\n      api_key: "os.environ/%s_API_KEY_SELFTEST"\n\n'
            % (name, model, key))


def head_row(*terms, default="local-a"):
    chain = "".join("'%s' if has.%s else " % term for term in terms)
    return "  'router': %s%s,\n" % (chain, "'%s'" % default if default else "false")


FREE_ONE = head_entry("free-one", "openrouter/vendor/one:free", "OPENROUTER")
FREE_TWO = head_entry("free-two", "openrouter/vendor/two:free", "OPENROUTER")
LARGE = head_entry("large", "mistral/vendor/large", "MISTRAL")
LOCAL_A = ('  - model_name: local-a\n    litellm_params:\n      model: groq/vendor/local-a\n'
           '      api_key: "os.environ/GROQ_API_KEY_SELFTEST"\n\n')

# (what the case proves, a change made to HEAD_TEMPLATE first, the (provider, id, kind) deletions
# asked for, the changes the result must show against the changed template, and the refusals
# expected as {(provider, id): code}).
HEAD_CASES = (
    ("a model no row of the table names goes as it would anywhere, and the table is left as it is",
     (), [("openrouter", "vendor/two:free", "retired")],
     [(FREE_TWO, ""), ("{% if has.OpenRouter %}\n        - free-two\n{% endif %}\n",
                       "{% if has.OpenRouter %}\n{% endif %}\n")], {}),
    ("the first model of a provider goes, and the provider falls behind another in the row, the "
     "cascade having its next model after theirs",
     (), [("openrouter", "vendor/one:free", "retired")],
     [(FREE_ONE, ""), ("        - free-one\n", ""),
      (HEAD_ROW_ROUTER, head_row(("gem-one", "Gemini"), ("large", "Mistral"), ("free-two", "OpenRouter")))],
     {}),
    ("a provider with no other model in the cascade leaves the row",
     (), [("mistral", "vendor/large", "retired")],
     [(LARGE, ""), ("        - large\n", ""),
      (HEAD_ROW_ROUTER, head_row(("gem-one", "Gemini"), ("free-one", "OpenRouter")))],
     {}),
    ("the model that answers whatever the keys goes, and the next one takes its place at the end of "
     "the row",
     (), [("groq", "vendor/local-a", "retired")],
     [(LOCAL_A, ""), ("        - local-a\n", ""),
      (HEAD_ROW_ROUTER, head_row(("gem-one", "Gemini"), ("free-one", "OpenRouter"), ("large", "Mistral"),
                                 default="local-b"))],
     {}),
    ("two deletions together write the row once, from what both leave",
     (), [("openrouter", "vendor/one:free", "retired"), ("mistral", "vendor/large", "retired")],
     [(FREE_ONE, ""), ("        - free-one\n", ""), (LARGE, ""), ("        - large\n", ""),
      (HEAD_ROW_ROUTER, head_row(("gem-one", "Gemini"), ("free-two", "OpenRouter")))],
     {}),
    ("a name the table shares with another Jinja statement is still out of reach",
     (("model_list:\n", "{% set pinned = 'free-one' %}\nmodel_list:\n"),),
     [("openrouter", "vendor/one:free", "retired")], [],
     {("openrouter", "vendor/one:free"): "stray"}),
    ("a row that is not what its cascade gives is not trusted, so its models stay out of reach",
     ((HEAD_ROW_ROUTER, head_row(("gem-one", "Gemini"), ("large", "Mistral"), ("free-one", "OpenRouter"))),),
     [("openrouter", "vendor/one:free", "retired")], [],
     {("openrouter", "vendor/one:free"): "stray"}),
    ("a table with a row this tool cannot read is not touched at all",
     (("  'lite': 'gem-lite' if has.Gemini else 'small' if has.Mistral else false\n",
       "  'lite': ('gem-lite' if has.Gemini else false)\n"),),
     [("openrouter", "vendor/one:free", "retired")], [],
     {("openrouter", "vendor/one:free"): "stray"}),
)


def run_head_cases():
    failures = 0
    for purpose, setup, wanted, changes, refusals in HEAD_CASES:
        text = edited(HEAD_TEMPLATE, setup, purpose)
        expected = edited(text, changes, purpose) if text is not None else None
        if expected is None:
            failures += 1
            continue
        new_text, outcomes = apply_removals(text, wanted)
        got = {(o["provider"], o["id"]): o["reason"][0] for o in outcomes if o["status"] == "refused"}
        why = None
        if new_text != expected:
            why = "the result is not the expected text:\n%s" % "\n".join(difflib.unified_diff(
                expected.splitlines(), new_text.splitlines(), "expected", "got", lineterm="", n=1))
        elif got != refusals:
            why = "refusals %r, expected %r" % (got, refusals)
        elif not refusals:
            before, after = changed_heads(text, new_text), None
            for given, document in keyset_documents(new_text):
                if not isinstance(document, dict):
                    why = "the result does not render when only %s given" % given_text(given)
                elif alias_drift(document):
                    why = "an alias is off its cascade's first member when only %s given" % given_text(given)
                if why:
                    break
        if why is None:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s) -- %s" % (purpose, why))

    # A row that is not written again leaves an alias on a model that is gone: the result is read back
    # against the cascades, and the deletion is refused, not made.
    purpose = "a deletion whose row is not written again is refused, for the alias it leaves behind"
    real = rewrite_heads
    try:
        globals()["rewrite_heads"] = lambda text, trusted: (text, [])
        new_text, outcomes = apply_removals(HEAD_TEMPLATE, [("openrouter", "vendor/one:free", "retired")])
    finally:
        globals()["rewrite_heads"] = real
    reason = outcomes[0]["reason"] or ("", "")
    if (new_text == HEAD_TEMPLATE and outcomes[0]["status"] == "refused" and reason[0] == "verification"
            and "the alias router points at free-one" in reason[1]):
        print("selftest: ok -- %s" % purpose)
    else:
        failures += 1
        print("selftest: FAILED (%s) -- got %r" % (purpose, (outcomes[0]["status"], reason)))

    # What the pull request and the commit say about the rows.
    purpose = "the pull request lists the rows written again, and says it will not merge itself"
    heads = changed_heads(HEAD_TEMPLATE, apply_removals(
        HEAD_TEMPLATE, [("openrouter", "vendor/one:free", "retired")])[0])
    result = {"date": "2026-01-01", "removals": {"heads": heads}, "providers": [{
        "name": "openrouter", "status": "read", "findings": [{
            "kind": "retired", "id": "vendor/one:free", "removal": {
                "status": "applied", "entries": [{"name": "free-one", "state": "active"}],
                "slots": [], "prose": [], "review": []}}]}]}
    body, message = render_pr_body(result), " ".join(render_commit_message(result).split())
    if (len(heads) == 1 and heads[0][0] == "router" and "## Table `head` réécrite" in body
            and "ne se fusionne pas seule" in body and "-  'router': " in body and "+  'router': " in body
            and "The head table of the template repeats the order of the cascades" in message):
        print("selftest: ok -- %s" % purpose)
    else:
        failures += 1
        print("selftest: FAILED (%s) -- heads %r" % (purpose, heads))
    return failures


# The ranking source, played on canned answers in the shape its API reference documents (no key of
# Artificial Analysis was available: the shape is the documented one, not a recorded answer).
RANKING_TEMPLATE = """\
model_list:
  - model_name: gem-top
    litellm_params:
      model: gemini/gem-top-model
      api_key: "os.environ/GEMINI_API_KEY_SELFTEST"

  - model_name: groq-mid
    litellm_params:
      model: groq/vendor/groq-mid-model
      api_key: "os.environ/GROQ_API_KEY_SELFTEST"

  - model_name: free-low
    litellm_params:
      model: openrouter/vendor/free-low-model:free
      api_key: "os.environ/OPENROUTER_API_KEY_SELFTEST"

router_settings:
  fallbacks:
    - flash:
        - gem-top
        - groq-mid
        - free-low
    - code:
        - gem-top
        - groq-mid
    - flash-lite:
        - free-low
        - groq-mid
    - pro:
        - free-low
  model_group_alias:
    "flash": "gem-top"
    "code": "gem-top"
    "flash-lite": "free-low"
    "pro": "free-low"
"""


def ranking_model(slug, name, intelligence=None, coding=None, speed=None, price=None, creator="Vendor"):
    return {"id": "aa-" + slug, "name": name, "slug": slug,
            "model_creator": {"id": "c-1", "name": creator, "slug": squash(creator)},
            "evaluations": {"artificial_analysis_intelligence_index": intelligence,
                            "artificial_analysis_coding_index": coding, "livecodebench": 0.5},
            "pricing": {"price_1m_blended_3_to_1": price, "price_1m_input_tokens": 1.0,
                        "price_1m_output_tokens": 2.0},
            "median_output_tokens_per_second": speed, "median_time_to_first_token_seconds": 1.2}


RANKING_KEYS = dict(SELFTEST_KEYS, MODEL_DRIFT_ARTIFICIAL_ANALYSIS_API_KEY="selftest-artificial-analysis-key-SECRET")


def ranking_answers(*aa_models, openrouter_extra=()):
    """Catalogues that list exactly what RANKING_TEMPLATE holds, plus the NEW OpenRouter models given
    as (id, label), and the ranking source's answer made of "aa_models"."""
    answers = answers_listing(RANKING_TEMPLATE)
    for identifier, label in openrouter_extra:
        model = openrouter_model(identifier)
        model["name"] = label
        answers["openrouter"]["data"].append(model)
    answers["rankings"] = {"status": 200, "prompt_options": {"parallel_queries": 1, "prompt_length": "medium"},
                           "data": list(aa_models)}
    return answers


def ranking_run(environment, answers):
    calls = []
    result = run_online(RANKING_TEMPLATE, environment, canned_opener(answers, calls), "2026-01-01")
    return result, calls, render_text(result, "selftest"), render_issue_body(result, "selftest")


def run_ranking_cases():
    failures = 0
    top = ranking_model("gem-top-model", "Gem Top Model", 70, 60, 100, 2.0)
    mid = ranking_model("groq-mid-model", "Groq Mid Model", 50, 45, 300, 0.5)
    low = ranking_model("free-low-model", "Free Low Model", 30, 20, 200, 0.0)
    fresh = ranking_model("fresh-model", "Fresh Model @bob <img src=x> | `x` ::error::", 55, 70, 250, 1.5)
    shiny = ranking_model("another-slug", "Shiny Name", 20, 10, 50, None)
    twins = [ranking_model("twin-model", "Twin One", 10), ranking_model("twin-model", "Twin Two", 20)]
    extra = [("vendor/fresh-model:free", "Vendor: Fresh Model (free)"),
             ("vendor/named-thing:free", "Vendor: Shiny Name (free)"),
             ("vendor/mystery-thing:free", "Vendor: Mystery"),
             ("vendor/twin-model:free", "Vendor: Twin")]
    base = ranking_answers(top, mid, low, fresh, shiny, *twins, openrouter_extra=extra)

    def judged(purpose, why):
        nonlocal failures
        if why is None:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s) -- %s" % (purpose, why))

    def first_wrong(*checks):
        return next((message for ok, message in checks if not ok), None)

    # No key: said, never called, and nothing else about the run changes.
    result, calls, report, body = ranking_run(SELFTEST_KEYS, base)
    judged("without its key the ranking source is not covered, never called, and the run is the same",
           first_wrong(
               (not any(url == RANKING_URL for url, _ in calls), "the ranking source was called without a key"),
               ("rankings    not covered (no key): MODEL_DRIFT_ARTIFICIAL_ANALYSIS_API_KEY is unset" in report,
                "the report does not say the key is missing"),
               ("| Artificial Analysis (classements) | non couvert (pas de clé : secret "
                "`MODEL_DRIFT_ARTIFICIAL_ANALYSIS_API_KEY`) |" in body, "the coverage table does not say it"),
               ("## Classement des nouveaux modèles" not in body, "a table was written without figures"),
               (result["ranked"] == [], "rows were built from a source that was not read"),
               (exit_status(result) == 1 and is_complete(result), "the exit status or the coverage moved")))

    # A key: the figures, the matching said to be a guess, the places, the source named.
    result, calls, report, body = ranking_run(RANKING_KEYS, base)
    sent = [headers for url, headers in calls if url == RANKING_URL]
    section = body.split("## Classement des nouveaux modèles")[1].split("\n## ")[0] if "## Classement des nouveaux modèles" in body else ""
    judged("with its key the NEW models get their figures, a guessed matching, a place per router and the source",
           first_wrong(
               (len(sent) == 1 and sent[0].get("x-api-key") == RANKING_KEYS["MODEL_DRIFT_ARTIFICIAL_ANALYSIS_API_KEY"],
                "the key was not sent once in x-api-key"),
               (not any("SECRET" in url for url, _ in calls), "a key was put in a URL"),
               ("<https://artificialanalysis.ai/>" in section and "Terms of Use" in section, "the source is not named"),
               ("| `openrouter/vendor/fresh-model:free` | Fresh Model" in section and "par l'identifiant : à vérifier" in section
                and "| 55.0 | 70.0 | 250.0 | 1.5 |" in section, "the matched row is wrong: %s" % section[:900]),
               ("par le nom : à vérifier" in section and "Shiny Name" in section, "the match by name is missing"),
               ("| `openrouter/vendor/mystery-thing:free` | inconnu de la source |" in section, "an unknown model is not said unknown"),
               ("| `openrouter/vendor/twin-model:free` | plusieurs entrées portent ce nom, aucune retenue |" in section,
                "an ambiguous model was matched"),
               ("`flash` : avant `groq-mid`" in section, "flash is not placed before groq-mid"),
               ("`code` : avant `gem-top`" in section, "code is not placed before gem-top"),
               ("`flash-lite` : avant `free-low`" in section, "flash-lite is not placed before free-low"),
               ("jamais une décision" in section, "the table does not say it is not a decision"),
               (exit_status(result) == 1 and is_complete(result), "the exit status or the coverage moved"),
               ("rankings    read, 7 model(s), 2 of the 4 NEW model(s) matched" in report, "the report does not count: %s" % report)))
    judged("no key, no echoed key and no markup of the ranking source's text reaches the output",
           first_wrong(
               ("SECRET" not in report and "SECRET" not in body, "a key reached the output"),
               (hostile_lines(report, body) is None, str(hostile_lines(report, body))),
               ("@bob" not in body and "<img" not in body and "::error" not in body and "`x`" not in body,
                "the source's text carried markup into the issue")))

    # A model that ranks below every member goes last; a router with no ranked member gets no place.
    # It is as fast as the members (250 tokens/s against 100, 300 and 200), so speed leaves it eligible.
    low_answers = ranking_answers(top, mid, low, ranking_model("fresh-model", "Fresh Model", 5, 5, 250),
                                  openrouter_extra=[extra[0]])
    result, calls, report, body = ranking_run(RANKING_KEYS, low_answers)
    section = body.split("## Classement des nouveaux modèles")[1] if "## Classement des nouveaux modèles" in body else ""
    judged("a model below every ranked member goes after the last of them, and a router without a ranked member is left out",
           first_wrong(("`flash` : après `free-low`, le dernier classé" in section, "flash is not placed last: %s" % section[-600:]),
                       ("`claude-code` :" not in section, "claude-code has no cascade here and was placed")))

    # A member the ranking does not know is left out of the count, and the count is said.
    partial = ranking_answers(top, mid, fresh, openrouter_extra=[extra[0]])
    result, calls, report, body = ranking_run(RANKING_KEYS, partial)
    section = body.split("## Classement des nouveaux modèles")[1] if "## Classement des nouveaux modèles" in body else ""
    judged("a cascade member the ranking does not know is not counted among the ranked ones",
           first_wrong(("`flash` : avant `groq-mid` (indice d'intelligence : 50.0 contre 55.0 pour ce modèle), "
                        "2 membre(s) classé(s) sur 3" in section, "the count is wrong: %s" % section[-700:]),
                       ("`pro` :" not in section, "pro has no ranked member and was placed")))

    # Speed decides a model's eligibility for flash and flash-lite, on the speeds of the cascade's own
    # members (flash: 100, 300, 200; flash-lite: 200, 300). Shaped on the real run's figures -- a model
    # of high intelligence and 81.5 tokens/s proposed ahead of the fast ones, and 0.0 read as a speed --
    # since no recorded answer of the API was available.
    def place_block(body, identifier):
        section = body.split("Places suggérées, routeur par routeur :")[1] if "Places suggérées" in body else ""
        head = "- `%s`" % identifier
        return section.split(head, 1)[1].split("\n- `")[0].split("\n\n")[0] if head in section else ""

    def speed_run(members, *candidates):
        extras = [("vendor/%s:free" % model["slug"], "Vendor: %s (free)" % model["name"]) for model in candidates]
        result, calls, report, body = ranking_run(
            RANKING_KEYS, ranking_answers(*members, *candidates, openrouter_extra=extras))
        return {model["slug"]: place_block(body, "openrouter/vendor/%s:free" % model["slug"])
                for model in candidates}, body

    def row_of(body, slug):
        return next((line for line in body.splitlines() if line.startswith("| `openrouter/vendor/%s:free`" % slug)), "")

    slow = ranking_model("slow-model", "Slow Model", 90, 80, 50, 1.0)
    blocks, body = speed_run((top, mid, low), slow)
    block = blocks["slow-model"]
    judged("a model slower than the slowest member of flash and flash-lite gets no place there, and keeps its place in pro and code",
           first_wrong(
               ("`flash` : pas suggéré, plus lent que la liste (50.0 jetons par seconde contre 100.0 pour `gem-top`" in block,
                "flash does not refuse it: %s" % block),
               ("`flash-lite` : pas suggéré, plus lent que la liste (50.0 jetons par seconde contre 200.0 pour `free-low`" in block,
                "flash-lite does not refuse it: %s" % block),
               ("`flash` : avant" not in block and "`flash` : après" not in block
                and "`flash-lite` : avant" not in block and "`flash-lite` : après" not in block,
                "a slow model was placed in flash or flash-lite: %s" % block),
               ("`pro` : avant `free-low`" in block and "`code` : avant `gem-top`" in block,
                "pro or code lost its place to the speed rule: %s" % block),
               ("un modèle plus lent que le plus lent de ces membres n'a pas de place suggérée" in body
                and "« Gemini 4 Argon (High) »" in body,
                "the section does not say what is now filtered and what is still not judged")))

    edge_flash = ranking_model("edge-flash", "Edge Flash", 90, 80, 100, 1.0)
    edge_lite = ranking_model("edge-lite", "Edge Lite", 90, 80, 200, 1.0)
    blocks, body = speed_run((top, mid, low), edge_flash, edge_lite)
    judged("a model exactly as fast as the slowest member is eligible, one slower by a hair is not",
           first_wrong(
               ("`flash` : avant `gem-top`" in blocks["edge-flash"], "100 against 100 was refused in flash: %s" % blocks["edge-flash"]),
               ("`flash-lite` : pas suggéré" in blocks["edge-flash"], "100 against 200 was placed in flash-lite: %s" % blocks["edge-flash"]),
               ("`flash` : avant `gem-top`" in blocks["edge-lite"], "200 was refused in flash: %s" % blocks["edge-lite"]),
               ("`flash-lite` : après `groq-mid`, le dernier classé" in blocks["edge-lite"],
                "200 against 200 was refused in flash-lite: %s" % blocks["edge-lite"])))

    unknown = ranking_model("unknown-speed", "Unknown Speed", 90, 80, None, 1.0)
    zero = ranking_model("zero-speed", "Zero Speed", 91, 80, 0.0, 1.0)
    blocks, body = speed_run((top, mid, low), unknown, zero)
    judged("a model with no speed, or a speed of 0.0, is said not evaluated in flash and flash-lite, shown with a dash",
           first_wrong(
               *[(f"`{router}` : pas évalué : vitesse inconnue pour ce modèle" in blocks[slug],
                  "%s is not said unevaluated in %s: %s" % (slug, router, blocks[slug]))
                 for slug in ("unknown-speed", "zero-speed") for router in ("flash", "flash-lite")],
               ("| 91.0 | 80.0 | — | 1.0 |" in row_of(body, "zero-speed"), "0.0 was shown as a speed: %s" % row_of(body, "zero-speed")),
               ("`pro` : avant `free-low`" in blocks["zero-speed"], "pro lost its place: %s" % blocks["zero-speed"])))

    blind = (ranking_model("gem-top-model", "Gem Top Model", 70, 60, None, 2.0),
             ranking_model("groq-mid-model", "Groq Mid Model", 50, 45, 0.0, 0.5),
             ranking_model("free-low-model", "Free Low Model", 30, 20, None, 0.0))
    quick = ranking_model("quick-model", "Quick Model", 90, 80, 250, 1.0)
    blocks, body = speed_run(blind, quick)
    judged("a model is not evaluated when no member of the cascade has a usable speed, and pro and code are unaffected",
           first_wrong(
               *[(f"`{router}` : pas évalué : vitesse inconnue pour tous les membres de la liste" in blocks["quick-model"],
                  "%s does not say that no member has a speed: %s" % (router, blocks["quick-model"]))
                 for router in ("flash", "flash-lite")],
               ("`pro` : avant `free-low`" in blocks["quick-model"] and "`code` : avant `gem-top`" in blocks["quick-model"],
                "pro or code lost its place: %s" % blocks["quick-model"])))

    zeroed = ranking_model("free-low-model", "Free Low Model", 30, 20, 0.0, 0.0)
    blocks, body = speed_run((top, mid, zeroed), slow)
    judged("a member whose speed is 0.0 is not counted as the slowest, flash and flash-lite compare with the next one",
           first_wrong(
               ("`flash` : pas suggéré, plus lent que la liste (50.0 jetons par seconde contre 100.0 pour `gem-top`" in blocks["slow-model"],
                "flash compared with the wrong member: %s" % blocks["slow-model"]),
               ("`flash-lite` : pas suggéré, plus lent que la liste (50.0 jetons par seconde contre 300.0 pour `groq-mid`" in blocks["slow-model"],
                "flash-lite compared with the wrong member: %s" % blocks["slow-model"])))

    unscored = ranking_model("gem-top-model", "Gem Top Model", None, 60, 100, 2.0)
    medium = ranking_model("medium-model", "Medium Model", 90, 80, 150, 1.0)
    blocks, body = speed_run((unscored, mid, low), medium)
    judged("a member with a speed but no intelligence still sets the speed flash is held to",
           first_wrong(("`flash` : avant `groq-mid`" in blocks["medium-model"],
                        "the speed of a member the intelligence does not know was left out: %s" % blocks["medium-model"])))

    models = read_ranking_models({"data": [ranking_model("zero-model", "Zero Model", 1, None, 0.0),
                                           ranking_model("negative-model", "Negative Model", 1, None, -5),
                                           ranking_model("real-model", "Real Model", 1, None, 12.5)]})
    judged("a speed of zero or less is none, and a positive one is kept as published",
           first_wrong(([model["speed"] for model in models] == [None, None, 12.5],
                        "the speeds read are %r" % [model["speed"] for model in models])))

    # Errors: reported, scrubbed, and never an error of the run.
    for purpose, answer, wanted in (
            ("a 401 whose body echoes the key is reported as its status, the key is gone, and the run goes on",
             leaky_401("artificial-analysis"), "HTTP 401"),
            ("a network error whose reason carries the key is reported with the key scrubbed",
             urllib.error.URLError("tunnel refused for selftest-artificial-analysis-key-SECRET"),
             "network error: tunnel refused for ***"),
            ("an answer that is not JSON is reported",
             b"<html>maintenance</html>", "the answer is not JSON"),
            ("an answer without its data list is reported",
             {"status": 200, "data": "nope"}, 'the answer holds no "data" list')):
        answers = dict(base, rankings=answer)
        result, calls, report, body = ranking_run(RANKING_KEYS, answers)
        judged(purpose, first_wrong(
            (result["rankings"]["status"] == "error" and wanted in result["rankings"]["error"], "got %r" % (result["rankings"],)),
            ("rankings    ERROR, not read: " + wanted in report, "the report does not carry it"),
            ("## Classements non lus" in body and "Rien d'autre n'en dépend" in body, "the issue does not say it"),
            ("## Classement des nouveaux modèles" not in body, "a table was written without figures"),
            (result["ranked"] == [], "rows were built from a source that was not read"),
            ("SECRET" not in report and "SECRET" not in body, "a key reached the output"),
            (exit_status(result) == 1 and is_complete(result), "the error moved the exit status or the coverage")))

    # Many NEW models: the table and the places stay bounded, matched rows first, and the rest is said.
    crowd = [("vendor/crowd-%03d:free" % number, "Vendor: Crowd %03d (free)" % number) for number in range(80)]
    crowd_models = [ranking_model("crowd-%03d" % number, "Crowd %03d" % number, 40 + number % 20,
                                  30 + number % 20, 100 + number, 1.0)
                    for number in range(0, 80, 2)]
    result, calls, report, body = ranking_run(RANKING_KEYS, ranking_answers(
        top, mid, low, *crowd_models, openrouter_extra=crowd))
    section = body.split("## Classement des nouveaux modèles")[1].split("\n## ")[0] if "## Classement des nouveaux modèles" in body else ""
    judged("eighty NEW models stay within the section's bounds, matched first, and the rest is counted",
           first_wrong((section.count("\n| `openrouter/") == RANKING_LISTED, "the table holds %d rows" % section.count("\n| `openrouter/")),
                       ("inconnu de la source" not in section, "an unmatched row came before a matched one"),
                       ("… et 55 autre(s) nouveau(x) modèle(s) sans chiffres ici" in section, "the rest was not counted"),
                       (len(body) < 40000, "the body is %d characters long" % len(body))))

    # Figures that are not figures are none, and the matching takes the spelling it can trust.
    junk = ranking_model("fresh-model", "Fresh Model", "NaN", True, float("inf"), "1.5")
    result, calls, report, body = ranking_run(RANKING_KEYS, ranking_answers(
        top, mid, low, junk, openrouter_extra=[extra[0]]))
    judged("a string, a boolean or an infinite figure is none, shown as a dash and placed nowhere",
           first_wrong(("| — | — | — | — |" in body, "a figure that is none was shown"),
                       ("Places suggérées" not in body, "a model with no figure was placed")))
    models = read_ranking_models({"data": [ranking_model("o3", "o3", 1), ranking_model("some-model", "Some Model", 2)]})
    judged("a spelling shorter than four characters is no match, and a label's provider prefix and (free) are dropped",
           first_wrong((match_ranking("openrouter", "vendor/o3:free", "", models)[0] is None, "o3 was matched"),
                       (match_ranking("openrouter", "vendor/x:free", "Vendor: Some Model (free)", models)[1] == "nom",
                        "the label was not tried")))
    return failures


def run_safety_net_case():
    """The last check, on every deletion together, is reached only when a plan is wrong for several
    deletions at once and not for each alone. None of the cases above does that, so make one: a
    plan that, for two deletions or more, takes a line nobody asked for along."""
    purpose = "deletions that pass alone but not together are all refused, and nothing is written"
    real = plan_lines
    wanted = [("openrouter", "vendor/paid-b", "gone"), ("sambanova", "SN-A", "gone")]

    def careless(layout, keys):
        marks, notes, slot_names = real(layout, keys)
        if len(keys) > 1:
            later = next(entry for entry in layout["entries"] if entry["name"] == "later-groq")
            marks = set(marks) | set(range(later["start"], later["end"]))
        return marks, notes, slot_names

    why = None
    try:
        globals()["plan_lines"] = careless
        new_text, outcomes = apply_removals(APPLY_TEMPLATE, wanted)
    finally:
        globals()["plan_lines"] = real
    control_text, control = apply_removals(APPLY_TEMPLATE, wanted)
    if [o["status"] for o in control] != ["applied", "applied"] or control_text == APPLY_TEMPLATE:
        why = "the control run, with the real plan, did not delete both"
    elif new_text != APPLY_TEMPLATE:
        why = "the file was written although the whole did not verify"
    elif [o["status"] for o in outcomes] != ["refused", "refused"] or any(
            o["reason"][0] != "verification" or not o["reason"][1].startswith("taken together")
            for o in outcomes):
        why = "outcomes %r" % [(o["status"], o["reason"]) for o in outcomes]
    if why is None:
        print("selftest: ok -- %s" % purpose)
        return 0
    print("selftest: FAILED (%s) -- %s" % (purpose, why))
    return 1


# (what the case proves, how the original is changed to make the result, the text a verification
# problem must contain, or None when the result is fine). Each result is written by hand, as the
# mistake it names -- not by plan_lines -- because verify_removal exists for what plan_lines gets
# wrong.
VERIFY_CASES = (
    ("an exact deletion passes",
     [(groq_entry("solo-groq", "solo") + "\n", ""),
      ("        - solo-groq\n        - shared-two\n", "        - shared-two\n")],
     [("groq", "vendor/solo")], None),
    ("an entry deleted and its cascade slot left behind fails the offline rules",
     [(groq_entry("solo-groq", "solo") + "\n", "")],
     [("groq", "vendor/solo")], "the offline rules fail"),
    ("a reason deleted from under the entry still there fails the offline rules",
     [(PAID_REASON, ""),
      (commented_entry("paid-a", "openrouter/vendor/paid-a", "OPENROUTER") + "  #\n", "")],
     [("openrouter", "vendor/paid-a")], "the offline rules fail"),
    ("a deletion that takes an entry nobody asked for along is not the original minus the asked",
     [(groq_entry("solo-groq", "solo") + "\n", ""),
      ("        - solo-groq\n        - shared-two\n", "        - shared-two\n"),
      (groq_entry("later-groq", "later") + "\n", "")],
     [("groq", "vendor/solo")], "not the original without"),
    ("a commented-out entry taken along is noticed, since YAML cannot see a comment",
     [(groq_entry("solo-groq", "solo") + "\n", ""),
      ("        - solo-groq\n        - shared-two\n", "        - shared-two\n"),
      ("  #\n" + commented_entry("paid-c", "openrouter/vendor/paid-c", "OPENROUTER"), "")],
     [("groq", "vendor/solo")], "commented-out entries of the result"),
    ("a drift-ignore line taken along is noticed too",
     [(groq_entry("solo-groq", "solo") + "\n", ""),
      ("        - solo-groq\n        - shared-two\n", "        - shared-two\n"),
      (DRIFT_IGNORE_LINE, "")],
     [("groq", "vendor/solo")], '"drift-ignore:" lines'),
    ("half an entry deleted leaves a file that does not read",
     [("    litellm_params:\n      model: groq/vendor/solo\n", "      model: groq/vendor/solo\n")],
     [("groq", "vendor/solo")], "not readable"),
)


def run_verify_cases():
    failures = 0
    for purpose, changes, keys, needle in VERIFY_CASES:
        result = edited(APPLY_TEMPLATE, changes, purpose)
        if result is None:
            failures += 1
            continue
        problem = verify_removal(APPLY_TEMPLATE, set(keys), result)
        passed = problem is None if needle is None else bool(problem and needle in problem)
        if passed:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s) -- expected %s, got %r"
                  % (purpose, "no problem" if needle is None else repr(needle), problem))
    return failures


# (what the case proves, a change made to APPLY_TEMPLATE first, the (provider, id, kind) deletions
# asked for, and the places a person is sent to as (why, a piece of the text, how many lines, the
# name a "mention" is about), in the order of the new file). The line numbers are checked against
# the new file itself: the span has to hold the piece, and has to be that long.
REVIEW_CASES = (
    ("the prose above a deleted active entry is left, and pointed at",
     (), [("groq", "vendor/alpha", "retired")],
     [("left", "Prose about alpha", 1, None)]),
    ("the reason over a run some of which is gone stays over the rest, and is pointed at",
     (), [("openrouter", "vendor/paid-a", "gone")],
     [("kept", "Served, but not routed to: paid only.", 1, None)]),
    ("a section heading left over no entry is pointed at, and the reason that went with its run "
     "is not",
     (), [("openrouter", "vendor/%s" % name, "retired" if name.endswith(":free") else "gone")
          for name in ("a:free", "b:free", "paid-a", "paid-b", "paid-c")],
     [("banner", 'OpenRouter (":free" entries only)', 3, None)]),
    ("a comment naming a deleted model_name is pointed at, with the name, full stop or not",
     (("  - model_name: gamma-groq", "  # gamma is tried after beta-groq, and beta-groq. is cheap\n"
       "  - model_name: gamma-groq"),),
     [("groq", "vendor/beta", "retired")],
     [("mention", "gamma is tried after beta-groq", 1, "beta-groq")]),
    ("a longer name that merely starts the same is not a mention",
     (("  - model_name: gamma-groq", "  # beta-groq-two is another model, and so is xbeta-groq\n"
       "  - model_name: gamma-groq"),),
     [("groq", "vendor/beta", "retired")], []),
    ("an id that an entry which stays carries too is not a stale mention",
     (("\nrouter_settings:\n", "\n  - model_name: twin\n    litellm_params:\n"
       "      model: mistral/vendor/alpha\n"
       '      api_key: "os.environ/MISTRAL_API_KEY_SELFTEST"\n\nrouter_settings:\n'),
      ("  - model_name: gamma-groq", "  # vendor/alpha is served by both\n"
       "  - model_name: gamma-groq")),
     [("groq", "vendor/alpha", "retired")],
     [("left", "Prose about alpha", 1, None)]),
    ("a mention inside a place already pointed at is not listed a second time",
     (("  # Served, but not routed to: paid only.\n",
       "  # Served, but not routed to: paid only (paid-a is the dearest).\n"),),
     [("openrouter", "vendor/paid-a", "gone")],
     [("kept", "Served, but not routed to: paid only (paid-a", 1, None)]),
    ("a name followed by a colon that ends a clause is a mention",
     (("  - model_name: gamma-groq", "  # after beta-groq: gamma-groq.\n"
       "  - model_name: gamma-groq"),),
     [("groq", "vendor/beta", "retired")],
     [("mention", "after beta-groq: gamma-groq", 1, "beta-groq")]),
    ("a name followed by a colon and a suffix is another name, and not a mention",
     (("  - model_name: gamma-groq", "  # beta-groq:free is another model.\n"
       "  - model_name: gamma-groq"),),
     [("groq", "vendor/beta", "retired")], []),
    ("a comment naming a deleted bare id is pointed at",
     (("  - model_name: gamma-groq", "  # vendor/beta is the cheap one\n"
       "  - model_name: gamma-groq"),),
     [("groq", "vendor/beta", "retired")],
     [("mention", "vendor/beta is the cheap one", 1, "vendor/beta")]),
    ("a comment naming it by its provider-qualified id is pointed at",
     (("  - model_name: gamma-groq", "  # groq/vendor/beta is the cheap one\n"
       "  - model_name: gamma-groq"),),
     [("groq", "vendor/beta", "retired")],
     [("mention", "groq/vendor/beta is the cheap one", 1, "groq/vendor/beta")]),
    ("the prose above the statement that wraps an entry is about that entry, and is pointed at",
     ((groq_entry("beta-groq", "beta"),
       "  # Prose about beta, written above its condition\n{% if Artificial_Intelligence_LiteLLM_Groq_API_key %}\n"
       + groq_entry("beta-groq", "beta") + "{% endif %}\n"),),
     [("groq", "vendor/beta", "retired")],
     [("left", "Prose about beta, written above its condition", 1, None)]),
    ("a deletion no comment is about points nowhere",
     (), [("groq", "vendor/solo", "retired")], []),
)


KEYSET_TEMPLATE = """\
model_list:
{% if Artificial_Intelligence_LiteLLM_Groq_API_key is string and Artificial_Intelligence_LiteLLM_Groq_API_key | length > 0 %}
  - model_name: only-groq
    litellm_params:
      model: groq/vendor/one
      api_key: "os.environ/GROQ_API_KEY_SELFTEST"
{% endif %}
{% if Artificial_Intelligence_LiteLLM_Mistral_API_key is string and Artificial_Intelligence_LiteLLM_Mistral_API_key | length > 0 %}
  - model_name: only-mistral
    litellm_params:
      model: mistral/vendor/two
      api_key: "os.environ/MISTRAL_API_KEY_SELFTEST"

  - model_name: unrouted-mistral
    litellm_params:
      model: mistral/vendor/three
      api_key: "os.environ/MISTRAL_API_KEY_SELFTEST"
{% endif %}
  - model_name: always
    litellm_params:
      model: openai/auto/always
      api_base: "http://stand-in.invalid/v1"
      api_key: "stand-in"

router_settings:
  fallbacks:
    - always:
{% if Artificial_Intelligence_LiteLLM_Groq_API_key is string and Artificial_Intelligence_LiteLLM_Groq_API_key | length > 0 %}
        - only-groq
{% endif %}
{% if Artificial_Intelligence_LiteLLM_Mistral_API_key is string and Artificial_Intelligence_LiteLLM_Mistral_API_key | length > 0 %}
        - only-mistral
{% endif %}
    - only-groq-or-mistral-first:
        - always
"""

KEYSET_CASES = (
    ("a model that is the only member of a cascade for some set of keys is not deleted, though "
     "another set of keys leaves the cascade a member",
     [("groq", "vendor/one", "retired")], "emptied"),
    ("and one that no cascade names goes",
     [("mistral", "vendor/three", "retired")], None),
)


def run_keyset_cases():
    """A cascade is judged for every set of provider keys, not on the union: the one that holds a
    provider's members alone is empty for each set that leaves the provider out."""
    failures = 0
    # The cascade above lists only-groq and only-mistral after "always", so "always" keeps it
    # non-empty for every set; the cases below use the template with "always" taken out of it.
    text = KEYSET_TEMPLATE.replace("    - always:\n", "    - only-groq-or-mistral:\n", 1).replace(
        "    - only-groq-or-mistral-first:\n        - always\n", "", 1)
    for purpose, wanted, expected in KEYSET_CASES:
        new_text, outcomes = apply_removals(text, wanted)
        got = outcomes[0]["reason"][0] if outcomes[0]["status"] == "refused" else None
        why = None
        if got != expected:
            why = "refused as %r, expected %r (%r)" % (got, expected, outcomes[0]["reason"])
        elif expected is None and not (new_text != text and "unrouted-mistral" not in new_text):
            why = "the entry that no cascade names was not deleted"
        if why is None:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s) -- %s" % (purpose, why))
    # The reading behind that rule, called on its own: a result that is the same file with all five
    # keys given and another for the set that gives one provider alone is refused.
    good, _ = apply_removals(text, [("mistral", "vendor/three", "retired")])
    guard = "{% if @@ is string and @@ | length > 0 %}\n        - only-mistral\n"

    def guarded(provider):
        return guard.replace("@@", "Artificial_Intelligence_LiteLLM_%s_API_key" % provider)

    entry_guard = "{% if @@ is string and @@ | length > 0 %}\n  - model_name: only-mistral\n"

    def entry_guarded(provider):
        return entry_guard.replace("@@", "Artificial_Intelligence_LiteLLM_%s_API_key" % provider)

    for purpose, bad, wanted in (
            ("a result whose cascade differs for one set of keys only is refused",
             good.replace(guarded("Mistral"), guarded("Groq")), "only Mistral given"),
            ("and so is one whose model list does",
             good.replace(entry_guarded("Mistral"), entry_guarded("Groq")), "only Mistral given")):
        problem = verify_removal(text, {("mistral", "vendor/three")}, bad)
        if bad == good or not problem or wanted not in problem:
            failures += 1
            print("selftest: FAILED (%s) -- %r" % (purpose, problem))
        else:
            print("selftest: ok -- %s" % purpose)
    return failures


def run_jinja_net_cases():
    """The net behind the block rule, called on its own: the cases above never reach it, since a
    statement that wraps an entry is trimmed off it before the net is asked."""
    failures = 0
    text = edited(APPLY_TEMPLATE, ((groq_entry("solo-groq", "solo"), "{% if Artificial_Intelligence_LiteLLM_Groq_API_key %}\n"
                                    + groq_entry("solo-groq", "solo") + "{% endif %}\n"),),
                  "the Jinja net")
    template, _ = read_template(text) if text else (None, None)
    layout = read_layout(text, template)[0] if template else None
    if layout is None:
        print("selftest: FAILED (the Jinja net cases could not be built)")
        return 1
    lines = layout["lines"]
    opener = next(number for number, line in enumerate(lines) if line.startswith("{% if "))
    closer = next(number for number, line in enumerate(lines) if line.startswith("{% endif %}"))
    body = set(range(opener, closer + 1))
    for purpose, marks, refused in (
            ("the end of a block taken without its start is refused", {closer}, True),
            ("the two ends of a block taken without what they enclose are refused",
             {opener, closer}, True),
            ("a block taken whole, with what is between its ends, is not", body, False)):
        got = jinja_refusal(layout, marks)
        if (got is not None) != refused:
            failures += 1
            print("selftest: FAILED (%s) -- got %r" % (purpose, got))
        else:
            print("selftest: ok -- %s" % purpose)
    return failures


def run_review_cases():
    failures = 0
    for purpose, setup, wanted, expected in REVIEW_CASES:
        text = edited(APPLY_TEMPLATE, setup, purpose)
        if text is None:
            failures += 1
            continue
        new_text, outcomes = apply_removals(text, wanted)
        lines = new_text.splitlines()
        got = sorted((item["line"], item["last"], item["why"], item["subject"], item["first"])
                     for outcome in outcomes for item in outcome["review"])
        why = None
        if any(outcome["status"] != "applied" for outcome in outcomes):
            why = "refused: %r" % [(o["reason"]) for o in outcomes if o["status"] != "applied"]
        elif len(got) != len(expected):
            why = "pointed at %r, expected %d place(s)" % (got, len(expected))
        else:
            for (line, last, kind, subject, first), (want, piece, count, name) in zip(got, expected):
                if (kind != want or subject != name or last - line + 1 != count
                        or piece not in "\n".join(lines[line - 1:last]) or piece not in first
                        or not 1 <= line <= last <= len(lines)):
                    why = "pointed at %r, expected (%s, %r, %d lines, %r)" % (
                        (line, last, kind, subject, first), want, piece, count, name)
                    break
        if why is None:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s) -- %s" % (purpose, why))
    return failures


def redirect_case():
    """(whether the redirect was refused, whether the stock opener follows it, the requests the
    refusing one made) against a server of this machine's own that redirects "/start"."""
    seen = []

    class Redirecting(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            if self.path == "/start":
                self.send_response(302)
                self.send_header("Location", "/elsewhere")
                self.end_headers()
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

        def log_message(self, *arguments):
            pass

    server = http.server.HTTPServer(("localhost", 0), Redirecting)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = "http://localhost:%d/start" % server.server_address[1]
    try:
        try:
            fetch_json(urllib_opener, url, {"Authorization": "Bearer selftest"})
            refused = None
        except FetchError as error:
            refused = str(error)
        requests = list(seen)
        del seen[:]
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            followed = seen == ["/start", "/elsewhere"] and response.read() == b"{}"
    finally:
        server.shutdown()
        server.server_close()
    return refused, followed, requests


def crash_through_main():
    """(the exit status, what was written to stderr) of this very file run as a script, over a
    config that reads, when the first request of the run raises an error whose message is a piece
    of an answer: the status must be a crash's, and the message must not be written anywhere."""
    with tempfile.TemporaryDirectory() as directory:
        config = os.path.join(directory, "config.yaml.j2")
        Path(config).write_text(SELFTEST_TEMPLATE, encoding="utf-8")
        real, saved = urllib.request.build_opener, sys.argv

        def failing(*handlers):
            raise RuntimeError("::error::a piece of an answer")

        err, out = io.StringIO(), io.StringIO()
        urllib.request.build_opener = failing
        sys.argv = [saved[0], "--online", "--config", config]
        try:
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
                try:
                    runpy.run_path(__file__, run_name="__main__")
                    status = None
                except SystemExit as exit:
                    status = exit.code
        finally:
            urllib.request.build_opener, sys.argv = real, saved
    return status, err.getvalue() + out.getvalue()


def run_hardening_cases():
    """What guards the run against its own inputs, and against its own mistakes."""
    failures = 0

    refused, followed, requests = redirect_case()
    cases = [
        ("a redirect is refused, reported as the status it is, and never followed",
         refused == "HTTP 302" and requests == ["/start"]),
        ("the stock opener does follow one, which is what the refusal is for", followed),
    ]

    def broken_reader(pages):
        return {}["no such key"]

    try:
        read_catalogue(lambda url, headers: b"{}", "https://selftest.invalid/", {}, broken_reader,
                       None)
        net = "no error"
    except FetchError as error:
        net = str(error)
    cases.append(("a reader that meets a shape nobody thought of reports that provider's error",
                  net == "the answer has a shape this check does not read"))

    def boom(argv):
        raise RuntimeError("::error::a piece of an answer")

    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        status = guarded(boom)
    cases.append(("a crash has a status of its own and says what kind and where, never its message",
                  status == CRASH_STATUS == 70 and "RuntimeError in boom" in err.getvalue()
                  and "a piece of an answer" not in err.getvalue()))
    try:
        guarded(lambda argv: sys.exit(2))
        exited = None
    except SystemExit as exit:
        exited = exit.code
    cases.append(("a status returned, or an exit asked for, goes through the guard untouched",
                  guarded(lambda argv: 1) == 1 and exited == 2))

    saved = {name: os.environ.get(name)
             for name in ("REMOVALS_BRANCH", "GITHUB_SERVER_URL", "GITHUB_REPOSITORY")}
    os.environ.update(REMOVALS_BRANCH="claude/selftest-branch",
                      GITHUB_SERVER_URL="https://selftest.invalid", GITHUB_REPOSITORY="owner/repo")
    try:
        answers = selftest_answers()
        answers["groq"] = {"data": [{"id": "whisper-large-v9", "active": True}]}
        issue = apply_run(SELFTEST_TEMPLATE, answers)[3]
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    cases.append(("the issue names the branch of the deletions, and links the pull request found by it",
                  "sur la branche `claude/selftest-branch`" in issue
                  and "(https://selftest.invalid/owner/repo/pulls?q=is%3Apr+is%3Aopen+head%3A"
                      "claude%2Fselftest-branch)" in issue))

    status, written = crash_through_main()
    cases.append(("run as a script, a crash exits 70, not 1, and writes none of the message",
                  status == CRASH_STATUS and "a piece of an answer" not in written
                  and "crashed, RuntimeError" in written))

    cases.append(("an id naming a use other than chat is never a new candidate, and a chat model is",
                  not any(chat_like(identifier) for identifier in (
                      "voxtral-small-latest", "gemini-nano-banana-2.1", "gemini-robotics-er-2-preview",
                      "deep-research-max-preview-04-2026", "gemini-2.5-computer-use-preview-10-2025",
                      "antigravity-preview-latest", "WHISPER-large-v9"))
                  and all(chat_like(identifier) for identifier in (
                      "mistral-large-4", "gemini-4-argon", "MiniMax-M3.1-Flash", "gemini-pro-latest",
                      "allam-2-7b", "labs-leanstral-1-5"))))
    cases.append(("a price too big for a float is not zero, and not a crash",
                  is_zero(10 ** 400) is False and is_zero("0") and not is_zero("free")))
    cases.append(("a code span is cut between two words, and says so",
                  code_span("word " * 40) == "`" + "word " * 19 + "word…`"
                  and code_span("short") == "`short`"
                  and code_span("x" * 150) == "`" + "x" * 100 + "…`"))

    balance = jinja_balance("{% if a %}{% for x in y %}{% else %}{% endfor %}{# {% if b %} #}"
                            "{% set z = 1 %}{% set w %}{% endset %}{% endif %}{% if c %}")
    cases.append(("Jinja blocks are counted per statement, comments and one-line sets aside",
                  balance == {"if": 1}))

    result = {"date": "2026-01-01", "providers": [], "removals": {}}
    for index in range(30):
        result["providers"].append({"name": "groq", "findings": [{
            "kind": "retired", "id": "vendor/a-very-long-identifier-number-%d" % index,
            "removal": {"status": "applied"}}]})
    message = render_commit_message(result)
    cases.append(("the commit message is wrapped, counts the ids by provider and lists none",
                  max(len(line) for line in message.splitlines()) <= 100
                  and "found 30 ids it no longer lists, from Groq (30)." in " ".join(message.split())
                  and "a-very-long-identifier" not in message
                  and message.splitlines()[0].endswith("(#243)")
                  and message.endswith("choices.\n")))

    for purpose, passed in cases:
        if passed:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s)" % purpose)
    return failures


def apply_run(text, answers, environment=None):
    """One whole online run with --apply, on canned catalogues: (result, new text, report, issue
    body, pull request body, commit message). The last two are None when nothing was deleted."""
    calls = []
    result = run_online(text, SELFTEST_KEYS if environment is None else environment,
                        canned_opener(answers, calls), "2026-01-01")
    new_text = apply_to_result(text, result)
    report = render_text(result, "selftest")
    issue = render_issue_body(result, "selftest", link=None)
    changed = result["removals"]["changed"]
    return (result, new_text, report, issue,
            render_pr_body(result) if changed else None,
            render_commit_message(result) if changed else None)


def hostile_lines(*texts):
    """The first line, if any, a workflow command could be read from at the head of: GitHub reads
    "::command::" after trimming the left of a log line, and any markup that makes a mention, a
    tag or a link from a catalogue's text is as unwelcome in an issue."""
    for text in texts:
        for line in (text or "").splitlines():
            if line.lstrip().startswith("::"):
                return "a line starts a workflow command: %r" % line
        for needle in ("@someone", "@bob", "<img", "::error", "::warning"):
            if needle in (text or ""):
                return "%r reached the output" % needle
        # A link is inert inside a code span, which is where a name from a catalogue is shown.
        outside = re.sub(r"`[^`]*`", "", text or "")
        for needle in ("](http", "www.evil", "http://evil"):
            if needle in outside:
                return "%r reached the output, outside a code span" % needle
    return None


def openrouter_with_notice(base):
    """The OpenRouter answer with one active id about to expire, a commented-out id free again under
    its ":free" twin, and an id the file does not know."""
    data = [m for m in base["openrouter"]["data"] if m["id"] != "vendor/one:free"]
    return {"data": data + [openrouter_model("vendor/one:free", expiration="2026-12-01"),
                            openrouter_model("vendor/paid-one:free"),
                            openrouter_model("vendor/fresh:free")]}


def online_apply_cases():
    """(what the case proves, template, answers, a check on (result, new_text, report, issue, pr,
    commit) returning None when it holds and why not otherwise, the exit status expected)."""
    base = selftest_answers()

    def changed(**replaced):
        answers = selftest_answers()
        answers.update(replaced)
        return answers

    def lacking(provider, *identifiers):
        key = "data"
        data = [m for m in base[provider][key] if m.get("id") not in identifiers]
        return dict(base[provider], data=data)

    def deletes_fast(result, new_text, report, issue, pr, commit):
        if "groq/vendor/fast" in new_text or "model_name: fast\n" in new_text:
            return "the retired entry is still in the file"
        if undeleted_count(result) != 0:
            return "a model that was deleted is counted as left to a person"
        for name, needle in (("issue", "## Supprimés par la pull request"),
                             ("issue", "`groq/vendor/fast`"),
                             ("pr", "`groq/vendor/fast` chez Groq"),
                             ("pr", "<https://api.groq.com/openai/v1/models>, lu le 2026-01-01"),
                             ("pr", "ansible-ci.yml"),
                             ("commit", "found 1 id it no longer lists, from Groq (1)")):
            if needle not in " ".join({"issue": issue, "pr": pr, "commit": commit}[name].split()):
                return "the %s lacks %r" % (name, needle)
        if "## Retirés" in issue:
            return "a deletion the pull request makes is still listed as to do by hand"
        if commit.splitlines()[0] != ("Delete the models their provider has retired from the "
                                      "LiteLLM model list (#243)"):
            return "the commit subject is %r" % commit.splitlines()[0]
        return None

    def nothing_to_read(result, new_text, report, issue, pr, commit):
        # "dependabot-auto-merge.yml" lets the pull request merge itself only when its body has no
        # "À relire" section: this is the case where it has none.
        if "groq/vendor/fast" in new_text:
            return "the retired entry is still in the file"
        if pr is None or re.search(r"^## À relire\s*$", pr, re.MULTILINE):
            return "the pull request asks a person to read something although nothing is left over"
        return None

    def something_to_read(result, new_text, report, issue, pr, commit):
        # ... and the case where it has one, which has to be a person's to merge.
        if "groq/vendor/fast" in new_text:
            return "the retired entry is still in the file"
        if pr is None or not re.search(r"^## À relire\s*$", pr, re.MULTILINE):
            return "the prose left above a deleted entry is not listed under \"À relire\""
        return None

    def keeps_free_one(result, new_text, report, issue, pr, commit):
        if new_text != SELFTEST_TEMPLATE:
            return "the file changed although the only retired model is behind an alias"
        if undeleted_count(result) != 1:
            return "the model that was refused is not counted as left to a person"
        if pr is not None or commit is not None:
            return "a pull request body was written although nothing was deleted"
        for needle in ("## Retirés : à supprimer à la main", "non supprimé par le workflow",
                       "l'alias \"auto-hidden\" pointe vers lui", "`openrouter/vendor/one:free`"):
            if needle not in issue:
                return "the issue lacks %r" % needle
        if "NOT DELETED, left to a person: the alias" not in report:
            return "the report does not say the model was left alone"
        return None

    def empty_not_believed(result, new_text, report, issue, pr, commit):
        if new_text != SELFTEST_TEMPLATE:
            return "an empty catalogue was taken for everything retired"
        if "catalogue ne liste aucun modèle" not in issue:
            return "the issue does not say why"
        if undeleted_count(result) != 1:
            return "a commented-out model that was refused is not counted as left to a person"
        return None

    def error_deletes_nothing_else(result, new_text, report, issue, pr, commit):
        if "deepseek/deepseek-v9" not in new_text:
            return "the entry of the provider that could not be read was deleted"
        if "## Catalogues non lus" not in pr or "`deepseek`" not in pr.split("## Catalogues non lus")[1]:
            return "the pull request does not say which catalogue was not read"
        if "groq/vendor/fast" in new_text:
            return "what could be read was not deleted"
        return hostile_lines(report, issue, pr, commit) or (
            "a key or an echoed key reached the output"
            if any("SECRET" in (text or "") for text in (report, issue, pr, commit)) else None)

    def idempotent(result, new_text, report, issue, pr, commit):
        again, second, _, _, again_pr, _ = apply_run(new_text, changed(
            groq={"data": [{"id": "whisper-large-v9", "active": True}]}))
        if second != new_text or again_pr is not None:
            return "a second run deleted something more"
        if [f for r in again["providers"] for f in r["findings"] if f["kind"] == "retired"]:
            return "the second run still finds the model retired"
        return None

    def decisions_untouched(result, new_text, report, issue, pr, commit):
        kinds = sorted({f["kind"] for r in result["providers"] for f in r["findings"]})
        if kinds != ["back", "new", "notice"]:
            return "the findings are %r, expected an announced retirement, a BACK and a NEW" % kinds
        if new_text != SELFTEST_TEMPLATE or pr is not None or commit is not None:
            return "an announced retirement, a model free again or a new model changed the file"
        if any("removal" in f for r in result["providers"] for f in r["findings"]):
            return "a finding that is a decision was given an outcome"
        return None

    def snippets(result, new_text, report, issue, pr, commit):
        blocks = re.findall(r"  ```yaml\n(.*?)\n  ```", issue, re.DOTALL)
        news = [f for r in result["providers"] for f in r["findings"] if f["kind"] == "new"]
        if len(blocks) != len(news) or len(news) != 6:
            return "%d snippet(s) for %d NEW id(s), expected 6 and 6" % (len(blocks), len(news))
        parsed = []
        for block in blocks:
            document = yaml.safe_load("\n".join(line[2:] for line in block.split("\n")))
            if not (isinstance(document, list) and len(document) == 1):
                return "a snippet does not parse as one entry: %r" % block
            parsed.append(document[0])
        names = [entry["model_name"] for entry in parsed]
        if len(set(names)) != len(names) or set(names) & set(result["names"]):
            return "a proposed model_name is not new: %r" % names
        by_model = {entry["litellm_params"]["model"]: entry["litellm_params"] for entry in parsed}
        want = {
            "openrouter/vendor/fresh:free": ("os.environ/OPENROUTER_API_KEY_SELFTEST", None),
            "groq/vendor/new-fast": ("os.environ/GROQ_API_KEY_SELFTEST", None),
            "mistral/magistral-9": ("os.environ/MISTRAL_API_KEY_SELFTEST", None),
            "gemini/gemini-10-pro": ("os.environ/GEMINI_API_KEY_SELFTEST", None),
            "openai/SN-New": ("os.environ/SAMBANOVA_API_KEY_SELFTEST",
                              "https://api.sambanova.ai/v1"),
            "cerebras/cb-new": ("os.environ/CEREBRAS_API_KEY_<ACCOUNT>", None),
        }
        for model, (key, base_url) in want.items():
            got = by_model.get(model)
            if got is None:
                return "no snippet for %s" % model
            if got.get("api_key") != key or got.get("api_base") != base_url:
                return "%s is modelled on %r, expected %r" % (model, got, (key, base_url))
        expected_names = {"fresh-free", "new-fast-groq", "magistral-9", "gemini-10-pro",
                          "sn-new-sambanova", "cb-new-cerebras"}
        if set(names) != expected_names:
            return "proposed names %r, expected %r" % (sorted(names), sorted(expected_names))
        if "ne s'accordent pas" in issue:
            return "the issue says a provider's entries disagree on the api_base, and none does"
        if "insérer `# ` après les deux espaces d'indentation de chaque ligne" not in issue:
            return "the issue does not say how to comment a snippet out"
        return None

    def mixed_api_base_said(result, new_text, report, issue, pr, commit):
        if "Les entrées existantes de `gemini` ne s'accordent pas toutes sur l'`api_base`" \
                not in issue:
            return "the issue does not say that the Gemini entries disagree on the api_base"
        if "Les entrées existantes de `groq`" in issue:
            return "the issue says so of a provider whose entries agree"
        return None

    def snippets_dropped_when_too_long(result, new_text, report, issue, pr, commit):
        if "```yaml" in issue:
            return "the snippets were kept in a body past the limit"
        if len(issue) > 65536:
            return "the body is %d characters, past GitHub's limit" % len(issue)
        if "- `openrouter/vendor/bulk-0:free`" not in issue:
            return "the findings themselves were dropped with the snippets"
        return None

    def commented_form_is_read(result, new_text, report, issue, pr, commit):
        block = next((b for b in re.findall(r"  ```yaml\n(.*?)\n  ```", issue, re.DOTALL)
                      if "vendor/fresh:free" in b), None)
        if block is None:
            return "no snippet for the new OpenRouter id"
        # What the issue says to do: a "# " after the two spaces of indentation of each line.
        pasted = "".join("  # " + line[4:] + "\n" for line in block.split("\n"))
        text = SELFTEST_TEMPLATE.replace(
            "\nrouter_settings:\n",
            "\n  # Served, but not routed to: paid only.\n" + pasted + "\nrouter_settings:\n")
        before, _ = read_template(SELFTEST_TEMPLATE)
        template, problems = read_template(text)
        if template is None or problems:
            return "the file with the commented-out snippet breaks a rule: %r" % problems
        if len(template["commented"]) != len(before["commented"]) + 1 or not any(
                entry["model"] == "openrouter/vendor/fresh:free" for entry in template["commented"]):
            return "the commented-out snippet is not read as a commented-out entry"
        again = run_online(text, SELFTEST_KEYS, canned_opener(snippet_answers, []), "2026-01-01")
        if any(finding["id"] == "vendor/fresh:free" for report in again["providers"]
               for finding in report["findings"]):
            return "the id is still reported NEW once its commented-out form is in the file"
        return None

    def listed_groq(without):
        return answers_listing(APPLY_TEMPLATE, {("groq", identifier) for identifier in without})

    def groq_outcomes(result):
        return [finding["removal"] for report in result["providers"] if report["name"] == "groq"
                for finding in report["findings"] if "removal" in finding]

    def too_short_not_believed(result, new_text, report, issue, pr, commit):
        outcomes = groq_outcomes(result)
        if new_text != APPLY_TEMPLATE or pr is not None or commit is not None:
            return "a catalogue that omits most of what the file holds changed the file"
        if len(outcomes) != 4 or any(o["status"] != "refused" or o["reason"][0] != "implausible"
                                     for o in outcomes):
            return "outcomes %r" % [(o["status"], o["reason"]) for o in outcomes]
        if "omits 4 of the 7 ids this file holds for that provider" not in report:
            return "the report does not say why"
        if "ne liste pas 4 des 7 identifiants" not in issue:
            return "the issue does not say why"
        return None

    def three_of_seven_believed(result, new_text, report, issue, pr, commit):
        outcomes = groq_outcomes(result)
        if len(outcomes) != 3 or any(o["status"] != "applied" for o in outcomes):
            return "outcomes %r" % [(o["status"], o["reason"]) for o in outcomes]
        gone = [name for name in ("alpha-groq", "beta-groq", "shared-one", "shared-two")
                if "model_name: " + name + "\n" in new_text]
        if gone or "model_name: later-groq" not in new_text or pr is None:
            return "the three retired ids were not all deleted, or more than they were"
        return None

    commented_groq = APPLY_TEMPLATE.replace(
        "\nrouter_settings:\n",
        "\n  # Usable on Groq but not routed to: enterprise only.\n"
        "  # - model_name: c1-groq\n  #   litellm_params:\n  #     model: groq/vendor/c1\n"
        '  #     api_key: "os.environ/GROQ_API_KEY_SELFTEST"\n  #\n'
        "  # - model_name: c2-groq\n  #   litellm_params:\n  #     model: groq/vendor/c2\n"
        '  #     api_key: "os.environ/GROQ_API_KEY_SELFTEST"\n\nrouter_settings:\n')

    def commented_ids_count_as_held(result, new_text, report, issue, pr, commit):
        outcomes = {o["id"]: o for o in groq_outcomes(result)}
        if len(outcomes) != 4 or any(o["reason"] and o["reason"][0] == "implausible"
                                     for o in outcomes.values()):
            return "outcomes %r" % [(i, o["status"], o["reason"]) for i, o in outcomes.items()]
        if [i for i, o in sorted(outcomes.items()) if o["status"] == "applied"] != [
                "vendor/alpha", "vendor/beta"]:
            return "the two retired ids that can go were not both deleted"
        return None

    eight_groq = APPLY_TEMPLATE.replace(
        "\nrouter_settings:\n",
        "\n  - model_name: extra-groq\n    litellm_params:\n      model: groq/vendor/extra\n"
        '      api_key: "os.environ/GROQ_API_KEY_SELFTEST"\n\nrouter_settings:\n')

    def half_believed(result, new_text, report, issue, pr, commit):
        outcomes = groq_outcomes(result)
        if len(outcomes) != 4 or any(o["status"] != "applied" for o in outcomes):
            return "outcomes %r" % [(o["status"], o["reason"]) for o in outcomes]
        if pr is None or "extra-groq" in new_text:
            return "the four retired ids were not deleted"
        return None

    quartet = (
        "model_list:\n"
        '  - model_name: router\n    litellm_params:\n      model: gemini/gemini-9-pro\n'
        '      api_key: "os.environ/GEMINI_API_KEY_SELFTEST"\n\n'
        + "".join('  - model_name: q%d-groq\n    litellm_params:\n      model: groq/vendor/q%d\n'
                  '      api_key: "os.environ/GROQ_API_KEY_SELFTEST"\n\n' % (number, number)
                  for number in range(1, 5))
        + "router_settings:\n  fallbacks:\n    - router:\n"
        + "".join("        - q%d-groq\n" % number for number in range(1, 5)))

    def three_of_four_not_believed(result, new_text, report, issue, pr, commit):
        outcomes = groq_outcomes(result)
        if new_text != quartet or pr is not None:
            return "a catalogue that omits three of the four ids the file holds changed the file"
        if len(outcomes) != 3 or any(o["status"] != "refused" or o["reason"][0] != "implausible"
                                     for o in outcomes):
            return "outcomes %r" % [(o["status"], o["reason"]) for o in outcomes]
        return None

    def small_provider_believed(result, new_text, report, issue, pr, commit):
        outcomes = [finding["removal"] for r in result["providers"] if r["name"] == "cerebras"
                    for finding in r["findings"] if "removal" in finding]
        if len(outcomes) != 2 or any(o["status"] != "applied" for o in outcomes):
            return "outcomes %r" % [(o["status"], o["reason"]) for o in outcomes]
        if "cerebras/cb-" in new_text:
            return "the two Cerebras entries were not deleted"
        return None

    def hostile(result, new_text, report, issue, pr, commit):
        problem = hostile_lines(report, issue, pr, commit)
        if problem:
            return problem
        if any(spelling in issue for spelling in (
                "vendor/evil", "vendor/tick", "vendor//slashes", "vendor/colon")):
            return "an id spelt out of the ordinary became a NEW candidate"
        okay = [line for line in issue.splitlines()
                if line.startswith("- `openrouter/vendor/okay:free`")]
        if len(okay) != 1:
            return "the well-spelt id with a hostile name is not listed once"
        if okay[0].count("`") != 4:
            return "the hostile name broke out of its code span: %r" % okay[0]
        if "unusual spelling left out" not in report:
            return "the report does not say that an id was left out"
        return None

    new_free = [openrouter_model("vendor/fresh:free")]
    snippet_answers = changed(
        openrouter={"data": base["openrouter"]["data"] + new_free},
        groq={"data": base["groq"]["data"] + [{"id": "vendor/new-fast", "active": True}]},
        mistral={"data": base["mistral"]["data"] + [
            {"id": "magistral-9", "capabilities": {"completion_chat": True}}]},
        gemini=[base["gemini"][0], {"models": [
            {"name": "models/gemini-10-pro", "supportedGenerationMethods": ["generateContent"]}]}],
        sambanova={"data": [{"id": "SN-One"}, {"id": "SN-New"}]},
        cerebras={"data": [{"id": "cb-new"}]})
    hostile_answers = changed(
        openrouter={"data": base["openrouter"]["data"] + [
            openrouter_model("vendor/evil\n::error::pwned:free"),
            openrouter_model("vendor/tick`s:free"),
            openrouter_model("vendor//slashes:free"),
            openrouter_model("vendor/colon::pair:free"),
            dict(openrouter_model("vendor/okay:free"),
                 name="<img src=x> @someone [x](http://evil.example) www.evil.example"),
        ]},
        mistral={"data": [
            {"id": "mistral-large-2609", "aliases": ["mistral-large-latest"],
             "capabilities": {"completion_chat": True},
             "deprecation": "2026-12-31\n::error::z @bob",
             "deprecation_replacement_model": "`x`\n::warning::y @bob"}]},
        deepseek=urllib.error.HTTPError("https://selftest.invalid/", 500,
                                        "Boom\n::error::pwned @bob", None, io.BytesIO(b"")))
    many = {"openrouter": {"data": base["openrouter"]["data"] + [
                openrouter_model("vendor/bulk-%d:free" % number) for number in range(200)]},
            "groq": {"data": base["groq"]["data"] + [
                {"id": "vendor/bulk-%d" % number, "active": True} for number in range(200)]}}

    return (
        ("a retired model nobody routes to is deleted, and the issue, the pull request and the "
         "commit all say so",
         SELFTEST_TEMPLATE,
         changed(groq={"data": [{"id": "whisper-large-v9", "active": True}]}),
         deletes_fast, 1),
        ("a deletion that leaves nothing for a person to read has no section asking for it",
         SELFTEST_TEMPLATE,
         changed(groq={"data": [{"id": "whisper-large-v9", "active": True}]}),
         nothing_to_read, 1),
        ("one that leaves prose above the deleted entry lists it under \"À relire\"",
         SELFTEST_TEMPLATE.replace(
             "  - model_name: fast\n",
             "  # Prose about fast, which may as well be about its neighbours.\n"
             "  - model_name: fast\n", 1),
         changed(groq={"data": [{"id": "whisper-large-v9", "active": True}]}),
         something_to_read, 1),
        ("a retired model an alias points at is left alone, and the issue says why in French",
         SELFTEST_TEMPLATE, changed(openrouter=lacking("openrouter", "vendor/one:free")),
         keeps_free_one, 1),
        ("an announced retirement, a model free again and a new model are never touched",
         SELFTEST_TEMPLATE,
         changed(openrouter=openrouter_with_notice(base),
                 mistral={"data": [{"id": "mistral-large-2609", "aliases": ["mistral-large-latest"],
                                    "capabilities": {"completion_chat": True},
                                    "deprecation": "2026-12-31"}]},
                 groq={"data": [{"id": "vendor/fast", "active": False}]}),
         decisions_untouched, 1),
        ("a catalogue that lists nothing is not taken for everything retired",
         SELFTEST_TEMPLATE, changed(sambanova={"data": []}), empty_not_believed, 1),
        ("a provider that could not be read has nothing deleted, and the others are",
         SELFTEST_TEMPLATE,
         changed(deepseek=leaky_401("deepseek"),
                 groq={"data": [{"id": "whisper-large-v9", "active": True}]}),
         error_deletes_nothing_else, 2),
        ("a second run on the result finds nothing more to delete", SELFTEST_TEMPLATE,
         changed(groq={"data": [{"id": "whisper-large-v9", "active": True}]}), idempotent, 1),
        ("every NEW id comes with an entry to complete, modelled on its provider's own",
         SELFTEST_TEMPLATE, snippet_answers, snippets, 1),
        ("the commented-out form the issue documents is one the check reads as an entry",
         SELFTEST_TEMPLATE, snippet_answers, commented_form_is_read, 1),
        ("a provider whose entries disagree on the api_base is said to, next to the snippet",
         SELFTEST_TEMPLATE.replace("\nrouter_settings:\n", "\n  - model_name: flash-two\n"
                                   "    litellm_params:\n      model: gemini/gemini-9-flash-two\n"
                                   '      api_base: "https://selftest.invalid/openai/"\n'
                                   '      api_key: "os.environ/GEMINI_API_KEY_SELFTEST"\n'
                                   "\nrouter_settings:\n"),
         changed(gemini=[{"models": base["gemini"][0]["models"] + [
             {"name": "models/gemini-9-flash-two", "supportedGenerationMethods": ["generateContent"]},
             {"name": "models/gemini-10-pro", "supportedGenerationMethods": ["generateContent"]}]}],
                 groq={"data": base["groq"]["data"] + [{"id": "vendor/new-fast", "active": True}]}),
         mixed_api_base_said, 1),
        ("snippets are dropped, findings kept, when the issue body would pass GitHub's limit",
         SELFTEST_TEMPLATE, changed(**many), snippets_dropped_when_too_long, 1),
        ("text from a catalogue cannot start a workflow command, mention anyone or make markup",
         SELFTEST_TEMPLATE, hostile_answers, hostile, 2),
        ("a catalogue that omits most of the ids the file holds for its provider is not believed",
         APPLY_TEMPLATE, listed_groq(("vendor/alpha", "vendor/beta", "vendor/shared", "vendor/solo")),
         too_short_not_believed, 1),
        ("three of seven, which is not more than half, are believed",
         APPLY_TEMPLATE, listed_groq(("vendor/alpha", "vendor/beta", "vendor/shared")),
         three_of_seven_believed, 1),
        ("the commented-out ids of a provider count among those the file holds for it",
         commented_groq, answers_listing(commented_groq, {
             ("groq", identifier) for identifier in
             ("vendor/alpha", "vendor/beta", "vendor/shared", "vendor/solo")}),
         commented_ids_count_as_held, 1),
        ("exactly half omitted, at least three of them, is believed: more than half is the line",
         eight_groq, answers_listing(eight_groq, {
             ("groq", identifier) for identifier in
             ("vendor/alpha", "vendor/beta", "vendor/shared", "vendor/extra")}),
         half_believed, 1),
        ("three omitted of four known is not believed: three is where the line is crossed",
         quartet, answers_listing(quartet, {
             ("groq", "vendor/q%d" % number) for number in (1, 2, 3)}),
         three_of_four_not_believed, 1),
        ("a provider with fewer than three ids is believed whatever share goes",
         APPLY_TEMPLATE, dict(answers_listing(APPLY_TEMPLATE), cerebras={"data": [{"id": "cb-c"}]}),
         small_provider_believed, 1),
    )


def run_online_apply_cases():
    failures = 0
    for purpose, text, answers, check, status in online_apply_cases():
        outputs = apply_run(text, answers)
        result = outputs[0]
        why = None
        if exit_status(result) != status:
            why = "exit status %d, expected %d" % (exit_status(result), status)
        else:
            why = check(*outputs)
        if why is None:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s) -- %s" % (purpose, why))
    return failures


def run_command_line_cases():
    """The command line, end to end on a file in a temporary directory: it is written in place,
    writes the three texts, takes back the ones a run that deletes nothing would leave stale."""
    failures = 0
    answers = selftest_answers()
    answers["groq"] = {"data": [{"id": "whisper-large-v9", "active": True}]}

    def run(arguments, directory, environment=SELFTEST_KEYS):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                status = main(arguments, opener=canned_opener(answers, []),
                              environment=environment)
            except SystemExit as error:
                status = error.code
        return status, out.getvalue()

    with tempfile.TemporaryDirectory() as directory:
        config = os.path.join(directory, "config.yaml.j2")
        paths = {name: os.path.join(directory, name)
                 for name in ("issue", "pr", "commit", "coverage", "undeleted")}
        arguments = ["--online", "--config", config, "--issue-body", paths["issue"]]

        def read(name):
            return Path(paths[name]).read_text(encoding="utf-8") if os.path.exists(
                paths[name]) else None

        Path(config).write_bytes(SELFTEST_TEMPLATE.replace("\n", "\r\n").encode("utf-8"))
        status, _ = run(arguments + ["--coverage", paths["coverage"],
                                     "--undeleted", paths["undeleted"]], directory)
        steps = [
            ("without --apply, the file is not touched",
             status == 1 and Path(config).read_bytes().decode("utf-8")
             == SELFTEST_TEMPLATE.replace("\n", "\r\n") and read("pr") is None),
            ("every provider read, the coverage is complete", read("coverage") == "complete\n"),
            ("without --apply, the one retired model is counted as not deleted",
             read("undeleted") == "1\n"),
        ]
        run(arguments + ["--coverage", paths["coverage"]], directory,
            dict(SELFTEST_KEYS, MODEL_DRIFT_GROQ_API_KEY=""))
        steps.append(("a provider with no key makes it partial, whatever the status",
                      read("coverage") == "partial\n"))
        os.unlink(paths["coverage"])
        status, out = run(arguments + ["--apply", "--pr-body", paths["pr"],
                                       "--commit-message", paths["commit"],
                                       "--undeleted", paths["undeleted"]], directory)
        rewritten = Path(config).read_bytes().decode("utf-8")
        steps += [
            ("with --apply, a model that was deleted is no longer counted",
             read("undeleted") == "0\n"),
            ("with --apply, the file is rewritten in place, and its line endings are kept",
             status == 1 and "groq/vendor/fast" not in rewritten and "\r\n" in rewritten
             and "\n" not in rewritten.replace("\r\n", "")),
            ("with --apply, the issue, the pull request and the commit are written",
             all(read(name) for name in ("issue", "pr", "commit"))
             and "DELETED from the file" in out
             and "1 deletion(s) made, 0 left to a person" in out),
        ]
        status, out = run(arguments + ["--apply", "--pr-body", paths["pr"],
                                       "--commit-message", paths["commit"]], directory)
        steps += [
            ("a second run deletes nothing, finds no drift, and takes back the stale texts",
             status == 0 and Path(config).read_bytes().decode("utf-8") == rewritten
             and read("pr") is None and read("commit") is None
             and "Aucune dérive." in (read("issue") or "")),
        ]
        Path(paths["undeleted"]).write_text("0\n", encoding="utf-8")
        Path(config).write_text("model_list: [unclosed\n", encoding="utf-8")
        status, _ = run(arguments + ["--undeleted", paths["undeleted"]], directory)
        steps.append(("a file that cannot be read gets no count, and a stale one is taken back",
                      status == 2 and read("undeleted") is None))
        Path(config).write_bytes(rewritten.encode("utf-8"))
        for flags, purpose in ((["--apply", "--config", config],
                                "--apply without --online is refused"),
                               (["--undeleted", paths["undeleted"], "--config", config],
                                "--undeleted without --online is refused"),
                               (["--coverage", paths["coverage"], "--config", config],
                                "--coverage without --online is refused"),
                               (["--online", "--config", config, "--pr-body", paths["pr"]],
                                "--pr-body without --apply is refused")):
            status, _ = run(flags, directory)
            steps.append((purpose, status == 2))
    for purpose, passed in steps:
        if passed:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s)" % purpose)
    return failures


def run_selftest():
    """Prove that every rule refuses what it claims to refuse, and lets the baseline through."""
    # What the weekly workflow sets in the job that runs this check makes the issue carry a link to
    # the pull request, which the cases below do not expect: the selftest runs without them.
    kept = {name: os.environ.pop(name) for name in (
        "REMOVALS_BRANCH", "GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID")
        if name in os.environ}
    try:
        return run_selftest_cases()
    finally:
        os.environ.update(kept)


def run_selftest_cases():
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

    failures += run_apply_cases()
    failures += run_head_cases()
    failures += run_ranking_cases()
    failures += run_verify_cases()
    failures += run_safety_net_case()
    failures += run_online_apply_cases()
    failures += run_review_cases()
    failures += run_keyset_cases()
    failures += run_jinja_net_cases()
    failures += run_hardening_cases()
    failures += run_command_line_cases()
    return 1 if failures else 0


# ------------------------------------------------------------------------------------------------

def main(argv=None, opener=urllib_opener, environment=None):
    """The command line. "opener" and "environment" are what the selftest replaces: how a catalogue
    is fetched, and where the keys are read from."""
    environment = os.environ if environment is None else environment
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true",
                        help="verify the check against its in-memory cases, with no network")
    parser.add_argument("--online", action="store_true",
                        help="read every provider's catalogue and report the drift")
    parser.add_argument("--apply", action="store_true",
                        help="with --online, delete from --config every RETIRED and GONE entry "
                             "that can be deleted without anybody's judgment, and rewrite it "
                             "IN PLACE: run it on a checkout you can throw away")
    parser.add_argument("--issue-body", metavar="PATH",
                        help="with --online, write the rolling issue's body (French) to PATH")
    parser.add_argument("--pr-body", metavar="PATH",
                        help="with --apply, write the deletion pull request's body (French) to "
                             "PATH, when something was deleted")
    parser.add_argument("--commit-message", metavar="PATH",
                        help="with --apply, write the deletion commit's message to PATH, when "
                             "something was deleted")
    parser.add_argument("--coverage", metavar="PATH",
                        help="with --online, write \"complete\" to PATH when every provider's "
                             "catalogue was read, \"partial\" when one was not (no key, or an "
                             "error): a run that read only some of them cannot say that nothing "
                             "is left to delete")
    parser.add_argument("--undeleted", metavar="PATH",
                        help="with --online, write to PATH how many RETIRED and GONE findings the "
                             "run did not delete (all of them without --apply): a deletion pull "
                             "request is closed over \"nothing left to delete\" only at 0, "
                             "since a model the run refused to delete is still retired")
    parser.add_argument("--config", metavar="PATH", default=str(CONFIG),
                        help="the LiteLLM configuration to read (default: %(default)s)")
    arguments = parser.parse_args(argv)

    if arguments.selftest:
        return run_selftest()
    if (arguments.issue_body or arguments.coverage or arguments.undeleted) \
            and not arguments.online:
        parser.error("--issue-body, --coverage and --undeleted need --online")
    if arguments.apply and not arguments.online:
        parser.error("--apply needs --online")
    if (arguments.pr_body or arguments.commit_message) and not arguments.apply:
        parser.error("--pr-body and --commit-message need --apply")

    path = Path(arguments.config)
    try:
        shown = str(path.resolve().relative_to(ROOT))
    except ValueError:
        shown = str(path)
    try:
        # Bytes, so that a file's line endings come back exactly as they were read.
        text = path.read_bytes().decode("utf-8")
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
    result = run_online(text, environment, opener, today)
    if arguments.apply and not result["unreadable"]:
        new_text = apply_to_result(text, result)
        if new_text != text:
            path.write_bytes(new_text.encode("utf-8"))
    sys.stdout.write(render_text(result, shown))
    if arguments.coverage:
        Path(arguments.coverage).write_text(
            "complete\n" if is_complete(result) else "partial\n", encoding="utf-8")
    if arguments.undeleted:
        # A file that could not be read has no findings, which is no reason to say that none is
        # left: no file is written for it, and the workflow reads that as "unknown".
        Path(arguments.undeleted).unlink(missing_ok=True)
        if not result["unreadable"]:
            Path(arguments.undeleted).write_text("%d\n" % undeleted_count(result),
                                                 encoding="utf-8")
    if arguments.issue_body:
        Path(arguments.issue_body).write_text(render_issue_body(result, shown, link=run_link()),
                                              encoding="utf-8")
    deleted = result.get("removals", {}).get("changed")
    for target, render in ((arguments.pr_body, lambda: render_pr_body(result, run_link())),
                           (arguments.commit_message, lambda: render_commit_message(result))):
        if target:
            # A file left over from an earlier run would be taken for this run's.
            Path(target).unlink(missing_ok=True)
            if deleted:
                Path(target).write_text(render(), encoding="utf-8")
    return exit_status(result)


def guarded(entry, argv=None):
    """The exit status of "entry(argv)", a crash having the status of its own."""
    try:
        return entry(argv)
    except Exception as error:
        return crashed(error)


def crashed(error):
    """What a crash is allowed to say: the kind of error and where, never its message, which can
    carry a piece of what a provider answered."""
    frames = traceback.extract_tb(error.__traceback__)
    where = " in %s (line %d)" % (frames[-1].name, frames[-1].lineno) if frames else ""
    sys.stderr.write("check_LiteLLM_model_drift: crashed, %s%s. The status %d is neither 0, 1 nor "
                     "2: nothing this run says can be trusted.\n"
                     % (error.__class__.__name__, where, CRASH_STATUS))
    return CRASH_STATUS


if __name__ == "__main__":
    # An uncaught exception exits 1 -- "drift" -- and a workflow that read it so would act on a
    # report nobody wrote: it would close a pull request over "nothing left to delete". A crash
    # exits with a status of its own.
    # The selftest has no provider's answer to keep out of the log, and wants its traceback.
    sys.exit(main() if "--selftest" in sys.argv[1:] else guarded(main))
