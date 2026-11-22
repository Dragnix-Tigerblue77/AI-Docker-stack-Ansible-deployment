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
cascades and the aliases follow. This check reads it RENDERED, with every provider key given --
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
  names it reads are still held to the provider keys, since that check reads the template without
  rendering it. Rendering every other set of keys and holding each alias to the first member of its
  cascade is "check_compose_template.py"'s job.
* A template that does not render -- a Jinja syntax error, a variable that is none of the provider
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
below -- OmniRoute, local and keyless, and the "zai/<id>" ones, whose provider this check does not
read -- is left out, and the report says how many: it is never RETIRED, never reported as unknown,
and a "drift-ignore:" line cannot name Z AI.

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

A video generation model served through "generateContent" (Gemini's "omni" one is) is therefore
still offered as NEW, and is turned down with a "drift-ignore:" line. Gemini's model listing has no
field that would tell it apart (name, version, displayName, description, token limits,
supportedGenerationMethods, temperature, thinking), and "omni" is not a marker to add: other
vendors' "omni" models are chat models, one of them routed in the file this check reads.

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
to examine, never claimed free, and the issue links the page of each provider listed there
(PRICING_PAGES, a table the selftest holds to the providers it can be needed for): the link is a
convenience, the free tier is still checked by a person.

A NEW id that neither pull request of additions carries (see "PROPOSING WHAT IS NEW" below), or
every NEW id when the run proposes nothing, is listed in the issue with an entry to complete, ready
to paste: the "model:" with its
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
model.

A list can omit a model that is still served, so on the providers whose API answers for one model
by its id (LOOKUPS: Gemini, Groq, Mistral) a finding is acted on only once the provider has been
asked for the model itself. One it still serves leaves the findings and is listed apart (SERVED in
the report, a section of the issue). One it answers 404 for is deleted. Any other answer leaves the
finding to a person, with that answer in the report, and so does a route that cannot be believed:
it has to answer 200 first for a model the list does name, of the same shape (with a slash in its
id or without, since a slash may not be routed like a plain id). The references document the route
and not the status of an unknown id, which is why nothing is deleted on any answer but a 404. The
other providers, whose API has no such route, are deleted from on their list alone, as before.

"--apply" deletes, for each such id, in a single pass over the file:

* every entry attributed to it, active or commented out, and the model_name's slot in each of the
  four fallback keys of both sections. The blank line that separated an active entry from the next
  goes with it, unless the entry had prose above it.
* of a commented-out entry, the reason prose that belongs to it alone. A run of entries shares the
  reason above its first (see above), so the reason stays while an entry of the run does, now over
  the first that stays, and goes when the last one does. A section banner goes with a run only when
  the banner is itself the reason ("SambaNova -- not routed to: ..."); one that is a heading over
  entries that may stay ("Cerebras & Groq") is kept, and so is a "# drift-ignore:" line, which is a
  statement about an id and not about the run. A Jinja statement written between the reason and
  its run ("{% if has.Groq %}" over the entries) is read through, as the rendering does, when it
  closes right after the run: the statement stays and the reason goes with the run, provided it
  says "not routed", names no model that stays, and no entry that stays follows the run once the
  statements are read away (the reason would then be that one's as well). Otherwise it stays, and
  is listed under "À relire".

What it leaves where it is, because only a person can tell, is every comment: none is rewritten, and
a comment can say what is no longer so. Verification reads the structure of the file, not its
prose, so the pull request body lists under "À relire", by their line numbers in the new file,
the places a deletion may have made false:

* the comment above a deleted ACTIVE entry, which may describe that entry or the group it opens,
  and the reason above a statement over a deleted run that it was not safe to delete with it;
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
hand: the pull requests of additions now carry them, and the issue for a NEW model neither carries.
With MODEL_DRIFT_ARTIFICIAL_ANALYSIS_API_KEY set, the run reads
Artificial Analysis's free API (GET https://artificialanalysis.ai/api/v2/language/models/free, the key
in the "x-api-key" header, 100 requests per 24 hours, one made per page of the answer and at most
MAX_PAGES per run) and the issue gains a table of each
NEW model's intelligence index, coding index, output speed and blended price, then a suggested place
per router: before the first member of that router's cascade the ranking scores lower on the figure
that decides it (intelligence for "pro", "flash" and "claude-code", coding for "code", speed for
"flash-lite"), or after the last one. The source is named in the issue with its day, as the terms of
use of that API ask, and the figures are shown as published.

* It is optional the way a provider's key is, and no more than that: without the key the report says
  "not covered" and the run is the same; a failed read is reported, with the HTTP status and nothing
  else, and changes neither the exit status, nor what the run covers, nor what it deletes. The
  ranking is not a catalogue of a provider, so it is kept out of "result[providers]" for this. An
  answer is read page by page ("page" parameter) for as long as its "pagination.has_more" says so;
  one still saying so after MAX_PAGES is a failed read, not a partial one, since a table made of a
  part of the models would place a new one against the wrong neighbours. The endpoint this replaces
  (/api/v2/data/llms/models) was retired by Artificial Analysis and answers 410 Gone, which is
  reported like any other status.
* The figures are read from the shape the free tier documents: the indexes under "evaluations", the
  speed under "performance_v3" (its headline mean of the end-to-end output speed) and the two prices
  under "pricing". The "performance" block is not read: its fields were retired, and answer null.
  That tier publishes no blended price, so the one shown is the 3 to 1 blend of input and output
  Artificial Analysis defines for it, computed here, and none when either price is missing. Its
  reference marks the coding index deprecated: when it goes, the figure is none and the table shows a
  dash.
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

PROPOSING WHAT IS NEW
--------------------
"--proposals DIR" proposes the NEW models in two pull requests of their own, which the workflow keeps
and which only a person merges, rather than listing them in the issue. They are split by how much the
run knows of each model, never by its provider:

* "ready", ready for review: a model of which the run holds every fact an addition needs -- its free
  tier, stated by its provider's own API (FREE_CATALOGUES: today OpenRouter's ":free", both prices
  "0", text the only output), and a figure of the ranking matched for certain (certain_match: the last
  segment of the id, less ":free", and the slug or the name of one entry of the whole ranking and of
  no other are equal once lower-cased with everything but letters and digits removed, and that
  entry's name carries no variant marker such as "(Reasoning)"). A provider whose free tier
  becomes machine-readable is added to FREE_CATALOGUES, and nothing else changes;
* "to_verify", opened as a draft: a model of which at least one of those facts is missing
  (missing_facts: a free tier the API does not state, a ranking not read, no entry, several, a match
  by name only or onto a variant, an entry with no figure). Its body says, for each model, which
  fact is missing and how to get it: for a free tier, the page to open and what to look for on it
  (FREE_TIER_CHECKS, held to PRICING_PAGES by the selftest), the comment with its date to write above
  the entry, and the "drift-ignore" line that sets the model aside if the answer is no; for the
  ranking, where to look the model up; and for every model a command that reads it in the provider's
  catalogue and prints nothing secret (a keyed one runs in the LiteLLM container, whose environment
  holds the key under the name the entry reads it from).

Each entry is modelled on its provider's last entry in "model_list" -- its last active one, else its
last commented-out one -- whose key and base it copies, and written right after it (after the comment
block, for a commented-out one, so that a run and its reason stay together), under a comment of a
fixed text that says where it comes from and when; it is commented out, with a "not routed" reason
to replace, when the provider has no active entry. Neither pull request puts a model in a cascade:
the body gives its figures and its suggested place in each router (THE RANKINGS), which are
suggestions computed on a ranking under revision, or, for a model the ranking does not measure, says
it is not placed and gives the "drift-ignore" line that sets it aside. A model merged, or set aside by
"drift-ignore", is known and never proposed again.

What is proposed is a provider, an id and a name, written to "proposals.json" with whether every
source the kind draws on was read; the job of the workflow that writes builds the file from those
alone, by the rules build_additions() follows, and pushes it only when it is the text this script
built and read back (addition_problem: it renders, breaks no offline rule the file did not, holds the
file's entries and the proposed ones and every cascade as it was). It refuses what this refuses: an
id or a name of another spelling than ADDITION_ID and ADDITION_NAME, a name that is a word of the
file, a ready model of a provider whose API does not state its free tier, an id of such a provider
that does not end in ":free", an id already an entry or set aside, an entry to model one on whose key
is not read from the environment or whose base is not https, more than PROPOSAL_LIMIT entries. A NEW
model this cannot propose -- of a spelling the file is not written with, of a provider with no entry,
past the cap, or one whose body would be too long -- stays in the issue, with the reason;
"--issue-status PATH" writes the status the issue is kept by, the exit status less the NEW models a
pull request carries.

THE ROUTER CONTRACTS
--------------------
".github/LiteLLM_router_contracts.yaml" says what each router is held to: a floor on the intelligence
index (on the version the file names), written as an ANCHOR, "at least as good as that model", whose
figure is read at every run and never copied into the file -- from the Artificial Analysis ranking for an
entry of the template, from Epoch AI's capabilities index for a model that index names -- or NO floor,
for a router that takes every model that answers; the exchange rate an extra reasoning level
must reach to be worth climbing to (points of index per extra second to the first answer token), how its
members are ordered, the members exempt from the floor on
purpose (the last resort), and, for each entry of the template, the Artificial Analysis record that
describes it at the reasoning level the entry is called at, with the page that gives that level, or
"unknown". There is NO time budget: the goal is to use as many free models as possible, so a slow model is
never ineligible. A member is eligible for a router if it reaches the floor (and, for "claude-code", takes
tool calls), and time only orders: "flash-lite" puts the shortest mean time to the first answer token
first, and the other routers put the best quality first, the time deciding between members whose quality
is less than the router's "tie_margin_points" apart.

The unit of routing is model plus level: Artificial Analysis has one record per level, told apart by the
suffix of its name. The level a router keeps for a model is found by walking up the levels that have an
index from the lowest, and climbing to the next only while each extra second of the time to the first
answer token buys at least "min_points_per_second" points of index (a router that values time asks more
points per second; a step that is no slower is taken when it buys points, a step that buys none or whose
time is unknown is not taken). "claude-code" derives from "code": it is ranked as
"code" is, and its cascade is the cascade of "code" without the members that cannot take tools, which the
report checks and whose differences it lists. The whole file is PROVISIONAL until the maintainer
validates it, and its header says what is left to define.

The capabilities index (ECI) of Epoch AI is read from the same archive as code quality (the member
"epoch_capabilities_index/eci_scores.csv", a figure per display name, under the same caps and the same
allow-list; the other members of that folder are never opened), with the same attribution. It measures
nearly every model the ranking has no index for, and the file declares how to turn it into the scale of the
intelligence index: calibration points, joined by a line that goes on past its ends with the slope of the
end segment and is never below 0. Every figure so obtained is an ESTIMATE, said "estimé" wherever it is
shown. It is used for two things. A floor may name a model of that index ("epoch") and then is the
converted figure. A member the ranking has no index for at the level it is called at, whether it has no
record, an index-less record or a level that is not verified, is placed on the converted index of the model
its entry names ("eci"), ordered by it like any other with the margin and the time rule (the time is the
ranking's, so an estimate has none); the index of the ranking always wins where it exists, the level kept
and the exchange rate stay the ranking's, and a router ordered by time takes no estimate. Where the index
was not read, an anchor on it cannot be read, nothing is judged against it and the issue says so, as for an
entry that cannot be read; a name the index no longer holds is listed as stale, and is information.

"code" is ranked on code quality, read from Epoch AI's benchmark data (benchmark_data.zip, free, no key, CC
BY 4.0, to be cited with the day it was read) by the online run that has the contracts, after the ranking
the contracts stand on. Five of its files are read and no other (DeepSWE, SWE-bench Verified, CursorBench,
Terminal-Bench, ALE-Bench: WebDev Arena and any design or interface arena measure design, and are never
opened): the archive is held in memory, its members are found by their exact names, each is cut at a size,
a row that is not a model version with a finite score is left out and counted, and a model version listed
several times keeps its best score. For a cascade, the score of a member in a file is the best of the model
versions its entry lists for that file; a file counts only if two members of the cascade have a score in
it, and ranks them (1 is the best, a tie shares the average rank); the code quality of a member is the
median of its ranks, over two files at least, and a member that fewer files rank is UNRANKABLE by code
quality. The router puts its ranked members first, best code quality first, the shorter time between equal
ones; the unrankable members are not removed, they follow in the main tier on the intelligence index that
stands in for it (with the time deciding inside the margin), and the report says so; the last resort and the
members under the floor go to the tail as for every router. The cascade of a router that derives from
"code" is ranked with the pool of that of "code", so that the two orders cannot disagree, and a member it
has that "code" has not is unrankable. A read that fails,
whatever the reason (the network, a size, the shape of the archive, no usable row), is reported as "not
read" in that section and changes nothing else: the intelligence index orders the cascade, as it did before
any of this, and the status the issue shows is what the run read, never what the file declares. The plain
run reads no archive.

It is a report and nothing else. The weekly issue gains a section "Contrats par routeur" (and no other
text carries it) with, per router, a table of its members (record, level called, intelligence, time,
speed, the level the router would keep, the verdict), the order the contract would give against the
current one, the outcome of each floor the contract proposes to compare, and for a derived router how its
cascade differs from the one it must be; then the entries without a mapping, those with no record, the
names the file keeps that the template no longer has, the mappings whose slug the ranking no longer has
("stale") and those called at a level the ranking does not cover. A verdict is "conforme", "sous le
plancher" (the member goes to the last resort tier, it is not removed), "inclassable" (no index, or, for a
router ordered by time, no time), or "variante non vérifiée" (the level is unknown and the family has
several, or the ranking has the family at other levels only). No member is removed from a cascade by it,
whatever its verdict: a member with no index stays where it is, flagged, until the fallback is read. It is
computed from the ranking the run already read, by the job that holds the key, from the template as it
stood before any deletion; it changes no cascade, no entry and no row of the "head" table, never changes
the exit status, never blocks the deletion pull request, and says only the kind of error when its
computation fails.

The plain offline run reads the file too, and fails on its structure alone: a router that does not exist
or has no contract, a number that is not a number, a value with no reason, a mapping with fields that are
wrong (no tools declaration, say), a file that cannot be read, a key written twice. It reads it only
against the repository's template (or the file given by "--contracts"), since a contract written for one
template means nothing against another. A name the file keeps that is no entry of the template any more,
in a mapping or in a last resort, is NOT a failure: the weekly deletion pull request is merged by a gate
that wants CI green, and a deletion leaves exactly that behind. The plain run prints one notice line for
each such stale row and exits 0, and the issue lists them under "Correspondances sans entrée", for a
person to remove from the file.

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
* It never adds a model to main, and never writes a reason a person has not. Every claim in the list
  cites the provider's own page and the date it was checked. A deletion can cite the catalogue it
  read and the day it read it, and the pull request body does; an addition is a choice, and a reason
  is somebody's statement, so what the check produces for those -- the pull requests of additions,
  BACK, NOTICE -- is where a person's check starts, not a substitute for it.
* It opens no pull request and pushes nothing: it edits a file and writes the texts it is given
  a path for (the issue, the pull request, the commit message, the coverage, the count of what it
  did not delete, the proposals). The workflow that runs it does the rest.
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
        --coverage /tmp/coverage.txt --undeleted /tmp/undeleted.txt \\
        --proposals /tmp/proposals --issue-status /tmp/issue_status.txt
"""

import argparse
import collections
import contextlib
import copy
import csv
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
import statistics
import sys
import tempfile
import textwrap
import threading
import traceback
import urllib.error
import urllib.parse
import urllib.request
import zipfile
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
    for provider in ("Gemini", "Mistral", "Groq", "OpenRouter", "DeepSeek", "Zai")
)
JINJA_EXPRESSION = re.compile(r"\{\{.*?\}\}", re.DOTALL)
JINJA_STATEMENT = re.compile(r"\{%.*?%\}", re.DOTALL)
JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)
JINJA_COMMENT_LINE = re.compile(r"^\s*\{#.*#\}\s*$")
# What a Jinja expression becomes in the file made parsable: a cascade named by one ("{{ alias }}: *anchor")
# is the list of its anchor under another name, and is not a cascade of its own to name in a message.
JINJA_PLACEHOLDER = "JINJA"
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
    """The file as this check's plain Jinja2 sandbox renders it with every provider key given."""
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
        raise RenderError("the file reads %s, which is none of the provider keys"
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
    return JINJA_EXPRESSION.sub(keep_lines(JINJA_PLACEHOLDER), text)


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
    file with every key given, and a cascade that holds only the members of one provider is empty
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
    """A catalogue that could not be read. Its message never carries a key nor a response body.
    "status" is the HTTP status when the provider answered with one, and None otherwise."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse to follow a redirect. urllib sends the request's headers again to wherever the
    "Location" names, host included, and the keys travel in those headers: a catalogue that
    redirects is an error to report (HTTP 302...), never a place to send a key to."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def urllib_opener(url, headers, limit=None):
    """The answer's body, or with a "limit" at most one byte more than it, which says it is too big
    without having held all of it."""
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.build_opener(NoRedirect).open(request, timeout=TIMEOUT) as response:
        return response.read() if limit is None else response.read(limit + 1)


def fetch_raw(opener, url, headers, *limit):
    """The body of an answer, or a FetchError that says no more than the kind of failure."""
    try:
        return opener(url, headers, *limit)
    except urllib.error.HTTPError as error:
        # Neither the body nor the reason phrase is read: a provider may echo the key back in
        # either, and the status says all a person needs to know (HTTP/2 has no phrase at all).
        raise FetchError("HTTP %d" % error.code, error.code) from None
    except urllib.error.URLError as error:
        raise FetchError("network error: %s" % safe_text(error.reason)) from None
    except (OSError, ValueError, http.client.HTTPException) as error:
        raise FetchError("network error: %s" % error.__class__.__name__) from None


def fetch_json(opener, url, headers):
    raw = fetch_raw(opener, url, headers)
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

# Where each other provider says what is free, which the report links under "to examine": its API
# does not say, so whoever checks a NEW model is sent to the page that does. Cerebras and Groq are
# linked on their rate-limits page, the one that states their free tier (Groq's "/pricing" leads to
# its home page); every page was opened when the entry was written.
PRICING_PAGES = {
    "cerebras": "https://inference-docs.cerebras.ai/support/rate-limits",
    "sambanova": "https://cloud.sambanova.ai/plans",
    "gemini": "https://ai.google.dev/gemini-api/docs/pricing",
    "groq": "https://console.groq.com/docs/rate-limits",
    "mistral": "https://mistral.ai/pricing",
    "deepseek": "https://api-docs.deepseek.com/quick_start/pricing",
}


def pricing_page_problems(providers, free_readable, pages):
    """What is wrong with the table of pricing pages, as sentences: a provider whose NEW models are
    listed to examine and has no page to examine them on, a page of a provider that is never listed
    there, and an address that is not a plain https one."""
    listed = [name for name in providers if name not in free_readable]
    problems = ["%s has no pricing page, so its NEW models are listed to examine with nowhere to "
                "examine them" % name for name in listed if name not in pages]
    problems += ["%s has a pricing page but none of its NEW models is ever listed to examine"
                 % name for name in sorted(pages) if name not in listed]
    problems += ["the pricing page of %s is not a plain https address: %r" % (name, url)
                 for name, url in sorted(pages.items())
                 if name in listed and not (isinstance(url, str) and url.startswith("https://")
                                            and url.isprintable() and " " not in url)]
    return problems


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


# Where a provider answers for ONE model by its id, on the three whose API reference documents it. A
# list can omit a model that is still served -- Gemini's omits a preview model that answers when asked
# for it -- so a model the list does not name is deleted only once the provider has also said, when
# asked for it directly, that there is no such model. Mistral answers for the subscription tier of the
# key: a model of another tier is missing from its list and answers 404 here, while a chat call to it
# is refused with 403, so for this key that is a retirement and the deletion stands. The references
# document the route and not the status of an unknown id, which is why nothing is deleted on any
# answer but a 404, and why that 404 is trusted only once the same route has answered 200 for a model
# the list does name.
LOOKUPS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models/",
    "groq": "https://api.groq.com/openai/v1/models/",
    "mistral": "https://api.mistral.ai/v1/models/",
}
LOOKUP_LIMIT = 30  # per provider and run: a list that omits more than this is not a retirement


def ask_for(opener, provider, identifier, headers):
    """What "provider" says when asked for the model "identifier": "served", "absent" (a 404), or
    why it did not say (a sentence, which never carries a key nor a response body)."""
    url = LOOKUPS[provider] + urllib.parse.quote(identifier, safe="/")
    try:
        answer = fetch_json(opener, url, headers)
    except FetchError as error:
        return "absent" if error.status == 404 else str(error)
    return "served" if isinstance(answer, dict) else "the answer is not an object"


def confirm_absences(provider, report, catalogue, opener, headers):
    """Ask "provider" for each model its list omits, on the providers that can be asked. A model it
    still serves is not retired: it leaves the findings, and is kept in report["served"]. One it
    says it does not know is marked "confirmed". Any other answer marks the finding "unconfirmed"
    with the reason, and the finding stays, to be left to a person."""
    if provider not in LOOKUPS:
        return
    trusted = {}

    def untrusted(slashed):
        # Why the route cannot be believed for ids of this shape (a slash may not be routed the
        # way a plain id is), or None once it has answered 200 for a listed model of that shape.
        if slashed not in trusted:
            sample = next((member for member in sorted(catalogue["members"])
                           if ("/" in member) == slashed), None)
            if sample is None:
                trusted[slashed] = "no listed model of this shape to check the lookup against"
            else:
                verdict = ask_for(opener, provider, sample, headers)
                trusted[slashed] = None if verdict == "served" else (
                    "the lookup of the listed model %s answered %s"
                    % (safe_text(sample), "404" if verdict == "absent" else verdict))
        return trusted[slashed]

    kept, asked = [], 0
    for finding in report["findings"]:
        if finding["kind"] not in ("retired", "gone"):
            kept.append(finding)
            continue
        kept.append(finding)
        reason = untrusted("/" in finding["id"])
        if reason is None and asked >= LOOKUP_LIMIT:
            reason = "more than %d models are missing from the list, too many to look up" % LOOKUP_LIMIT
        if reason is not None:
            finding["unconfirmed"] = reason
            continue
        asked += 1
        verdict = ask_for(opener, provider, finding["id"], headers)
        if verdict == "served":
            kept.pop()
            report.setdefault("served", []).append(finding)
        elif verdict == "absent":
            finding["confirmed"] = True
        else:
            finding["unconfirmed"] = verdict
    report["findings"] = kept


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
RANKING_URL = "https://artificialanalysis.ai/api/v2/language/models/free"
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


def blended_price(price_in, price_out):
    """The price per million tokens at three input tokens to one output, as Artificial Analysis blends
    it, or None when either price is not a figure: the free tier publishes the two and not the blend."""
    price_in, price_out = figure(price_in), figure(price_out)
    return None if price_in is None or price_out is None else (3 * price_in + price_out) / 4


def has_more_pages(payload):
    """Whether the page says another follows: only an explicit true does, so a page without
    "pagination" is the last one."""
    pagination = payload.get("pagination") if isinstance(payload, dict) else None
    return isinstance(pagination, dict) and pagination.get("has_more") is True


def read_ranking_models(payload):
    """The models of one page of the free language models endpoint, as documented on its API reference:
    a "data" list of objects with "name", "slug", "evaluations" (the intelligence and coding indexes),
    "pricing" and "performance_v3" (the mean output speed). Anything else in an object is ignored and a
    missing figure is None; what is shown of it is cut to plain words, since the answer is untrusted
    text."""
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise FetchError('the answer holds no "data" list')
    models = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        evaluations = item.get("evaluations") if isinstance(item.get("evaluations"), dict) else {}
        pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
        performance = item.get("performance_v3") if isinstance(item.get("performance_v3"), dict) else {}
        creator = item.get("model_creator") if isinstance(item.get("model_creator"), dict) else {}
        slug = item.get("slug") if isinstance(item.get("slug"), str) else ""
        models.append({
            "name": safe_text(item["name"], 80),
            # Compared with an id, never shown.
            "slug": slug.lower(),
            "creator": safe_text(creator.get("name") or "", 40),
            "keys": {key for key in (squash(slug), squash(item["name"])) if len(key) >= RANKING_MIN_KEY},
            "intelligence": figure(evaluations.get("artificial_analysis_intelligence_index")),
            "coding": figure(evaluations.get("artificial_analysis_coding_index")),
            "speed": speed_figure(performance.get("mean_output_tokens_per_second")),
            "slug": slug if SAFE_ID.fullmatch(slug) else "",
            "first_answer": seconds_figure(performance.get("mean_time_to_first_answer_token_seconds")),
            "price": blended_price(pricing.get("price_1m_input_tokens"), pricing.get("price_1m_output_tokens")),
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
        for number in range(1, MAX_PAGES + 1):
            payload = fetch_json(opener, "%s?page=%d" % (RANKING_URL, number), headers)
            ranking["models"] += read_ranking_models(payload)
            ranking["index_version"] = figure(payload.get("intelligence_index_version"))
            if not has_more_pages(payload):
                break
        else:
            raise FetchError("the ranking source still has pages after %d" % MAX_PAGES)
    except FetchError as error:
        ranking["status"] = "error"
        ranking["models"] = []
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
        confirm_absences(name, report, catalogue, opener, headers)
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
# Epoch AI's benchmark data: the source of code quality, and of the capabilities index
# ------------------------------------------------------------------------------------------------

EPOCH_URL = "https://epoch.ai/data/benchmark_data.zip"
EPOCH_SITE = "https://epoch.ai/benchmarks"
EPOCH_ATTRIBUTION = "Epoch AI, benchmark data, CC BY 4.0"
# The benchmark files code quality is read from, as (key, name shown, the column that holds the score).
# Only these five members of the archive, and the capabilities index below, are ever opened, by their
# exact name: a web interface arena measures design and is left out on purpose, and nothing else of the
# archive is code quality.
EPOCH_FILES = (
    ("deepswe_external", "DeepSWE", "Pass@1"),
    ("swe_bench_verified", "SWE-bench Verified", "mean_score"),
    ("cursorbench_external", "CursorBench", "Score"),
    ("terminalbench_external", "Terminal-Bench", "Accuracy mean"),
    ("ale_bench_external", "ALE-Bench", "Performance"),
)
EPOCH_KEYS = tuple(key for key, _, _ in EPOCH_FILES)
EPOCH_ID_COLUMN = "Model version"
# The capabilities index (ECI) is one figure per model, in a member of its own: the model's display name
# and the index. It is held under its own key where the archive says what it did not read.
EPOCH_ECI_KEY = "eci"
EPOCH_ECI_MEMBER = "epoch_capabilities_index/eci_scores.csv"
EPOCH_ECI_ID_COLUMN = "Display name"
EPOCH_ECI_COLUMN = "eci"
# The archive is downloaded whole and its members are read from memory, never extracted. The caps are
# a few times what the real figures are, so that an answer that is not the archive is refused before
# it is held, and a member that expands far beyond its size is cut.
EPOCH_MAX_ARCHIVE = 8 * 1024 * 1024
EPOCH_MAX_MEMBER = 2 * 1024 * 1024
EPOCH_MAX_ROWS = 20000
EPOCH_MAX_BAD_ROWS = 1000
EPOCH_MAX_ID = 200
# A benchmark file ranks the members of a cascade only if this many of them have a score in it, and a
# member is ranked only if this many files rank it.
EPOCH_MIN_MEMBERS = 2
EPOCH_MIN_FILES = 2


def epoch_member_name(key):
    return key + ".csv"


def read_epoch_scores(raw, column, id_column=EPOCH_ID_COLUMN):
    """({name: best score}, rows read, rows left out) of one CSV member, or the reason it is not read
    as a string. A model version listed several times (Terminal-Bench has a row per agent) keeps its
    best score. A row with no name, or no score that is a finite number, is left out and counted, and
    a file that is not a table at all is no file."""
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="replace")))
        if id_column not in (reader.fieldnames or ()) or column not in reader.fieldnames:
            return "it has not the columns expected"
        rows = iter(reader)
        scores, read, bad = {}, 0, 0
        while read + bad < EPOCH_MAX_ROWS and bad <= EPOCH_MAX_BAD_ROWS:
            try:
                row = next(rows)
            except StopIteration:
                break
            except csv.Error:
                bad += 1
                continue
            identifier, text = row.get(id_column), row.get(column)
            try:
                score = figure(float(text.strip())) if isinstance(text, str) else None
            except ValueError:
                score = None
            if not isinstance(identifier, str) or not identifier.strip() or score is None \
                    or len(identifier.strip()) > EPOCH_MAX_ID:
                bad += 1
                continue
            read += 1
            identifier = identifier.strip()
            scores[identifier] = max(scores.get(identifier, score), score)
    except (csv.Error, ValueError):
        return "it is not read as a table"
    return (scores, read, bad) if scores else "it has no usable row"


def read_epoch_member(archive, name, column, id_column=EPOCH_ID_COLUMN):
    """The scores of one member of the archive, found by its exact name, as read_epoch_scores gives
    them, or the reason it is not read. At most EPOCH_MAX_MEMBER bytes of it are read, whatever its
    header says."""
    info = archive.NameToInfo.get(name)
    if info is None or info.is_dir():
        return "absent from the archive"
    if info.file_size > EPOCH_MAX_MEMBER:
        return "larger than %d bytes" % EPOCH_MAX_MEMBER
    try:
        with archive.open(info) as member:
            data = member.read(EPOCH_MAX_MEMBER + 1)
    except Exception as error:
        return "unreadable (%s)" % error.__class__.__name__
    if len(data) > EPOCH_MAX_MEMBER:
        return "larger than %d bytes" % EPOCH_MAX_MEMBER
    return read_epoch_scores(data, column, id_column)


def read_epoch_archive(raw):
    """(files, skipped, eci) from the bytes of the archive: {key: {"scores", "rows", "bad"}} for each of
    the five benchmark members that gave a usable row, {key: reason} for each member that did not
    (the capabilities index under EPOCH_ECI_KEY), and {display name: index} of the capabilities index,
    empty when its member is not read. Raises FetchError when the bytes are no archive. Nothing is
    extracted."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except (zipfile.BadZipFile, ValueError, OSError):
        raise FetchError("the answer is not a zip archive") from None
    files, skipped, eci = {}, {}, {}
    with archive:
        for key, _, column in EPOCH_FILES:
            found = read_epoch_member(archive, epoch_member_name(key), column)
            if isinstance(found, str):
                skipped[key] = found
            else:
                files[key] = {"scores": found[0], "rows": found[1], "bad": found[2]}
        found = read_epoch_member(archive, EPOCH_ECI_MEMBER, EPOCH_ECI_COLUMN, EPOCH_ECI_ID_COLUMN)
        if isinstance(found, str):
            skipped[EPOCH_ECI_KEY] = found
        else:
            eci = found[0]
    return files, skipped, eci


def read_epoch(opener, today):
    """The state of Epoch AI's archive: {"status": "read" | "error", "date", ...}. "read" holds the
    benchmark files that gave scores, the capabilities index ("eci", empty when its member is not
    read) and, for the members that did not, why not; "error" says why nothing was read, and is never
    more than the kind of failure. It raises nothing and changes nothing else of the run: a code
    quality that is not read is the intelligence index standing in for it."""
    try:
        raw = fetch_raw(opener, EPOCH_URL, {"User-Agent": USER_AGENT, "Accept": "application/zip"},
                        EPOCH_MAX_ARCHIVE)
        if len(raw) > EPOCH_MAX_ARCHIVE:
            raise FetchError("the archive is larger than %d bytes" % EPOCH_MAX_ARCHIVE)
        files, skipped, eci = read_epoch_archive(raw)
        if not files and not eci:
            raise FetchError("no benchmark file of the archive holds a usable row")
    except FetchError as error:
        return {"status": "error", "date": today, "error": safe_text(error, 120)}
    except Exception as error:
        return {"status": "error", "date": today, "error": "failed: %s" % error.__class__.__name__}
    return {"status": "read", "date": today, "files": files, "skipped": skipped, "eci": eci}


# ------------------------------------------------------------------------------------------------
# Router contracts: what each router is held to, reported and never enforced
# ------------------------------------------------------------------------------------------------

CONTRACTS = ROOT / ".github" / "LiteLLM_router_contracts.yaml"
CONTRACT_STATUSES = ("provisional", "validated")
CONTRACT_CRITERIA = ("intelligence", "first_answer", "code_quality")
CONTRACT_STAND_INS = ("intelligence",)
CONTRACT_REQUIRES = ("tools",)
TOOLS_SUPPORT = ("yes", "no", "unknown")
CONTRACT_FALLBACKS = "router_settings.fallbacks"
# The levels Artificial Analysis names in the suffix of a record, from the one that thinks least to
# the one that thinks most: the level a router keeps for a model is the highest of these that fits.
# "reasoning" stands alone in a family that has no named level, so where it sits does not matter.
LEVEL_ORDER = ("non-reasoning", "minimal", "low", "medium", "reasoning", "high", "xhigh", "max")
LEVEL_UNKNOWN = "unknown"
LEVEL_NOT_APPLICABLE = "n/a"
LEVEL_SUFFIX = re.compile(r"^(?P<base>.*)\((?P<level>[^()]*)\)\s*$")


def seconds_figure(value):
    """A time in seconds, or None: zero or less is no time of a model that answers, and is read as
    not measured, as a speed of zero is."""
    seconds = figure(value)
    return seconds if seconds is not None and seconds > 0 else None


def split_level(name):
    """(family, level) of a record's name: "Gemini 4 Hydrogen (Low)" is ("Gemini 4 Hydrogen", "low").
    A last parenthesis that is no level ("(Sep '25)", "(Low, Default Fallback)") is part of the
    name, and the level is None."""
    match = LEVEL_SUFFIX.match(name)
    if match and match.group("level").strip().lower() in LEVEL_ORDER:
        return match.group("base").strip(), match.group("level").strip().lower()
    return name.strip(), None


def level_rank(level):
    return LEVEL_ORDER.index(level) if level in LEVEL_ORDER else -1


def ranking_families(models):
    """({slug: record}, {family: [records]}) of the ranking's models, a record being the model with
    its "family" and "level". Two records under one slug make it no address, so it is left out."""
    by_slug, twins, families = {}, set(), {}
    for model in models:
        if not model.get("slug"):
            continue
        family, level = split_level(model["name"])
        record = dict(model, family=family, level=level)
        if model["slug"] in by_slug:
            twins.add(model["slug"])
        by_slug[model["slug"]] = record
        families.setdefault(family.lower(), []).append(record)
    return {slug: record for slug, record in by_slug.items() if slug not in twins}, families


def chosen_level(family, min_rate):
    """The record of the level a router keeps for a model: walk up the levels that have an index from
    the lowest, and climb to the next only while each extra second of the time to the first answer
    token buys at least "min_rate" points of index, the first step that buys less being the last. A
    step that buys no points is not taken, a step that is no slower and buys points always is, and a
    step whose time is unknown on either level cannot be judged and is not taken. None when no level
    has an index. A router that values time asks a higher rate, since each level costs time."""
    ranked = sorted((record for record in family if record["intelligence"] is not None),
                    key=lambda record: level_rank(record["level"]))
    if not ranked:
        return None
    kept = ranked[0]
    for record in ranked[1:]:
        points = record["intelligence"] - kept["intelligence"]
        before, after = kept["first_answer"], record["first_answer"]
        if points <= 0 or before is None or after is None:
            break
        seconds = after - before
        if seconds > 0 and points / seconds < min_rate:
            break
        kept = record
    return kept


def describe_entry(mapping, by_slug, families):
    """What the ranking says of one mapped entry: "state" is "no_record" (the file says no record
    describes it), "stale" (its slug is no longer in the ranking) or "resolved", and then "record" is
    the one whose figures are the entry's, "family" its levels, and "unverified" says why those
    figures cannot be taken for the called level: "unknown" (the level is not known and the family
    has several) or "uncovered" (the ranking has the family at other levels only)."""
    if "no_record" in mapping:
        return {"state": "no_record", "why": mapping["no_record"]}
    record = by_slug.get(mapping["slug"])
    if record is None:
        return {"state": "stale", "slug": mapping["slug"]}
    family = families[record["family"].lower()]
    level = mapping["level"]
    found = {"state": "resolved", "record": record, "family": family, "called": level,
             "unverified": None, "unstated": False}
    if level == LEVEL_UNKNOWN:
        if len(family) > 1:
            found["unverified"] = "unknown"
    elif level in LEVEL_ORDER:
        at_level = next((other for other in family if other["level"] == level), None)
        if at_level is not None:
            found["record"] = at_level
        elif len(family) == 1 and family[0]["level"] is None:
            found["unstated"] = True
        else:
            found["unverified"] = "uncovered"
    return found


def floor_figure(value):
    """A floor as the report writes it: one decimal at most, as the figures of the ranking are, since a
    floor converted from the capabilities index has more digits than anything says."""
    return "%g" % round(value, 1)


def effective_intelligence(found, estimate):
    """(figure, estimated) of an entry on the scale of the intelligence index: the index of the record
    at the level the entry is called at when there is one and the entry is not "unverified", and
    otherwise the "estimate" given (an index converted from the capabilities index) flagged as such,
    or none."""
    if found["state"] == "resolved" and not found["unverified"] and found["record"]["intelligence"] is not None:
        return found["record"]["intelligence"], False
    return (estimate, True) if estimate is not None else (None, False)


def entry_verdict(found, floor, last_resort, tools, needs_time, needs_index=True, estimate=None):
    """(kind, text) of one entry against its router's floor, the only bound there is: no time makes a
    member ineligible. A member of the last resort is exempt from the floor; one under it is not
    removed but goes to the last resort tier ("below_floor"). "tools" is what the entry's provider
    declares of tool calls, given only to a router that requires them: "no" excludes the entry, and
    "unknown" is said and excludes nothing. "needs_time" is given to a router ordered by time, where
    a member with no time cannot be placed. "needs_index" is false for such a router that has no
    floor, whose members need no index. "estimate" is the index the capabilities index gives the
    entry, used only where the ranking has no figure for it at the level it is called at, and said."""
    if found["state"] == "unmapped":
        return "unmapped", "sans correspondance"
    if tools == "no":
        return "no_tools", "sans appels d'outils"
    note = " ; appels d'outils inconnus" if tools == "unknown" else ""
    value, estimated = effective_intelligence(found, estimate)
    if value is None:
        if found["state"] == "no_record":
            return "no_record", "sans enregistrement" + note
        if found["state"] == "stale":
            return "stale", "correspondance périmée" + note
        if found["unverified"]:
            return "unverified", "variante non vérifiée" + note
        if needs_index and not last_resort:
            return "unrankable", "inclassable : pas d'indice" + note
    if needs_time and found["record"]["first_answer"] is None:
        return "unrankable", "inclassable : pas de délai" + note
    if not last_resort and floor is not None and value is not None and value < floor:
        return "below_floor", ("sous le plancher (%.1f%s contre %s) : dernier recours"
                               % (value, " estimé" if estimated else "", floor_figure(floor))) + note
    if last_resort:
        return "conforming", "conforme (dernier recours)" + note
    return "conforming", ("conforme (estimé)" if estimated else "conforme") + note


def time_ties(rows, margin):
    """The members in the order of their quality, those whose quality is less than "margin" points
    under the best of their group being ordered by time instead, the shortest first, the current
    order settling what is left. A group starts at the first member that is "margin" points or more
    under the best of the one before; a member with no time comes last in its group."""
    def by_time(row):
        seconds = row["first_answer"]
        return (seconds is None, seconds or 0, row["position"])

    ordered, group = [], []
    for row in rows:
        if group and group[0]["intelligence"] - row["intelligence"] >= margin:
            ordered += sorted(group, key=by_time)
            group = []
        group.append(row)
    return ordered + sorted(group, key=by_time)


def rank_with_ties(scores):
    """{name: rank} for {name: score}: 1 is the highest score, and members with the same score share
    the average of the places they take."""
    ordered = sorted(scores.items(), key=lambda item: -item[1])
    ranks, start = {}, 0
    while start < len(ordered):
        end = start
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[start][1]:
            end += 1
        for name, _ in ordered[start:end + 1]:
            ranks[name] = (start + end) / 2 + 1
        start = end + 1
    return ranks


def epoch_member_scores(mapping, epoch):
    """{benchmark file: best score} of one entry in the files of the archive read: the best of the
    model versions the entry lists for that file. A file the archive does not hold, or a version it
    does not know, gives nothing."""
    listed = mapping.get("epoch") if isinstance(mapping, dict) else None
    found = {}
    for key in EPOCH_KEYS:
        scores = epoch["files"].get(key, {}).get("scores", {})
        best = [scores[version] for version in listed.get(key, ()) if version in scores] \
            if isinstance(listed, dict) else []
        if best:
            found[key] = max(best)
    return found


def code_quality(pool, mappings, epoch):
    """The code quality of each member of "pool" (the names of a cascade), from the archive read:
    {name: {"ranks": {file: (rank, members scored)}, "median", "why"}}. A benchmark file counts only
    if EPOCH_MIN_MEMBERS members of the pool have a score in it, and ranks them (1 is the best, a tie
    shares the average rank). The code quality of a member is the median of its ranks over the files
    that count, and none ("median" is None, "why" says why) below EPOCH_MIN_FILES of them: it is
    unrankable by code quality, which is not the same as a bad one."""
    scores = {name: epoch_member_scores(mappings.get(name), epoch) for name in pool}
    counting = {}
    for key in EPOCH_KEYS:
        scored = {name: found[key] for name, found in scores.items() if key in found}
        if len(scored) >= EPOCH_MIN_MEMBERS:
            counting[key] = (rank_with_ties(scored), len(scored))
    quality = {}
    for name in pool:
        ranks = {key: (counting[key][0][name], counting[key][1]) for key in counting if name in counting[key][0]}
        mapping = mappings.get(name)
        listed = mapping.get("epoch") if isinstance(mapping, dict) else None
        median = statistics.median(rank for rank, _ in ranks.values()) if len(ranks) >= EPOCH_MIN_FILES else None
        why = None
        if median is None:
            why = ("no_ids" if not isinstance(listed, dict) else "no_scores" if not scores[name] else "few_files")
        quality[name] = {"ranks": ranks, "median": median, "why": why, "scored": len(scores[name])}
    return quality


def outside_quality():
    """The code quality of a member the ranking pool does not hold: none."""
    return {"ranks": {}, "median": None, "why": "outside", "scored": 0}


def router_quality(members, base_members, contract, mappings, epoch):
    """The code quality of the members of a router's cascade, or None where the router is not ranked
    on it or the archive was not read. A router that derives from another is ranked as that one is:
    its members get the quality that the cascade of the other one gives them, so that the two orders
    cannot disagree, and a member that cascade does not hold is unrankable ("outside")."""
    if epoch is None or contract["ranking"]["criterion"] != "code_quality":
        return None
    quality = code_quality(list(base_members if base_members is not None else members), mappings, epoch)
    return {name: quality.get(name) or outside_quality() for name in members}


def quality_key(row):
    """What orders members of the same code quality: the shorter time to the first answer token, a
    member with none last, then the position the cascade has now."""
    seconds = row["first_answer"]
    return (row["quality"]["median"], seconds is None, seconds or 0, row["position"])


def contract_order(rows, ranking):
    """The order a router's contract would give: the members that conform, then the last resort tier
    in the order it has now (the members the contract declares exempt and those under the floor). A
    router ordered by time puts the shortest first; any other puts the best quality first, time
    breaking a tie between members less than the router's margin apart. Code quality is the median
    rank of the members the archive of Epoch AI ranks, best first, and the others (unrankable by it)
    follow them in the order of the intelligence index that stands in for it; without the archive the
    intelligence index orders them all. A member that cannot be judged is not placed."""
    main = [row for row in rows if row["kind"] == "conforming" and not row["last_resort"]]
    tail = [row["name"] for row in rows if row["last_resort"] or row["kind"] == "below_floor"]
    if ranking["criterion"] == "first_answer":
        return [row["name"] for row in sorted(
            main, key=lambda row: (row["record"]["first_answer"], row["position"]))] + tail
    ranked = []
    if ranking["criterion"] == "code_quality" and any(row.get("quality") for row in rows):
        ranked = sorted((row for row in main if row["quality"]["median"] is not None), key=quality_key)
        main = [row for row in main if row["quality"]["median"] is None]
    main.sort(key=lambda row: (-row["intelligence"], row["position"]))
    return ([row["name"] for row in ranked] + [row["name"] for row in time_ties(main, ranking["tie_margin_points"])]
            + tail)


def effective_contract(routers, name):
    """The contract a router is held to: its own, or for a router that derives from another, that
    one's, with what the derived router requires."""
    contract = routers[name]
    if "derives_from" not in contract:
        return contract
    return dict(routers[contract["derives_from"]], derives_from=contract["derives_from"],
                requires=contract["requires"], reason=contract["reason"])


def eci_to_index(eci, points):
    """The capabilities index "eci" on the scale of the intelligence index, by the piecewise linear
    line through "points" ([capabilities index, intelligence index] pairs, going up). Beyond either end
    the slope of the end segment goes on, since the calibration holds no model there and a constant
    would make every model past the end of the points tie; it is clamped at 0, since an index is not
    negative and the lowest segment runs down through it. None when there are fewer than two points.
    Every figure it gives is an estimate, whatever the calibration."""
    if len(points) < 2:
        return None
    first, last = points[0], points[-1]
    if eci <= first[0]:
        low, high = points[0], points[1]
    elif eci >= last[0]:
        low, high = points[-2], points[-1]
    else:
        low, high = next((low, high) for low, high in zip(points, points[1:]) if low[0] <= eci <= high[0])
    return max(0.0, low[1] + (eci - low[0]) * (high[1] - low[1]) / (high[0] - low[0]))


def eci_scale(epoch, contracts):
    """{"eci": {display name: index}, "points": [...]}, what turns a capabilities index into an
    estimated intelligence index, or None when the archive was not read, it holds no capabilities index,
    or the contracts declare no calibration to convert it by."""
    eci = epoch.get("eci") if epoch and epoch.get("status") == "read" else None
    block = contracts.get("fallback_index")
    points = block.get("points") if isinstance(block, dict) else None
    if not eci or not isinstance(points, list) or len(points) < 2 or any(
            not isinstance(point, list) or len(point) != 2 or any(figure(item) is None for item in point)
            for point in points):
        return None
    return {"eci": eci, "points": [(float(low), float(high)) for low, high in points]}


def anchor_floor(anchor, mappings, by_slug, families, scale=None):
    """(value, text) of a floor anchor: the index of the record of the entry it names, or, with a
    "level", the index of that level of the entry's family; or, for an anchor that names an "epoch"
    model, its capabilities index converted to the scale of the index, and said estimated. (None, why)
    when the entry has no mapping, its record or the level is not in the ranking, or the record has no
    index, or the model is not in the capabilities index read, or it was not read: a floor that cannot
    be read judges nothing, and the report says so."""
    if "epoch" in anchor:
        text = "%s (Epoch, estimé)" % safe_text(anchor["epoch"], 60)
        if scale is None:
            return None, "%s : indice de capacités non lu" % text
        eci = scale["eci"].get(anchor["epoch"])
        if eci is None:
            return None, "%s : absent de l'indice de capacités" % text
        return eci_to_index(eci, scale["points"]), text
    entry = safe_text(anchor["entry"], 60)
    mapping = mappings.get(anchor["entry"])
    if not mapping or "slug" not in mapping:
        return None, "%s : aucun enregistrement associé" % entry
    record = by_slug.get(mapping["slug"])
    if record is None:
        return None, "%s : enregistrement introuvable" % entry
    level = anchor.get("level")
    if level:
        record = next((item for item in families[record["family"].lower()] if item["level"] == level), None)
        if record is None:
            return None, "%s : pas de niveau %s" % (entry, safe_text(level, 20))
    if record["intelligence"] is None:
        return None, "%s : pas d'indice" % safe_text(record["name"], 80)
    return record["intelligence"], safe_text(record["name"], 80)


def resolved_contract(contract, mappings, by_slug, families, scale=None):
    """The contract with the anchors of its floor read: the floor gets a "value" and a "text" (the
    record it is the index of), and its "candidates" become the numbers of the anchors that could be
    read, "candidate_texts" naming them. A floor that cannot be read has no value (None), and a router
    that says it has no floor ("none") has no value, no text and no candidate."""
    block = contract["intelligence_floor"]
    if block.get("none"):
        return dict(contract, intelligence_floor=dict(block, value=None, text=None, candidates=[], candidate_texts=[]))
    value, text = anchor_floor(block["anchor"], mappings, by_slug, families, scale)
    read = [anchor_floor(anchor, mappings, by_slug, families, scale) for anchor in block.get("candidates") or []]
    return dict(contract, intelligence_floor=dict(
        block, value=value, text=text,
        candidates=[item[0] for item in read if item[0] is not None],
        candidate_texts=[item[1] for item in read if item[0] is not None]))


def floor_text(block):
    """The floor of a resolved contract, as the report says it."""
    if block.get("none"):
        return "aucun"
    if block["value"] is None:
        return "introuvable (%s), aucun membre n'est jugé sous le plancher" % block["text"]
    return "%s (%s)" % (floor_figure(block["value"]), block["text"])


def router_rows(members, contract, mappings, by_slug, families, floor=None, quality=None, scale=None):
    """One row per member of a cascade against its router's contract, at the floor given or the
    contract's own. "quality" is the code quality of the members (see router_quality), or None. "scale"
    is what converts a capabilities index (see eci_scale), or None: a member the ranking has no index
    for at the level it is called at is then placed on the estimate its entry's "eci" gives, which a
    router ordered by time never uses, since its time comes from the ranking."""
    rate = contract["level_gain"]["min_points_per_second"]
    block = contract["intelligence_floor"]
    floor = block["value"] if floor is None else floor
    needs_time = contract["ranking"]["criterion"] == "first_answer"
    needs_index = not (needs_time and block.get("none"))
    rows = []
    for position, name in enumerate(members):
        mapping = mappings.get(name)
        found = describe_entry(mapping, by_slug, families) if mapping else {"state": "unmapped"}
        last_resort = name in contract["last_resort"]["members"]
        tools = mapping["tools"]["support"] if mapping else "unknown"
        eci = scale["eci"].get(mapping.get("eci")) if scale and mapping and not needs_time else None
        estimate = eci_to_index(eci, scale["points"]) if eci is not None else None
        kind, text = entry_verdict(found, floor, last_resort,
                                   tools if "tools" in contract.get("requires", ()) else None,
                                   needs_time, needs_index, estimate)
        value, estimated = effective_intelligence(found, estimate)
        record = found.get("record")
        rows.append({"name": name, "position": position, "found": found, "kind": kind,
                     "verdict": text, "last_resort": last_resort, "tools": tools,
                     "record": record, "quality": quality.get(name) if quality else None,
                     "intelligence": value, "estimated": estimated,
                     "first_answer": record["first_answer"] if record is not None and not estimated else None,
                     "kept": chosen_level(found["family"], rate) if found["state"] == "resolved" else None})
    return rows


def floor_effects(members, contract, mappings, by_slug, families, quality=None, scale=None):
    """What each floor the contract proposes to compare does to a cascade: who stays in front and who
    goes to the last resort tier. Who is not placed at all does not depend on the floor."""
    effects = []
    block = contract["intelligence_floor"]
    compared = list(zip(block.get("candidates") or [], block.get("candidate_texts") or []))
    for floor, anchor_name in compared or ([(block["value"], block["text"])] if block["value"] is not None else []):
        rows = router_rows(members, contract, mappings, by_slug, families, floor, quality, scale)
        placed = contract_order(rows, contract["ranking"])
        tail = [row["name"] for row in rows if row["last_resort"] or row["kind"] == "below_floor"]
        effects.append({"floor": floor, "text": anchor_name, "main": [name for name in placed if name not in tail], "last": tail})
    return effects


def derivation_differences(base, derived, tools):
    """How a derived cascade differs from the one it must be: the cascade it derives from without the
    members whose tool support is refused, in the same order. "tools" is {name: "yes" | "no" |
    "unknown"}. A member whose support is unknown is neither required nor refused, and is listed."""
    kept = [name for name in base if tools.get(name, "unknown") != "no"]
    common = [name for name in derived if name in base]
    return {
        "extra": [name for name in derived if name not in base],
        "refused": [name for name in derived if tools.get(name, "unknown") == "no"],
        "missing": [name for name in base if tools.get(name, "unknown") == "yes" and name not in derived],
        "unordered": common != [name for name in kept if name in derived],
        "unknown": [name for name in base if tools.get(name, "unknown") == "unknown"],
    }


def epoch_state(epoch):
    """What the report says of the archive of Epoch AI: {"status": "read" | "error" | "unread", ...}.
    "unread" is a run that did not try, and "error" one that failed, with the kind of failure."""
    if not epoch:
        return {"status": "unread"}
    if epoch["status"] != "read":
        return {"status": "error", "date": epoch["date"], "error": epoch["error"]}
    return {"status": "read", "date": epoch["date"], "skipped": dict(epoch["skipped"]),
            "eci": len(epoch.get("eci") or {}),
            "files": {key: dict(rows=data["rows"], bad=data["bad"]) for key, data in epoch["files"].items()}}


def stale_eci_names(contracts, scale):
    """The capabilities index names the contracts keep and the archive read no longer holds, as
    (entry, name), the entry being "" for a name only a floor anchor holds: information for a person to
    correct, as for a name the template lost. Nothing is stale until the index was read."""
    if scale is None:
        return []
    found = [(name, mapping["eci"]) for name, mapping in contracts["models"].items()
             if isinstance(mapping, dict) and isinstance(mapping.get("eci"), str) and mapping["eci"] not in scale["eci"]]
    anchors = {anchor["epoch"] for _, anchor in contract_anchors(contracts["routers"])
               if isinstance(anchor, dict) and isinstance(anchor.get("epoch"), str)}
    return found + [("", name) for name in sorted(anchors) if name not in scale["eci"]]


def contracts_report(template, ranking, contracts, epoch=None):
    """What the contracts say of the cascades as they stand, from the ranking as it was read, and from
    the archive of Epoch AI where it was read ("epoch", see read_epoch):
    {"status": "computed", "routers": [...], "unmapped": [...], ...}. A pure reading, it changes
    nothing and judges nothing: every violation in it is information."""
    archive = epoch if epoch and epoch["status"] == "read" else None
    lists = fallback_lists(template["document"])
    names = [entry["name"] for entry in template["active"] if isinstance(entry["name"], str)]
    mappings = contracts["models"]
    by_slug, families = ranking_families(ranking["models"])
    tools = {name: mapping["tools"]["support"] for name, mapping in mappings.items()}
    scale = eci_scale(archive, contracts)
    routers = []
    for router, _ in RANKING_ROUTERS:
        members = lists.get((CONTRACT_FALLBACKS, router))
        if members is None or router not in contracts["routers"]:
            continue
        contract = resolved_contract(effective_contract(contracts["routers"], router), mappings, by_slug, families, scale)
        base = contract.get("derives_from")
        quality = router_quality(members, lists.get((CONTRACT_FALLBACKS, base)) if base else None,
                                 contract, mappings, archive)
        rows = router_rows(members, contract, mappings, by_slug, families, quality=quality, scale=scale)
        routers.append({
            "name": router, "contract": contract, "rows": rows, "current": list(members),
            "proposed": contract_order(rows, contract["ranking"]),
            "floors": floor_effects(members, contract, mappings, by_slug, families, quality, scale),
            "base": base, "quality": quality,
            "differences": derivation_differences(lists.get((CONTRACT_FALLBACKS, base), []), members, tools)
            if base else None})
    described = {name: describe_entry(mappings[name], by_slug, families) for name in names
                 if name in mappings}
    version, wanted = ranking.get("index_version"), figure(contracts.get("index_version"))
    return {
        "status": "computed", "routers": routers, "date": ranking["date"], "epoch": epoch_state(epoch),
        "unmapped": [name for name in names if name not in mappings],
        "no_record": [name for name in names if described.get(name, {}).get("state") == "no_record"],
        "stale": [(name, found["slug"]) for name, found in described.items() if found["state"] == "stale"],
        "absent": absent_names(contracts, template),
        "eci_stale": stale_eci_names(contracts, scale),
        "uncovered": [(name, found) for name, found in described.items()
                      if found["state"] == "resolved" and found["unverified"] == "uncovered"],
        "provisional": contracts.get("status") != "validated",
        "fallback": contracts.get("fallback_index"),
        "version": version, "wanted_version": wanted,
    }


def contract_block_problems(block, where, problems):
    """The block of a value and its reason, or None, adding what is wrong with it to "problems"."""
    if not isinstance(block, dict):
        problems.append('%s is missing or is not a mapping of a value and its "reason"' % where)
        return None
    reason = block.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        problems.append('%s has no "reason": every value says why it is what it is' % where)
    return block


def contracts_problems(contracts, template):
    """The structural problems of a contracts document against the template it is read with: a router
    that does not exist or has no contract, a number that is not a number, a value with no reason, a
    mapping with fields that are wrong. Only the shape is judged, never a figure. A name that is no
    entry of the template any more is no problem, since a deletion leaves it behind: see
    absent_names."""
    problems = []
    if not isinstance(contracts, dict):
        return ["the router contracts file is not a mapping"]
    lists = fallback_lists(template["document"])
    if contracts.get("status") not in CONTRACT_STATUSES:
        problems.append('"status" must be one of %s' % ", ".join(CONTRACT_STATUSES))
    if figure(contracts.get("index_version")) is None:
        problems.append('"index_version" must be a number: the floors are on one version of the index')
    routers = contracts.get("routers")
    if not isinstance(routers, dict):
        problems.append('"routers" is missing or is not a mapping')
        routers = {}
    for router in routers:
        if (CONTRACT_FALLBACKS, router) not in lists:
            problems.append('the contract of "%s" is that of no router: the template has no cascade of '
                            "that name" % router)
    for router, _ in RANKING_ROUTERS:
        if router not in routers:
            problems.append('the router "%s" has no contract' % router)
    for router, contract in routers.items():
        where = 'router "%s"' % router
        if not isinstance(contract, dict):
            problems.append("%s is not a mapping" % where)
        elif "derives_from" in contract:
            base = routers.get(contract["derives_from"])
            if not isinstance(base, dict) or "derives_from" in base or contract["derives_from"] == router:
                problems.append('%s derives from "%s", which is no router with a contract of its own'
                                % (where, contract["derives_from"]))
            requires = contract.get("requires")
            if not isinstance(requires, list) or any(item not in CONTRACT_REQUIRES for item in requires):
                problems.append('%s must list what it "requires" among: %s' % (where, ", ".join(CONTRACT_REQUIRES)))
            contract_block_problems(contract, where, problems)
        else:
            full_contract_problems(contract, where, problems)
    mappings = contracts.get("models")
    if not isinstance(mappings, dict):
        problems.append('"models" is missing or is not a mapping')
        mappings = {}
    for name, mapping in mappings.items():
        mapping_problems(name, mapping, problems)
    for where, anchor in contract_anchors(routers):
        anchor_problems(anchor, where, problems)
        if isinstance(anchor, dict) and isinstance(anchor.get("entry"), str) and anchor["entry"] not in mappings:
            problems.append('%s names "%s", which "models" does not map' % (where, anchor["entry"]))
    inputs = contracts.get("inputs")
    if inputs is not None and not isinstance(inputs, dict):
        problems.append('"inputs" is not a mapping')
    if contracts.get("fallback_index") is not None:
        fallback_problems(contracts["fallback_index"], problems)
    elif any(isinstance(mapping, dict) and "eci" in mapping for mapping in mappings.values()) or any(
            isinstance(anchor, dict) and "epoch" in anchor for _, anchor in contract_anchors(routers)):
        problems.append('the capabilities index is used ("eci" in a mapping, or an "epoch" anchor) and the file '
                        'declares no "fallback_index" calibration to convert it by')
    return problems


def fallback_problems(block, problems):
    """The shape of the declared fallback for the general intelligence of a member with no index: where
    it comes from, whether it is read, how it was calibrated and how uncertain it is, and the points of
    the calibration, which only ever go up."""
    if not isinstance(block, dict):
        problems.append('"fallback_index" is not a mapping')
        return
    for key in ("source", "status", "method", "uncertainty"):
        if not isinstance(block.get(key), str) or not block[key].strip():
            problems.append('"fallback_index" has no "%s", in words' % key)
    points = block.get("points")
    if (not isinstance(points, list) or len(points) < 2
            or any(not isinstance(point, list) or len(point) != 2 or any(figure(item) is None for item in point)
                   for point in points)):
        problems.append('"fallback_index" must list its calibration "points" as pairs of numbers, two at least')
    elif any(later[0] <= earlier[0] or later[1] < earlier[1] for earlier, later in zip(points, points[1:])):
        problems.append('"fallback_index" has calibration "points" that do not go up with the source figure')


def anchor_problems(anchor, where, problems):
    """The shape of a floor anchor: the "entry" it is read from, and optionally the "level" of that
    entry's family to take, or an "epoch" model, named as the capabilities index names it, and then
    no level. Exactly one of the two is named."""
    if isinstance(anchor, dict) and "entry" in anchor and "epoch" in anchor:
        problems.append('%s names both an "entry" and an "epoch" model: exactly one' % where)
    elif isinstance(anchor, dict) and "epoch" in anchor:
        if not isinstance(anchor["epoch"], str) or not anchor["epoch"].strip():
            problems.append('%s has an "epoch" that is no model name of the capabilities index' % where)
        elif "level" in anchor:
            problems.append('%s names an "epoch" model, which has no "level"' % where)
    elif not isinstance(anchor, dict) or not isinstance(anchor.get("entry"), str) or not anchor["entry"].strip():
        problems.append('%s must be a mapping that names an "entry" or an "epoch" model' % where)
    elif "level" in anchor and anchor["level"] not in LEVEL_ORDER:
        problems.append('%s has a "level" that is none of: %s' % (where, ", ".join(LEVEL_ORDER)))


def contract_anchors(routers):
    """Every anchor of the contracts of "routers" (a mapping), as (where, anchor). A router with no
    floor ("none") has none."""
    found = []
    for router, contract in routers.items():
        block = contract.get("intelligence_floor") if isinstance(contract, dict) else None
        if isinstance(block, dict) and not block.get("none"):
            found.append(('router "%s", "intelligence_floor", "anchor"' % router, block.get("anchor")))
            candidates = block.get("candidates")
            for number, anchor in enumerate(candidates if isinstance(candidates, list) else []):
                found.append(('router "%s", "intelligence_floor", candidate %d' % (router, number + 1), anchor))
    return found


def full_contract_problems(contract, where, problems):
    block = contract_block_problems(contract.get("level_gain"), '%s, "level_gain",' % where, problems)
    if block is not None:
        value = figure(block.get("min_points_per_second"))
        if value is None or value < 0:
            problems.append('%s, "level_gain", has a "min_points_per_second" that is not a number from 0 up' % where)
    block = contract_block_problems(contract.get("intelligence_floor"), '%s, "intelligence_floor",' % where, problems)
    if block is not None and "none" in block:
        if block["none"] is not True:
            problems.append('%s, "intelligence_floor", has a "none" that is not true: a router with a floor says '
                            "no such thing" % where)
        elif "anchor" in block or "candidates" in block:
            problems.append('%s, "intelligence_floor", says "none" and so names no "anchor" and no "candidates"' % where)
    elif block is not None:
        candidates = block.get("candidates")
        if candidates is not None and not isinstance(candidates, list):
            problems.append('%s, "intelligence_floor", must list its "candidates" as anchors' % where)
    block = contract_block_problems(contract.get("ranking"), '%s, "ranking",' % where, problems)
    if block is not None:
        if block.get("criterion") not in CONTRACT_CRITERIA:
            problems.append('%s, "ranking", must have a "criterion" among: %s'
                            % (where, ", ".join(CONTRACT_CRITERIA)))
        elif block["criterion"] != "first_answer" and (
                figure(block.get("tie_margin_points")) is None or block["tie_margin_points"] < 0):
            problems.append('%s, "ranking", must have a "tie_margin_points" that is a number from 0 up' % where)
        elif block["criterion"] == "code_quality" and (
                block.get("stand_in") not in CONTRACT_STAND_INS
                or any(not isinstance(block.get(key), str) or not block[key].strip()
                       for key in ("source", "source_status"))):
            problems.append('%s, "ranking", on "code_quality" must say its "source", its "source_status" and '
                            'a "stand_in" among: %s' % (where, ", ".join(CONTRACT_STAND_INS)))
    block = contract_block_problems(contract.get("last_resort"), '%s, "last_resort",' % where, problems)
    if block is not None:
        members = block.get("members")
        if not isinstance(members, list):
            problems.append('%s, "last_resort", must list its "members"' % where)
        else:
            if any(not isinstance(name, str) for name in members):
                problems.append('%s, "last_resort", must list its "members" by name' % where)


def mapping_problems(name, mapping, problems):
    where = 'the mapping of "%s"' % name
    if not isinstance(mapping, dict):
        problems.append("%s is not a mapping" % where)
        return
    tools = mapping.get("tools")
    if (not isinstance(tools, dict) or tools.get("support") not in TOOLS_SUPPORT
            or not isinstance(tools.get("source"), str) or not tools["source"].strip()):
        problems.append('%s has no "tools" saying "yes", "no" or "unknown" and its source' % where)
    epoch = mapping.get("epoch", "unknown")
    if epoch != "unknown" and (not isinstance(epoch, dict) or not epoch or any(
            not isinstance(ids, list) or not ids or any(not isinstance(item, str) or not item.strip()
                                                        for item in ids) for ids in epoch.values())):
        problems.append('%s has an "epoch" that is neither "unknown" nor benchmark files and their model ids'
                        % where)
    elif isinstance(epoch, dict) and any(key not in EPOCH_KEYS for key in epoch):
        problems.append('%s has an "epoch" on a benchmark file that is not read: only %s are'
                        % (where, ", ".join(EPOCH_KEYS)))
    if "eci" in mapping and (not isinstance(mapping["eci"], str) or not mapping["eci"].strip()):
        problems.append('%s has an "eci" that is no model name of the capabilities index: a display name, spelt as '
                        "the index has it" % where)
    if "no_record" in mapping:
        if "slug" in mapping or not isinstance(mapping["no_record"], str) or not mapping["no_record"].strip():
            problems.append('%s has "no_record" and so says why in it, in words, and names no "slug"' % where)
        return
    slug = mapping.get("slug")
    if not isinstance(slug, str) or not SAFE_ID.fullmatch(slug):
        problems.append('%s has no "slug" spelt like one' % where)
    if mapping.get("level") not in LEVEL_ORDER + (LEVEL_UNKNOWN, LEVEL_NOT_APPLICABLE):
        problems.append('%s has a "level" that is none of: %s' % (
            where, ", ".join(LEVEL_ORDER + (LEVEL_UNKNOWN, LEVEL_NOT_APPLICABLE))))
    source = mapping.get("level_source")
    if not isinstance(source, str) or not source.strip():
        problems.append('%s has no "level_source": the page that gives the level, or "unknown"' % where)


class UniqueKeyLoader(yaml.SafeLoader):
    """A loader that refuses a key written twice in a mapping, which PyYAML would otherwise let the
    second one silently replace."""

    def construct_mapping(self, node, deep=False):
        keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
        for key in keys:
            if keys.count(key) > 1:
                raise yaml.constructor.ConstructorError(None, None, "a key is written twice", node.start_mark)
        return super().construct_mapping(node, deep=deep)


def load_contracts(path):
    """(document, problems): the contracts file parsed, or why it could not be."""
    try:
        return yaml.load(Path(path).read_text(encoding="utf-8"), Loader=UniqueKeyLoader), []
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        return None, ["the router contracts file cannot be read (%s)" % error.__class__.__name__]


def contracts_file_for(arguments):
    """The contracts file this run reads: the one of the repository when the template read is the
    repository's own, none for another template unless one is given, since a contract written for
    one template means nothing against another."""
    if arguments.contracts:
        return Path(arguments.contracts)
    return CONTRACTS if Path(arguments.config).resolve() == CONFIG.resolve() else None


def absent_names(contracts, template):
    """The names the contracts keep that are no active entry of the template any more, as (where,
    name): "models" for a mapping, a router's name for a member of its last resort. A deletion
    leaves them behind, and the plain run must stay green for it, so they are reported as stale and
    never refused."""
    active = {entry["name"] for entry in template["active"] if isinstance(entry["name"], str)}
    found = [("models", name) for name in contracts["models"] if name not in active]
    for router, contract in contracts["routers"].items():
        found += [(router, name) for name in contract.get("last_resort", {}).get("members", [])
                  if name not in active]
    return found


def offline_contract_notices(text, path):
    """One line per stale name of the contracts file at "path" against the template in "text", for
    the plain run to print: an information, never a failure. None while the file has a problem."""
    template, _ = read_template(text)
    if template is None:
        return []
    document, problems = load_contracts(path)
    if problems or contracts_problems(document, template):
        return []
    return ['Router contracts: "%s" (%s) is no entry of the template any more: a stale mapping, its '
            "row is to be removed from %s." % (name, "mapping" if where == "models" else "last resort of %s" % where,
                                              Path(path).name) for where, name in absent_names(document, template)]


def offline_contract_problems(text, path):
    """The structural problems of the contracts file at "path", read against the template in
    "text": what the offline run fails on, and all that it does."""
    template, _ = read_template(text)
    if template is None:
        return []
    document, problems = load_contracts(path)
    return problems or contracts_problems(document, template)


def router_contracts(text, result, path):
    """The contracts' reading of the cascades for the issue, or None where there is nothing to say
    (no path, or the ranking was not read). It never raises and never changes the run: a file that
    is wrong says so in the issue, and so does a computation that failed, by the kind of error."""
    ranking = result.get("rankings")
    if path is None or not ranking or ranking["status"] != "read":
        return None
    try:
        template, _ = read_template(text)
        document, problems = load_contracts(path)
        problems = problems or contracts_problems(document, template)
        if problems:
            return {"status": "invalid", "problems": problems}
        return contracts_report(template, ranking, document, result.get("epoch"))
    except Exception as error:
        return {"status": "error", "kind": error.__class__.__name__}


def level_text(record):
    return record["level"] if record["level"] else "niveau unique"


def contract_cells(row):
    """The cells of a member's row in the issue: the record, the level called, its figures, the level
    the router would keep, and the verdict."""
    found, record = row["found"], row["record"]
    name = "`%s`%s" % (safe_text(row["name"], 60), " (dernier recours)" if row["last_resort"] else "")
    if record is None:
        return [name, "—", "—", "%s (estimé)" % figure_text(row["intelligence"]) if row["estimated"] else "—",
                "—", "—", "—", row["verdict"]]
    kept = row["kept"]
    if kept is None:
        kept_text = "aucun niveau n'a d'indice"
    else:
        kept_text = "%s (indice %s%s)" % (
            level_text(kept), figure_text(kept["intelligence"]),
            "" if kept["first_answer"] is None else ", %s s" % figure_text(kept["first_answer"]))
    called = found["called"] if found["called"] != LEVEL_NOT_APPLICABLE else "sans niveau"
    return [name, safe_text(record["name"], 80), "inconnu" if called == LEVEL_UNKNOWN else called,
            "%s (estimé)" % figure_text(row["intelligence"]) if row["estimated"] else figure_text(record["intelligence"]),
            figure_text(record["first_answer"]), figure_text(record["speed"]), kept_text, row["verdict"]]


def names_text(names):
    return ", ".join("`%s`" % safe_text(name, 60) for name in names) or "—"


def epoch_status_text(epoch):
    """The state of the archive of Epoch AI in a sentence: what this run read, never what the
    contracts file declares."""
    if epoch["status"] == "read":
        return "lue le %s" % epoch["date"]
    return "non lue" + (" (%s)" % safe_text(epoch["error"], 120) if epoch["status"] == "error" else "")


def ranking_text(contract, epoch):
    ranking = contract["ranking"]
    if ranking["criterion"] == "first_answer":
        return "le délai le plus court"
    margin = ", le délai départageant deux membres à moins de %g points d'écart" % ranking["tie_margin_points"]
    if ranking["criterion"] != "code_quality":
        return "l'indice d'intelligence" + margin
    source = "source : %s, %s" % (safe_text(ranking["source"], 200), epoch_status_text(epoch))
    if epoch["status"] == "read":
        return ("la qualité de code (%s), la médiane des rangs sur les benchmarks, le délai départageant deux "
                "membres à égalité ; les membres que cette source ne permet pas de classer suivent, ordonnés "
                "sur l'indice d'intelligence%s" % (source, margin))
    return ("la qualité de code (%s) ; Artificial Analysis n'a pas d'indice de code, l'indice d'intelligence "
            "en tient lieu à titre provisoire%s" % (source, margin))


def derivation_lines(router):
    """What the derived router's cascade is, against the one it must be."""
    base, differences = router["base"], router["differences"]
    unknown = differences["unknown"]
    out = []
    for key, text in (("extra", "dans `%s` mais pas dans `%s`" % (router["name"], base)),
                      ("refused", "sans appels d'outils déclarés, pourtant dans `%s`" % router["name"]),
                      ("missing", "avec appels d'outils, dans `%s` mais pas dans `%s`" % (base, router["name"]))):
        if differences[key]:
            out.append("- %s : %s" % (text, names_text(differences[key])))
    if differences["unordered"]:
        out.append("- l'ordre des membres communs n'est pas celui de `%s`" % base)
    if unknown:
        out.append("- appels d'outils inconnus (ni exigés ni refusés, à vérifier) : %s" % names_text(unknown))
    same = not (differences["extra"] or differences["refused"] or differences["missing"] or differences["unordered"])
    return ["La cascade de `%s` %s la cascade de `%s` sans les membres sans outils, dans le même ordre."
            % (router["name"], "est" if same else "n'est **pas**", base), ""] + out + ([""] if out else [])


def rank_text(rank, of):
    return "%g/%d" % (rank, of)


def quality_lines(router, epoch):
    """The code quality of a router's members, in French: the rank of each in each benchmark of the
    archive of Epoch AI, the median, the position it gives, and which members are unrankable by it, why,
    and that they follow the others on the intelligence index."""
    quality = router["quality"]
    if quality is None:
        return []
    base, by_name = router["base"], {row["name"]: row for row in router["rows"]}
    kept = [name for name in router["proposed"] if by_name[name]["kind"] == "conforming"
            and not by_name[name]["last_resort"] and quality[name]["median"] is not None]
    out = ["Qualité de code, d'après %s (<%s>, archive lue le %s). Chaque benchmark classe les membres de la "
           "cascade%s qui y ont un score (1 est le meilleur, les égalités partagent le rang moyen, « 2/5 » est le "
           "deuxième de 5) et ne compte que si deux membres au moins y ont un score ; la qualité de code d'un "
           "membre est la médiane de ses rangs, sur deux benchmarks au moins. WebDev Arena et toute arène de "
           "design ou d'interface ne sont pas lues."
           % (EPOCH_ATTRIBUTION, EPOCH_SITE, epoch["date"], " de `%s`" % base if base else ""), "",
           "| Membre | %s | Médiane | Position |" % " | ".join(label for _, label, _ in EPOCH_FILES),
           "| %s |" % " | ".join(["---"] * (len(EPOCH_FILES) + 3))]
    for row in router["rows"]:
        found = quality[row["name"]]
        if row["name"] in kept:
            position = str(kept.index(row["name"]) + 1)
        elif row["kind"] == "conforming" and not row["last_resort"]:
            position = "inclassable : indice d'intelligence"
        elif row["last_resort"]:
            position = "dernier recours"
        else:
            position = "sous le plancher" if row["kind"] == "below_floor" else row["verdict"]
        out.append("| `%s` | %s | %s | %s |" % (
            safe_text(row["name"], 60),
            " | ".join(rank_text(*found["ranks"][key]) if key in found["ranks"] else "—" for key in EPOCH_KEYS),
            "—" if found["median"] is None else "%g" % found["median"], position))
    counting = {key for found in quality.values() for key in found["ranks"]}
    useless = [label for key, label, _ in EPOCH_FILES if key in epoch["files"] and key not in counting]
    unread = ["%s (`%s`)" % (label, safe_text(epoch["skipped"][key], 80))
              for key, label, _ in EPOCH_FILES if key in epoch["skipped"]]
    why = {"no_ids": "aucun identifiant Epoch connu", "no_scores": "aucun score dans l'archive pour ses identifiants",
           "outside": "hors de la cascade de `%s`" % safe_text(base or "", 20)}
    unranked = ["`%s` (%s)" % (safe_text(row["name"], 60), why.get(quality[row["name"]]["why"]) or
                               "%d benchmark(s) comptant(s) pour lui, %d requis" % (
                                   len(quality[row["name"]]["ranks"]), EPOCH_MIN_FILES))
                for row in router["rows"] if row["kind"] == "conforming" and not row["last_resort"]
                and quality[row["name"]]["median"] is None]
    out.append("")
    if useless:
        out += ["Benchmarks sans effet sur cette cascade (moins de deux membres y ont un score) : %s." % ", ".join(useless), ""]
    if unread:
        out += ["Fichiers de l'archive non lus : %s." % ", ".join(unread), ""]
    if unranked:
        out += ["Inclassables par la qualité de code, placés après les membres classés et ordonnés sur l'indice "
                "d'intelligence qui en tient lieu : %s." % ", ".join(unranked), ""]
    return out


def contracts_section(result):
    """The section "Contrats par routeur" of the weekly issue, in French: one table per router, the
    order the contract would give against the current one, the floors side by side, and what the
    mapping does not cover. A report, whose every violation is information."""
    report = result.get("contracts")
    if not report:
        return []
    out = ["## Contrats par routeur", ""]
    if report["status"] == "invalid":
        out += ["Le fichier `.github/LiteLLM_router_contracts.yaml` n'a pas la forme attendue, rien n'est "
                "calculé cette semaine :", ""]
        return out + capped(["- " + " ".join(problem.split()) for problem in report["problems"]]) + [""]
    if report["status"] == "error":
        return out + ["Le calcul a échoué (%s) : rien n'est calculé cette semaine, et rien d'autre n'en "
                      "dépend." % code_span(report["kind"]), ""]
    fallback, epoch = report["fallback"], report["epoch"]
    estimating = epoch["status"] == "read" and epoch["eci"] > 0
    out += ["Les cascades lues contre `.github/LiteLLM_router_contracts.yaml`, d'après les chiffres "
            "d'Artificial Analysis lus le %s (<%s>)%s. **C'est un rapport** : rien ne change une cascade, une "
            "entrée ni une ligne `head`, et un écart n'est qu'une information : un membre dit inclassable ou "
            "sous le plancher n'est retiré d'aucune cascade. Aucun délai ne rend un membre inéligible : la "
            "seule borne est le plancher d'intelligence (et les appels d'outils pour `claude-code`), le délai "
            "moyen avant le premier jeton de la réponse ne sert qu'à ordonner. Le niveau retenu pour un "
            "modèle s'obtient en montant de niveau tant que chaque seconde de plus avant la première réponse "
            "rapporte au moins le nombre de points d'indice que le routeur demande. Un membre sous le plancher "
            "passe au dernier recours. L'échelle "
            "d'intelligence est comprimée dans le bas, où deux points séparent des modèles qu'on ne mettrait "
            "pas dans la même classe, et la plupart des enregistrements n'ont aucun indice : %s."
            % (report["date"], RANKING_SITE,
               "" if not report["provisional"] else " ; les contrats sont **provisoires** jusqu'à validation "
               "du mainteneur",
               "un membre qui n'en a pas au niveau où il est appelé est placé sur une estimation tirée de "
               "l'indice de capacités d'Epoch AI quand celui-ci le couvre, et signalé inclassable sinon "
               "(il reste alors où il est)" if estimating else
               "ces membres restent où ils sont, signalés inclassables%s" % (
                   "" if not fallback else ", tant que l'indice de repli (%s) n'est pas lu"
                   % safe_text(fallback["source"], 80))), ""]
    if estimating:
        out += ["Indice de capacités d'Epoch AI (ECI), lu le %s dans la même archive : %s (<%s>). Il est converti à "
                "l'échelle de l'indice d'intelligence par les points de calibration du fichier, une droite par "
                "morceaux prolongée au-delà de ses extrémités par la pente du dernier segment et bornée à 0 : "
                "tout chiffre ainsi obtenu est une **estimation**, marquée « estimé » partout où il sert, soit "
                "pour un plancher qui nomme un modèle d'Epoch AI, soit pour placer un membre qui n'a pas d'indice "
                "au niveau où il est appelé (le niveau retenu et le délai restent ceux d'Artificial Analysis)."
                % (epoch["date"], EPOCH_ATTRIBUTION, EPOCH_SITE), ""]
    else:
        out += ["L'indice de capacités d'Epoch AI (ECI) n'est pas lu%s : un plancher qui s'y ancre est introuvable et "
                "ne juge personne, et aucun membre n'est placé sur une estimation."
                % (", l'archive étant %s" % epoch_status_text(epoch) if epoch["status"] != "read"
                   else " (%s)" % safe_text(epoch["skipped"].get(EPOCH_ECI_KEY, "il ne contient aucun modèle"), 80)), ""]
    if (report["version"] is not None and report["wanted_version"] is not None
            and report["version"] != report["wanted_version"]):
        out += ["**L'indice d'intelligence est maintenant en version %g, les planchers sont écrits pour la "
                "version %g : à revoir avant de se fier à une ligne.**" % (report["version"],
                                                                         report["wanted_version"]), ""]
    for router in report["routers"]:
        contract = router["contract"]
        out += ["### `%s`" % router["name"], ""]
        if router["base"]:
            out += ["Dérivé de `%s` : mêmes plancher (%s), taux d'échange (%g points par seconde) et classement, et les "
                    "modèles sans appels d'outils en sont exclus." % (
                        router["base"], floor_text(contract["intelligence_floor"]),
                        contract["level_gain"]["min_points_per_second"]), ""]
        else:
            out += ["%s, un niveau de plus tant qu'il rapporte au moins %g points d'indice par seconde de plus, classé par %s." % (
                "Aucun plancher" if contract["intelligence_floor"].get("none")
                else "Plancher %s" % floor_text(contract["intelligence_floor"]), contract["level_gain"]["min_points_per_second"],
                ranking_text(contract, report["epoch"])), ""]
        out += ["| Membre | Enregistrement | Appelé à | Indice | Délai (s) | Jetons/s | Niveau retenu | Verdict |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        out += ["| %s |" % " | ".join(contract_cells(row)) for row in router["rows"]]
        out += ["", "Ordre actuel : %s." % " > ".join("`%s`" % safe_text(name, 60) for name in router["current"]),
                "", "Ordre des contrats : %s." % (" > ".join("`%s`" % safe_text(name, 60)
                                                           for name in router["proposed"]) or "aucun membre"), ""]
        if report["epoch"]["status"] == "read":
            out += quality_lines(router, report["epoch"])
        if router["base"]:
            out += derivation_lines(router)
        if len(router["floors"]) > 1:
            out += ["Effet de chaque plancher :", "", "| Plancher | En tête | Dernier recours |",
                    "| --- | --- | --- |"]
            out += ["| %s (%s)%s | %s | %s |" % (
                floor_figure(effect["floor"]), effect["text"], " (proposé)" if effect["floor"] == contract["intelligence_floor"]["value"] else "",
                names_text(effect["main"]), names_text(effect["last"])) for effect in router["floors"]]
            out.append("")
    for title, entries in (
            ("Entrées sans correspondance (à ajouter au fichier des contrats)",
             ["`%s`" % safe_text(name, 60) for name in report["unmapped"]]),
            ("Entrées sans enregistrement chez Artificial Analysis",
             ["`%s`" % safe_text(name, 60) for name in report["no_record"]]),
            ("Correspondances sans entrée (l'entrée n'est plus au modèle, la ligne est à retirer du fichier des contrats)",
             ["`%s` (%s)" % (safe_text(name, 60), "correspondance" if where == "models"
                             else "dernier recours de `%s`" % safe_text(where, 20)) for where, name in report["absent"]]),
            ("Noms absents de l'indice de capacités d'Epoch AI (le nom est à corriger dans le fichier des contrats)",
             ["`%s` : `%s`" % (safe_text(entry, 60), safe_text(name, 60)) if entry
              else "ancre d'un plancher : `%s`" % safe_text(name, 60) for entry, name in report["eci_stale"]]),
            ("Correspondances périmées (l'enregistrement n'est plus au classement)",
             ["`%s` : `%s`" % (safe_text(name, 60), safe_text(slug, 80)) for name, slug in report["stale"]]),
            ("Appelées à un niveau que le classement ne couvre pas",
             ["`%s` appelé à `%s`, classé à : %s" % (
                 safe_text(name, 60), safe_text(found["called"], 20),
                 ", ".join(sorted({level_text(other) for other in found["family"]}, key=level_rank)))
              for name, found in report["uncovered"]])):
        if entries:
            out += ["%s :" % title, ""] + capped(["- " + entry for entry in entries]) + [""]
    return out


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
    "unconfirmed": (
        "its provider's list omits it, and asking the provider for the model itself did not "
        "confirm that it is gone: %s",
        "la liste de son fournisseur l'omet, et lui demander directement le modèle n'a pas "
        "confirmé qu'il a disparu : %s",
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


def is_statement(line):
    """A line that holds Jinja statements and nothing else: the template writes nothing for it."""
    return bool(JINJA_STATEMENT.search(line)) and not JINJA_STATEMENT.sub("", line).strip()


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
    first line that is not a comment, or the first line of a commented-out entry. With the "entry"
    that starts there, or the last one of the run that does, the one statement line that opens a
    block closing right after it is stepped over: prose written above "{% if x %}" and the entry it
    wraps is about that entry, as the rendering, which has no such line, reads it."""
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


def goes_with_the_run(layout, keys, members, prose):
    """Whether "prose", the reason written above a Jinja statement that wraps the run "members" (all
    of which go), goes with the run. The rendering has no such statement, so by the offline rules
    the prose is the run's reason; but it was written above a statement, where a person may as well
    have been writing about the block, and only what is plainly the run's own goes: it says "not
    routed", it names no model that stays, and no entry that stays follows the run once the
    statements are read away, since the prose would then be that one's reason too."""
    lines = layout["lines"]
    text = " ".join(comment_content(lines[number]).strip() for number in prose)
    if not REASON.search(text):
        return False
    for entry in layout["entries"]:
        if entry["key"] not in keys and any(
                isinstance(token, str) and mention_pattern(token).search(text)
                for token in (entry["name"], entry["key"] and entry["key"][1])):
            return False
    number = members[-1]["end"]
    while True:
        while number < len(lines) and (is_bare(lines[number]) or is_statement(lines[number])):
            number += 1
        follower = layout["owner"].get(number)
        if follower is None:
            return True
        if layout["commented"][follower]["key"] not in keys:
            return False
        number = layout["commented"][follower]["end"]


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
            found = comments_above(layout, members[0]["start"], members[-1])
            prose = reason_lines(layout, found)
            if found and found[-1] != members[0]["start"] - 1:
                # A statement stands between the prose and the run. Bare "#" lines alone are not
                # a reason, and nothing there is worth a person's reading.
                if all(is_bare(lines[number]) for number in prose):
                    prose = []
                elif not goes_with_the_run(layout, keys, members, prose):
                    notes[members[0]["key"]]["left"].append(prose)
                    prose = []
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
            point(gone[0]["key"], comments_above(layout, members[0]["start"], members[-1]), "kept")

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
            elif finding.get("unconfirmed"):
                finding["removal"] = refused_outcome(report, finding, "unconfirmed",
                                                     finding["unconfirmed"])
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
    epoch = result.get("epoch")
    if epoch:
        if epoch["status"] == "error":
            state = "ERROR, not read: %s" % epoch["error"]
        else:
            state = "read, %d of the %d benchmark file(s) and %d model(s) of the capabilities index%s; source: %s, %s" % (
                len(epoch["files"]), len(EPOCH_FILES), len(epoch.get("eci") or {}),
                "".join(" (%s: %s)" % (key, reason) for key, reason in epoch["skipped"].items()),
                EPOCH_ATTRIBUTION, EPOCH_SITE)
        out.append("%-11s %s" % ("epoch", state))
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
                elif finding.get("unconfirmed"):
                    line += (" -- not confirmed by asking the provider for the model itself: "
                             + finding["unconfirmed"])
                lines.append(line)
        if lines:
            out += [labels[kind]] + lines + [""]
            count += len(lines)
    served = [(report, finding) for report in result["providers"]
              for finding in report.get("served", ())]
    if served:
        out += ["SERVED   missing from the provider's list, yet it answers when asked for the model "
                "itself -- kept, nothing to delete"]
        for report, finding in served:
            line = "  %s%s" % litellm_id(report["name"], finding["id"])
            if finding.get("names"):
                line += " (%s)" % ", ".join(str(name) for name in finding["names"])
            out.append(line)
        out.append("")
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


def name_stem(identifier):
    """The last segment of an id in the spelling of the file's names: lower case, dashes."""
    stem = identifier.split("/")[-1].lower().replace(":free", "-free")
    return re.sub(r"[^a-z0-9]+", "-", stem).strip("-") or "model"


def propose_name(provider, identifier, taken):
    stem = name_stem(identifier)
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


def ranking_caveat(ranking):
    """Where the figures come from and what a suggested place does not judge, in French: the issue
    and the addition pull requests both say it above the places they suggest."""
    return ("Chiffres lus le %s dans l'API gratuite d'Artificial Analysis, <%s> (source à citer ; "
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
            % (ranking["date"], RANKING_SITE))


def ranking_section(result):
    """The table of figures of the NEW models and the place each would take, in French: a suggestion
    with its source and its day, whose every row is to be checked, and which nothing applies."""
    ranking = result.get("rankings")
    # A model an addition pull request carries is ranked there, beside its entry.
    rows = [row for row in result.get("ranked") or [] if not proposed(result, row["provider"], row["id"])]
    if not ranking or ranking["status"] != "read" or not rows:
        return []
    out = ["## Classement des nouveaux modèles", "", ranking_caveat(ranking), "",
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
        listed = []
        for report in result["providers"]:
            for finding in report["findings"]:
                finding_kind = finding["kind"]
                removal = finding.get("removal")
                if finding.get("proposed"):
                    continue
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
                if finding.get("unproposed"):
                    line += " : **pas proposé par pull request** : " + finding["unproposed"]
                if kind.startswith("new") and snippets:
                    name = propose_name(report["name"], finding["id"], taken)
                    block = snippet(report["name"], finding["id"], report["basis"], name)
                    line += "\n" + "\n".join(
                        ["  ```yaml"] + ["  " + code for code in block] + ["  ```"])
                lines.append(line)
                if report["name"] not in listed:
                    listed.append(report["name"])
        if lines:
            title, explanation = sections[kind][0], sections[kind][1]
            out += ["## %s" % title, "", explanation, ""]
            if kind == "new_examine":
                pages = ["[%s](%s)" % (name, PRICING_PAGES[name])
                         for name in listed if name in PRICING_PAGES]
                if pages:
                    out += ["Pages de tarifs des fournisseurs de cette liste : %s." % ", ".join(pages),
                            ""]
            out += capped(lines) + [""]

    served = [(report, finding) for report in result["providers"]
              for finding in report.get("served", ())]
    if served:
        out += ["## Absents de la liste, mais toujours servis", "",
                "La liste de leur fournisseur ne les nomme pas, mais il répond quand on lui demande "
                "le modèle lui-même : ils ne sont pas retirés, rien n'est supprimé, et cette section "
                "n'est qu'une information.", ""]
        out += capped(["- `%s`%s%s" % (litellm_id(report["name"], finding["id"])[0],
                                      litellm_id(report["name"], finding["id"])[1].replace(
                                          " on ", " chez "),
                                      " (%s)" % ", ".join("`%s`" % name for name in finding["names"])
                                      if finding.get("names") else "")
                       for report, finding in served]) + [""]

    out += proposals_section(result)
    out += ranking_section(result)
    out += contracts_section(result)

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
    if issue_status(result) == 0:
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
        if source and source != JINJA_PLACEHOLDER and source not in sources:
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
        if finding.get("confirmed"):
            line += " Interrogé sur ce modèle, le fournisseur répond qu'il n'existe pas."
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
                  "no longer lists it (and, where the provider's API can be asked about one "
                  "model, when asking for it directly says it does not exist), only when the "
                  "cascades and aliases it leaves behind still "
                  "name an active entry, and only after reading the result back against the "
                  "original. What it could not delete without choosing stays in the weekly "
                  "issue, with the reason; so do additions and announced retirements, which are "
                  "choices.")
        + written_again
        + "\n")


# ------------------------------------------------------------------------------------------------
# Proposing the NEW models: two pull requests, which only a person merges
# ------------------------------------------------------------------------------------------------
# "--proposals DIR" writes what the weekly workflow needs to keep two pull requests of additions,
# split by how much the run knows of each model, never by provider: "ready" for a model of which it
# holds every fact a person would need (a free tier the provider's own API states, and a figure of the
# ranking matched for certain), "to_verify", opened as a draft, for any model one fact of which is
# missing, with which one and how to get it. Neither puts a model in a cascade: the places are
# suggestions in the body, computed on a ranking that is itself under revision. The job that writes
# builds the file itself, from nothing but a provider, an id and a name per model, and pushes it only
# if its text is the one built here: its "additions builder" mirrors addition_entries() and
# build_additions() line for line, and "check_drift_publish_guard.py" holds the two to the same output.

PROPOSAL_KINDS = ("ready", "to_verify")
PROPOSAL_LIMIT = 25  # entries per pull request, which the builder of the workflow holds too
PROPOSAL_BRANCHES = {"ready": "ADDITIONS_BRANCH", "to_verify": "ADDITIONS_TO_VERIFY_BRANCH"}
# What the job that writes accepts, and so all this proposes: an id that ends in a letter or a digit
# (a trailing ":" would make a YAML key of it), a name in the file's own spelling, a key read from
# the environment, an "https" base.
ADDITION_ID = re.compile(r"(?!.*(?:::|//))[A-Za-z0-9][A-Za-z0-9._:/+~-]{0,198}[A-Za-z0-9]")
ADDITION_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
ADDITION_NAME_LIMIT = 80
ADDITION_KEY = re.compile(r"os\.environ/[A-Z][A-Z0-9_]*")
ADDITION_BASE = re.compile(r"https://[a-z0-9.-]+(?::[0-9]{1,5})?(?:/[A-Za-z0-9._-]+)*/?")
ADDITION_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# The file as written, read line by line the way the builder of the workflow reads it.
ADDITION_ENTRY = re.compile(r"  (# )?- model_name: ([^\s#]+)\s*")
ADDITION_FIELD = re.compile(r"\s+(model|api_key|api_base):\s*(?:\"([^\"]*)\"|(\S+))\s*")
ADDITION_ACTIVE_BODY = re.compile(r" {4,}\S")
ADDITION_COMMENTED_BODY = re.compile(r"  # {2,}\S")
ADDITION_COMMENT_RUN = re.compile(r"  #( |$)")
TOP_LEVEL_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*:")
WORD = re.compile(r"[A-Za-z0-9_.-]+")
IGNORED_TARGET = re.compile(r"^\s*#\s*drift-ignore\s*:\s*(\S+)\s+--", re.M)
# What to look for on each provider's pricing page, in French, from what the file's own comments
# cite of those pages. The selftest holds it to PRICING_PAGES.
FREE_TIER_CHECKS = {
    "gemini": "dans le tableau de tarifs du modèle, la colonne « Free Tier » : « Free of charge » "
              "pour le prix d'entrée et pour celui de sortie veut dire gratuit, « Not available » "
              "veut dire payant seulement (la mention que citent les entrées Gemini commentées)",
    "groq": "le tableau « Free Plan Limits » : le modèle doit y avoir sa ligne (requêtes et jetons "
            "par minute et par jour) ; absent du tableau, il n'a pas de quota gratuit. Sa fiche, "
            "depuis <https://console.groq.com/docs/models>, dit aussi s'il est parmi les « Preview "
            "Models », que Groq peut arrêter à bref délai",
    "mistral": "son prix par million de jetons : Mistral n'a plus d'offre gratuite pour l'API (le mode "
               "« Free » ne couvre que Vibe et Studio, d'après sa documentation), et ses entrées sont "
               "payantes, rangées après les gratuits comme celles de DeepSeek ; l'ajouter, c'est "
               "accepter ce prix",
    "deepseek": "son prix par million de jetons : DeepSeek n'a pas d'offre gratuite, et ses entrées "
                "sont un dernier recours payant, en fin de cascade ; l'ajouter, c'est accepter ce prix",
    "cerebras": "la réponse de la FAQ à « Is there a permanently free tier? » : tant qu'elle est "
                "« No. », le modèle reste commenté, comme les autres entrées Cerebras",
    "sambanova": "l'offre « Free » : tant qu'elle demande « Add a payment method and purchase "
                 "credits to run your first requests », le modèle reste commenté, comme les autres "
                 "entrées SambaNova",
}

# The bodies the workflow writes are signed like everything posted from a session here, with the
# session that wrote this generator, and end with an open HTML comment that hides any footer added
# after them.
PROPOSAL_SIGNATURE = ("---\n\n_Generated by [Claude Code](https://claude.ai/code/"
                      "session_01RFPPZ73Abj4AkXu1wRnrtu) and supervised by @tigerblue77._\n\n<!--\n")


def proposed(result, provider, identifier):
    """Whether an addition pull request carries the NEW model "identifier" of "provider"."""
    return any(finding.get("proposed") for report in result["providers"] if report["name"] == provider
               for finding in report["findings"]
               if finding["kind"] == "new" and finding["id"] == identifier)


def issue_status(result):
    """The exit status, less the NEW models an addition pull request carries: the issue no longer
    lists them, so a week whose only news is one of them leaves it closed."""
    status = exit_status(result)
    if status != 1 or result["rules"]:
        return status
    return 1 if any(not finding.get("proposed") for report in result["providers"]
                    for finding in report["findings"]) else 0


def addition_entries(lines):
    """The entries of the "model_list" section as written, active and commented out: {"name",
    "commented", "fields" (model, api_key, api_base as written), "last" (the index of the line a new
    entry would follow)}. None when there is no "model_list:" line."""
    if "model_list:" not in lines:
        return None
    start = lines.index("model_list:")
    end = next((index for index in range(start + 1, len(lines)) if TOP_LEVEL_KEY.match(lines[index])),
               len(lines))
    entries = []
    for index in range(start + 1, end):
        head = ADDITION_ENTRY.fullmatch(lines[index])
        if not head:
            continue
        commented = head.group(1) is not None
        entry = {"name": head.group(2), "commented": commented, "fields": {}, "last": index}
        body = ADDITION_COMMENTED_BODY if commented else ADDITION_ACTIVE_BODY
        at = index + 1
        while at < end and body.match(lines[at]):
            field = ADDITION_FIELD.fullmatch(lines[at][4:] if commented else lines[at])
            if field and field.group(1) not in entry["fields"]:
                entry["fields"][field.group(1)] = (field.group(2) if field.group(2) is not None
                                                   else field.group(3))
            entry["last"] = at
            at += 1
        # A commented-out entry is followed after the comment block that holds it, so that a run of
        # them and the reason they share stay together.
        while commented and at < end and ADDITION_COMMENT_RUN.match(lines[at]):
            entry["last"] = at
            at += 1
        entries.append(entry)
    return entries


def addition_anchor(entries, provider):
    """The entry a new one of "provider" is modelled on and written after: its last active entry,
    else its last commented-out one, else None."""
    own = [entry for entry in entries
           if (attribute(entry["fields"].get("model"), entry["fields"].get("api_base")) or (None,))[0]
           == provider]
    active = [entry for entry in own if not entry["commented"]]
    return (active or own or [None])[-1]


# The catalogue that states a provider's free tier, for the providers whose API does (FREE_READABLE,
# which the selftest holds it to): the comment above the entry of such a model cites it.
FREE_CATALOGUES = {"openrouter": "openrouter.ai/api/v1/models"}


def addition_note(kind, date, provider, commented):
    """The comment written above a proposed entry. A commented-out one says "not routed", which is
    what the offline rule asks of its reason."""
    label = PROVIDER_LABELS[provider]
    if commented:
        return ("Not routed to: proposed by the weekly drift run on %s, its free tier on %s not "
                "verified yet." % (date, label))
    if provider in FREE_CATALOGUES:
        return 'Proposed by the weekly drift run on %s: listed free by "%s" that day.' % (
            date, FREE_CATALOGUES[provider])
    return "Proposed by the weekly drift run on %s: its free tier on %s is not verified yet." % (
        date, label)


def addition_block(kind, date, item, anchor):
    """The lines a proposed entry adds after its anchor: a blank line, its comment, the entry."""
    lead = "  # " if anchor["commented"] else "  "
    block = ["", "  # " + addition_note(kind, date, item["provider"], anchor["commented"]),
             "%s- model_name: %s" % (lead, item["name"]), "%s  litellm_params:" % lead,
             "%s    model: %s" % (lead, litellm_id(item["provider"], item["id"])[0])]
    if anchor["fields"].get("api_base") is not None:
        block.append('%s    api_base: "%s"' % (lead, anchor["fields"]["api_base"]))
    block.append('%s    api_key: "%s"' % (lead, anchor["fields"]["api_key"]))
    return block


def build_additions(text, date, kind, items):
    """(the file with the entries of "items" added, None), or (None, why not), refusing whatever the
    builder of the workflow refuses: the two must give the same text, and the selftest of
    "check_drift_publish_guard.py" compares them."""
    if not isinstance(text, str) or "\r" in text:
        return None, "the base template is not a text with plain line feeds"
    if not isinstance(date, str) or not ADDITION_DATE.fullmatch(date):
        return None, "the date is no date"
    if kind not in PROPOSAL_KINDS:
        return None, "the kind is neither ready nor to_verify"
    if not isinstance(items, list) or not 0 < len(items) <= PROPOSAL_LIMIT:
        return None, "there are no items, or more than %d" % PROPOSAL_LIMIT
    lines = text.split("\n")
    entries = addition_entries(lines)
    if entries is None:
        return None, 'the base template has no "model_list:" line'
    words = set(WORD.findall(text))
    ignored = set(IGNORED_TARGET.findall(text))
    known = {entry["fields"]["model"] for entry in entries if entry["fields"].get("model")}
    names = set()
    after = {}
    for item in items:
        if not isinstance(item, dict) or sorted(item) != ["id", "name", "provider"]:
            return None, "an item is not {provider, id, name}"
        provider, identifier, name = item["provider"], item["id"], item["name"]
        if not isinstance(provider, str) or provider not in PROVIDER_LABELS:
            return None, "an item names no provider this reads"
        if kind == "ready" and provider not in FREE_CATALOGUES:
            return None, "a ready addition is of a provider whose API states its free tier, and only"
        if not isinstance(identifier, str) or not ADDITION_ID.fullmatch(identifier):
            return None, "an id is not spelt like one"
        if provider in FREE_CATALOGUES and not identifier.endswith(":free"):
            return None, 'an id of a provider whose API states its free tier does not end in ":free"'
        if (not isinstance(name, str) or len(name) > ADDITION_NAME_LIMIT
                or not ADDITION_NAME.fullmatch(name)):
            return None, "a name is not spelt like the file's"
        if name in words or name in names:
            return None, "the name %s is already a word of the template or another item's" % name
        names.add(name)
        if litellm_id(provider, identifier)[0] in known:
            return None, "%s/%s is already an entry" % (provider, identifier)
        if "%s/%s" % (provider, identifier) in ignored:
            return None, "%s/%s is set aside by a drift-ignore line" % (provider, identifier)
        anchor = addition_anchor(entries, provider)
        if anchor is None:
            return None, "the template has no entry of %s to model one on" % provider
        key, base = anchor["fields"].get("api_key"), anchor["fields"].get("api_base")
        if not isinstance(key, str) or not ADDITION_KEY.fullmatch(key):
            return None, "the key of the entry %s is not read from the environment" % anchor["name"]
        if base is not None and not ADDITION_BASE.fullmatch(base):
            return None, "the api_base of the entry %s is not a plain https address" % anchor["name"]
        if kind == "ready" and anchor["commented"]:
            return None, "a ready addition follows an active entry"
        after.setdefault(anchor["last"], []).extend(addition_block(kind, date, item, anchor))
    out = []
    for index, line in enumerate(lines):
        out.append(line)
        out += after.get(index, [])
    return "\n".join(out), None


def addition_problem(text, new_text, items):
    """Why the file with the entries added does not read back as the file plus those entries, or
    None. It must render, break no offline rule the file did not already break, hold exactly the
    entries of the file and the proposed ones, and hold every cascade as it was."""
    before, old_problems = read_template(text)
    after, problems = read_template(new_text)
    if after is None:
        return problems[0]
    fresh = [problem for problem in problems if problem not in old_problems]
    if fresh:
        return fresh[0]

    def pairs(template):
        return {(entry["name"], entry["model"]) for entry in template["active"] + template["commented"]}

    wanted = pairs(before) | {(item["name"], litellm_id(item["provider"], item["id"])[0])
                              for item in items}
    if pairs(after) != wanted or len(after["active"]) + len(after["commented"]) != (
            len(before["active"]) + len(before["commented"]) + len(items)):
        return "the entries it reads are not the file's and the proposed ones"
    if fallback_lists(after["document"]) != fallback_lists(before["document"]):
        return "a cascade is not what it was"
    return None


# A trailing parenthesis on a ranking entry's name ("(Reasoning)", "(Xhigh)", "(Low)") names the
# configuration its figure was measured in, which may not be the one the entry calls.
VARIANT_MARKER = re.compile(r"\([^()]*\)\s*$")


def certain_match(row):
    """Whether the ranking's entry is certainly the model: match_ranking() took it by the id, whose
    last segment less ":free", squashed, is the squashed slug or name of that one entry of the whole
    ranking and of no other, and its name carries no variant marker. A match by the provider's name
    for the model, or onto a variant, is a guess, and a ready model is not one."""
    model = row.get("model") if row else None
    return bool(model) and row["how"] == "identifiant" and not VARIANT_MARKER.search(model["name"])


def missing_facts(result, provider, finding):
    """[(what, sentence)] of what the run does not know of a NEW model, in French: a model of which it
    knows both its free tier, from its provider's API, and a figure of the ranking matched for certain,
    is ready; any other is to verify."""
    missing = []
    if not finding.get("free"):
        missing.append(("free", "sa gratuité ne se lit pas dans l'API de %s" % PROVIDER_LABELS[provider]))
    ranking = result.get("rankings") or {"status": "no key"}
    row = next((row for row in result.get("ranked") or []
                if (row["provider"], row["id"]) == (provider, finding["id"])), None)
    model = row["model"] if row else None
    if ranking["status"] != "read":
        missing.append(("ranking", "le classement d'Artificial Analysis n'a pas été lu à cette exécution"))
    elif model is None and row and row["how"] == "ambigu":
        missing.append(("match", "rapprochement ambigu : plusieurs entrées du classement s'écrivent comme lui, "
                        "aucune n'est retenue"))
    elif model is None:
        missing.append(("ranking", "aucune entrée du classement ne s'écrit comme lui"))
    elif row["how"] != "identifiant":
        missing.append(("match", "rapprochement par le nom seulement : son identifiant ne s'écrit comme aucune "
                        "entrée du classement, le nom que lui donne son fournisseur comme « %s »"
                        % safe_text(model["name"], 80)))
    elif not certain_match(row):
        missing.append(("match", "rapprochement vers une variante : « %s » porte entre parenthèses la "
                        "configuration où son chiffre a été mesuré, qui peut ne pas être celle qu'appelle "
                        "l'entrée" % safe_text(model["name"], 80)))
    elif all(model.get(key) is None for key in ("intelligence", "coding", "speed")):
        missing.append(("figures", "le classement le connaît, sans aucun chiffre"))
    return missing


def addition_name(provider, identifier, taken):
    """A name for a proposed entry, the way propose_name() makes them, that is no word of the file nor
    another proposal's, or None."""
    stem = name_stem(identifier)[:60].strip("-") or "model"
    stem += "" if stem.endswith("-free") else NAME_SUFFIXES.get(provider, "")
    for extra in ["", "-" + provider, "-new"] + ["-%d" % number for number in range(2, 100)]:
        if stem + extra not in taken:
            taken.add(stem + extra)
            return stem + extra
    return None


def propose_additions(text, result, link=None):
    """{kind: {"complete", "items", "text", "body", "commit"}} for the two
    addition pull requests, every NEW finding being marked "proposed" (the kind that carries it) or
    "unproposed" (why not, in French, which the issue shows), and "missing" (what the run does not
    know of it, empty for a ready one). "complete" says whether every source the kind draws on was
    read: a pull request is closed over "nothing left to propose" only then."""
    proposals = {kind: {"complete": False, "items": []} for kind in PROPOSAL_KINDS}
    if result["unreadable"]:
        return proposals
    read = {report["name"]: report["status"] == "read" for report in result["providers"]}
    ranking = (result.get("rankings") or {"status": "no key"})["status"]
    proposals["ready"]["complete"] = all(read.get(name) for name in FREE_CATALOGUES) and ranking != "error"
    proposals["to_verify"]["complete"] = all(read.values())
    entries = addition_entries(text.split("\n")) or []
    taken = set(WORD.findall(text))
    candidates = {kind: [] for kind in PROPOSAL_KINDS}
    for report in result["providers"]:
        for finding in report["findings"]:
            if finding["kind"] != "new":
                continue
            anchor = addition_anchor(entries, report["name"])
            name = None
            if not ADDITION_ID.fullmatch(finding["id"]):
                finding["unproposed"] = "son identifiant n'a pas une forme que le workflow écrit dans le fichier"
            elif anchor is None:
                finding["unproposed"] = "le fichier n'a aucune entrée de ce fournisseur sur laquelle modeler la sienne"
            else:
                name = addition_name(report["name"], finding["id"], taken)
                if name is None:
                    finding["unproposed"] = "aucun nom libre pour son entrée"
            if name is not None:
                finding["missing"] = missing_facts(result, report["name"], finding)
                candidates["to_verify" if finding["missing"] else "ready"].append((report, finding, name))

    for kind in PROPOSAL_KINDS:
        chosen = candidates[kind]
        for _, finding, _ in chosen[PROPOSAL_LIMIT:]:
            finding["unproposed"] = "au-delà des %d entrées qu'une pull request porte" % PROPOSAL_LIMIT
        chosen = chosen[:PROPOSAL_LIMIT]
        while chosen:
            items = [{"provider": report["name"], "id": finding["id"], "name": name}
                     for report, finding, name in chosen]
            built, problem = build_additions(text, result["date"], kind, items)
            problem = problem or addition_problem(text, built, items)
            if problem:
                for _, finding, _ in chosen:
                    finding["unproposed"] = ("le fichier que la pull request porterait ne se relit pas : %s"
                                             % code_span(problem))
                chosen = []
                break
            body = render_additions_body(result, kind, chosen, entries, link)
            if len(body) <= BODY_LIMIT:
                proposals[kind].update(items=items, text=built, body=body,
                                       commit=render_additions_commit(result, kind, chosen))
                break
            chosen.pop()[1]["unproposed"] = "le corps de la pull request dépasserait la taille que GitHub accepte"
        for _, finding, _ in chosen:
            finding["proposed"] = kind
    result["proposals"] = {kind: len(proposals[kind]["items"]) for kind in PROPOSAL_KINDS}
    return proposals


def write_proposals(directory, proposals, date):
    """"proposals.json" (the date, and for each kind whether it is complete and its items: what the job
    that writes builds from), and for each kind that has items its body, its commit message and the
    file as built here, which that job requires its own to equal. A file of an earlier run is removed
    first."""
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    data = {"date": date}
    for kind in PROPOSAL_KINDS:
        part = proposals[kind]
        data[kind] = {"complete": part["complete"], "items": part["items"]}
        for suffix, key in (("body.md", "body"), ("commit.txt", "commit"), ("template.j2", "text")):
            path = folder / ("%s_%s" % (kind, suffix))
            path.unlink(missing_ok=True)
            if part["items"]:
                path.write_bytes(part[key].encode("utf-8"))
    (folder / "proposals.json").write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


def branch_link(variable):
    """Where the open pull request of the branch the workflow names in "variable" is."""
    server = os.environ.get("GITHUB_SERVER_URL")
    repository = os.environ.get("GITHUB_REPOSITORY")
    branch = os.environ.get(variable)
    if server and repository and branch:
        return "%s/%s/pulls?q=is%%3Apr+is%%3Aopen+head%%3A%s" % (
            server, repository, urllib.parse.quote(branch, safe=""))
    return None


def keyed(provider):
    """Whether the catalogue of "provider" is read with a key."""
    return next(variable for name, _, variable, _, _, _ in PROVIDERS if name == provider) is not None


def catalogue_command(provider, identifier, key):
    """A command that prints what "provider" says of the model "identifier", and nothing secret: the
    provider's own route for one model where it has one, else its list filtered to that id. A keyed
    one runs in the LiteLLM container, whose environment holds the key under the name the entry reads
    it from, and prints the model's description, never the key. "identifier" is an ADDITION_ID and
    "key" an ADDITION_KEY, so neither can end a quoted string of the shell or of Python."""
    pick = "answer"
    if provider in LOOKUPS:
        url = LOOKUPS[provider] + urllib.parse.quote(identifier, safe="/")
    else:
        url = catalogue_url(provider)
        pick = '[model for model in answer.get("data", []) if model.get("id") == "%s"]' % identifier
    headers = '"User-Agent": "%s"' % USER_AGENT
    if keyed(provider):
        variable = key.split("/", 1)[1]
        headers += (', "x-goog-api-key": os.environ["%s"]' % variable if provider == "gemini"
                    else ', "Authorization": "Bearer " + os.environ["%s"]' % variable)
    program = ('import json, os, urllib.request; request = urllib.request.Request("%s", headers={%s}); '
               "answer = json.load(urllib.request.urlopen(request, timeout=30)); "
               "print(json.dumps(%s, indent=1))" % (url, headers, pick))
    if keyed(provider):
        return ('docker exec "$(docker ps --quiet --filter name=litellm | head -n 1)" python3 -c \'%s\''
                % program)
    return "python3 -c '%s'" % program


def proposals_section(result):
    """The pointer of the issue to the two addition pull requests, in French."""
    counts = result.get("proposals")
    if not counts or not any(counts.values()):
        return []
    out = ["## Ajouts proposés par pull request", "",
           "Les nouveaux modèles ne sont plus listés ici : chacun est proposé, avec son entrée, par l'une de "
           "deux pull requests que le workflow tient à jour et que rien ne fusionne seul.", ""]
    for kind, text in (("ready", "prêts, dont l'exécution sait tout ce qu'un ajout demande"),
                       ("to_verify", "à vérifier, en brouillon, avec pour chacun l'information qui manque "
                                     "et comment l'obtenir")):
        if counts.get(kind):
            link = branch_link(PROPOSAL_BRANCHES[kind])
            out.append("- %s : %s%s." % (text, count_phrase(counts[kind], "modèle", "modèles"),
                                        " ([la pull request](%s))" % link if link else ""))
    return out + [""]


def figures_text(model, how, certain=False):
    return ("intelligence %s, code %s, vitesse %s jetons/s, prix mixte %s $/M jetons, d'après « %s », %s" % (
        figure_text(model["intelligence"]), figure_text(model["coding"]), figure_text(model["speed"]),
        figure_text(model["price"]), safe_text(model["name"], 80),
        "rapprochement sûr" if certain else "rapproché par %s : à vérifier" % (
            "l'identifiant" if how == "identifiant" else "le nom")))


def ranked_row(result, provider, identifier):
    return next((row for row in result.get("ranked") or []
                 if (row["provider"], row["id"]) == (provider, identifier)), None)


def placing_lines(result, provider, identifier):
    """What the ranking says of a proposed model, as list items: its figures and the place it would
    take in each router, or that it is not placed, and why. The second value is the reason, in
    English, of the drift-ignore line that sets an unmeasured model aside, or None for a measured one."""
    ranking = result.get("rankings") or {"status": "no key"}
    row = ranked_row(result, provider, identifier)
    model = row["model"] if row else None
    if ranking["status"] != "read":
        return (["**Non placé** : le classement d'Artificial Analysis n'a pas été lu à cette exécution, "
                 "il n'y a aucun chiffre pour le placer."],
                "the Artificial Analysis ranking was not read on %s, so there are no figures to place it "
                "by in any cascade" % result["date"])
    if model is None or all(model.get(key) is None for key in ("intelligence", "coding", "speed")):
        why = ("plusieurs entrées du classement portent ce nom, aucune n'est retenue"
               if row and row["how"] == "ambigu" else
               "le classement le connaît, sans aucun chiffre" if model else
               "aucune entrée du classement ne s'écrit comme lui")
        return (["**Non placé**, faute de mesure : %s." % why],
                "no entry of the Artificial Analysis ranking measured it on %s, so there are no figures "
                "to place it by in any cascade" % result["date"])
    lines = ["Classement : %s." % figures_text(model, row["how"], certain_match(row))]
    if row["places"]:
        lines += ["Places suggérées :"] + ["  - " + place_text(router, row["places"][router])
                                           for router, _ in RANKING_ROUTERS if router in row["places"]]
    else:
        lines.append("Aucune place suggérée : aucun routeur n'a de membre classé sur le chiffre qui "
                     "le départage.")
    return lines, None


def yaml_fence(lines, indent=""):
    return ["%s```yaml" % indent] + ["%s%s" % (indent, line) for line in lines] + ["%s```" % indent]


# How to get each fact a model to verify lacks, in French.
MISSING_HOWTO = {
    "ranking": "le chercher sur <%s> ; s'il y est, relever son indice d'intelligence, son indice de "
               "code et sa vitesse, et le placer à la main en les comparant à ceux des membres de "
               "chaque cascade ; s'il n'y est pas, le placer sans chiffre ou l'écarter" % RANKING_SITE,
    "match": "ouvrir sa fiche sur <%s> et vérifier que c'est bien ce modèle (même éditeur, même taille, "
             "même variante d'effort de raisonnement) ; si oui, les places suggérées plus bas tiennent" % RANKING_SITE,
    "figures": "attendre que le classement le mesure, ou le placer à la main",
}


def render_additions_body(result, kind, chosen, entries, link=None):
    """The body of one addition pull request, in French: what it is, how to decide, and each model with
    its entry, its figures and places, and, for the one to verify, which fact is missing and how to
    get it."""
    date = result["date"]
    ready = kind == "ready"
    other = os.environ.get(PROPOSAL_BRANCHES["to_verify" if ready else "ready"])
    branch = os.environ.get(PROPOSAL_BRANCHES[kind])
    run = "à l'exécution du %s%s" % (date, " (%s)" % link if link else "")
    if ready:
        out = ["Ajouts **prêts**, proposés **sans IA** par `.github/workflows/LiteLLM_model_drift.yml`, %s. "
               "Pour chaque modèle ci-dessous, l'exécution tient tout ce qu'il faut pour l'ajouter sans y "
               "réfléchir : sa gratuité, lue dans l'API de son fournisseur (chez OpenRouter, <%s> : un "
               "identifiant `:free`, un prix de 0 en entrée comme en sortie, le texte pour seule sortie), et "
               "un chiffre du classement d'Artificial Analysis rapproché de façon sûre (son identifiant, sans `:free`, s'écrit à la casse et à la ponctuation près comme le slug ou le nom d'une seule entrée du classement, qui ne porte aucune marque de variante entre parenthèses). Les nouveaux "
               "modèles auxquels il manque une de ces informations, de quelque fournisseur qu'ils soient, sont "
               "dans une pull request à part, en brouillon%s." % (
                   run, catalogue_url("openrouter"), " (branche %s)" % code_span(other) if other else ""),
               "",
               "Le commit ajoute chaque entrée après la dernière entrée de son fournisseur, sous un "
               "commentaire qui cite le catalogue et le jour, et ne la met dans **aucune cascade** : "
               "fusionnée telle quelle, l'entrée s'appelle par son nom et aucun routeur ne s'en sert. Les "
               "places données plus bas sont des **suggestions, calculées sur le classement actuel, qui est "
               "en cours de révision** : son chiffre est celui d'une seule variante d'effort de "
               "raisonnement, et sa vitesse en jetons par seconde ne dit rien du temps jusqu'à la réponse "
               "d'un modèle qui raisonne. Rien ne les applique."]
    else:
        out = ["**Brouillon : à ne pas fusionner avant d'avoir fait, pour chaque modèle, les vérifications "
               "listées sous lui.** Ajouts **à vérifier**, proposés **sans IA** par "
               "`.github/workflows/LiteLLM_model_drift.yml`, %s. À chaque modèle ci-dessous, il manque au "
               "moins une information pour l'ajouter sans y réfléchir : sa gratuité, quand l'API de son "
               "fournisseur ne la dit pas, un chiffre du classement d'Artificial Analysis, ou un rapprochement "
               "sûr avec lui. Ce qui manque est dit sous chacun, avec la façon de l'obtenir. Les modèles dont "
               "l'exécution sait tout sont dans une pull request à part, prête à relire%s." % (
                   run, " (branche %s)" % code_span(other) if other else ""),
               "",
               "Le commit ajoute chaque entrée après la dernière entrée de son fournisseur, sous un "
               "commentaire qui dit d'où elle vient et quand. L'entrée est active, sauf chez un fournisseur "
               "dont le fichier n'a aucune entrée active : elle suit alors, commentée, sa dernière entrée "
               "commentée, avec une raison provisoire. Elle n'est mise dans **aucune cascade** : les places "
               "données plus bas, quand elles se calculent, sont des suggestions."]
    out += ["",
            "**Rien ne la fusionne seule** : `.github/workflows/dependabot-auto-merge.yml` ne reconnaît que la "
            "branche des suppressions, et celle-ci%s attend tigerblue77." % (
                ", %s," % code_span(branch) if branch else ""),
            "",
            "## Décider",
            ""]
    out.append("- **Garder un modèle** : %spour qu'un routeur s'en serve, ajouter son nom à la cascade de "
               "ce routeur, à la place choisie, dans un commit sur cette branche (et dans la table `head` du "
               "modèle de configuration s'il en devient le premier membre) ; fusionnée sans cela, l'entrée "
               "s'appelle par son nom." % ("" if ready else "faire ses vérifications, puis, "))
    out += ["- **Écarter un modèle** : remplacer son entrée et le commentaire au-dessus par une ligne "
            "`# drift-ignore: <fournisseur>/<id> -- <raison>`%s, dans un commit sur cette branche. Une fois "
            "fusionnée, le modèle n'est plus jamais proposé." % (
                "" if ready else " ; celle qui est donnée plus bas est prête à coller"),
            "- **Fermer sans fusionner ne décide rien** : la pull request revient à l'exécution suivante "
            "avec les modèles que le fichier ne connaît toujours pas.",
            "",
            "## %s" % ("Modèle proposé" if len(chosen) == 1 else "Modèles proposés"), ""]
    anchors = {}
    for report, finding, name in chosen:
        provider, identifier = report["name"], finding["id"]
        anchor = anchors.setdefault(provider, addition_anchor(entries, provider))
        item = {"provider": provider, "id": identifier, "name": name}
        block = addition_block(kind, date, item, anchor)[1:]
        full = "%s/%s" % (provider, identifier)
        out += ["### %s → %s" % (code_span(litellm_id(provider, identifier)[0], 220), code_span(name)), ""]
        if finding.get("label"):
            # Groq's catalogue names no model, only who owns it, which is what its label holds.
            out += ["%s chez %s : %s." % ("Propriétaire" if provider == "groq" else "Nom",
                                         PROVIDER_LABELS[provider], code_span(finding["label"])), ""]
        out += ["Entrée %s par le commit :" % ("commentée ajoutée" if anchor["commented"] else "ajoutée"), ""]
        out += yaml_fence(block) + [""]
        placing, unmeasured = placing_lines(result, provider, identifier)
        if ready:
            out.append("- Gratuité : lue dans <https://%s>, le %s." % (FREE_CATALOGUES[provider], date))
            out += [line if line.startswith("  - ") else "- " + line for line in placing]
            out.append("")
            continue
        missing = finding.get("missing") or []
        out += ["**Ce qui manque** :", ""] + ["- %s." % sentence for _, sentence in missing] + [""]
        if any(what == "free" for what, _ in missing):
            page = PRICING_PAGES.get(provider, "")
            out.append("- [ ] **Gratuité.** Ouvrir <%s> et y chercher, pour %s, %s." % (
                page, code_span(identifier, 220), FREE_TIER_CHECKS.get(provider, "s'il est gratuit")))
        else:
            out.append("- Gratuité : lue dans <https://%s>, le %s ; rien à vérifier." % (
                FREE_CATALOGUES[provider], date))
        out += ["- [ ] **Catalogue.** Vérifier que %s sert toujours ce modèle : la commande n'affiche "
                "que sa fiche, aucune clé%s." % (
                    PROVIDER_LABELS[provider],
                    ", et se lance en root sur la machine qui fait tourner la pile, car elle lit la clé "
                    "dans le conteneur LiteLLM" if keyed(provider) else ""),
                "",
                "  ```sh",
                "  " + catalogue_command(provider, identifier, anchor["fields"]["api_key"]),
                "  ```",
                ""]
        for what, _ in missing:
            if what in MISSING_HOWTO:
                out.append("- [ ] **%s.** %s." % (
                    {"ranking": "Classement", "match": "Rapprochement", "figures": "Chiffres"}[what], MISSING_HOWTO[what][0].upper() + MISSING_HOWTO[what][1:]))
        out.append("- [ ] **Place.** Choisir sa place dans les routeurs, ou n'en donner aucune :")
        out += ["  - " + line if not line.startswith("  - ") else "  " + line for line in placing]
        if unmeasured:
            out += ["", "  Pour l'écarter faute de mesure, la ligne est :", ""]
            out += yaml_fence(["  # drift-ignore: %s -- %s" % (full, unmeasured)], "  ")
        if any(what == "free" for what, _ in missing):
            page_name = PRICING_PAGES.get(provider, "").split("://", 1)[-1]
            out += ["",
                    "- [ ] **Commentaire.** Remplacer le commentaire provisoire au-dessus de l'entrée par la "
                    "source et la date de la vérification, la date étant celle du jour où la page a été lue "
                    "(AAAA-MM-JJ), par exemple :",
                    ""]
            if anchor["commented"]:
                out += yaml_fence(['  # Not routed to: <la raison>, per "%s", checked %s.' % (page_name, date)],
                                  "  ")
            else:
                out += yaml_fence(['  # Free per "%s", checked %s: "<la mention lue>".' % (page_name, date)],
                                  "  ")
            out += ["",
                    "- **Si la réponse est non** : supprimer l'entrée et son commentaire, et écrire à leur place :",
                    ""]
            out += yaml_fence(['  # drift-ignore: %s -- not free per "%s" (read %s)' % (full, page_name, date)],
                              "  ")
        out.append("")
    ranking = result.get("rankings") or {"status": "no key"}
    out += ["## Classement", ""]
    if ranking["status"] == "read":
        out += [ranking_caveat(ranking)
                + (" Ici, chaque modèle est rapproché de façon sûre : le rapprochement est sûr, "
                   "pas la place, que le classement en révision changera." if ready else ""), ""]
    else:
        out += ["Le classement d'Artificial Analysis n'a pas été lu à cette exécution (%s) : aucun modèle "
                "n'est placé." % ("pas de clé : secret `%s`" % RANKING_KEY if ranking["status"] == "no key"
                                  else "erreur : %s" % code_span(ranking.get("error", ""))), ""]
    out += ["## Comment elle évolue", "",
            "Elle est refaite à chaque exécution depuis `main` : sa branche est `main` plus un commit du "
            "workflow, et son titre et son corps sont réécrits (une case cochée reste cochée tant que sa "
            "ligne ne change pas). Une semaine qui ne change que les dates des commentaires ne pousse rien : "
            "chaque entrée garde le jour où elle a été proposée. Un modèle fusionné, ou écarté par sa ligne "
            "`drift-ignore`, n'y revient plus ; un modèle à qui il manquait une information passe dans la "
            "pull request des modèles prêts la semaine où l'exécution l'a. Un commit d'une personne sur la "
            "branche la fige : tant que la pull request est ouverte, le workflow n'y touche plus, ni pour "
            "l'enrichir ni pour la fermer ; une fois qu'elle est fermée sans être fusionnée, son exécution "
            "échoue chaque semaine jusqu'à ce que la branche soit supprimée. Elle se ferme quand plus rien "
            "n'est à proposer, à condition que l'exécution ait lu chacune des sources dont elle dépend%s." % (
                "" if ready else " et qu'elle reste en brouillon tant qu'une personne ne la passe pas "
                "« Ready for review » (là où le dépôt refuse les brouillons, elle est ouverte prête à "
                "relire, et ce corps seul dit d'attendre)"),
            "", PROPOSAL_SIGNATURE]
    return "\n".join(out)


def render_additions_commit(result, kind, chosen):
    """The commit that carries the proposed entries, in English like every commit here."""
    identifiers = ", ".join(litellm_id(report["name"], finding["id"])[0] for report, finding, _ in chosen)
    count = count_phrase(len(chosen), "model", "models")
    if kind == "ready":
        subject = "Propose the new LiteLLM models the weekly drift check knows everything of (#346)"
        found = ("The weekly drift check found on %s %s the model list does not know and of which it holds "
                 "every fact an addition needs: a free tier its provider's API states, and a figure of the "
                 "Artificial Analysis ranking matched for certain: %s. Each is added after the last "
                 "entry of its provider, modelled on it, under a comment citing the catalogue and the day, "
                 "in no cascade: the places the pull request suggests are computed on a ranking that is "
                 "under revision." % (result["date"], count, identifiers))
    else:
        subject = "Propose the new LiteLLM models a person has to check before adding (#346)"
        found = ("The weekly drift check found on %s %s the model list does not know and of which at least "
                 "one fact an addition needs is missing (a free tier the provider's API does not state, a "
                 "figure of the ranking, a certain match with it): %s. Each is added after the last "
                 "entry of its provider, modelled on it, in no cascade, and the draft pull request says what "
                 "is missing for each and how to get it." % (result["date"], count, identifiers))
    return subject + "\n\n" + wrapped(found) + "\n\n" + wrapped("Nothing merges it but a person.") + "\n"


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
    ("a variable that is none of the provider keys is a finding",
     ("\"auto\": \"{{ to['flash'] }}\"",
      '"auto": "{{ Artificial_Intelligence_LiteLLM_Cerebras_API_key }}"'), "none of the provider keys"),
    ("a key beyond those the template reads, read the way it reads them, is a finding too, though "
     "\"is string\" would take it for a key that is not given",
     ("  'OpenRouter': Artificial_Intelligence_LiteLLM_OpenRouter_API_key is string and "
      "Artificial_Intelligence_LiteLLM_OpenRouter_API_key | length > 0\n} %}",
      "  'OpenRouter': Artificial_Intelligence_LiteLLM_OpenRouter_API_key is string and "
      "Artificial_Intelligence_LiteLLM_OpenRouter_API_key | length > 0,\n"
      "  'Cerebras': Artificial_Intelligence_LiteLLM_Cerebras_API_key is string and "
      "Artificial_Intelligence_LiteLLM_Cerebras_API_key | length > 0\n} %}"), "none of the provider keys"),
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


# Groq without "vendor/fast". It still lists one id with a slash, as the real one lists many, because
# the lookup of a model is trusted only once it has answered for a listed model of the same shape;
# "vendor/whisper-v9" is not a chat model, so it is not offered as a NEW one.
GROQ_WITHOUT_FAST = {"data": [{"id": "whisper-large-v9", "active": True},
                              {"id": "vendor/whisper-v9", "active": True}]}


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


def http_error(status):
    return urllib.error.HTTPError("https://selftest.invalid/", status, "selftest", None,
                                  io.BytesIO(b"{}"))


def canned_opener(answers, calls):
    """An opener serving "answers" by provider. An answer that is an exception is raised. The ranking
    source's answer is a list of pages, or a single page served for every page asked for.

    A lookup of one model (see LOOKUPS) is answered the way a provider is expected to: 200 for a
    model the canned catalogue names, 404 for any other. "answers" may hold a "lookups" mapping of
    (provider, id) to what to serve instead: an exception is raised, an integer is the status of
    an HTTP error, anything else is the body."""
    urls = {name: url for name, url, _, _, _, _ in PROVIDERS}
    readers = {name: reader for name, _, _, _, reader, _ in PROVIDERS}

    def lookup(name, identifier):
        served = answers.get("lookups", {})
        if (name, identifier) in served:
            answer = served[(name, identifier)]
            if isinstance(answer, Exception):
                raise answer
            if isinstance(answer, int):
                raise http_error(answer)
            return answer if isinstance(answer, bytes) else json.dumps(answer).encode()
        pages = answers[name] if isinstance(answers[name], list) else [answers[name]]
        if identifier in readers[name](pages)["members"]:
            return json.dumps({"id": identifier}).encode()
        raise http_error(404)

    def opener(url, headers, limit=None):
        calls.append((url, dict(headers)))
        if url == EPOCH_URL:
            # The archive of Epoch AI, which a case serves in "answers" as bytes, and which nobody
            # served is a 404.
            answer = answers.get("epoch", http_error(404))
            if isinstance(answer, Exception):
                raise answer
            return answer
        for name, base in LOOKUPS.items():
            if url.startswith(base):
                return lookup(name, urllib.parse.unquote(url[len(base):]))
        if url.startswith(RANKING_URL):
            answer = answers["rankings"]
            if isinstance(answer, list):
                # One answer per page, asked for as "?page=N": a page nobody wrote is a read too far.
                number = int(url.rsplit("page=", 1)[1])
                if number > len(answer):
                    raise AssertionError("the ranking source was asked for page %d of %d" % (number, len(answer)))
                answer = answer[number - 1]
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

    def examine_section(body):
        return body.split("## Nouveaux modèles à examiner")[1].split("\n## ")[0] \
            if "## Nouveaux modèles à examiner" in body else None

    def pricing_links(wanted):
        """A check: the "to examine" section links exactly these providers' pricing pages, in this
        order, and still tells the reader to verify the free tier."""
        def check(result, calls, report, body):
            section = examine_section(body)
            if section is None:
                return "no \"to examine\" section"
            if "la vérifier sur sa page de tarifs avant de les router" not in section:
                return "the instruction to verify the free tier is gone from the section"
            links = [line for line in section.splitlines() if line.startswith("Pages de tarifs")]
            expected = ("Pages de tarifs des fournisseurs de cette liste : "
                        + ", ".join("[%s](%s)" % (name, PRICING_PAGES.get(name))
                                    for name in wanted)
                        + ".")
            return None if links == [expected] else "links %r, expected %r" % (links, [expected])
        return check

    def no_pricing_links(result, calls, report, body):
        return "a pricing page is linked" if "Pages de tarifs" in body else None

    def new_models_of(gemini, groq):
        answers = selftest_answers()
        if gemini:
            answers["gemini"] = [{"models": answers["gemini"][0]["models"] + [
                {"name": "models/gemini-10-pro", "supportedGenerationMethods": ["generateContent"]}]}]
        if groq:
            answers["groq"] = {"data": answers["groq"]["data"] + [
                {"id": "vendor/new-fast", "active": True}]}
        return answers

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
        ("a new Mistral model gets the link to Mistral's pricing page and to no other",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         changed("mistral", {"data": base["mistral"]["data"] + [
             {"id": "magistral-9", "capabilities": {"completion_chat": True}}]}),
         [("new", "magistral-9")], 1, pricing_links(["mistral"])),
        ("new models of two providers get one link each, in the providers' order",
         SELFTEST_TEMPLATE, SELFTEST_KEYS, new_models_of(True, True),
         [("new", "gemini-10-pro"), ("new", "vendor/new-fast")], 1,
         pricing_links(["gemini", "groq"])),
        ("a new model that only OpenRouter lists, free there, gets no pricing link",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         changed("openrouter", openrouter_with(openrouter_model("vendor/fresh:free"))),
         [("new", "vendor/fresh:free")], 1, no_pricing_links),
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
IF_GROQ = "{% if Artificial_Intelligence_LiteLLM_Groq_API_key %}\n"
ENDIF = "{% endif %}\n"
PAID_A, PAID_B, PAID_C = (commented_entry("paid-%s" % letter, "openrouter/vendor/paid-%s" % letter,
                                          "OPENROUTER") for letter in "abc")
PAID_A_ONLY = "  # paid-a is not routed to: paid only.\n"


def statement_over_run(close_after=ENDIF):
    """The paid run, wrapped in a statement written between its reason and its first entry."""
    return ((PAID_REASON, PAID_REASON + IF_GROQ), (PAID_C, PAID_C + close_after))


def statement_over_first(prose):
    """The first paid entry alone under a statement, with "prose" above the statement, and the other
    two entries a run of their own under the reason that was there."""
    return ((PAID_REASON + PAID_A + "  #\n", prose + IF_GROQ + PAID_A + ENDIF + "\n" + PAID_REASON),)


def statement_over_first_then_run():
    """The first paid entry under a statement that closes right before the entries that follow it,
    which the rendering reads as one run under the reason above the statement."""
    return ((PAID_REASON + PAID_A + "  #\n", PAID_REASON + IF_GROQ + PAID_A + ENDIF + "  #\n"),)

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
    ("the reason above a statement that wraps a run deleted whole goes with it, and the statement "
     "stays, empty",
     statement_over_run(), [("openrouter", "vendor/paid-%s" % letter, "gone") for letter in "abc"],
     [(PAID_REASON + IF_GROQ + PAID_A + "  #\n" + PAID_B + "  #\n" + PAID_C, IF_GROQ)],
     {}),
    ("so does the prose about the one model that the statement wraps",
     statement_over_first(PAID_A_ONLY), [("openrouter", "vendor/paid-a", "gone")],
     [(PAID_A_ONLY + IF_GROQ + PAID_A, IF_GROQ)],
     {}),
    ("a statement that closes two blank lines after the run still wraps it",
     statement_over_run("\n\n" + ENDIF),
     [("openrouter", "vendor/paid-%s" % letter, "gone") for letter in "abc"],
     [(PAID_REASON + IF_GROQ + PAID_A + "  #\n" + PAID_B + "  #\n" + PAID_C, IF_GROQ)],
     {}),
    ("one that closes three lines after it wraps more than the run, and the reason stays",
     statement_over_run("\n\n\n" + ENDIF),
     [("openrouter", "vendor/paid-%s" % letter, "gone") for letter in "abc"],
     [(IF_GROQ + PAID_A + "  #\n" + PAID_B + "  #\n" + PAID_C, IF_GROQ)],
     {}),
    ("only one statement is stepped over: the reason above two stacked ones stays",
     ((PAID_REASON, PAID_REASON + IF_GROQ + IF_GROQ), (PAID_C, PAID_C + ENDIF + ENDIF)),
     [("openrouter", "vendor/paid-%s" % letter, "gone") for letter in "abc"],
     [(IF_GROQ + IF_GROQ + PAID_A + "  #\n" + PAID_B + "  #\n" + PAID_C, IF_GROQ + IF_GROQ)],
     {}),
    ("prose that names a model which stays is left where it is, whichever way it names it",
     statement_over_first(PAID_A_ONLY.replace("paid only", "paid only; alpha-groq is free")),
     [("openrouter", "vendor/paid-a", "gone")],
     [(PAID_A, "")],
     {}),
    ("by its id",
     statement_over_first(PAID_A_ONLY.replace("paid only", "paid only; vendor/alpha is free")),
     [("openrouter", "vendor/paid-a", "gone")],
     [(PAID_A, "")],
     {}),
    ("prose that does not say the entry is not routed to is not taken for its reason",
     statement_over_first("  # Paid, and a card is needed.\n"), [("openrouter", "vendor/paid-a", "gone")],
     [(PAID_A, "")],
     {}),
    ("the reason stays when an entry that stays follows the statement: the rendering makes it the "
     "reason of that one too",
     statement_over_first_then_run(), [("openrouter", "vendor/paid-a", "gone")],
     [(PAID_A, "")],
     {}),
    ("and so when it is the next but one, the entry after it going too",
     statement_over_first_then_run(),
     [("openrouter", "vendor/paid-a", "gone"), ("openrouter", "vendor/paid-b", "gone")],
     [(PAID_A, ""), (PAID_B + "  #\n", "")],
     {}),
    ("a reason of several paragraphs goes whole, the bare line between them included",
     statement_over_run() + ((PAID_REASON + IF_GROQ,
                              PAID_REASON + "  #\n  # A second paragraph.\n" + IF_GROQ),),
     [("openrouter", "vendor/paid-%s" % letter, "gone") for letter in "abc"],
     [(PAID_REASON + "  #\n  # A second paragraph.\n" + IF_GROQ + PAID_A + "  #\n" + PAID_B
       + "  #\n" + PAID_C, IF_GROQ)],
     {}),
    ("a name that merely starts like one that stays is not that model",
     statement_over_first(PAID_A_ONLY.replace("paid only", "paid only; alpha-groq-two is free")),
     [("openrouter", "vendor/paid-a", "gone")],
     [(PAID_A_ONLY.replace("paid only", "paid only; alpha-groq-two is free") + IF_GROQ + PAID_A,
       IF_GROQ)],
     {}),
    ("a closing statement above the run is not stepped over: only the one that opens a block is",
     ((PAID_REASON, IF_GROQ + PAID_REASON + ENDIF),),
     [("openrouter", "vendor/paid-%s" % letter, "gone") for letter in "abc"],
     [(PAID_A + "  #\n" + PAID_B + "  #\n" + PAID_C, "")],
     {}),
    ("the reason goes when a blank line separates the statement from the entry that stays: that "
     "one is a run of its own",
     ((PAID_REASON + PAID_A + "  #\n", PAID_REASON + IF_GROQ + PAID_A + ENDIF + "\n"),),
     [("openrouter", "vendor/paid-a", "gone")],
     [(PAID_REASON + IF_GROQ + PAID_A, IF_GROQ)],
     {}),
    ("and when a comment of its own stands on the line of the closing statement, which the "
     "rendering writes as a line of prose between them",
     ((PAID_REASON + PAID_A + "  #\n",
       PAID_REASON + IF_GROQ + PAID_A + "{% endif %}  # paid-b is not routed to: too dear\n"),),
     [("openrouter", "vendor/paid-a", "gone")],
     [(PAID_REASON + IF_GROQ + PAID_A, IF_GROQ)],
     {}),
    ("the reason goes when every entry that follows the statement goes with it",
     statement_over_first_then_run(),
     [("openrouter", "vendor/paid-%s" % letter, "gone") for letter in "abc"],
     [(PAID_REASON + IF_GROQ + PAID_A, IF_GROQ), ("  #\n" + PAID_B + "  #\n" + PAID_C, "")],
     {}),
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
                            "artificial_analysis_coding_index": coding,
                            "artificial_analysis_agentic_index": 1.0},
            "pricing": {"price_1m_input_tokens": price, "price_1m_output_tokens": price,
                        "price_1m_cache_hit_tokens": None, "price_1m_cache_write_tokens": None},
            "performance": {"median_output_tokens_per_second": None,
                            "median_time_to_first_token_seconds": None},
            "performance_v3": {"mean_output_tokens_per_second": speed,
                               "mean_time_to_first_token_seconds": 1.2,
                               "mean_time_to_first_answer_token_seconds": 1.2}}


RANKING_KEYS = dict(SELFTEST_KEYS, MODEL_DRIFT_ARTIFICIAL_ANALYSIS_API_KEY="selftest-artificial-analysis-key-SECRET")


def ranking_page(*aa_models, number=1, more=False):
    """One page of the free endpoint's answer, with its documented pagination block."""
    return {"tier": "free", "intelligence_index_version": 4.0,
            "pagination": {"page": number, "page_size": 200, "total_pages": number + more, "has_more": more},
            "data": list(aa_models)}


def ranking_answers(*aa_models, openrouter_extra=()):
    """Catalogues that list exactly what RANKING_TEMPLATE holds, plus the NEW OpenRouter models given
    as (id, label), and the ranking source's answer made of "aa_models"."""
    answers = answers_listing(RANKING_TEMPLATE)
    for identifier, label in openrouter_extra:
        model = openrouter_model(identifier)
        model["name"] = label
        answers["openrouter"]["data"].append(model)
    answers["rankings"] = ranking_page(*aa_models)
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
               (not any(url.startswith(RANKING_URL) for url, _ in calls), "the ranking source was called without a key"),
               ("rankings    not covered (no key): MODEL_DRIFT_ARTIFICIAL_ANALYSIS_API_KEY is unset" in report,
                "the report does not say the key is missing"),
               ("| Artificial Analysis (classements) | non couvert (pas de clé : secret "
                "`MODEL_DRIFT_ARTIFICIAL_ANALYSIS_API_KEY`) |" in body, "the coverage table does not say it"),
               ("## Classement des nouveaux modèles" not in body, "a table was written without figures"),
               (result["ranked"] == [], "rows were built from a source that was not read"),
               (exit_status(result) == 1 and is_complete(result), "the exit status or the coverage moved")))

    # A key: the figures, the matching said to be a guess, the places, the source named.
    result, calls, report, body = ranking_run(RANKING_KEYS, base)
    sent = [headers for url, headers in calls if url.startswith(RANKING_URL)]
    section = body.split("## Classement des nouveaux modèles")[1].split("\n## ")[0] if "## Classement des nouveaux modèles" in body else ""
    judged("with its key the NEW models get their figures, a guessed matching, a place per router and the source",
           first_wrong(
               (len(sent) == 1 and sent[0].get("x-api-key") == RANKING_KEYS["MODEL_DRIFT_ARTIFICIAL_ANALYSIS_API_KEY"],
                "the key was not sent once in x-api-key"),
               (not any("SECRET" in url for url, _ in calls), "a key was put in a URL"),
               ([url for url, _ in calls if url.startswith("https://artificialanalysis.ai/")]
                == ["https://artificialanalysis.ai/api/v2/language/models/free?page=1"],
                "the free endpoint was not asked for its first page, once"),
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

    # Pages: every page is asked for and read, in order, with the key, up to the one that says it is the last.
    whole = ranking_run(RANKING_KEYS, base)
    paged = dict(base, rankings=[ranking_page(top, mid, low, more=True),
                                 ranking_page(fresh, shiny, *twins, number=2)])
    result, calls, report, body = ranking_run(RANKING_KEYS, paged)
    asked = [(url, headers) for url, headers in calls if url.startswith(RANKING_URL)]
    judged("two pages of the ranking source are both read, in order, and give what one page holding them all gives",
           first_wrong(
               ([url for url, _ in asked] == [RANKING_URL + "?page=1", RANKING_URL + "?page=2"],
                "the pages asked for are %r" % [url for url, _ in asked]),
               (all(headers.get("x-api-key") == RANKING_KEYS["MODEL_DRIFT_ARTIFICIAL_ANALYSIS_API_KEY"]
                    for _, headers in asked), "a page was asked for without the key"),
               (result["rankings"]["status"] == "read" and len(result["rankings"]["models"]) == 7,
                "the models read are %r" % (result["rankings"],)),
               (body == whole[3] and report == whole[2], "the output differs from a single page's")))

    # The shape of the free tier: the speed under "performance_v3" (a top-level one is the retired
    # shape's, and the retired "performance" block is not read either), the blended price made of the
    # two published ones.
    legacy = ranking_model("legacy-model", "Legacy Model", 1, None, None, 1.0)
    legacy["median_output_tokens_per_second"] = 99.0
    retired = ranking_model("retired-model", "Retired Model", 1, None, None, 1.0)
    retired["performance"]["median_output_tokens_per_second"] = 77.0
    unmeasured = ranking_model("unmeasured-model", "Unmeasured Model", 1, None, None, 1.0)
    unmeasured["performance"]["median_output_tokens_per_second"] = 66.0
    unmeasured["performance_v3"] = None
    half_priced = ranking_model("half-model", "Half Model", 1, None, 10.0, 1.0)
    half_priced["pricing"]["price_1m_output_tokens"] = None
    blend = ranking_model("blend-model", "Blend Model", 1, None, 10.0, 1.0)
    blend["pricing"].update(price_1m_input_tokens=1.0, price_1m_output_tokens=5.0)
    shaped = ranking_model("shaped-model", "Shaped Model", 1, 2, 10.0, 1.0)
    shaped["performance_v3"], shaped["pricing"], shaped["evaluations"] = "fast", [], None
    models = {model["name"]: model for model in read_ranking_models(
        {"data": [legacy, retired, unmeasured, half_priced, blend, shaped,
                  ranking_model("fast-model", "Fast Model", 1, None, 42.5, 1.0)]})}
    judged("the speed is read from performance_v3, the blended price from the input and output prices, and a field of the wrong shape is none",
           first_wrong(
               (models["Fast Model"]["speed"] == 42.5, "the speed under performance_v3 was not read: %r" % models["Fast Model"]),
               (models["Legacy Model"]["speed"] is None, "a top-level speed was read"),
               (models["Retired Model"]["speed"] is None, "the retired performance block was read"),
               (models["Unmeasured Model"]["speed"] is None,
                "a model with no performance_v3 fell back on the retired block"),
               (models["Blend Model"]["price"] == 2.0, "the blend is %r, not 2.0" % models["Blend Model"]["price"]),
               (models["Half Model"]["price"] is None, "a price missing its output side was blended"),
               (all(models["Shaped Model"][key] is None for key in ("speed", "price", "intelligence", "coding")),
                "a field of the wrong shape gave a figure: %r" % models["Shaped Model"])))

    # Only an explicit true asks for another page: any other pagination block is the last page.
    for pagination in ({"has_more": "false"}, {"has_more": 1}, {"page": 1}, "more", ["has_more"], None):
        odd = dict(ranking_page(top), pagination=pagination)
        result, calls, report, body = ranking_run(RANKING_KEYS, dict(base, rankings=odd))
        judged("a pagination block of %r is the last page" % (pagination,), first_wrong(
            (len([url for url, _ in calls if url.startswith(RANKING_URL)]) == 1, "another page was asked for"),
            (result["rankings"]["status"] == "read" and len(result["rankings"]["models"]) == 1,
             "got %r" % (result["rankings"],))))

    # A source that never says it is done: stopped at MAX_PAGES and reported, not read in part.
    result, calls, report, body = ranking_run(RANKING_KEYS, dict(base, rankings=ranking_page(top, more=True)))
    judged("a page loop that never ends stops at MAX_PAGES and is reported, with nothing of what it read",
           first_wrong(
               (len([url for url, _ in calls if url.startswith(RANKING_URL)]) == MAX_PAGES,
                "the source was asked %d times" % len([url for url, _ in calls if url.startswith(RANKING_URL)])),
               (result["rankings"]["status"] == "error" and "still has pages after %d" % MAX_PAGES in result["rankings"]["error"],
                "got %r" % (result["rankings"],)),
               (result["rankings"]["models"] == [] and result["ranked"] == [], "a partial read was used"),
               ("rankings    ERROR, not read: " in report and "## Classements non lus" in body, "the failure is not reported"),
               (exit_status(result) == 1 and is_complete(result), "the failure moved the exit status or the coverage")))

    # A page that fails or is shaped wrongly after a good one fails the whole read.
    for purpose, pages, wanted in (
            ("a second page that answers 410 is reported as its status, and the first page's models are not kept",
             [ranking_page(top, more=True), urllib.error.HTTPError("https://selftest.invalid/", 410, "Gone", None, io.BytesIO(b""))],
             "HTTP 410"),
            ("a second page that holds no data list is reported, and the first page's models are not kept",
             [ranking_page(top, more=True), [top]], 'the answer holds no "data" list')):
        result, calls, report, body = ranking_run(RANKING_KEYS, dict(base, rankings=pages))
        judged(purpose, first_wrong(
            (result["rankings"]["status"] == "error" and wanted in result["rankings"]["error"], "got %r" % (result["rankings"],)),
            (result["rankings"]["models"] == [] and result["ranked"] == [], "models of the first page were kept"),
            (exit_status(result) == 1 and is_complete(result), "the failure moved the exit status or the coverage")))

    # Errors: reported, scrubbed, and never an error of the run.
    for purpose, answer, wanted in (
            ("a 401 whose body echoes the key is reported as its status, the key is gone, and the run goes on",
             leaky_401("artificial-analysis"), "HTTP 401"),
            ("a network error whose reason carries the key is reported with the key scrubbed",
             urllib.error.URLError("tunnel refused for selftest-artificial-analysis-key-SECRET"),
             "network error: tunnel refused for ***"),
            ("a 410, the status of the retired endpoint, is reported as its status",
             urllib.error.HTTPError("https://selftest.invalid/", 410, "Gone", None, io.BytesIO(b"")), "HTTP 410"),
            ("an answer that is a list and not an object is reported",
             [[]], 'the answer holds no "data" list'),
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
    ("the prose about the one model, above the statement that wraps its commented-out entry, goes "
     "with it and is no longer pointed at as a mention",
     statement_over_first(PAID_A_ONLY), [("openrouter", "vendor/paid-a", "gone")], []),
    ("the reason above a statement stays over the entries of the run that stay, and is pointed at",
     statement_over_run(), [("openrouter", "vendor/paid-a", "gone")],
     [("kept", "Served, but not routed to: paid only.", 1, None)]),
    ("prose above the statement that names a model which stays is pointed at, and left",
     statement_over_first(PAID_A_ONLY.replace("paid only", "paid only; alpha-groq is free")),
     [("openrouter", "vendor/paid-a", "gone")],
     [("left", "paid-a is not routed to: paid only; alpha-groq", 1, None)]),
    ("a reason that an entry which stays follows is pointed at too, and left",
     statement_over_first_then_run(), [("openrouter", "vendor/paid-a", "gone")],
     [("left", "Served, but not routed to: paid only.", 1, None)]),
    ("bare # lines above the statement are nobody's reason, and are not pointed at",
     ((PAID_REASON, "  #\n" + IF_GROQ), (PAID_C, PAID_C + ENDIF)),
     [("openrouter", "vendor/paid-%s" % letter, "gone") for letter in "abc"], []),
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
    # The reading behind that rule, called on its own: a result that is the same file with every
    # provider key given and another for the set that gives one provider alone is refused.
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
        answers["groq"] = GROQ_WITHOUT_FAST
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
    cases.append(("a cascade named by a Jinja expression is not named in a message of its own",
                  slots_text([("router_settings.fallbacks", "flash-lite"),
                              ("router_settings.fallbacks", JINJA_PLACEHOLDER)])
                  == "la cascade `flash-lite` de `router_settings.fallbacks`"
                  and slots_text([("router_settings.fallbacks", JINJA_PLACEHOLDER)])
                  == "`router_settings.fallbacks`"))
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

    groq_without_fast = GROQ_WITHOUT_FAST

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
        again, second, _, _, again_pr, _ = apply_run(new_text, changed(groq=groq_without_fast))
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
         changed(groq=groq_without_fast),
         deletes_fast, 1),
        ("a deletion that leaves nothing for a person to read has no section asking for it",
         SELFTEST_TEMPLATE,
         changed(groq=groq_without_fast),
         nothing_to_read, 1),
        ("one that leaves prose above the deleted entry lists it under \"À relire\"",
         SELFTEST_TEMPLATE.replace(
             "  - model_name: fast\n",
             "  # Prose about fast, which may as well be about its neighbours.\n"
             "  - model_name: fast\n", 1),
         changed(groq=groq_without_fast),
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
         changed(deepseek=leaky_401("deepseek"), groq=groq_without_fast),
         error_deletes_nothing_else, 2),
        ("a second run on the result finds nothing more to delete", SELFTEST_TEMPLATE,
         changed(groq=groq_without_fast), idempotent, 1),
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


def confirmation_cases():
    """(what the case proves, template, answers, a check on (result, new_text, report, issue, pr,
    commit) returning None when it holds and why not otherwise, the exit status expected): what a
    model that its provider's list omits is, once the provider has been asked for it."""
    def changed(**replaced):
        answers = selftest_answers()
        answers.update(replaced)
        return answers

    # Mistral's list without the model the template routes to, and the Gemini one likewise: each
    # still lists one other id, which is what the lookup is checked against.
    mistral_omitting = {"data": [{"id": "mistral-embed",
                                  "capabilities": {"completion_chat": False}}]}
    gemini_omitting = [{"models": [{"name": "models/text-embedding-9",
                                    "supportedGenerationMethods": ["embedContent"]}]}]

    def kept_and_said(label, config_name):
        def check(result, new_text, report, issue, pr, commit):
            if new_text != SELFTEST_TEMPLATE or pr is not None:
                return "a model its provider still serves was deleted"
            if any(finding["kind"] in ("retired", "gone")
                   for each in result["providers"] for finding in each["findings"]):
                return "a model its provider still serves is still a finding"
            if undeleted_count(result) != 0:
                return "a model that is not retired is counted as left to a person"
            block = report.split("SERVED")[1] if "SERVED" in report else ""
            if label not in block.split("\n\n")[0]:
                return "the report does not name the model as still served"
            section = issue.split("## Absents de la liste, mais toujours servis")
            if len(section) != 2 or "`%s` (`%s`)" % (label, config_name) not in section[1]:
                return "the issue does not name the model under the section for the served ones"
            return None
        return check

    def deleted_and_confirmed(result, new_text, report, issue, pr, commit):
        if "mistral/mistral-large-latest" in new_text or "model_name: large" in new_text:
            return "a model its provider says it does not know was not deleted"
        retired = [finding for each in result["providers"] for finding in each["findings"]
                   if finding["kind"] == "retired"]
        if len(retired) != 1 or retired[0].get("confirmed") is not True:
            return "the finding does not say that the provider confirmed the retirement"
        if "SERVED" in report:
            return "a deleted model is reported as still served"
        if pr is None or ("Interrogé sur ce modèle, le fournisseur répond qu'il n'existe pas."
                          not in " ".join(pr.split())):
            return "the pull request does not say that the provider was asked"
        return None

    def left_to_a_person(reason, french_reason=None):
        def check(result, new_text, report, issue, pr, commit):
            if new_text != SELFTEST_TEMPLATE or pr is not None:
                return "a deletion nobody confirmed was made"
            if undeleted_count(result) != 1:
                return "the model that was not deleted is not counted as left to a person"
            wanted = ("NOT DELETED, left to a person: its provider's list omits it, and asking the "
                      "provider for the model itself did not confirm that it is gone: " + reason)
            if wanted not in report:
                return "the report lacks %r" % wanted
            if "**non supprimé par le workflow** : la liste de son fournisseur l'omet" not in issue:
                return "the issue does not say, in French, that the workflow left it alone"
            if reason not in issue:
                return "the issue does not give the answer the provider made"
            return hostile_lines(report, issue) or (
                "a key reached the output"
                if any("SECRET" in (text or "") for text in (report, issue)) else None)
        return check

    def not_a_lookup_provider(result, new_text, report, issue, pr, commit):
        if "deepseek/deepseek-v9" in new_text:
            return "a retired model of a provider that cannot be asked was not deleted"
        retired = [finding for each in result["providers"] for finding in each["findings"]
                   if finding["kind"] == "retired"]
        if len(retired) != 1 or "confirmed" in retired[0] or "unconfirmed" in retired[0]:
            return "a provider that cannot be asked was given a confirmation"
        if pr is None or "Interrogé sur ce modèle" in pr:
            return "the pull request says a provider that cannot be asked was asked"
        return None

    return (
        ("a model the list omits but the provider serves is kept, and said to be served",
         SELFTEST_TEMPLATE,
         changed(mistral=mistral_omitting,
                 lookups={("mistral", "mistral-large-latest"): {"id": "mistral-large-latest"}}),
         kept_and_said("mistral/mistral-large-latest", "large"), 0),
        ("the same on Gemini, whose lookup is asked with the key in its own header",
         SELFTEST_TEMPLATE,
         changed(gemini=gemini_omitting,
                 lookups={("gemini", "gemini-9-flash"): {"name": "models/gemini-9-flash"}}),
         kept_and_said("gemini/gemini-9-flash", "flash"), 0),
        ("a model the provider says it does not know is deleted, and the pull request says it was asked",
         SELFTEST_TEMPLATE, changed(mistral=mistral_omitting), deleted_and_confirmed, 1),
        ("an answer that is not a 404 leaves the deletion to a person: HTTP 400",
         SELFTEST_TEMPLATE,
         changed(groq=GROQ_WITHOUT_FAST, lookups={("groq", "vendor/fast"): 400}),
         left_to_a_person("HTTP 400"), 1),
        ("an answer that is not a 404 leaves the deletion to a person: HTTP 503",
         SELFTEST_TEMPLATE,
         changed(groq=GROQ_WITHOUT_FAST, lookups={("groq", "vendor/fast"): 503}),
         left_to_a_person("HTTP 503"), 1),
        ("a lookup that fails on the network leaves the deletion to a person",
         SELFTEST_TEMPLATE,
         changed(groq=GROQ_WITHOUT_FAST,
                 lookups={("groq", "vendor/fast"): urllib.error.URLError("selftest-unreachable")}),
         left_to_a_person("network error: selftest-unreachable"), 1),
        ("a 200 that is not a model leaves the deletion to a person",
         SELFTEST_TEMPLATE,
         changed(groq=GROQ_WITHOUT_FAST, lookups={("groq", "vendor/fast"): ["not", "a", "model"]}),
         left_to_a_person("the answer is not an object"), 1),
        ("a 404 is not believed when the same route cannot find a model the list names",
         SELFTEST_TEMPLATE,
         changed(groq=GROQ_WITHOUT_FAST, lookups={("groq", "vendor/whisper-v9"): 404}),
         left_to_a_person("the lookup of the listed model vendor/whisper-v9 answered 404"), 1),
        ("nor when the list names no model of the same shape to try the route on",
         SELFTEST_TEMPLATE,
         changed(groq={"data": [{"id": "whisper-large-v9", "active": True}]}),
         left_to_a_person("no listed model of this shape to check the lookup against"), 1),
        ("a provider that cannot be asked about one model is deleted from as before",
         SELFTEST_TEMPLATE, changed(deepseek={"data": [{"id": "deepseek-other"}]}),
         not_a_lookup_provider, 1),
    )


def run_lookup_cases():
    """The lookup itself, apart from any template: the address it asks, the key it sends, how often
    it asks, and where it stops."""
    failures = 0

    def report_case(purpose, why):
        nonlocal failures
        if why is None:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s) -- %s" % (purpose, why))

    calls = []

    def listed_opener(url, headers):
        calls.append((url, dict(headers)))
        if url.rsplit("/", 1)[-1].startswith("listed"):
            return b'{"id": "x"}'
        raise http_error(404)

    headers = {"Authorization": "Bearer selftest-key-SECRET"}
    answer = ask_for(listed_opener, "groq", "vendor/a b?c#d", headers)
    expected = "https://api.groq.com/openai/v1/models/vendor/a%20b%3Fc%23d"
    report_case("an id is asked for with its slash kept and every character that would end the "
                "path encoded, and the key goes along",
                None if calls == [(expected, headers)] and answer == "absent"
                else "asked %r, answered %r" % (calls, answer))

    def finding(identifier, kind="retired"):
        return {"kind": kind, "id": identifier, "names": [identifier]}

    calls.clear()
    members = {"listed-plain", "vendor/listed-slashed", "other"}
    report = {"findings": [finding("gone-a"), finding("vendor/gone-b"), finding("gone-c"),
                           finding("new-one", kind="new"), finding("listed-plain")]}
    confirm_absences("mistral", report, {"members": members}, listed_opener, headers)
    asked = [url.split("/models/")[1] for url, _ in calls]
    report_case("the route is tried once per shape of id on a model the list names, and only the "
                "models the list omits are asked about",
                None if asked == ["listed-plain", "gone-a", "vendor/listed-slashed",
                                  "vendor/gone-b", "gone-c", "listed-plain"]
                else "asked %r" % asked)
    # "listed-plain" is a finding here too, because a list that names it and a finding that omits
    # it cannot both be true: the case is only about the order and the number of calls.

    calls.clear()
    report = {"findings": [finding("gone-%02d" % number) for number in range(LOOKUP_LIMIT + 4)]}
    confirm_absences("mistral", report, {"members": {"listed"}}, listed_opener, headers)
    confirmed = [each for each in report["findings"] if each.get("confirmed")]
    stopped = [each for each in report["findings"] if "too many to look up" in
               each.get("unconfirmed", "")]
    report_case("past the limit a provider is no longer asked, and what was not asked is left to a "
                "person",
                None if len(calls) == LOOKUP_LIMIT + 1 and len(confirmed) == LOOKUP_LIMIT
                and len(stopped) == 4 else "%d calls, %d confirmed, %d stopped"
                % (len(calls), len(confirmed), len(stopped)))

    # Without "--apply" nothing is refused, so the report itself says what the provider answered.
    answers = selftest_answers()
    answers.update(groq=GROQ_WITHOUT_FAST, lookups={("groq", "vendor/fast"): 400})
    result = run_online(SELFTEST_TEMPLATE, SELFTEST_KEYS, canned_opener(answers, []), "2026-01-01")
    text = render_text(result, "selftest")
    report_case("without --apply the report says that the provider's answer did not confirm it",
                None if ("not confirmed by asking the provider for the model itself: HTTP 400" in text
                         and "NOT DELETED" not in text)
                else "the report is %r" % text)

    calls.clear()
    report = {"findings": [finding("gone-a")]}
    confirm_absences("openrouter", report, {"members": {"listed"}}, listed_opener, headers)
    report_case("a provider whose API has no such lookup is not asked anything",
                None if not calls and "confirmed" not in report["findings"][0]
                and "unconfirmed" not in report["findings"][0] else "asked %r" % calls)
    return failures


def run_confirmation_cases():
    failures = 0
    for purpose, text, answers, check, status in confirmation_cases():
        outputs = apply_run(text, answers)
        result = outputs[0]
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


# Every shape build_additions() reads: a provider with active entries only, one with commented-out ones
# only, in a run it shares with another provider under one reason, one with both, an entry whose key is
# a literal and one whose base is no https address, which no proposal may be modelled on.
# "check_drift_publish_guard.py" plays the workflow's builder on it too.
ADDITIONS_TEMPLATE = """\
{% set has = {
  'Gemini': Artificial_Intelligence_LiteLLM_Gemini_API_key is string,
  'OpenRouter': Artificial_Intelligence_LiteLLM_OpenRouter_API_key is string
} %}
# drift-ignore: openrouter/vendor/set-aside:free -- turned down
model_list:
{% if has.Gemini %}
  - model_name: gem-one
    litellm_params:
      model: gemini/gem-one
      api_key: "os.environ/GEMINI_API_KEY"

  # Served, but not routed to: paid only.
  # - model_name: gem-paid
  #   litellm_params:
  #     model: gemini/gem-paid
  #     api_key: "os.environ/GEMINI_API_KEY"
{% endif %}
  # Cerebras: not routed to, a bank card is required.
  # - model_name: cb-one
  #   litellm_params:
  #     model: cerebras/cb-one
  #     api_key: "os.environ/CEREBRAS_API_KEY"
  #
  # - model_name: cb-two
  #   litellm_params:
  #     model: cerebras/cb-two
  #     api_key: "os.environ/CEREBRAS_API_KEY"
  #
  # - model_name: sn-one
  #   litellm_params:
  #     model: openai/sn-one
  #     api_base: "https://api.sambanova.ai/v1"
  #     api_key: "os.environ/SAMBANOVA_API_KEY"

{% if has.OpenRouter %}
  - model_name: free-one
    litellm_params:
      model: openrouter/vendor/one:free
      api_key: "os.environ/OPENROUTER_API_KEY"
{% endif %}
  - model_name: literal-key
    litellm_params:
      model: groq/vendor/literal
      api_key: "not-from-the-environment"

  - model_name: plain-http
    litellm_params:
      model: deepseek/plain
      api_base: "http://deepseek.invalid/v1"
      api_key: "os.environ/DEEPSEEK_API_KEY"

router_settings:
  fallbacks:
    - flash:
        - gem-one
        - free-one
"""


def proposal_answers(text=SELFTEST_TEMPLATE):
    """Catalogues that list what "text" holds, and one NEW model of every provider: three free on
    OpenRouter -- one the ranking matches for certain, one it matches onto an entry whose name marks
    a variant, one it does not know --, Cerebras' with no entry of its provider to model one on, and
    one per provider of a spelling the pull requests do not write (it starts with "~", or ends with
    "-"). The ranking also knows the Gemini one for certain, which does not make its free tier known."""
    answers = answers_listing(text)
    fresh = openrouter_model("vendor/fresh:free")
    fresh["name"] = "Vendor: Fresh @bob <img src=x> `x` ::error:: (free)"
    answers["openrouter"]["data"] += [fresh, openrouter_model("~vendor/odd:free"),
                                      openrouter_model("vendor/rough-cut:free"),
                                      openrouter_model("vendor/unmeasured:free")]
    answers["rankings"] = ranking_page(ranking_model("fresh", "Fresh", 40, 30, 200, 0.0),
                                       ranking_model("rough.cut", "Rough Cut (Reasoning)", 35, 25, 150, 0.0),
                                       ranking_model("gemini-10-pro", "Gemini 10 Pro", 60, 50, 100, 1.0))
    answers["gemini"][0]["models"] += [
        {"name": "models/gemini-10-pro", "displayName": "Gemini 10 Pro",
         "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-odd-", "supportedGenerationMethods": ["generateContent"]}]
    answers["groq"]["data"].append({"id": "vendor/quick", "active": True, "owned_by": "Vendor"})
    answers["mistral"]["data"].append({"id": "magistral-9", "capabilities": {"completion_chat": True}})
    answers["deepseek"]["data"].append({"id": "deepseek-v10"})
    answers["sambanova"]["data"].append({"id": "SN-Two"})
    answers["cerebras"]["data"].append({"id": "cb-new"})
    return answers


def proposal_run(text, answers, environment=RANKING_KEYS):
    result = run_online(text, environment, canned_opener(answers, []), "2026-01-01")
    return result, propose_additions(text, result)


def run_proposal_cases():
    """The two pull requests of additions: what is proposed in which, the files with the entries added,
    the bodies and their checklists, what the issue keeps, and what is refused."""
    failures = 0

    def judged(purpose, why):
        nonlocal failures
        if why is None:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s) -- %s" % (purpose, why))

    def first_wrong(*checks):
        return next((message for ok, message in checks if not ok), None)

    def ids(part):
        return [(item["provider"], item["id"]) for item in part["items"]]

    result, proposals = proposal_run(SELFTEST_TEMPLATE, proposal_answers())
    ready, to_verify = proposals["ready"], proposals["to_verify"]
    issue = render_issue_body(result, "selftest")
    unproposed = {(report["name"], finding["id"]): finding.get("unproposed") for report in result["providers"]
                  for finding in report["findings"] if finding["kind"] == "new"}
    missing = {(report["name"], finding["id"]): [what for what, _ in finding.get("missing", [])]
               for report in result["providers"] for finding in report["findings"] if finding["kind"] == "new"}
    judged("a model the run knows everything of is ready; one with a fact missing, whatever its provider, is to verify",
           first_wrong(
               (ids(ready) == [("openrouter", "vendor/fresh:free")], "ready: %r" % ids(ready)),
               (ids(to_verify) == [("openrouter", "vendor/rough-cut:free"), ("openrouter", "vendor/unmeasured:free"),
                                   ("sambanova", "SN-Two"), ("gemini", "gemini-10-pro"), ("groq", "vendor/quick"),
                                   ("mistral", "magistral-9"), ("deepseek", "deepseek-v10")],
                "to verify: %r" % ids(to_verify)),
               ([item["name"] for item in to_verify["items"]] == [
                   "rough-cut-free", "unmeasured-free", "sn-two-sambanova", "gemini-10-pro", "quick-groq",
                   "magistral-9", "deepseek-v10-direct"],
                "the names are %r" % [item["name"] for item in to_verify["items"]]),
               (missing[("openrouter", "vendor/fresh:free")] == [], "the ready model misses %r"
                % missing[("openrouter", "vendor/fresh:free")]),
               (missing[("openrouter", "vendor/rough-cut:free")] == ["match"], "an approximate match is not said"),
               (missing[("openrouter", "vendor/unmeasured:free")] == ["ranking"], "an unmeasured model is not said"),
               (missing[("gemini", "gemini-10-pro")] == ["free"], "a certain match made a free tier known"),
               (ready["complete"] and to_verify["complete"], "a kind is said incomplete")))
    judged("a model of a provider with no entry, or of a spelling the file is not written with, is left to the issue",
           first_wrong(
               ("aucune entrée de ce fournisseur" in (unproposed.get(("cerebras", "cb-new")) or ""),
                "cerebras: %r" % unproposed.get(("cerebras", "cb-new"))),
               ("forme" in (unproposed.get(("openrouter", "~vendor/odd:free")) or ""), "the odd id was proposed"),
               ("forme" in (unproposed.get(("gemini", "gemini-odd-")) or ""), "the odd Gemini id was proposed"),
               ("`cerebras/cb-new`" in issue and "pas proposé par pull request" in issue,
                "the issue does not list what is not proposed"),
               ("vendor/fresh:free" not in issue and "gemini-10-pro" not in issue and "rough-cut" not in issue,
                "the issue still lists a proposed model"),
               ("## Ajouts proposés par pull request" in issue and ": 1 modèle." in issue
                and "comment l'obtenir : 7 modèles." in issue, "the issue does not point at the pull requests"),
               (exit_status(result) == 1 and issue_status(result) == 1, "the statuses moved")))
    added = [line for line in difflib.ndiff(SELFTEST_TEMPLATE.split("\n"), to_verify["text"].split("\n"))
             if line.startswith(("+ ", "- "))]
    judged("each entry follows its provider's last entry, modelled on it, active or commented out like it",
           first_wrong(
               (not any(line.startswith("- ") for line in added), "a line of the file was changed: %r" % added[:3]),
               ('      api_key: "os.environ/OPENROUTER_API_KEY_SELFTEST"\n\n  # Proposed by the weekly drift run '
                'on 2026-01-01: listed free by "openrouter.ai/api/v1/models" that day.\n  - model_name: fresh-free\n'
                '    litellm_params:\n      model: openrouter/vendor/fresh:free\n'
                '      api_key: "os.environ/OPENROUTER_API_KEY_SELFTEST"\n' in ready["text"],
                "the OpenRouter entry is not after free-one"),
               ("fresh-free" not in ready["text"].split("\nrouter_settings:")[1], "a ready model was placed"),
               ('  #     api_key: "os.environ/SAMBANOVA_API_KEY_SELFTEST"\n\n  # Not routed to: proposed by the '
                'weekly drift run on 2026-01-01, its free tier on SambaNova not verified yet.\n'
                '  # - model_name: sn-two-sambanova\n  #   litellm_params:\n  #     model: openai/SN-Two\n'
                '  #     api_base: "https://api.sambanova.ai/v1"\n' in to_verify["text"],
                "the SambaNova entry is not a commented-out one after sn-one, with its base"),
               ("  - model_name: quick-groq\n    litellm_params:\n      model: groq/vendor/quick\n"
                '      api_key: "os.environ/GROQ_API_KEY_SELFTEST"' in to_verify["text"], "the Groq entry is wrong"),
               (addition_problem(SELFTEST_TEMPLATE, to_verify["text"], to_verify["items"]) is None
                and addition_problem(SELFTEST_TEMPLATE, ready["text"], ready["items"]) is None,
                "a file built does not read back")))
    body = to_verify["body"]

    def section(text, heading):
        return text.split(heading)[1].split("\n### ")[0].split("\n## ")[0] if heading in text else ""

    gemini = section(body, "### `gemini/gemini-10-pro`")
    samba = section(body, "### `openai/SN-Two`")
    rough = section(body, "### `openrouter/vendor/rough-cut:free`")
    unmeasured = section(body, "### `openrouter/vendor/unmeasured:free`")
    judged("the draft says, for each model, which page to open, what to look for, how to read the catalogue, "
           "what comment to write and what line sets it aside",
           first_wrong(
               (body.startswith("**Brouillon : à ne pas fusionner"), "the body does not start with the warning"),
               ("- [ ] **Gratuité.** Ouvrir <https://ai.google.dev/gemini-api/docs/pricing>" in gemini
                and "« Free Tier »" in gemini, "the Gemini page or what to look for is missing"),
               ('docker exec "$(docker ps --quiet --filter name=litellm | head -n 1)" python3 -c \'' in gemini
                and 'os.environ["GEMINI_API_KEY_SELFTEST"]' in gemini
                and "https://generativelanguage.googleapis.com/v1beta/models/gemini-10-pro" in gemini,
                "the Gemini command does not read the model with the key of the container"),
               ("python3 -c 'import json" in samba and '== "SN-Two"' in samba and "docker" not in samba,
                "the SambaNova command is not a keyless read of its list"),
               ('# Free per "ai.google.dev/gemini-api/docs/pricing", checked 2026-01-01' in gemini,
                "the comment to write is missing"),
               ('# Not routed to: <la raison>, per "cloud.sambanova.ai/plans", checked 2026-01-01.' in samba,
                "the commented-out entry's reason to write is missing"),
               ('# drift-ignore: gemini/gemini-10-pro -- not free per "ai.google.dev/gemini-api/docs/pricing" '
                "(read 2026-01-01)" in gemini, "the drift-ignore line is missing"),
               ("SECRET" not in body, "a key reached the body"),
               (body.endswith(PROPOSAL_SIGNATURE), "the body is not signed")))
    judged("an OpenRouter model to verify says which fact is missing, how to get it, and not to check its free tier",
           first_wrong(
               ("**Ce qui manque** :" in rough and "rapprochement vers une variante : « Rough Cut (Reasoning) »" in rough
                and "- [ ] **Rapprochement.** Ouvrir sa fiche sur <https://artificialanalysis.ai/>" in rough,
                "the approximate match is not said with how to check it: %s" % rough[:900]),
               ("- Gratuité : lue dans <https://openrouter.ai/api/v1/models>, le 2026-01-01 ; rien à vérifier." in rough
                and "**Gratuité.**" not in rough and "not free per" not in rough, "its free tier is to check"),
               ("  - Places suggérées :" in rough, "the places that can be computed are missing"),
               ("- [ ] **Classement.** Le chercher sur <https://artificialanalysis.ai/>" in unmeasured
                and "  # drift-ignore: openrouter/vendor/unmeasured:free -- no entry of the Artificial Analysis "
                "ranking measured it on 2026-01-01" in unmeasured, "the unmeasured model is not said so")))
    vbody = ready["body"]
    judged("the ready pull request names what it read, places nothing, and says the places are under revision",
           first_wrong(
               ("<https://openrouter.ai/api/v1/models?output_modalities=all>" in vbody, "the catalogue is not named"),
               ("- Gratuité : lue dans <https://openrouter.ai/api/v1/models>, le 2026-01-01." in vbody
                and "rapprochement sûr." in vbody and "qui ne porte aucune marque de variante" in vbody,
                "the facts it holds are not said"),
               ("**suggestions, calculées sur le classement actuel, qui est en cours de révision**" in vbody
                and "aucune cascade" in vbody, "the places are not said to be suggestions under revision"),
               ("drift-ignore: openrouter/vendor/fresh:free" not in vbody, "a ready model is set aside"),
               ("- [ ]" not in vbody, "the ready pull request has a checklist"),
               # The signature is the one link a body writes on purpose; the issue links pricing pages.
               (hostile_lines(vbody.replace(PROPOSAL_SIGNATURE, ""), body.replace(PROPOSAL_SIGNATURE, "")) is None,
                str(hostile_lines(vbody.replace(PROPOSAL_SIGNATURE, ""), body.replace(PROPOSAL_SIGNATURE, "")))),
               ("@bob" not in issue and "<img" not in issue and "::error" not in issue, "markup reached the issue"),
               (vbody.endswith(PROPOSAL_SIGNATURE), "the body is not signed")))
    judged("the commits say what they add, in English, under the issue",
           first_wrong(
               (ready["commit"].startswith("Propose the new LiteLLM models the weekly drift check knows everything "
                                           "of (#346)\n\n"), "the ready subject is wrong"),
               (to_verify["commit"].startswith("Propose the new LiteLLM models a person has to check before adding "
                                               "(#346)\n\n") and "openai/SN-Two" in to_verify["commit"],
                "the subject or the models are wrong: %s" % to_verify["commit"][:300])))

    # Decided: merged, or set aside. Neither comes back.
    merged = proposals["to_verify"]["text"]
    ignored = SELFTEST_TEMPLATE.replace(
        "  # drift-ignore: openrouter/vendor/noise:free", "  # drift-ignore: openrouter/vendor/fresh:free -- "
        "turned down\n  # drift-ignore: openrouter/vendor/noise:free")
    again, again_proposals = proposal_run(merged, proposal_answers())
    aside, aside_proposals = proposal_run(ignored, proposal_answers())
    judged("a model merged, or set aside by drift-ignore, is never proposed again",
           first_wrong(
               (ids(again_proposals["to_verify"]) == [], "merged models came back: %r" % ids(again_proposals["to_verify"])),
               (ids(again_proposals["ready"]) == [("openrouter", "vendor/fresh:free")], "the other kind moved"),
               (ids(aside_proposals["ready"]) == [], "a model set aside came back"),
               (len(aside_proposals["to_verify"]["items"]) == 7, "the other kind moved")))

    # Partial, and unreadable.
    partial, partial_proposals = proposal_run(SELFTEST_TEMPLATE, proposal_answers(),
                                              dict(RANKING_KEYS, MODEL_DRIFT_GROQ_API_KEY=""))
    unranked, unranked_proposals = proposal_run(SELFTEST_TEMPLATE, proposal_answers(), SELFTEST_KEYS)
    failed, failed_proposals = proposal_run(SELFTEST_TEMPLATE, dict(proposal_answers(), rankings=http_error(500)))
    unreadable = run_online("model_list: [unclosed\n", SELFTEST_KEYS, canned_opener(proposal_answers(), []),
                            "2026-01-01")
    nothing = propose_additions("model_list: [unclosed\n", unreadable)
    judged("a catalogue not read leaves its kind incomplete, and a file not read proposes nothing",
           first_wrong(
               (partial_proposals["ready"]["complete"] and not partial_proposals["to_verify"]["complete"],
                "the completeness is wrong"),
               (("groq", "vendor/quick") not in ids(partial_proposals["to_verify"]), "an unread model was proposed"),
               (not failed_proposals["ready"]["complete"] and failed_proposals["to_verify"]["complete"],
                "a ranking that failed leaves the ready pull request complete"),
               (unranked_proposals["ready"]["complete"] and ids(unranked_proposals["ready"]) == []
                and ("openrouter", "vendor/fresh:free") in ids(unranked_proposals["to_verify"]),
                "without the ranking a model is still ready"),
               (nothing == {"ready": {"complete": False, "items": []}, "to_verify": {"complete": False, "items": []}},
                "an unreadable file proposed something: %r" % nothing)))

    # The ranking: a model matched for certain is ready, with its suggested places; one the ranking does
    # not know is to verify, not placed, with its line; and the issue ranks neither.
    measured = ranking_answers(ranking_model("gem-top-model", "Gem Top Model", 70, 60, 100, 2.0),
                               ranking_model("groq-mid-model", "Groq Mid Model", 50, 45, 300, 0.5),
                               ranking_model("free-low-model", "Free Low Model", 30, 20, 200, 0.0),
                               ranking_model("fresh-model", "Fresh Model", 55, 70, 250, 1.5),
                               openrouter_extra=[("vendor/fresh-model:free", "Vendor: Fresh Model (free)"),
                                                 ("vendor/mystery-thing:free", "Vendor: Mystery")])
    ranked = run_online(RANKING_TEMPLATE, RANKING_KEYS, canned_opener(measured, []), "2026-01-01")
    ranked_proposals = propose_additions(RANKING_TEMPLATE, ranked)
    vbody = ranked_proposals["ready"]["body"]
    fresh = section(vbody, "### `openrouter/vendor/fresh-model:free`")
    mystery = section(ranked_proposals["to_verify"]["body"], "### `openrouter/vendor/mystery-thing:free`")
    judged("a model matched for certain is ready with its places, an unmeasured one is to verify and not placed",
           first_wrong(
               ("- Classement : intelligence 55.0, code 70.0, vitesse 250.0" in fresh
                and "rapprochement sûr" in fresh, "the figures are missing: %s" % fresh[:600]),
               ("  - `flash` : avant `groq-mid`" in fresh and "  - `code` : avant `gem-top`" in fresh,
                "the places are missing"),
               ("drift-ignore" not in fresh, "a measured model is offered a line to set it aside"),
               ("**Non placé**, faute de mesure : aucune entrée du classement ne s'écrit comme lui" in mystery
                and "  # drift-ignore: openrouter/vendor/mystery-thing:free -- no entry of the Artificial Analysis "
                "ranking measured it on 2026-01-01" in mystery, "the unmeasured model is placed: %s" % mystery[:600]),
               ("**approximatif**" in vbody, "the caveat of the matching is missing"),
               ("## Classement des nouveaux modèles" not in render_issue_body(ranked, "selftest"),
                "the issue still ranks the proposed models"),
               (issue_status(ranked) == 0 and exit_status(ranked) == 1,
                "a week whose only news is proposed does not leave the issue closed")))

    # The caps: entries per pull request, and the size of a body.
    many = answers_listing(RANKING_TEMPLATE)
    many["openrouter"]["data"] += [openrouter_model("vendor/m%02d:free" % number) for number in range(30)]
    capped_result = run_online(RANKING_TEMPLATE, SELFTEST_KEYS, canned_opener(many, []), "2026-01-01")
    capped_proposals = propose_additions(RANKING_TEMPLATE, capped_result)
    capped = capped_proposals["to_verify"]
    left = [finding.get("unproposed") for report in capped_result["providers"] for finding in report["findings"]
            if finding.get("unproposed")]
    global BODY_LIMIT
    kept_limit = BODY_LIMIT
    try:
        BODY_LIMIT = len(capped["body"]) - 1
        shrunk_result = run_online(RANKING_TEMPLATE, SELFTEST_KEYS, canned_opener(many, []), "2026-01-01")
        shrunk = propose_additions(RANKING_TEMPLATE, shrunk_result)
    finally:
        BODY_LIMIT = kept_limit
    judged("a pull request carries %d entries at most, and fewer when its body would be too long" % PROPOSAL_LIMIT,
           first_wrong(
               (len(capped["items"]) == PROPOSAL_LIMIT, "it carries %d" % len(capped["items"])),
               (len(left) == 30 - PROPOSAL_LIMIT and all("au-delà des 25" in reason for reason in left),
                "the rest is not left to the issue: %r" % left[:2]),
               (0 < len(shrunk["to_verify"]["items"]) < PROPOSAL_LIMIT
                and len(shrunk["to_verify"]["body"]) <= len(capped["body"]) - 1,
                "a body too long was not shortened"),
               (any("dépasserait la taille" in (finding.get("unproposed") or "") for report in shrunk_result["providers"]
                    for finding in report["findings"]), "what was dropped does not say why")))

    # What the job that writes refuses, refused here first.
    for purpose, items, kind, needle in (
            ("an id spelt otherwise", [{"provider": "openrouter", "id": "vendor/x:free\n- evil", "name": "x-free"}],
             "ready", "spelt like one"),
            ("a name spelt otherwise", [{"provider": "openrouter", "id": "vendor/x:free", "name": "X_Free"}],
             "ready", "spelt like the file's"),
            ("a name that is a word of the file", [{"provider": "openrouter", "id": "vendor/x:free", "name": "flash"}],
             "ready", "already a word"),
            ("a provider this does not read", [{"provider": "__proto__", "id": "vendor/x:free", "name": "x-free"}],
             "ready", "names no provider"),
            ("a model of a provider whose API does not state its free tier as ready",
             [{"provider": "gemini", "id": "gemini-x", "name": "gemini-x"}], "ready", "free tier, and only"),
            ("an OpenRouter id without \":free\", even to verify",
             [{"provider": "openrouter", "id": "vendor/x", "name": "x-free"}], "to_verify", 'does not end in ":free"'),
            ("an item with a key more", [{"provider": "openrouter", "id": "vendor/x:free", "name": "x-free",
                                           "api_key": "os.environ/X"}], "ready", "is not {provider, id, name}"),
            ("a provider with no entry to model one on", [{"provider": "cerebras", "id": "cb-x", "name": "cb-x-cerebras"}],
             "to_verify", "no entry of cerebras")):
        problem = build_additions(SELFTEST_TEMPLATE, "2026-01-01", kind, items)[1]
        judged("the entries are refused: %s" % purpose,
               None if problem and needle in problem else "refused for %r" % problem)

    # The file as written: where an entry goes, and what it may not be modelled on.
    mini = ADDITIONS_TEMPLATE
    cerebras, _ = build_additions(mini, "2026-01-01", "to_verify", [
        {"provider": "cerebras", "id": "cb-three", "name": "cb-three-cerebras"}])
    judged("an entry of a provider with commented-out entries only follows the whole run, commented out",
           None if cerebras and ('  #     api_key: "os.environ/SAMBANOVA_API_KEY"\n\n  # Not routed to: proposed '
                                 "by the weekly drift run on 2026-01-01, its free tier on Cerebras not verified "
                                 "yet.\n  # - model_name: cb-three-cerebras\n" in cerebras)
           and addition_problem(mini, cerebras, [{"provider": "cerebras", "id": "cb-three",
                                                  "name": "cb-three-cerebras"}]) is None
           else "it was not written after sn-one: %r" % (cerebras or "")[-900:])
    for purpose, base, kind, items, needle in (
            ("an id already a commented-out entry", mini, "to_verify",
             [{"provider": "cerebras", "id": "cb-two", "name": "fresh-cerebras"}], "is already an entry"),
            ("an id set aside by drift-ignore", mini, "ready",
             [{"provider": "openrouter", "id": "vendor/set-aside:free", "name": "fresh-free"}], "drift-ignore"),
            ("an entry whose key is not read from the environment", mini, "to_verify",
             [{"provider": "groq", "id": "vendor/fresh", "name": "fresh-groq"}], "not read from the environment"),
            ("an entry whose base is not https", mini, "to_verify",
             [{"provider": "deepseek", "id": "fresh", "name": "fresh-direct"}], "not a plain https address"),
            ("carriage returns", mini.replace("\n", "\r\n"), "ready",
             [{"provider": "openrouter", "id": "vendor/x:free", "name": "x-free"}], "plain line feeds"),
            ("more items than a pull request carries", mini, "ready",
             [{"provider": "openrouter", "id": "vendor/m%d:free" % number, "name": "m%d-free" % number}
              for number in range(PROPOSAL_LIMIT + 1)], "more than %d" % PROPOSAL_LIMIT),
            ("an id ending in a colon", mini, "ready",
             [{"provider": "openrouter", "id": "vendor/x:free:", "name": "x-free"}], "spelt like one")):
        problem = build_additions(base, "2026-01-01", kind, items)[1]
        judged("the entries are refused: %s" % purpose,
               None if problem and needle in problem else "refused for %r" % problem)
    entry_text = ("\n  - model_name: stray\n    litellm_params:\n      model: groq/vendor/stray\n"
                  '      api_key: "os.environ/GROQ_API_KEY_SELFTEST"\n')
    reasonless = SELFTEST_TEMPLATE.replace("\nrouter_settings:", "\n  # - model_name: stray\n  #   litellm_params:\n"
                                           "  #     model: groq/vendor/stray\n\nrouter_settings:")
    judged("a file that does not read back as the file plus the proposed entries is refused",
           first_wrong(
               ("gives no reason" in (addition_problem(SELFTEST_TEMPLATE, reasonless, []) or ""),
                "a commented-out entry without its reason was let through"),
               ("not the file's and the proposed ones" in (addition_problem(
                   SELFTEST_TEMPLATE, SELFTEST_TEMPLATE.replace("\nrouter_settings:", entry_text + "\nrouter_settings:"),
                   []) or ""), "an entry nobody proposed was let through")))
    taken = set(WORD.findall(SELFTEST_TEMPLATE))
    names = [addition_name("openrouter", identifier, taken)
             for identifier in ("vendor/same:free", "other/same:free", "third/same:free", "x/" + "y" * 150 + ":free")]
    judged("each name is free and spelt like the file's, a long one cut",
           None if names[:3] == ["same-free", "same-free-openrouter", "same-free-new"]
           and len(names[3]) <= ADDITION_NAME_LIMIT and ADDITION_NAME.fullmatch(names[3]) else "names %r" % names)

    # The issue keeps what the files break, and the commands read the right header and route.
    broken = SELFTEST_TEMPLATE.replace("  # Served at $0, but not routed to: a guardrail, not a generator.\n", "")
    rules = run_online(broken, SELFTEST_KEYS, canned_opener(dict(answers_listing(broken), openrouter={"data": [
        openrouter_model(i) for i in ("vendor/one:free", "vendor/paid-one", "vendor/paid-two",
                                      "vendor/guardrail:free", "vendor/new-one:free")]}), []), "2026-01-01")
    propose_additions(broken, rules)
    groq = to_verify["body"].split("### `groq/vendor/quick`")[1].split("\n### ")[0]
    judged("a file that breaks a rule keeps the issue open, whatever is proposed; each command its own header",
           first_wrong(
               (rules["rules"] and proposed(rules, "openrouter", "vendor/new-one:free") and issue_status(rules) == 1,
                "the issue would close over a broken rule"),
               ('"Authorization": "Bearer " + os.environ["GROQ_API_KEY_SELFTEST"]' in groq
                and "x-goog-api-key" not in groq and "https://api.groq.com/openai/v1/models/vendor/quick" in groq,
                "the Groq command is wrong"),
               ("models/a%3Ab" in catalogue_command("gemini", "a:b", "os.environ/GEMINI_API_KEY"),
                "an id is not quoted in its route")))

    # A model the ranking knows without a figure is not placed either.
    blank = ranking_answers(ranking_model("gem-top-model", "Gem Top Model", 70, 60, 100, 2.0),
                            ranking_model("blank-model", "Blank Model"),
                            openrouter_extra=[("vendor/blank-model:free", "Vendor: Blank Model (free)")])
    blanked = run_online(RANKING_TEMPLATE, RANKING_KEYS, canned_opener(blank, []), "2026-01-01")
    blank_proposals = propose_additions(RANKING_TEMPLATE, blanked)
    blank_body = blank_proposals["to_verify"]["body"]
    judged("a model the ranking knows with no figure is to verify, not placed, and gets its line",
           first_wrong(
               (blank_proposals["ready"]["items"] == [], "a model with no figure is ready"),
               ("**Non placé**, faute de mesure : le classement le connaît, sans aucun chiffre" in blank_body
                and "drift-ignore: openrouter/vendor/blank-model:free" in blank_body, "it was placed"),
               ("Aucune dérive." in render_issue_body(blanked, "selftest"),
                "an issue whose only news is proposed does not say there is no drift")))

    # A certain match, and nothing else, makes a model ready: not one by name after the id found two
    # entries, not one with no ranking at all, which the body says.
    twins = ranking_answers(ranking_model("twin-x", "Twin X Prime", 40, 30, 200, 0.0),
                            ranking_model("twin.x", "Other Twin", 20, 10, 100, 0.0),
                            openrouter_extra=[("vendor/twin-x:free", "Vendor: Twin X Prime (free)")])
    twinned = run_online(RANKING_TEMPLATE, RANKING_KEYS, canned_opener(twins, []), "2026-01-01")
    twin_proposals = propose_additions(RANKING_TEMPLATE, twinned)
    unread = section(unranked_proposals["to_verify"]["body"], "### `openrouter/vendor/fresh:free`")
    judged("a match by name after the id found two entries is not certain; an unread ranking is said so",
           first_wrong(
               (twin_proposals["ready"]["items"] == [] and len(twin_proposals["to_verify"]["items"]) == 1
                and "rapprochement par le nom seulement" in twin_proposals["to_verify"]["body"]
                and "rapproché par le nom : à vérifier" in twin_proposals["to_verify"]["body"],
                "a match by name made a model ready"),
               ("**Non placé** : le classement d'Artificial Analysis n'a pas été lu" in unread
                and "the Artificial Analysis ranking was not read on 2026-01-01" in unread,
                "an unread ranking is not said: %s" % unread[:600])))
    # What "certain" means, case by case: the same model spelt with other punctuation, by its slug or by
    # its name, is certain; two entries that spell alike, a digit apart, or a variant are not.
    certainty = ranking_answers(
        ranking_model("lfm3-1-7b", "LFM3-1.7B", 30, 20, 300, 0.0),
        ranking_model("amazon-nova-lite-v1", "Nova Lite", 30, 20, 300, 0.0),
        ranking_model("dup-model", "Dup Model", 30, 20, 300, 0.0),
        ranking_model("dup.model", "Another", 31, 21, 301, 0.0),
        ranking_model("cutter", "Cutter (Max)", 30, 20, 300, 0.0),
        ranking_model("mid-paren", "Mid (2026) Paren", 30, 20, 300, 0.0),
        openrouter_extra=[("liquid/lfm-3-1.7b:free", "LiquidAI: LFM3-1.7B (free)"),
                          ("liquid/lfm-3-1.8b:free", "LiquidAI: LFM3-1.8B (free)"),
                          ("vendor/nova-lite:free", "Vendor: Nova Lite (free)"),
                          ("vendor/dup_model:free", "Vendor: Dupe (free)"),
                          ("vendor/cutter:free", "Vendor: Cutter (free)"),
                          ("vendor/mid-paren:free", "Vendor: Mid Paren (free)")])
    certain_result = run_online(RANKING_TEMPLATE, RANKING_KEYS, canned_opener(certainty, []), "2026-01-01")
    certain_proposals = propose_additions(RANKING_TEMPLATE, certain_result)
    reasons = {finding["id"]: [sentence for _, sentence in finding.get("missing", [])]
               for report in certain_result["providers"] for finding in report["findings"] if finding["kind"] == "new"}
    judged("a match is certain on punctuation, by slug or by name, and only on one entry with no variant",
           first_wrong(
               (ids(certain_proposals["ready"]) == [("openrouter", "liquid/lfm-3-1.7b:free"),
                                                    ("openrouter", "vendor/mid-paren:free"),
                                                    ("openrouter", "vendor/nova-lite:free")],
                "ready: %r" % ids(certain_proposals["ready"])),
               (any("rapprochement ambigu" in reason for reason in reasons["vendor/dup_model:free"])
                and "- [ ] **Rapprochement.**" in section(certain_proposals["to_verify"]["body"],
                                                          "### `openrouter/vendor/dup_model:free`"),
                "two entries that spell alike: %r" % reasons["vendor/dup_model:free"]),
               (any("aucune entrée du classement" in reason for reason in reasons["liquid/lfm-3-1.8b:free"]),
                "a digit apart: %r" % reasons["liquid/lfm-3-1.8b:free"]),
               (any("rapprochement vers une variante : « Cutter (Max) »" in reason
                    for reason in reasons["vendor/cutter:free"]), "a variant: %r" % reasons["vendor/cutter:free"]),
               ("rapproché par l'identifiant : à vérifier" in section(certain_proposals["to_verify"]["body"],
                                                                      "### `openrouter/vendor/cutter:free`"),
                "a variant's figures are said to come from a certain match")))
    commented_only = ADDITIONS_TEMPLATE.replace(
        "  - model_name: free-one\n    litellm_params:\n      model: openrouter/vendor/one:free\n"
        '      api_key: "os.environ/OPENROUTER_API_KEY"\n',
        "  # Not routed to: a guardrail.\n  # - model_name: free-one\n  #   litellm_params:\n"
        '  #     model: openrouter/vendor/one:free\n  #     api_key: "os.environ/OPENROUTER_API_KEY"\n')
    problem = build_additions(commented_only, "2026-01-01", "ready",
                              [{"provider": "openrouter", "id": "vendor/b:free", "name": "b-free"}])[1]
    judged("a ready model of a provider with commented-out entries only is refused",
           None if commented_only != ADDITIONS_TEMPLATE and problem and "follows an active entry" in problem
           else "refused for %r" % problem)

    # The tables the bodies read, against the providers they serve.
    commands = [catalogue_command(name, "vendor/model-1", "os.environ/%s_API_KEY" % name.upper())
                for name in PROVIDER_NAMES]
    judged("each provider listed to verify has what to look for, and each command quotes nothing it should not",
           first_wrong(
               (set(FREE_TIER_CHECKS) == set(PRICING_PAGES), "FREE_TIER_CHECKS and PRICING_PAGES differ"),
               (set(FREE_CATALOGUES) == FREE_READABLE, "FREE_CATALOGUES and FREE_READABLE differ"),
               (all(command.count("'") == 2 for command in commands), "a command holds a quote of its own"),
               (all(("docker exec" in command) == keyed(name) for name, command in zip(PROVIDER_NAMES, commands)),
                "a keyed command does not run in the container, or a keyless one does")))
    return failures


def run_proposal_command_line_cases():
    """"--proposals" and "--issue-status" end to end: the files the workflow reads are written, and the
    ones of a run with nothing to propose are taken back."""
    failures = 0
    with tempfile.TemporaryDirectory() as directory:
        config = os.path.join(directory, "config.yaml.j2")
        folder = os.path.join(directory, "proposals")
        status_file = os.path.join(directory, "issue_status.txt")
        Path(config).write_text(SELFTEST_TEMPLATE, encoding="utf-8")
        arguments = ["--online", "--config", config, "--proposals", folder, "--issue-status", status_file]

        def run(answers, flags=arguments):
            environment = RANKING_KEYS if "rankings" in answers else SELFTEST_KEYS
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                try:
                    return main(flags, opener=canned_opener(answers, []), environment=environment)
                except SystemExit as error:
                    return error.code

        def files():
            return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

        status = run(proposal_answers())
        data = json.loads(Path(folder, "proposals.json").read_text(encoding="utf-8"))
        steps = [
            ("--proposals writes the data, and the body, commit and file of each pull request",
             status == 1 and files() == ["proposals.json", "ready_body.md", "ready_commit.txt",
                                         "ready_template.j2", "to_verify_body.md", "to_verify_commit.txt",
                                         "to_verify_template.j2"]
             and sorted(data) == ["date", "ready", "to_verify"]
             and data["ready"] == {"complete": True, "items": [
                 {"provider": "openrouter", "id": "vendor/fresh:free", "name": "fresh-free"}]}
             and Path(config).read_text(encoding="utf-8") == SELFTEST_TEMPLATE),
            ("--issue-status counts what no pull request carries",
             Path(status_file).read_text(encoding="utf-8") == "1\n"),
        ]
        only_new = answers_listing(SELFTEST_TEMPLATE)
        only_new["groq"]["data"] = [model for model in only_new["groq"]["data"] if model["id"] != "vendor/fast"]
        only_new["groq"]["data"].append({"id": "vendor/quick", "active": True})
        status = run(only_new, arguments + ["--apply"])
        steps += [
            ("--issue-status leaves out what a pull request carries, and --apply does not change what is proposed on",
             status == 1 and Path(status_file).read_text(encoding="utf-8") == "1\n"
             and "groq/vendor/fast" not in Path(config).read_text(encoding="utf-8")
             and "model: groq/vendor/fast" in Path(folder, "to_verify_template.j2").read_text(encoding="utf-8")),
        ]
        Path(config).write_text(SELFTEST_TEMPLATE, encoding="utf-8")
        only_new = answers_listing(SELFTEST_TEMPLATE)
        only_new["groq"]["data"].append({"id": "vendor/quick", "active": True})
        status = run(only_new)
        steps.append(("a run whose only news is proposed leaves the issue at 0",
                      status == 1 and Path(status_file).read_text(encoding="utf-8") == "0\n"))
        status = run(answers_listing(SELFTEST_TEMPLATE))
        data = json.loads(Path(folder, "proposals.json").read_text(encoding="utf-8"))
        steps += [
            ("a run with nothing to propose takes back the files of the last one",
             status == 0 and files() == ["proposals.json"]
             and data["ready"]["items"] == [] and data["to_verify"]["items"] == []
             and Path(status_file).read_text(encoding="utf-8") == "0\n"),
            ("--proposals without --online is refused", run({}, ["--config", config, "--proposals", folder]) == 2),
            ("--issue-status without --online is refused",
             run({}, ["--config", config, "--issue-status", status_file]) == 2),
        ]
    for purpose, passed in steps:
        if passed:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s)" % purpose)
    return failures


def run_command_line_cases():
    """The command line, end to end on a file in a temporary directory: it is written in place,
    writes the three texts, takes back the ones a run that deletes nothing would leave stale."""
    failures = 0
    answers = selftest_answers()
    answers["groq"] = GROQ_WITHOUT_FAST

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


# ------------------------------------------------------------------------------------------------
# The real model list. The cases above delete from small templates written for them; this one deletes
# from "templates/LiteLLM_config.yaml.j2" itself what a week's retirements could ask for, so that a
# shape of the file the deletion cannot take fails here and not in the weekly run, whose pull request
# merges itself. Nothing of the file is copied: what is held to is read off the file and its result.

REAL_PAIR_STEP = 4  # bound: one pair of neighbours in four, since a deletion costs what an entry does
REAL_CRLF_CASES = 2  # bound: the CRLF replay is of the first scenarios only


@contextlib.contextmanager
def quick_rendering():
    """A deletion renders the file for every set of keys, several times over, and parsing the results is
    most of the time: here a text is compiled and parsed once, by the C loader where there is one. The
    first rendering of a text is the plain one, which the quick one is held to."""
    import jinja2
    from jinja2.sandbox import SandboxedEnvironment
    environment = SandboxedEnvironment(undefined=jinja2.StrictUndefined, trim_blocks=True,
                                       keep_trailing_newline=True)
    plain, loaded = render_with_keys, yaml.safe_load
    rendered, compiled, parsed = {}, {}, {}

    def quick(text, given):
        return compiled[text].render({name: "" if given is not None and name not in given
                                      else "placeholder" for name in PROVIDER_KEY_VARIABLES})

    def render(text, given):
        key = (text, None if given is None else frozenset(given))
        if key not in rendered:
            if text in compiled:
                rendered[key] = quick(text, key[1])
            else:
                rendered[key] = plain(text, given)
                compiled[text] = environment.from_string(text)
                if quick(text, key[1]) != rendered[key]:
                    raise RuntimeError("the quick rendering is not the plain one")
        return rendered[key]

    def load(text):
        if text not in parsed:
            parsed[text] = yaml.load(text, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
        return parsed[text]

    globals()["render_with_keys"], yaml.safe_load = render, load
    try:
        yield
    finally:
        globals()["render_with_keys"], yaml.safe_load = plain, loaded


def real_scenarios(layout):
    """The sets of (provider, id) to delete: each entry alone, active or commented out; each run of
    commented-out entries whole and minus each of its members; each provider whole; the two ends of
    the list together; and the pairs of neighbours, one in REAL_PAIR_STEP."""
    keys = [entry["key"] for entry in sorted(layout["entries"], key=lambda entry: entry["start"])
            if entry["key"]]
    runs = [[layout["commented"][index]["key"] for index in run] for run in layout["runs"]]
    found = [{key} for key in keys] + [set(run) for run in runs]
    found += [set(run) - {key} for run in runs for key in run]
    found += [{key for key in keys if key[0] == provider} for provider in sorted({k[0] for k in keys})]
    found += [{keys[0], keys[-1]}] + [set(keys[n:n + 2]) for n in range(0, len(keys) - 1, REAL_PAIR_STEP)]
    return [chosen for number, chosen in enumerate(found) if chosen and chosen not in found[:number]]


def dangling(text):
    """What is wrong with the rendering of "text" for each set of keys: a set that does not render, a
    cascade slot or an alias that names no model."""
    found = set()
    for given, document in keyset_documents(text):
        where = "when only %s given" % given_text(given)
        if not isinstance(document, dict):
            found.add("the file does not render " + where)
            continue
        names = {item.get("model_name") for item in document.get("model_list") or []
                 if isinstance(item, dict)}
        found.update("%s names %s, which is no model, %s" % (place(group), name, where)
                     for group, targets in fallback_lists(document).items() for name in targets
                     if name not in names | {group[1]})
        found.update("the alias %s names %s, which is no model, %s" % (alias, target, where)
                     for section in SETTINGS_SECTIONS
                     for alias, target in ((document.get(section) or {}).get("model_group_alias")
                                           or {}).items() if target not in names)
    return found


def real_failure(text, keys, new_text, outcomes, layout, known):
    """Why the deletion of "keys" from "text" is wrong, or None. The entries asked for and their cascade
    slots go, of the rest only comments and blank lines may, and the comments are the reason of what
    went and the separators it leaves alone."""
    if [(o["provider"], o["id"]) for o in outcomes] != sorted(keys):
        return "the outcomes are not the keys asked for, one each"
    for o in outcomes:
        code = o["reason"] and o["reason"][0]
        if (o["status"] == "applied") != (o["reason"] is None) or (o["status"] == "refused") != bool(
                code in REFUSALS and refusal_text(o)) or (o["reason"] and (
                o["entries"] or o["slots"] or o["prose"] or o["review"])):
            return "the outcome of %s says %r with the reason %r" % (o["id"], o["status"], o["reason"])
        if code in ("verification", "unlocated"):
            return "%s is refused, and no shape of this file should be: %s" % (o["id"], o["reason"][1])
    applied = {(o["provider"], o["id"]) for o in outcomes if o["status"] == "applied"}
    if not applied:
        return None if new_text == text else "every deletion was refused and the file is not as it was"
    old, new = text.splitlines(), new_text.splitlines()
    gone = [entry for entry in layout["entries"] if entry["key"] in applied]
    names = {entry["name"] for entry in gone} - {entry["name"] for entry in layout["entries"]
                                                  if entry["key"] not in applied}
    slots = [ref["line"] for ref in layout["references"]
             if ref["role"] in ("target", "default") and ref["name"] in names]
    taken = {number for entry in gone for number in range(entry["start"], entry["end"])} | set(slots)
    rows = lambda source: {row["line"] for row in (read_head(source) or {}).values()}
    code = lambda lines, skipped: [line for number, line in enumerate(lines) if number not in skipped
                                   and line.strip() and not is_comment(line)]
    if code(old, taken | rows(text)) != code(new, rows(new_text)):
        return "the lines that are not comments are not the file's without the entries asked for"
    before = [line for number, line in enumerate(old) if is_comment(line) and number not in taken]
    after = [line for line in new if is_comment(line)]
    lost = collections.Counter(before) - collections.Counter(after)
    # Between two entries of a run, the bare lines go with a deleted one and stay between two that
    # stay; the rest of the comments that go are the prose the outcomes report.
    separators = 0
    for run in layout["runs"]:
        members = [layout["commented"][index] for index in run]
        away = [member["key"] in applied for member in members]
        for number in range(len(members) - 1):
            if away[number] or (away[number + 1] and all(away[number + 2:])):
                separators += sum(is_bare(line) for line in old[members[number]["end"]:
                                                               members[number + 1]["start"]])
    reported = sum(entry["lines"] for o in outcomes for entry in o["prose"])
    if not is_subsequence(after, before) or sum(lost.values()) != reported + separators:
        return "%d comment lines went, and %d were prose or separators of what was deleted" % (
            sum(lost.values()), reported + separators)
    # An active entry takes the blank line after it unless prose above it stays; no more than one
    # blank line goes for each entry.
    trailing = sum(entry["state"] == "active" and entry["end"] < len(old) and not old[entry["end"]].strip()
                   and not left_behind(layout, entry) for entry in gone)
    blanks = sum(not line.strip() for line in old) - sum(not line.strip() for line in new)
    if not trailing <= blanks <= len(gone) or (
            "\n\n\n" in new_text.replace("\r", "") and "\n\n\n" not in text.replace("\r", "")):
        return "%d blank lines went, and %d to %d were the deletion's" % (blanks, trailing, len(gone))
    if ("\r\n" in text and new_text.count("\n") != new_text.count("\r\n")) or (
            new_text.endswith("\n") != text.endswith("\n")):
        return "the result does not keep the line endings of the file"
    # A heading stays unless it is itself a reason; the prose directly above a run that goes whole goes.
    rules = [number for number, line in enumerate(old) if BANNER_RULE.match(line)]
    while len(rules) > 1:
        heading = old[rules[0] + 1:rules[1]]
        if all(is_comment(line) for line in heading):
            if not REASON.search(" ".join(map(comment_content, heading))) and any(
                    line in lost for line in heading if not is_bare(line)):
                return "the section heading at line %d went, and it is no reason" % (rules[0] + 2)
            rules.pop(0)
        rules.pop(0)
    for run in layout["runs"]:
        members = [layout["commented"][index] for index in run]
        above = old[members[0]["start"] - 1] if members[0]["start"] else ""
        if (all(member["key"] in applied for member in members) and is_comment(above)
                and not is_bare(above) and not BANNER_RULE.match(above)
                and not DRIFT_IGNORE_START.match(comment_content(above)) and above not in lost):
            return "the reason above the run at line %d stayed: %r" % (members[0]["start"] + 1, above)
    found = sorted((entry["name"], entry["state"], entry["start"] + 1) for entry in gone)
    said = sorted((item["name"], item["state"], item["line"]) for o in outcomes for item in o["entries"])
    if found != said or sum(len(o["slots"]) for o in outcomes) != len(slots):
        return "the entries and slots the outcomes name are not the ones that went"
    return next(iter(sorted(dangling(new_text) - known)), None)


def run_real_list_cases():
    """Each scenario of real_scenarios deleted from the real file (each key asked for twice, which is
    one deletion) and read back by real_failure; then the first of them with CRLF line endings."""
    failures = 0
    with quick_rendering():
        for ending, bound in (("\n", None), ("\r\n", REAL_CRLF_CASES)):
            text = CONFIG.read_text(encoding="utf-8").replace("\n", ending)
            template, problems = read_template(text)
            layout = read_layout(text, template)[0] if template else None
            if layout is None:
                print("selftest: FAILED (the real model list) -- it cannot be read: %s" % problems)
                return 1
            known = dangling(text)
            scenarios = real_scenarios(layout)
            for keys in scenarios[:bound]:
                wanted = [(provider, name, "gone") for provider, name in sorted(keys)] * 2
                new_text, outcomes = apply_removals(text, wanted)
                why = real_failure(text, keys, new_text, outcomes, layout, known)
                if why:
                    failures += 1
                    print("selftest: FAILED (deleting %s from the real model list%s) -- %s" % (
                        ", ".join(sorted("%s/%s" % key for key in keys)),
                        " with CRLF line endings" if ending != "\n" else "", why))
    if not failures:
        print("selftest: ok -- %d deletions from the real model list leave what they should"
              % len(scenarios))
    return failures


def run_selftest():
    """Prove that every rule refuses what it claims to refuse, and lets the baseline through."""
    # What the weekly workflow sets in the job that runs this check makes the issue carry a link to
    # the pull request, which the cases below do not expect: the selftest runs without them.
    kept = {name: os.environ.pop(name) for name in (
        "REMOVALS_BRANCH", "ADDITIONS_BRANCH", "ADDITIONS_TO_VERIFY_BRANCH", "GITHUB_SERVER_URL",
        "GITHUB_REPOSITORY", "GITHUB_RUN_ID")
        if name in os.environ}
    try:
        return run_selftest_cases()
    finally:
        os.environ.update(kept)


def run_pricing_page_cases():
    """The table of pricing pages against the providers it must serve: the real one first, then the
    ways it can go wrong, so that a provider added to PROVIDERS cannot be left without a page."""
    failures = 0
    pages = dict(PRICING_PAGES)
    without_groq = {name: url for name, url in pages.items() if name != "groq"}
    # The domain each page must be on, written out a second time on purpose: an address copied from
    # one provider's line onto another's, or one that points at a third party's article, is the
    # mistake a table of addresses invites, and nothing else would see it.
    own_domains = {"cerebras": "inference-docs.cerebras.ai", "sambanova": "cloud.sambanova.ai",
                   "gemini": "ai.google.dev", "groq": "console.groq.com", "mistral": "mistral.ai",
                   "deepseek": "api-docs.deepseek.com"}

    def foreign(table):
        return ["%s -> %s" % (name, urllib.parse.urlparse(url).hostname)
                for name, url in sorted(table.items())
                if urllib.parse.urlparse(url).hostname != own_domains.get(name)]

    for purpose, table, wrong in (
            ("each pricing page is on its own provider's domain", pages, []),
            ("an address copied onto another provider's line is refused",
             dict(pages, groq=pages["mistral"]), ["groq -> mistral.ai"]),
            ("a page of a third party is refused",
             dict(pages, groq="https://blog.example.invalid/groq-pricing"),
             ["groq -> blog.example.invalid"])):
        if foreign(table) == wrong:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s) -- foreign pages %r, expected %r"
                  % (purpose, foreign(table), wrong))

    cases = (
        ("the pricing pages cover exactly the providers whose free tier is not machine-readable",
         PROVIDER_NAMES, FREE_READABLE, pages, None),
        ("a provider with no pricing page is refused",
         PROVIDER_NAMES, FREE_READABLE, without_groq, "groq has no pricing page"),
        ("a provider added to PROVIDERS and not to the table is refused",
         PROVIDER_NAMES + ("newcomer",), FREE_READABLE, pages, "newcomer has no pricing page"),
        ("a page for the provider whose free tier is machine-readable is refused",
         PROVIDER_NAMES, FREE_READABLE, dict(pages, openrouter="https://example.invalid/"),
         "openrouter has a pricing page"),
        ("a page for a provider that does not exist is refused",
         PROVIDER_NAMES, FREE_READABLE, dict(pages, ghost="https://example.invalid/"),
         "ghost has a pricing page"),
        ("an address that is not https is refused",
         PROVIDER_NAMES, FREE_READABLE, dict(pages, groq="http://console.groq.com/docs/rate-limits"),
         "groq is not a plain https address"),
        ("an address with a space in it is refused",
         PROVIDER_NAMES, FREE_READABLE, dict(pages, groq="https://console.groq.com/a b"),
         "groq is not a plain https address"),
    )
    for purpose, providers, free_readable, table, needle in cases:
        problems = pricing_page_problems(providers, free_readable, table)
        if needle is None:
            passed = not problems
        else:
            passed = any(needle in problem for problem in problems)
        if passed:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s) -- expected %s, got %r"
                  % (purpose, "no problem" if needle is None else repr(needle), problems))
    return failures


# The router contracts, played on made-up records only: no figure of Artificial Analysis is held here.
# A template of five cascades over entries named after the alphabet, a contract for each router, and
# ranking records shaped to hit each verdict, each boundary and each way a mapping can go wrong.
CONTRACT_TEMPLATE = """\
model_list:
""" + "".join("""  - model_name: %s
    litellm_params:
      model: groq/vendor/%s-model
      api_key: "os.environ/GROQ_API_KEY_SELFTEST"

""" % (name, name) for name in (
    "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet", "kilo",
    "lima", "mike", "november", "oscar", "papa", "quebec", "romeo", "sierra")) + """\
router_settings:
  fallbacks:
    - pro: [alpha, charlie, delta, echo, india, juliet, foxtrot]
    - flash: [bravo, kilo, lima, hotel, golf, mike, papa, romeo]
    - flash-lite: [kilo, india, bravo, lima, quebec]
    - code: [alpha, delta, november, oscar, sierra]
    - claude-code: [alpha, echo, november, delta, quebec]
  model_group_alias:
    "pro": "alpha"
    "flash": "bravo"
    "flash-lite": "kilo"
    "code": "alpha"
    "claude-code": "alpha"
"""


def contract_router(anchor, rate, criterion="intelligence", last_resort=(), candidates=None):
    ranking = {"criterion": criterion, "reason": "selftest"}
    if criterion != "first_answer":
        ranking["tie_margin_points"] = 2
    if criterion == "code_quality":
        ranking.update(source="Epoch AI selftest source", source_status="read", stand_in="intelligence")
    contract = {"intelligence_floor": {"anchor": anchor, "reason": "selftest"},
                "level_gain": {"min_points_per_second": rate, "reason": "selftest"},
                "ranking": ranking, "last_resort": {"members": list(last_resort), "reason": "selftest"}}
    if candidates:
        contract["intelligence_floor"]["candidates"] = list(candidates)
    return contract


def contract_mapping(slug, level, tools="yes"):
    return {"slug": slug, "level": level, "level_source": "selftest",
            "tools": {"support": tools, "source": "selftest"}}


def contract_document():
    """The contracts the cases read: a fresh one at every call, since a case edits it."""
    return {
        "status": "provisional", "index_version": 5,
        "fallback_index": {"source": "Epoch selftest", "status": "not read yet", "method": "selftest",
                           "uncertainty": "selftest", "points": [[140, 4], [150, 20], [160, 20], [170, 50]]},
        "routers": {
            "pro": contract_router({"entry": "alpha", "level": "low"}, 0.2, last_resort=("juliet", "foxtrot"),
                                   candidates=({"entry": "sierra"}, {"entry": "alpha", "level": "low"},
                                               {"entry": "alpha", "level": "high"})),
            "flash": contract_router({"entry": "mike"}, 0.5,
                                     candidates=({"entry": "mike"}, {"entry": "charlie", "level": "non-reasoning"})),
            "flash-lite": contract_router({"entry": "india"}, 1.5, criterion="first_answer"),
            "code": contract_router({"entry": "alpha", "level": "low"}, 0.2, criterion="code_quality"),
            "claude-code": {"derives_from": "code", "requires": ["tools"], "reason": "selftest"},
        },
        "models": {
            "alpha": dict(contract_mapping("alpha-medium", "medium"), epoch={"deepswe_external": ["alpha_medium"]}),
            "bravo": contract_mapping("bravo", "n/a"),
            "charlie": contract_mapping("charlie", "unknown"),
            "delta": contract_mapping("delta-high", "medium"),
            "echo": contract_mapping("echo", "n/a"),
            "foxtrot": {"no_record": "a router: no record describes it",
                        "tools": {"support": "unknown", "source": "selftest"}},
            "golf": contract_mapping("golf-gone", "high"),
            "india": contract_mapping("india", "n/a"),
            "juliet": contract_mapping("juliet", "unknown"),
            "kilo": contract_mapping("kilo", "n/a"),
            "lima": contract_mapping("lima-high", "high"),
            "mike": contract_mapping("mike", "medium"),
            "november": contract_mapping("twin", "high", tools="no"),
            "oscar": contract_mapping("oscar", "high", tools="unknown"),
            "papa": contract_mapping("papa", "n/a"),
            "quebec": contract_mapping("quebec", "n/a", tools="unknown"),
            "romeo": contract_mapping("romeo", "n/a"),
            "sierra": contract_mapping("sierra", "n/a"),
        },
    }


def timed_model(slug, name, intelligence=None, first_answer=None, speed=100.0):
    model = ranking_model(slug, name, intelligence, None, speed)
    model["performance_v3"]["mean_time_to_first_answer_token_seconds"] = first_answer
    return model


def contract_records():
    """Ranking records for the contracts above: figures are (intelligence, seconds to the first answer
    token), and a family is told by the suffix of its names, as the real ones are."""
    return [
        timed_model("alpha-low", "Alpha (Low)", 20, 5), timed_model("alpha-medium", "Alpha (Medium)", 30, 12),
        timed_model("alpha-high", "Alpha (High)", 40, 25), timed_model("alpha", "Alpha (Xhigh)", 50, 60),
        timed_model("bravo", "Bravo @bob <img src=x> | `x` ::error::", 12, 4),
        timed_model("charlie", "Charlie (Reasoning)", 40, 20), timed_model("charlie-non", "Charlie (Non-reasoning)", 15, 2),
        timed_model("delta-low", "Delta (Low)", 12, 3), timed_model("delta-high", "Delta (High)", 45, 40),
        timed_model("echo", "Echo", None, 3), timed_model("india", "India", 8, 2),
        timed_model("juliet", "Juliet", None, 50), timed_model("kilo", "Kilo", 13.5, 6),
        timed_model("lima-high", "Lima (High)", 60, 90), timed_model("lima-low", "Lima (Low)", 15, 8),
        timed_model("mike", "Mike", 10, 20),
        timed_model("twin", "November One", 30, 5), timed_model("twin", "November Two", 31, 6),
        timed_model("oscar", "Oscar (High)", 50, 99), timed_model("papa", "Papa", 12, 1), timed_model("romeo", "Romeo", 9, 20),
        timed_model("quebec", "Quebec", 30, None), timed_model("sierra", "Sierra", 5, 50),
    ]


def contract_ranking(models=None, version=5.0):
    page = ranking_page(*(contract_records() if models is None else models))
    page["intelligence_index_version"] = version
    return {"status": "read", "date": "2026-01-01", "index_version": version,
            "models": read_ranking_models(page)}


def contract_rows(report, router):
    found = next(entry for entry in report["routers"] if entry["name"] == router)
    return {row["name"]: row for row in found["rows"]}, found


def run_contract_cases():
    failures = 0

    def judged(purpose, why):
        nonlocal failures
        if why is None:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s) -- %s" % (purpose, why))

    def first_wrong(*checks):
        return next((message for ok, message in checks if not ok), None)

    template, problems = read_template(CONTRACT_TEMPLATE)
    if template is None or problems:
        print("selftest: BROKEN CASE (the contracts' template) -- %r" % problems)
        return failures + 1
    document = contract_document()
    judged("the baseline contracts have no structural problem",
           first_wrong((contracts_problems(document, template) == [], "got %r" % contracts_problems(document, template))))

    # Reading a record's level from its name.
    judged("the level is the last parenthesis when it names one, and a name otherwise",
           first_wrong(
               (split_level("Gemini 4 Hydrogen (Low)") == ("Gemini 4 Hydrogen", "low"), "a plain level"),
               (split_level("Qwen (Non-reasoning)") == ("Qwen", "non-reasoning"), "non-reasoning"),
               (split_level("Model (Sep '25) (Reasoning)") == ("Model (Sep '25)", "reasoning"), "two parentheses"),
               (split_level("Model (Low, Default Fallback)") == ("Model (Low, Default Fallback)", None), "a fallback"),
               (split_level("Model (Xhigh)") == ("Model", "xhigh"), "xhigh"),
               (split_level("Model (Max)") == ("Model", "max"), "max"),
               (split_level("Model (Minimal)") == ("Model", "minimal"), "minimal"),
               (split_level("Plain Model") == ("Plain Model", None), "no parenthesis"),
               (split_level("Model  ( Low )") == ("Model", "low"), "blanks around a level"),
               (split_level("  Plain Model  ") == ("Plain Model", None), "blanks around a name")))
    judged("a time is a positive finite number of seconds, and anything else is none",
           first_wrong(
               (seconds_figure(1.5) == 1.5 and seconds_figure(3) == 3.0, "a time was refused"),
               (seconds_figure(0) is None and seconds_figure(-2) is None, "zero or less was taken for a time"),
               (seconds_figure("3") is None and seconds_figure(True) is None and seconds_figure(None) is None
                and seconds_figure(float("nan")) is None, "a non-number was taken for a time")))

    # The ranking keeps what the contracts need, and the rest as before.
    models = read_ranking_models(ranking_page(
        timed_model("some-slug", "Some Name", 33, 4.5, 80), timed_model("bad slug//", "Odd", 1, 0, 50),
        timed_model("no-time", "Slow", 1, "fast", 50)))
    judged("the ranking keeps the slug and the time to the first answer token beside its other figures",
           first_wrong(
               (models[0]["slug"] == "some-slug" and models[0]["first_answer"] == 4.5, "slug or time lost: %r" % models[0]),
               (models[0]["intelligence"] == 33.0 and models[0]["speed"] == 80.0 and models[0]["name"] == "Some Name",
                "a figure the other code reads was dropped"),
               (models[1]["slug"] == "" and models[1]["first_answer"] is None, "an unsafe slug or a zero time was kept"),
               (models[2]["first_answer"] is None, "a time that is no number was kept")))
    answers = ranking_answers(ranking_model("m", "M", 1, 1, 1))
    answers["rankings"]["intelligence_index_version"] = 5.0
    result, _, _, _ = ranking_run(RANKING_KEYS, answers)
    judged("the version of the index the ranking was read at is kept",
           first_wrong((result["rankings"]["index_version"] == 5.0, "got %r" % result["rankings"].get("index_version"))))

    # The level a router keeps: climb while the next level buys at least the router's gain.
    family = ranking_families(read_ranking_models(ranking_page(*contract_records())))[1]["alpha"]
    hydra = ranking_families(read_ranking_models(ranking_page(
        timed_model("hy-xhigh", "Hy (Xhigh)", 53, 40), timed_model("hy-low", "Hy (Low)", 26, 8),
        timed_model("hy-high", "Hy (High)", 50, 20), timed_model("hy-medium", "Hy (Medium)", 41, 12),
        timed_model("sun-low", "Sun (Low)", 22.5, 5), timed_model("sun-medium", "Sun (Medium)", 30, 9),
        timed_model("sun-high", "Sun (High)", 30.8, 15),
        timed_model("zed-low", "Zed (Low)", None, 1), timed_model("zed-medium", "Zed (Medium)", 10, 2),
        timed_model("zed-high", "Zed (High)", 30, 3), timed_model("nil-low", "Nil (Low)", None, 1),
        timed_model("wil-low", "Wil (Low)", 10, None), timed_model("wil-medium", "Wil (Medium)", 30, 5),
        timed_model("fast-low", "Fast (Low)", 10, 5), timed_model("fast-medium", "Fast (Medium)", 20, 5),
        timed_model("fast-high", "Fast (High)", 25, 4),
        timed_model("flat-low", "Flat (Low)", 20, 5), timed_model("flat-medium", "Flat (Medium)", 20, 9))))[1]

    def kept(name, rate):
        record = chosen_level(hydra[name], rate)
        return record and record["level"]

    judged("the level kept climbs while each extra second buys at least the rate asked, the first step that buys less being the last, whatever the order the records come in",
           first_wrong(
               # Hy: Low to Medium 3.75 points a second, Medium to High 1.125, High to Xhigh 0.15.
               (kept("hy", 0.1) == "xhigh", "a rate of 0.1 does not climb Hy to the top: %r" % kept("hy", 0.1)),
               (kept("hy", 0.2) == "high", "a rate of 0.2 does not stop Hy at High: %r" % kept("hy", 0.2)),
               (kept("hy", 2) == "medium", "a rate of 2 does not stop Hy at Medium: %r" % kept("hy", 2)),
               (kept("hy", 4) == "low", "a rate of 4 does not keep Hy at Low: %r" % kept("hy", 4)),
               (kept("hy", 3.75) == "medium", "a step that buys exactly the rate asked is not taken"),
               (kept("hy", 0) == "xhigh", "a rate of 0 does not climb to the top"),
               (kept("sun", 0.2) == "medium" and kept("sun", 2) == "low", "Sun: %r, %r" % (kept("sun", 0.2), kept("sun", 2))),
               (kept("zed", 5) == "high" and kept("zed", 25) == "medium", "a level with no index was climbed from or through: %r" % kept("zed", 5)),
               (kept("nil", 0) is None, "a family with no index keeps a level"),
               (kept("wil", 0) == "low", "a step whose time is unknown was taken: %r" % kept("wil", 0)),
               (kept("fast", 1000) == "high", "a step that is no slower, or faster, and buys points was refused: %r" % kept("fast", 1000)),
               (kept("flat", 0) == "low", "a step that buys no points was taken: %r" % kept("flat", 0)),
               (chosen_level(family, 0.28)["level"] == "xhigh" and chosen_level(family, 0.3)["level"] == "high"
                and chosen_level(family, 0.8)["level"] == "medium" and chosen_level(family, 1.5)["level"] == "low", "alpha"),
               (chosen_level([], 1) is None, "an empty family keeps a level")))

    def tie_rows(*figures):
        return [{"position": number, "name": name, "intelligence": quality, "first_answer": seconds,
                 "record": {"intelligence": quality, "first_answer": seconds}}
                for number, (name, quality, seconds) in enumerate(figures)]

    judged("members less than the margin apart in quality are ordered by time, the shortest first, one with no time last, and a gap of exactly the margin starts a new group",
           first_wrong(
               ([row["name"] for row in time_ties(tie_rows(("a", 30, 9), ("b", 29, 3), ("c", 28.5, None), ("d", 28.2, 1)), 2)]
                == ["d", "b", "a", "c"], "a group of four"),
               ([row["name"] for row in time_ties(tie_rows(("a", 30, 9), ("b", 28, 3)), 2)] == ["a", "b"], "a gap of exactly 2 joined the group"),
               ([row["name"] for row in time_ties(tie_rows(("a", 30, 9), ("b", 29.9, 3), ("c", 27.5, 1)), 2)] == ["b", "a", "c"],
                "the group of the next member is measured from the best of the previous one"),
               ([row["name"] for row in time_ties(tie_rows(("a", 30, 5), ("b", 30, 5)), 2)] == ["a", "b"], "equal times left the current order"),
               (time_ties([], 2) == [], "no member")))

    report = contracts_report(template, contract_ranking(), document)
    pro, pro_order = contract_rows(report, "pro")
    flash, flash_order = contract_rows(report, "flash")
    lite, lite_order = contract_rows(report, "flash-lite")
    code, code_order = contract_rows(report, "code")
    claude, claude_order = contract_rows(report, "claude-code")

    judged("a member that reaches the floor conforms whatever its time, with its figures, the level it is called at and the level the router would keep",
           first_wrong(
               (pro["alpha"]["kind"] == "conforming" and pro["alpha"]["verdict"] == "conforme", "alpha: %r" % pro["alpha"]["verdict"]),
               (pro["alpha"]["record"]["slug"] == "alpha-medium" and pro["alpha"]["record"]["intelligence"] == 30.0
                and pro["alpha"]["record"]["first_answer"] == 12.0, "alpha's record is not the medium one"),
               (pro["alpha"]["kept"]["slug"] == "alpha" and code["alpha"]["kept"]["slug"] == "alpha", "alpha is not kept at xhigh, 0.2 points a second"),
               (flash["lima"]["kind"] == "conforming" and flash["lima"]["verdict"] == "conforme", "a slow member was refused: %r" % flash["lima"]["verdict"]),
               (code["oscar"]["kind"] == "conforming" and code["oscar"]["verdict"] == "conforme", "oscar, at 99 s: %r" % code["oscar"]["verdict"]),
               (flash["lima"]["kept"]["slug"] == "lima-high", "lima's level was not kept at high, 45 points for 82 s"),
               (flash["bravo"]["kept"]["slug"] == "bravo", "a family of one has no level to keep")))
    judged("a member exactly at the floor conforms, one under it goes to the last resort tier and is not refused",
           first_wrong(
               (flash["mike"]["kind"] == "conforming", "mike, at the floor of 10, is refused: %r" % flash["mike"]["verdict"]),
               (pro["india"]["kind"] == "below_floor" and pro["india"]["verdict"] == "sous le plancher (8.0 contre 20) : dernier recours",
                "india: %r" % pro["india"]["verdict"]),
               (flash["romeo"]["kind"] == "below_floor" and flash["romeo"]["verdict"] == "sous le plancher (9.0 contre 10) : dernier recours",
                "romeo: %r" % flash["romeo"]["verdict"]),
               (code["sierra"]["kind"] == "below_floor" and code["sierra"]["verdict"] == "sous le plancher (5.0 contre 20) : dernier recours",
                "sierra, slow and weak, is under the floor and nothing more: %r" % code["sierra"]["verdict"])))
    judged("a model with no index cannot be ranked; one with no time cannot be placed only where the router is ordered by time",
           first_wrong(
               (pro["echo"]["kind"] == "unrankable" and pro["echo"]["verdict"] == "inclassable : pas d'indice",
                "echo: %r" % pro["echo"]["verdict"]),
               (lite["quebec"]["kind"] == "unrankable" and lite["quebec"]["verdict"] == "inclassable : pas de délai",
                "quebec in flash-lite: %r" % lite["quebec"]["verdict"]),
               (claude["quebec"]["kind"] == "conforming" and claude["quebec"]["verdict"] == "conforme ; appels d'outils inconnus",
                "quebec in claude-code, whose order does not need its time: %r" % claude["quebec"]["verdict"]),
               (claude["quebec"]["kept"]["slug"] == "quebec", "the level of a record with no time was lost")))
    judged("the last resort is exempt from the floor",
           first_wrong(
               (pro["juliet"]["last_resort"] and pro["juliet"]["kind"] == "conforming"
                and pro["juliet"]["verdict"] == "conforme (dernier recours)",
                "juliet, with no index, in the last resort: %r" % pro["juliet"]["verdict"]),
               (not pro["alpha"]["last_resort"], "a member was taken for the last resort")))
    judged("an unknown level is unverified where the family has several levels, and no more where it has one; a called level the ranking lacks is unverified",
           first_wrong(
               (pro["charlie"]["verdict"] == "variante non vérifiée" and pro["charlie"]["found"]["unverified"] == "unknown",
                "charlie: %r" % pro["charlie"]["verdict"]),
               (pro["delta"]["verdict"] == "variante non vérifiée" and pro["delta"]["found"]["unverified"] == "uncovered",
                "delta: %r" % pro["delta"]["verdict"]),
               (lite["bravo"]["found"]["unverified"] is None and lite["bravo"]["kind"] == "conforming", "a level that does not apply is unverified"),
               (flash["mike"]["found"]["unstated"] and flash["mike"]["found"]["unverified"] is None,
                "a single record whose level is not stated was refused for the level called"),
               (not pro["alpha"]["found"]["unstated"], "a record that states its level is said not to")))
    judged("a record is the one at the level called, even when the mapping names another",
           first_wrong(
               (flash["lima"]["record"]["slug"] == "lima-high", "lima: %r" % flash["lima"]["record"]["slug"]),
               (code["delta"]["record"]["slug"] == "delta-high", "an unverified entry lost its mapped record")))
    by_slug, families = ranking_families(read_ranking_models(ranking_page(
        *contract_records(), timed_model("foo", "Foo", 5, 1), timed_model("foo-low", "Foo (Low)", 6, 2))))
    wrong_slug = describe_entry(contract_mapping("lima-low", "high"), by_slug, families)
    alone = describe_entry(contract_mapping("oscar", "medium"), by_slug, families)
    mixed = describe_entry(contract_mapping("foo", "medium"), by_slug, families)
    judged("an entry is described by the record of the level it is called at whichever record its slug names; a family with one record that states its level, or with an unlabeled record among others, does not cover another level",
           first_wrong(
               (wrong_slug["record"]["slug"] == "lima-high" and wrong_slug["unverified"] is None, "the record of the slug was kept: %r" % wrong_slug["record"]["slug"]),
               (alone["unverified"] == "uncovered" and not alone["unstated"], "a single record that states High covers medium"),
               (mixed["unverified"] == "uncovered" and not mixed["unstated"], "an unlabeled record among others covers medium")))
    fewer = contracts_report(read_template(CONTRACT_TEMPLATE.replace("    - claude-code: [alpha, echo, november, delta, quebec]\n", ""))[0],
                             contract_ranking(), document)
    without_lite = contract_document()
    del without_lite["routers"]["flash-lite"]
    judged("a router with no cascade in the template, or with no contract, is left out of the report",
           first_wrong(
               ([entry["name"] for entry in fewer["routers"]] == ["pro", "flash", "flash-lite", "code"], "no cascade: %r" % [e["name"] for e in fewer["routers"]]),
               ([entry["name"] for entry in contracts_report(template, contract_ranking(), without_lite)["routers"]]
                == ["pro", "flash", "code", "claude-code"], "no contract")))

    def derivation_text(**changes):
        differences = {"extra": [], "refused": [], "missing": [], "unordered": False, "unknown": []}
        differences.update(changes)
        return derivation_lines({"name": "c", "base": "b", "differences": differences})

    judged("a derived cascade is said to be the one it derives from only when no difference is left, a member of unknown tools being no difference",
           first_wrong(
               (derivation_text()[0].startswith("La cascade de `c` est la cascade de `b`"), "no difference, and not said so"),
               (derivation_text(unknown=["u"])[0].startswith("La cascade de `c` est la cascade de `b`"), "a member of unknown tools is a difference"),
               *[(derivation_text(**{key: value})[0].startswith("La cascade de `c` n'est **pas** la cascade de `b`"), "%s is no difference" % key)
                 for key, value in (("extra", ["x"]), ("refused", ["x"]), ("missing", ["x"]), ("unordered", True))]))
    judged("a name the file does not map, a slug the ranking lost, an ambiguous slug and a model with no record are each said",
           first_wrong(
               (flash["hotel"]["kind"] == "unmapped" and flash["hotel"]["verdict"] == "sans correspondance", "hotel: %r" % flash["hotel"]["verdict"]),
               (flash["golf"]["kind"] == "stale" and flash["golf"]["verdict"] == "correspondance périmée", "golf: %r" % flash["golf"]["verdict"]),
               (code["november"]["kind"] == "stale", "a slug two records share was believed"),
               (pro["foxtrot"]["kind"] == "no_record" and pro["foxtrot"]["verdict"] == "sans enregistrement", "foxtrot: %r" % pro["foxtrot"]["verdict"]),
               (report["unmapped"] == ["hotel"], "unmapped: %r" % report["unmapped"]),
               (report["no_record"] == ["foxtrot"], "no record: %r" % report["no_record"]),
               (report["stale"] == [("golf", "golf-gone"), ("november", "twin")], "stale: %r" % report["stale"]),
               ([name for name, _ in report["uncovered"]] == ["delta"], "uncovered: %r" % report["uncovered"])))
    judged("the order the contract gives puts the conforming first, by quality with the time deciding within the margin or by time alone for flash-lite, then the last resort tier, and leaves the rest out",
           first_wrong(
               (pro_order["proposed"] == ["alpha", "india", "juliet", "foxtrot"], "pro: %r" % pro_order["proposed"]),
               (flash_order["proposed"] == ["lima", "papa", "bravo", "kilo", "mike", "romeo"], "flash: %r" % flash_order["proposed"]),
               (lite_order["proposed"] == ["india", "bravo", "kilo", "lima"], "flash-lite goes by time: %r" % lite_order["proposed"]),
               (code_order["proposed"] == ["oscar", "alpha", "sierra"], "code: %r" % code_order["proposed"]),
               (claude_order["proposed"] == ["alpha", "quebec"], "claude-code: %r" % claude_order["proposed"]),
               (flash_order["current"] == ["bravo", "kilo", "lima", "hotel", "golf", "mike", "papa", "romeo"], "the current order moved"),
               (report["provisional"] and report["version"] == 5.0 and report["wanted_version"] == 5.0, "the header facts")))
    def played(order):
        return [{key: value for key, value in effect.items() if key != "text"} for effect in order["floors"]]

    judged("each floor a contract proposes is played side by side, each named by the record it is the index of: who stays in front, who goes to the last resort tier",
           first_wrong(
               (played(pro_order) == [{"floor": 5, "main": ["alpha", "india"], "last": ["juliet", "foxtrot"]},
                                      {"floor": 20, "main": ["alpha"], "last": ["india", "juliet", "foxtrot"]},
                                      {"floor": 40, "main": [], "last": ["alpha", "india", "juliet", "foxtrot"]}],
                "pro: %r" % played(pro_order)),
               ([effect["text"] for effect in pro_order["floors"]] == ["Sierra", "Alpha (Low)", "Alpha (High)"],
                "the anchors are not named: %r" % [effect["text"] for effect in pro_order["floors"]]),
               (played(flash_order) == [{"floor": 10, "main": ["lima", "papa", "bravo", "kilo", "mike"], "last": ["romeo"]},
                                        {"floor": 15, "main": ["lima"], "last": ["bravo", "kilo", "mike", "papa", "romeo"]}],
                "flash: %r" % played(flash_order)),
               (played(lite_order) == [{"floor": 8, "main": ["india", "bravo", "kilo", "lima"], "last": []}],
                "a contract with no candidates is played at its own floor: %r" % played(lite_order))))
    anchor_slugs, anchor_families = ranking_families(contract_ranking()["models"])

    def anchored(entry, level=None):
        return anchor_floor(dict({"entry": entry}, **({"level": level} if level else {})), document["models"], anchor_slugs, anchor_families)

    judged("an anchor is read from the ranking: the record of the entry, or the level of its family that it names; one that cannot be read has no value and says why",
           first_wrong(
               (anchored("alpha") == (30.0, "Alpha (Medium)"), "the record of the entry: %r" % (anchored("alpha"),)),
               (anchored("alpha", "high") == (40.0, "Alpha (High)"), "a level of the family: %r" % (anchored("alpha", "high"),)),
               (anchored("alpha", "low") == (20.0, "Alpha (Low)"), "the lowest level: %r" % (anchored("alpha", "low"),)),
               (anchored("echo") == (None, "Echo : pas d'indice"), "an entry whose record has no index: %r" % (anchored("echo"),)),
               (anchored("alpha", "max")[0] is None and "pas de niveau max" in anchored("alpha", "max")[1], "a level the family lacks"),
               (anchored("zulu")[0] is None and "aucun enregistrement associé" in anchored("zulu")[1], "an entry with no mapping"),
               (anchored("golf")[0] is None and "enregistrement introuvable" in anchored("golf")[1], "an entry whose record left the ranking"),
               (anchored("foxtrot")[0] is None, "an entry that is a router, with no record")))
    unread = contract_document()
    unread["routers"]["pro"]["intelligence_floor"]["anchor"] = {"entry": "echo"}
    unread_report = contracts_report(template, contract_ranking(), unread)
    unread_pro, unread_order = contract_rows(unread_report, "pro")
    unread_section = "\n".join(contracts_section({"contracts": unread_report}))
    judged("a floor whose anchor cannot be read judges nothing: no member is under it, the floor has no value, the candidates still readable are compared, and the issue says that the anchor is not found",
           first_wrong(
               (unread_order["contract"]["intelligence_floor"]["value"] is None, "a floor of an unreadable anchor has a value"),
               (not any(row["kind"] == "below_floor" for row in unread_pro.values()), "a member was put under a floor that is not there"),
               ([effect["text"] for effect in unread_order["floors"]] == ["Sierra", "Alpha (Low)", "Alpha (High)"],
                "the candidates, which can still be read, were not compared: %r" % unread_order["floors"]),
               ("Plancher introuvable (Echo : pas d'indice), aucun membre n'est jugé sous le plancher" in unread_section,
                "the unreadable anchor is not said: %s" % unread_section[:600])))

    judged("a router that derives from another is held to its contract, requires tools of its members, and is checked against its cascade",
           first_wrong(
               (claude_order["base"] == "code" and claude_order["contract"]["level_gain"]["min_points_per_second"] == 0.2
                and claude_order["contract"]["ranking"]["criterion"] == "code_quality", "the contract was not inherited"),
               (code_order["base"] is None and code_order["differences"] is None, "a router with a contract of its own was derived"),
               (claude["november"]["kind"] == "no_tools" and claude["november"]["verdict"] == "sans appels d'outils",
                "a member with no tool calls was kept: %r" % claude["november"]["verdict"]),
               (code["alpha"]["verdict"] == "conforme" and claude["alpha"]["verdict"] == "conforme",
                "a member whose tools are declared was refused, or a router that needs none said so"),
               (claude_order["differences"] == {"extra": ["echo", "quebec"], "refused": ["november"], "missing": ["sierra"],
                                                "unordered": True, "unknown": ["oscar"]},
                "differences: %r" % claude_order["differences"])))
    judged("a derived cascade is the cascade it derives from, without the members that have no tools, in the same order",
           first_wrong(
               (derivation_differences(["a", "b", "c"], ["a", "c"], {"a": "yes", "b": "no", "c": "yes"})
                == {"extra": [], "refused": [], "missing": [], "unordered": False, "unknown": []}, "the same cascade differs"),
               (derivation_differences(["a", "b", "c"], ["c", "a"], {"a": "yes", "b": "no", "c": "yes"})["unordered"], "another order is the same"),
               (derivation_differences(["a", "b", "c"], ["a", "b", "c"], {"a": "yes", "b": "no", "c": "yes"})["refused"] == ["b"],
                "a member without tools was allowed"),
               (derivation_differences(["a", "b", "c"], ["a", "c"], {"a": "yes", "b": "yes", "c": "yes"})["missing"] == ["b"],
                "a member with tools was allowed to be missing"),
               (derivation_differences(["a", "b", "c"], ["a"], {})
                == {"extra": [], "refused": [], "missing": [], "unordered": False, "unknown": ["a", "b", "c"]},
                "a member whose tools are not known was required or refused"),
               (derivation_differences(["a", "b"], ["a", "x"], {"a": "yes", "b": "unknown"})["extra"] == ["x"], "an extra member went unsaid"),
               (not derivation_differences(["a", "b", "c"], ["a", "c"], {"a": "yes", "b": "unknown", "c": "yes"})["unordered"],
                "a member of unknown tools, left out, was taken for a change of order")))
    # The ranking that does not hold a family at all, and a contract that is validated.
    bare = contracts_report(template, contract_ranking([timed_model("bravo", "Bravo", 12, 4)]), dict(document, status="validated"))
    judged("a ranking without the mapped models makes every mapping stale and no row resolved, and a validated file is not provisional",
           first_wrong(
               (not bare["provisional"], "a validated file is provisional"),
               (len(bare["stale"]) == 16 and bare["no_record"] == ["foxtrot"], "stale: %r" % bare["stale"]),
               (contract_rows(bare, "flash")[0]["bravo"]["kind"] == "conforming", "the one record there is was lost")))

    # Structural problems: what the plain run fails on, each said once and by what it is about.
    def mutated(change):
        mutant = contract_document()
        change(mutant)
        return contracts_problems(mutant, template)

    def set_in(path, value):
        def change(mutant):
            target = mutant
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
        return change

    def drop(*path):
        def change(mutant):
            target = mutant
            for key in path[:-1]:
                target = target[key]
            del target[path[-1]]
        return change

    structural = (
        ("a router that does not exist", set_in(("routers", "ghost"), contract_router({"entry": "alpha"}, 5)), "the contract of \"ghost\" is that of no router"),
        ("a router with no contract", drop("routers", "flash-lite"), 'the router "flash-lite" has no contract'),
        ("a last resort naming something that is no name", set_in(("routers", "pro", "last_resort", "members"), [3]), 'must list its "members" by name'),
        ("a mapping of a name that is no entry, with fields that are wrong", set_in(("models", "zulu"), {"slug": "a b"}), 'the mapping of "zulu" has no "slug" spelt like one'),
        ("a last resort that is no list", set_in(("routers", "pro", "last_resort", "members"), "alpha"), 'must list its "members"'),
        ("a gain that is a string", set_in(("routers", "pro", "level_gain", "min_points_per_second"), "4"), 'has a "min_points_per_second" that is not a number from 0 up'),
        ("a gain that is a boolean", set_in(("routers", "pro", "level_gain", "min_points_per_second"), True), 'has a "min_points_per_second" that is not a number from 0 up'),
        ("a gain below zero", set_in(("routers", "pro", "level_gain", "min_points_per_second"), -1), 'has a "min_points_per_second" that is not a number from 0 up'),
        ("a gain that is none", set_in(("routers", "pro", "level_gain", "min_points_per_second"), None), 'has a "min_points_per_second" that is not a number from 0 up'),
        ("a level gain that is missing", drop("routers", "pro", "level_gain"), 'router "pro", "level_gain", is missing or is not a mapping'),
        ("a level gain with no reason", drop("routers", "pro", "level_gain", "reason"), '"level_gain", has no "reason"'),
        ("a tie margin that is missing", drop("routers", "pro", "ranking", "tie_margin_points"), 'must have a "tie_margin_points" that is a number from 0 up'),
        ("a tie margin that is a string", set_in(("routers", "pro", "ranking", "tie_margin_points"), "2"), 'must have a "tie_margin_points"'),
        ("a tie margin below zero", set_in(("routers", "pro", "ranking", "tie_margin_points"), -1), 'must have a "tie_margin_points"'),
        ("a tie margin on code quality that is missing", drop("routers", "code", "ranking", "tie_margin_points"), 'must have a "tie_margin_points"'),
        ("a floor with no anchor", drop("routers", "pro", "intelligence_floor", "anchor"), '"anchor" must be a mapping that names an "entry"'),
        ("a floor that is a number, not an anchor", set_in(("routers", "pro", "intelligence_floor", "anchor"), 22.5), '"anchor" must be a mapping that names an "entry"'),
        ("an anchor with no entry", set_in(("routers", "pro", "intelligence_floor", "anchor"), {"level": "low"}), '"anchor" must be a mapping that names an "entry"'),
        ("an anchor with an entry of blanks", set_in(("routers", "pro", "intelligence_floor", "anchor"), {"entry": " "}), '"anchor" must be a mapping that names an "entry"'),
        ("an anchor naming an entry no mapping has", set_in(("routers", "pro", "intelligence_floor", "anchor"), {"entry": "zulu"}), 'names "zulu", which "models" does not map'),
        ("an anchor with a level that is none", set_in(("routers", "pro", "intelligence_floor", "anchor"), {"entry": "alpha", "level": "loud"}), 'has a "level" that is none of'),
        ("a fallback that is no mapping", set_in(("fallback_index",), "eci"), '"fallback_index" is not a mapping'),
        ("a fallback with no source", drop("fallback_index", "source"), '"fallback_index" has no "source"'),
        ("a fallback with no status", drop("fallback_index", "status"), '"fallback_index" has no "status"'),
        ("a fallback with no method", drop("fallback_index", "method"), '"fallback_index" has no "method"'),
        ("a fallback with no uncertainty", set_in(("fallback_index", "uncertainty"), " "), '"fallback_index" has no "uncertainty"'),
        ("a fallback with no points", drop("fallback_index", "points"), 'must list its calibration "points" as pairs of numbers'),
        ("a fallback with empty points", set_in(("fallback_index", "points"), []), 'must list its calibration "points" as pairs of numbers'),
        ("a fallback with a point of three", set_in(("fallback_index", "points"), [[140, 4, 1]]), 'must list its calibration "points" as pairs of numbers'),
        ("a fallback with a point that is no pair", set_in(("fallback_index", "points"), [140]), 'must list its calibration "points" as pairs of numbers'),
        ("a fallback with one good point and one of one number", set_in(("fallback_index", "points"), [[140, 4], [150]]), 'must list its calibration "points" as pairs of numbers'),
        ("a fallback with one good point and one that is no number", set_in(("fallback_index", "points"), [[140, 4], [150, "5"]]), 'must list its calibration "points" as pairs of numbers'),
        ("a fallback whose second step goes down", set_in(("fallback_index", "points"), [[140, 4], [150, 5], [145, 6]]), "do not go up with the source figure"),
        ("a fallback whose second step lowers the index", set_in(("fallback_index", "points"), [[140, 4], [150, 5], [160, 4]]), "do not go up with the source figure"),
        ("a fallback with a point that is no number", set_in(("fallback_index", "points"), [[140, "4"]]), 'must list its calibration "points" as pairs of numbers'),
        ("a fallback whose source figure does not go up", set_in(("fallback_index", "points"), [[140, 4], [140, 5]]), "do not go up with the source figure"),
        ("a fallback whose source figure goes down", set_in(("fallback_index", "points"), [[150, 4], [140, 5]]), "do not go up with the source figure"),
        ("a fallback whose index goes down", set_in(("fallback_index", "points"), [[140, 6], [150, 5]]), "do not go up with the source figure"),
        ("floor candidates that are no list", set_in(("routers", "pro", "intelligence_floor", "candidates"), "alpha"), 'must list its "candidates" as anchors'),
        ("a floor candidate that is no anchor", set_in(("routers", "pro", "intelligence_floor", "candidates"), [{"entry": "alpha"}, 5]), 'candidate 2 must be a mapping that names an "entry"'),
        ("a floor candidate naming an entry no mapping has", set_in(("routers", "pro", "intelligence_floor", "candidates"), [{"entry": "zulu"}]), 'candidate 1 names "zulu", which "models" does not map'),
        ("a reason of blanks", set_in(("routers", "pro", "intelligence_floor", "reason"), "  "), '"intelligence_floor", has no "reason"'),
        ("a reason that is no text", set_in(("routers", "pro", "ranking", "reason"), 5), '"ranking", has no "reason"'),
        ("a last resort with no reason", drop("routers", "pro", "last_resort", "reason"), '"last_resort", has no "reason"'),
        ("a block that is missing", drop("routers", "pro", "intelligence_floor"), "is missing or is not a mapping"),
        ("a criterion that is none of the three", set_in(("routers", "pro", "ranking", "criterion"), "speed"),
         '"criterion" among: intelligence, first_answer, code_quality'),
        ("code quality with no source", drop("routers", "code", "ranking", "source"), 'must say its "source", its "source_status"'),
        ("code quality with a source of blanks", set_in(("routers", "code", "ranking", "source"), " "), 'must say its "source", its "source_status"'),
        ("code quality with no source status", drop("routers", "code", "ranking", "source_status"), 'must say its "source", its "source_status"'),
        ("code quality with no stand-in", drop("routers", "code", "ranking", "stand_in"), 'a "stand_in" among: intelligence'),
        ("code quality with a stand-in nobody knows", set_in(("routers", "code", "ranking", "stand_in"), "vibes"), 'a "stand_in" among: intelligence'),
        ("a router derived from one that does not exist", set_in(("routers", "claude-code", "derives_from"), "ghost"),
         'derives from "ghost", which is no router with a contract of its own'),
        ("a router derived from itself", set_in(("routers", "claude-code", "derives_from"), "claude-code"),
         'derives from "claude-code", which is no router with a contract of its own'),
        ("a router derived from a derived one", set_in(("routers", "code"), {"derives_from": "pro", "requires": [], "reason": "x"}),
         'derives from "code", which is no router with a contract of its own'),
        ("a derived router requiring what nobody knows", set_in(("routers", "claude-code", "requires"), ["telepathy"]),
         'must list what it "requires" among: tools'),
        ("a derived router whose requirements are no list", set_in(("routers", "claude-code", "requires"), "tools"),
         'must list what it "requires" among: tools'),
        ("a derived router requiring one thing known and one not", set_in(("routers", "claude-code", "requires"), ["tools", "telepathy"]),
         'must list what it "requires" among: tools'),
        ("a derived router with no reason", drop("routers", "claude-code", "reason"), 'router "claude-code" has no "reason"'),
        ("a status that is neither", set_in(("status",), "draft"), '"status" must be one of provisional, validated'),
        ("an index version that is no number", set_in(("index_version",), "5"), '"index_version" must be a number'),
        ("a file that is not a mapping", None, "the router contracts file is not a mapping"),
        ("routers that are no mapping", set_in(("routers",), ["pro"]), '"routers" is missing'),
        ("a router that is no mapping", set_in(("routers", "pro"), "x"), 'router "pro" is not a mapping'),
        ("models that are no mapping", set_in(("models",), []), '"models" is missing'),
        ("inputs that are no mapping", set_in(("inputs",), []), '"inputs" is not a mapping'),
        ("a mapping that is no mapping", set_in(("models", "alpha"), "x"), 'the mapping of "alpha" is not a mapping'),
        ("a model with a record and none", set_in(("models", "alpha", "no_record"), "x"), '"no_record" and so says why'),
        ("a no_record that says nothing", set_in(("models", "foxtrot", "no_record"), " "), '"no_record" and so says why'),
        ("a slug that is missing", drop("models", "alpha", "slug"), 'has no "slug" spelt like one'),
        ("a slug that is not spelt like one", set_in(("models", "alpha", "slug"), "a b"), 'has no "slug" spelt like one'),
        ("a level nobody knows", set_in(("models", "alpha", "level"), "extreme"), 'has a "level" that is none of'),
        ("a level source that is missing", drop("models", "alpha", "level_source"), 'has no "level_source"'),
        ("a level source of blanks", set_in(("models", "alpha", "level_source"), " "), 'has no "level_source"'),
        ("tools that are missing", drop("models", "alpha", "tools"), 'has no "tools" saying "yes", "no" or "unknown"'),
        ("tools that are no mapping", set_in(("models", "alpha", "tools"), "yes"), 'has no "tools" saying'),
        ("tools of a support nobody knows", set_in(("models", "alpha", "tools", "support"), "maybe"), 'has no "tools" saying'),
        ("tools with no source", drop("models", "alpha", "tools", "source"), 'has no "tools" saying'),
        ("tools with a source of blanks", set_in(("models", "alpha", "tools", "source"), " "), 'has no "tools" saying'),
        ("a no_record entry with no tools", drop("models", "foxtrot", "tools"), 'has no "tools" saying'),
        ("an epoch that is a word", set_in(("models", "alpha", "epoch"), "known"), 'has an "epoch" that is neither "unknown"'),
        ("an epoch that is empty", set_in(("models", "alpha", "epoch"), {}), 'has an "epoch" that is neither "unknown"'),
        ("an epoch with ids that are no list", set_in(("models", "alpha", "epoch"), {"f": "x"}), 'has an "epoch" that is neither "unknown"'),
        ("an epoch with an empty list", set_in(("models", "alpha", "epoch"), {"f": []}), 'has an "epoch" that is neither "unknown"'),
        ("an epoch with an id of blanks", set_in(("models", "alpha", "epoch"), {"f": [" "]}), 'has an "epoch" that is neither "unknown"'),
        ("an epoch with an id that is no text", set_in(("models", "alpha", "epoch"), {"f": [3]}), 'has an "epoch" that is neither "unknown"'),
        ("an epoch with one good file and one bad", set_in(("models", "alpha", "epoch"), {"f": ["a"], "g": []}), 'has an "epoch" that is neither "unknown"'),
        ("an epoch with one good id and one bad", set_in(("models", "alpha", "epoch"), {"f": ["a", 3]}), 'has an "epoch" that is neither "unknown"'),
        ("an epoch with one good id and a blank one", set_in(("models", "alpha", "epoch"), {"f": ["a", " "]}), 'has an "epoch" that is neither "unknown"'),
        ("an epoch on an arena of web interfaces", set_in(("models", "alpha", "epoch"), {"webdev_arena_external": ["a"]}),
         'has an "epoch" on a benchmark file that is not read: only deepswe_external, swe_bench_verified, cursorbench_external, terminalbench_external, ale_bench_external are'),
        ("an epoch with a benchmark file that is read and one that is not", set_in(("models", "alpha", "epoch"), {"deepswe_external": ["a"], "design_arena": ["b"]}),
         'has an "epoch" on a benchmark file that is not read'),
    )
    for purpose, change, needle in structural:
        if change is None:
            found = contracts_problems(["not", "a", "mapping"], template)
        else:
            found = mutated(change)
        judged("structure: %s is refused" % purpose,
               None if any(needle in problem for problem in found) else "expected %r, got %r" % (needle, found))
    judged("structure: a name the template does not have any more is no problem, in a mapping or in a last resort",
           first_wrong((mutated(set_in(("models", "zulu"), contract_mapping("zulu", "n/a"))) == [], "a mapping of a deleted entry was refused"),
                       (mutated(set_in(("routers", "pro", "last_resort", "members"), ["juliet", "zulu"])) == [],
                        "a last resort naming a deleted entry was refused")))
    judged("structure: an anchor on a level, a rate of zero, a note, an epoch said unknown and a derived router are no problem",
           first_wrong((mutated(set_in(("routers", "pro", "intelligence_floor", "anchor"), {"entry": "alpha", "level": "high"})) == [], "an anchor on a level was refused"),
                       (mutated(set_in(("routers", "pro", "level_gain", "min_points_per_second"), 0)) == [], "a rate of 0 was refused"),
                       (mutated(set_in(("routers", "pro", "ranking", "tie_margin_points"), 0)) == [], "a tie margin of 0 was refused"),
                       (mutated(drop("fallback_index")) == [], "a file with no fallback was refused"),
                       (mutated(set_in(("fallback_index", "points"), [[140, 4], [150, 4]])) == [], "calibration points that stay level were refused"),
                       (mutated(set_in(("models", "alpha", "note"), "a note")) == [], "a note was refused"),
                       (mutated(set_in(("models", "alpha", "epoch"), "unknown")) == [], "an epoch said unknown was refused"),
                       (mutated(drop("models", "alpha", "epoch")) == [], "an entry with no epoch was refused"),
                       (mutated(set_in(("models", "alpha", "epoch"), {key: ["a"] for key in EPOCH_KEYS})) == [], "the five benchmark files were refused"),
                       (mutated(drop("routers", "pro", "intelligence_floor", "candidates")) == [], "a floor with no candidates was refused"),
                       (mutated(set_in(("routers", "pro", "intelligence_floor", "candidates"), [{"entry": "alpha"}, {"entry": "sierra", "level": "low"}])) == [],
                        "candidates that are anchors were refused")))

    # The file itself: unreadable, or not YAML, says so; a good one is read.
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "contracts.yaml")
        missing = offline_contract_problems(CONTRACT_TEMPLATE, path)
        Path(path).write_text("routers: [unclosed\n", encoding="utf-8")
        broken = offline_contract_problems(CONTRACT_TEMPLATE, path)
        Path(path).write_bytes(b"\xff\xfe")
        binary = offline_contract_problems(CONTRACT_TEMPLATE, path)
        Path(path).write_text(yaml.safe_dump(contract_document()), encoding="utf-8")
        good = offline_contract_problems(CONTRACT_TEMPLATE, path)
        unreadable_template = offline_contract_problems("model_list: [unclosed\n", path)
        judged("a contracts file that cannot be read, or is not YAML, is a problem of its own, and a good one passes",
               first_wrong((len(missing) == 1 and "cannot be read (FileNotFoundError)" in missing[0], "missing: %r" % missing),
                           (len(broken) == 1 and "cannot be read" in broken[0], "broken: %r" % broken),
                           (len(binary) == 1 and "cannot be read" in binary[0], "binary: %r" % binary),
                           (good == [], "good: %r" % good),
                           (unreadable_template == [], "a template that cannot be read is another rule's to say")))

        # The issue: the section from the command line, end to end, on a template and a contracts file.
        config = os.path.join(directory, "config.yaml.j2")
        Path(config).write_text(CONTRACT_TEMPLATE, encoding="utf-8")
        issue = os.path.join(directory, "issue.md")
        listing = answers_listing(CONTRACT_TEMPLATE)

        def run(arguments, environment=RANKING_KEYS, version=5.0):
            page = ranking_page(*contract_records())
            page["intelligence_index_version"] = version
            out = io.StringIO()
            Path(issue).unlink(missing_ok=True)
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                try:
                    status = main(arguments, opener=canned_opener(dict(listing, rankings=page), []),
                                  environment=environment)
                except SystemExit as error:
                    status = error.code
            return status, out.getvalue(), Path(issue).read_text(encoding="utf-8") if os.path.exists(issue) else ""

        online = ["--online", "--config", config, "--issue-body", issue, "--contracts", path]
        status, out, body = run(online)
        section = body.split("## Contrats par routeur")[1].split("\n## ")[0] if "## Contrats par routeur" in body else ""
        judged("with the ranking read, the issue carries a section of contracts: a table per router, the two orders, the floors side by side and what the mapping does not cover, and nothing else changes",
               first_wrong(
                   (status == 0 and "Aucune dérive." in body, "the section changed the status or the drift: %d" % status),
                   ("### `pro`" in section and "### `flash-lite`" in section and "### `claude-code`" in section, "a router has no table"),
                   ("Plancher 20 (Alpha (Low)), un niveau de plus tant qu'il rapporte au moins 0.2 points d'indice par seconde de plus, classé par l'indice d'intelligence, "
                    "le délai départageant deux membres à moins de 2 points d'écart." in section, "pro's contract is not said"),
                   ("Plancher 8 (India), un niveau de plus tant qu'il rapporte au moins 1.5 points d'indice par seconde de plus, classé par le délai le plus court." in section,
                    "flash-lite's criterion is not said"),
                   ("Plancher 20 (Alpha (Low)), un niveau de plus tant qu'il rapporte au moins 0.2 points d'indice par seconde de plus, classé par la qualité de code "
                    "(source : Epoch AI selftest source, non lue (HTTP 404)) ; Artificial Analysis n'a pas d'indice de code, l'indice "
                    "d'intelligence en tient lieu à titre provisoire, le délai départageant deux membres à moins de 2 points d'écart." in section,
                    "code's ranking is not said as a stand-in"),
                   ("Dérivé de `code` : mêmes plancher (20 (Alpha (Low))), taux d'échange (0.2 points par seconde) et classement, et les modèles sans appels d'outils "
                    "en sont exclus." in section, "the derived router is not said"),
                   ("| `alpha` | Alpha (Medium) | medium | 30.0 | 12.0 | 100.0 | xhigh (indice 50.0, 60.0 s) | conforme |" in section,
                    "alpha's row is wrong: %s" % section[:1500]),
                   ("| `india` | India | sans niveau | 8.0 | 2.0 | 100.0 | niveau unique (indice 8.0, 2.0 s) | "
                    "sous le plancher (8.0 contre 20) : dernier recours |" in section, "india's row is wrong"),
                   ("| `juliet` (dernier recours) | Juliet | inconnu | — | 50.0 | 100.0 | aucun niveau n'a d'indice | "
                    "conforme (dernier recours) |" in section, "juliet's row is wrong"),
                   ("| `foxtrot` (dernier recours) | — | — | — | — | — | — | sans enregistrement |" in section, "an entry with no record has no row"),
                   ("| `november` | — | — | — | — | — | — | sans appels d'outils |" in section, "a member without tools has no row"),
                   ("| `quebec` | Quebec | sans niveau | 30.0 | — | 100.0 | niveau unique (indice 30.0) | "
                    "conforme ; appels d'outils inconnus |" in section, "quebec's row in claude-code is wrong"),
                   ("| `quebec` | Quebec | sans niveau | 30.0 | — | 100.0 | niveau unique (indice 30.0) | "
                    "inclassable : pas de délai |" in section, "quebec's row in flash-lite is wrong"),
                   ("| `bravo` | Bravo" in section and "sans niveau" in section, "a level that does not apply is not said"),
                   ("Ordre actuel : `bravo` > `kilo` > `lima` > `hotel` > `golf` > `mike` > `papa` > `romeo`." in section, "the current order is missing"),
                   ("Ordre des contrats : `lima` > `papa` > `bravo` > `kilo` > `mike` > `romeo`." in section, "the contracts' order is missing"),
                   ("Ordre des contrats : `alpha` > `india` > `juliet` > `foxtrot`." in section, "pro's order is missing"),
                   ("| 5 (Sierra) | `alpha`, `india` | `juliet`, `foxtrot` |" in section
                    and "| 20 (Alpha (Low)) (proposé) | `alpha` | `india`, `juliet`, `foxtrot` |" in section
                    and "| 40 (Alpha (High)) | — | `alpha`, `india`, `juliet`, `foxtrot` |" in section, "the floors are not played side by side"),
                   (section.count("Effet de chaque plancher :") == 2, "a table of floors for a contract that proposes one floor"),
                   ("La cascade de `claude-code` n'est **pas** la cascade de `code` sans les membres sans outils, dans le même ordre." in section
                    and "- dans `claude-code` mais pas dans `code` : `echo`, `quebec`" in section
                    and "- sans appels d'outils déclarés, pourtant dans `claude-code` : `november`" in section
                    and "- avec appels d'outils, dans `code` mais pas dans `claude-code` : `sierra`" in section
                    and "- l'ordre des membres communs n'est pas celui de `code`" in section
                    and "- appels d'outils inconnus (ni exigés ni refusés, à vérifier) : `oscar`" in section,
                    "the derivation is not reported: %s" % section[-1800:]),
                   ("Entrées sans correspondance (à ajouter au fichier des contrats) :\n\n- `hotel`\n" in section, "hotel is not listed unmapped"),
                   ("- `golf` : `golf-gone`" in section, "the stale mapping is not listed"),
                   ("- `delta` appelé à `medium`, classé à : low, high" in section, "the uncovered level is not listed"),
                   ("**C'est un rapport**" in section and "**provisoires**" in section, "the report is not said to be one, or provisional, in bold"),
                   ("provisoires" in section and "comprimée" in section and "n'est retiré d'aucune cascade" in section
                    and "Aucun délai ne rend un membre inéligible" in section,
                    "the provisional status, the compressed scale, the advisory status or the absence of a time bound is not said"),
                   ("restent où ils sont, signalés inclassables, tant que l'indice de repli (Epoch selftest) n'est pas lu." in section,
                    "the fallback is not said"),
                   ("<https://artificialanalysis.ai/>" in section, "the source is not named"),
                   ("version" not in section.split("### `pro`")[0], "a version warning without a version change")))
        judged("what a record's name carries into the issue is cut to plain words",
               first_wrong((hostile_lines(body) is None, str(hostile_lines(body))),
                           ("@bob" not in body and "<img" not in body, "markup reached the issue")))
        judged("the contracts are read from the file's text, once, and the same run's exit status is the one the drift gives",
               first_wrong((run(["--online", "--config", config, "--contracts", path])[0] == status, "the status moved")))

        # The ranking at another version of the index warns that the floors are on the other one.
        warned = run(online, version=6.0)[2]
        judged("an index that is not the version the floors were written for is said before any row",
               first_wrong(("L'indice d'intelligence est maintenant en version 6, les planchers sont écrits pour la version 5"
                            in warned.split("### `pro`")[0], "the version change is not said"),
                           ("**L'indice d'intelligence est maintenant en version 6" in warned and "à revoir avant de se fier à une ligne.**" in warned,
                            "the version change is not in bold"),
                           ("version 6" not in body, "a version change was said where there is none")))

        # No key, another template, a file that is wrong and a computation that fails: the run is the same.
        status_none, _, body_none = run(online, environment=SELFTEST_KEYS)
        status_other, _, body_other = run(["--online", "--config", config, "--issue-body", issue])
        judged("without the ranking, or with another template and no contracts of its own, no section is written and the status is the same",
               first_wrong(("## Contrats par routeur" not in body_none, "a section without the ranking"),
                           ("## Contrats par routeur" not in body_other, "the repository's contracts were read against another template"),
                           (status_none == status and status_other == status, "the status moved")))
        broken_document = contract_document()
        del broken_document["routers"]["pro"]["level_gain"]["reason"]
        Path(path).write_text(yaml.safe_dump(broken_document), encoding="utf-8")
        status_bad, _, body_bad = run(online)
        judged("a contracts file with a structural problem says so in the issue, computes nothing, and changes neither the status nor the rest",
               first_wrong(("n'a pas la forme attendue" in body_bad and '"level_gain", has no "reason"' in body_bad, "the problem is not said"),
                           ("### `pro`" not in body_bad, "a table was written from a file that is wrong"),
                           (status_bad == status and "Aucune dérive." in body_bad, "the status or the drift moved")))
        Path(path).write_text(yaml.safe_dump(contract_document()), encoding="utf-8")
        real = globals()["contracts_report"]

        def exploding(*arguments):
            raise RuntimeError("selftest: the computation failed with SECRET")

        globals()["contracts_report"] = exploding
        try:
            status_boom, _, body_boom = run(online)
        finally:
            globals()["contracts_report"] = real
        judged("a computation that fails says the kind of the error and nothing of its message, and never fails the run",
               first_wrong(("Le calcul a échoué (`RuntimeError`)" in body_boom, "the failure is not said"),
                           ("SECRET" not in body_boom, "the message of the error reached the issue"),
                           (status_boom == status and "Aucune dérive." in body_boom, "the status moved")))

        # A deleted entry leaves its row: reported as stale in the issue and as a notice in the plain run,
        # and neither fails.
        stale_document = contract_document()
        stale_document["models"]["zulu"] = contract_mapping("zulu", "n/a")
        stale_document["routers"]["code"]["last_resort"]["members"] = ["zulu"]
        Path(path).write_text(yaml.safe_dump(stale_document), encoding="utf-8")
        status_stale, _, body_stale = run(online)
        status_notice, out_notice, _ = run(["--config", config, "--contracts", path])
        absent = [("models", "zulu"), ("code", "zulu")]
        judged("an entry deleted from the template leaves a stale row: the report lists it, the plain run says so and stays green, the weekly status does not move",
               first_wrong(
                   (absent_names(stale_document, template) == absent, "absent: %r" % absent_names(stale_document, template)),
                   (contracts_report(template, contract_ranking(), stale_document)["absent"] == absent, "the report does not hold them"),
                   ("Correspondances sans entrée (l'entrée n'est plus au modèle, la ligne est à retirer du fichier des contrats) :\n\n"
                    "- `zulu` (correspondance)\n- `zulu` (dernier recours de `code`)\n" in body_stale, "the issue does not list them"),
                   (status_stale == status and "Aucune dérive." in body_stale, "the status moved"),
                   (status_notice == 0 and 'Router contracts: "zulu" (mapping) is no entry of the template any more: a stale mapping, '
                    "its row is to be removed from contracts.yaml." in out_notice
                    and 'Router contracts: "zulu" (last resort of code) is no entry' in out_notice, "the notice is missing: %s" % out_notice),
                   (offline_contract_problems(CONTRACT_TEMPLATE, path) == [], "a stale row is a problem"),
                   ("Correspondances sans entrée" not in body, "a stale section where there is none")))
        Path(path).write_text(yaml.safe_dump(dict(broken_document, models=dict(
            broken_document["models"], zulu=contract_mapping("zulu", "n/a")))), encoding="utf-8")
        judged("a file with a problem prints no notice of stale rows",
               first_wrong((offline_contract_notices(CONTRACT_TEMPLATE, path) == [], "a notice for a file that is wrong"),
                           (offline_contract_notices("model_list: [unclosed\n", path) == [], "a notice for a template that cannot be read")))
        Path(path).write_text("status: provisional\nstatus: validated\n", encoding="utf-8")
        twice = offline_contract_problems(CONTRACT_TEMPLATE, path)
        status_twice, out_twice, _ = run(["--config", config, "--contracts", path])
        judged("a key written twice is a problem of the file, not a value silently replaced",
               first_wrong((len(twice) == 1 and "cannot be read (ConstructorError)" in twice[0], "twice: %r" % twice),
                           (status_twice == 1, "the plain run passed a file with a key written twice")))

        # The plain run: the contracts file is read against the template it is given.
        plain = ["--config", config, "--contracts", path]
        Path(path).write_text(yaml.safe_dump(contract_document()), encoding="utf-8")
        status_plain, out_plain, _ = run(plain)
        Path(path).write_text(yaml.safe_dump(broken_document), encoding="utf-8")
        status_wrong, out_wrong, _ = run(plain)
        status_alone, out_alone, _ = run(["--config", config])
        judged("the plain run fails only on the structure of the contracts, and reads none for a template that is not the repository's",
               first_wrong((status_plain == 0 and "Router contracts: contracts.yaml holds a contract for each router" in out_plain,
                            "a good file was refused: %s" % out_plain),
                           (status_wrong == 1 and "Router contracts: 1 problem(s) in contracts.yaml." in out_wrong
                            and '"level_gain", has no "reason"' in out_wrong, "a wrong file passed: %s" % out_wrong),
                           (status_alone == 0 and "Router contracts" not in out_alone, "contracts were read for another template: %s" % out_alone)))
    judged("the repository's own contracts file passes against the repository's template",
           first_wrong((offline_contract_problems(CONFIG.read_text(encoding="utf-8"), CONTRACTS) == [],
                        "%r" % offline_contract_problems(CONFIG.read_text(encoding="utf-8"), CONTRACTS))))
    return failures


# Code quality from Epoch AI's archive, played on made-up members only: archives built in memory, whose
# members carry the allowed names and invented model versions, and no figure of the real data.
EPOCH_TEMPLATE = """\
model_list:
""" + "".join("""  - model_name: %s
    litellm_params:
      model: groq/vendor/%s-model
      api_key: "os.environ/GROQ_API_KEY_SELFTEST"

""" % (name, name) for name in ("p", "q", "r", "s", "t", "u", "v", "w", "y", "z")) + """\
router_settings:
  fallbacks:
    - code: [p, q, r, s, t, u, v, z]
    - claude-code: [p, q, s, t, y]
  model_group_alias:
    "code": "p"
    "claude-code": "p"
"""

# The scores of the made-up archive, by benchmark file. Some benchmark files count for the cascade of
# "code" (two members or more have a score) and some do not (one member only), and v tops two of them
# while being under the floor.
EPOCH_SCORES = {
    "deepswe_external": {"p_high": 0.5, "q_high": 0.6, "r_high": 0.6, "v_high": 0.9, "y_high": 0.99},
    "swe_bench_verified": {"s_high": 0.9, "p_high": 0.7, "q_high": 0.5},
    "cursorbench_external": {"q_high": 0.3},
    "terminalbench_external": {"s_high": 0.8},
    "ale_bench_external": {"v_high": 1500, "r_high": 1200, "p_high": 1000, "p_low": 900, "q_high": 900},
}
# Made-up capabilities indexes, by display name.
EPOCH_ECI = {"Pee Model": 145.0, "Que Model": 165.0, "Floor Model": 155.0, "Low Model": 135.0, "High Model": 175.0}
EPOCH_IDS = {
    "p": {"deepswe_external": ["p_high"], "swe_bench_verified": ["p_high"], "ale_bench_external": ["p_low", "p_high"]},
    "q": {"deepswe_external": ["q_high"], "swe_bench_verified": ["q_high"], "ale_bench_external": ["q_high"],
          "cursorbench_external": ["q_high"]},
    "r": {"deepswe_external": ["r_high"], "ale_bench_external": ["r_high"]},
    "s": {"swe_bench_verified": ["s_high"], "terminalbench_external": ["s_high"]},
    "t": "unknown",
    "u": {"deepswe_external": ["u_nowhere"]},
    "v": {"deepswe_external": ["v_high"], "ale_bench_external": ["v_high"]},
    "y": {"deepswe_external": ["y_high"]},
}


def epoch_csv(column, scores, extra=""):
    """A benchmark file as Epoch AI writes them: the model version first, other columns around the score."""
    return ("Model version,Release date,%s,Notes\n" % column
            + "".join("%s,2026-01-01,%s,\n" % item for item in scores.items()) + extra)


def epoch_zip(members):
    """An archive in memory: {member name: text or bytes}."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def eci_csv(scores, extra=""):
    """The capabilities index as Epoch AI writes it: the model, its display name and the index first."""
    return ("Model,Display name,eci,eci_ci_low,date\n"
            + "".join("%s,%s,%s,0,2026-01-01\n" % (name, name, score) for name, score in scores.items()) + extra)


def epoch_members(scores=None, extra=None, eci=None):
    """The members of the archive: the five benchmark files for "scores" (EPOCH_SCORES by default), the
    capabilities index for "eci" (EPOCH_ECI by default), plus "extra" members."""
    scores = EPOCH_SCORES if scores is None else scores
    members = {epoch_member_name(key): epoch_csv(column, scores.get(key, {})) for key, _, column in EPOCH_FILES}
    members[EPOCH_ECI_MEMBER] = eci_csv(EPOCH_ECI if eci is None else eci)
    return dict(members, **(extra or {}))


def epoch_read(content, **limits):
    """read_epoch on an opener that serves "content" (bytes, or an exception to raise) for the archive's
    address and nothing else, and the calls it made: (state, calls). "limits" patch the caps meanwhile."""
    calls = []

    def opener(url, headers, limit=None):
        calls.append((url, dict(headers), limit))
        if isinstance(content, Exception):
            raise content
        return content

    saved = {name: globals()[name] for name in limits}
    globals().update(limits)
    try:
        return read_epoch(opener, "2026-01-02"), calls
    finally:
        globals().update(saved)


def epoch_archive(scores=None, eci=None):
    """The state of an archive that was read, built from "scores" and "eci" without a zip: what
    read_epoch gives."""
    scores = EPOCH_SCORES if scores is None else scores
    return {"status": "read", "date": "2026-01-02", "skipped": {}, "eci": dict(EPOCH_ECI if eci is None else eci),
            "files": {key: {"scores": dict(found), "rows": len(found), "bad": 0} for key, found in scores.items()}}


def epoch_document():
    """The contracts of "code" and of "claude-code" over the cascades of EPOCH_TEMPLATE: an anchor at 10
    points, z exempt from it, the made-up model versions of EPOCH_IDS."""
    document = {"routers": {"code": contract_router({"entry": "w"}, 0.2, criterion="code_quality", last_resort=("z",)),
                            "claude-code": {"derives_from": "code", "requires": ["tools"], "reason": "selftest"}},
                "models": {name: contract_mapping(name, "n/a") for name in "pqrstuvwyz"},
                "status": "provisional", "index_version": 5}
    for name, ids in EPOCH_IDS.items():
        document["models"][name]["epoch"] = ids
    return document


def epoch_ranking():
    """What Artificial Analysis says of the made-up models: (intelligence, seconds to the first answer token)."""
    return contract_ranking([
        timed_model("p", "Pee", 30, 8), timed_model("q", "Que", 30, 4), timed_model("r", "Are", 25, 6),
        timed_model("s", "Ess", 20, 3), timed_model("t", "Tee", 15, 2), timed_model("u", "You", 12, 5),
        timed_model("v", "Vee", 5, 1), timed_model("w", "Double", 10, 9), timed_model("y", "Why", 14, 1),
        timed_model("z", "Zed", 50, 1)])


def contracts_runner(directory, document, template_text=CONTRACT_TEMPLATE):
    """A template and a contracts file written into "directory", and (run, config, path, issue): run(arguments,
    served, environment, opener) is the command line on them, with the ranking of contract_records() read and
    "served" as the archive of Epoch AI (nothing served is a 404), and gives (status, output, the issue written,
    the requests made for the archive)."""
    config, path, issue = (os.path.join(directory, name) for name in ("config.yaml.j2", "contracts.yaml", "issue.md"))
    Path(config).write_text(template_text, encoding="utf-8")
    Path(path).write_text(yaml.safe_dump(document), encoding="utf-8")
    listing = answers_listing(template_text)
    page = ranking_page(*contract_records())
    page["intelligence_index_version"] = 5.0

    def run(arguments, served=None, environment=RANKING_KEYS, opener=None):
        calls, out = [], io.StringIO()
        Path(issue).unlink(missing_ok=True)
        answers = dict(listing, rankings=page, **({} if served is None else {"epoch": served}))
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            status = main(arguments, opener=opener or canned_opener(answers, calls), environment=environment)
        return (status, out.getvalue(), Path(issue).read_text(encoding="utf-8") if os.path.exists(issue) else "",
                [url for url, _ in calls if url == EPOCH_URL])

    return run, config, path, issue


def run_epoch_cases():
    failures = 0

    def judged(purpose, why):
        nonlocal failures
        if why is None:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s) -- %s" % (purpose, why))

    def first_wrong(*checks):
        return next((message for ok, message in checks if not ok), None)

    # Reading the archive: from bytes in memory, by the exact names of five members, never extracted.
    good, calls = epoch_read(epoch_zip(epoch_members(dict(
        EPOCH_SCORES, terminalbench_external={"s_high": 0.4}), {"unrelated.csv": "a,b\n1,2\n"})))
    judged("a good archive is read: five files, a score a version, and the request is keyless, capped and says who asks",
           first_wrong(
               (good["status"] == "read" and good["date"] == "2026-01-02" and good["skipped"] == {}, "state: %r" % good),
               (sorted(good["files"]) == sorted(EPOCH_KEYS), "files: %r" % sorted(good["files"])),
               (good["files"]["deepswe_external"]["scores"] == EPOCH_SCORES["deepswe_external"], "scores were not kept"),
               (good["files"]["ale_bench_external"]["rows"] == 5 and good["files"]["ale_bench_external"]["bad"] == 0, "rows counted"),
               (len(calls) == 1 and calls[0][0] == EPOCH_URL and calls[0][2] == EPOCH_MAX_ARCHIVE, "calls: %r" % calls),
               (set(calls[0][1]) == {"User-Agent", "Accept"}, "the request carries more than it should: %r" % sorted(calls[0][1]))))
    best, _ = epoch_read(epoch_zip(epoch_members({"terminalbench_external": {}}, {
        "terminalbench_external.csv": "Model version,Agent,Accuracy mean\nm1,a,0.4\nm1,b,0.9\nm1,c,0.5\nm2,a,0.1\n"})))
    judged("a model version listed once per agent keeps its best score",
           first_wrong((best["files"]["terminalbench_external"]["scores"] == {"m1": 0.9, "m2": 0.1}, "%r" % best["files"]),
                       (best["files"]["terminalbench_external"]["rows"] == 4, "four rows were read")))
    absent, _ = epoch_read(epoch_zip({name: text for name, text in epoch_members().items()
                                      if name != "swe_bench_verified.csv"}))
    judged("a member the archive lacks is skipped and said, the others are read",
           first_wrong((absent["status"] == "read" and sorted(absent["files"]) == sorted(set(EPOCH_KEYS) - {"swe_bench_verified"}),
                        "files: %r" % sorted(absent["files"])),
                       (absent["skipped"] == {"swe_bench_verified": "absent from the archive"}, "skipped: %r" % absent["skipped"])))
    alone, _ = epoch_read(epoch_zip({"deepswe_external.csv": epoch_csv("Pass@1", EPOCH_SCORES["deepswe_external"])}))
    judged("an archive with one benchmark file only is read as that one, and says it lacks the four others and the capabilities index",
           first_wrong((alone["status"] == "read" and sorted(alone["files"]) == ["deepswe_external"], "files: %r" % sorted(alone["files"])),
                       (sorted(alone["skipped"]) == sorted((set(EPOCH_KEYS) - {"deepswe_external"}) | {EPOCH_ECI_KEY}), "skipped: %r" % alone["skipped"])))
    big, _ = epoch_read(epoch_zip(epoch_members(None, {"deepswe_external.csv": epoch_csv("Pass@1", EPOCH_SCORES["deepswe_external"], "x,1,0.1,\n" * 80)})),
                        EPOCH_MAX_MEMBER=300)
    judged("a member larger than the cap is skipped without being read, and the others are read",
           first_wrong((big["status"] == "read" and "deepswe_external" not in big["files"], "files: %r" % sorted(big["files"])),
                       (big["skipped"] == {"deepswe_external": "larger than 300 bytes"}, "skipped: %r" % big["skipped"]),
                       ("swe_bench_verified" in big["files"], "a small member was refused with the big one")))
    # Each of these would read as any of the five files, were its name taken for one of theirs.
    wide = ("Model version,Display name," + ",".join(column for _, _, column in EPOCH_FILES) + ",eci\n"
            "x,x,1,1,1,1,1,1\n")
    hostile = {"webdev_arena_external.csv": wide, "sub/deepswe_external.csv": wide, "../deepswe_external.csv": wide,
               "deepswe_external.csv/": "", "README.md": wide, "epoch_capabilities_index/edi_scores.csv": wide,
               "x/epoch_capabilities_index/eci_scores.csv": wide, "eci_scores.csv": wide, "model_metadata.csv": wide}
    outside, _ = epoch_read(epoch_zip(hostile))
    judged("members outside the allow-list are never read: another arena, a path, a directory, and nothing is extracted",
           first_wrong((outside["status"] == "error" and outside["error"] == "no benchmark file of the archive holds a usable row",
                        "read: %r" % outside),
                       (not os.path.exists("sub") and not os.path.exists("deepswe_external.csv"), "a member was extracted")))
    mixed, _ = epoch_read(epoch_zip(dict(epoch_members(None, {
        "deepswe_external.csv": ("Model version,Pass@1\n,0.5\nno-score,\nword,abc\nnan-one,nan\ninf-one,inf\nneg,-1e999\n"
                                 "short\ngood,0.25\ngood,0.5\n  spaced  ,0.75\n" + "l" * 201 + ",0.9\n\"open,0.1\n"),
        "swe_bench_verified.csv": "Model version,mean_score\nonly,\x00,\n",
        "cursorbench_external.csv": "Model version,Other\nm,0.5\n",
        "terminalbench_external.csv": b"\xff\xfe\x00\x01\x02",
        "ale_bench_external.csv": "Model version,Performance\n"}))))
    judged("bad rows are tolerated and counted: no version, no score, a score that is no finite number, a ragged row, a version too long; a file with the wrong columns, no rows or no text is skipped",
           first_wrong((mixed["status"] == "read" and sorted(mixed["files"]) == ["deepswe_external"], "files: %r" % sorted(mixed["files"])),
                       (mixed["files"]["deepswe_external"]["scores"] == {"good": 0.5, "spaced": 0.75}, "scores: %r" % mixed["files"]["deepswe_external"]["scores"]),
                       (mixed["files"]["deepswe_external"]["rows"] == 3 and mixed["files"]["deepswe_external"]["bad"] >= 6, "rows: %r" % mixed["files"]["deepswe_external"]),
                       (mixed["skipped"]["cursorbench_external"] == "it has not the columns expected", "%r" % mixed["skipped"]),
                       (mixed["skipped"]["terminalbench_external"].startswith("it "), "%r" % mixed["skipped"]),
                       (mixed["skipped"]["ale_bench_external"] == "it has no usable row", "%r" % mixed["skipped"]),
                       (mixed["skipped"]["swe_bench_verified"] == "it has no usable row", "%r" % mixed["skipped"])))
    judged("an archive with no usable row anywhere is not read",
           first_wrong((epoch_read(epoch_zip(epoch_members({}, None, {})))[0]["error"] == "no benchmark file of the archive holds a usable row", "empty members")))

    # What does not read at all: size, shape, status, network, and a failure of the reader itself.
    bulky, _ = epoch_read(b"x" * 300, EPOCH_MAX_ARCHIVE=100)
    leaky = urllib.error.HTTPError(EPOCH_URL, 403, "SECRET reason", None, io.BytesIO(b"SECRET body"))
    failed = (("an answer larger than the cap", bulky, "the archive is larger than 100 bytes"),
              ("an answer that is no archive", epoch_read(b"<html>not a zip</html>")[0], "the answer is not a zip archive"),
              ("an empty answer", epoch_read(b"")[0], "the answer is not a zip archive"),
              ("an HTTP status", epoch_read(leaky)[0], "HTTP 403"),
              ("a redirect", epoch_read(urllib.error.HTTPError(EPOCH_URL, 302, "Found", None, io.BytesIO(b"")))[0], "HTTP 302"),
              ("a network failure", epoch_read(urllib.error.URLError("no route"))[0], "network error: no route"),
              ("a timeout", epoch_read(TimeoutError())[0], "network error: TimeoutError"),
              ("a reader that crashes", epoch_read(RuntimeError("SECRET crash"))[0], "failed: RuntimeError"))
    judged("an archive that cannot be read says the kind of failure and nothing of the body, the reason phrase or the message",
           first_wrong(*[(state["status"] == "error" and state["error"] == text and "files" not in state, "%s: %r" % (purpose, state))
                         for purpose, state, text in failed],
                       ("SECRET" not in repr([state for _, state, _ in failed]), "a secret reached the state")))

    # The rank of each member in each file: ties share the average, and the best score is rank 1.
    judged("a rank is 1 for the best score, and members with the same score share the average of their places",
           first_wrong((rank_with_ties({"a": 3, "b": 2, "c": 2, "d": 1}) == {"a": 1, "b": 2.5, "c": 2.5, "d": 4}, "a tie in the middle"),
                       (rank_with_ties({"a": 5, "b": 5, "c": 5}) == {"a": 2, "b": 2, "c": 2}, "all equal"),
                       (rank_with_ties({"a": 1, "b": 2, "c": 2, "d": 2}) == {"a": 4, "b": 2, "c": 2, "d": 2}, "a tie at the top is 2"),
                       (rank_with_ties({"a": 7}) == {"a": 1}, "a single member"), (rank_with_ties({}) == {}, "no member"),
                       (rank_with_ties({"a": 0.1, "b": 0.3}) == {"b": 1, "a": 2}, "fractions")))
    archive = epoch_archive()
    mappings = epoch_document()["models"]
    judged("the score of an entry in a file is the best of the versions it lists there, and a version the file lacks, a file the archive lacks or an epoch that is unknown gives none",
           first_wrong((epoch_member_scores(mappings["p"], archive) == {"deepswe_external": 0.5, "swe_bench_verified": 0.7, "ale_bench_external": 1000},
                        "p: %r" % epoch_member_scores(mappings["p"], archive)),
                       (epoch_member_scores(mappings["u"], archive) == {}, "a version the file lacks"),
                       (epoch_member_scores(mappings["t"], archive) == {} and epoch_member_scores(None, archive) == {}, "unknown"),
                       (epoch_member_scores(dict(mappings["p"], epoch={"webdev_arena_external": ["p_high"]}), archive) == {}, "another arena was read"),
                       (epoch_member_scores(mappings["q"], epoch_archive({"deepswe_external": {"q_high": 0.1}})) == {"deepswe_external": 0.1},
                        "a file the archive lacks was invented")))
    quality = code_quality(["p", "q", "r", "s", "t", "u", "v", "z"], mappings, archive)

    def ranks(name):
        return {key: rank for key, (rank, _) in quality[name]["ranks"].items()}

    judged("per benchmark file the members are ranked among those that have a score, and the code quality is the median of the ranks",
           first_wrong((ranks("p") == {"deepswe_external": 4, "swe_bench_verified": 2, "ale_bench_external": 3} and quality["p"]["median"] == 3,
                        "p: %r" % quality["p"]),
                       (ranks("q") == {"deepswe_external": 2.5, "swe_bench_verified": 3, "ale_bench_external": 4} and quality["q"]["median"] == 3,
                        "q, who is tied in DeepSWE: %r" % quality["q"]),
                       (ranks("r") == {"deepswe_external": 2.5, "ale_bench_external": 2} and quality["r"]["median"] == 2.25,
                        "r, ranked on two files: %r" % quality["r"]),
                       (ranks("v") == {"deepswe_external": 1, "ale_bench_external": 1} and quality["v"]["median"] == 1, "v"),
                       (quality["p"]["ranks"]["deepswe_external"] == (4, 4) and quality["p"]["ranks"]["swe_bench_verified"] == (2, 3),
                        "the number of members scored is not kept: %r" % quality["p"]["ranks"])))
    judged("a benchmark file with fewer than two members of the cascade scored does not count, and a member ranked on fewer than two files is unrankable and says why",
           first_wrong(("cursorbench_external" not in ranks("q") and "terminalbench_external" not in ranks("s"), "a file with one member counted"),
                       (quality["s"]["median"] is None and quality["s"]["why"] == "few_files" and ranks("s") == {"swe_bench_verified": 1}
                        and quality["s"]["scored"] == 2, "s: %r" % quality["s"]),
                       (quality["t"]["median"] is None and quality["t"]["why"] == "no_ids", "t: %r" % quality["t"]),
                       (quality["u"]["median"] is None and quality["u"]["why"] == "no_scores", "u: %r" % quality["u"]),
                       (quality["z"]["why"] == "no_ids", "a member with no mapping at all"),
                       (all(found["why"] is None for name, found in quality.items() if found["median"] is not None), "a ranked member says why")))
    judged("a pool of fewer than two members ranks nothing, and a file the pool makes count depends on the pool only",
           first_wrong((all(found["median"] is None for found in code_quality(["p"], mappings, archive).values()), "a pool of one ranked someone"),
                       (all(found["ranks"] == {} for found in code_quality(["p"], mappings, archive).values()), "a pool of one counted a file"),
                       (set(code_quality(["p", "q"], mappings, archive)["p"]["ranks"]) == {"deepswe_external", "swe_bench_verified", "ale_bench_external"},
                        "p and q alone rank three files"),
                       (code_quality(["p", "q"], mappings, archive)["p"]["median"] == 1 and code_quality(["p", "q"], mappings, archive)["q"]["median"] == 2,
                        "p and q alone: %r" % code_quality(["p", "q"], mappings, archive))))

    # The order a router's contract gives: the members the archive ranks first by their median, then the
    # others on the index that stands in, and the tail as before.
    template, problems = read_template(EPOCH_TEMPLATE)
    if template is None or problems:
        print("selftest: BROKEN CASE (the template of the code quality) -- %r" % problems)
        return failures + 1
    document, ranking = epoch_document(), epoch_ranking()
    report = contracts_report(template, ranking, document, archive)
    code, code_order = contract_rows(report, "code")
    claude, claude_order = contract_rows(report, "claude-code")
    judged("code is ordered by code quality: the ranked members by median with the shorter time between equal ones, then the unrankable ones on the intelligence index, then the last resort and the members under the floor",
           first_wrong((code_order["proposed"] == ["r", "q", "p", "s", "t", "u", "v", "z"], "code: %r" % code_order["proposed"]),
                       (code["v"]["kind"] == "below_floor" and code["v"]["quality"]["median"] == 1, "v, first on code quality, is not under the floor"),
                       (code["z"]["last_resort"] and code["z"]["quality"]["why"] == "no_ids", "z"),
                       (code_order["current"] == ["p", "q", "r", "s", "t", "u", "v", "z"], "the current order moved")))
    judged("claude-code is ranked as code is: the quality code gives its members, the same order for the members they share, and a member that code does not hold is unrankable and goes after the others on the index",
           first_wrong((claude_order["proposed"] == ["q", "p", "s", "y", "t"], "claude-code: %r" % claude_order["proposed"]),
                       (claude["y"]["quality"] == {"ranks": {}, "median": None, "why": "outside", "scored": 0},
                        "y, whose scores the archive has, is ranked on a pool that is not code's: %r" % claude["y"]["quality"]),
                       ([name for name in claude_order["proposed"] if name in code_order["proposed"]]
                        == [name for name in code_order["proposed"] if name in claude_order["proposed"]], "the order of the common members differs"),
                       (claude["p"]["quality"] == code["p"]["quality"] and claude["q"]["quality"] == code["q"]["quality"], "a member's quality differs")))
    judged("the same members tied on code quality are told apart by their time and then by their position, and the members unrankable by it by the index with the time inside the margin",
           first_wrong((report["routers"][0]["proposed"].index("q") < report["routers"][0]["proposed"].index("p"), "q is faster than p"),
                       (claude_order["proposed"].index("y") < claude_order["proposed"].index("t"), "y is within 2 points of t and faster")))

    def order_rows(*members):
        return [{"name": name, "position": number, "kind": "conforming", "last_resort": False,
                 "intelligence": index, "first_answer": seconds,
                 "record": {"intelligence": index, "first_answer": seconds}, "quality": {"median": median}}
                for number, (name, median, index, seconds) in enumerate(members)]

    contract_ranking_block = {"criterion": "code_quality", "tie_margin_points": 2}
    judged("equal medians are ordered by time, a member with no time after the others, then by position; the unrankable follow in the order of the index",
           first_wrong((contract_order(order_rows(("a", 2, 9, 5), ("b", 2, 9, 3), ("c", 2, 9, None), ("d", 2, 9, 3)), contract_ranking_block)
                        == ["b", "d", "a", "c"], "ties"),
                       (contract_order(order_rows(("a", None, 10, 1), ("b", 5, 1, 9), ("c", None, 30, 9), ("d", 1.5, 2, 9)), contract_ranking_block)
                        == ["d", "b", "c", "a"], "ranked first, whatever their index"),
                       (contract_order(order_rows(("a", 1, 9, 5)) + [dict(order_rows(("z", 9, 9, 1))[0], last_resort=True)], contract_ranking_block)
                        == ["a", "z"], "the last resort stays at the tail whatever its quality")))
    judged("a router with no code quality read is ordered as before, on the intelligence index alone",
           first_wrong((contract_order([dict(row, quality=None) for row in order_rows(("a", 1, 5, 1), ("b", 9, 30, 1))], contract_ranking_block)
                        == ["b", "a"], "a member with a quality was ranked on it without the archive"),
                       (contract_order([{key: value for key, value in row.items() if key != "quality"}
                                        for row in order_rows(("a", 1, 5, 1), ("b", 9, 30, 1))], contract_ranking_block) == ["b", "a"],
                        "rows with no quality at all")))
    stand_in = contracts_report(template, ranking, document)
    failed_read = contracts_report(template, ranking, document, {"status": "error", "date": "2026-01-02", "error": "HTTP 404"})
    stand_code, stand_order = contract_rows(stand_in, "code")
    judged("without the archive, read or failed, code and claude-code keep the intelligence index as their order, with no quality on any row",
           first_wrong((stand_order["proposed"] == ["q", "p", "r", "s", "t", "u", "v", "z"], "code: %r" % stand_order["proposed"]),
                       (contract_rows(stand_in, "claude-code")[1]["proposed"] == ["q", "p", "s", "y", "t"],
                        "claude-code: %r" % contract_rows(stand_in, "claude-code")[1]["proposed"]),
                       (all(row["quality"] is None for row in stand_code.values()) and stand_order["quality"] is None, "a quality without the archive"),
                       ([entry["proposed"] for entry in failed_read["routers"]] == [entry["proposed"] for entry in stand_in["routers"]], "a failed read moved an order"),
                       (stand_in["epoch"] == {"status": "unread"} and failed_read["epoch"] == {"status": "error", "date": "2026-01-02", "error": "HTTP 404"},
                        "states: %r %r" % (stand_in["epoch"], failed_read["epoch"])),
                       (report["epoch"]["status"] == "read" and report["epoch"]["date"] == "2026-01-02" and sorted(report["epoch"]["files"]) == sorted(EPOCH_KEYS),
                        "state of a read: %r" % report["epoch"])))
    other_routers = contracts_report(template, ranking, document, archive)
    judged("a criterion other than code quality is not touched by the archive",
           first_wrong((contracts_report(read_template(CONTRACT_TEMPLATE)[0], contract_ranking(), contract_document(), archive)["routers"][0]["proposed"]
                        == contracts_report(read_template(CONTRACT_TEMPLATE)[0], contract_ranking(), contract_document())["routers"][0]["proposed"],
                        "pro moved"),
                       (all(entry["quality"] is None for entry in contracts_report(
                           read_template(CONTRACT_TEMPLATE)[0], contract_ranking(), contract_document(), archive)["routers"]
                            if entry["name"] in ("pro", "flash", "flash-lite")), "a router that is not on code quality got one"),
                       (other_routers["routers"][0]["quality"] is not None, "code got none")))

    # The same archive through the reader gives the same orders: the zip, the reader and the ranking agree.
    through, _ = epoch_read(epoch_zip(epoch_members()))
    judged("the archive read from its bytes orders the cascades as the archive built directly does",
           first_wrong(([entry["proposed"] for entry in contracts_report(template, ranking, document, through)["routers"]]
                        == [entry["proposed"] for entry in report["routers"]], "the orders differ")))

    # The issue.
    section = "\n".join(contracts_section({"contracts": report}))
    code_block = section.split("### `code`")[1].split("### `claude-code`")[0]
    claude_block = section.split("### `claude-code`")[1]
    judged("the issue says, for code and claude-code, each member's rank in each benchmark, the median, the position, who is unrankable and why, and that they are ordered on the intelligence index, with the attribution and the day of the reading",
           first_wrong(
               ("Qualité de code, d'après Epoch AI, benchmark data, CC BY 4.0 (<https://epoch.ai/benchmarks>, archive lue le 2026-01-02)." in code_block
                and "Qualité de code, d'après Epoch AI, benchmark data, CC BY 4.0" in claude_block, "the attribution or the day is missing"),
               ("| Membre | DeepSWE | SWE-bench Verified | CursorBench | Terminal-Bench | ALE-Bench | Médiane | Position |" in code_block, "the table"),
               ("| `r` | 2.5/4 | — | — | — | 2/4 | 2.25 | 1 |" in code_block, "r: %s" % code_block[:2500]),
               ("| `q` | 2.5/4 | 3/3 | — | — | 4/4 | 3 | 2 |" in code_block and "| `p` | 4/4 | 2/3 | — | — | 3/4 | 3 | 3 |" in code_block,
                "q and p"),
               ("| `s` | — | 1/3 | — | — | — | — | inclassable : indice d'intelligence |" in code_block, "s"),
               ("| `v` | 1/4 | — | — | — | 1/4 | 1 | sous le plancher |" in code_block, "v is ranked and under the floor"),
               ("| `z` | — | — | — | — | — | — | dernier recours |" in code_block, "z"),
               ("Benchmarks sans effet sur cette cascade (moins de deux membres y ont un score) : CursorBench, Terminal-Bench." in code_block, "files that do not count"),
               ("Inclassables par la qualité de code, placés après les membres classés et ordonnés sur l'indice d'intelligence qui en tient lieu : "
                "`s` (1 benchmark(s) comptant(s) pour lui, 2 requis), `t` (aucun identifiant Epoch connu), "
                "`u` (aucun score dans l'archive pour ses identifiants)." in code_block, "the unrankable: %s" % code_block[-900:]),
               ("de la cascade de `code` qui y ont" in claude_block and "hors de la cascade de `code`" in claude_block, "claude-code's pool is not said"),
               ("| `y` | — | — | — | — | — | — | inclassable : indice d'intelligence |" in claude_block, "y"),
               ("Ordre des contrats : `r` > `q` > `p` > `s` > `t` > `u` > `v` > `z`." in code_block, "the order"),
               ("WebDev Arena et toute arène de design ou d'interface ne sont pas lues." in code_block, "the exclusion is not said"),
               ("(source : Epoch AI selftest source, lue le 2026-01-02), la médiane des rangs sur les benchmarks" in code_block
                and "ordonnés sur l'indice d'intelligence, le délai départageant deux membres à moins de 2 points d'écart" in code_block,
                "the ranking is not said: %s" % code_block[:700]),
               ("non lue" not in section, "an archive that was read is said not to be")))
    skipped = dict(archive, skipped={"swe_bench_verified": "absent from the archive"})
    skipped["files"] = {key: found for key, found in archive["files"].items() if key != "swe_bench_verified"}
    skipped_section = "\n".join(contracts_section({"contracts": contracts_report(template, ranking, document, skipped)}))
    judged("a file of the archive that was not read is said, and its figures are not used",
           first_wrong(("Fichiers de l'archive non lus : SWE-bench Verified (`absent from the archive`)." in skipped_section, "the skipped file is not said"),
                       ("| `s` | — | — | — | — | — | — |" in skipped_section, "s was ranked on a file that was not read")))
    unread_section = "\n".join(contracts_section({"contracts": stand_in}))
    failed_section = "\n".join(contracts_section({"contracts": failed_read}))
    judged("an archive that was not read leaves the stand-in, and the issue says that the source is not read: no quality block, no rank",
           first_wrong(("(source : Epoch AI selftest source, non lue) ; Artificial Analysis n'a pas d'indice de code, l'indice d'intelligence en tient lieu à titre provisoire"
                        in unread_section, "unread: %s" % unread_section[:500]),
                       ("(source : Epoch AI selftest source, non lue (HTTP 404)) ; Artificial Analysis n'a pas d'indice de code" in failed_section,
                        "failed: %s" % failed_section[:500]),
                       ("Qualité de code, d'après" not in unread_section and "Qualité de code, d'après" not in failed_section, "a quality block without the archive"),
                       ("Ordre des contrats : `q` > `p` > `r` > `s` > `t` > `u` > `v` > `z`." in unread_section, "the order moved without the archive"),
                       ("CC BY" not in unread_section and "CC BY" not in failed_section, "an attribution for a source that was not read")))
    judged("what the archive carries into the issue is cut to plain words",
           first_wrong((hostile_lines("\n".join(contracts_section({"contracts": contracts_report(template, ranking, document, dict(
               archive, skipped={"deepswe_external": "@bob <img src=x> ::error:: `x`"}))}))) is None, "markup from a reason reached the issue")))

    # The run: the archive is read by the online run that has the contracts, after the ranking, and by no other.
    with tempfile.TemporaryDirectory() as directory:
        run_document = contract_document()
        run_document["models"]["alpha"]["epoch"] = {"deepswe_external": ["alpha_medium"], "swe_bench_verified": ["alpha_medium"]}
        run_document["models"]["oscar"]["epoch"] = {"deepswe_external": ["oscar_high"], "swe_bench_verified": ["oscar_high"]}
        run, config, path, issue = contracts_runner(directory, run_document)
        run_archive = epoch_zip(epoch_members({"deepswe_external": {"alpha_medium": 0.4, "oscar_high": 0.8},
                                               "swe_bench_verified": {"alpha_medium": 0.9, "oscar_high": 0.5}}))
        online = ["--online", "--config", config, "--issue-body", issue, "--contracts", path]
        status, out, body, asked = run(online, run_archive)
        status_none, out_none, body_none, asked_none = run(online)
        section = body.split("## Contrats par routeur")[1].split("\n## ")[0]
        none_section = body_none.split("## Contrats par routeur")[1].split("\n## ")[0]
        judged("the online run that has the contracts reads the archive once, and the issue orders code on it",
               first_wrong((asked == [EPOCH_URL], "asked: %r" % asked),
                           ("Ordre des contrats : `alpha` > `oscar` > `sierra`." in section, "the order of code: %s" % section[:200]),
                           ("(source : Epoch AI selftest source, lue le " in section and "Epoch AI, benchmark data, CC BY 4.0" in section, "the source"),
                           ("| `alpha` | 2/2 | 1/2 | — | — | — | 1.5 | 1 |" in section and "| `oscar` | 1/2 | 2/2 | — | — | — | 1.5 | 2 |" in section,
                            "the ranks of the two: %s" % section),
                           ("epoch " in out and "read, 2 of the 5 benchmark file(s)" in out and "Epoch AI, benchmark data, CC BY 4.0" in out, "the log: %s" % out)))
        judged("an archive nobody serves is a read that failed: the issue and the log say so, the order is the stand-in's, and nothing else of the run moves",
               first_wrong((asked_none == [EPOCH_URL], "asked: %r" % asked_none),
                           ("Ordre des contrats : `oscar` > `alpha` > `sierra`." in none_section, "the stand-in order: %s" % none_section[:200]),
                           ("non lue (HTTP 404)" in none_section and "Qualité de code, d'après" not in none_section, "the failure is not said"),
                           ("ERROR, not read: HTTP 404" in out_none, "the log: %s" % out_none),
                           (status_none == status and "Aucune dérive." in body_none and "Aucune dérive." in body, "the status or the drift moved"),
                           (body.split("## Contrats par routeur")[0] == body_none.split("## Contrats par routeur")[0], "the rest of the issue moved")))
        status_bad, _, body_bad, _ = run(online, b"not an archive")
        status_boom, _, body_boom, _ = run(online, RuntimeError("selftest: SECRET"))
        judged("an answer that is no archive, or a reader that fails, is a read that failed and never the run's failure",
               first_wrong(("non lue (the answer is not a zip archive)" in body_bad, "not an archive: %s" % body_bad[-600:]),
                           ("non lue (failed: RuntimeError)" in body_boom and "SECRET" not in body_boom, "a failing opener"),
                           (status_bad == status and status_boom == status, "the status moved")))
        status_off, _, body_off, asked_off = run(online, run_archive, environment=SELFTEST_KEYS)
        status_other, _, body_other, asked_other = run(["--online", "--config", config, "--issue-body", issue], run_archive)
        judged("the archive is not read where there is no section to use it: without the ranking, or with another template and no contracts",
               first_wrong((asked_off == [] and asked_other == [], "asked: %r %r" % (asked_off, asked_other)),
                           ("## Contrats par routeur" not in body_off and "## Contrats par routeur" not in body_other, "a section without its inputs")))

        def refusing(url, headers, limit=None):
            raise AssertionError("the plain run reached the network: %s" % url)

        status_plain, out_plain, _, _ = run(["--config", config, "--contracts", path], opener=refusing)
        judged("the plain run stays offline: it reads the contracts, never the archive",
               first_wrong((status_plain == 0 and "holds a contract for each router" in out_plain, "the plain run: %s" % out_plain)))
    judged("the repository's contracts name only benchmark files the reader reads",
           first_wrong((offline_contract_problems(CONFIG.read_text(encoding="utf-8"), CONTRACTS) == [], "a problem of the real file")))
    return failures


def run_eci_cases():
    """The capabilities index of Epoch AI: read from the same archive, converted to the scale of the
    intelligence index, and used for the floors that name a model of it and for the members the ranking
    has no figure for. Made-up archives and members only."""
    failures = 0

    def judged(purpose, why):
        nonlocal failures
        if why is None:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s) -- %s" % (purpose, why))

    def first_wrong(*checks):
        return next((message for ok, message in checks if not ok), None)

    # Reading: the member of the archive is found by its exact name, and its absence or its rows change nothing else.
    good, _ = epoch_read(epoch_zip(epoch_members()))
    judged("the capabilities index is read from its member of the same archive: a figure by display name, nothing else of that folder",
           first_wrong((good["status"] == "read" and good["eci"] == EPOCH_ECI and good["skipped"] == {}, "state: %r" % good),
                       (sorted(good["files"]) == sorted(EPOCH_KEYS), "the benchmark files moved")))
    missing, _ = epoch_read(epoch_zip({name: text for name, text in epoch_members().items() if name != EPOCH_ECI_MEMBER}))
    judged("a capabilities index that the archive lacks is skipped and said, and the benchmark files are read as before",
           first_wrong((missing["status"] == "read" and missing["eci"] == {}, "state: %r" % missing),
                       (missing["skipped"] == {EPOCH_ECI_KEY: "absent from the archive"}, "skipped: %r" % missing["skipped"]),
                       (sorted(missing["files"]) == sorted(EPOCH_KEYS), "the benchmark files were lost with it")))
    rough_rows = "x,,151,0,d\nx,Nobody,abc,0,d\nx,Nan,nan,0,d\nx,Inf,inf,0,d\nx,Blank,,0,d\nx,Short\nx,  Spaced  ,141,0,d\nx,Dup,145,0,d\n"
    rough, _ = epoch_read(epoch_zip(dict(epoch_members(None, None, {}), **{EPOCH_ECI_MEMBER: eci_csv({"Good": 150, "Dup": 140}, rough_rows)})))
    judged("bad rows of the capabilities index are tolerated: no name, no figure, a figure that is no finite number, a ragged row; a name listed twice keeps its best figure",
           first_wrong((rough["status"] == "read", "state: %r" % rough),
                       (rough["eci"] == {"Good": 150.0, "Spaced": 141.0, "Dup": 145.0}, "eci: %r" % rough["eci"]),
                       (EPOCH_ECI_KEY not in rough["skipped"], "skipped: %r" % rough["skipped"])))
    wrong, _ = epoch_read(epoch_zip(dict(epoch_members(), **{EPOCH_ECI_MEMBER: "Model,Name,score\nA,A,150\n"})))
    empty, _ = epoch_read(epoch_zip(dict(epoch_members(), **{EPOCH_ECI_MEMBER: "Model,Display name,eci\n"})))
    big, _ = epoch_read(epoch_zip(dict(epoch_members(), **{EPOCH_ECI_MEMBER: eci_csv({"Model %d" % number: 150 for number in range(80)})})),
                        EPOCH_MAX_MEMBER=800)
    judged("a capabilities index with the wrong columns, no row or more than the cap is skipped and said, and leaves everything else read",
           first_wrong((wrong["eci"] == {} and wrong["skipped"] == {EPOCH_ECI_KEY: "it has not the columns expected"}, "wrong: %r" % wrong["skipped"]),
                       (empty["eci"] == {} and empty["skipped"] == {EPOCH_ECI_KEY: "it has no usable row"}, "empty: %r" % empty["skipped"]),
                       (big["eci"] == {} and big["skipped"] == {EPOCH_ECI_KEY: "larger than 800 bytes"}, "big: %r" % big["skipped"]),
                       (all(state["status"] == "read" and sorted(state["files"]) == sorted(EPOCH_KEYS) for state in (wrong, empty, big)),
                        "a benchmark file was lost")))
    only, _ = epoch_read(epoch_zip({EPOCH_ECI_MEMBER: eci_csv(EPOCH_ECI)}))
    judged("an archive whose only usable member is the capabilities index is read, and one with nothing usable is not",
           first_wrong((only["status"] == "read" and only["files"] == {} and only["eci"] == EPOCH_ECI, "state: %r" % only),
                       (sorted(only["skipped"]) == sorted(EPOCH_KEYS), "skipped: %r" % only["skipped"]),
                       (epoch_read(epoch_zip({EPOCH_ECI_MEMBER: "Model,Name\n"}))[0]["status"] == "error", "nothing usable was read")))

    # The conversion: a line through the points, the slope of an end segment going on beyond it, never below 0.
    points = [(140.0, 4.0), (150.0, 20.0), (160.0, 20.0), (170.0, 50.0)]

    def converted(value, calibration=points):
        found = eci_to_index(value, calibration)
        return None if found is None else round(found, 9)

    judged("a capabilities index is turned into an index by the line through the points, the slope of the end segments going on beyond them, and never below 0",
           first_wrong((converted(140) == 4 and converted(150) == 20 and converted(160) == 20 and converted(170) == 50, "a point is not itself"),
                       (converted(145) == 12 and converted(165) == 35, "inside a sloping segment"),
                       (converted(155) == 20, "inside a flat segment"),
                       (converted(138) == 0.8 and converted(135) == 0 and converted(100) == 0, "below the first point: slope on, then 0"),
                       (converted(175) == 65 and converted(180) == 80, "above the last point: slope on"),
                       (converted(150.0001) > 20 - 1e-9, "a point is not continuous"),
                       (converted(150, [(140.0, 4.0), (150.0, 4.0)]) == 4 and converted(139, [(140.0, 4.0), (150.0, 4.0)]) == 4, "a flat line"),
                       (converted(150, [(140.0, 4.0)]) is None and converted(150, []) is None, "a calibration of fewer than two points converted")))
    scale = eci_scale(epoch_archive(), contract_document())
    judged("a scale needs the archive read, a capabilities index in it and the calibration of the contracts, and is none otherwise",
           first_wrong((scale is not None and scale["eci"] == EPOCH_ECI and scale["points"] == [tuple(map(float, point)) for point in contract_document()["fallback_index"]["points"]],
                        "scale: %r" % scale),
                       (eci_scale(None, contract_document()) is None, "an archive that was not read gave a scale"),
                       (eci_scale({"status": "error"}, contract_document()) is None, "a failed read gave a scale"),
                       (eci_scale(epoch_archive(eci={}), contract_document()) is None, "an empty index gave a scale"),
                       (eci_scale(epoch_archive(), {}) is None, "no calibration gave a scale"),
                       (eci_scale(epoch_archive(), {"fallback_index": {"points": [[140, 4]]}}) is None, "one point gave a scale"),
                       (eci_scale(epoch_archive(), {"fallback_index": {"points": [[140, "4"], [150, 5]]}}) is None, "a bad point gave a scale")))

    # Anchors and floors on the capabilities index, on the cascades of CONTRACT_TEMPLATE.
    template = read_template(CONTRACT_TEMPLATE)[0]
    ranking = contract_ranking()
    archive = epoch_archive({}, EPOCH_ECI)

    def eci_document():
        document = contract_document()
        document["routers"]["pro"]["intelligence_floor"] = {
            "anchor": {"epoch": "Floor Model"}, "reason": "selftest",
            "candidates": [{"epoch": "Floor Model"}, {"entry": "alpha", "level": "high"}, {"epoch": "Pee Model"}]}
        document["models"]["echo"]["eci"] = "Que Model"
        document["models"]["charlie"]["eci"] = "Floor Model"
        document["models"]["delta"]["eci"] = "Pee Model"
        document["models"]["alpha"]["eci"] = "High Model"
        document["models"]["juliet"]["eci"] = "Low Model"
        return document

    document = eci_document()
    report = contracts_report(template, ranking, document, archive)
    pro, pro_order = contract_rows(report, "pro")
    floor = pro_order["contract"]["intelligence_floor"]
    judged("an anchor that names a model of the capabilities index has its index converted, and said estimated; the candidates are read the same way",
           first_wrong((floor["value"] == 20 and floor["text"] == "Floor Model (Epoch, estimé)", "floor: %r %r" % (floor["value"], floor["text"])),
                       (floor["candidates"] == [20, 40, 12] and floor["candidate_texts"] == ["Floor Model (Epoch, estimé)", "Alpha (High)", "Pee Model (Epoch, estimé)"],
                        "candidates: %r %r" % (floor["candidates"], floor["candidate_texts"])),
                       ([effect["floor"] for effect in pro_order["floors"]] == [20, 40, 12], "floors side by side: %r" % pro_order["floors"])))

    def anchored(anchor, given=scale):
        return anchor_floor(anchor, document["models"], {}, {}, given)

    judged("an anchor on the capabilities index that cannot be read has no value and says why: the archive not read, the index empty, or the model not in it",
           first_wrong((anchored({"epoch": "Pee Model"}) == (12, "Pee Model (Epoch, estimé)"), "found: %r" % (anchored({"epoch": "Pee Model"}),)),
                       (anchored({"epoch": "Low Model"}) == (0, "Low Model (Epoch, estimé)"), "a figure converted to 0 is a floor of 0"),
                       (anchored({"epoch": "Nobody"}) == (None, "Nobody (Epoch, estimé) : absent de l'indice de capacités"), "%r" % (anchored({"epoch": "Nobody"}),)),
                       (anchored({"epoch": "Pee Model"}, None) == (None, "Pee Model (Epoch, estimé) : indice de capacités non lu"),
                        "%r" % (anchored({"epoch": "Pee Model"}, None),))))
    unread = contracts_report(template, ranking, document)
    unread_pro, unread_order = contract_rows(unread, "pro")
    unread_section = "\n".join(contracts_section({"contracts": unread}))
    judged("with the archive not read, an anchor on the capabilities index has no value, nothing is judged against it and the issue says introuvable and why, as for an entry that cannot be read",
           first_wrong((unread_order["contract"]["intelligence_floor"]["value"] is None, "a floor with a value"),
                       (unread_order["contract"]["intelligence_floor"]["candidates"] == [40], "the candidates that can be read are not compared: %r" % unread_order["contract"]["intelligence_floor"]["candidates"]),
                       (not any(row["kind"] == "below_floor" for row in unread_pro.values()), "a member was put under a floor that is not there"),
                       (unread_pro["echo"]["kind"] == "unrankable" and unread_pro["echo"]["verdict"] == "inclassable : pas d'indice"
                        and unread_pro["delta"]["kind"] == "unverified" and unread_pro["charlie"]["kind"] == "unverified",
                        "a member was placed on an estimate nobody read"),
                       ("Plancher introuvable (Floor Model (Epoch, estimé) : indice de capacités non lu), aucun membre n'est jugé sous le plancher" in unread_section,
                        "the floor is not said: %s" % unread_section[:900]),
                       ("n'est pas lu, l'archive étant non lue" in unread_section, "the index is not said unread"),
                       (unread_order["proposed"] == ["alpha", "india", "juliet", "foxtrot"], "pro: %r" % unread_order["proposed"])))

    # A member the ranking has no figure for at the level it is called at is placed on the estimate of its entry.
    judged("a member with no index at the level it is called at is placed on the estimate its capabilities index gives, a member the ranking has an index for never is, and the tail keeps its order",
           first_wrong((pro["echo"]["intelligence"] == 35 and pro["echo"]["estimated"] and pro["echo"]["kind"] == "conforming", "echo: %r" % pro["echo"]["verdict"]),
                       (pro["charlie"]["intelligence"] == 20 and pro["charlie"]["estimated"] and pro["charlie"]["kind"] == "conforming",
                        "charlie, unverified, at the floor exactly: %r" % pro["charlie"]["verdict"]),
                       (pro["delta"]["intelligence"] == 12 and pro["delta"]["kind"] == "below_floor", "delta, unverified, under the floor: %r" % pro["delta"]["verdict"]),
                       (pro["alpha"]["intelligence"] == 30 and not pro["alpha"]["estimated"] and pro["alpha"]["verdict"] == "conforme",
                        "alpha has an index at its level and was given its estimate: %r" % pro["alpha"]["verdict"]),
                       (pro["india"]["intelligence"] == 8 and not pro["india"]["estimated"] and pro["india"]["kind"] == "below_floor", "india"),
                       (pro["juliet"]["last_resort"] and pro["juliet"]["verdict"] == "conforme (dernier recours)", "a member of the last resort keeps its words"),
                       (pro_order["proposed"] == ["echo", "alpha", "charlie", "delta", "india", "juliet", "foxtrot"], "pro: %r" % pro_order["proposed"])))
    judged("the verdict of a member placed on an estimate says so, and so does a member under the floor on one",
           first_wrong((pro["echo"]["verdict"] == "conforme (estimé)", "echo: %r" % pro["echo"]["verdict"]),
                       (pro["delta"]["verdict"] == "sous le plancher (12.0 estimé contre 20) : dernier recours", "delta: %r" % pro["delta"]["verdict"]),
                       (pro["india"]["verdict"] == "sous le plancher (8.0 contre 20) : dernier recours", "india, whose figure is the ranking's: %r" % pro["india"]["verdict"])))
    lost = contracts_report(template, ranking, document, dict(archive, eci={}, skipped={EPOCH_ECI_KEY: "absent from the archive"}))
    judged("an archive read without its capabilities index gives no estimate and no floor on it, and says why in the issue",
           first_wrong((contract_rows(lost, "pro")[1]["contract"]["intelligence_floor"]["value"] is None, "a floor from nothing"),
                       (contract_rows(lost, "pro")[0]["echo"]["estimated"] is False and contract_rows(lost, "pro")[0]["echo"]["intelligence"] is None, "an estimate from nothing"),
                       ("n'est pas lu (absent from the archive)" in "\n".join(contracts_section({"contracts": lost})), "the missing member is not said"),
                       (lost["eci_stale"] == [], "a name was called stale before the index was read")))
    section = "\n".join(contracts_section({"contracts": report}))
    pro_block = section.split("### `pro`")[1].split("### `flash`")[0]
    judged("the issue says the capabilities index was read from the same archive, with the attribution and the day, shows each estimate as estimated and each floor with its anchor named, the candidates side by side",
           first_wrong(("Indice de capacités d'Epoch AI (ECI), lu le 2026-01-02 dans la même archive : Epoch AI, benchmark data, CC BY 4.0 (<https://epoch.ai/benchmarks>)." in section
                        and "tout chiffre ainsi obtenu est une **estimation**, marquée « estimé »" in section, "the capabilities index is not said: %s" % section[:1700]),
                       ("Plancher 20 (Floor Model (Epoch, estimé)), un niveau de plus tant qu'il rapporte au moins 0.2 points d'indice par seconde de plus, classé par l'indice d'intelligence"
                        in pro_block, "the floor is not said: %s" % pro_block[:500]),
                       ("| `echo` | Echo | sans niveau | 35.0 (estimé) |" in pro_block and "conforme (estimé) |" in pro_block, "the estimate is not in the table: %s" % pro_block),
                       ("| `delta` | Delta (High) | medium | 12.0 (estimé) |" in pro_block
                        and "sous le plancher (12.0 estimé contre 20) : dernier recours |" in pro_block, "delta"),
                       ("| `alpha` | Alpha (Medium) | medium | 30.0 | 12.0 |" in pro_block, "an index of the ranking was flagged"),
                       ("| 20 (Floor Model (Epoch, estimé)) (proposé) |" in pro_block and "| 40 (Alpha (High)) |" in pro_block
                        and "| 12 (Pee Model (Epoch, estimé)) |" in pro_block, "the floors side by side: %s" % pro_block[-900:]),
                       ("Ordre des contrats : `echo` > `alpha` > `charlie` > `delta` > `india` > `juliet` > `foxtrot`." in pro_block, "the order"),
                       ("n'est pas lu" not in section.split("### `pro`")[0], "the index is said unread though it was read")))

    # A name the contracts keep that the index no longer holds is information, and nothing before the index is read.
    thin = contracts_report(template, ranking, document, epoch_archive({}, {"Que Model": 165.0}))
    thin_section = "\n".join(contracts_section({"contracts": thin}))
    judged("a name the capabilities index no longer holds is listed as stale, in a mapping or in an anchor, once it was read, and is no failure",
           first_wrong((sorted(thin["eci_stale"]) == sorted([("charlie", "Floor Model"), ("delta", "Pee Model"), ("alpha", "High Model"),
                                                              ("juliet", "Low Model"), ("", "Floor Model"), ("", "Pee Model")]),
                        "stale: %r" % thin["eci_stale"]),
                       ("Noms absents de l'indice de capacités d'Epoch AI (le nom est à corriger dans le fichier des contrats) :\n\n- `" in thin_section
                        and "- `charlie` : `Floor Model`\n" in thin_section
                        and "- ancre d'un plancher : `Floor Model`\n" in thin_section, "the issue does not list them: %s" % thin_section[-1500:]),
                       (report["eci_stale"] == [] and unread["eci_stale"] == [], "a name was stale in an index that holds it, or before it was read"),
                       (contract_rows(thin, "pro")[0]["charlie"]["estimated"] is False, "a stale name gave an estimate")))

    # No floor.
    template_lite = read_template(CONTRACT_TEMPLATE.replace("    - flash-lite: [kilo, india, bravo, lima, quebec]\n",
                                                            "    - flash-lite: [kilo, india, bravo, lima, quebec, echo, sierra]\n"))[0]
    lite_document = contract_document()
    lite_document["routers"]["flash-lite"]["intelligence_floor"] = {"none": True, "reason": "selftest"}
    lite_document["models"]["echo"]["eci"] = "Que Model"
    with_floor = contracts_report(template_lite, ranking, contract_document(), archive)
    no_floor = contracts_report(template_lite, ranking, lite_document, archive)
    held, held_order = contract_rows(with_floor, "flash-lite")
    free, free_order = contract_rows(no_floor, "flash-lite")
    free_section = "\n".join(contracts_section({"contracts": no_floor}))
    judged("a router with no floor has every member that is not otherwise excluded conform, a member with no index included, and nothing goes under the floor",
           first_wrong((held["echo"]["kind"] == "unrankable" and held["sierra"]["kind"] == "below_floor", "with a floor: %r %r" % (held["echo"]["kind"], held["sierra"]["kind"])),
                       (held_order["proposed"] == ["india", "bravo", "kilo", "lima", "sierra"], "with a floor: %r" % held_order["proposed"]),
                       (free["echo"]["kind"] == "conforming" and free["echo"]["verdict"] == "conforme" and not free["echo"]["estimated"],
                        "echo, with no index, in a router that needs none: %r" % free["echo"]["verdict"]),
                       (free["sierra"]["kind"] == "conforming", "sierra, under the old floor: %r" % free["sierra"]["verdict"]),
                       (not any(row["kind"] == "below_floor" for row in free.values()), "a member went under a floor that does not exist"),
                       (free["quebec"]["kind"] == "unrankable" and free["quebec"]["verdict"] == "inclassable : pas de délai", "a member with no time was placed"),
                       (free_order["proposed"] == ["india", "echo", "bravo", "kilo", "sierra", "lima"], "ordered by time alone: %r" % free_order["proposed"]),
                       (free_order["contract"]["intelligence_floor"]["value"] is None and free_order["contract"]["intelligence_floor"]["candidates"] == []
                        and free_order["floors"] == [], "the floor has a value or candidates: %r" % free_order["floors"])))
    judged("the issue says that a router has no floor, in its sentence and not as a floor that could not be found",
           first_wrong(("Aucun plancher, un niveau de plus tant qu'il rapporte au moins 1.5 points d'indice par seconde de plus, classé par le délai le plus court." in free_section,
                        "the sentence: %s" % free_section[:3000]),
                       ("introuvable" not in free_section.split("### `flash-lite`")[1].split("### `code`")[0], "no floor was said not found"),
                       ("Effet de chaque plancher" not in free_section.split("### `flash-lite`")[1].split("### `code`")[0], "a table of floors for no floor")))
    lite_floored = contract_document()
    lite_floored["models"]["echo"]["eci"] = "Que Model"
    floored, _ = contract_rows(contracts_report(template_lite, ranking, lite_floored, archive), "flash-lite")
    judged("a router ordered by time takes no estimate from the capabilities index, with a floor or without: its time comes from the ranking",
           first_wrong((floored["echo"]["estimated"] is False and floored["echo"]["intelligence"] is None and floored["echo"]["kind"] == "unrankable",
                        "echo was estimated in flash-lite: %r" % floored["echo"]["verdict"]),
                       (free["echo"]["estimated"] is False and free["echo"]["intelligence"] is None, "echo was estimated with no floor")))

    # claude-code follows code, estimates included.
    estimates = contracts_report(template, ranking, document, archive)
    code, code_order = contract_rows(estimates, "code")
    claude, claude_order = contract_rows(estimates, "claude-code")
    judged("claude-code is ordered as code is on the estimates too: the same floor, the same figures, the same order for the members they share",
           first_wrong((code_order["proposed"] == ["oscar", "alpha", "delta", "sierra"], "code: %r" % code_order["proposed"]),
                       (claude_order["proposed"] == ["echo", "alpha", "quebec", "delta"], "claude-code: %r" % claude_order["proposed"]),
                       (claude["echo"]["estimated"] and claude["echo"]["verdict"] == "conforme (estimé)", "echo: %r" % claude["echo"]["verdict"]),
                       (claude["delta"]["verdict"] == "sous le plancher (12.0 estimé contre 20) : dernier recours"
                        and code["delta"]["verdict"] == claude["delta"]["verdict"], "delta"),
                       (claude["november"]["kind"] == "no_tools", "a member with no tools was placed on an estimate"),
                       (code_order["contract"]["intelligence_floor"]["value"] == claude_order["contract"]["intelligence_floor"]["value"] == 20, "the floor"),
                       ([name for name in claude_order["proposed"] if name in code_order["proposed"]]
                        == [name for name in code_order["proposed"] if name in claude_order["proposed"]], "the order of the shared members differs")))

    # Structure.
    problems_template = read_template(CONTRACT_TEMPLATE)[0]

    def mutated(change):
        mutant = eci_document()
        change(mutant)
        return contracts_problems(mutant, problems_template)

    def set_in(path, value):
        def change(mutant):
            target = mutant
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
        return change

    def drop(*path):
        def change(mutant):
            target = mutant
            for key in path[:-1]:
                target = target[key]
            del target[path[-1]]
        return change

    floor_path = ("routers", "pro", "intelligence_floor")
    structural = (
        ("an anchor on the capabilities index", set_in(floor_path + ("anchor",), {"epoch": "Pee Model"}), None),
        ("a router with no floor", set_in(floor_path, {"none": True, "reason": "x"}), None),
        ("a router with no floor and an anchor", set_in(floor_path, {"none": True, "reason": "x", "anchor": {"epoch": "Pee Model"}}), 'says "none" and so names no "anchor" and no "candidates"'),
        ("a router with no floor and candidates", set_in(floor_path, {"none": True, "reason": "x", "candidates": []}), 'says "none" and so names no "anchor" and no "candidates"'),
        ("a router with no floor and no reason", set_in(floor_path, {"none": True}), '"intelligence_floor", has no "reason"'),
        ("a no-floor that is false", set_in(floor_path, {"none": False, "reason": "x"}), 'has a "none" that is not true'),
        ("a no-floor that is a word", set_in(floor_path, {"none": "yes", "reason": "x"}), 'has a "none" that is not true'),
        ("an anchor naming an entry and a model", set_in(floor_path + ("anchor",), {"entry": "alpha", "epoch": "Pee Model"}), 'names both an "entry" and an "epoch" model: exactly one'),
        ("an anchor with a blank model", set_in(floor_path + ("anchor",), {"epoch": " "}), 'has an "epoch" that is no model name'),
        ("an anchor with a model that is no text", set_in(floor_path + ("anchor",), {"epoch": 5}), 'has an "epoch" that is no model name'),
        ("an anchor on a model with a level", set_in(floor_path + ("anchor",), {"epoch": "Pee Model", "level": "low"}), 'names an "epoch" model, which has no "level"'),
        ("an anchor naming nothing", set_in(floor_path + ("anchor",), {"level": "low"}), 'must be a mapping that names an "entry" or an "epoch" model'),
        ("a candidate naming a model that is no text", set_in(floor_path + ("candidates",), [{"epoch": ["x"]}]), 'candidate 1 has an "epoch" that is no model name'),
        ("a mapping with an eci that is blank", set_in(("models", "echo", "eci"), " "), 'has an "eci" that is no model name of the capabilities index'),
        ("a mapping with an eci that is no text", set_in(("models", "echo", "eci"), 150), 'has an "eci" that is no model name of the capabilities index'),
        ("the capabilities index used with no calibration", drop("fallback_index"), 'declares no "fallback_index" calibration'),
        ("a calibration of one point", set_in(("fallback_index", "points"), [[140, 4]]), 'must list its calibration "points" as pairs of numbers, two at least'),
    )
    for purpose, change, needle in structural:
        found = mutated(change)
        judged("structure: %s is %s" % (purpose, "no problem" if needle is None else "refused"),
               (None if found == [] else "got %r" % found) if needle is None
               else None if any(needle in problem for problem in found) else "expected %r, got %r" % (needle, found))
    judged("structure: no calibration is no problem where nothing uses the capabilities index",
           first_wrong((contracts_problems({key: value for key, value in contract_document().items() if key != "fallback_index"}, problems_template) == [],
                        "a file that uses no index was refused")))

    # The run: the same archive gives the index, and the plain run reads nothing.
    with tempfile.TemporaryDirectory() as directory:
        run_document = eci_document()
        run, config, path, issue = contracts_runner(directory, run_document)
        online = ["--online", "--config", config, "--issue-body", issue, "--contracts", path]
        served = epoch_zip(epoch_members({}, None, EPOCH_ECI))
        status, out, body, asked = run(online, served)
        status_down, out_down, body_down, _ = run(online)
        section = body.split("## Contrats par routeur")[1].split("\n## ")[0]
        down = body_down.split("## Contrats par routeur")[1].split("\n## ")[0]
        judged("the online run reads the capabilities index in the archive it already reads, once, and orders the cascades on it",
               first_wrong((asked == [EPOCH_URL], "asked: %r" % asked),
                           ("Ordre des contrats : `echo` > `alpha` > `charlie` > `delta` > `india` > `juliet` > `foxtrot`." in section, "the order of pro: %s" % section[:300]),
                           ("read, 0 of the 5 benchmark file(s) and 5 model(s) of the capabilities index" in out, "the log: %s" % out),
                           ("Indice de capacités d'Epoch AI (ECI), lu le" in section, "the capabilities index is not said read")))
        judged("a run that cannot read the archive judges nothing on the capabilities index and says so, and nothing else of the run moves",
               first_wrong(("Plancher introuvable (Floor Model (Epoch, estimé) : indice de capacités non lu)" in down, "the floor: %s" % down[:600]),
                           (status == status_down and "Aucune dérive." in body and "Aucune dérive." in body_down, "the status moved"),
                           ("conforme (estimé)" not in down, "an estimate without the index")))
        refusing_calls = []

        def refusing(url, headers, limit=None):
            refusing_calls.append(url)
            raise AssertionError("the plain run reached the network: %s" % url)

        status_plain, out_plain, _, _ = run(["--config", config, "--contracts", path], opener=refusing)
        judged("the plain run stays offline with floors and mappings on the capabilities index: it reads the shape of the contracts and nothing else",
               first_wrong((status_plain == 0 and "holds a contract for each router" in out_plain, "the plain run: %s" % out_plain),
                           (refusing_calls == [], "the network was reached")))
    return failures


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
    failures += run_pricing_page_cases()
    failures += run_ranking_cases()
    failures += run_contract_cases()
    failures += run_epoch_cases()
    failures += run_eci_cases()
    failures += run_verify_cases()
    failures += run_safety_net_case()
    failures += run_online_apply_cases()
    failures += run_confirmation_cases()
    failures += run_lookup_cases()
    failures += run_review_cases()
    failures += run_keyset_cases()
    failures += run_jinja_net_cases()
    failures += run_hardening_cases()
    failures += run_command_line_cases()
    failures += run_proposal_cases()
    failures += run_proposal_command_line_cases()
    failures += run_real_list_cases()
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
    parser.add_argument("--proposals", metavar="DIR",
                        help="with --online, propose the NEW models in two pull requests rather than "
                             "in the issue, and write to DIR what the workflow keeps them with: "
                             "proposals.json, and for each pull request with something to propose its "
                             "body, its commit message and the file with the entries added")
    parser.add_argument("--issue-status", metavar="PATH",
                        help="with --online, write to PATH the status the issue is kept by: the exit "
                             "status, less the NEW models a pull request of --proposals carries")
    parser.add_argument("--config", metavar="PATH", default=str(CONFIG),
                        help="the LiteLLM configuration to read (default: %(default)s)")
    parser.add_argument("--contracts", metavar="PATH",
                        help="the router contracts to read, by default the repository's own when "
                             "--config is the repository's template, and none for another one")
    arguments = parser.parse_args(argv)

    if arguments.selftest:
        return run_selftest()
    if (arguments.issue_body or arguments.coverage or arguments.undeleted or arguments.proposals
            or arguments.issue_status) and not arguments.online:
        parser.error("--issue-body, --coverage, --undeleted, --proposals and --issue-status need --online")
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
        contracts_file = contracts_file_for(arguments)
        if contracts_file:
            problems = offline_contract_problems(text, contracts_file)
            if problems:
                print("\nRouter contracts: %d problem(s) in %s.\n" % (len(problems), contracts_file.name))
                for problem in problems:
                    print(problem + "\n")
                return 1
            for notice in offline_contract_notices(text, contracts_file):
                print(notice)
            print("Router contracts: %s holds a contract for each router, and its mappings are well formed."
                  % contracts_file.name)
        return 0

    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    result = run_online(text, environment, opener, today)
    contracts_file = contracts_file_for(arguments)
    # The archive of Epoch AI is read only where the contracts are, and after the ranking they stand on:
    # a run that has no section of contracts has no use for it.
    if contracts_file is not None and (result.get("rankings") or {}).get("status") == "read":
        result["epoch"] = read_epoch(opener, today)
    result["contracts"] = router_contracts(text, result, contracts_file)
    if arguments.apply and not result["unreadable"]:
        new_text = apply_to_result(text, result)
        if new_text != text:
            path.write_bytes(new_text.encode("utf-8"))
    if arguments.proposals:
        # Made on the file as main has it, whatever was deleted: the additions are pull requests of
        # their own, built on main.
        write_proposals(arguments.proposals, propose_additions(text, result, run_link()), today)
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
    if arguments.issue_status:
        Path(arguments.issue_status).write_text("%d\n" % issue_status(result), encoding="utf-8")
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
