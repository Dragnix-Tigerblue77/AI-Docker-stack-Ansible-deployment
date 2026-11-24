#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77 and the AI Docker stack Ansible deployment contributors
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
the report and pull requests it feeds, exist to see it; the deletion of what a provider has
retired, which nobody should have to do by hand, is its third mode.

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
"version" tests) makes this check exit 2 although Ansible renders the file. The job installs
PyYAML and Jinja2 alone, so the check cannot lean on ansible-core. The day the template needs such
a filter, add it to this check explicitly, as "check_compose_template.py" does for "to_json", keep
the pull-request and the job's environments identical, and install ansible-core in that job
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
  keys or of the configuration's switches (TEMPLATE_SWITCHES, rendered at their default), however the
  template reads it -- is a finding that names the problem, and ends the run with
  status 2 like a file that is not YAML. Only Jinja2's own filters and tests exist here (the
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
  (d) every "# drift-ignore:" line is well formed and gives its reason;
  (e) every active entry belongs to a provider whose catalogue this check reads, OmniRoute's virtual
      routes apart (see "HOW EACH PROVIDER IS READ"): a model of a provider nobody reads is one that
      nothing would ever report retired.

"--online" reads each provider's model catalogue as well, and reports the drift: it prints a
plain-text report and, with "--summary PATH", writes the whole report that
".github/workflows/LiteLLM_model_drift.yml" puts in the summary of its run. That text is in French,
since it is read on GitHub by the maintainers (CLAUDE.md, "Language"); the printed report is English,
like any run's output. "--unreadable PATH" writes one line "<provider> <class>" per catalogue that
could not be read, the class being that of the HTTP status ("4xx"...), "network" when nothing answered
or "answer" when the answer could not be read, and nothing else: an empty file when every catalogue
was read, no file when the model list itself could not be read. Those lines alone make the workflow
try again two hours later and, at the day's last attempt, open its issue; a missing key is not one of
them.
Exit status: 0 no drift, 1 drift, 2 a provider, or the file itself, could not be read (an error outranks
drift, since it means the report is incomplete), 70 a crash: the script's own bug, or an
answer it could not read at all, which prints the kind of error and where and never its message.
An uncaught exception would exit 1 and be read as drift, which is why a crash has a status of its
own. The offline rules are applied in this mode too: nothing blocks a human's merge here, so a red
pull request can still land on main, and the next run is the next place it shows.
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
was deleted; a file left at that path by an earlier run is removed first. It writes no catalogue: the
overview of what the gateway serves, "docs/CATALOG.md", is generated from the template by
"generate_catalog.py", which the workflow runs on the template this one edited and on each one it proposes,
so that the pull requests carry the catalogue in the same commit as the template.

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
"cloudflare/<id>" (whose id starts with "@cf/"), "zai/<id>", "nvidia_nim/<id>", and, as "openai/<id>" with
an "api_base" on the provider's host, SambaNova ("api.sambanova.ai"), Kilo Gateway ("ai-gateway.kilo.ai"),
OVHcloud AI Endpoints ("oai.endpoints.kepler.ai.cloud.ovh.net"), Requesty ("requesty.ai"), Cent AI
("api.cent-ai.dev") and Aion Labs ("api.aionlabs.ai"). Every provider the model list routes to has its catalogue read here, one that needs
a key included, and the offline run refuses an active entry of any other: OmniRoute's virtual routes
("openai/auto/..." on a local "api_base"), which no catalogue lists because the machine itself picks the
model, and the Auto router, which calls only other routers, are exempt, and the report says how many
there are. The names a "drift-ignore:" line takes are those of the table below, Cent AI's being "centai" and Aion
Labs' "aionlabs": the workflow's tables read a name as plain letters.

  provider    catalogue, and how its key is sent       what the provider's own filter keeps, for NEW
  openrouter  openrouter.ai/api/v1/models              ":free" and both prices "0"
              ?output_modalities=all -- no key
  cerebras    api.cerebras.ai/public/v1/models         not "deprecated"
              -- no key
  sambanova   api.sambanova.ai/v1/models -- no key     not "deprecated"
  gemini      generativelanguage.googleapis.com/       every model
              v1beta/models, paginated -- header
  groq        api.groq.com/openai/v1/models -- Bearer  "active" not false
  mistral     api.mistral.ai/v1/models -- Bearer       no "deprecation", no "ft:" (a fine-tune)
  deepseek    api.deepseek.com/models -- Bearer        every model
  cloudflare  api.cloudflare.com/client/v4/accounts/   not marked for removal
              {account}/ai/models/search, paginated
              -- Bearer
  kilo        ai-gateway.kilo.ai/api/v1/models         "isFree" true
              -- no key
  nvidia      integrate.api.nvidia.com/v1/models       every model
              -- no key
  ovhcloud    oai.endpoints.kepler.ai.cloud.ovh.net/   every model
              v1/models -- no key
  requesty    router.eu.requesty.ai/v1/models          "input_price" and "output_price" both 0
              -- no key
  zai         api.z.ai/api/paas/v4/models -- Bearer    every model listed, which omits the free ones
  centai      api.cent-ai.dev/v1/models -- Bearer      every model
  aionlabs    api.aionlabs.ai/v1/models -- no key      every model not retired ("expires_at")

No filter drops a model for what it is for: every provider and every kind of model is on the same
footing, so a new speech, transcription, embedding or image model is reported like a new chat one.
What a NEW finding says of its kind is its "usage", read from the catalogue where it says so and from
the id where it does not (USAGE_MARKERS: "tts", "whisper", "embed", "guard"...):

  openrouter, kilo  "output_modalities": text only -> the id decides; "image" among them -> image;
                    "audio" -> speech; "video" -> video; "embeddings" -> embeddings
  gemini            "embedContent" with no "generateContent" -> embeddings; the id decides otherwise,
                    and a model with neither of the two methods the id does not name is unclassified
  mistral           "completion_chat" true -> the id decides, a chat model if it names nothing;
                    false -> the id decides, unclassified if it names nothing
  cloudflare        the "task": "Automatic Speech Recognition" -> transcription, "Text-to-Speech" ->
                    speech, "Text Embeddings" -> embeddings, "Text-to-Image" -> image, "Text
                    Generation" -> the id decides, any other task its own name
  the others        the id decides, a chat model if it names nothing

Only a chat model goes on to what assumes one: the ranking (THE RANKINGS) and the entry to paste. A NEW
model of another usage is listed in the same sections as the rest, with its usage and the
"model_info.mode" its entry needs (USAGE_MODES), and the pull requests of additions write its entry like
any other (PROPOSING WHAT IS NEW): in the access group of its mode (USAGE_GROUPS, which
check_compose_template.py holds the template to), with a slot at the tail of the cascade of its router
where it has one. A text entry is written with no "model_info.max_input_tokens": the window is the model's
own, no catalogue read here gives it, and check_compose_template.py refuses a cascade member without one until
a person writes it, which the pull request says. Cloudflare's Clef and Clairic families are
read as "decision" and "extraction" by their id (CLOUDFLARE_FAMILY_USAGES), since their task is not
documented. Only a model of which the run cannot tell the kind (a usage it did not classify, a Cloudflare
task it does not know) has no mode to write, and is a report line with that reason. The filters narrow
NEW only. Whether a model is RETIRED is decided against everything the provider lists, so that no
filter can ever make a served model look retired -- which is also why OpenRouter is read with
"output_modalities=all", its default being "text" only.

A video generation model served through "generateContent" (Gemini's "omni" one is) is read as a chat
model, and is turned down with a "drift-ignore:" line. Gemini's model listing has no field that would
tell it apart (name, version, displayName, description, token limits, supportedGenerationMethods,
temperature, thinking), and "omni" is not a marker to add: other vendors' "omni" models are chat
models, one of them routed in the file this check reads.

Requesty lists every model it relays, nearly all of them paid, each with the "input_price" and the
"output_price" per token it states: only a model priced 0 in and out is offered as NEW, and an active entry
whose model is still listed but no longer priced 0 is a NOTICE and never RETIRED, as Kilo's is. A "retires"
timestamp is a NOTICE too, read as seconds since the epoch, which is what its values look like. NVIDIA,
OVHcloud, Z AI and Cent AI are read as plain lists of ids. OVHcloud states a price per token and says nothing
of the keyless access its entries are called through, so its NEW models are listed to examine and never
claimed free; NVIDIA, Z AI and Cent AI state nothing per model either.

Aion Labs' catalogue is public and lists its models with a price each: its free tier is the allowance of
the account and no model's own, so no model of it is ever read as free, and a NEW one is listed to examine and
proposed only in the pull request of models to verify. Its models are in an access group of their own
("Fiction", which ACCESS_GROUPS gives an entry written for it) and in one router of their own.

Kilo Gateway lists all of its models, paid ones included, and flags the free ones with "isFree" (and
whether it "mayTrainOnYourPrompts"). Its entries are the keyless ones, served without an account, so only
the free ids are offered as NEW. Every id is a member, though: a model that stops being free is still
listed, and is reported as a NOTICE and never as RETIRED, which is what a deletion would otherwise take
it for. The list is the only route: Kilo documents no way to ask for one model, so a deletion rests on
it alone, as OpenRouter's does. It also lists virtual models that pick another at each request
("kilo-auto/free", "openrouter/free"), which are free and no model to route to, and which the template
sets aside with a "drift-ignore:" line.

The keys are read from MODEL_DRIFT_GEMINI_API_KEY, MODEL_DRIFT_GROQ_API_KEY,
MODEL_DRIFT_MISTRAL_API_KEY, MODEL_DRIFT_DEEPSEEK_API_KEY, MODEL_DRIFT_ZAI_API_KEY,
MODEL_DRIFT_CENT_AI_API_KEY and MODEL_DRIFT_CLOUDFLARE_API_KEY, the last
with MODEL_DRIFT_CLOUDFLARE_ACCOUNT_ID beside it. An unset or empty one leaves its
provider "not covered (no key)", which the report says every time rather than skipping it, and says
which of the two Cloudflare lacks. Gemini's
goes in the "x-goog-api-key" header rather than the "?key=" parameter its examples use, so that no
URL this script builds, prints or reports ever carries a key.

Cloudflare Workers AI is the one catalogue whose address carries a second secret: the account's
identifier is in its path. It is read from MODEL_DRIFT_CLOUDFLARE_ACCOUNT_ID, held to 32 hexadecimal
characters before it goes into an address (a secret with anything else in it is that provider's error,
named by its variable and never by its value), put into the address at the last moment and replaced like a
key by "***" in every message, and the address kept in PROVIDERS, in the report and in the summary has the
placeholder "{account_id}" where it goes. What its answer holds is NOT documented: the API reference types
each model "unknown", so the shape is the one that the documentation's own model catalogue and Cloudflare's
command line tool read -- a "result" list, the model's "name" being the "@cf/..." id LiteLLM calls it by, its
"task" and a "properties" list -- and no run has read the live answer, which needs a token this repository's
sessions do not hold. Anything that shape does not have is skipped or is that provider's error, never a
retirement: a list that repeats a model across its pages, one that ends on a full page after as many
pages as MAX_PAGES allows, or one with no "result" list. The list is asked for with
"include_deprecated=true", which keeps a model whose date has passed for three months, so that it is
retired when it has left the list and is a NOTICE until then. A NOTICE is a model with a
"planned_deprecation_date" property, which is the date the model pages show, or a "deprecated" flag.
The API has no route that answers for one model by its id that this reads, so Cloudflare's models are
deleted from the list alone, as OpenRouter's are, under the same refusals (an empty list, more than half
the file's models missing).

The answers of Z AI and Cent AI are read as the OpenAI-style list ("data", each with an "id") their
documentation describes. Both answer 401 without a key and no session of this repository holds one: the drift
run, which holds the keys, is what reads them, and first did on 2026-11-24. A shape that is not that list is the provider's error, never a retirement.

Z AI's list omits its free "Flash" models although it serves them: a call to glm-4.7-flash on the account's
key was answered with an overload error (HTTP 429, code 1305), which a model the provider does not know is
not. Reading it as complete would delete a served model, so it is declared in INCOMPLETE_CATALOGUES, and the
list alone never makes an entry of it RETIRED or GONE. Z AI has no route that answers for one model, so the
run asks it with the cheapest call that proves a model exists: a chat completion of "max_tokens": 1 on the
key it holds, for each ACTIVE entry the list omits (probe_absences) -- but only once the pricing page below,
which costs no request of the quota, has not listed it free: a model that page names is served and is asked
about nowhere, so a normal day spends none, and the probe is the fallback for a model neither names or for
a page that could not be read that run. HTTP 200, and any 429 (the codes its
error page documents under 429 are limits, a balance and a plan, never an unknown model), say the model is
served: it is listed apart (SERVED), and is no finding. HTTP 400 with code 1211, "Unknown Model", the one
code that page documents for a model that does not exist, makes it RETIRED, deleted like any other. Every
other answer (an authentication code, a code about the call and not the model, a 5xx, a timeout, a code the
page does not list, a body that is not an error of its shape) settles nothing: the entry stays a NOTICE that
says what the probe answered. A commented-out entry is never asked about, since it is one not routed to for
its price and a call to it could cost, so its absence is a NOTICE. A list that holds nothing asks nothing.
Z AI's pricing page, which its documentation serves as Markdown, tables the models free of charge ("Free" in
both the Input and the Output column), and is read as a second source of NEW models the list omits too: they
are listed to examine, labelled as read there, like any NEW model of a provider whose API says nothing of the
free tier. A page that holds no such table is that provider's error and never a retirement. The page is public
and the key is not sent to it. Only a provider known to omit what it serves is declared.

Whether a Cloudflare model is free is not read, and no check for it is made up: the pricing page names, in
a note of prose, the models that need a paid billing method, and every other model draws on the
10,000 neurons a day of the whole account. The models' own records carry a "require_workers_paid" property
for the first, which says nothing of the others, so it is not read either. A NEW Cloudflare model is
therefore listed to examine, linked to the pricing page, and proposed only in the pull request of models to
verify.

WHAT IS REPORTED
----------------
RETIRED    an active entry whose id the catalogue no longer lists: delete it and its cascade slots.
GONE       a commented-out entry whose id the catalogue no longer lists: delete it too -- the rule
           keeps no commented-out corpse of a retired model.
           Neither is said on the list alone of a provider whose catalogue is known to omit models it serves
           (INCOMPLETE_CATALOGUES, Z AI's, which leaves out its free "Flash" models): there an active entry
           is asked about (see above) and is RETIRED only when the provider says the model does not exist,
           and a commented-out one is a NOTICE that says so.
NOTICE     an entry, active or commented out, that a source announces for retirement: the provider's own
           signal, which is OpenRouter's and Kilo's "expiration_date", Requesty's "retires", Aion Labs'
           "expires_at", Mistral's "deprecation" (with "deprecation_replacement_model"), the "deprecated"
           flag of Cerebras and SambaNova, Groq's "active": false, Cloudflare's "planned_deprecation_date",
           or the "deprecation_date" LiteLLM's public price map gives the model (see THE SECOND SOURCE OF
           ANNOUNCED RETIREMENTS), each notice saying which source said it; an active Kilo entry that is no longer flagged free, since
           its keyless call would be refused; an active Requesty entry that is no longer priced 0;
           and an entry, active or commented out, that a provider of INCOMPLETE_CATALOGUES does not list
           and that asking it could not settle (a commented-out one is not asked).
WARNING    two sources of an announced retirement contradict each other (see THE SECOND SOURCE OF ANNOUNCED
           RETIREMENTS): the earliest day is kept, and both sources and what each says are named. Not a
           finding of its own: it qualifies a NOTICE, and holds nothing back.
BACK       OpenRouter only: a commented-out id without ":free" whose ":free" twin is now free. A
           commented-out ":free" id is never BACK: it is free whenever it exists, so it cannot have
           been commented out for its price, and its being free again is no news -- that is the
           guardrail "nemotron-3.5-content-safety:free", commented out for being no generator.
NEW        an id the file does not know. Known ids are those of the active and the commented-out
           entries, and those a "# drift-ignore: <provider>/<id> -- <reason>" line names, which is
           how a model examined and turned down stops being reported without an entry of its own.
           <provider> is one of the names above: "sambanova/<id>" for SambaNova, "kilo/<id>" for
           Kilo Gateway, "ovhcloud/<id>", "requesty/<id>" and "centai/<id>", "aionlabs/<id>", and "nvidia/<id>" for
           the entries that read "nvidia_nim/<id>", where the entry itself reads "openai/<id>". A Mistral id is known when one
           of its "aliases" is. Each carries its usage (see above), shown on its line.

Free-tier eligibility is machine-readable on OpenRouter, as ":free" and a price of "0", on Kilo
Gateway, as "isFree", and on Requesty, as the two prices at 0. Every other provider publishes it only in prose, on a pricing page, so a NEW model there is listed as one
to examine, never claimed free, and the summary links the page of each provider listed there
(PRICING_PAGES, a table the selftest holds to the providers it can be needed for): the link is a
convenience, the free tier is still checked by a person.

A NEW id of a chat model that neither pull request of additions carries (see "PROPOSING WHAT IS NEW"
below), or every such id when the run proposes nothing, is listed in the summary, and in the body of the pull
request of the models to verify when there is one, with an entry to complete, ready to paste: the
"model:" with its
provider prefix, a model_name proposed the way the file's own names are made (the id with its dots
turned to dashes, and the provider's name as a suffix for the providers whose names carry one, a
name already taken getting it anyway), and the "litellm_credential_name" (the "api_key" of a keyless
gateway, which is a literal marker) and the "api_base" most of that provider's existing entries use.
A provider with no entry yet gets a placeholder for the credential. Pasted as it is, it is an active entry;
for one that is not routed to, a "# " goes in after the two spaces of indentation of each line, as
the file's other commented-out entries have it (a "# " in front of the indentation is a comment
this check does not read as an entry), and the reason goes above, with the provider's page and the
date, which only a person can write. The snippets are left out when they would take the text past
the size GitHub accepts.

THE SECOND SOURCE OF ANNOUNCED RETIREMENTS
------------------------------------------
Several providers announce nothing in their API (Google's lists no deprecation), so the providers' own
signals alone leave a model that is about to go unreported. LiteLLM's public price map, the
"model_prices_and_context_window.json" of its repository, gives some models a "deprecation_date", and it is
read as a double check of those signals: once per run, with no key, over a public address, and no model is
ever called. Each entry of the file, active or commented out, is looked up in it under the key LiteLLM holds
the model by, "<prefix>/<id>" (the prefix of its "model:" for the native providers, nvidia_nim for NVIDIA,
and the provider's own name for SambaNova and OVHcloud, which the file reaches as "openai/<id>"). Kilo Gateway,
Requesty, Cent AI and Aion Labs have no key in the map, and are skipped rather than looked up as "openai/<id>",
which would read the deprecation of OpenAI's own model of that name. Only a real day of the calendar is read
from it, and only that day is ever shown.

What the two sources say of an entry the provider still lists is combined:

  both silent                                   nothing
  one announces, the other is silent            a NOTICE saying which source said it; the map "silent" is a
  (or does not carry the model)                 model it carries with no date, or one it does not carry
  both announce the same day                    a NOTICE citing both
  the sources contradict: two different days,   the retirement is kept, on the earliest day, and a WARNING
  or the provider states in so many words       names both sources and what each says, in the summary and in
  that the model is active against a day of     the body of the pull request of the deletions
  the map

A provider "states the model is active" only where it says so with a flag: Groq's "active": true, and the
"deprecated": false of Cerebras, SambaNova and Cloudflare. A provider that merely lists a model with no
deprecation field says nothing, and so does a null date. A provider that flags a model with no day
("deprecated": true, "active": false) and a day of the map do not contradict: there is no day to differ. The
map has no way to state that a model is not deprecated, so the opposite contradiction cannot occur. A provider
whose catalogue could not be read leaves the map alone to speak, and the notice says the catalogue was not
read. A day that has passed while the provider still lists the model is a NOTICE like any other, which says
the date has passed: it deletes nothing, since a deletion rests on the provider's catalogue alone, and a model
its catalogue no longer lists is RETIRED whatever the map says of it.

A map that cannot be read (a failed request, an answer that is no JSON object, one in which no entry names a
"litellm_provider") is the error of that source: the summary and the pull request of the deletions say so, and
it changes neither the exit status, nor what is deleted, nor the coverage, nor the retries and the issue, which
are the providers' catalogues' alone. What the providers announce is reported all the same.

DELETING WHAT A PROVIDER HAS RETIRED
------------------------------------
RETIRED and GONE are the one kind of finding that needs no judgment: the provider's own catalogue
no longer lists the id, so the model cannot be called, and CLAUDE.md says what becomes of such a
model.

A list can omit a model that is still served, so on the providers whose API answers for one model
by its id (LOOKUPS: Gemini, Groq, Mistral) a finding is acted on only once the provider has been
asked for the model itself. One it still serves leaves the findings and is listed apart (SERVED in
the report, a section of the summary). One it answers 404 for is deleted. Any other answer leaves the
finding to a person, with that answer in the report, and so does a route that cannot be believed:
it has to answer 200 first for a model the list does name, of the same shape (with a slash in its
id or without, since a slash may not be routed like a plain id). The references document the route
and not the status of an unknown id, which is why nothing is deleted on any answer but a 404. The
other providers, whose API has no such route, are deleted from on their list alone, as before --
bar those of INCOMPLETE_CATALOGUES, whose list is known to omit models that are served: an active
entry is deleted only when asking the provider says the model does not exist, as above.

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

What it refuses to delete, leaving the finding in the summary and in the body of the deletion pull
request with the reason, and writing nothing
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
  request of a hundred lines rewritten at every run on its word is not worth the risk. The summary
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
Where a NEW chat model would go in a cascade is a question of figures, which someone used to look up by
hand: the pull requests of additions now carry them, and the summary for a NEW model neither carries.
With MODEL_DRIFT_ARTIFICIAL_ANALYSIS_API_KEY set, the run reads
Artificial Analysis's free API (GET https://artificialanalysis.ai/api/v2/language/models/free, the key
in the "x-api-key" header, 100 requests per 24 hours, one made per page of the answer and at most
MAX_PAGES per run) and the summary gains a table of each
NEW chat model's intelligence index, coding index, output speed and blended price, then a suggested place
per router: before the first member of that router's cascade the ranking scores lower on the figure
that decides it (intelligence for "pro", "flash" and "claude-code", coding for "code", speed for
"flash-lite"), or after the last one. The source is named in the summary with its day, as the terms of
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

THE FIGURES THE CATALOGUE SHOWS
-------------------------------
"--scores PATH" is the figures file "docs/catalog_scores.json": the intelligence index and the time to the first answer
token of the Artificial Analysis record each entry is mapped to by the router contracts, at the level it is called at
(never a record whose level is unverified), and the capabilities index and the code position of its model in Epoch AI's
archive, which this run already reads. The file the path names is read first, as the figures of the run before; a source
this run did not read (no key, an error, none asked) keeps what that file held of it, with its day, and one it read
replaces it, a figure it no longer gives being dropped. The file is rewritten in place when "--apply" deleted something,
so that the entries that went take their figures with them, and for each pull request of additions "<kind>_scores.json"
is written beside its template, for the entries of that template. Nothing is written otherwise, so a run that changes
nothing leaves the file alone. The file is held to its shape by "scores_problems" and written the one way
"render_scores" writes it, which "generate_catalog.py --check" requires of every copy: it is data, numbers within
bounds for entries of the template, and nothing a reader of those sites could write into it is more than a wrong figure.

PROPOSING WHAT IS NEW
--------------------
"--proposals DIR" proposes the NEW models, whatever their kind, in two pull requests of their own, which the
workflow keeps and which only a person merges. They are split by how much the run knows of each model,
never by its provider. A model of a usage other than chat is written with its "model_info.mode" and the
access group of that mode, after the provider's last entry of the same mode (its last entry of no mode when
it has none).

An active entry whose mode has a router is also given a slot, because an entry that has a router and is in
none of its cascades is one the template's own checks refuse. The slot is the safe place, the TAIL of the
cascade, written under the provider's key condition ("{% if has.Groq %}") unless the router has that provider
alone, so that the cascade holds no name the rendering does not have; the person who reviews moves it. A text
model goes to the tail of Auto-Flash-Lite (the router that takes every model that answers, held to no floor),
Aion Labs' to Auto-Fiction. A slot never changes the "head" table: a tail is never the first member, and it is
verified for the key sets that matter (slot_keysets_problem). A model whose router does not route to its
provider (a Groq speech model, since only Gemini has a key that serves Auto-TTS) cannot be given the slot the
template needs, so it is a report line with that reason, its entry being written by hand along with the "head"
row. A commented-out entry has no slot.

  * embeddings: addressed by its own name alone, the way the template's embedding entries are, so with no slot.
    Cloudflare's are written through its OpenAI-compatible endpoint, with the "api_base" read from the
    environment, modelled on the entry that already has it;
  * speech, transcription, decision, extraction: written with their mode and group, and a slot at the tail of
    Auto-TTS, Auto-STT, Auto-Decision or Auto-Extraction;
  * image, video, rerank, moderation, ocr: the kinds of model the gateway has no router, no client and no key
    group for. They are written with LiteLLM's mode for them and a group named for the kind, with no slot, and
    the pull request of the models to verify says the gateway has nothing for that kind yet, so that the person
    keeps it or turns it down by a "drift-ignore" line;
  * audio, agent, music: models LiteLLM serves through its chat route, written as chat entries with the same
    remark;
  * a model of which the kind is not known has no mode to write, and stays a report line.

A model of a usage other than chat has no ranking to be matched to. It is ready when its provider's API
states its free tier and the file already serves the usage through that provider (route_known: an entry of
the mode, active or commented out), which shows LiteLLM has the route under that prefix; any other is to
verify, whose body says which of the two is missing.

* "ready", ready for review: a model of which the run holds every fact an addition needs -- its free
  tier, stated by its provider's own API (FREE_CATALOGUES: OpenRouter's ":free", both prices
  "0", Kilo's "isFree", and Requesty's two prices at 0), and a figure of the
  ranking matched for certain (certain_match: the last segment of the id, less ":free", and the
  slug or the name of one entry of the whole ranking and of no other are equal once lower-cased
  with everything but letters and digits removed, and that entry's name carries no variant marker
  such as "(Reasoning)"). A provider whose free tier becomes machine-readable is added to
  FREE_CATALOGUES, and nothing else changes;
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
last commented-out one -- whose key and base it copies (a keyless gateway's, KEYLESS_GATEWAYS, copies
its literal marker and writes the "extra_headers" that blank the Authorization header, which the
gateway answers 401 to otherwise), and written right after it (after the comment
block, for a commented-out one, so that a run and its reason stay together), under a comment of a
fixed text that says where it comes from and when; it is commented out, with a "not routed" reason
to replace, when the provider has no active entry. Neither pull request puts a model anywhere but at the
tail of a cascade (above): the body gives its figures and its suggested place in each router (THE RANKINGS), which are
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
whose ids all end in a suffix (FREE_SUFFIX: OpenRouter's ":free") that does not, an id already an
entry or set aside, an entry to model one on that does not read its key through a credential (or, on a
keyless gateway, whose key is no plain marker) or whose base is not https, more than PROPOSAL_LIMIT entries. It
also refuses, alone, an entry whose credential the file does not declare: the command of the body reads the
variable behind it, which only this script needs. A NEW
model this cannot propose -- of a spelling the file is not written with, of a provider with no entry,
past the cap, or one whose body would be too long -- is listed, with the reason and its entry to
complete, in the body of the pull request of the models to verify, and in the summary.

What no entry is made of rides on the body of the pull request it concerns (carried_sections), which
notifies the people it is assigned to: a commented-out model free again on OpenRouter on the ready one
(on the one to verify when no ready one is opened), the NEW models no pull request proposes on the
one to verify, and an announced retirement (NOTICE) on the deletion pull request, under a heading that
does not hold its merge. A section that would take a body past the size GitHub accepts loses its
entries, then itself. Whatever has no pull request to ride on that run is in the summary only.

THE ROUTER CONTRACTS
--------------------
".github/LiteLLM_router_contracts.yaml" says what each router is held to: a floor, written as an
ANCHOR, "at least as good as that model", whose figure is read at every run and never copied into the
file, on one of two scales -- the intelligence index (on the version the file names), from the Artificial
Analysis ranking for an entry of the template or from Epoch AI's capabilities index for a model that
index names, or, for "code", the code position described below -- or NO floor, for a router that takes
every model that answers. A floor on the index may carry a "margin", in points of the index and 0 where it
is omitted: a member conforms while its figure is no more than the margin under the floor, and the report
says the margin wherever it says the floor. The file also gives the exchange rate an extra reasoning level
must reach to be worth climbing to (points of index per extra second to the first answer token), how its
members are ordered, the members exempt from the floor on purpose (the last resort), and, for each entry
of the template, the Artificial Analysis record that describes it at the reasoning level the entry is
called at, with the page that gives that level, or "unknown". There is NO time budget: the goal is to use
as many free models as possible, so a slow model is never ineligible. A member is eligible for a router if
it reaches the floor (and, for "claude-code", takes tool calls), and time only orders: "flash-lite" puts the
shortest mean time to the first answer token first, and the other routers put the best quality first, the
time deciding between members whose quality is less than the router's "tie_margin_points" apart.

The unit of routing is model plus level: Artificial Analysis has one record per level, told apart by the
suffix of its name. The level a router keeps for a model is found by walking up the levels that have an
index from the lowest, and climbing to the next only while each extra second of the time to the first
answer token buys at least "min_points_per_second" points of index (a router that values time asks more
points per second; a step that is no slower is taken when it buys points, a step that buys none or whose
time is unknown is not taken). "claude-code" derives from "code": it is ranked as
"code" is, and its cascade is the cascade of "code" without the members that cannot take tools, which the
report checks and whose differences it lists. The file carries a "status", provisional until the
maintainer validates it and validated after, which the summary says.

The capabilities index (ECI) of Epoch AI is read from the same archive as the code positions (the member
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
was not read, an anchor on it cannot be read, nothing is judged against it and the summary says so, as for an
entry that cannot be read; a name the index no longer holds is listed as stale, and is information.

"code" is ranked on its CODE POSITION, read from Epoch AI's benchmark data (benchmark_data.zip, free, no
key, CC BY 4.0, to be cited with the day it was read) by the online run that has the contracts, after the
ranking the contracts stand on. Five of its files are read and no other (DeepSWE, SWE-bench Verified,
CursorBench, Terminal-Bench, ALE-Bench: WebDev Arena and any design or interface arena measure design, and
are never opened): the archive is held in memory, its members are found by their exact names, each is cut
at a size, a row that is not a model version with a finite score is left out and counted, and a model
version listed several times keeps its best score. In a file, the position of a score is one more than the
number of model versions of the file whose score is strictly greater, over the number of model versions of
the file, as a percentage: a smaller figure is better, and every version of the file counts, effort
variants included. The position of a member in a file is that of the best score among the versions its
entry lists for that file, and its code position is the median of its positions over the files where it
has one, two at least: with fewer it has none, which is not the same as a bad one. A position belongs to
the member alone and depends on no cascade, so "claude-code", which derives from "code", is ranked as
"code" is. A floor on this scale is an anchor "code_epoch" naming, per file (two at least), the versions
that stand for a model, with the "name" the report shows; its position is computed exactly as a member's,
and a member conforms while its position is no more than the floor's plus the margin, which "code" has
none of.

A member with no code position of its own (no version listed, none found, or found in one file only) but
with an effective intelligence (the ranking's index, or the estimate from the capabilities index) is
placed on an ESTIMATED position: the file's "code_fallback" gives points [index, position], the index
going up and the position never, joined by straight segments and kept at the first and the last position
beyond them, since the calibration holds no model there. Such a position is said "estimé" wherever it is
shown, is judged against the floor like any other, and has no time of its own, as no estimate has. A
member with neither stays where it is, flagged unrankable. The router puts the members that have a
position first, the smallest first, the shorter time deciding between two members whose positions are
less than the router's "tie_margin_points" apart (an estimated member has no time and goes last among
them); the last resort and the members past the floor go to the tail as for every other router. A read
that fails, whatever the reason (the network, a size, the shape of the archive, no usable row), is
reported as "not read" in that section and changes nothing else: the floor of "code" is not found and
judges nobody, and the intelligence index orders the cascade, as it did before any of this. The status
the summary shows is what the run read, never what the file declares. The plain run reads no archive.

It is a report and nothing else. The summary gains a section "Contrats par routeur" (and no other
text carries it) with, per router, a table of its members (record, level called, intelligence, time,
speed, the level the router would keep, the verdict), the order the contract would give against the
current one, the outcome of each floor the contract proposes to compare, and for a derived router how its
cascade differs from the one it must be; then the entries without a mapping, those with no record, the
names the file keeps that the template no longer has, the mappings whose slug the ranking no longer has
("stale") and those called at a level the ranking does not cover. A verdict is "conforme", "sous le
plancher" (the member goes to the last resort tier, it is not removed), "inclassable" (no index, or, for a
router ranked on code, no code position, or, for a router ordered by time, no time), or "variante non
vérifiée" (the level is unknown and the family has several, or the ranking has the family at other levels
only). No member is removed from a cascade by it,
whatever its verdict: a member with no index stays where it is, flagged, until the fallback is read. It is
computed from the ranking the run already read, by the job that holds the key, from the template as it
stood before any deletion; it changes no cascade, no entry and no row of the "head" table, never changes
the exit status, never blocks the deletion pull request, and says only the kind of error when its
computation fails.

The plain offline run reads the file too, and fails on its structure alone: a router that does not exist
or has no contract, a number that is not a number, a value with no reason, a mapping with fields that are
wrong (no tools declaration, say), a floor anchor that is not well formed or a floor on two scales, a
conversion of the index into a code position that does not go the way it should, a file that cannot be
read, a key written twice. It reads it only
against the repository's template (or the file given by "--contracts"), since a contract written for one
template means nothing against another. A name the file keeps that is no entry of the template any more,
in a mapping or in a last resort, is NOT a failure: the deletion pull request is merged by a gate
that wants CI green, and a deletion leaves exactly that behind. The plain run prints one notice line for
each such stale row and exits 0, and the summary lists them under "Correspondances sans entrée", for a
person to remove from the file.

UNTRUSTED TEXT
--------------
What a catalogue says -- an id, a name, a date -- ends up in the log, in a summary, in a pull request
and in a snippet someone pastes, and is read as untrusted. An id is offered as NEW only when it is
spelt the way ids are (letters, digits and "._:/+~-", with the "@cf/" Cloudflare puts in front of its
own as the one "@" allowed, no "::", no "//", so that no address and no workflow command can be one);
any other piece of an answer that is shown is cut to plain words, in which no newline, backtick, "@"
(bar that "@cf/"), angle bracket, square bracket or "::" survives, and is shown in a code span. The
catalogue's members are never filtered, since an id is retired by not being among
ALL of them. No key and no response body is ever printed: a failed read says its HTTP status and
nothing else (the reason phrase can carry a key as the body can, and HTTP/2 has none), whatever
else of an error is shown has every key of the run replaced by "***", and the summary shows it in a
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
  a path for (the summary, the catalogues it could not read, the pull request, the commit message,
  the coverage, the count of what it did not delete, the proposals). The workflow that runs it does
  the rest, the issue included, whose text it writes itself.
* It calls no model, bar the one-token probe of a provider of INCOMPLETE_CATALOGUES for an active entry
  its list omits. A listed model can still refuse a given key -- Google restricts
  Gemini 2.5 to accounts that used it before -- and only LiteLLM's own health check on the node
  would see that.
* It does not read OpenRouter's "/api/v1/models/<id>/endpoints". A removed slug answers there with
  200 and "endpoints": [] -- and so does "openrouter/free", the free router "flash" falls back on,
  measured 2026-09-27. The route cannot tell the two apart; the catalogue can.
* It does not report a commented-out entry's deprecation: nothing routes to it. Once it is
  actually retired, it comes back as GONE.
* It does not cover what a key cannot see. A keyed provider's catalogue is the one of the account
  behind the key, so a model reserved to another tier or region is invisible to it.
* It does not read the rate limits, the prices outside OpenRouter, or whether a provider still
  offers a free tier at all -- those live in prose only.
* It does not decide where a model goes. The rankings give a number and a suggested place; the order
  of a cascade stays a choice made by a person, with the router's other constraints in mind.

Its verification cases are Python literals rather than fixture files, for the reason CLAUDE.md
gives: a fixture on disk is reachable by "ansible-lint --fix", which has rewritten one here before.
They live in "check_LiteLLM_model_drift_selftest.py", beside this script, which "--selftest" runs
and which can be run directly. The online cases are fed canned catalogues, so the selftest needs no
network and no key.

Run it from the repository root:

    python3 .github/scripts/check_LiteLLM_model_drift.py --selftest
    python3 .github/scripts/check_LiteLLM_model_drift_selftest.py
    python3 .github/scripts/check_LiteLLM_model_drift.py
    python3 .github/scripts/check_LiteLLM_model_drift.py --online --summary /tmp/summary.md

and, on a checkout you can throw away, what the workflow runs:

    python3 .github/scripts/check_LiteLLM_model_drift.py --online --apply --summary /tmp/summary.md \\
        --unreadable /tmp/unreadable.txt --pr-body /tmp/pull_request.md \\
        --commit-message /tmp/commit.txt --coverage /tmp/coverage.txt \\
        --undeleted /tmp/undeleted.txt --proposals /tmp/proposals
"""

import argparse
import collections
import copy
import csv
import datetime
import functools
import http.client
import io
import itertools
import json
import os
import re
import statistics
import sys
import textwrap
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
# variable is a non-empty string, and the template reads nothing else but the switches below.
PROVIDER_KEY_VARIABLES = tuple(
    "Artificial_Intelligence_LiteLLM_%s_API_key" % provider
    for provider in ("Gemini", "Mistral", "Groq", "OpenRouter", "DeepSeek", "Cloudflare", "Zai", "Requesty", "NVIDIA",
                     "Cent_AI", "Aion_Labs")
)
# What the template reads besides the keys: switches of the configuration itself, which have no say in its model
# list. They are given here at their default, which is the state every deployment starts in, so that reading one is
# no finding; any other name is still one, since an unknown name would be "not given" without a word.
TEMPLATE_SWITCHES = {"Artificial_Intelligence_LiteLLM_disable_env_credential_login": False}
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

# Substrings of an id that name a use other than chat, each with that use. The first that an id holds
# decides, so a marker precedes the more general one it contains ("transcribe" before "voxtral"). They
# name a NEW model's usage only, and never touch RETIRED.
USAGE_MARKERS = (
    ("whisper", "transcription"), ("transcribe", "transcription"),
    ("tts", "speech"), ("speech", "speech"), ("orpheus", "speech"), ("playai", "speech"),
    ("embed", "embeddings"), ("rerank", "rerank"),
    ("imagen", "image"), ("banana", "image"), ("image", "image"),
    ("veo", "video"), ("lyria", "music"),
    ("guard", "moderation"), ("moderation", "moderation"),
    ("ocr", "ocr"),
    ("audio", "audio"), ("voxtral", "audio"),
    ("antigravity", "agent"), ("computer-use", "agent"), ("deep-research", "agent"),
    ("robotics", "agent"),
)
CHAT = "chat"
UNCLASSIFIED = "unclassified"
# The "model_info.mode" an entry of a usage needs where the file has one: an entry of no mode is a text
# model, and each of these modes has an access group of its own (check_compose_template.py holds the groups
# to its own table, and the selftest holds the two tables to each other). The first five are served by a
# router or a client of the gateway; the rest are the modes LiteLLM has for kinds of model the gateway has no
# router, no client and no key for yet, which an addition still writes so that a person keeps it or turns
# it down.
USAGE_MODES = {"transcription": "audio_transcription", "speech": "audio_speech", "embeddings": "embedding",
               "decision": "evaluation", "extraction": "extraction",
               "image": "image_generation", "video": "video_generation", "rerank": "rerank",
               "moderation": "moderation", "ocr": "ocr"}
USAGE_GROUPS = {"transcription": "STT", "speech": "TTS", "embeddings": "Embeddings",
                "decision": "Decisions", "extraction": "Extraction",
                "image": "Images", "video": "Videos", "rerank": "Rerank",
                "moderation": "Moderation", "ocr": "OCR"}
# The usages the gateway has a router or a client for. Any other typed usage is one it has none for: its entry
# says so in the pull request, and nothing routes to it.
SERVED_USAGES = {"transcription", "speech", "embeddings", "decision", "extraction"}
# Usages LiteLLM serves through its chat route although the model does more than text (a voice in and out, an
# agent that browses or uses a computer, a music model reached by "generateContent"): written like a chat entry,
# in the group of the text models, and said in the pull request to be of a kind the gateway has no client for.
CHAT_LIKE_USAGES = {"audio", "agent", "music"}
KEPT_APART_PROVIDERS = {"aionlabs"}


def servable(provider, usage):
    """Whether the additions pull requests write an entry for a NEW model of this usage: chat, a usage with a
    mode and a group, and the chat-like ones. Only a model whose kind the run could not tell (a usage it did
    not classify, or a Cloudflare task it does not know) has no entry to write, since it has no mode."""
    return usage == CHAT or usage in USAGE_MODES or usage in CHAT_LIKE_USAGES


def entry_usage(usage):
    """The usage an item carries: a chat-like one is written as chat, and an item says nothing of it."""
    return CHAT if usage in CHAT_LIKE_USAGES else usage


# Cloudflare names the task of most of its models, but the decision and extraction ones (Clef and Clairic
# families) are told by their id, which is what the template's entries are written for.
CLOUDFLARE_FAMILY_USAGES = (("@cf/cloudflare/clef", "decision"), ("@cf/cloudflare/clairic", "extraction"))

# The title of the section of the pull request body that lists what a person has to read.
# "dependabot-auto-merge.yml" lets the pull request merge itself only when the body has no section
# of this title, and "check_auto_merge_gate.py" holds the two to the same text.
REVIEW_HEADING = "## À relire"

# The exit status of a crash: 0, 1 and 2 mean something, and the status of an uncaught exception
# (1) would be read as drift.
CRASH_STATUS = 70

TIMEOUT = 30
MAX_PAGES = 20
MAX_LISTED = 150  # per section of a body, which GitHub caps at 65536 characters
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
    # Ansible's own environment is a sandbox, and the drift run holds the providers' keys.
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
    unknown = sorted(read - assigned - set(PROVIDER_KEY_VARIABLES) - set(TEMPLATE_SWITCHES))
    if unknown:
        raise RenderError("the file reads %s, which is none of the provider keys and no switch of the "
                          "configuration" % ", ".join(unknown))
    context = {variable: "placeholder" if given is None or variable in given else ""
               for variable in PROVIDER_KEY_VARIABLES}
    context.update(TEMPLATE_SWITCHES)
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


# The "model:" prefix LiteLLM routes each provider it has a provider for by, where it is not the name this check
# gives the provider.
LITELLM_PREFIXES = {"nvidia": "nvidia_nim"}
NATIVE_PROVIDERS = ("gemini", "groq", "mistral", "deepseek", "cerebras", "openrouter", "cloudflare", "nvidia", "zai")
# The providers LiteLLM has no provider of its own for, reached as "openai/<id>" on the host their "api_base" names.
OPENAI_HOSTS = {"sambanova": "api.sambanova.ai", "kilo": "ai-gateway.kilo.ai",
                "ovhcloud": "oai.endpoints.kepler.ai.cloud.ovh.net", "requesty": "requesty.ai",
                "centai": "api.cent-ai.dev", "aionlabs": "api.aionlabs.ai"}
# The one provider whose entries no catalogue backs: OmniRoute is a local gateway that picks among the models the
# machine itself holds, so its virtual "auto/..." routes are listed nowhere upstream and no reader could cover them.
# An "api_base" read whole from the environment, because the address holds the account's identifier: LiteLLM's
# "cloudflare/" provider has no embedding route, so Cloudflare's embedding entries are "openai/<id>" on it.
OPENAI_ENV_BASES = {"os.environ/CLOUDFLARE_EMBEDDINGS_API_BASE": "cloudflare"}
OMNIROUTE_BASE = re.compile(r"https?://omniroute[:/]")


def attribute(model, api_base):
    """(provider, id) for a LiteLLM "model:" value, or None when no catalogue here covers it."""
    if not isinstance(model, str) or "/" not in model:
        return None
    prefix, identifier = model.split("/", 1)
    for provider in NATIVE_PROVIDERS:
        if prefix == LITELLM_PREFIXES.get(provider, provider):
            return provider, identifier
    if prefix == "openai" and api_base in OPENAI_ENV_BASES:
        return OPENAI_ENV_BASES[api_base], identifier
    if prefix == "openai" and isinstance(api_base, str):
        for provider, host in OPENAI_HOSTS.items():
            if host in api_base:
                return provider, identifier
    return None


# The model of the entry that picks a router by the complexity of a request: it calls no provider and is no model of
# any catalogue, so nothing is attributed to it, mapped for it or read about it.
COMPLEXITY_ROUTER_MODEL = "auto_router/complexity_router"


def entry_of(item):
    parameters = item.get("litellm_params") if isinstance(item, dict) else None
    parameters = parameters if isinstance(parameters, dict) else {}
    return {
        "name": item.get("model_name") if isinstance(item, dict) else None,
        "model": parameters.get("model"),
        "api_base": parameters.get("api_base"),
        "api_key": parameters.get("api_key"),
        "credential": parameters.get("litellm_credential_name"),
        "item": item,
    }


# The name each router is published under, which is the key of its cascade and of its alias in the template. The
# contracts, the "head" table, the document of the routes and everything below call a router by its short id, so
# the one place a cascade's key is read, "fallback_lists", gives it by that id: a name that is no router's is
# left alone.
ROUTER_PUBLIC_NAMES = {
    "pro": "Auto-Pro",
    "flash": "Auto-Flash",
    "flash-lite": "Auto-Flash-Lite",
    "code": "Auto-Code",
    "claude-code": "Auto-Claude-Code",
    "stt": "Auto-STT",
    "tts": "Auto-TTS",
    "decision": "Auto-Decision",
    "extraction": "Auto-Extraction",
    "fiction": "Auto-Fiction",
}
ROUTER_OF_PUBLIC_NAME = {public: router for router, public in ROUTER_PUBLIC_NAMES.items()}


def router_id(name):
    """The short id of the router published under "name", or "name" when none is."""
    return ROUTER_OF_PUBLIC_NAME.get(name, name)


def fallback_lists(document):
    """{(section.key, source): [targets]} of every fallback list of a parsed file, "source" being
    None for "default_fallbacks" and a router's short id for a router. A cascade with nothing under it is
    an empty list."""
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
                    found[(where, router_id(source))] = [name for name in (
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


def provider_name(variable):
    """The provider a key variable is for: "Artificial_Intelligence_LiteLLM_<Provider>_API_key", a name that
    may hold underscores ("Cent_AI"), which a count of them from the end would cut."""
    return variable[len("Artificial_Intelligence_LiteLLM_"):-len("_API_key")]


def given_text(given):
    """The providers of a set of key variables, for a message."""
    names = [provider_name(variable) for variable in given]
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

    # (e) Every active entry belongs to a provider whose catalogue is read: an entry of any other is never
    # retired nor reported, whatever its provider does.
    for entry in active:
        if (attribute(entry["model"], entry["api_base"]) is None
                and not OMNIROUTE_BASE.match(str(entry["api_base"]))
                and entry["model"] != COMPLEXITY_ROUTER_MODEL):
            problems.append(
                'the active entry "%s" (model: %s) belongs to no provider whose catalogue this check reads.\n'
                "    Every provider the list routes to has its catalogue read, one that needs a key included,\n"
                "    so that a model it retires is deleted and one it announces is reported: add its reader to\n"
                "    PROVIDERS and the tables that name the providers (OmniRoute's virtual routes and the Auto\n"
                "    router, which no catalogue lists, are exempt)." % (entry["name"], entry["model"]))

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


def urllib_opener(url, headers, limit=None, data=None):
    """The answer's body, or with a "limit" at most one byte more than it, which says it is too big
    without having held all of it. "data" makes the request a POST of that body."""
    request = urllib.request.Request(url, headers=headers, data=data)
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
        # Cut after the secrets are replaced (shown_error), not before: a cut through the middle of one
        # leaves the half that no replacement can find.
        raise FetchError("network error: %s" % safe_text(error.reason, ERROR_READ)) from None
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


ERROR_READ = 400
ERROR_SHOWN = 95  # the "network error: " and the 80 characters of a reason that a message always had


def shown_error(error, environment):
    """What a failed read says, with every secret replaced and then cut to a line."""
    return scrub(str(error), environment)[:ERROR_SHOWN]


def scrub(text, environment):
    """"text" with every key of the run replaced by "***". No message here is meant to carry one,
    and this is what stands between a surprise and the log, the summary and the pull request."""
    for variable in ([provider[2] for provider in PROVIDERS if provider[2]] + [RANKING_KEY]
                     + list(ACCOUNT_VARIABLES.values())):
        key = (environment.get(variable) or "").strip()
        if key:
            text = text.replace(key, "***")
    return text


def is_zero(price):
    try:
        return float(price) == 0
    except (TypeError, ValueError, OverflowError):
        return False


def usage_of_id(identifier, default=CHAT):
    """What an id says it is for, or "default" when it names no use but its own."""
    lowered = identifier.lower()
    return next((usage for marker, usage in USAGE_MARKERS if marker in lowered), default)


def listed(payload, key="data"):
    items = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise FetchError('the answer holds no "%s" list' % key)
    return [item for item in items if isinstance(item, dict) and isinstance(item.get("id"), str)]


# Everything a provider's answer says is untrusted text, and ends up in a run's log, a summary, a pull
# request and a YAML snippet someone pastes. An id is therefore offered as NEW only when it is spelt
# the way ids are (SAFE_ID), and every other piece of the answer that is shown -- a name, a date, a
# replacement, a reason phrase -- is cut down to plain words by safe_text(): no newline, no
# backtick, no "@" (bar the "@cf/" that opens a Cloudflare id, as a whole text or after a slash), no
# angle bracket, so that it can neither start a workflow command at the head
# of a log line, nor mention somebody, nor close a code span and write markup of its own. The
# catalogue's "members" are never filtered: an id is retired by not being among ALL of them.
SAFE_ID = re.compile(r"(?!.*(?:::|//))[A-Za-z0-9~][A-Za-z0-9._:/+~-]{0,199}")
# A model id is spelt like that, or with the "@cf/" Cloudflare puts in front of every one of its own: the one
# "@" a catalogue's id may carry, and nowhere else in it, so that no mention can be one.
SAFE_MODEL_ID = re.compile(r"(?!.*(?:::|//))(?:@cf/)?[A-Za-z0-9~][A-Za-z0-9._:/+~-]{0,199}")
UNSAFE_TEXT = re.compile(r"(?!(?<![^/])@cf/)[^\w .,:;+()/'-]")


def safe_text(value, limit=80):
    text = " ".join(str(value).split())
    # No two colons side by side either: "::" is how a workflow command starts.
    return re.sub(r":(?=:)", ": ", UNSAFE_TEXT.sub("?", text))[:limit]


def new_catalogue():
    return {"members": set(), "candidates": {}, "usages": {}, "notices": {}, "aliases": {}, "unsafe": 0,
            "not_deprecated": set()}


def offer(catalogue, identifier, label="", usage=CHAT):
    """Put "identifier" up as a NEW candidate for the "usage" its catalogue or its id gives it, unless
    it is not spelt like an id."""
    if SAFE_MODEL_ID.fullmatch(identifier):
        catalogue["candidates"][identifier] = safe_text(label)
        catalogue["usages"][identifier] = safe_text(usage, 40)
    else:
        catalogue["unsafe"] += 1


# What a model that is not text-only is, by an output modality it lists: the first of these it holds.
MODALITY_USAGES = (("image", "image"), ("audio", "speech"), ("video", "video"), ("embeddings", "embeddings"))


def modalities_usage(model, identifier):
    """The usage of an OpenRouter or Kilo model: by its output modalities when they are no text alone,
    by its id when they are, and unclassified when it lists none."""
    architecture = model.get("architecture")
    modalities = architecture.get("output_modalities") if isinstance(architecture, dict) else None
    if not isinstance(modalities, list) or not modalities:
        return usage_of_id(identifier, UNCLASSIFIED)
    if modalities == ["text"]:
        return usage_of_id(identifier)
    return next((usage for modality, usage in MODALITY_USAGES if modality in modalities),
                usage_of_id(identifier, UNCLASSIFIED))


def read_openrouter(pages):
    catalogue = new_catalogue()
    for model in listed(pages[0]):
        identifier = model["id"]
        catalogue["members"].add(identifier)
        if model.get("expiration_date"):
            catalogue["notices"][identifier] = {"what": "expiration",
                                                "date": safe_text(model["expiration_date"])}
        pricing = model.get("pricing") if isinstance(model.get("pricing"), dict) else {}
        if (identifier.endswith(":free")
                and is_zero(pricing.get("prompt")) and is_zero(pricing.get("completion"))):
            offer(catalogue, identifier, model.get("name") or "", modalities_usage(model, identifier))
    return catalogue


def read_kilo(pages):
    """Kilo Gateway: every model it lists, paid ones too, with "isFree" saying which ones the keyless
    entries can call. Only a free model is offered as NEW. One that is listed and no longer free
    is a NOTICE and never a retirement: it still answers, to a caller with an account."""
    catalogue = new_catalogue()
    models = listed(pages[0])
    if models and not any("isFree" in model for model in models):
        # Without the flag every model would read as paid, and every active entry as a notice.
        raise FetchError('the answer lists no "isFree" flag')
    for model in models:
        identifier = model["id"]
        catalogue["members"].add(identifier)
        if model.get("isFree") is not True:
            catalogue["notices"][identifier] = {"what": "paid"}
            continue
        if model.get("expiration_date"):
            catalogue["notices"][identifier] = {"what": "expiration",
                                                "date": safe_text(model["expiration_date"])}
        offer(catalogue, identifier, model.get("name") or "", modalities_usage(model, identifier))
    return catalogue


def requesty_price(model, key):
    """The price per token Requesty states under "key", or None when it states none that is a number."""
    price = model.get(key)
    return price if isinstance(price, (int, float)) and not isinstance(price, bool) else None


def retirement_date(timestamp):
    """The day of a Unix timestamp in seconds, or None when it is no plausible one."""
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not 0 < timestamp < 4102444800:
        return None
    return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc).date().isoformat()


def read_requesty(pages):
    """Requesty: every model it lists, nearly all of them paid, each with the prices it states per token. Only
    a model priced 0 in and out is offered as NEW, and one that is listed and priced otherwise is a NOTICE and
    never a retirement, as Kilo's is: it still answers, to a caller who pays. A "retires" date is a NOTICE too."""
    catalogue = new_catalogue()
    models = listed(pages[0])
    if models and not any(requesty_price(model, "input_price") is not None
                          and requesty_price(model, "output_price") is not None for model in models):
        # Without the prices every model would read as paid, and every active entry as a notice.
        raise FetchError("the answer lists no price")
    for model in models:
        identifier = model["id"]
        catalogue["members"].add(identifier)
        retires = retirement_date(model.get("retires"))
        if retires:
            catalogue["notices"][identifier] = {"what": "expiration", "date": retires}
        elif requesty_price(model, "input_price") == 0 and requesty_price(model, "output_price") == 0:
            offer(catalogue, identifier, usage=usage_of_id(identifier))
        else:
            catalogue["notices"][identifier] = {"what": "priced"}
    return catalogue


def read_aionlabs(pages):
    """Aion Labs: a public list of the models, each with a price and, where it is retired, an "expires_at" (and the
    "replacement_model_id" that takes its place). Its free tier is the account's allowance and no model's own, so
    nothing here says one is free: every model not retired is offered as NEW, and the free tier is checked by a
    person. A modality other than text on both sides is read for what it is."""
    catalogue = new_catalogue()
    for model in listed(pages[0]):
        identifier = model["id"]
        catalogue["members"].add(identifier)
        if model.get("expires_at"):
            replacement = model.get("replacement_model_id")
            catalogue["notices"][identifier] = {
                "what": "expiration", "date": safe_text(model["expires_at"]),
                "replacement": safe_text(replacement) if isinstance(replacement, str) and replacement else None}
            continue
        architecture = model.get("architecture")
        modality = architecture.get("modality") if isinstance(architecture, dict) else None
        sides = modality.split("->") if isinstance(modality, str) else []
        if len(sides) == 2 and sides[1].strip() != "text":
            usage = next((usage for kind, usage in MODALITY_USAGES if kind in sides[1]),
                         usage_of_id(identifier, UNCLASSIFIED))
        else:
            usage = usage_of_id(identifier, CHAT if sides else UNCLASSIFIED)
        offer(catalogue, identifier, model.get("name") or "", usage)
    return catalogue


def read_flagged(pages):
    """Cerebras and SambaNova: an OpenAI-style list, with a "deprecated" flag where there is one."""
    catalogue = new_catalogue()
    for model in listed(pages[0]):
        identifier = model["id"]
        catalogue["members"].add(identifier)
        if model.get("deprecated") is True:
            catalogue["notices"][identifier] = {"what": "deprecation"}
        else:
            if model.get("deprecated") is False:
                catalogue["not_deprecated"].add(identifier)
            offer(catalogue, identifier, model.get("name") or "", usage_of_id(identifier))
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
            if "generateContent" in methods:
                usage = usage_of_id(identifier)
            elif "embedContent" in methods:
                usage = "embeddings"
            else:
                usage = usage_of_id(identifier, UNCLASSIFIED)
            offer(catalogue, identifier, model.get("displayName") or "", usage)
    return catalogue


def read_groq(pages):
    catalogue = new_catalogue()
    for model in listed(pages[0]):
        identifier = model["id"]
        catalogue["members"].add(identifier)
        if model.get("active") is False:
            catalogue["notices"][identifier] = {"what": "inactive"}
        else:
            if model.get("active") is True:
                catalogue["not_deprecated"].add(identifier)
            offer(catalogue, identifier, model.get("owned_by") or "", usage_of_id(identifier))
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
        if not identifier.startswith("ft:"):
            chat = capabilities.get("completion_chat") is True
            offer(catalogue, identifier, model.get("name") or "",
                  usage_of_id(identifier, CHAT if chat else UNCLASSIFIED))
    return catalogue


def read_plain(pages):
    """DeepSeek: an OpenAI-style list and nothing else."""
    catalogue = new_catalogue()
    for model in listed(pages[0]):
        catalogue["members"].add(model["id"])
        offer(catalogue, model["id"], usage=usage_of_id(model["id"]))
    return catalogue


# Cloudflare Workers AI answers "GET /accounts/{account_id}/ai/models/search" with the API's usual envelope,
# a "result" list of one object per model, and its own reference types each of them "unknown", so the
# shape read here is the one its documentation's model catalogue and its command line tool read: the id
# LiteLLM calls the model by ("@cf/<vendor>/<model>") is the "name", "task" says what it is for, and the
# "properties" list holds {"property_id", "value"} pairs, one of which, "planned_deprecation_date", is the
# announced retirement the model pages show. A flag "deprecated" is read too, where there is one. Pages are
# asked for the way that tool asks them, "per_page" and "page" until one comes back short.
CLOUDFLARE_PER_PAGE = 50
# The usage a Cloudflare task names; "Text Generation" is every kind of text model, so the id decides.
CLOUDFLARE_TEXT_TASK = "Text Generation"
CLOUDFLARE_TASK_USAGES = {"Automatic Speech Recognition": "transcription", "Text-to-Speech": "speech",
                          "Text Embeddings": "embeddings", "Text-to-Image": "image"}


def cloudflare_property(model, property_id):
    properties = model.get("properties")
    for each in properties if isinstance(properties, list) else []:
        if isinstance(each, dict) and each.get("property_id") == property_id:
            return each.get("value")
    return None


def read_cloudflare(pages):
    catalogue = new_catalogue()
    for page in pages:
        items = page.get("result") if isinstance(page, dict) else None
        if not isinstance(items, list) or page.get("success") is False:
            raise FetchError('the answer holds no "result" list')
        for model in items:
            name = model.get("name") if isinstance(model, dict) else None
            if not isinstance(name, str):
                continue
            if name in catalogue["members"]:
                # The same model on two pages is a server that ignored the page asked for.
                raise FetchError("the pages of the answer repeat a model")
            catalogue["members"].add(name)
            planned = cloudflare_property(model, "planned_deprecation_date")
            if model.get("deprecated") is True or (isinstance(planned, str) and planned):
                catalogue["notices"][name] = {"what": "deprecation"}
                if isinstance(planned, str) and planned:
                    catalogue["notices"][name]["date"] = safe_text(planned)
                continue
            if model.get("deprecated") is False:
                catalogue["not_deprecated"].add(name)
            task = model.get("task")
            task = task.get("name") if isinstance(task, dict) else None
            family = next((usage for prefix, usage in CLOUDFLARE_FAMILY_USAGES if name.startswith(prefix)), None)
            if family:
                usage = family
            elif task == CLOUDFLARE_TEXT_TASK or not isinstance(task, str) or not task:
                usage = usage_of_id(name, CHAT if task == CLOUDFLARE_TEXT_TASK else UNCLASSIFIED)
            else:
                usage = CLOUDFLARE_TASK_USAGES.get(task) or " ".join(task.lower().split())
            offer(catalogue, name, usage=usage)
    # A last page that is full is not the end of the list: the pages this check reads ran out first, and
    # a list read in part would call the models of the rest retired.
    last = pages[-1].get("result") if isinstance(pages[-1], dict) else None
    if isinstance(last, list) and len(last) >= CLOUDFLARE_PER_PAGE:
        raise FetchError("the list goes on past the last page this check reads")
    return catalogue


def cloudflare_next(url, page):
    items = page.get("result") if isinstance(page, dict) else None
    if not isinstance(items, list) or len(items) < CLOUDFLARE_PER_PAGE:
        return None
    head, _, number = url.rpartition("page=")
    return "%spage=%d" % (head, int(number) + 1)


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
    # Deprecated models are asked for, which the API lists for three months after their date: a model is
    # then retired when it has left that list, not on the day its date passes.
    ("cloudflare", "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/models/search"
                   "?include_deprecated=true&per_page=%d&page=1" % CLOUDFLARE_PER_PAGE,
     "MODEL_DRIFT_CLOUDFLARE_API_KEY", bearer, read_cloudflare, cloudflare_next),
    ("kilo", "https://ai-gateway.kilo.ai/api/v1/models", None, None, read_kilo, None),
    # NVIDIA's, OVHcloud's and Requesty's catalogues are public. Requesty's is the European one the entries'
    # "api_base" names, and lists the same models as its other address. Z AI's and Cent AI's need a key, and
    # their answer is read as the OpenAI-style list they document, which the drift run first read on 2026-11-24.
    ("nvidia", "https://integrate.api.nvidia.com/v1/models", None, None, read_plain, None),
    ("ovhcloud", "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/models", None, None, read_plain, None),
    ("requesty", "https://router.eu.requesty.ai/v1/models", None, None, read_requesty, None),
    ("zai", "https://api.z.ai/api/paas/v4/models", "MODEL_DRIFT_ZAI_API_KEY", bearer, read_plain, None),
    ("centai", "https://api.cent-ai.dev/v1/models", "MODEL_DRIFT_CENT_AI_API_KEY", bearer, read_plain, None),
    ("aionlabs", "https://api.aionlabs.ai/v1/models", None, None, read_aionlabs, None),
)
PROVIDER_NAMES = tuple(provider[0] for provider in PROVIDERS)
# The providers whose catalogue omits models they serve. An entry of theirs that the catalogue does not
# list proves nothing by itself, so it is never RETIRED or GONE on the list alone. Only a provider known to
# omit models goes here, with what was observed; a provider whose list is merely thought incomplete does not.
# Each declares:
#   "reason"        why, in English and in French, as a NOTICE says it;
#   "probe"         how to ask the provider about ONE model, when it has no route that answers for it (LOOKUPS
#                   is for those that do): a request that proves the model exists as cheaply as the API
#                   allows, and how its answer is read (probe_verdict). An ACTIVE entry the list omits is
#                   asked about; a commented-out one never is, since it is one not routed to for its price
#                   and a call to it could cost. Without a probe, or when it cannot settle the question,
#                   the absence stays a NOTICE;
#   "free_listing"  a page of the provider's documentation, in Markdown, that tables the models it offers
#                   free, read for the NEW ones the list omits too (read_free_listing).
# Z AI. Its error codes are documented at https://docs.z.ai/api-reference/api-code (read 2026-11-24): the
# error is {"error": {"code": "<code>", "message": ...}} under an HTTP status, 1211 with HTTP 400 is
# "Unknown Model, please check the model code", and every 429 is a limit, a balance or a plan -- 1113
# insufficient balance, 1302 rate limit, 1305 service temporarily overloaded, 1308, 1310, 1311 plan does not
# include the model, and the rest -- which a model that does not exist is never answered with. So 200 and
# 429 say the model is served, and 400 with 1211 is the only answer that says it is not; every other answer
# (an authentication code, 1210 invalid parameter, 1212 and 1220-1222, which speak of the call and not the
# model, a 5xx, a timeout, a code the page does not list) settles nothing. The free models are the
# routed ones, so the probe costs nothing; "max_tokens": 1 keeps it small whatever is routed.
# The pricing page serves its tables as Markdown (https://docs.z.ai/guides/overview/pricing.md, read
# 2026-11-24), where a model free of charge is one whose Input and Output cells both read "Free".
INCOMPLETE_CATALOGUES = {
    "zai": {
        "reason": ("its catalogue omits its free \"Flash\" models, which are served all the same (a call to one "
                   "is answered, with an overload error at times, and never as an unknown model)",
                   "son catalogue omet ses modèles gratuits « Flash », qui sont servis malgré tout (un appel "
                   "à l'un d'eux reçoit une réponse, une erreur de surcharge parfois, jamais celle d'un modèle "
                   "inconnu)"),
        "probe": {
            "url": "https://api.z.ai/api/paas/v4/chat/completions",
            "body": lambda model: {"model": model, "messages": [{"role": "user", "content": "hi"}],
                                   "max_tokens": 1},
            "served": (200, 429),
            "unknown": ((400, "1211"),),
        },
        "free_listing": "https://docs.z.ai/guides/overview/pricing.md",
    },
}
# What a catalogue's address is made of besides its key: Cloudflare's carries the account's identifier in
# its path, which the secret gives and nothing that is printed may. The address in PROVIDERS keeps the
# placeholder, the identifier is put in at the last moment and is replaced like a key wherever a message
# could carry it.
ACCOUNT_VARIABLES = {"cloudflare": "MODEL_DRIFT_CLOUDFLARE_ACCOUNT_ID"}
ACCOUNT_ID = re.compile(r"[0-9a-fA-F]{32}")
FREE_READABLE = {"openrouter", "kilo", "requesty"}

# Where each other provider says what is free, which the report links under "to examine": its API
# does not say, so whoever checks a NEW model is sent to the page that does. Cerebras and Groq are
# linked on their rate-limits page, the one that states their free tier (Groq's "/pricing" leads to
# its home page); every page was opened when the entry was written.
PRICING_PAGES = {
    "cloudflare": "https://developers.cloudflare.com/workers-ai/platform/pricing/",
    "cerebras": "https://inference-docs.cerebras.ai/support/rate-limits",
    "sambanova": "https://cloud.sambanova.ai/plans",
    "gemini": "https://ai.google.dev/gemini-api/docs/pricing",
    "groq": "https://console.groq.com/docs/rate-limits",
    "mistral": "https://mistral.ai/pricing",
    "deepseek": "https://api-docs.deepseek.com/quick_start/pricing",
    "nvidia": "https://build.nvidia.com/",
    "ovhcloud": "https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/",
    "zai": "https://docs.z.ai/guides/overview/pricing",
    "centai": "https://cent-ai.dev/",
    "aionlabs": "https://www.aionlabs.ai/docs/rate-limits/",
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


PROBE_READ = 4096  # what is read of a probe's answer: a code and a message, never more


def probe_verdict(probe, status, raw):
    """How a probe's answer reads: ("served", None), ("absent", None), or ("unsettled", why), the reason
    being a sentence that never carries a key nor any of the answer but its status and its numeric code."""
    code = None
    try:
        payload = json.loads(raw) if raw else None
    except (ValueError, RecursionError):
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        value = payload["error"].get("code")
        if isinstance(value, (str, int)) and not isinstance(value, bool) and re.fullmatch(r"\d{1,6}", str(value)):
            code = str(value)
    if (status, code) in probe["unknown"]:
        return "absent", None
    if status == 200:
        if isinstance(payload, dict) and "error" not in payload:
            return "served", None
        return "unsettled", "HTTP 200 with an answer that is not a completion"
    if status in probe["served"]:
        return "served", None
    return "unsettled", "HTTP %d%s" % (status, ", code %s" % code if code else "")


def ask_by_probe(opener, probe, identifier, headers):
    """What "probe" says when asked for the model "identifier": see probe_verdict. A failure of the
    request itself is "unsettled" too, and never "absent"."""
    body = json.dumps(probe["body"](identifier)).encode()
    headers = dict(headers, **{"Content-Type": "application/json"})
    try:
        raw, status = opener(probe["url"], headers, PROBE_READ, body), 200
    except urllib.error.HTTPError as error:
        try:
            raw = error.read(PROBE_READ + 1)
        except (OSError, ValueError, http.client.HTTPException):
            raw = b""
        status = error.code
    except urllib.error.URLError as error:
        return "unsettled", "network error: %s" % safe_text(error.reason, ERROR_READ)
    except (OSError, ValueError, http.client.HTTPException) as error:
        return "unsettled", "network error: %s" % error.__class__.__name__
    if len(raw) > PROBE_READ:
        return "unsettled", "HTTP %d with an answer too long to read" % status
    return probe_verdict(probe, status, raw)


def probe_absences(provider, report, catalogue, opener, headers):
    """For a provider of INCOMPLETE_CATALOGUES that declares a probe, settle each ACTIVE entry its list
    omits. One its free listing names is served and costs no request; the rest are asked about, and a model
    the provider serves leaves the findings and is kept in report["served"]. One it says does not
    exist becomes RETIRED, deleted like any other. Anything else leaves the NOTICE, with why. A commented-out
    entry is never asked about. A list that holds nothing is a failed read, and asks nothing."""
    probe = (INCOMPLETE_CATALOGUES.get(provider) or {}).get("probe")
    if not probe or not catalogue["members"]:
        return
    kept, asked = [], 0
    free_listed = catalogue.get("free_listed", ())
    for finding in report["findings"]:
        notice = finding.get("notice") or {}
        if finding["kind"] != "notice" or notice.get("what") != "unlisted" or notice.get("commented"):
            kept.append(finding)
            continue
        if finding["id"] in free_listed:
            # The provider's own page lists it as free: served, and no request is spent to know it.
            finding["served_by"] = "its pricing page"
            report.setdefault("served", []).append(finding)
            continue
        if asked >= LOOKUP_LIMIT:
            notice["probe"] = "more than %d models are missing from the list, too many to ask about" % LOOKUP_LIMIT
            kept.append(finding)
            continue
        asked += 1
        verdict, why = ask_by_probe(opener, probe, finding["id"], headers)
        if verdict == "served":
            report.setdefault("served", []).append(finding)
        elif verdict == "absent":
            kept.append({"kind": "retired", "id": finding["id"], "names": finding["names"], "confirmed": True})
        else:
            notice["probe"] = why
            kept.append(finding)
    report["findings"] = kept


FREE_LISTING_LIMIT = 1_000_000
FREE_MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def read_free_listing(markdown):
    """The ids of the models a provider's Markdown pricing page tables as free: a row of a table whose
    header names a "Model", an "Input" and an "Output" column, with "Free" in both of the last two. The
    id is the name lowercased, which is how this provider writes it. A page with no such table is not
    one this check can read, which is that provider's error and never a model gone."""
    free, tables = set(), 0
    columns = None
    for line in markdown.splitlines():
        line = line.strip().lstrip(">").strip()
        if not (line.startswith("|") and line.endswith("|")):
            columns = None
            continue
        cells = [cell.strip().replace("\\", "") for cell in line.strip("|").split("|")]
        if columns is None:
            lowered = [cell.lower() for cell in cells]
            if "model" in lowered and "input" in lowered and "output" in lowered:
                columns = (lowered.index("model"), lowered.index("input"), lowered.index("output"))
                tables += 1
            continue
        if all(re.fullmatch(r":?-+:?", cell) for cell in cells if cell):
            continue
        if max(columns) < len(cells):
            name, price_in, price_out = (cells[column] for column in columns)
            if price_in.lower() == "free" and price_out.lower() == "free" and FREE_MODEL_NAME.fullmatch(name):
                free.add(name.lower())
    if not tables:
        raise FetchError("the pricing page holds no table of prices this check reads")
    return free


def add_free_listing(opener, url, catalogue):
    """Read the provider's pricing page for its free models and offer the ones the list omits as NEW,
    labelled with where they were read. The key is never sent: the page is public documentation."""
    raw = fetch_raw(opener, url, {"User-Agent": USER_AGENT, "Accept": "text/markdown"}, FREE_LISTING_LIMIT)
    if len(raw) > FREE_LISTING_LIMIT:
        raise FetchError("the pricing page is too big to read")
    try:
        free = read_free_listing(raw.decode("utf-8"))
    except UnicodeDecodeError:
        raise FetchError("the pricing page is not text") from None
    catalogue["free_listed"] = free
    for identifier in sorted(free):
        if identifier not in catalogue["candidates"]:
            offer(catalogue, identifier, usage=usage_of_id(identifier))
        if identifier in catalogue["candidates"]:
            catalogue["candidates"][identifier] = "listed free on its pricing page"


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
    incomplete = INCOMPLETE_CATALOGUES.get(provider)

    def absent(kind, identifier, names):
        if incomplete:
            return {"kind": "notice", "id": identifier, "names": names,
                    "notice": {"what": "unlisted", "reason": incomplete["reason"],
                               "commented": kind == "gone"}}
        return {"kind": kind, "id": identifier, "names": names}

    for identifier, names in sorted(active.items()):
        if identifier not in members:
            findings.append(absent("retired", identifier, names))
        elif identifier in catalogue["notices"]:
            findings.append({"kind": "notice", "id": identifier, "names": names,
                             "notice": catalogue["notices"][identifier]})
    for identifier, names in sorted(commented.items()):
        if identifier not in members and identifier not in active:
            findings.append(absent("gone", identifier, names))

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
                         "usage": catalogue.get("usages", {}).get(identifier, CHAT),
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
# a long context besides, which a score does not say: the report says so, and nothing here applies. "fiction"
# has a contract and a table in the document of the routes like the others, but none of its members has a
# figure, so no new model is ever placed in it and its report lists them unranked.
RANKING_ROUTERS = (("pro", "intelligence"), ("flash", "intelligence"), ("flash-lite", "speed"),
                   ("code", "coding"), ("claude-code", "intelligence"), ("fiction", "intelligence"))
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
        ranking["error"] = shown_error(error, environment)
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
    """One row per NEW chat model: what the ranking source says of it and where it would go. A model of
    another usage is no language model, so the ranking of language models has nothing to say of it."""
    ranking = result["rankings"]
    rows = []
    if ranking["status"] != "read":
        return rows
    for report in result["providers"]:
        for finding in report["findings"]:
            if finding["kind"] != "new" or finding["usage"] != CHAT:
                continue
            model, how = match_ranking(report["name"], finding["id"], finding.get("label", ""),
                                       ranking["models"])
            rows.append({"provider": report["name"], "id": finding["id"], "model": model, "how": how,
                         "places": suggest_places(model, template, ranking["models"]) if model else {}})
    return rows


# ------------------------------------------------------------------------------------------------
# LiteLLM's model map: a second source of announced retirements
# ------------------------------------------------------------------------------------------------
# A provider's own API is the first source of a retirement it announces, and several publish nothing of the
# kind (Google's lists no deprecation at all), so the drift run could not tell a person that a model was
# about to go. LiteLLM's public price map carries an optional "deprecation_date" per model, read here as a
# double check of the providers' own signals: it is a public file of a public repository, read once per run
# without a key, and no model is ever called. It decides nothing about deletion, which stays driven by the
# provider's catalogue alone; an announced retirement is a NOTICE for a person, whichever source says it.

LITELLM_MAP_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
LITELLM_MAP_SITE = "https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json"
LITELLM_MAP_MAX = 16 * 1024 * 1024
# The providers the map keys as "<prefix>/<id>", the prefix being the one the template's "model:" carries for
# the native ones (LITELLM_PREFIXES where it is not the provider's name) and the provider's own name for the two
# that the template reaches as "openai/<id>" on their host. The others reached that way (Kilo Gateway,
# Requesty, Cent AI, Aion Labs) have no key in the map, and looking one up as "openai/<id>" would read the
# deprecation of OpenAI's own model of that name: their entries are skipped, which says nothing of them.
LITELLM_MAP_PROVIDERS = frozenset(NATIVE_PROVIDERS) | {"sambanova", "ovhcloud"}
# What a provider's notice says that is a retirement, as opposed to a model that is no longer free.
DEPRECATION_KINDS = ("expiration", "deprecation", "inactive")
DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def day_of(text):
    """The day a text names, "YYYY-MM-DD", or None: a date, or a timestamp that starts with one, and a real
    day of the calendar. What is shown of the map is only ever such a day, never a piece of its text."""
    match = DAY.match(text.strip()) if isinstance(text, str) else None
    if not match:
        return None
    try:
        datetime.date.fromisoformat(match.group(0))
    except ValueError:
        return None
    return match.group(0)


def litellm_map_key(provider, identifier):
    """The key LiteLLM's map holds the model under, or None when the map has none for this provider."""
    if provider not in LITELLM_MAP_PROVIDERS:
        return None
    return "%s/%s" % (LITELLM_PREFIXES.get(provider, provider), identifier)


def read_litellm_map(opener, today):
    """The state of LiteLLM's map: {"status": "read" | "error", "date", ...}. "read" holds "dates", the day
    of each key that has a valid "deprecation_date", and "members", every model key it carries. "error"
    says why nothing was read, and is never more than the kind of failure. It raises nothing and changes
    nothing else of the run: the providers' own signals stand, and a deletion rests on a catalogue alone."""
    state = {"status": "read", "date": today, "url": LITELLM_MAP_URL, "dates": {}, "members": set(),
             "matched": 0}
    try:
        raw = fetch_raw(opener, LITELLM_MAP_URL, {"User-Agent": USER_AGENT, "Accept": "application/json"},
                        LITELLM_MAP_MAX)
        if len(raw) > LITELLM_MAP_MAX:
            raise FetchError("the map is larger than %d bytes" % LITELLM_MAP_MAX)
        try:
            payload = json.loads(raw)
        except ValueError:
            raise FetchError("the map is not JSON") from None
        except RecursionError:
            raise FetchError("the map is nested too deeply to read") from None
        if not isinstance(payload, dict):
            raise FetchError("the map is not an object")
        models = {key: value for key, value in payload.items()
                  if isinstance(key, str) and key != "sample_spec" and isinstance(value, dict)}
        if not any("litellm_provider" in value for value in models.values()):
            # Without it any object would read as a map in which no model is deprecated.
            raise FetchError("no entry of the map names a litellm_provider")
        state["members"] = set(models)
        state["dates"] = {key: day for key, value in models.items()
                          if (day := day_of(value.get("deprecation_date")))}
    except FetchError as error:
        return {"status": "error", "date": today, "url": LITELLM_MAP_URL, "error": safe_text(error, 120)}
    except Exception as error:
        return {"status": "error", "date": today, "url": LITELLM_MAP_URL,
                "error": "failed: %s" % error.__class__.__name__}
    return state


def deprecation_notice(provider, denies, litellm_date, label, provider_read, map_read, today, commented):
    """The NOTICE of one entry, from what the provider's catalogue says of it ("provider": its notice when it
    announces a retirement, "denies" when it states in so many words that the model is active, not
    deprecated) and what the map says ("litellm_date": its day, or None when it is silent or carries no such
    model), or None when neither announces anything.

    One source announcing and the other silent is a retirement announced, and the notice says which source
    said it. Both announcing the same day is one notice citing both. The sources contradict when they give
    two days, or when the provider says in so many words that the model is active while the map gives a day:
    the retirement is kept, on the earliest day, and the notice carries the disagreement for a WARNING. A
    provider that announces with no day (a flag) cannot differ from a day the map gives. A day already
    passed is a notice all the same, since the model is still listed: it says so, and deletes nothing."""
    if provider is None and litellm_date is None:
        return None
    provider_date = provider.get("date") if provider else None
    provider_day = day_of(provider_date)
    notice = {"what": provider["what"] if provider else "deprecation",
              "date": provider_date if provider else litellm_date,
              "replacement": provider.get("replacement") if provider else None,
              "provider": label, "provider_read": provider_read, "map_read": map_read,
              "provider_date": provider_date, "litellm_date": litellm_date,
              "sources": (["provider"] if provider else []) + (["litellm"] if litellm_date else []),
              "conflict": None, "commented": commented}
    if provider and litellm_date:
        if provider_day and provider_day != litellm_date:
            notice["conflict"] = "dates"
            notice["date"] = min(provider_day, litellm_date)
        elif provider_day:
            notice["date"] = provider_day
        else:
            notice["date"] = litellm_date
    elif litellm_date and denies:
        notice["conflict"] = "provider_active"
    day = day_of(notice["date"])
    notice["passed"] = bool(day and day < today)
    return notice


def add_litellm_dates(result, template, catalogues, today):
    """Combine, for every entry of the file (active or commented out), the provider's own deprecation signal
    with the map's, and put the result in the provider's findings as a NOTICE: the one the provider's reader
    already made is replaced by it, and an entry only the map or a commented-out one has gets its own. An
    entry its provider's catalogue no longer lists is left to the deletion, and an entry of a provider that
    was not read is judged on the map alone, which the notice says."""
    litellm = result["litellm"]
    read = litellm["status"] == "read"
    for report in result["providers"]:
        name = report["name"]
        catalogue = catalogues.get(name)
        active = known_ids(template["active"], name)
        entries = [(identifier, names, False) for identifier, names in active.items()]
        entries += [(identifier, names, True) for identifier, names
                    in known_ids(template["commented"], name).items() if identifier not in active]
        existing = {finding["id"]: finding for finding in report["findings"]
                    if finding["kind"] == "notice" and finding["notice"].get("what") in DEPRECATION_KINDS}
        for identifier, names, commented in sorted(entries, key=lambda entry: entry[0]):
            listed = catalogue is not None and identifier in catalogue["members"]
            if catalogue is not None and not listed and name not in INCOMPLETE_CATALOGUES:
                continue
            key = litellm_map_key(name, identifier)
            if read and key in litellm["members"]:
                litellm["matched"] += 1
            notice = (catalogue or {}).get("notices", {}).get(identifier) if listed else None
            if notice and notice.get("what") not in DEPRECATION_KINDS:
                notice = None
            notice = deprecation_notice(
                notice, listed and identifier in catalogue.get("not_deprecated", ()),
                litellm["dates"].get(key) if read else None, PROVIDER_LABELS[name], catalogue is not None,
                read, today, commented)
            if notice is None:
                continue
            finding = None if commented else existing.get(identifier)
            if finding is not None:
                finding["notice"] = notice
            else:
                report["findings"].append({"kind": "notice", "id": identifier, "names": names, "notice": notice})


def deprecation_conflicts(result):
    """[(report, finding)] of the notices whose two sources disagree, which the summary and the pull
    request of the deletions both print as a WARNING."""
    return [(report, finding) for report in result["providers"] for finding in report["findings"]
            if finding["kind"] == "notice" and finding["notice"].get("conflict")]


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
        and entry["model"] != COMPLEXITY_ROUTER_MODEL
    })
    catalogues = {}
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
            account_variable = ACCOUNT_VARIABLES.get(name)
            account = (environment.get(account_variable) or "").strip() if account_variable else ""
            report["unset"] = [variable for variable, value in ((key_variable, key), (account_variable, account))
                               if variable and not value]
            if report["unset"]:
                report["status"] = "no key"
                continue
            headers.update(send_key(key))
            if account_variable:
                if not ACCOUNT_ID.fullmatch(account):
                    # It goes into the path of the address, so it is held to its spelling, and never shown.
                    report["status"] = "error"
                    report["error"] = "%s is not an account identifier of 32 hexadecimal characters" % account_variable
                    report["error_class"] = "answer"
                    continue
                url = url.replace("{account_id}", account)
        try:
            catalogue = read_catalogue(opener, url, headers, reader, next_page)
        except FetchError as error:
            report["status"] = "error"
            report["error"] = shown_error(error, environment)
            report["error_class"] = error_class(error)
            continue
        free_listing = (INCOMPLETE_CATALOGUES.get(name) or {}).get("free_listing")
        if free_listing:
            try:
                add_free_listing(opener, free_listing, catalogue)
            except FetchError as error:
                # The list was read and its findings stand; the page is a second source for NEW models
                # only, and what it could not say deletes nothing. It is the provider's error all the same.
                report["status"] = "error"
                report["error"] = "its pricing page: " + shown_error(error, environment)
                report["error_class"] = error_class(error)
        report["members"] = len(catalogue["members"])
        report["candidates"] = len(catalogue["candidates"])
        report["unsafe"] = catalogue["unsafe"]
        report["findings"] = diff(name, catalogue, active, commented, ignored)
        confirm_absences(name, report, catalogue, opener, headers)
        probe_absences(name, report, catalogue, opener, headers)
        catalogues[name] = catalogue
    result["litellm"] = read_litellm_map(opener, today)
    add_litellm_dates(result, template, catalogues, today)
    result["rankings"] = read_rankings(opener, environment, today)
    result["ranked"] = rank_new_models(result, template)
    return result


def error_class(error):
    """What kind of failure a FetchError is, in one word the workflow can carry and the issue show:
    the class of its HTTP status, "network" when nothing answered, "answer" when what answered could
    not be read. Never more: the status class says what a person needs, and nothing of a key or a
    body can ride on it."""
    if error.status is not None:
        return "%dxx" % (error.status // 100) if 100 <= error.status <= 599 else "answer"
    return "network" if str(error).startswith("network error") else "answer"


def unreadable_providers(result):
    """[(provider, class)] of the catalogues the run could not read, or None when the model list itself
    could not be read, which reads no catalogue and says nothing of them. These alone make the workflow
    try again two hours later, and open its issue when the day's last attempt still cannot read one."""
    if result["unreadable"]:
        return None
    return [(report["name"], report.get("error_class") or "answer")
            for report in result["providers"] if report["status"] == "error"]


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
# Epoch AI's benchmark data: the source of the code positions, and of the capabilities index
# ------------------------------------------------------------------------------------------------

EPOCH_URL = "https://epoch.ai/data/benchmark_data.zip"
EPOCH_SITE = "https://epoch.ai/benchmarks"
EPOCH_ATTRIBUTION = "Epoch AI, benchmark data, CC BY 4.0"
# The benchmark files the code positions are read from, as (key, name shown, the column that holds the score).
# Only these five members of the archive, and the capabilities index below, are ever opened, by their
# exact name: a web interface arena measures design and is left out on purpose, and nothing else of the
# archive is a code position.
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
# A member has a code position only if this many benchmark files hold a score for it, and a floor on the
# code scale is read from at least this many files too.
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
    more than the kind of failure. It raises nothing and changes nothing else of the run: code
    positions that are not read leave the intelligence index standing in for them."""
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
CONTRACT_CRITERIA = ("intelligence", "intelligence_for_time", "code_quality")
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


def scale_text(value, code):
    """A figure of a floor's scale as the report writes it: a code position is a percentage."""
    return ("%s %%" if code else "%s") % floor_figure(value)


def entry_verdict(found, value, estimated, floor, last_resort, tools, needs_time, needs_index=True,
                  margin=0, code=False):
    """(kind, text) of one entry against its router's floor, the only bound there is: no time makes a
    member ineligible. "value" is the figure of the member on the scale of the router: its effective
    intelligence (see effective_intelligence) or, on a router ranked on code, its code position, and
    "estimated" says it is an estimate. A member conforms while it is no further than the floor's
    "margin" from the floor, on the side that is worse: under it on the index, over it on the code scale,
    where a smaller position is better. A member of the last resort is exempt from the floor; one past it
    is not removed but goes to the last resort tier ("below_floor"). "tools" is what the entry's
    provider declares of tool calls, given only to a router that requires them: "no" excludes the entry,
    and "unknown" is said and excludes nothing. "needs_time" is given to a router ordered by time, where
    a member with no time cannot be placed. "needs_index" is false for such a router that has no floor,
    whose members need no index."""
    if found["state"] == "unmapped":
        return "unmapped", "sans correspondance"
    if tools == "no":
        return "no_tools", "sans appels d'outils"
    note = " ; appels d'outils inconnus" if tools == "unknown" else ""
    if value is None:
        if found["state"] == "no_record":
            return "no_record", "sans enregistrement" + note
        if found["state"] == "stale":
            return "stale", "correspondance périmée" + note
        if found["unverified"]:
            return "unverified", "variante non vérifiée" + note
        if needs_index and not last_resort:
            return "unrankable", ("inclassable : pas de position de code" if code
                                  else "inclassable : pas d'indice") + note
    if needs_time and found["record"]["first_answer"] is None:
        return "unrankable", "inclassable : pas de délai" + note
    if not last_resort and floor is not None and value is not None and (
            value > floor + margin if code else value < floor - margin):
        return "below_floor", ("sous le plancher (%s%s contre %s%s) : dernier recours" % (
            scale_text(value, code) if code else "%.1f" % value, " estimé" if estimated else "",
            scale_text(floor, code), ", marge %g" % margin if margin else "")) + note
    if last_resort:
        return "conforming", "conforme (dernier recours)" + note
    return "conforming", ("conforme (estimé)" if estimated else "conforme") + note


def time_ties(rows, margin, quality=lambda row: row["intelligence"]):
    """The members in the order of their quality, those whose quality is less than "margin" points
    under the best of their group being ordered by time instead, the shortest first, the current
    order settling what is left. A group starts at the first member that is "margin" points or more
    under the best of the one before; a member with no time comes last in its group. "quality" is
    the figure of a row, the higher the better: the intelligence index, or the opposite of a code
    position."""
    def by_time(row):
        seconds = row["first_answer"]
        return (seconds is None, seconds or 0, row["position"])

    ordered, group = [], []
    for row in rows:
        if group and quality(group[0]) - quality(row) >= margin:
            ordered += sorted(group, key=by_time)
            group = []
        group.append(row)
    return ordered + sorted(group, key=by_time)


def epoch_position(score, scores):
    """The position of a score in a benchmark file, as a percentage: one more than the number of models of
    the file whose score is strictly greater, over the number of models of the file, so that a smaller
    figure is better and models with the same score share one. "scores" is {model version: best score}
    for every model of the file."""
    return 100 * (1 + sum(1 for other in scores.values() if other > score)) / len(scores)


def code_positions(listed, epoch):
    """{benchmark file: position} of a model given as {benchmark file: [model versions]} (the "epoch" of an
    entry, or the versions a floor anchor stands for) in the archive read: in each file, the position of
    the best score among the versions listed for it. A file the archive does not hold, or in which none of
    its versions is, gives nothing."""
    found = {}
    for key in EPOCH_KEYS:
        scores = epoch["files"].get(key, {}).get("scores", {})
        best = [scores[version] for version in listed.get(key, ()) if version in scores] \
            if isinstance(listed, dict) else []
        if best:
            found[key] = epoch_position(max(best), scores)
    return found


def median_position(positions):
    """The code position: the median of the positions of a model, which needs EPOCH_MIN_FILES files at
    least, and none below them."""
    return statistics.median(positions.values()) if len(positions) >= EPOCH_MIN_FILES else None


def member_quality(mapping, epoch):
    """The code quality of one entry from the archive read: {"positions": {file: position}, "position":
    the median or None, "why"}. "why" says why there is no code position (none is not a bad one):
    "no_ids" when the entry lists no model version, "no_scores" when none of them is in the archive, and
    "few_files" when they are in too few files."""
    listed = mapping.get("epoch") if isinstance(mapping, dict) else None
    positions = code_positions(listed, epoch)
    position = median_position(positions)
    why = None
    if position is None:
        why = "no_ids" if not isinstance(listed, dict) else "no_scores" if not positions else "few_files"
    return {"positions": positions, "position": position, "why": why}


def router_quality(members, contract, mappings, epoch):
    """The code quality of the members of a router's cascade, or None where the router is not ranked on it
    or the archive was not read: the intelligence index then orders the cascade as a stand-in. A position
    is a property of the member alone, so a router that derives from another is ranked exactly as the
    other one is without being given its cascade."""
    if epoch is None or contract["ranking"]["criterion"] != "code_quality":
        return None
    return {name: member_quality(mappings.get(name), epoch) for name in members}


def code_points(contracts):
    """The points of the conversion of the index into a code position that the contracts declare, as
    [(index, position)] going up, or None when they declare none or it is not well formed."""
    block = contracts.get("code_fallback")
    points = block.get("points") if isinstance(block, dict) else None
    if not isinstance(points, list) or len(points) < 2 or any(
            not isinstance(point, list) or len(point) != 2 or any(figure(item) is None for item in point)
            for point in points):
        return None
    return [(float(index), float(position)) for index, position in points]


def index_to_position(index, points):
    """The code position that an intelligence index estimates, by the line through "points" ([index,
    position] pairs, the index going up and the position never), clamped to the first and the last
    position beyond them: no extrapolation, since the calibration holds no model there. Every figure it
    gives is an estimate."""
    if index <= points[0][0]:
        return points[0][1]
    if index >= points[-1][0]:
        return points[-1][1]
    (low, first), (high, last) = next(pair for pair in zip(points, points[1:]) if pair[0][0] <= index <= pair[1][0])
    return first + (index - low) * (last - first) / (high - low)


def code_figure(quality, intelligence, points):
    """(position, estimated) of a member on the code scale: its measured code position, or else the one
    its effective intelligence estimates by the declared conversion, or none when it has neither."""
    if quality["position"] is not None:
        return quality["position"], False
    if intelligence is not None and points:
        return index_to_position(intelligence, points), True
    return None, False


def time_worth(intelligence, seconds, rate):
    """What a member is worth to a router that values time: its intelligence index less the router's
    exchange rate times its mean time to the first answer token, the same rate the router asks of one
    model's levels. None when either figure is missing: the worth of a member is never estimated."""
    if intelligence is None or seconds is None:
        return None
    return intelligence - rate * seconds


def contract_order(rows, ranking):
    """The order a router's contract would give: the members that conform, then the last resort tier
    in the order it has now (the members the contract declares exempt and those under the floor). A
    router that values time puts the members that have a worth first, the greatest first (see
    time_worth), then those that have a time and no index, the shortest first, the current order
    settling a tie, then the members whose quota is shared with a member of the routers it
    names (see "shared_quota_with"), ordered the same way, so that they come after every member that
    has a quota of its own, and then the last resort tier as for any router; any other router puts the best quality first, time breaking a tie between
    members less than the router's margin apart. Code quality is the code position, measured or
    estimated, the smallest first; without the archive the intelligence index orders them all, as a
    stand-in. A member that cannot be judged is not placed."""
    main = [row for row in rows if row["kind"] == "conforming" and not row["last_resort"]]
    tail = [row["name"] for row in rows if row["last_resort"] or row["kind"] == "below_floor"]
    if ranking["criterion"] == "intelligence_for_time":
        def by_worth(row):
            return (row["worth"] is None, -(row["worth"] or 0), row["record"]["first_answer"], row["position"])

        own = sorted((row for row in main if not row["shared_quota"]), key=by_worth)
        shared = sorted((row for row in main if row["shared_quota"]), key=by_worth)
        return [row["name"] for row in own + shared] + tail
    if ranking["criterion"] == "code_quality" and any(row.get("quality") for row in rows):
        main.sort(key=lambda row: (row["code_position"], row["position"]))
        return [row["name"] for row in time_ties(main, ranking["tie_margin_points"],
                                                 lambda row: -row["code_position"])] + tail
    main.sort(key=lambda row: (-row["intelligence"], row["position"]))
    return [row["name"] for row in time_ties(main, ranking["tie_margin_points"])] + tail


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


def anchor_scale(anchor):
    """The scale a floor anchor is on: "code" for an anchor that names the model versions of Epoch AI's
    benchmark files ("code_epoch"), where a smaller position is better, and the intelligence index
    ("index") for any other."""
    return "code" if isinstance(anchor, dict) and "code_epoch" in anchor else "index"


def anchor_floor(anchor, mappings, by_slug, families, scale=None, archive=None):
    """(value, text) of a floor anchor: the index of the record of the entry it names, or, with a
    "level", the index of that level of the entry's family; or, for an anchor that names an "epoch"
    model, its capabilities index converted to the scale of the index, and said estimated; or, for an
    anchor that names the model versions of benchmark files ("code_epoch"), their code position in the
    archive "archive", computed as a member's is. (None, why) when the entry has no mapping, its record
    or the level is not in the ranking, or the record has no index, or the model is not in the
    capabilities index read, or it was not read, or the archive has the versions in too few files: a
    floor that cannot be read judges nothing, and the report says so."""
    if "code_epoch" in anchor:
        text = "%s (Epoch, position de code)" % safe_text(anchor["name"], 60)
        if archive is None:
            return None, "%s : archive d'Epoch AI non lue" % text
        position = median_position(code_positions(anchor["code_epoch"], archive))
        if position is None:
            return None, "%s : trouvé dans moins de %d benchmarks de l'archive" % (text, EPOCH_MIN_FILES)
        return position, text
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


def resolved_contract(contract, mappings, by_slug, families, scale=None, archive=None):
    """The contract with the anchors of its floor read: the floor gets a "value" and a "text" (the
    record it is the index of), a "scale" ("index" or "code") and its "candidates" become the numbers of
    the anchors that could be read, "candidate_texts" naming them. A floor that cannot be read has no
    value (None), and a router that says it has no floor ("none") has no value, no text and no
    candidate."""
    block = contract["intelligence_floor"]
    if block.get("none"):
        return dict(contract, intelligence_floor=dict(block, value=None, text=None, candidates=[], candidate_texts=[]))
    value, text = anchor_floor(block["anchor"], mappings, by_slug, families, scale, archive)
    read = [anchor_floor(anchor, mappings, by_slug, families, scale, archive) for anchor in block.get("candidates") or []]
    return dict(contract, intelligence_floor=dict(
        block, value=value, text=text, scale=anchor_scale(block["anchor"]),
        candidates=[item[0] for item in read if item[0] is not None],
        candidate_texts=[item[1] for item in read if item[0] is not None]))


def floor_text(block):
    """The floor of a resolved contract, as the report says it: its figure, the anchor it is read from and
    the margin it tolerates, if it has one."""
    if block.get("none"):
        return "aucun"
    if block["value"] is None:
        return "introuvable (%s), aucun membre n'est jugé sous le plancher" % block["text"]
    return "%s (%s)%s" % (scale_text(block["value"], block["scale"] == "code"), block["text"],
                          ", marge %g" % block["margin"] if block.get("margin") else "")


def router_rows(members, contract, mappings, by_slug, families, floor=None, quality=None, scale=None, points=None,
                shared=frozenset()):
    """One row per member of a cascade against its router's contract, at the floor given or the
    contract's own. "quality" is the code quality of the members (see router_quality), or None: the
    members are then judged and ordered on the intelligence index, and otherwise on their code position,
    measured or, for a member that has none, estimated from its index by "points" (see code_points) and
    said so. "scale" is what converts a capabilities index (see eci_scale), or None: a member the
    ranking has no index for at the level it is called at is then placed on the estimate its entry's
    "eci" gives, which a router that values time never uses, since its time comes from the ranking.
    "shared" is the names of the members whose quota is shared with a member of the routers the contract
    names (see shared_quota_names)."""
    rate = contract["level_gain"]["min_points_per_second"]
    block = contract["intelligence_floor"]
    floor = block["value"] if floor is None else floor
    needs_time = contract["ranking"]["criterion"] == "intelligence_for_time"
    needs_index = not (needs_time and block.get("none"))
    code = quality is not None
    rows = []
    for position, name in enumerate(members):
        mapping = mappings.get(name)
        found = describe_entry(mapping, by_slug, families) if mapping else {"state": "unmapped"}
        last_resort = name in contract["last_resort"]["members"]
        tools = mapping["tools"]["support"] if mapping else "unknown"
        eci = scale["eci"].get(mapping.get("eci")) if scale and mapping and not needs_time else None
        estimate = eci_to_index(eci, scale["points"]) if eci is not None else None
        value, estimated = effective_intelligence(found, estimate)
        place, place_estimated = code_figure(quality[name], value, points) if code else (None, False)
        kind, text = entry_verdict(found, place if code else value, place_estimated if code else estimated,
                                   floor, last_resort, tools if "tools" in contract.get("requires", ()) else None,
                                   needs_time, needs_index, block.get("margin", 0), code)
        record = found.get("record")
        timed = record is not None and not (place_estimated if code else estimated)
        seconds = record["first_answer"] if timed else None
        sharing = name in shared and kind == "conforming" and not last_resort
        rows.append({"name": name, "position": position, "found": found, "kind": kind,
                     "verdict": text + (" ; quota partagé : en dernier" if sharing else ""),
                     "last_resort": last_resort, "tools": tools, "shared_quota": sharing,
                     "record": record, "quality": quality[name] if code else None,
                     "intelligence": value, "estimated": estimated,
                     "code_position": place, "code_estimated": place_estimated,
                     "first_answer": seconds,
                     "worth": time_worth(None if estimated else value, seconds, rate) if needs_time else None,
                     "kept": chosen_level(found["family"], rate) if found["state"] == "resolved" else None})
    return rows


def quota_identity(entry):
    """What a quota is counted on, as far as the template tells: the provider's model id and its base
    address. Two entries with the same identity draw on the same quota of the same account, whatever
    their names and levels; None for an entry that names no model."""
    return (entry["model"], entry["api_base"]) if isinstance(entry.get("model"), str) else None


def shared_quota_names(members, ranking, lists, entries):
    """The members of a cascade that are the same model of the same provider (see quota_identity) as a
    member of one of the routers its ranking names in "shared_quota_with", read off the template and not
    kept by hand: a free quota is counted per model, so such a member spends the quota of the router it
    must not eat. "entries" is {name: entry} of the template's active entries."""
    wanted = {quota_identity(entries[name]) for router in ranking.get("shared_quota_with") or ()
              for name in lists.get((CONTRACT_FALLBACKS, router), ()) if name in entries} - {None}
    return frozenset(name for name in members if name in entries and quota_identity(entries[name]) in wanted)


def floor_effects(members, contract, mappings, by_slug, families, quality=None, scale=None, points=None,
                  shared=frozenset()):
    """What each floor the contract proposes to compare does to a cascade: who stays in front and who
    goes to the last resort tier. Who is not placed at all does not depend on the floor."""
    effects = []
    block = contract["intelligence_floor"]
    compared = list(zip(block.get("candidates") or [], block.get("candidate_texts") or []))
    for floor, anchor_name in compared or ([(block["value"], block["text"])] if block["value"] is not None else []):
        rows = router_rows(members, contract, mappings, by_slug, families, floor, quality, scale, points, shared)
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
    names = [entry["name"] for entry in template["active"]
             if isinstance(entry["name"], str) and entry["model"] != COMPLEXITY_ROUTER_MODEL]
    mappings = contracts["models"]
    by_slug, families = ranking_families(ranking["models"])
    tools = {name: mapping["tools"]["support"] for name, mapping in mappings.items()}
    scale, points = eci_scale(archive, contracts), code_points(contracts)
    entries = {entry["name"]: entry for entry in template["active"] if isinstance(entry["name"], str)}
    routers = []
    for router, _ in RANKING_ROUTERS:
        members = lists.get((CONTRACT_FALLBACKS, router))
        if members is None or router not in contracts["routers"]:
            continue
        contract = resolved_contract(effective_contract(contracts["routers"], router), mappings, by_slug, families,
                                     scale, archive)
        base = contract.get("derives_from")
        quality = router_quality(members, contract, mappings, archive)
        shared = shared_quota_names(members, contract["ranking"], lists, entries)
        rows = router_rows(members, contract, mappings, by_slug, families, quality=quality, scale=scale, points=points,
                           shared=shared)
        routers.append({
            "name": router, "contract": contract, "rows": rows, "current": list(members),
            "proposed": contract_order(rows, contract["ranking"]),
            "floors": floor_effects(members, contract, mappings, by_slug, families, quality, scale, points, shared),
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
        "fallback": contracts.get("fallback_index"), "code_fallback": contracts.get("code_fallback"),
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
            shared_quota_problems(router, contract, routers, problems)
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
    if contracts.get("code_fallback") is not None:
        fallback_problems(contracts["code_fallback"], problems, "code_fallback")
    if contracts.get("fallback_index") is not None:
        fallback_problems(contracts["fallback_index"], problems)
    elif any(isinstance(mapping, dict) and "eci" in mapping for mapping in mappings.values()) or any(
            isinstance(anchor, dict) and "epoch" in anchor for _, anchor in contract_anchors(routers)):
        problems.append('the capabilities index is used ("eci" in a mapping, or an "epoch" anchor) and the file '
                        'declares no "fallback_index" calibration to convert it by')
    return problems


def fallback_problems(block, problems, name="fallback_index"):
    """The shape of a declared fallback: "fallback_index", the general intelligence of a member with no
    index, or "code_fallback", the code position of a member that has none. Where it comes from, whether it
    is read, how it was calibrated and how uncertain it is, and the points of the calibration: pairs of
    numbers, the source figure always going up with the index going up for the first and, for the second,
    the position never going up with it."""
    if not isinstance(block, dict):
        problems.append('"%s" is not a mapping' % name)
        return
    for key in ("source", "status", "method", "uncertainty"):
        if not isinstance(block.get(key), str) or not block[key].strip():
            problems.append('"%s" has no "%s", in words' % (name, key))
    points = block.get("points")
    if (not isinstance(points, list) or len(points) < 2
            or any(not isinstance(point, list) or len(point) != 2 or any(figure(item) is None for item in point)
                   for point in points)):
        problems.append('"%s" must list its calibration "points" as pairs of numbers, two at least' % name)
    elif name == "code_fallback":
        if any(later[0] <= earlier[0] or later[1] > earlier[1] for earlier, later in zip(points, points[1:])):
            problems.append('"code_fallback" has calibration "points" whose index does not go up, or whose '
                            "position goes up with it")
    elif any(later[0] <= earlier[0] or later[1] < earlier[1] for earlier, later in zip(points, points[1:])):
        problems.append('"%s" has calibration "points" that do not go up with the source figure' % name)


def anchor_problems(anchor, where, problems):
    """The shape of a floor anchor: the "entry" it is read from, and optionally the "level" of that
    entry's family to take; or an "epoch" model, named as the capabilities index names it, and then no
    level; or, on the code scale, a "code_epoch": the model versions of the benchmark files that stand for
    the model, with the "name" the report shows. Exactly one of the three is named."""
    if isinstance(anchor, dict) and sum(key in anchor for key in ("entry", "epoch", "code_epoch")) > 1:
        problems.append('%s names more than one of "entry", "epoch" and "code_epoch": exactly one' % where)
    elif isinstance(anchor, dict) and "code_epoch" in anchor:
        versions = anchor["code_epoch"]
        if not isinstance(anchor.get("name"), str) or not anchor["name"].strip():
            problems.append('%s names a "code_epoch" with no "name" to show' % where)
        if "level" in anchor:
            problems.append('%s names a "code_epoch", which has no "level"' % where)
        if (not isinstance(versions, dict) or len(versions) < EPOCH_MIN_FILES or any(
                not isinstance(ids, list) or not ids or any(not isinstance(item, str) or not item.strip()
                                                            for item in ids) for ids in versions.values())):
            problems.append('%s has a "code_epoch" that is not %d benchmark files at least and their model '
                            "versions" % (where, EPOCH_MIN_FILES))
        elif any(key not in EPOCH_KEYS for key in versions):
            problems.append('%s has a "code_epoch" on a benchmark file that is not read: only %s are'
                            % (where, ", ".join(EPOCH_KEYS)))
    elif isinstance(anchor, dict) and "epoch" in anchor:
        if not isinstance(anchor["epoch"], str) or not anchor["epoch"].strip():
            problems.append('%s has an "epoch" that is no model name of the capabilities index' % where)
        elif "level" in anchor:
            problems.append('%s names an "epoch" model, which has no "level"' % where)
    elif not isinstance(anchor, dict) or not isinstance(anchor.get("entry"), str) or not anchor["entry"].strip():
        problems.append('%s must be a mapping that names an "entry", an "epoch" model or a "code_epoch"' % where)
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


def shared_quota_problems(router, contract, routers, problems):
    """The "shared_quota_with" of a ranking, which only a router that values time has: the routers whose
    members' quota it must not eat, each a router with a contract of its own and not the router itself."""
    ranking = contract.get("ranking")
    if not isinstance(ranking, dict) or "shared_quota_with" not in ranking:
        return
    where = 'router "%s", "ranking",' % router
    names = ranking["shared_quota_with"]
    if ranking.get("criterion") != "intelligence_for_time":
        problems.append('%s has a "shared_quota_with" and is not ranked on "intelligence_for_time", the only '
                        "criterion that reads it" % where)
    elif (not isinstance(names, list) or not names or any(not isinstance(name, str) for name in names)
          or any(name == router or not isinstance(routers.get(name), dict) or "derives_from" in routers[name]
                 for name in names)):
        problems.append('%s has a "shared_quota_with" that is not a list of other routers that have a contract of '
                        "their own" % where)


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
        if "margin" in block and (figure(block["margin"]) is None or block["margin"] < 0):
            problems.append('%s, "intelligence_floor", has a "margin" that is not a number from 0 up' % where)
        scales = {anchor_scale(anchor) for _, anchor in contract_anchors({"router": contract})}
        wanted = "code" if isinstance(contract.get("ranking"), dict) and contract["ranking"].get("criterion") == "code_quality" else "index"
        if scales and scales != {wanted}:
            problems.append('%s, "intelligence_floor", must be on one scale, the code scale ("code_epoch" anchors) '
                            'for a router ranked on "code_quality" and the intelligence index for any other'
                            % where)
    if block is not None and block.get("none") is True and "margin" in block:
        problems.append('%s, "intelligence_floor", says "none" and so has no "margin"' % where)
    block = contract_block_problems(contract.get("ranking"), '%s, "ranking",' % where, problems)
    if block is not None:
        if block.get("criterion") not in CONTRACT_CRITERIA:
            problems.append('%s, "ranking", must have a "criterion" among: %s'
                            % (where, ", ".join(CONTRACT_CRITERIA)))
        elif block["criterion"] != "intelligence_for_time" and (
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
    """The contracts' reading of the cascades for the summary, or None where there is nothing to say
    (no path, or the ranking was not read). It never raises and never changes the run: a file that
    is wrong says so in the summary, and so does a computation that failed, by the kind of error."""
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


# ------------------------------------------------------------------------------------------------
# The figures of the catalogue: what this run read of Artificial Analysis and of Epoch AI, per entry
# ------------------------------------------------------------------------------------------------

# "docs/catalog_scores.json" holds the figures that "docs/CATALOG.md" shows for each entry. The CI cannot read the
# sites they come from, so the weekly run does, and rewrites the file in each pull request it opens; the check of
# every pull request then holds the file to its shape (below) and the catalogue to the file. The file is data
# and nothing else: the figures are numbers, within bounds that no real figure leaves, and each belongs to an
# entry of the template, so that what a compromised reader could put in it steers nothing and says nothing.
SCORES = ROOT / "docs" / "catalog_scores.json"
SCORE_SOURCES = (
    ("artificial_analysis_read", ("aa_index", "aa_first_answer_seconds")),
    ("epoch_read", ("epoch_eci", "epoch_code_position")),
)
SCORE_KEYS = tuple(key for _, keys in SCORE_SOURCES for key in keys)
# The widest range each figure can take, a bound and not a judgement: a figure outside it is no figure of its kind.
SCORE_BOUNDS = {"aa_index": (0, 200), "aa_first_answer_seconds": (0, 3600), "epoch_eci": (0, 1000),
                "epoch_code_position": (0, 100)}
SCORE_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
SCORE_TOP = tuple(read for read, _ in SCORE_SOURCES) + ("entries",)


def score_figure(value, key):
    """The figure as the file writes it, or None when it is no figure of this kind: a number, finite, within its
    bounds, to two decimals so that a revised source does not rewrite the file for a digit nobody reads."""
    number = figure(value)
    low, high = SCORE_BOUNDS[key]
    return round(number, 2) if number is not None and low <= number <= high else None


def scores_problems(document, names):
    """Why "document" is not a file of figures for the entries "names", as a list: a list of nothing means the shape
    is the one the generator reads. Every figure is a number, every key one of the four, every entry one of the
    template's, every date a real day or none, and a figure of a source that was never read is refused."""
    if not isinstance(document, dict) or set(document) != set(SCORE_TOP):
        return ["the file is not an object with exactly the keys %s" % ", ".join(SCORE_TOP)]
    problems = []
    dates = {}
    for read, _ in SCORE_SOURCES:
        value = document[read]
        if value is not None:
            try:
                datetime.date.fromisoformat(value)
            except (TypeError, ValueError):
                value = False
            if value is False or not SCORE_DATE.fullmatch(value):
                problems.append("%s is not a day written YYYY-MM-DD, or null" % read)
                value = None
        dates[read] = value
    entries = document["entries"]
    if not isinstance(entries, dict):
        return problems + ["entries is not an object"]
    for name, figures in entries.items():
        if name not in names:
            problems.append("%s is no entry of the template" % safe_text(name, 60))
        elif not isinstance(figures, dict) or not figures:
            problems.append("%s holds no figure" % name)
        else:
            for key, value in figures.items():
                if key not in SCORE_KEYS:
                    problems.append("%s: %s is no kind of figure" % (name, safe_text(key, 40)))
                elif score_figure(value, key) is None:
                    problems.append("%s: %s is not a number within %s and %s" % ((name, key) + SCORE_BOUNDS[key]))
                elif score_figure(value, key) != value:
                    problems.append("%s: %s is not written to two decimals at most" % (name, key))
                elif dates[next(read for read, keys in SCORE_SOURCES if key in keys)] is None:
                    problems.append("%s: %s comes from a source the file says was never read" % (name, key))
    return problems


def render_scores(document):
    """The file as it is written, and the only way it is: the entries by name, the figures in the order of
    SCORE_KEYS, one space of indentation, a newline at the end. A copy that is not exactly this is refused, so that
    the file has one spelling and no room in it."""
    ordered = {read: document[read] for read, _ in SCORE_SOURCES}
    ordered["entries"] = {name: {key: document["entries"][name][key] for key in SCORE_KEYS
                                 if key in document["entries"][name]} for name in sorted(document["entries"])}
    return json.dumps(ordered, indent=1) + "\n"


def parse_scores(text):
    """(document, problems) of the text of the file: a key written twice and anything but an object are refused."""
    def pairs(items):
        keys = [key for key, _ in items]
        if len(set(keys)) != len(keys):
            raise ValueError("a key is written twice")
        return dict(items)
    try:
        return json.loads(text, object_pairs_hook=pairs), []
    except (ValueError, RecursionError) as error:
        return None, ["the file is not JSON (%s)" % error.__class__.__name__]


def scores_file_problems(text, names):
    """(document, problems) of the text of the figures file against the entries "names": the problems of its shape, or
    that it is not written the one way it is."""
    document, problems = parse_scores(text)
    problems = problems or scores_problems(document, names)
    if not problems and text != render_scores(document):
        problems = ["the file is not written the way the generator writes it (entries by name, one space of "
                    "indentation, a newline at the end)"]
    return document, problems


def read_scores(path, names):
    """(document, problems) of the file at "path" against the entries "names". A file that is absent is a problem, so
    that nothing is checked against figures nobody committed."""
    try:
        text = Path(path).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return None, ["the file cannot be read (%s)" % error.__class__.__name__]
    return scores_file_problems(text, names)


def code_position_of(mapping, archive):
    """The measured code position of an entry in the archive read, or None."""
    return member_quality(mapping, archive)["position"]


def catalog_scores(text, contracts, ranking, epoch, previous, today):
    """The document of the figures for the template "text": what this run read of each source for each entry the
    contracts map, and, for a source this run did not read (no key, an error, none asked), what the file already
    held of it, with its day. An entry that is no entry of the template is left out whichever source says
    something of it, which is how a deletion takes its figures with it. Never raises: a source that cannot be
    turned into figures counts as not read."""
    template, _ = read_template(text)
    names = [entry["name"] for entry in template["active"] if isinstance(entry["name"], str)]
    held = previous.get("entries") if isinstance(previous, dict) and isinstance(previous.get("entries"), dict) else {}
    mappings = contracts.get("models") if isinstance(contracts, dict) and isinstance(contracts.get("models"), dict) else {}
    fresh = {name: {} for name in names}
    read = {}
    for source, keys in SCORE_SOURCES:
        before = previous.get(source) if isinstance(previous, dict) else None
        read[source] = before if isinstance(before, str) else None
        try:
            if source == "artificial_analysis_read" and (ranking or {}).get("status") == "read":
                by_slug, families = ranking_families(ranking["models"])
                for name in names:
                    mapping = mappings.get(name)
                    found = describe_entry(mapping, by_slug, families) if isinstance(mapping, dict) else None
                    if found and found["state"] == "resolved" and not found["unverified"]:
                        record = found["record"]
                        for key, value in (("aa_index", record["intelligence"]),
                                           ("aa_first_answer_seconds", record["first_answer"])):
                            if score_figure(value, key) is not None:
                                fresh[name][key] = score_figure(value, key)
                read[source] = today
                continue
            if source == "epoch_read" and (epoch or {}).get("status") == "read":
                for name in names:
                    mapping = mappings.get(name)
                    if not isinstance(mapping, dict):
                        continue
                    found = {"epoch_eci": (epoch.get("eci") or {}).get(mapping.get("eci")),
                             "epoch_code_position": code_position_of(mapping, epoch)}
                    for key, value in found.items():
                        if score_figure(value, key) is not None:
                            fresh[name][key] = score_figure(value, key)
                read[source] = today
                continue
        except Exception:
            fresh = {name: {key: value for key, value in figures.items() if key not in keys}
                     for name, figures in fresh.items()}
        if read[source] is None:
            continue
        for name in names:
            old = held.get(name) if isinstance(held.get(name), dict) else {}
            for key in keys:
                if key in old and score_figure(old[key], key) == old[key]:
                    fresh[name][key] = old[key]
    document = {source: read[source] for source, _ in SCORE_SOURCES}
    document["entries"] = {name: figures for name, figures in fresh.items() if figures}
    return document


def scores_text(text, contracts, ranking, epoch, previous, today):
    """The text of the figures file for the template "text", as it is written, or None when the template cannot be
    read."""
    template, _ = read_template(text)
    if template is None:
        return None
    return render_scores(catalog_scores(text, contracts, ranking, epoch, previous, today))


def previous_scores(path):
    """The figures file as the checkout has it, or None when it is absent or no figures file: a run then holds on to
    nothing and writes what it read."""
    try:
        document, _ = parse_scores(Path(path).read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError):
        return None
    return document if isinstance(document, dict) else None


def level_text(record):
    return record["level"] if record["level"] else "niveau unique"


def contract_cells(row):
    """The cells of a member's row in the summary: the record, the level called, its figures, the level
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
    if ranking["criterion"] == "intelligence_for_time":
        shared = ranking.get("shared_quota_with") or []
        return ("l'indice d'intelligence moins %g points par seconde de délai moyen avant le premier jeton de la "
                "réponse, le plus grand en tête ; un membre qui a un délai et pas d'indice vient après ceux qui "
                "ont les deux, le plus rapide d'abord%s"
                % (contract["level_gain"]["min_points_per_second"],
                   " ; un membre qui est le même modèle chez le même fournisseur qu'un membre de %s, donc sur le "
                   "même quota, passe après tous les autres, dans le même ordre"
                   % " ou ".join("`%s`" % safe_text(name, 20) for name in shared) if shared else ""))
    margin = ", le délai départageant deux membres à moins de %g points d'écart" % ranking["tie_margin_points"]
    if ranking["criterion"] != "code_quality":
        return "l'indice d'intelligence" + margin
    source = "source : %s, %s" % (safe_text(ranking["source"], 200), epoch_status_text(epoch))
    if epoch["status"] == "read":
        return ("la position de code (%s), la médiane des positions sur les benchmarks, la plus petite en tête, "
                "le délai départageant deux membres à moins de %g points de position d'écart ; un membre qui n'en a "
                "pas reçoit une position estimée d'après son indice d'intelligence"
                % (source, ranking["tie_margin_points"]))
    return ("la position de code (%s) ; Artificial Analysis n'a pas d'indice de code, l'indice d'intelligence "
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


def position_text(position, estimated=False):
    """A code position as the report writes it: "18 %", and "56 % (estimé)" for an estimated one."""
    return scale_text(position, True) + (" (estimé)" if estimated else "")


def quality_lines(router, epoch, fallback=None):
    """The code position of a router's members, in French: the position of each in each benchmark of the
    archive of Epoch AI, the code position that is their median, the place it gives, which members have
    none measured and are placed on an estimate from their index, and which are not placed at all."""
    quality = router["quality"]
    if quality is None:
        return []
    by_name = {row["name"]: row for row in router["rows"]}
    kept = [name for name in router["proposed"] if by_name[name]["kind"] == "conforming"
            and not by_name[name]["last_resort"]]
    out = ["Position de code, d'après %s (<%s>, archive lue le %s). Dans chaque benchmark, la position d'un "
           "score est (1 + le nombre de modèles du fichier dont le score est strictement meilleur) / le nombre "
           "de modèles du fichier, en pourcentage : plus elle est petite, meilleur est le modèle, et les "
           "variantes d'effort d'un modèle comptent chacune pour un modèle. La position d'un membre dans un "
           "benchmark est celle du meilleur score parmi les modèles que son entrée y liste, et sa position de "
           "code est la médiane de ses positions, sur %d benchmarks au moins. Un membre est sous le plancher "
           "quand sa position de code le dépasse de plus que la marge du plancher. %s WebDev Arena et toute "
           "arène de design ou d'interface ne sont pas lues."
           % (EPOCH_ATTRIBUTION, EPOCH_SITE, epoch["date"], EPOCH_MIN_FILES,
              "Un membre qui n'a aucune position de code mesurée en reçoit une, estimée d'après son indice "
              "d'intelligence par la conversion du fichier (%s), marquée « estimé » partout, et sans délai "
              "propre." % safe_text(fallback["source"], 120) if fallback else
              "Le fichier ne déclare aucune conversion de l'indice en position : un membre sans position de "
              "code mesurée n'est pas placé."), "",
           "| Membre | %s | Position de code | Place |" % " | ".join(label for _, label, _ in EPOCH_FILES),
           "| %s |" % " | ".join(["---"] * (len(EPOCH_FILES) + 3))]
    for row in router["rows"]:
        found = quality[row["name"]]
        if row["name"] in kept:
            place = str(kept.index(row["name"]) + 1)
        elif row["last_resort"]:
            place = "dernier recours"
        else:
            place = "sous le plancher" if row["kind"] == "below_floor" else row["verdict"]
        out.append("| `%s` | %s | %s | %s |" % (
            safe_text(row["name"], 60),
            " | ".join(position_text(found["positions"][key]) if key in found["positions"] else "—"
                       for key in EPOCH_KEYS),
            "—" if row["code_position"] is None else position_text(row["code_position"], row["code_estimated"]),
            place))
    unread = ["%s (`%s`)" % (label, safe_text(epoch["skipped"][key], 80))
              for key, label, _ in EPOCH_FILES if key in epoch["skipped"]]
    why = {"no_ids": "aucun identifiant Epoch connu", "no_scores": "aucun score dans l'archive pour ses identifiants",
           "few_files": "moins de %d benchmarks où il a un score" % EPOCH_MIN_FILES}
    estimated = ["`%s` (%s)" % (safe_text(row["name"], 60), why[quality[row["name"]]["why"]])
                 for row in router["rows"] if row["code_estimated"]]
    unranked = ["`%s`" % safe_text(row["name"], 60) for row in router["rows"] if row["kind"] == "unrankable"]
    out.append("")
    if unread:
        out += ["Fichiers de l'archive non lus : %s." % ", ".join(unread), ""]
    if estimated:
        out += ["Sans position de code mesurée, placés sur une position estimée d'après leur indice d'intelligence : "
                "%s." % ", ".join(estimated), ""]
    if unranked:
        out += ["Inclassables, faute de position de code (mesurée, ou estimée d'après un indice d'intelligence), donc non placés : %s."
                % ", ".join(unranked), ""]
    return out


def contracts_section(result):
    """The section "Contrats par routeur" of the summary, in French: one table per router, the
    order the contract would give against the current one, the floors side by side, and what the
    mapping does not cover. A report, whose every violation is information."""
    report = result.get("contracts")
    if not report:
        return []
    out = ["## Contrats par routeur", ""]
    if report["status"] == "invalid":
        out += ["Le fichier `.github/LiteLLM_router_contracts.yaml` n'a pas la forme attendue, rien n'est "
                "calculé dans cette exécution :", ""]
        return out + capped(["- " + " ".join(problem.split()) for problem in report["problems"]]) + [""]
    if report["status"] == "error":
        return out + ["Le calcul a échoué (%s) : rien n'est calculé dans cette exécution, et rien d'autre n'en "
                      "dépend." % code_span(report["kind"]), ""]
    fallback, epoch = report["fallback"], report["epoch"]
    estimating = epoch["status"] == "read" and epoch["eci"] > 0
    out += ["Les cascades lues contre `.github/LiteLLM_router_contracts.yaml`, d'après les chiffres "
            "d'Artificial Analysis lus le %s (<%s>)%s. **C'est un rapport** : rien ne change une cascade, une "
            "entrée ni une ligne `head`, et un écart n'est qu'une information : un membre dit inclassable ou "
            "sous le plancher n'est retiré d'aucune cascade. Aucun délai ne rend un membre inéligible : la "
            "seule borne est le plancher (et les appels d'outils pour `claude-code`), le délai "
            "moyen avant le premier jeton de la réponse ne sert qu'à ordonner. Le niveau retenu pour un "
            "modèle s'obtient en montant de niveau tant que chaque seconde de plus avant la première réponse "
            "rapporte au moins le nombre de points d'indice que le routeur demande. Un membre sous le plancher "
            "passe au dernier recours, et la marge d'un plancher, quand il en a une, est tolérée : un membre qui "
            "en reste à moins de cette marge n'est pas dessous. L'échelle "
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
            out += quality_lines(router, report["epoch"], report["code_fallback"])
        if router["base"]:
            out += derivation_lines(router)
        if len(router["floors"]) > 1:
            margin = contract["intelligence_floor"].get("margin")
            out += ["Effet de chaque plancher%s :" % (", avec la marge de %g" % margin if margin else ""), "",
                    "| Plancher | En tête | Dernier recours |", "| --- | --- | --- |"]
            out += ["| %s (%s)%s | %s | %s |" % (
                scale_text(effect["floor"], contract["intelligence_floor"]["scale"] == "code"), effect["text"],
                " (proposé)" if effect["floor"] == contract["intelligence_floor"]["value"] else "",
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

# Why a deletion is left to a human: (the run's report, in English; the summary, in French). The %s is
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
HEAD_PROVIDERS = tuple(provider_name(variable) for variable in PROVIDER_KEY_VARIABLES)


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
            members = lists.get(("%s.fallbacks" % section_name, router_id(alias)))
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
            members = lists.get(("%s.fallbacks" % section_name, router_id(alias)))
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
# exactly what a mass retirement looks like. Such a run is a person's to read, in the summary.
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
# The renderings: the run's report in English, the summary, pull request and commit in the language
# the people who read each of them write in
# ------------------------------------------------------------------------------------------------

KINDS = ("retired", "gone", "notice", "back", "new")

PROVIDER_LABELS = {
    "openrouter": "OpenRouter", "cerebras": "Cerebras", "sambanova": "SambaNova",
    "gemini": "Gemini", "groq": "Groq", "mistral": "Mistral", "deepseek": "DeepSeek",
    "cloudflare": "Cloudflare",
    "kilo": "Kilo Gateway",
    "nvidia": "NVIDIA", "ovhcloud": "OVHcloud", "requesty": "Requesty", "zai": "Z AI", "centai": "Cent AI",
    "aionlabs": "Aion Labs",
}
# GitHub refuses an issue or pull request body past 65536 characters, and the run's summary is held
# to the same size.
BODY_LIMIT = 60000
UNCARRIED_HEADING = "## Nouveaux modèles qu'aucun ajout ne porte"
UNPROPOSED_ELSEWHERE = (" La pull request des modèles à vérifier liste aussi ceux qu'aucun ajout ne "
                        "porte, quand cette exécution l'ouvre ou la réécrit.")


def notice_text(notice, french=False):
    what = notice.get("what")
    date = notice.get("date")
    replacement = notice.get("replacement")
    if what == "unlisted":
        if french:
            extra = (", et une entrée commentée n'est jamais interrogée" if notice.get("commented")
                     else ", et interroger le fournisseur sur ce modèle n'a pas tranché (%s)" % notice["probe"]
                     if notice.get("probe") else "")
            return "non listé ; %s%s : ce n'est pas un retrait" % (notice["reason"][1], extra)
        extra = (", and a commented-out entry is never asked about" if notice.get("commented")
                 else ", and asking the provider about the model could not settle it (%s)" % notice["probe"]
                 if notice.get("probe") else "")
        return "not listed; %s%s, so the absence is not a retirement" % (notice["reason"][0], extra)
    text = notice_head(what, date, french)
    if replacement:
        text += (", remplaçant désigné : `%s`" if french else ", replacement: %s") % replacement
    return text + sources_text(notice, french)


def notice_head(what, date, french=False):
    """What a notice says of a model, and the day where it has one: "expires on 2026-12-01"."""
    if french:
        text = {"expiration": "expiration annoncée", "deprecation": "déprécié",
                "inactive": "marqué inactif", "paid": "n'est plus gratuit",
                "priced": "n'est plus à 0 $"}.get(what, what)
        return text + (" (`%s`)" % date if date else "")
    text = {"expiration": "expires", "deprecation": "deprecated",
            "inactive": "listed as inactive", "paid": "no longer flagged free",
            "priced": "no longer priced at 0"}.get(what, what)
    return text + (" on %s" % date if date else "")


def sources_text(notice, french=False):
    """Which source said a retirement, and what the other one says of it, appended to the notice. A notice
    no map was ever asked about carries no "sources", and says nothing here."""
    sources = notice.get("sources")
    if not sources:
        return ""
    provider = notice["provider"]
    litellm = "la carte de LiteLLM" if french else "LiteLLM's map"
    silent = " n'en dit rien" if french else " says nothing of it"
    conflict = notice.get("conflict")
    if len(sources) == 2:
        if conflict:
            says = ("%s et %s divergent, voir l'avertissement" if french
                    else "%s and %s disagree, see the warning") % (provider, litellm)
        else:
            says = "%s %s %s" % (provider, "et" if french else "and", litellm)
    elif sources == ["provider"]:
        says = provider + (("%s %s" % (" ;" if french else ";", litellm + silent)) if notice["map_read"] else "")
    elif conflict:
        says = ("%s ; %s l'indique actif, voir l'avertissement" if french
                else "%s; %s lists it as active, see the warning") % (litellm, provider)
    elif notice["provider_read"]:
        says = "%s%s %s%s" % (litellm, " ;" if french else ";", provider, silent)
    else:
        says = "%s%s %s" % (litellm, " ;" if french else ";",
                            "le catalogue de %s n'a pas été lu" % provider if french
                            else "the %s catalogue was not read" % provider)
    text = " (%s)" % says
    if notice.get("commented"):
        text += " -- entrée commentée" if french else " -- commented-out entry"
    if notice.get("passed"):
        text += " -- cette date est dépassée" if french else " -- this date has passed"
    return text


def conflict_text(notice, french=False):
    """What a WARNING says of a notice whose sources disagree: both of them, and what each says."""
    provider = notice["provider"]
    litellm = notice_head("deprecation", notice["litellm_date"], french)
    if notice["conflict"] == "provider_active":
        if french:
            return ("les sources divergent : %s indique le modèle actif, non déprécié, la carte de LiteLLM le "
                    "dit %s ; la dépréciation est retenue" % (provider, litellm))
        return ("the sources disagree: %s lists the model as active, not deprecated, LiteLLM's map says it is %s; "
                "the deprecation is kept" % (provider, litellm))
    said = notice_head(notice["what"], notice["provider_date"], french)
    if french:
        return ("les sources divergent : %s dit %s, la carte de LiteLLM dit %s ; la date la plus proche, %s, "
                "est retenue" % (provider, said, litellm, "`%s`" % notice["date"]))
    return ("the sources disagree: %s says %s, LiteLLM's map says %s; the earliest date, %s, is kept"
            % (provider, said, litellm, notice["date"]))


# The providers whose entries are "openai/<id>" with the provider's "api_base", by the name the report gives them.
OPENAI_COMPATIBLE = {"sambanova": "SambaNova", "kilo": "Kilo Gateway", "ovhcloud": "OVHcloud",
                     "requesty": "Requesty", "centai": "Cent AI",
                     "aionlabs": "Aion Labs"}


def litellm_id(provider, identifier):
    """The id as the file writes it in "model:"; the "openai/" ones need their provider named beside them."""
    if provider in OPENAI_COMPATIBLE:
        return "openai/%s" % identifier, " on %s" % OPENAI_COMPATIBLE[provider]
    return "%s/%s" % (LITELLM_PREFIXES.get(provider, provider), identifier), ""


def by_hand_text(usage, provider=None):
    """What a NEW model of a usage other than chat gets, in English: an entry the pull requests of additions
    write, or none when the run cannot tell what the model is or its router does not route to its provider."""
    mode = USAGE_MODES.get(usage)
    if provider and servable(provider, usage) and slot_refusal(provider, entry_usage(usage)):
        return "its entry is written by hand, with model_info.mode %s, and a slot its router does not route to" % mode
    if mode:
        return "its entry is proposed, with model_info.mode %s" % mode + (
            "" if usage in SERVED_USAGES else " (the gateway has no router or client for it yet)")
    if usage in CHAT_LIKE_USAGES:
        return "its entry is proposed as a chat one (the gateway has no client for this kind yet)"
    return "its entry is written by hand, the kind of model being unknown"


def by_hand_reason(usage):
    """The same, in French, as the reason no pull request of additions carries such a model."""
    return ("le workflow ne sait pas de quel type de modèle il s'agit (`%s`), donc quel `model_info.mode` écrire : "
            "l'entrée s'écrit à la main" % usage)


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
            unset = report["unset"]
            state = "not covered (no key): %s %s unset" % (" and ".join(unset), "are" if len(unset) > 1 else "is")
        elif report["status"] == "error":
            state = "ERROR, not read: %s" % report["error"]
        else:
            state = "read, %d model(s), %d candidate(s)" % (report["members"], report["candidates"])
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
            state = ("read, %d model(s), %d of the %d NEW chat model(s) matched; source: Artificial "
                     "Analysis, %s" % (len(ranking["models"]), sum(1 for row in rows if row["model"]),
                                       len(rows), RANKING_SITE))
        out.append("%-11s %s" % ("rankings", state))
    litellm = result.get("litellm")
    if litellm:
        if litellm["status"] == "error":
            state = "ERROR, not read: %s" % litellm["error"]
        else:
            state = ("read, %d model(s), %d with a deprecation date, %d of the entries here matched; source: "
                     "LiteLLM, %s" % (len(litellm["members"]), len(litellm["dates"]), litellm["matched"],
                                      LITELLM_MAP_SITE))
        out.append("%-11s %s" % ("litellm", state))
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
        "notice": "NOTICE   marked for removal by the provider or by LiteLLM's map, or not listed by a catalogue that omits served models",
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
                    line += " -- usage: " + finding["usage"]
                    if finding["usage"] != CHAT:
                        line += ", " + by_hand_text(finding["usage"], report["name"])
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
    conflicts = deprecation_conflicts(result)
    if conflicts:
        out += ["WARNING  the sources of an announced retirement disagree -- the retirement is kept, on the earliest date"]
        for report, finding in conflicts:
            line = "  %s%s" % litellm_id(report["name"], finding["id"])
            if finding.get("names"):
                line += " (%s)" % ", ".join(str(name) for name in finding["names"])
            out.append(line + ": " + conflict_text(finding["notice"]))
        out.append("")
    served = [(report, finding) for report in result["providers"]
              for finding in report.get("served", ())]
    if served:
        out += ["SERVED   missing from the provider's list, yet it answers when asked for the model "
                "itself, or its provider's own page lists it free -- kept, nothing to delete"]
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
    REMOVALS_BRANCH: the number is not known when the summary is written."""
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
                 "cerebras": "-cerebras", "sambanova": "-sambanova", "deepseek": "-direct",
                 "cloudflare": "-cloudflare", "kilo": "-kilo", "nvidia": "-nvidia", "zai": "-zai",
                 "ovhcloud": "-ovh", "requesty": "-requesty", "centai": "-cent-ai",
                 "aionlabs": "-aion-labs"}
DEFAULT_BASES = {"sambanova": "https://api.sambanova.ai/v1", "kilo": "https://ai-gateway.kilo.ai/api/v1",
                 "ovhcloud": "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
                 "requesty": "https://router.eu.requesty.ai/v1", "centai": "https://api.cent-ai.dev/v1",
                 "aionlabs": "https://api.aionlabs.ai/v1"}
# The access group of an entry written for a provider whose models are kept out of "LLM" on purpose, and the one
# every other provider's entries are in. "check_compose_template.py" holds the template to the same table.
ACCESS_GROUPS = {"aionlabs": "Fiction"}
DEFAULT_ACCESS_GROUP = "LLM"
# The second group of every entry, what its provider does with the data sent to it, written after the first. The
# verdicts and their reasons are LITELLM_DATA_GROUPS of "check_compose_template.py", which holds the template to
# them, so an entry written here with the wrong one fails that check on the pull request that adds it. A provider
# whose terms were not read is "Public-Data-Only", which is also what a provider this table lacks gets.
DATA_GROUPS = {"gemini": "Private-Data", "mistral": "Private-Data", "cloudflare": "Private-Data",
               "aionlabs": "Private-Data", "ovhcloud": "Private-Data",
               "openrouter": "Public-Data-Only", "groq": "Public-Data-Only", "deepseek": "Public-Data-Only",
               "zai": "Public-Data-Only", "requesty": "Public-Data-Only", "nvidia": "Public-Data-Only",
               "centai": "Public-Data-Only", "kilo": "Public-Data-Only", "cerebras": "Public-Data-Only",
               "sambanova": "Public-Data-Only"}
DEFAULT_DATA_GROUP = "Public-Data-Only"


def addition_group(provider, usage=CHAT):
    """The first group of an entry: the models kept out of "LLM" on purpose are in the group of their own
    whatever their mode, as check_compose_template.py holds them to, and any other is in the group of its
    usage."""
    return ACCESS_GROUPS.get(provider) or USAGE_GROUPS.get(usage) or DEFAULT_ACCESS_GROUP


def access_groups(provider, usage=CHAT):
    """The groups of an entry written for this provider and usage, as the template writes them."""
    return [addition_group(provider, usage), DATA_GROUPS.get(provider, DEFAULT_DATA_GROUP)]


def access_groups_text(provider, usage=CHAT):
    return '["%s", "%s"]' % tuple(access_groups(provider, usage))


SAFE_CREDENTIAL = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
SAFE_BASE = re.compile(r"https?://[A-Za-z0-9._:/-]+")
# The gateways that need no key. Their entries carry a literal marker for "api_key", which LiteLLM sends as
# a bearer token and the gateway refuses with a 401, so each blanks the Authorization header with
# "extra_headers": an entry written without it fails at run time, behind a cascade that hides the failure.
# Their names are the model's and the gateway's ("beam-kilo"), where ":free" is no word of the name.
KEYLESS_GATEWAYS = {"kilo", "ovhcloud"}
# The providers whose entries are named after the model and the provider ("hy4-flash-cent-ai"), the ":free" of an id
# being no word of the name: the keyless gateways', and the one reseller whose only free model is spelt so.
FREE_NOT_IN_NAME = KEYLESS_GATEWAYS | {"centai"}


def keyless_header_lines(indent):
    """The two lines that blank the Authorization header of an entry whose "api_key" is at "indent"."""
    return [indent + "extra_headers:", indent + '  Authorization: ""']


ADDITION_MARKER = re.compile(r"[a-z][a-z0-9-]{0,63}")


def provider_basis(entries, provider):
    keys = collections.Counter()
    bases = collections.Counter()
    # A keyless gateway's entry carries a literal marker as its "api_key", every other provider's entry
    # names the credential that holds its key.
    field = "api_key" if provider in KEYLESS_GATEWAYS else "credential"
    for entry in entries:
        attributed = attribute(entry["model"], entry["api_base"])
        if attributed and attributed[0] == provider:
            keys[entry[field]] += 1
            bases[entry["api_base"]] += 1
    safe = ADDITION_MARKER if provider in KEYLESS_GATEWAYS else SAFE_CREDENTIAL
    key = next((k for k, _ in keys.most_common() if isinstance(k, str) and safe.fullmatch(k)), None)
    base = bases.most_common(1)[0][0] if bases else DEFAULT_BASES.get(provider)
    if not (isinstance(base, str) and SAFE_BASE.fullmatch(base)):
        base = None
    # The entries of a provider do not all agree on the "api_base" (Gemini's Gemma ones have none):
    # the snippet gets the majority's, and the summary says the choice is open.
    return {"api_key": key, "api_base": base, "mixed": len(bases) > 1}  # the marker, or the credential's name


def name_stem(identifier):
    """The last segment of an id in the spelling of the file's names: lower case, dashes."""
    stem = identifier.split("/")[-1].lower().replace(":free", "-free")
    return re.sub(r"[^a-z0-9]+", "-", stem).strip("-") or "model"


def suffixed_stem(provider, stem):
    """The stem with the provider's suffix: OpenRouter's names end in "-free" for the ":free" of the id, and
    the other providers' get their own, FREE_NOT_IN_NAME's replacing the "-free" rather than following it."""
    if provider in FREE_NOT_IN_NAME:
        stem = re.sub(r"-free$", "", stem) or stem
        return stem + NAME_SUFFIXES.get(provider, "")
    return stem + ("" if stem.endswith("-free") else NAME_SUFFIXES.get(provider, ""))


def propose_name(provider, identifier, taken):
    name = suffixed_stem(provider, name_stem(identifier))
    for suffix in ("", "-" + provider, "-new"):
        if name + suffix not in taken:
            name += suffix
            break
    taken.add(name)
    return name


def snippet(provider, identifier, basis, name):
    lines = ["  - model_name: %s" % name,
             "    model_info:",
             "      access_groups: %s" % access_groups_text(provider),
             "    litellm_params:",
             "      model: %s" % litellm_id(provider, identifier)[0]]
    if basis["api_base"]:
        lines.append('      api_base: "%s"' % basis["api_base"])
    if provider in KEYLESS_GATEWAYS:
        lines.append('      api_key: "%s"' % (basis["api_key"] or "%s-no-key-needed" % provider))
        return lines + keyless_header_lines("      ")
    lines.append('      litellm_credential_name: "%s"' % (basis["api_key"] or "%s-<ACCOUNT>" % provider))
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
    """Where the figures come from and what a suggested place does not judge, in French: the summary
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


def render_summary(result, config_name, link=None):
    """The whole report of a run, in French, for the run's summary: what the pull requests carry and
    what none of them does. It notifies nobody, which is why the issue is kept for the one finding
    nothing else carries, a catalogue that stays unreadable."""
    body = summary_body(result, config_name, link, snippets=True)
    if len(body) > BODY_LIMIT:
        body = summary_body(result, config_name, link, snippets=False)
    return body


def left_outside_pull_requests(result):
    """Whether the run found anything that no pull request of additions carries: a broken rule, a
    provider in error, or a finding that is not a NEW model one of them proposes."""
    return exit_status(result) != 0 and (
        exit_status(result) == 2 or bool(result["rules"]) or any(
            not finding.get("proposed") for report in result["providers"] for finding in report["findings"]))


def summary_body(result, config_name, link, snippets):
    applying = "removals" in result
    out = []
    out.append(
        "Rapport de `.github/workflows/LiteLLM_model_drift.yml` : il compare `%s` sur `main` au "
        "catalogue que publie chaque fournisseur. Ce résumé est le rapport entier de l'exécution, et "
        "le seul endroit où figure ce qu'aucune pull request ne porte ; il n'envoie aucune "
        "notification. Les retraits annoncés sont aussi dans la pull request des suppressions, et les "
        "modèles redevenus gratuits et les nouveaux modèles qu'aucun ajout ne peut porter dans les "
        "pull requests d'ajout, quand cette exécution les ouvre ou les met à jour. Une issue n'est "
        "ouverte que pour un catalogue de fournisseur encore illisible à la dernière tentative du jour." % config_name
    )
    out.append("")
    if applying:
        out.append(
            "Une seule sorte de constat se traite sans jugement : un modèle que son fournisseur ne "
            "liste plus. Le workflow le supprime lui-même, sans IA, dans une pull request, en "
            "citant le catalogue lu et la date ; ce qu'il ne peut pas supprimer sans risque est "
            "listé ici avec sa raison. Tout le reste se décide après vérification sur la page du "
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
    help_text = ("Chaque identifiant d'un modèle de chat vient avec une entrée à compléter : le nom de "
                 "modèle est une proposition, la clé et l'`api_base` sont ceux de la plupart des "
                 "entrées existantes du même fournisseur. La coller telle quelle l'active ; pour la "
                 "laisser inactive, insérer `# ` après les deux espaces d'indentation de chaque "
                 "ligne (`  # - model_name: ...`, comme les autres entrées commentées du "
                 "fichier) et écrire au-dessus « Served, but not routed to: <raison> », avec la "
                 "page du fournisseur et la date de la vérification. L'entrée d'un modèle d'un autre "
                 "usage que le chat s'écrit à la main.")
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
                   "Entrées, actives ou commentées, dont le fournisseur, la carte des prix de LiteLLM "
                   "(`deprecation_date`) ou les deux annoncent le retrait, la source étant citée à chaque "
                   "ligne : prévoir leur remplacement dans les cascades. Un seul des deux suffit à "
                   "l'annoncer ; une date dépassée alors que le modèle est toujours listé reste une "
                   "alerte, rien n'est supprimé pour autant. La pull request des suppressions les liste "
                   "aussi quand cette exécution l'ouvre ou la réécrit."),
        "unlisted": ("Absents d'un catalogue incomplet",
                     "Entrées, actives ou commentées, que le catalogue de leur fournisseur ne liste pas, "
                     "alors qu'il omet des modèles qu'il sert : l'absence ne prouve pas un retrait, donc "
                     "rien n'est supprimé. À vérifier à la main, par un appel au modèle."),
        "back": ("De nouveau gratuits sur OpenRouter",
                 "Entrées commentées dont la variante `:free` est au catalogue, à 0 $ : relire la "
                 "raison écrite au-dessus, et décommenter si elle ne tient plus. La pull request "
                 "des modèles prêts les liste aussi quand elle est ouverte, sinon celle des modèles "
                 "à vérifier."),
        "new_free": ("Nouveaux modèles gratuits",
                     "Gratuité lue dans l'API de leur fournisseur (OpenRouter : `:free` et à 0 $ ; Kilo Gateway : "
                     "`isFree` ; Requesty : prix d'entrée et de sortie à 0), quel que soit l'usage du modèle. À ajouter, ou à commenter avec "
                     "sa raison, ou à écarter par une ligne `# drift-ignore: <fournisseur>/<id> -- "
                     "<raison>` dans le fichier." + UNPROPOSED_ELSEWHERE
                     + (" " + help_text if snippets else "")),
        "new_examine": ("Nouveaux modèles à examiner",
                        "Leur gratuité ne se lit pas dans l'API du fournisseur : la vérifier sur "
                        "sa page de tarifs avant de les router, et sinon les écarter comme "
                        "ci-dessus." + UNPROPOSED_ELSEWHERE + (" " + help_text if snippets else "")),
    }
    taken = set(result.get("names", ()))
    for kind in ("removed", "retired", "gone", "notice", "unlisted", "back", "new_free", "new_examine"):
        lines = []
        listed = []
        for report in result["providers"]:
            for finding in report["findings"]:
                finding_kind = finding["kind"]
                removal = finding.get("removal")
                if finding.get("proposed"):
                    continue
                if finding_kind == "notice" and finding["notice"].get("what") == "unlisted":
                    finding_kind = "unlisted"
                elif finding_kind == "new":
                    finding_kind = "new_free" if finding["free"] else "new_examine"
                elif removal and removal["status"] == "applied":
                    finding_kind = "removed"
                if finding_kind != kind:
                    continue
                if kind.startswith("new"):
                    lines.append(new_model_line(report, finding, snippets, taken))
                else:
                    lines.append(finding_line(report, finding))
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

    out += conflicts_section(result)

    served = [(report, finding) for report in result["providers"]
              for finding in report.get("served", ())]
    if served:
        out += ["## Absents de la liste, mais toujours servis", "",
                "La liste de leur fournisseur ne les nomme pas, mais il répond quand on lui demande "
                "le modèle lui-même, ou sa page de tarifs les donne gratuits : ils ne sont pas retirés, "
                "rien n'est supprimé, et cette section n'est qu'une information.", ""]
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
                "expirée ou révoquée, et Gemini répond `400` à une clé invalide. Le "
                "workflow refait l'exécution deux heures plus tard, trois fois au plus, tant qu'un "
                "catalogue reste illisible, et n'ouvre son issue que si la dernière tentative ne le "
                "lit toujours pas.", ""]
        out += ["- %s : %s" % (report["name"], code_span(report["error"]))
                for report in errors] + [""]

    ranking = result.get("rankings")
    if ranking and ranking["status"] == "error":
        out += ["## Classements non lus", "",
                "La source des classements n'a pas pu être lue : aucune place n'est suggérée "
                "dans cette exécution pour les nouveaux modèles. Rien d'autre n'en dépend, ni les suppressions ni "
                "l'issue du workflow.", "", "- Artificial Analysis : %s"
                % code_span(ranking["error"]), ""]

    litellm = result.get("litellm")
    if litellm and litellm["status"] == "error":
        out += ["## Carte de LiteLLM non lue", "",
                "La carte des prix de LiteLLM, seconde source des retraits annoncés, n'a pas pu être lue : "
                "cette exécution ne rapporte que les retraits que les fournisseurs annoncent eux-mêmes. "
                "Rien d'autre n'en dépend, ni les suppressions ni l'issue du workflow.", "",
                "- LiteLLM : %s" % code_span(litellm["error"]), ""]

    out += ["## Couverture", "",
            "| Fournisseur | État | Modèles au catalogue | Identifiants actifs ici "
            "| Commentés ici |",
            "| --- | --- | --- | --- | --- |"]
    for report in result["providers"]:
        if report["status"] == "no key":
            state = "non couvert (pas de clé : %s %s)" % (
                "secrets" if len(report["unset"]) > 1 else "secret",
                " et ".join("`%s`" % variable for variable in report["unset"]))
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
    if litellm:
        if litellm["status"] == "error":
            state, members = "erreur", "—"
        else:
            state, members = "lu", str(len(litellm["members"]))
        out.append("| Carte de LiteLLM (dates de dépréciation) | %s | %s | — | — |" % (state, members))
    out.append("")
    if result["unattributed"]:
        out.append("Entrées actives d'aucun catalogue lu ici : %s."
                   % ", ".join("`%s`" % model for model in result["unattributed"]))
        out.append("")
    if not left_outside_pull_requests(result):
        out += ["Aucune dérive.", ""]
    return "\n".join(out) + "\n"


def conflicts_section(result):
    """The WARNING of a retirement the two sources disagree about, in French, for the summary and for the
    pull request of the deletions: each entry, both sources and what each says of it. It is no section that
    asks for a reading, and holds back nothing."""
    conflicts = deprecation_conflicts(result)
    if not conflicts:
        return []
    out = ["## Avertissement : sources en désaccord sur un retrait", "",
           "Le fournisseur et la carte des prix de LiteLLM ne disent pas la même chose de ces entrées. Le "
           "retrait est retenu à la date la plus proche, et rien n'est supprimé pour autant : une personne "
           "vérifie sur la page du fournisseur laquelle des deux sources a raison.", ""]
    return out + capped(["%s -- **avertissement** : %s" % (finding_line(report, finding),
                                                       conflict_text(finding["notice"], True))
                         for report, finding in conflicts]) + [""]


def finding_line(report, finding):
    """A finding as a list item, in French: the id, the names it has here, and what is said of it."""
    identifier, where = litellm_id(report["name"], finding["id"])
    line = "- `%s`%s" % (identifier, where.replace(" on ", " chez "))
    if finding.get("names"):
        line += " (%s)" % ", ".join("`%s`" % name for name in finding["names"])
    if finding["kind"] == "notice":
        line += " : " + notice_text(finding["notice"], french=True)
    removal = finding.get("removal")
    if removal and removal["status"] == "refused":
        line += " : **non supprimé par le workflow** : " + refusal_text(removal, True)
    return line


def new_model_line(report, finding, snippets, taken):
    """A NEW model no pull request of additions carries, as a list item in French: its label, why it is
    not proposed, and, with "snippets", the entry to complete, ready to paste. The summary and the pull
    request of the models to verify both list them this way. Every line says the model's usage; only a chat
    model gets an entry to paste."""
    line = finding_line(report, finding)
    if finding.get("label"):
        line += " : `%s`" % finding["label"]
    line += " : usage `%s`" % finding["usage"]
    if finding.get("unproposed"):
        line += " : **pas proposé par pull request** : " + finding["unproposed"]
    if snippets and finding["usage"] == CHAT:
        name = propose_name(report["name"], finding["id"], taken)
        block = snippet(report["name"], finding["id"], report["basis"], name)
        line += "\n" + "\n".join(["  ```yaml"] + ["  " + code for code in block] + ["  ```"])
    return line


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
        "échoue chaque jour pour le dire, jusqu'à ce que la branche soit supprimée. "
        "Fermée sans être fusionnée, elle est remplacée par une nouvelle à l'exécution suivante si "
        "les fournisseurs ne listent toujours pas ces modèles ; fusionnée, ces modèles "
        "disparaissent du rapport à l'exécution d'après.",
        "",
        "Elle se fusionne seule quand aucune section « À relire » n'y figure, que les lignes "
        "supprimées du modèle sont uniquement des entrées entières, les places de cascade qui les "
        "nomment, des commentaires ou des lignes vides, que le catalogue `docs/CATALOG.md`, généré "
        "à partir du modèle et commité avec lui, ne fait que perdre des lignes, qu'elle reste sous "
        "les plafonds d'entrées et de lignes fixés par `.github/workflows/dependabot-auto-merge.yml`, "
        "que sa branche contient tout `main` et que les contrôles que ce workflow attend sont verts. "
        "Sinon elle attend une personne.",
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
                "restent dans le résumé de chaque exécution, avec la raison, jusqu'à ce qu'une "
                "personne le fasse.", ""]
        out += capped(["- `%s` : %s." % (safe_text(litellm_id(report["name"], finding["id"])[0],
                                                    120),
                                           refusal_text(finding["removal"], True))
                       for report, finding in refused]) + [""]

    notices = [(report, finding) for report in result["providers"] for finding in report["findings"]
               if finding["kind"] == "notice" and finding["notice"].get("what") != "unlisted"]
    if notices:
        # Not the section that asks for a reading: an announced retirement does not hold back the
        # deletions this pull request makes.
        out += ["## Retraits annoncés", "",
                "Le fournisseur, la carte des prix de LiteLLM ou les deux annoncent le retrait de ces "
                "entrées (la source est citée à chaque ligne) sans que leur catalogue les ait encore "
                "retirées : cette pull request ne les supprime pas, et ne s'en fusionne pas moins "
                "seule. Prévoir leur remplacement dans les cascades ; elles viendront ici, supprimées, "
                "l'exécution où leur catalogue ne les listera plus.", ""]
        out += capped([finding_line(report, finding) for report, finding in notices]) + [""]
        out += conflicts_section(result)

    litellm = result.get("litellm")
    if litellm and litellm["status"] == "error":
        out += ["## Carte de LiteLLM non lue", "",
                "La carte des prix de LiteLLM, seconde source des retraits annoncés, n'a pas pu être lue à "
                "cette exécution : la section des retraits annoncés ne porte que ce que les fournisseurs "
                "annoncent eux-mêmes. Les suppressions ne dépendent que des catalogues.", ""]

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
        + wrapped("The drift check read each provider's own model catalogue on %s "
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
                  "original. What it could not delete without choosing is listed in the pull "
                  "request and in the run's summary, with the reason; announced retirements are "
                  "listed in the pull request too, and additions get pull requests of their own, "
                  "since they are choices.")
        + written_again
        + "\n")


# ------------------------------------------------------------------------------------------------
# Proposing the NEW models: two pull requests, which only a person merges
# ------------------------------------------------------------------------------------------------
# "--proposals DIR" writes what the drift workflow needs to keep two pull requests of additions,
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
ADDITION_ID = re.compile(r"(?!.*(?:::|//))(?:@cf/)?[A-Za-z0-9][A-Za-z0-9._:/+~-]{0,198}[A-Za-z0-9]")
ADDITION_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
ADDITION_NAME_LIMIT = 80
ADDITION_CREDENTIAL = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
ADDITION_BASE = re.compile(r"https://[a-z0-9.-]+(?::[0-9]{1,5})?(?:/[A-Za-z0-9._-]+)*/?")
ADDITION_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# The file as written, read line by line the way the builder of the workflow reads it.
ADDITION_ENTRY = re.compile(r"  (# )?- model_name: ([^\s#]+)\s*")
ADDITION_FIELD = re.compile(r"\s+(model|api_key|litellm_credential_name|api_base|mode):\s*(?:\"([^\"]*)\"|(\S+))\s*")
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
    "nvidia": "la page d'accueil du catalogue et la fiche du modèle : l'offre est celle d'un service d'essai, "
              "annoncée pour le service et non modèle par modèle, et l'API ne dit rien de la gratuité d'un modèle",
    "ovhcloud": "la fiche du modèle dans le catalogue : l'API donne un prix par jeton, mais l'accès sans clé que "
                "les entrées d'OVHcloud utilisent n'y est pas décrit ; vérifier les appels d'outils annoncés "
                "(« Function Calling ») et que le modèle est servi sans clé, comme les autres entrées OVHcloud",
    "zai": "la page des tarifs, qui nomme les modèles gratuits : la gratuité d'un modèle n'est lue nulle part "
           "dans l'API de Z AI, dont la réponse n'est pas documentée",
    "centai": "la page d'accueil, qui annonce le modèle gratuit avec sa date de fin : la gratuité d'un modèle "
              "n'est lue nulle part dans l'API de Cent AI",
    "aionlabs": "la page « Rate limits » de sa documentation : l'offre gratuite est celle du compte (15 requêtes "
                "par minute, 20 000 jetons par minute et par jour, tous les modèles ensemble) et non celle d'un "
                "modèle, dont le catalogue donne un prix ; ses conditions la disent « a courtesy that we may "
                "change or withdraw at any time ». Un modèle d'Aion Labs n'entre que dans `Auto-Fiction`, avec le "
                "groupe d'accès `Fiction`, jamais dans `LLM` ni dans un autre routeur",
    "cloudflare": "la note qui nomme les modèles demandant un moyen de facturation payant : un modèle qui "
                  "n'y est pas est gratuit dans la limite des 10 000 neurons par jour de tout le compte, "
                  "mais la page ne le dit pas, et rien dans l'API ne le dit : c'est une déduction, que "
                  "chaque entrée Cloudflare du fichier dit « Free status unconfirmed » tant que le compte "
                  "ne l'a pas confirmée",
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


CREDENTIAL_NAME = re.compile(r"\s*(?:#\s*)?-\s+credential_name:\s*(\S+)\s*")
CREDENTIAL_KEY = re.compile(r"\s*(?:#\s*)?api_key:\s*\"os\.environ/([A-Z][A-Z0-9_]*)\"\s*")


def credential_variables(lines):
    """{credential name: the environment variable it reads} of the credentials the file declares, those
    commented out with their entries too, read line by line like the entries are."""
    found = {}
    name = None
    for line in lines:
        if "- model_name:" in line:
            name = None
        declared = CREDENTIAL_NAME.fullmatch(line)
        if declared:
            name = declared.group(1)
            continue
        key = CREDENTIAL_KEY.fullmatch(line)
        if key and name is not None:
            found.setdefault(name, key.group(1))
    return found


def addition_entries(lines):
    """The entries of the "model_list" section as written, active and commented out: {"name",
    "commented", "fields" (model, api_key, litellm_credential_name, api_base as written), "variable" (the
    environment variable the credential its fields name reads, or None), "last" (the index of the line a new
    entry would follow)}. None when there is no "model_list:" line."""
    if "model_list:" not in lines:
        return None
    start = lines.index("model_list:")
    end = next((index for index in range(start + 1, len(lines)) if TOP_LEVEL_KEY.match(lines[index])),
               len(lines))
    entries = []
    variables = credential_variables(lines)
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
        entry["variable"] = variables.get(entry["fields"].get("litellm_credential_name"))
        entries.append(entry)
    return entries


def addition_anchor(entries, provider, usage=CHAT):
    """The entry a new one of "provider" and "usage" is modelled on and written after: for a usage other than
    chat, the provider's last entry of the same mode, active before commented out; failing that, and for chat,
    its last entry of no mode, then any of its entries, with the same preference. An entry whose "api_base" is
    read from the environment is only the model of an embedding, which a chat model is not written after."""
    own = [entry for entry in entries
           if (attribute(entry["fields"].get("model"), entry["fields"].get("api_base")) or (None,))[0] == provider]
    usable = [entry for entry in own if entry["fields"].get("api_base") not in OPENAI_ENV_BASES]
    mode = USAGE_MODES.get(usage)
    if mode:
        same = [entry for entry in own if entry["fields"].get("mode") == mode]
        if same:
            return ([entry for entry in same if not entry["commented"]] or same)[-1]
    pool = [entry for entry in usable if "mode" not in entry["fields"]] or usable
    return ([entry for entry in pool if not entry["commented"]] or pool or [None])[-1]


# The catalogue that states a provider's free tier, for the providers whose API does (FREE_READABLE,
# which the selftest holds it to): the comment above the entry of such a model cites it.
FREE_CATALOGUES = {"openrouter": "openrouter.ai/api/v1/models", "kilo": "ai-gateway.kilo.ai/api/v1/models",
                   "requesty": "router.eu.requesty.ai/v1/models"}
# Of those, the ones whose free ids all end in a suffix: OpenRouter's ":free". Kilo flags a model free and
# spells some of them without it ("reflection/beam-free", "stealth/glyph-cluster"), and Requesty prices them at 0
# under ids that say nothing of it, so no suffix is asked.
FREE_SUFFIX = {"openrouter": ":free"}


def addition_note(kind, date, provider, commented):
    """The comment written above a proposed entry. A commented-out one says "not routed", which is
    what the offline rule asks of its reason."""
    label = PROVIDER_LABELS[provider]
    if commented:
        return ("Not routed to: proposed by the drift run on %s, its free tier on %s not "
                "verified yet." % (date, label))
    if provider in FREE_CATALOGUES:
        return 'Proposed by the drift run on %s: listed free by "%s" that day.' % (
            date, FREE_CATALOGUES[provider])
    return "Proposed by the drift run on %s: its free tier on %s is not verified yet." % (
        date, label)


def addition_model(provider, identifier, usage=CHAT):
    """The "model:" value of an entry for this id and usage: Cloudflare's embeddings go through its
    OpenAI-compatible endpoint, since LiteLLM's "cloudflare/" provider has no embedding route."""
    if provider == "cloudflare" and usage == "embeddings":
        return "openai/%s" % identifier
    return litellm_id(provider, identifier)[0]


def addition_block(kind, date, item, anchor):
    """The lines a proposed entry adds after its anchor: a blank line, its comment, the entry."""
    lead = "  # " if anchor["commented"] else "  "
    usage = item.get("usage", CHAT)
    block = ["", "  # " + addition_note(kind, date, item["provider"], anchor["commented"]),
             "%s- model_name: %s" % (lead, item["name"]), "%s  model_info:" % lead]
    if usage in USAGE_MODES:
        block.append("%s    mode: %s" % (lead, USAGE_MODES[usage]))
    block += ["%s    access_groups: %s" % (lead, access_groups_text(item["provider"], usage)),
              "%s  litellm_params:" % lead,
              "%s    model: %s" % (lead, addition_model(item["provider"], item["id"], usage))]
    if anchor["fields"].get("api_base") is not None:
        block.append('%s    api_base: "%s"' % (lead, anchor["fields"]["api_base"]))
    if item["provider"] in KEYLESS_GATEWAYS:
        block.append('%s    api_key: "%s"' % (lead, anchor["fields"]["api_key"]))
        block += keyless_header_lines(lead + "    ")
    else:
        block.append('%s    litellm_credential_name: "%s"' % (lead, anchor["fields"]["litellm_credential_name"]))
    return block


# The cascade an active entry is given a slot in, at its tail, which is where a person reorders it from: an
# entry whose mode has a router is in a cascade or is an alias target, or the template fails its checks. A text
# entry goes to "Auto-Flash-Lite", the router that holds every model that answers; Aion Labs' to the router of
# their own; a typed one to the router of its mode. Embeddings and the kinds the gateway has no router for are
# reached by their own name and get no slot.
ROUTER_OF_USAGE = {CHAT: "flash-lite", "speech": "tts", "transcription": "stt", "decision": "decision",
                   "extraction": "extraction"}
ROUTER_OF_PROVIDER = {"aionlabs": "fiction"}
# The providers a router routes to (check_compose_template.py's LITELLM_MEDIA_ROUTERS): the router exists
# when one of them has a key, so a member of another provider could be in none of its renderings.
ROUTER_PROVIDERS = {"stt": {"groq", "gemini", "mistral"}, "tts": {"gemini"}, "decision": {"cloudflare"},
                    "extraction": {"cloudflare"}, "fiction": {"aionlabs"}}
# The condition each provider's members are written under in a cascade, None where the provider needs no key.
SLOT_CONDITIONS = {"gemini": "has.Gemini", "mistral": "has.Mistral", "groq": "has.Groq",
                   "openrouter": "has.OpenRouter", "deepseek": "has.DeepSeek", "cloudflare": "has.Cloudflare",
                   "zai": "has.Zai", "requesty": "has.Requesty", "nvidia": "has.NVIDIA", "centai": "has.Cent_AI",
                   "aionlabs": "has.Aion_Labs", "kilo": None, "ovhcloud": None}
ROUTER_NAMES = ROUTER_PUBLIC_NAMES
SLOT_INDENT = "        - "
JINJA_IF_LINE = re.compile(r"\{%-?\s*if\b.*%\}")
JINJA_ENDIF_LINE = re.compile(r"\{%-?\s*endif\s*-?%\}")
JINJA_OTHER_BRANCH = re.compile(r"\{%-?\s*(else|elif)\b.*%\}")


def slot_router(provider, usage):
    """The short id of the router an entry of this provider and usage is given a slot in, or None."""
    if provider in ROUTER_OF_PROVIDER:
        return ROUTER_OF_PROVIDER[provider] if usage == CHAT else None
    return ROUTER_OF_USAGE.get(usage)


def slot_refusal(provider, usage):
    """Why an entry of this provider and usage cannot be given the slot its router needs, or None."""
    router = slot_router(provider, usage)
    if router is None:
        return None
    if router in ROUTER_PROVIDERS and provider not in ROUTER_PROVIDERS[router]:
        return ("%s is not one of the providers of the %s router, which exists only when one of them has a key"
                % (provider, ROUTER_NAMES[router]))
    if provider not in SLOT_CONDITIONS:
        return "%s has no key variable to write a slot under" % provider
    return None


def slot_lines(provider, router, name):
    """The lines that put "name" at the tail of a cascade: under its provider's key, unless the router has
    that provider alone, in which case the template writes its members bare."""
    condition = SLOT_CONDITIONS[provider]
    if condition is None or ROUTER_PROVIDERS.get(router) == {provider}:
        return [SLOT_INDENT + name]
    return ["{%% if %s %%}" % condition, SLOT_INDENT + name, "{% endif %}"]


def cascade_tail(lines, router):
    """The index of the line a slot at the tail of the cascade of "router" is written before: the
    "{% endif %}" that closes the router's own block, or the first line that is no member. None when the
    template has no such cascade, "" when it has one that cannot be read (an else branch)."""
    heading = "    - %s:" % ROUTER_NAMES[router]
    start = next((index for index, line in enumerate(lines) if line.rstrip() == heading), None)
    if start is None:
        return None
    depth = 0
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if JINJA_OTHER_BRANCH.fullmatch(line):
            return ""
        if JINJA_IF_LINE.fullmatch(line):
            depth += 1
        elif JINJA_ENDIF_LINE.fullmatch(line):
            if depth == 0:
                return index
            depth -= 1
        elif not re.fullmatch(r"        - [^\s#]+", line):
            return index
    return len(lines)


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
    slots = {}
    for item in items:
        if not isinstance(item, dict) or sorted(item) not in (["id", "name", "provider"],
                                                                ["id", "name", "provider", "usage"]):
            return None, "an item is not {provider, id, name} or {provider, id, name, usage}"
        provider, identifier, name = item["provider"], item["id"], item["name"]
        usage = item.get("usage", CHAT)
        if not isinstance(provider, str) or provider not in PROVIDER_LABELS:
            return None, "an item names no provider this reads"
        if "usage" in item and not (isinstance(usage, str) and usage in USAGE_MODES):
            return None, "an item's usage is none the template has a mode for"
        if kind == "ready" and provider not in FREE_CATALOGUES:
            return None, "a ready addition is of a provider whose API states its free tier, and only"
        if not isinstance(identifier, str) or not ADDITION_ID.fullmatch(identifier):
            return None, "an id is not spelt like one"
        if provider in FREE_SUFFIX and not identifier.endswith(FREE_SUFFIX[provider]):
            return None, 'an id of a provider whose API states its free tier does not end in ":free"'
        if (not isinstance(name, str) or len(name) > ADDITION_NAME_LIMIT
                or not ADDITION_NAME.fullmatch(name)):
            return None, "a name is not spelt like the file's"
        if name in words or name in names:
            return None, "the name %s is already a word of the template or another item's" % name
        names.add(name)
        if addition_model(provider, identifier, usage) in known:
            return None, "%s/%s is already an entry" % (provider, identifier)
        if "%s/%s" % (provider, identifier) in ignored:
            return None, "%s/%s is set aside by a drift-ignore line" % (provider, identifier)
        anchor = addition_anchor(entries, provider, usage)
        if anchor is None:
            return None, "the template has no entry of %s to model one on" % provider
        key, base = anchor["fields"].get("api_key"), anchor["fields"].get("api_base")
        credential = anchor["fields"].get("litellm_credential_name")
        # Cloudflare's embeddings are the one entry with a base read from the environment, and only one
        # that already has it is modelled on, since the base holds the account's identifier.
        if provider == "cloudflare" and usage == "embeddings":
            if base not in OPENAI_ENV_BASES:
                return None, "the template has no embedding entry of cloudflare to model one on"
            base = None
        if provider in KEYLESS_GATEWAYS:
            if not isinstance(key, str) or not ADDITION_MARKER.fullmatch(key):
                return None, "the key of the entry %s is not a plain marker, as a keyless gateway's is" % anchor["name"]
        elif not isinstance(credential, str) or not ADDITION_CREDENTIAL.fullmatch(credential):
            return None, "the entry %s does not read its key through a credential" % anchor["name"]
        elif keyed(provider) and anchor["variable"] is None:
            # Only this script reads the variable (the command of the body below runs in the container that
            # holds it), so the step that writes the file does not ask.
            return None, "the credential of the entry %s is declared by no credential_list" % anchor["name"]
        if base is not None and not ADDITION_BASE.fullmatch(base):
            return None, "the api_base of the entry %s is not a plain https address" % anchor["name"]
        if kind == "ready" and anchor["commented"]:
            return None, "a ready addition follows an active entry"
        after.setdefault(anchor["last"], []).extend(addition_block(kind, date, item, anchor))
        refusal = slot_refusal(provider, usage)
        if refusal and not anchor["commented"]:
            return None, refusal
        router = slot_router(provider, usage)
        if router and not anchor["commented"]:
            slots.setdefault(router, []).extend(slot_lines(provider, router, name))
    before = {}
    for router, written in slots.items():
        tail = cascade_tail(lines, router)
        if tail == "":
            return None, "the cascade of %s has an else branch, where a slot cannot be written" % ROUTER_NAMES[router]
        if tail is not None:
            before[tail] = written
    out = []
    for index, line in enumerate(lines):
        out += before.get(index, []) if index else []
        out.append(line)
        out += after.get(index, [])
    out += before.get(len(lines), [])
    return "\n".join(out), None


@functools.lru_cache(maxsize=256)
def keyset_render(text, given):
    return render_keyset(text, given)


def key_variable(provider):
    """The key variable of a provider, or None for one that needs none."""
    condition = SLOT_CONDITIONS.get(provider)
    return None if condition is None else "Artificial_Intelligence_LiteLLM_%s_API_key" % condition[len("has."):]


def slot_keysets_problem(text, new_text, slotted, written):
    """Why the slots written do not hold when only some of the keys are given, or None. Rendered with every
    key, a slot is easy; it is with a provider's key alone, or without it, that a cascade is emptied, a slot
    names an entry that is not there, or an entry of a router is left in none."""
    if not slotted:
        return None
    every = list(PROVIDER_KEY_VARIABLES)
    sets = []
    for provider in dict.fromkeys(provider for provider, _, _ in slotted):
        variable = key_variable(provider)
        sets += [(variable,) if variable else (every[0],), tuple(v for v in every if v != variable)]
    for given in dict.fromkeys(tuple(each) for each in sets):
        before, after = keyset_render(text, given), keyset_render(new_text, given)
        if not isinstance(before, dict):
            continue
        if not isinstance(after, dict):
            return "the file does not render when only %s given" % given_text(given)
        names_before = [item.get("model_name") for item in before.get("model_list") or [] if isinstance(item, dict)]
        names_after = [item.get("model_name") for item in after.get("model_list") or [] if isinstance(item, dict)]
        if [name for name in names_after if name not in written] != names_before:
            return "the model list is not the file's when only %s given" % given_text(given)
        lists_before, lists_after = fallback_lists(before), fallback_lists(after)
        for key, members in lists_before.items():
            wanted = members + [name for _, router, name in slotted if key[1] == router and name in names_after
                                and key[0].endswith(".fallbacks")]
            if lists_after.get(key) != wanted:
                return "%s is not what it was plus the slots when only %s given" % (place(key), given_text(given))
        if set(lists_after) != set(lists_before):
            return "a cascade appears or disappears when only %s given" % given_text(given)
        if set(alias_drift(after)) - set(alias_drift(before)):
            return "an alias leaves the head of its cascade when only %s given" % given_text(given)
        # A slot whose entry renders is in a cascade, and a cascade that renders names entries that render.
        for _, router, name in slotted:
            if name in names_after and not any(name in members for key, members in lists_after.items()
                                               if key[1] == router):
                return "the entry %s is in no cascade when only %s given" % (name, given_text(given))
    return None


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

    wanted = pairs(before) | {(item["name"], addition_model(item["provider"], item["id"], item.get("usage", CHAT)))
                              for item in items}
    if pairs(after) != wanted or len(after["active"]) + len(after["commented"]) != (
            len(before["active"]) + len(before["commented"]) + len(items)):
        return "the entries it reads are not the file's and the proposed ones"
    # Every cascade is what it was, plus the slots the active entries were given at the tail of their router's.
    lines_before = text.split("\n")
    active_names = {entry["name"] for entry in after["active"]}
    expected = {key: list(members) for key, members in fallback_lists(before["document"]).items()}
    slotted = []
    for item in items:
        router = slot_router(item["provider"], item.get("usage", CHAT))
        if router and item["name"] in active_names and cascade_tail(lines_before, router) is not None:
            key = next((key for key in expected if key[1] == router and key[0].endswith(".fallbacks")), None)
            if key is None:
                return "the cascade of %s is not one the file reads" % ROUTER_NAMES[router]
            expected[key].append(item["name"])
            slotted.append((item["provider"], router, item["name"]))
    if fallback_lists(after["document"]) != expected:
        return "a cascade is not what it was plus the slots of the entries written"
    problem = slot_keysets_problem(text, new_text, slotted, {item["name"] for item in items})
    if problem:
        return problem
    # An entry is in the one access group its mode makes it: a key limited to a type of models reaches that
    # type and no other, which check_compose_template.py holds the template to.
    for item in items:
        entry = next(entry for entry in after["active"] + after["commented"] if entry["name"] == item["name"])
        info = entry["item"].get("model_info") if isinstance(entry["item"], dict) else None
        info = info if isinstance(info, dict) else {}
        usage = item.get("usage", CHAT)
        if info.get("mode") != USAGE_MODES.get(usage) or info.get("access_groups") != access_groups(
                item["provider"], usage):
            return "the entry %s is not in the mode and the access group of its usage" % item["name"]
    # A keyless gateway's entry that does not blank the Authorization header is refused with a 401 at run time.
    for item in items:
        if item.get("provider") in KEYLESS_GATEWAYS:
            entry = next(entry for entry in after["active"] + after["commented"] if entry["name"] == item["name"])
            parameters = entry["item"].get("litellm_params") if isinstance(entry["item"], dict) else None
            if not isinstance(parameters, dict) or parameters.get("extra_headers") != {"Authorization": ""}:
                return "the entry %s of a keyless gateway does not blank the Authorization header" % item["name"]
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


def route_known(entries, provider, usage):
    """Whether the file already serves this usage through this provider (an entry of the mode, active or
    commented out), which is what shows LiteLLM has a route for it under the provider's prefix."""
    return any(entry["fields"].get("mode") == USAGE_MODES[usage]
               and (attribute(entry["fields"].get("model"), entry["fields"].get("api_base")) or (None,))[0] == provider
               for entry in entries)


def missing_facts(result, provider, finding, entries=()):
    """[(what, sentence)] of what the run does not know of a NEW model, in French: a model of which it
    knows both its free tier, from its provider's API, and a figure of the ranking matched for certain,
    is ready; any other is to verify. A model that is no chat one has no ranking to be matched to: it needs
    its free tier, and a route, which the file shows when it already serves the usage through the provider."""
    missing = []
    if not finding.get("free"):
        missing.append(("free", "sa gratuité ne se lit pas dans l'API de %s" % PROVIDER_LABELS[provider]))
    if finding["usage"] != CHAT:
        if finding["usage"] not in SERVED_USAGES:
            missing.append(("kind", "la passerelle n'a ni routeur, ni groupe de clés, ni client pour le type `%s` "
                            "aujourd'hui : l'entrée est écrite pour qu'une personne la garde ou l'écarte"
                            % finding["usage"]))
        elif not route_known(entries, provider, finding["usage"]):
            missing.append(("route", "le fichier ne sert encore l'usage `%s` par aucune entrée de %s : rien ne montre "
                            "que LiteLLM le route sous ce préfixe" % (finding["usage"], PROVIDER_LABELS[provider])))
        return missing
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
    stem = suffixed_stem(provider, name_stem(identifier)[:60].strip("-") or "model")
    for extra in ["", "-" + provider, "-new"] + ["-%d" % number for number in range(2, 100)]:
        if stem + extra not in taken:
            taken.add(stem + extra)
            return stem + extra
    return None


def propose_additions(text, result, link=None):
    """{kind: {"complete", "items", "text", "body", "commit"}} for the two
    addition pull requests, every NEW finding being marked "proposed" (the kind that carries it) or
    "unproposed" (why not, in French, which the summary and the pull request of the models to verify
    show), and "missing" (what the run does not know of it, empty for a ready one). "complete" says
    whether every source the kind draws on was read: a pull request is closed over "nothing left to
    propose" only then. The bodies also carry what no entry is made of (carried_sections)."""
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
    kept = {}
    for report in result["providers"]:
        for finding in report["findings"]:
            if finding["kind"] != "new":
                continue
            anchor = addition_anchor(entries, report["name"], finding["usage"])
            name = None
            if not servable(report["name"], finding["usage"]):
                finding["unproposed"] = by_hand_reason(finding["usage"])
            elif not ADDITION_ID.fullmatch(finding["id"]):
                finding["unproposed"] = "son identifiant n'a pas une forme que le workflow écrit dans le fichier"
            elif anchor is None:
                finding["unproposed"] = "le fichier n'a aucune entrée de ce fournisseur sur laquelle modeler la sienne"
            elif not anchor["commented"] and slot_refusal(report["name"], entry_usage(finding["usage"])):
                finding["unproposed"] = ("le workflow ne sait pas lui donner la place que son routeur exige : %s ; "
                                         "son entrée s'écrit à la main, avec la table `head` du modèle de "
                                         "configuration" % slot_refusal(report["name"], entry_usage(finding["usage"])))
            elif (report["name"], finding["usage"]) == ("cloudflare", "embeddings") and anchor["fields"].get(
                    "api_base") not in OPENAI_ENV_BASES:
                finding["unproposed"] = ("le fichier n'a aucune entrée d'embeddings de Cloudflare, dont l'`api_base` "
                                         "se lit dans l'environnement, sur laquelle modeler la sienne")
            else:
                name = addition_name(report["name"], finding["id"], taken)
                if name is None:
                    finding["unproposed"] = "aucun nom libre pour son entrée"
            if name is not None:
                finding["missing"] = missing_facts(result, report["name"], finding, entries)
                candidates["to_verify" if finding["missing"] else "ready"].append((report, finding, name))

    for kind in PROPOSAL_KINDS:
        chosen = candidates[kind]
        for _, finding, _ in chosen[PROPOSAL_LIMIT:]:
            finding["unproposed"] = "au-delà des %d entrées qu'une pull request porte" % PROPOSAL_LIMIT
        chosen = chosen[:PROPOSAL_LIMIT]
        while chosen:
            items = [dict({"provider": report["name"], "id": finding["id"], "name": name},
                          **({"usage": finding["usage"]} if entry_usage(finding["usage"]) != CHAT else {}))
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
                kept[kind] = chosen
                break
            chosen.pop()[1]["unproposed"] = "le corps de la pull request dépasserait la taille que GitHub accepte"
        for _, finding, _ in chosen:
            finding["proposed"] = kind
    # Once every NEW finding is marked, so that what a body carries apart is final. The ready pull
    # request carries the models free again, its free tier being the same fact; the other one when it
    # alone is open. A section that would take a body past the limit loses its entries first, then
    # itself: it is in the run's summary all the same.
    back = next((kind for kind in PROPOSAL_KINDS if proposals[kind]["items"]), None)
    for kind, chosen in kept.items():
        for snippets in (True, False):
            carried = carried_sections(result, kind, back, snippets)
            if not carried:
                break
            body = render_additions_body(result, kind, chosen, entries, link, carried)
            if len(body) <= BODY_LIMIT:
                proposals[kind]["body"] = body
                break
    result["proposals"] = {kind: len(proposals[kind]["items"]) for kind in PROPOSAL_KINDS}
    return proposals


def carried_sections(result, kind, back, snippets):
    """What the addition pull request of "kind" carries beside its entries, in French: the commented-out
    models free again on OpenRouter, in the pull request "back" names,
    and, in the one of the models to verify, every NEW model no pull request proposes, with why and the
    entry to complete."""
    out = []
    returning = [(report, finding) for report in result["providers"] for finding in report["findings"]
                 if finding["kind"] == "back"]
    if returning and kind == back:
        out += ["## De nouveau gratuits sur OpenRouter", "",
                "Entrées commentées du fichier dont la variante `:free` est au catalogue d'OpenRouter, à "
                "0 $ : relire la raison écrite au-dessus de chacune, et la décommenter, dans un commit à "
                "part, si elle ne tient plus. Cette pull request ne les touche pas.", ""]
        out += capped([finding_line(report, finding) for report, finding in returning]) + [""]
    left = [(report, finding) for report in result["providers"] for finding in report["findings"]
            if finding["kind"] == "new" and not finding.get("proposed")]
    if left and kind == "to_verify":
        taken = set(result.get("names", ()))
        out += [UNCARRIED_HEADING, "",
                "Le fichier ne les connaît pas, mais le workflow ne sait pas écrire leur entrée, pour la "
                "raison donnée à chacun : ils sont listés ici, avec l'entrée à compléter quand c'est "
                "un modèle de chat, à ajouter dans un commit sur cette branche, à commenter avec sa "
                "raison, ou à écarter par une ligne "
                "`# drift-ignore: <fournisseur>/<id> -- <raison>`." + (
                    " Coller l'entrée telle quelle l'active ; la clé et l'`api_base` sont ceux de la "
                    "plupart des entrées existantes du même fournisseur." if snippets else ""), ""]
        out += capped([new_model_line(report, finding, snippets, taken) for report, finding in left]) + [""]
    return out


def write_proposals(directory, proposals, date, scores=None):
    """"proposals.json" (the date, and for each kind whether it is complete and its items: what the job
    that writes builds from), and for each kind that has items its body, its commit message and the
    file as built here, which that job requires its own to equal, and, when "scores" is given (a function
    of the text of a template that returns the figures file for it, or None), the figures of the
    entries of that file. A file of an earlier run is removed first."""
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
        path = folder / ("%s_scores.json" % kind)
        path.unlink(missing_ok=True)
        written = scores(part["text"]) if scores and part["items"] else None
        if written is not None:
            path.write_bytes(written.encode("utf-8"))
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


def catalogue_command(provider, identifier, variable):
    """A command that prints what "provider" says of the model "identifier", and nothing secret: the
    provider's own route for one model where it has one, else its list filtered to that id. A keyed
    one runs in the LiteLLM container, whose environment holds the key under the name the entry reads
    it from, and prints the model's description, never the key. "identifier" is an ADDITION_ID and
    "variable" the name an environment variable is read under, so neither can end a quoted string of the
    shell or of Python."""
    pick = "answer"
    if provider in LOOKUPS:
        url = '"%s"' % (LOOKUPS[provider] + urllib.parse.quote(identifier, safe="/"))
    elif provider in ACCOUNT_VARIABLES:
        # The account's identifier is read where the key is, in the container, and never written here.
        head, tail = catalogue_url(provider).split("{account_id}")
        url = '"%s" + os.environ["CLOUDFLARE_ACCOUNT_ID"] + "%s&search=%s"' % (
            head, tail.split("?")[0] + "?per_page=%d" % CLOUDFLARE_PER_PAGE,
            urllib.parse.quote(identifier.rsplit("/", 1)[-1], safe=""))
        pick = '[model for model in answer.get("result", []) if model.get("name") == "%s"]' % identifier
    else:
        url = '"%s"' % catalogue_url(provider)
        pick = '[model for model in answer.get("data", []) if model.get("id") == "%s"]' % identifier
    headers = '"User-Agent": "%s"' % USER_AGENT
    if keyed(provider):
        headers += (', "x-goog-api-key": os.environ["%s"]' % variable if provider == "gemini"
                    else ', "Authorization": "Bearer " + os.environ["%s"]' % variable)
    program = ('import json, os, urllib.request; request = urllib.request.Request(%s, headers={%s}); '
               "answer = json.load(urllib.request.urlopen(request, timeout=30)); "
               "print(json.dumps(%s, indent=1))" % (url, headers, pick))
    if keyed(provider):
        return ('docker exec "$(docker ps --quiet --filter name=litellm | head -n 1)" python3 -c \'%s\''
                % program)
    return "python3 -c '%s'" % program


def proposals_section(result):
    """The pointer of the summary to the two addition pull requests, in French."""
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


# The router each usage other than embeddings is served through, by the name a client types.
USAGE_ROUTERS = {"speech": "tts", "transcription": "stt", "decision": "decision", "extraction": "extraction"}


def usage_lines(usage):
    """What a proposed model of a usage other than chat is placed by, as list items in French: no ranking
    measures it, and where it goes is a person's to say."""
    if usage == "embeddings":
        return ["**Aucun routeur** : un modèle d'embeddings s'appelle par son nom, seul, et aucune cascade ni "
                "aucun alias ne le porte (les vecteurs de deux modèles ne se comparent pas). Dimension du "
                "vecteur à lire sur la première réponse, pas sur une page."]
    if usage not in USAGE_ROUTERS:
        return ["**Aucun routeur** : la passerelle n'a ni routeur ni client pour ce type de modèle, et l'entrée "
                "s'appelle par son nom. La garder, c'est décider d'un routeur, d'un groupe de clés et d'un "
                "client qui l'appelle ; l'écarter, c'est la ligne `drift-ignore` ci-dessus."]
    router = ROUTER_PUBLIC_NAMES[USAGE_ROUTERS[usage]]
    return ["**Place laissée à une personne** : aucun classement ne mesure ce modèle, et l'ordre de la cascade de "
            "`%s` se règle à la main, sans règle qui dise où il va : l'entrée est en queue de cette cascade, la "
            "place sûre, et se déplace dans un commit sur cette branche (avec la table `head` du modèle de "
            "configuration si elle devient le premier membre)." % router]


def slot_sentence(provider, usage, name, commented):
    """Where the entry written for a model is put in the cascades, in French."""
    router = slot_router(provider, entry_usage(usage))
    if commented:
        return "Aucune cascade : l'entrée est commentée, sa raison étant provisoire."
    if router is None:
        return ("Aucune cascade : un modèle d'embeddings s'appelle par son nom, et la passerelle n'a pas de routeur "
                "pour ce type de modèle." if usage == "embeddings" else
                "Aucune cascade : la passerelle n'a pas de routeur pour ce type de modèle, l'entrée s'appelle par "
                "son nom.")
    condition = SLOT_CONDITIONS[provider]
    return ("Cascade : en **queue** de `%s`%s, la place sûre, à déplacer à la relecture." % (
        ROUTER_NAMES[router], " sous `{%% if %s %%}`" % condition
        if condition and ROUTER_PROVIDERS.get(router) != {provider} else ""))


def placing_lines(result, provider, identifier, usage=CHAT):
    """What the ranking says of a proposed model, as list items: its figures and the place it would
    take in each router, or that it is not placed, and why. The second value is the reason, in
    English, of the drift-ignore line that sets an unmeasured model aside, or None for a measured one.
    A model of another usage has no ranking: see usage_lines()."""
    if usage != CHAT:
        return usage_lines(usage), None
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
    "kind": "décider si la passerelle doit un jour servir ce type de modèle (un routeur, un groupe de clés et un "
            "client qui l'appelle) ; sinon, supprimer l'entrée et écrire la ligne `drift-ignore` ci-dessous",
    "route": "la fusion ne suffit pas à le savoir : appeler le modèle par son nom depuis la passerelle une fois "
             "l'entrée fusionnée, ou lire la documentation de LiteLLM pour ce fournisseur et cet usage ; si la "
             "route n'existe pas, supprimer l'entrée et écrire la ligne `drift-ignore` ci-dessous",
}


# How each catalogue that states a free tier says it, for the body of the pull request of the ready models.
FREE_READINGS = {"openrouter": "un identifiant `:free`, un prix de 0 en entrée comme en sortie, le texte pour seule sortie",
                 "kilo": "le drapeau `isFree`, le texte pour seule sortie",
                 "requesty": "`input_price` et `output_price` à 0"}
FREE_READING = " ; ".join("chez %s, <%s> : %s" % (PROVIDER_LABELS[name], catalogue_url(name), reading)
                          for name, reading in FREE_READINGS.items())


def render_additions_body(result, kind, chosen, entries, link=None, carried=()):
    """The body of one addition pull request, in French: what it is, how to decide, and each model with
    its entry, its figures and places, and, for the one to verify, which fact is missing and how to
    get it; then the sections "carried" holds."""
    date = result["date"]
    ready = kind == "ready"
    other = os.environ.get(PROPOSAL_BRANCHES["to_verify" if ready else "ready"])
    branch = os.environ.get(PROPOSAL_BRANCHES[kind])
    run = "à l'exécution du %s%s" % (date, " (%s)" % link if link else "")
    if ready:
        out = ["Ajouts **prêts**, proposés **sans IA** par `.github/workflows/LiteLLM_model_drift.yml`, %s. "
               "Pour chaque modèle ci-dessous, l'exécution tient tout ce qu'il faut pour l'ajouter sans y "
               "réfléchir : sa gratuité, lue dans l'API de son fournisseur (%s), et "
               "un chiffre du classement d'Artificial Analysis rapproché de façon sûre (son identifiant, sans `:free`, s'écrit à la casse et à la ponctuation près comme le slug ou le nom d'une seule entrée du classement, qui ne porte aucune marque de variante entre parenthèses) ; pour un modèle qui n'est pas du chat (embeddings, voix, transcription, décisions, extraction), qu'aucun classement ne mesure, sa gratuité et une route déjà servie par le fichier chez le même fournisseur. Les nouveaux "
               "modèles auxquels il manque une de ces informations, de quelque fournisseur qu'ils soient, sont "
               "dans une pull request à part, en brouillon%s." % (
                   run, FREE_READING, " (branche %s)" % code_span(other) if other else ""),
               "",
               "Le commit ajoute chaque entrée après la dernière entrée de son fournisseur du même usage (de chat, "
               "à défaut), sous un commentaire qui cite le catalogue et le jour, avec le `model_info.mode` et le "
               "groupe d'accès de son usage quand ce n'est pas du chat, et la met en **queue** de la cascade de son routeur "
               "(`Auto-Flash-Lite` pour le texte, celui de son mode pour la voix, la transcription, les "
               "décisions et l'extraction ; aucune cascade pour les embeddings et les types sans routeur), car "
               "une entrée qui a un routeur est dans une cascade. Les "
               "places données plus bas sont des **suggestions, calculées sur le classement actuel, qui est "
               "en cours de révision** : son chiffre est celui d'une seule variante d'effort de "
               "raisonnement, et sa vitesse en jetons par seconde ne dit rien du temps jusqu'à la réponse "
               "d'un modèle qui raisonne. Rien ne les applique. Le commit n'écrit aucune fenêtre de contexte, aucun "
               "catalogue lu ici n'en donnant : une entrée de texte en cascade n'a donc pas de `model_info.max_input_tokens`, "
               "et `check_compose_template.py` la refuse tant qu'une personne ne l'a pas écrit."]
    else:
        out = ["**Brouillon : à ne pas fusionner avant d'avoir fait, pour chaque modèle, les vérifications "
               "listées sous lui.** Ajouts **à vérifier**, proposés **sans IA** par "
               "`.github/workflows/LiteLLM_model_drift.yml`, %s. À chaque modèle ci-dessous, il manque au "
               "moins une information pour l'ajouter sans y réfléchir : sa gratuité, quand l'API de son "
               "fournisseur ne la dit pas, un chiffre du classement d'Artificial Analysis, ou un rapprochement "
               "sûr avec lui (pour un modèle qui n'est pas du chat : une route que le fichier sert déjà chez ce "
               "fournisseur). Ce qui manque est dit sous chacun, avec la façon de l'obtenir. Les modèles dont "
               "l'exécution sait tout sont dans une pull request à part, prête à relire%s." % (
                   run, " (branche %s)" % code_span(other) if other else ""),
               "",
               "Le commit ajoute chaque entrée après la dernière entrée de son fournisseur du même usage (de chat, "
               "à défaut), sous un commentaire qui dit d'où elle vient et quand, avec le `model_info.mode` et le "
               "groupe d'accès de son usage quand ce n'est pas du chat. L'entrée est active, sauf chez un fournisseur "
               "dont le fichier n'a aucune entrée active : elle suit alors, commentée, sa dernière entrée "
               "commentée, avec une raison provisoire. Elle est mise en **queue** de la cascade de son routeur (celle de "
               "`Auto-Flash-Lite` pour le texte, de son mode pour la voix, la transcription, les décisions et "
               "l'extraction), la place sûre ; les types sans routeur et les embeddings n'ont aucune cascade. Les "
               "places données plus bas, quand elles se calculent, sont des suggestions. Le commit n'écrit aucune "
               "fenêtre de contexte, aucun catalogue lu ici n'en donnant : une entrée de texte en cascade n'a donc pas "
               "de `model_info.max_input_tokens`, et `check_compose_template.py` la refuse tant qu'une personne ne "
               "l'a pas écrit."]
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
        usage = finding["usage"]
        anchor = anchors.setdefault((provider, usage), addition_anchor(entries, provider, usage))
        item = dict({"provider": provider, "id": identifier, "name": name},
                    **({"usage": usage} if entry_usage(usage) != CHAT else {}))
        block = addition_block(kind, date, item, anchor)[1:]
        full = "%s/%s" % (provider, identifier)
        out += ["### %s → %s" % (code_span(litellm_id(provider, identifier)[0], 220), code_span(name)), ""]
        if finding.get("label"):
            # Groq's catalogue names no model, only who owns it, which is what its label holds.
            out += ["%s chez %s : %s." % ("Propriétaire" if provider == "groq" else "Nom",
                                         PROVIDER_LABELS[provider], code_span(finding["label"])), ""]
        out += ["Entrée %s par le commit :" % ("commentée ajoutée" if anchor["commented"] else "ajoutée"), ""]
        out += yaml_fence(block) + [""]
        out += [slot_sentence(provider, usage, name, anchor["commented"]), ""]
        placing, unmeasured = placing_lines(result, provider, identifier, usage)
        if usage in USAGE_MODES:
            out.append("Usage : `%s`, `model_info.mode: %s`, groupe d'accès `%s`." % (
                usage, USAGE_MODES[usage], addition_group(provider, usage)))
            out.append("")
        elif usage != CHAT:
            out += ["Usage : `%s`, écrit comme une entrée de chat, LiteLLM le servant par sa route de chat." % usage, ""]
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
                "  " + catalogue_command(provider, identifier, anchor["variable"]),
                "  ```",
                ""]
        for what, _ in missing:
            if what in MISSING_HOWTO:
                out.append("- [ ] **%s.** %s." % (
                    {"ranking": "Classement", "match": "Rapprochement", "figures": "Chiffres",
                     "route": "Route", "kind": "Type"}[what], MISSING_HOWTO[what][0].upper() + MISSING_HOWTO[what][1:]))
        if any(what in ("route", "kind") for what, _ in missing):
            reason = ("no route for %s in LiteLLM under this prefix" if any(what == "route" for what, _ in missing)
                      else "the gateway has no router or client for %s models") % usage
            out += ["", "  Pour l'écarter, la ligne est :", ""]
            out += yaml_fence(["  # drift-ignore: %s -- %s (read %s)" % (full, reason, date)], "  ")
            out.append("")
        if usage == "embeddings":
            out += ["- " + line for line in placing]
        else:
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
    out += list(carried)
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
            "ligne ne change pas). Une exécution qui ne change que les dates des commentaires ne pousse rien : "
            "chaque entrée garde le jour où elle a été proposée. Un modèle fusionné, ou écarté par sa ligne "
            "`drift-ignore`, n'y revient plus ; un modèle à qui il manquait une information passe dans la "
            "pull request des modèles prêts à l'exécution qui l'a. Un commit d'une personne sur la "
            "branche la fige : tant que la pull request est ouverte, le workflow n'y touche plus, ni pour "
            "l'enrichir ni pour la fermer ; une fois qu'elle est fermée sans être fusionnée, son exécution "
            "échoue chaque jour jusqu'à ce que la branche soit supprimée. Elle se ferme quand plus rien "
            "n'est à proposer, à condition que l'exécution ait lu chacune des sources dont elle dépend%s." % (
                "" if ready else " et qu'elle reste en brouillon tant qu'une personne ne la passe pas "
                "« Ready for review » (là où le dépôt refuse les brouillons, elle est ouverte prête à "
                "relire, et ce corps seul dit d'attendre)"),
            "", PROPOSAL_SIGNATURE]
    return "\n".join(out)


def render_additions_commit(result, kind, chosen):
    """The commit that carries the proposed entries, in English like every commit here."""
    identifiers = ", ".join(addition_model(report["name"], finding["id"], entry_usage(finding["usage"]))
                            for report, finding, _ in chosen)
    count = count_phrase(len(chosen), "model", "models")
    if kind == "ready":
        subject = "Propose the new LiteLLM models the drift check knows everything of (#346)"
        found = ("The drift check found on %s %s the model list does not know and of which it holds "
                 "every fact an addition needs: a free tier its provider's API states, and, for a chat model, a "
                 "figure of the Artificial Analysis ranking matched for certain, or, for any other usage, a route "
                 "the file already serves through the provider: %s. Each is added after the last "
                 "entry of its provider of the same usage, modelled on it, with the mode and the access group "
                 "of its usage, under a comment citing the catalogue and the day, "
                 "at the tail of its router's cascade: the places the pull request suggests are computed on a ranking that is "
                 "under revision." % (result["date"], count, identifiers))
    else:
        subject = "Propose the new LiteLLM models a person has to check before adding (#346)"
        found = ("The drift check found on %s %s the model list does not know and of which at least "
                 "one fact an addition needs is missing (a free tier the provider's API does not state, a "
                 "figure of the ranking, a certain match with it, or, for a model that is no chat one, a route "
                 "the file serves through the provider): %s. Each is added after the last "
                 "entry of its provider of the same usage, modelled on it, at the tail of its router's cascade, and the draft pull request says what "
                 "is missing for each and how to get it." % (result["date"], count, identifiers))
    return subject + "\n\n" + wrapped(found) + "\n\n" + wrapped("Nothing merges it but a person.") + "\n"


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
    parser.add_argument("--summary", metavar="PATH",
                        help="with --online, write the whole report (French) to PATH, for the run's "
                             "summary")
    parser.add_argument("--unreadable", metavar="PATH",
                        help="with --online, write to PATH one line \"<provider> <class>\" per "
                             "catalogue that could not be read, the class being that of its HTTP "
                             "status, \"network\" or \"answer\"; no file when the model list "
                             "itself could not be read")
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
                        help="with --online, propose the NEW models in two pull requests, and write "
                             "to DIR what the workflow keeps them with: "
                             "proposals.json, and for each pull request with something to propose its "
                             "body, its commit message and the file with the entries added")
    parser.add_argument("--scores", metavar="PATH",
                        help="with --online, the file of the figures the catalogue shows (Artificial Analysis "
                             "and Epoch AI, per entry): it is read as the figures of the run before, rewritten "
                             "in place when --apply deleted something, and written for each pull request of "
                             "additions beside its template, as \"<kind>_scores.json\"")
    parser.add_argument("--config", metavar="PATH", default=str(CONFIG),
                        help="the LiteLLM configuration to read (default: %(default)s)")
    parser.add_argument("--contracts", metavar="PATH",
                        help="the router contracts to read, by default the repository's own when "
                             "--config is the repository's template, and none for another one")
    arguments = parser.parse_args(argv)

    if arguments.selftest:
        # Imported here: nothing else of this script needs the cases, or the modules they use.
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import check_LiteLLM_model_drift_selftest
        return check_LiteLLM_model_drift_selftest.run_selftest()
    if (arguments.summary or arguments.coverage or arguments.undeleted or arguments.proposals
            or arguments.unreadable or arguments.scores) and not arguments.online:
        parser.error("--summary, --coverage, --undeleted, --proposals, --unreadable and --scores need --online")
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
    scores = scores_writer(arguments, contracts_file, result, today)
    if arguments.apply and not result["unreadable"]:
        new_text = apply_to_result(text, result)
        if new_text != text:
            path.write_bytes(new_text.encode("utf-8"))
            # The figures follow the template in the same pull request, and lose those of the entries it lost.
            written = scores(new_text) if scores else None
            if written is not None:
                Path(arguments.scores).write_bytes(written.encode("utf-8"))
    if arguments.proposals:
        # Made on the file as main has it, whatever was deleted: the additions are pull requests of
        # their own, built on main.
        write_proposals(arguments.proposals, propose_additions(text, result, run_link()), today, scores)
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
    if arguments.unreadable:
        # No file is no answer: the workflow neither tries again nor opens or closes its issue over a
        # model list it could not read.
        Path(arguments.unreadable).unlink(missing_ok=True)
        unread = unreadable_providers(result)
        if unread is not None:
            Path(arguments.unreadable).write_text(
                "".join("%s %s\n" % pair for pair in unread), encoding="utf-8")
    if arguments.summary:
        Path(arguments.summary).write_text(render_summary(result, shown, link=run_link()),
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


def scores_writer(arguments, contracts_file, result, today):
    """A function of the text of a template that returns the figures file for it, or None where there is nothing to
    write them from: no "--scores", no contracts, a model list that could not be read or contracts that are not
    well formed. What the file held before the run is read once, here, since the deletion rewrites it before the
    proposals are made."""
    if not arguments.scores or contracts_file is None or result["unreadable"]:
        return None
    contracts, problems = load_contracts(contracts_file)
    if problems or not isinstance(contracts, dict):
        return None
    previous = previous_scores(arguments.scores)
    return lambda body: scores_text(body, contracts, result.get("rankings"), result.get("epoch"), previous, today)


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
