#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77 and the AI Docker stack Ansible deployment contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Write "docs/CATALOG.md", the overview of everything the LiteLLM gateway serves, and refuse a stale copy.

WHY THIS SCRIPT EXISTS
----------------------
What the gateway serves is spread over three places: the model list and the cascades in
"templates/LiteLLM_config.yaml.j2", the access groups that "check_compose_template.py" holds each entry to, and the
router contracts in ".github/LiteLLM_router_contracts.yaml". A person who wants the picture, which groups exist,
which routers there are and what is in them, which provider holds which entries, has to read all three. An
overview written by hand is true on the day it is written and false the day after a model is added, which is what
"ROUTAGE.md" accepts for the reasons it gives. This one is generated, so that it cannot drift: the CI refuses a copy
that is not what the sources produce.

WHAT IT WRITES
--------------
The template, rendered the way "check_LiteLLM_model_drift.py" renders it (every provider key given, by Jinja2 alone),
the contracts file, read with the same loader, and the figures file "docs/catalog_scores.json" (below), in four
sections:

1. The access groups and the LiteLLM types: the table "check_compose_template.py" reads ("LITELLM_ACCESS_GROUPS" and
   "LITELLM_KEPT_APART_GROUPS"), and any other group found on an entry, which is a group in addition to the one of
   its type, one row for each type group it sits on.
2. The routers: each one's cascade, "router_settings.fallbacks", in order; its head, "model_group_alias";
   its purpose, the first sentence of the comment that opens its cascade in the template, cut at its first colon; the ranking, the last
   resort members, the quota it shares and what it requires, from the contracts; the entry that picks a router by
   the complexity of the request, and the fallbacks of entries called by name.
3. The providers: a badge in the colour of the provider's logo (GitHub strips colour from Markdown, so the colour is
   in a picture of the badge service, once in the table and once at the head of the provider's section, and never
   on a row of a model, where hundreds of pictures would slow the page), the key variable (or none) and the routers
   it appears in. Its free limits are in "ROUTAGE.md", whose table is linked and not copied; "--check" holds its
   heading to be there.
4. The models: one row per entry of the model list with its provider, type, groups, routers, the level of
   reasoning (the static "reasoning_effort" of the template, else the level the contracts say the provider calls it
   at), the context window, the longest answer and the "rpm", "tpm" and "rpd" the template sets, and then the scores
   of each entry, with the record of Artificial Analysis and the model of Epoch AI the contracts map it to.

THE FIGURES FILE
----------------
The CI cannot read Artificial Analysis or Epoch AI, so the figures of the scores live in "docs/catalog_scores.json":
the day each source was read, and for each entry the figures it gave, the intelligence index and the time to the
first answer token of the record the entry is mapped to, at the level it is called at, the capabilities index of its
model and its code position. The weekly drift run, which reads both sources online, rewrites the file and
regenerates the catalogue in every pull request it opens. This script reads the file, and "--check" holds it to its
shape ("check_LiteLLM_model_drift.py", "scores_problems"): nothing but numbers, each within the bounds no real
figure leaves, for the entries that are in the template, with days that are days, written the one way the drift run
writes it. A figure outside that is a refusal, not a rendering: what a reader of those sites could be made to put in
the file steers no routing and says nothing.

WHAT IT DELIBERATELY DOES NOT WRITE
-----------------------------------
No figure no source holds: a dash. No offer or quota prose of its own, since "ROUTAGE.md" keeps the free limits of the
providers with the page read and its day. Nothing is dated by the day it was generated, so that the same sources give
the same bytes on any day: the only days in the file are those of the figures file.

A row is one fact about one thing and no count, no total and no number of rank is written, so that an entry that goes
takes its rows and nothing else of the file changes; the order of a cascade is the order of its rows, and "ROUTAGE.md"
keeps the ranks. Nothing relies on that any more, since the gate that merges the deletion pull request lets the catalogue
change by whatever lines and trusts the check below instead, but a deletion that only removes lines is a diff a person
reads in a minute.

WHY THE CHECK COMPARES BYTES
----------------------------
"--check" regenerates the file in memory and compares it with the committed one, and refuses any difference, a
hand edit included: a copy that is edited by hand is a copy a regeneration silently reverts. A change to the template,
to the contracts file or to the figures file therefore regenerates the catalogue in the same commit, and so do the pull
requests of the drift workflow: its job that reads the providers' catalogues runs this script, with a template, a
figures file and an output file of its own, on the template it edited and on each one it proposes, and the job that
writes commits the three together. That is also what lets the deletion pull request merge by itself with a catalogue and
a figures file that were rewritten: the check proves the first is what the other two produce.

Its verification cases are Python literals rather than fixture files, for the reason CLAUDE.md gives: a fixture on
disk is reachable by "ansible-lint --fix". Run it from the repository root:

    python3 .github/scripts/generate_catalog.py              # writes docs/CATALOG.md
    python3 .github/scripts/generate_catalog.py --check      # exits 1 when the committed file is stale
    python3 .github/scripts/generate_catalog.py --selftest
    python3 .github/scripts/generate_catalog.py --template FILE --scores FILE --output FILE   # others than the repository's
"""

import collections
import difflib
import os
import re
import sys
import urllib.parse
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_compose_template as compose  # noqa: E402  (the table that maps a type to its group)
import check_LiteLLM_model_drift as drift  # noqa: E402  (the one place that knows how to render the template)

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = drift.CONFIG
CONTRACTS = drift.CONTRACTS
CATALOG = ROOT / "docs" / "CATALOG.md"
COMMAND = "python3 .github/scripts/generate_catalog.py"

TITLE = "Catalogue de la passerelle LiteLLM"
SECTION_GROUPS = "Les groupes d'accès et les types de LiteLLM"
SECTION_ROUTERS = "Les routeurs"
SECTION_PROVIDERS = "Les fournisseurs"
SECTION_MODELS = "Les modèles"
NAMED_FALLBACKS = "Les entrées qui ont un repli"
SCORES_TITLE = "Les scores d'Artificial Analysis et d'Epoch AI"
# Where the free limits of every provider are written once, with the page read and its day: the catalogue links to
# it and keeps no copy. "--check" holds the heading to be there, so that the link cannot die unseen.
LIMITS_FILE = "ROUTAGE.md"
LIMITS_HEADING = "Les limites gratuites des fournisseurs"
LIMITS_LINK = "../%s#%s" % (LIMITS_FILE, "les-limites-gratuites-des-fournisseurs")
SCORES = drift.SCORES
NO_VALUE = "—"
# What an entry that calls no provider is shown as: the entry that picks a router.
GATEWAY = "LiteLLM"
# The narrow no-break space French groups digits with, which keeps a figure on one line.
THOUSANDS = "\u202f"

# The colour of each provider's badge, in the providers table and at the head of its section: the main colour of the
# fill of its official logo, read on 2026-11-24 from the file named after it. Where the logo is a raster file, the
# colour is the dominant pixel of the file, which says so. A provider whose logo has no main colour, and one this
# table does not know, is given the neutral grey: a badge that is grey says "no colour was found", not a colour.
NEUTRAL = "808080"
PROVIDER_COLOURS = {
    # The base stop of the gradient of the sparkle, "stop-color", in
    # www.gstatic.com/lamda/images/gemini_sparkle_aurora_33f86dc0c0257da337c63.svg, the logo gemini.google.com serves.
    "Gemini": "3186FF",
    # The widest of the five bands of the logo, "fill" of the rectangle that is 118 wide, in mistral.ai/favicon.svg.
    "Mistral": "FA500F",
    # The fill of the square behind the bolt, in groq.com/favicon.svg.
    "Groq": "F43E01",
    # The fill of the "Grape" glyph, the colourway of the primary lockup of the brand page, in
    # openrouter.ai/brand/logos/transparent/glyph/svg/glyph-grape.svg.
    "OpenRouter": "7624F4",
    # The fill of the whale, in api-docs.deepseek.com/img/favicon.svg.
    "DeepSeek": "4D6BFE",
    # The fill of the large cloud, ".st2", in www.cloudflare.com/img/logo-web-badges/cf-logo-on-white-bg.svg.
    "Cloudflare": "F48220",
    # No colour: the logo, z-cdn.chatglm.cn/z-ai/static/logo.svg, is an illustration of many greys and blues with no
    # fill that is the main one.
    "Zai": NEUTRAL,
    # The dominant pixel of the favicon, www.requesty.ai/icon.png: the site serves no SVG of its logo.
    "Requesty": "1677FF",
    # The fill of the eye, in the logo drawn inline on www.nvidia.com/en-us/about-nvidia/legal-info/logo-brand-usage/.
    "NVIDIA": "76B900",
    # The fill of the coin, in cent-ai.dev/favicon.svg.
    "Cent_AI": "FBBF24",
    # The dominant pixel of the logo, aionlabs.ai/static/images/logos/aion-logo.f40cfec9b77a.png, a dark navy: the site
    # serves only a one-colour black mask as an SVG.
    "Aion_Labs": "061929",
    # The fill of the square behind the mark, in kilo.ai/favicon/favicon.svg.
    "Kilo": "FFDD00",
    # The fill of the mark, "cls-1", in www.ovhcloud.com/icon.svg.
    "OVHcloud": "000E9C",
    # The first stop of the gradient of the square, in public/favicon.svg of the project's repository,
    # raw.githubusercontent.com/diegosouzapw/OmniRoute/main/public/favicon.svg.
    "OmniRoute": "E54D5E",
}

# The header of the generated file. REUSE reads this script too and would take the lines below for its own licence
# expression, which the "\n" that ends one makes invalid, so they sit between the markers it provides.
# REUSE-IgnoreStart
SPDX_HEADER = (
    "<!--\n"
    "SPDX-FileCopyrightText: 2026 Tigerblue77 and the AI Docker stack Ansible deployment contributors\n"
    "SPDX-License-Identifier: AGPL-3.0-only\n"
    "-->\n"
)
# REUSE-IgnoreEnd

# What each "model_info.mode" is for. A mode this table does not know is shown with no usage rather than refused,
# so that LiteLLM growing a mode never stops a deletion that has nothing to do with it.
MODE_USAGES = {
    None: "Texte : conversation et complétion",
    "audio_transcription": "Transcription de la parole (`/audio/transcriptions`)",
    "audio_speech": "Synthèse vocale (`/audio/speech`)",
    "embedding": "Vecteurs d'un texte (`/embeddings`)",
    "evaluation": "Décisions typées",
    "extraction": "Extraction typée",
    "image_generation": "Génération d'images (`/images/generations`)",
    "video_generation": "Génération de vidéos (`/videos`)",
    "rerank": "Reclassement de documents (`/rerank`)",
    "moderation": "Modération de contenu (`/moderations`)",
    "ocr": "Lecture du texte d'une image ou d'un PDF (`/ocr`)",
}
# How the contracts name what a router is ranked on, and what it requires of a member.
CRITERIA = {
    "intelligence": "indice d'intelligence",
    "intelligence_for_time": "indice d'intelligence, moins le temps jusqu'au premier jeton de la réponse",
    "code_quality": "position dans les benchmarks de code",
}
REQUIREMENTS = {"tools": "les appels d'outils"}

HEADING = re.compile(r"^\s*#\s*\d+\.\s+(?P<name>[A-Z][A-Z-]*)\s+--\s+(?P<text>.*?)\s*$")
CONTINUATION = re.compile(r"^\s*#\s+(?P<text>\S.*?)\s*$")
SENTENCE_END = re.compile(r"\.(?:\s|$)")


# ------------------------------------------------------------------------------------------------
# What the sources say
# ------------------------------------------------------------------------------------------------

def purposes(template_text):
    """{router short id: first sentence of the comment that opens its cascade}, read off the raw template: "# 1.
    PRO -- pure reasoning, multi-step logic, architecture." gives "pro". The comment is in English, as the template
    is, and is quoted as written."""
    lines = template_text.splitlines()
    found = {}
    for number, line in enumerate(lines):
        heading = HEADING.match(line)
        if not heading:
            continue
        text = heading.group("text")
        following = number + 1
        while (not SENTENCE_END.search(text) and following < len(lines) and not HEADING.match(lines[following])
               and CONTINUATION.match(lines[following])):
            text += " " + CONTINUATION.match(lines[following]).group("text")
            following += 1
        # Cut at the first colon too: what follows it explains the purpose and does not fit a table cell.
        sentence = SENTENCE_END.split(text, 1)[0].split(": ", 1)[0].strip()
        if sentence:
            found[heading.group("name").lower()] = sentence[0].upper() + sentence[1:]
    return found


def provider_of(entry):
    """The provider of an entry of the model list: the name of its key in the role ("Gemini", "Cent_AI"), the name of
    a keyless gateway ("Kilo", "OVHcloud", "OmniRoute"), or None for the entry that calls no provider."""
    parameters = entry.get("litellm_params") if isinstance(entry.get("litellm_params"), dict) else {}
    key, base = parameters.get("api_key"), parameters.get("api_base")
    if isinstance(key, str) and key.startswith("os.environ/"):
        variable = key[len("os.environ/"):]
        for name, environment in compose.LITELLM_PROVIDERS.items():
            if environment == variable:
                return name
        return variable
    if isinstance(base, str):
        for name, address in compose.LITELLM_KEYLESS_BASES.items():
            if base.startswith(address):
                return name
        if drift.OMNIROUTE_BASE.match(base):
            return "OmniRoute"
    return None


def provider_label(name):
    return GATEWAY if name is None else name.replace("_", " ")


def key_variable(name):
    return "Artificial_Intelligence_LiteLLM_%s_API_key" % name if name in compose.LITELLM_PROVIDERS else None


def mode_of(entry):
    info = entry.get("model_info") if isinstance(entry.get("model_info"), dict) else {}
    return info.get("mode")


def groups_of(entry):
    info = entry.get("model_info") if isinstance(entry.get("model_info"), dict) else {}
    groups = info.get("access_groups")
    return [group for group in groups if isinstance(group, str)] if isinstance(groups, list) else []


def type_group_of(entry):
    """The group of the entry's type, which is the one "check_compose_template.py" holds it to."""
    parameters = entry.get("litellm_params") if isinstance(entry.get("litellm_params"), dict) else {}
    return compose.litellm_access_group(mode_of(entry), parameters.get("api_key"))


def level_of(entry, contract_entry):
    """What the entry is called at: the static level the template sets, else the one the contracts say the provider
    calls it at, else nothing."""
    parameters = entry.get("litellm_params") if isinstance(entry.get("litellm_params"), dict) else {}
    static = parameters.get("reasoning_effort")
    if isinstance(static, str):
        return "`%s`" % static
    level = contract_entry.get("level") if isinstance(contract_entry, dict) else None
    if isinstance(level, str) and level not in (drift.LEVEL_UNKNOWN, drift.LEVEL_NOT_APPLICABLE):
        return "défaut : %s" % level
    return NO_VALUE


def cascades(document):
    """{router public name or entry name: [members]} of "router_settings.fallbacks", in the order written."""
    settings = document.get("router_settings") if isinstance(document.get("router_settings"), dict) else {}
    found = {}
    for mapping in settings.get("fallbacks") or []:
        if isinstance(mapping, dict):
            for name, members in mapping.items():
                found[name] = [member for member in (members or []) if isinstance(member, str)]
    return found


def aliases(document):
    settings = document.get("router_settings") if isinstance(document.get("router_settings"), dict) else {}
    value = settings.get("model_group_alias")
    return value if isinstance(value, dict) else {}


# ------------------------------------------------------------------------------------------------
# Writing it
# ------------------------------------------------------------------------------------------------

def slug(title):
    """The anchor GitHub gives a heading: lower case, anything but a word character, a hyphen or a space dropped,
    the spaces turned into hyphens."""
    return re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(cell(value) for value in row) + " |" for row in rows]
    return "\n".join(lines)


def number(value):
    if not compose.positive_int(value):
        return NO_VALUE
    return "{:,}".format(value).replace(",", THOUSANDS)


def decimal(value):
    """A figure of the scores as French writes it: at most the two decimals the file keeps, a comma."""
    return "{:g}".format(value).replace(".", ",")


def badge(name):
    """The badge of a provider, a picture of its name in the colour of its logo. GitHub strips colour from Markdown, so
    the colour is in the picture. A name is escaped the way the badge service reads one: "-" and "_" are doubled."""
    label = provider_label(name)
    escaped = urllib.parse.quote(label.replace("-", "--").replace("_", "__"), safe="")
    return "![%s](https://img.shields.io/badge/%s-%s)" % (label, escaped, PROVIDER_COLOURS.get(name, NEUTRAL))


def provider_name(entry):
    """The name a provider is shown under in a row: its badge and its name."""
    return "%s %s" % (badge(entry), provider_label(entry))


def code_list(names):
    return ", ".join("`%s`" % name for name in names)


def section(title, body, top):
    return "## %s\n\n%s\n\n[↑ Retour en haut](#%s)\n" % (title, body.strip("\n"), top)


def groups_section(entries):
    type_groups = collections.OrderedDict()
    type_groups[compose.litellm_access_group(None)] = (None, "")
    for mode, group in compose.LITELLM_ACCESS_GROUPS.items():
        type_groups[group] = (mode, "")
    for variable, group in compose.LITELLM_KEPT_APART_GROUPS.items():
        provider = next((name for name, environment in compose.LITELLM_PROVIDERS.items() if environment == variable),
                        variable)
        type_groups[group] = (None, "mis à part : seules les entrées qui lisent la clé de %s en font partie, et "
                                    "aucune clé qui n'a que `%s` ne les atteint"
                              % (provider_label(provider), compose.litellm_access_group(None)))
    rows = []
    for group, (mode, note) in type_groups.items():
        rows.append((
            "`%s`" % group,
            "chat (aucun `mode`)" if mode is None else "`%s`" % mode,
            MODE_USAGES.get(mode, NO_VALUE),
            note or NO_VALUE,
        ))
    text = (
        "Chaque entrée est dans le groupe de son type, ce qui permet de limiter une clé virtuelle à un type de "
        "modèles dans l'interface de LiteLLM. Les groupes sont des étiquettes que ce dépôt pose sur les entrées "
        "(`model_info.access_groups`), alors que le type est le `model_info.mode` de LiteLLM, un ensemble borné : "
        "une entrée sans `mode` est un modèle de conversation. Un routeur suit sa tête : une clé qui atteint "
        "l'entrée atteint les routeurs dont elle est la tête.\n\n"
        + table(("Groupe", "Type LiteLLM", "Usage", "Remarque"), rows)
    )
    extra = collections.OrderedDict()
    for entry in entries:
        for group in groups_of(entry):
            if group not in type_groups:
                extra.setdefault(group, []).append(entry)
    extra_rows = [("`%s`" % group, "`%s`" % type_group)
                  for group, members in extra.items() for type_group in sorted({type_group_of(member) for member in members})]
    text += (
        "\n\nCes groupes s'ajoutent au groupe du type : une entrée qui en porte un est aussi dans celui de son "
        "type, et la ligne dit sur quel groupe de type il se trouve.\n\n"
        + table(("Groupe supplémentaire", "Groupe de type"), extra_rows)
    )
    return text


def router_facts(short, contract_routers, public_names):
    """The bullets of one router that its contract gives, as (label, text) pairs."""
    contract = contract_routers.get(short) if isinstance(contract_routers.get(short), dict) else {}
    facts = []
    ranking = contract.get("ranking") if isinstance(contract.get("ranking"), dict) else {}
    if contract.get("derives_from"):
        facts.append(("Dérive de", "`%s`, ordonné de la même façon, sans les membres qui ne répondent pas aux "
                      "exigences ci-dessous"
                      % public_names.get(contract["derives_from"], contract["derives_from"])))
    if ranking.get("criterion"):
        facts.append(("Classement", CRITERIA.get(ranking["criterion"], ranking["criterion"])))
    requires = contract.get("requires")
    if isinstance(requires, list) and requires:
        facts.append(("Exige des membres", ", ".join(REQUIREMENTS.get(item, str(item)) for item in requires)))
    shared = ranking.get("shared_quota_with")
    if isinstance(shared, list) and shared:
        facts.append(("Quota partagé avec", code_list(public_names.get(item, item) for item in shared)
                      + " : un membre qui est le même modèle chez le même fournisseur que l'un de leurs membres "
                      "passe en dernier"))
    last_resort = contract.get("last_resort") if isinstance(contract.get("last_resort"), dict) else {}
    if isinstance(last_resort.get("members"), list) and last_resort["members"]:
        facts.append(("Derniers recours", code_list(last_resort["members"])))
    return facts, set(last_resort.get("members") or [])


def routers_section(document, entries, contracts, purpose_of):
    by_name = {entry.get("model_name"): entry for entry in entries}
    contract_models = contracts.get("models") if isinstance(contracts.get("models"), dict) else {}
    contract_routers = contracts.get("routers") if isinstance(contracts.get("routers"), dict) else {}
    lists = cascades(document)
    heads = aliases(document)
    public_names = drift.ROUTER_PUBLIC_NAMES
    routers = [(short, public) for short, public in public_names.items() if public in lists]
    tier_entries = [entry for entry in entries
                    if (entry.get("litellm_params") or {}).get("model") == compose.LITELLM_TIER_ROUTER_MODEL]

    summary = []
    for entry in tier_entries:
        tiers = ((entry.get("litellm_params") or {}).get("complexity_router_config") or {}).get("tiers") or {}
        picked = list(collections.OrderedDict.fromkeys(tiers.values()))
        summary.append(("`%s`" % entry["model_name"],
                        "Aiguille chaque requête vers %s selon sa complexité" % code_list(picked),
                        NO_VALUE))
    for short, public in routers:
        summary.append(("`%s`" % public, purpose_of.get(short, NO_VALUE),
                        "`%s`" % heads[public] if public in heads else NO_VALUE))
    text = (
        "Un routeur est un nom que le client écrit et derrière lequel LiteLLM essaie les membres de sa cascade dans "
        "l'ordre, en passant au suivant quand un membre échoue. Les cascades ci-dessous sont celles du modèle rendu "
        "avec la clé de tous les fournisseurs : sans la clé d'un fournisseur, ses entrées disparaissent et l'ordre "
        "des autres ne change pas. Le rôle d'un routeur est la première phrase du commentaire qui ouvre sa cascade "
        "dans le modèle, en anglais comme lui ; le reste vient des contrats des routeurs. Les membres d'une cascade sont "
        "dans l'ordre de ses lignes, le premier d'abord.\n\n"
        + table(("Routeur", "Rôle", "Tête"), summary)
    )
    subsections = []
    for entry in tier_entries:
        tiers = ((entry.get("litellm_params") or {}).get("complexity_router_config") or {}).get("tiers") or {}
        rows = [("`%s`" % level, "`%s`" % target) for level, target in tiers.items()]
        subsections.append("### `%s`\n\nCette entrée n'a pas de cascade : le routeur qu'elle choisit a la sienne.\n\n%s"
                           % (entry["model_name"], table(("Complexité de la requête", "Routeur choisi"), rows)))
    for short, public in routers:
        facts, last = router_facts(short, contract_routers, public_names)
        rows = []
        for member in lists[public]:
            found = by_name.get(member) or {}
            rows.append(("`%s`" % member, provider_label(provider_of(found)) if found else NO_VALUE,
                         level_of(found, contract_models.get(member)) if found else NO_VALUE,
                         "dernier recours" if member in last else NO_VALUE))
        bullets = "".join("- %s : %s\n" % fact for fact in facts)
        subsections.append("### `%s`\n\n%s\n%s" % (
            public, bullets, table(("Entrée", "Fournisseur", "Niveau", "Remarque"), rows)))
    named = [(name, members) for name, members in lists.items() if name not in drift.ROUTER_OF_PUBLIC_NAME]
    pairs = [("`%s`" % name, "`%s`" % member) for name, members in named for member in members]
    if pairs:
        rows = pairs
        subsections.append("### %s\n\nUne entrée appelée par son nom, qui n'est la tête d'aucun routeur, et ce que "
                           "LiteLLM essaie quand elle échoue.\n\n%s" % (NAMED_FALLBACKS, table(("Entrée", "Repli"), rows)))
    return text + "\n\n" + "\n\n".join(subsections), [
        entry["model_name"] for entry in tier_entries] + [public for _, public in routers] + (
            [NAMED_FALLBACKS] if pairs else [])


def providers_section(document, entries, contracts):
    lists = cascades(document)
    public_names = drift.ROUTER_PUBLIC_NAMES
    counts = collections.Counter(provider_of(entry) for entry in entries)
    counts.pop(None, None)
    names = [name for name in compose.LITELLM_PROVIDERS if name in counts]
    names += sorted(name for name in counts if name not in compose.LITELLM_PROVIDERS)
    appears = collections.defaultdict(list)
    by_name = {entry.get("model_name"): entry for entry in entries}
    for public in public_names.values():
        for member in lists.get(public, []):
            if provider_of(by_name.get(member) or {}) is not None:
                name = provider_of(by_name[member])
                if public not in appears[name]:
                    appears[name].append(public)
    rows = [(provider_name(name), "`%s`" % key_variable(name) if key_variable(name) else "sans clé") for name in names]
    text = (
        "Un fournisseur est celui que lit l'entrée : la clé dont la variable est donnée, ou une passerelle qui n'en "
        "demande aucune. Un fournisseur dont la clé n'est pas donnée n'a aucune entrée dans la configuration "
        "rendue. La couleur de la pastille est celle du logo du fournisseur, et le générateur dit d'où chacune vient.\n\n"
        "Les limites gratuites de chaque fournisseur, avec la page lue et le jour, sont dans [le tableau de %s](%s), "
        "et ce catalogue n'en garde pas de copie. Celles que le modèle de configuration fixe à une entrée, `rpm`, "
        "`tpm` et `rpd`, sont dans le tableau des modèles.\n\n" % (LIMITS_FILE, LIMITS_LINK)
        + table(("Fournisseur", "Variable de la clé"), rows)
    )
    for name in names:
        text += "\n\n### %s\n\n- Variable de la clé : %s\n- Routeurs où il figure : %s" % (
            provider_name(name), "`%s`" % key_variable(name) if key_variable(name) else "aucune, il est sans clé",
            code_list(appears[name]) or NO_VALUE)
    return text, []


def quota(entry, key):
    parameters = entry.get("litellm_params") if isinstance(entry.get("litellm_params"), dict) else {}
    return number(parameters.get(key))


def scores_section(entries, contracts, scores):
    """The figures of Artificial Analysis and of Epoch AI of each entry the contracts map or the file holds, with the
    record and the model the contracts say they are those of. A dash says that no source gives the figure."""
    contract_models = contracts.get("models") if isinstance(contracts.get("models"), dict) else {}
    figures = scores["entries"]
    rows = []
    for entry in entries:
        name = entry.get("model_name")
        mapping = contract_models.get(name) if isinstance(contract_models.get(name), dict) else {}
        got = figures.get(name, {})
        if not got and not mapping.get("slug") and not isinstance(mapping.get("eci"), str):
            continue
        record = NO_VALUE
        if isinstance(mapping.get("slug"), str):
            level = mapping.get("level")
            record = "`%s`" % mapping["slug"] + (" (`%s`)" % level if isinstance(level, str)
                                                 and level not in (drift.LEVEL_UNKNOWN, drift.LEVEL_NOT_APPLICABLE)
                                                 else "")
        rows.append((
            "`%s`" % name, record,
            decimal(got["aa_index"]) if "aa_index" in got else NO_VALUE,
            decimal(got["aa_first_answer_seconds"]) if "aa_first_answer_seconds" in got else NO_VALUE,
            "`%s`" % mapping["eci"] if isinstance(mapping.get("eci"), str) else NO_VALUE,
            decimal(got["epoch_eci"]) if "epoch_eci" in got else NO_VALUE,
            decimal(got["epoch_code_position"]) if "epoch_code_position" in got else NO_VALUE,
        ))
    read = [(label, scores[key]) for label, key in (("Artificial Analysis", "artificial_analysis_read"),
                                                    ("Epoch AI", "epoch_read"))]
    text = (
        "Les chiffres sont ceux d'Artificial Analysis et d'Epoch AI : l'enregistrement et le niveau d'Artificial "
        "Analysis, et le modèle d'Epoch AI, sont ceux que dit `.github/LiteLLM_router_contracts.yaml` de l'entrée. La "
        "CI ne peut lire aucun de ces deux sites : la vérification hebdomadaire des modèles les lit et réécrit "
        "[`docs/catalog_scores.json`](catalog_scores.json) dans chaque pull request qu'elle ouvre. La CI tient ce "
        "fichier à sa forme (des nombres, et des entrées du modèle de configuration) et ce catalogue à ce fichier. "
        "Jours de lecture : %s. Un tiret veut dire qu'aucune source ne donne le chiffre : l'enregistrement est "
        "introuvable ou n'est pas celui du niveau où l'entrée est appelée, le modèle n'est pas à l'indice d'Epoch AI, "
        "ou moins de deux de ses benchmarks de code ont un score pour lui.\n\n"
        "- **Indice AA** : l'indice d'intelligence de l'enregistrement, plus haut est meilleur.\n"
        "- **Premier mot AA** : le temps moyen jusqu'au premier jeton de la réponse, en secondes, que le temps de "
        "réflexion compte.\n"
        "- **ECI Epoch** : l'indice de capacités du modèle, plus haut est meilleur.\n"
        "- **Position de code Epoch** : la médiane, en pour cent, de la position du modèle dans les benchmarks de "
        "code où il a un score, deux au moins, où 100 est le dernier : plus petit est meilleur.\n\n"
        "Sources : Artificial Analysis (artificialanalysis.ai) et %s.\n\n"
        % (", ".join("%s le %s" % (label, day or "jamais") for label, day in read), drift.EPOCH_ATTRIBUTION)
        + table(("Entrée", "Enregistrement AA", "Indice AA", "Premier mot AA (s)", "Modèle Epoch", "ECI Epoch",
                 "Position de code Epoch (%)"), rows)
    )
    return text


def models_section(document, entries, contracts, scores):
    lists = cascades(document)
    public_names = drift.ROUTER_PUBLIC_NAMES
    contract_models = contracts.get("models") if isinstance(contracts.get("models"), dict) else {}
    placed = collections.defaultdict(list)
    for public in public_names.values():
        for member in lists.get(public, []):
            if public not in placed[member]:
                placed[member].append(public)
    rows = []
    for entry in entries:
        name = entry.get("model_name")
        info = entry.get("model_info") if isinstance(entry.get("model_info"), dict) else {}
        mode = mode_of(entry)
        rows.append((
            "`%s`" % name,
            provider_label(provider_of(entry)),
            "chat" if mode is None else "`%s`" % mode,
            code_list(groups_of(entry)) or NO_VALUE,
            code_list(placed[name]) or NO_VALUE,
            level_of(entry, contract_models.get(name)),
            number(info.get("max_input_tokens")),
            number(info.get("max_output_tokens")),
            quota(entry, "rpm"), quota(entry, "tpm"), quota(entry, "rpd"),
        ))
    text = (
        "Une ligne par entrée de la liste des modèles, dans l'ordre du modèle. La fenêtre de contexte et la réponse "
        "la plus longue sont celles que le fournisseur sert, `model_info.max_input_tokens` et "
        "`model_info.max_output_tokens`. Le niveau est le `reasoning_effort` que le modèle fixe, sinon celui auquel "
        "les contrats disent que le fournisseur appelle l'entrée par défaut. `rpm`, `tpm` et `rpd` sont les limites que "
        "le modèle de configuration pose à l'entrée, `litellm_params.rpm`, `tpm` et `rpd` : des requêtes par minute, "
        "des jetons par minute et des requêtes par jour, que LiteLLM applique à l'entrée. Un tiret veut dire qu'aucune "
        "source ne donne la valeur, ou que le modèle de configuration n'en fixe aucune : les limites d'un fournisseur "
        "entier sont dans [le tableau de %s](%s). Les scores d'Artificial Analysis et d'Epoch AI sont dans la section "
        "qui suit.\n\n" % (LIMITS_FILE, LIMITS_LINK)
        + table(("Entrée", "Fournisseur", "Type", "Groupes", "Routeurs", "Niveau", "Contexte", "Sortie max",
                 "rpm", "tpm", "rpd"), rows)
    )
    return text + "\n\n### %s\n\n%s" % (SCORES_TITLE, scores_section(entries, contracts, scores))


def entry_names(template_text):
    """The names of the entries of the template as rendered, in the order of the model list."""
    document = yaml.safe_load(drift.render_with_keys(template_text, None))
    return [entry.get("model_name") for entry in (document.get("model_list") or []) if isinstance(entry, dict)]


def build(template_text, contracts, scores):
    """The text of the catalogue for this template, these contracts (a mapping, or None for none) and these figures
    (the document of "catalog_scores.json", which holds nothing but numbers for entries of the template)."""
    document = yaml.safe_load(drift.render_with_keys(template_text, None))
    entries = [entry for entry in (document.get("model_list") or []) if isinstance(entry, dict)]
    contracts = contracts if isinstance(contracts, dict) else {}
    purpose_of = purposes(template_text)
    top = slug(TITLE)
    routers_body, router_headings = routers_section(document, entries, contracts, purpose_of)
    providers_body, provider_headings = providers_section(document, entries, contracts)
    sections = [
        (SECTION_GROUPS, groups_section(entries), []),
        (SECTION_ROUTERS, routers_body, router_headings),
        (SECTION_PROVIDERS, providers_body, provider_headings),
        (SECTION_MODELS, models_section(document, entries, contracts, scores), [SCORES_TITLE]),
    ]
    contents = []
    for title, _, subs in sections:
        contents.append("- [%s](#%s)" % (title, slug(title)))
        contents += ["  - [%s](#%s)" % (sub if sub in (NAMED_FALLBACKS, SCORES_TITLE) else "`%s`" % sub, slug(sub))
                     for sub in subs]
    header = (
        SPDX_HEADER + "\n"
        "# %s\n\n"
        "> Ce fichier est généré par `%s` à partir du modèle de configuration de LiteLLM "
        "(`templates/LiteLLM_config.yaml.j2`), des contrats des routeurs "
        "(`.github/LiteLLM_router_contracts.yaml`) et des scores lus en ligne (`docs/catalog_scores.json`). Ne le "
        "modifiez pas à la main : la CI refuse un fichier qui n'est pas ce que ces sources produisent, et un "
        "changement de l'une d'elles le régénère dans le même commit.\n\n"
        "Ce catalogue dit tout ce que la passerelle sert : les groupes d'accès, les routeurs et leurs membres, les "
        "fournisseurs, et chaque modèle, avec ses limites et ses scores. Il décrit la configuration rendue avec la "
        "clé de tous les fournisseurs donnée.\n\n"
        "## Sommaire\n\n%s\n"
    ) % (TITLE, COMMAND, "\n".join(contents))
    return header + "\n" + "\n".join(section(title, body, top) for title, body, _ in sections)


# ------------------------------------------------------------------------------------------------
# The check
# ------------------------------------------------------------------------------------------------

def routage_problem(text):
    """Why the document that holds the free limits of the providers no longer has the heading the catalogue links to,
    or None."""
    if text is None or ("\n## %s\n" % LIMITS_HEADING) not in "\n" + text:
        return "%s has no heading \"%s\", which docs/CATALOG.md links to" % (LIMITS_FILE, LIMITS_HEADING)
    return None


def check(template_text, contracts, scores, committed):
    """(status, message) of a committed catalogue (None when absent) against what the sources produce: 0 when it is
    that, 1 when it is not, 2 when the sources cannot be read. "scores" is the document of the figures file, which
    the caller has already held to its shape."""
    try:
        wanted = build(template_text, contracts, scores)
    except (drift.RenderError, yaml.YAMLError) as error:
        return 2, "The template cannot be read: %s" % error
    if committed is None:
        return 1, "docs/CATALOG.md does not exist. Write it with `%s` and commit it." % COMMAND
    if committed == wanted:
        return 0, ""
    difference = list(difflib.unified_diff(committed.splitlines(), wanted.splitlines(), "docs/CATALOG.md (committed)",
                                           "docs/CATALOG.md (generated)", lineterm="", n=0))
    shown = difference[:14] + (["... (%d more lines)" % (len(difference) - 14)] if len(difference) > 14 else [])
    return 1, ("docs/CATALOG.md is not what the template, the router contracts and the figures produce. It is "
               "generated: run `%s` and commit the result in the same commit as the change.\n\n%s"
               % (COMMAND, "\n".join(shown)))


# ------------------------------------------------------------------------------------------------
# Its own verification
# ------------------------------------------------------------------------------------------------

SELFTEST_TEMPLATE = """\
model_list:
  - model_name: alpha
    model_info: {access_groups: ["LLM"], max_input_tokens: 1048576, max_output_tokens: 65536}
    litellm_params: {model: gemini/alpha, api_key: os.environ/GEMINI_API_KEY, reasoning_effort: high, rpm: 5, tpm: 250000, rpd: 20}
  - model_name: bravo
    model_info: {access_groups: ["LLM", "Claude-Code"], max_input_tokens: 131072}
    litellm_params: {model: openai/bravo, api_base: "https://ai-gateway.kilo.ai/api/v1", api_key: kilo-no-key-needed}
  - model_name: whisper
    model_info: {mode: audio_transcription, access_groups: ["STT"]}
    litellm_params: {model: groq/whisper, api_key: os.environ/GROQ_API_KEY}
  - model_name: tale
    model_info: {access_groups: ["Fiction"], max_input_tokens: 32768}
    litellm_params: {model: openai/tale, api_key: os.environ/AION_LABS_API_KEY}
  - model_name: strange
    model_info: {mode: mystery, access_groups: ["Mystery"]}
    litellm_params: {model: openai/strange, api_key: os.environ/GROQ_API_KEY}
  - model_name: Auto
    model_info: {access_groups: ["LLM"]}
    litellm_params:
      model: auto_router/complexity_router
      complexity_router_config:
        tiers: {SIMPLE: Auto-Pro, COMPLEX: Auto-Pro}
router_settings:
  fallbacks:
    # 1. PRO -- pure reasoning, multi-step logic. Second sentence, which is not kept.
    - Auto-Pro:
        - alpha
        - bravo
    # 7. TTS -- a purpose that
    # runs over two lines: this is not kept. Nor this.
    - Auto-TTS:
        - whisper
    - alpha:
        - bravo
  model_group_alias:
    "Auto-Pro": "alpha"
    "Auto-TTS": "whisper"
"""
SELFTEST_CONTRACTS = {
    "routers": {"pro": {"ranking": {"criterion": "intelligence", "shared_quota_with": ["flash"]},
                        "last_resort": {"members": ["bravo"]}, "requires": ["tools"]}},
    "models": {"bravo": {"level": "medium", "slug": "bravo-medium"},
               "alpha": {"slug": "alpha", "level": "high", "eci": "Alpha 1"}},
}
SELFTEST_SCORES = {"artificial_analysis_read": "2026-11-24", "epoch_read": "2026-11-23",
                   "entries": {"alpha": {"aa_index": 53.9, "aa_first_answer_seconds": 47.4, "epoch_eci": 166.81,
                                         "epoch_code_position": 9.37},
                               "bravo": {"aa_index": 12.5}}}


def scores_verdict(document, names=("alpha", "bravo")):
    """The problems the figures file has when "document" is written the one way a file is, as a string, or None."""
    return "; ".join(drift.scores_file_problems(drift.render_scores(document), names)[1]) or None


def scores_refused(text, names=("alpha", "bravo"), phrase=""):
    """None when the text of a figures file is refused, and says "phrase", or what is wrong when it is not."""
    _, problems = drift.scores_file_problems(text, names)
    if not problems:
        return "the file was accepted"
    return None if phrase in "; ".join(problems) else "refused for another reason: %s" % problems[0]


def selftest_cases():
    """(purpose, a function of the catalogue that returns what is wrong with it, or None)."""
    good = build(SELFTEST_TEMPLATE, SELFTEST_CONTRACTS, SELFTEST_SCORES)
    written = drift.render_scores(SELFTEST_SCORES)

    def expect(text, *phrases):
        missing = [phrase for phrase in phrases if phrase not in text]
        return "missing %r" % missing if missing else None

    def verdict(template, contracts, committed, wanted_status, phrase="", scores=SELFTEST_SCORES):
        status, message = check(template, contracts, scores, committed)
        if status != wanted_status or phrase not in message:
            return "status %d (wanted %d): %s" % (status, wanted_status, message[:200])
        return None

    def with_figure(key, value):
        document = {name: dict(figures) for name, figures in SELFTEST_SCORES["entries"].items()}
        document["alpha"][key] = value
        return dict(SELFTEST_SCORES, entries=document)

    return [
        ("the same sources give the same bytes", lambda: None if build(SELFTEST_TEMPLATE, SELFTEST_CONTRACTS,
                                                                       SELFTEST_SCORES) == good
         and good.endswith("\n") and "\r" not in good else "the output differs between two runs"),
        ("the file starts with its SPDX header and says it is generated, and by which command",
         lambda: expect(good, "généré par `%s`" % COMMAND) if good.startswith(SPDX_HEADER + "\n# ")
         else "no SPDX header at the top"),
        ("a table of contents and a way back to the top after each section",
         lambda: expect(good, "- [Les routeurs](#les-routeurs)", "  - [`Auto-Pro`](#auto-pro)",
                        "  - [Les scores d'Artificial Analysis et d'Epoch AI](#les-scores-dartificial-analysis-et-depoch-ai)",
                        "[↑ Retour en haut](#catalogue-de-la-passerelle-litellm)")
         if good.count("[↑ Retour en haut]") == 4 else "not one way back to the top per section"),
        ("the groups come from the code that maps a mode to its group, the kept apart one included",
         lambda: expect(good, "| `LLM` | chat (aucun `mode`) |", "| `STT` | `audio_transcription` |",
                        "| `Decisions` | `evaluation` |", "| `Fiction` | chat (aucun `mode`) |", "clé de Aion Labs")),
        ("a group in addition to the type group is listed as such, with the types it sits on",
         lambda: expect(good, "| Groupe supplémentaire | Groupe de type |", "| `Claude-Code` | `LLM` |")),
        ("a router has its head, its purpose (the first sentence of its comment), its ranking and its last resort",
         lambda: expect(good, "| `Auto-Pro` | Pure reasoning, multi-step logic | `alpha` |",
                        "- Classement : indice d'intelligence", "- Derniers recours : `bravo`",
                        "- Exige des membres : les appels d'outils", "- Quota partagé avec : `Auto-Flash`")),
        ("a comment over two lines gives its first sentence whole",
         lambda: None if purposes(SELFTEST_TEMPLATE).get("tts") == "A purpose that runs over two lines"
         else "got %r" % purposes(SELFTEST_TEMPLATE).get("tts")),
        ("the members of a cascade come in order with their level and last resort, and no rank",
         lambda: expect(good, "| `alpha` | Gemini | `high` | — |\n| `bravo` | Kilo | défaut : medium | dernier recours |")),
        ("the entry that picks a router lists what each complexity goes to",
         lambda: expect(good, "| `SIMPLE` | `Auto-Pro` |", "Aiguille chaque requête vers `Auto-Pro`")),
        ("an entry called by name with a fallback is listed",
         lambda: expect(good, "| `alpha` | `bravo` |")),
        ("a provider has its key variable, or none, a section of its own and the routers it is in",
         lambda: expect(good, "| %s | `Artificial_Intelligence_LiteLLM_Gemini_API_key` |" % provider_name("Gemini"),
                        "| %s | sans clé |" % provider_name("Kilo"), "### %s\n\n- Variable de la clé : `Arti" % provider_name("Gemini"),
                        "- Routeurs où il figure : `Auto-Pro`")),
        ("a provider is a badge in the colour of its logo, escaped the way the badge service reads a name",
         lambda: expect(good, "![Gemini](https://img.shields.io/badge/Gemini-3186FF)",
                        "![Kilo](https://img.shields.io/badge/Kilo-FFDD00)")
         or expect(badge("Aion_Labs"), "https://img.shields.io/badge/Aion%20Labs-061929")
         or expect(badge("Somebody-New"), "/badge/Somebody--New-%s)" % NEUTRAL)),
        ("every provider the compose check knows has a colour, in six hexadecimal digits, or is grey on purpose",
         lambda: next((name for name in list(compose.LITELLM_PROVIDERS) + list(compose.LITELLM_KEYLESS_BASES) + ["OmniRoute"]
                       if not re.fullmatch(r"[0-9A-F]{6}", PROVIDER_COLOURS.get(name, ""))), None)),
        ("the limits of the providers are a link and no copy, and the quotas of an entry are columns",
         lambda: expect(good, "[le tableau de ROUTAGE.md](../ROUTAGE.md#les-limites-gratuites-des-fournisseurs)",
                        "| rpm | tpm | rpd |", "| 5 | 250\u202f000 | 20 |") if "a declared quota" not in good
         else "the catalogue copies a quota of the contracts"),
        ("the heading the catalogue links to is the one the routing document has, and a missing one is refused",
         lambda: None if routage_problem("# T\n\n## %s\n\ntext\n" % LIMITS_HEADING) is None
         and routage_problem("# T\n\n## Another\n") and routage_problem(None) else "the link is not held"),
        ("a model has its type, groups, ranks, level, sizes and quotas, a dash where no source says",
         lambda: expect(good, "| `alpha` | Gemini | chat | `LLM` | `Auto-Pro` | `high` | 1\u202f048\u202f576 | 65\u202f536 | 5 | 250\u202f000 | 20 |",
                        "| `whisper` | Groq | `audio_transcription` | `STT` | `Auto-TTS` | — | — | — | — | — | — |")),
        ("the scores of an entry are its figures with the record and the model the contracts map, a dash where none",
         lambda: expect(good, "| `alpha` | `alpha` (`high`) | 53,9 | 47,4 | `Alpha 1` | 166,81 | 9,37 |",
                        "| `bravo` | `bravo-medium` (`medium`) | 12,5 | — | — | — | — |",
                        "Artificial Analysis le 2026-11-24, Epoch AI le 2026-11-23")),
        ("an entry with no mapping and no figure has no row of scores",
         lambda: None if "| `whisper` | `" not in good.split("Position de code Epoch (%)")[-1] else "it has a row"),
        ("a source never read is said so", lambda: expect(build(SELFTEST_TEMPLATE, SELFTEST_CONTRACTS, dict(
            SELFTEST_SCORES, artificial_analysis_read=None, entries={})), "Artificial Analysis le jamais")),
        ("a mode the usage table does not know is shown with no usage and is no failure",
         lambda: expect(good, "| `Mystery` | `LLM` |") if "`mystery`" in good else "the entry vanished"),
        ("the committed file that is what the sources give is accepted",
         lambda: verdict(SELFTEST_TEMPLATE, SELFTEST_CONTRACTS, good, 0)),
        ("a hand edit is refused, and the message says what to run",
         lambda: verdict(SELFTEST_TEMPLATE, SELFTEST_CONTRACTS, good.replace("`alpha`", "`alpha-edited`", 1), 1, COMMAND)),
        ("a model added to the template makes the committed file stale",
         lambda: verdict(SELFTEST_TEMPLATE.replace("router_settings:", "  - model_name: gamma\n    model_info: "
                                                   "{access_groups: [\"LLM\"]}\n    litellm_params: {model: openai/gamma}\n"
                                                   "router_settings:"), SELFTEST_CONTRACTS, good, 1, "gamma")),
        ("a change of the contracts makes the committed file stale",
         lambda: verdict(SELFTEST_TEMPLATE, dict(SELFTEST_CONTRACTS, models={"bravo": {"level": "high"}}), good, 1,
                         "défaut : high")),
        ("a figure that changes makes the committed file stale",
         lambda: verdict(SELFTEST_TEMPLATE, SELFTEST_CONTRACTS, good, 1, "54,1",
                         scores=with_figure("aa_index", 54.1))),
        ("the figures file as the drift run writes it is accepted, and so is one with nothing read yet",
         lambda: scores_verdict(SELFTEST_SCORES) or scores_verdict(
             {"artificial_analysis_read": None, "epoch_read": None, "entries": {}})),
        ("a figures file with a figure that is no number is refused: text, a boolean, null, a list, NaN",
         lambda: next((wrong for wrong in (scores_refused(drift.render_scores(with_figure("aa_index", value)),
                                                 phrase="aa_index") for value in ("53.9", True, None, [53.9], float("nan"))) if wrong), None)),
        ("a figure out of its bounds is refused",
         lambda: scores_refused(drift.render_scores(with_figure("epoch_code_position", 140)), phrase="epoch_code_position")),
        ("a figure that has more than two decimals is refused",
         lambda: scores_refused(written.replace("166.81", "166.8123"), phrase="two decimals")),
        ("an entry that is none of the template's is refused",
         lambda: scores_refused(drift.render_scores(dict(SELFTEST_SCORES, entries=dict(
             SELFTEST_SCORES["entries"], gone={"aa_index": 1}))), phrase="gone is no entry")),
        ("a kind of figure that is not one of the four is refused",
         lambda: scores_refused(written.replace('"aa_index"', '"note"'), phrase="no kind of figure")),
        ("an entry with no figure is refused", lambda: scores_refused(
            '{\n "artificial_analysis_read": "2026-11-24",\n "epoch_read": null,\n "entries": {\n  "alpha": {}\n }\n}\n',
            phrase="holds no figure")),
        ("a day that is no day is refused, and a figure of a source never read",
         lambda: scores_refused(written.replace("2026-11-24", "2026-13-45"), phrase="artificial_analysis_read")
         or scores_refused(written.replace("2026-11-24", "24/11/2026"), phrase="artificial_analysis_read")
         or scores_refused(written.replace('"epoch_read": "2026-11-23"', '"epoch_read": null'), phrase="never read")),
        ("a key written twice, a key more, a key less and a file that is no object are refused",
         lambda: scores_refused(written.replace('"aa_index": 12.5', '"aa_index": 12.5, "aa_index": 13'), phrase="not JSON")
         or scores_refused(written.rstrip("\n").rstrip("}") + ', "note": 1}\n', phrase="exactly the keys")
         or scores_refused('{"entries": {}}\n', phrase="exactly the keys") or scores_refused("[1]\n", phrase="exactly")),
        ("a file that is not written the one way is refused: another order, another indentation, no final newline",
         lambda: scores_refused(written.replace(" ", "  "), phrase="the way the generator writes")
         or scores_refused(written.rstrip("\n"), phrase="the way the generator writes")
         or scores_refused(drift.json.dumps({"entries": SELFTEST_SCORES["entries"], "epoch_read": "2026-11-23",
                                             "artificial_analysis_read": "2026-11-24"}, indent=1) + "\n",
                           phrase="the way the generator writes")),
        ("a figures file that is absent is refused", lambda: None if drift.read_scores(
            ROOT / "docs" / "no_such_scores.json", ("alpha",))[1] else "an absent file was read"),
        ("the figures file of the repository is the one a run writes, for the entries of the real template",
         lambda: "; ".join(drift.read_scores(SCORES, entry_names(real_sources()[0]))[1]) or None),
        ("a template and an output file can be given, each once, and nothing else is a command line",
         lambda: None if (parse_arguments(["--template", "a", "--output", "b"]) == ("write", Path("a"), Path("b"), SCORES)
                          and parse_arguments(["--output", "b"]) == ("write", TEMPLATE, Path("b"), SCORES)
                          and parse_arguments(["--scores", "c"]) == ("write", TEMPLATE, CATALOG, Path("c"))
                          and parse_arguments([]) == ("write", TEMPLATE, CATALOG, SCORES)
                          and all(parse_arguments(each) is None for each in (
                              ["--template"], ["--template", "a", "--template", "b"], ["--check", "x"], ["a"],
                              ["--scores", "a", "--scores", "b"])))
         else "the arguments are not read as they should be"),
        ("a catalogue that is not there is refused", lambda: verdict(SELFTEST_TEMPLATE, SELFTEST_CONTRACTS, None, 1, "does not exist")),
        ("a template that does not render cannot be read", lambda: verdict("model_list: [", SELFTEST_CONTRACTS, good, 2)),
    ]


def run_selftest():
    failures = 0
    for purpose, case in selftest_cases():
        try:
            wrong = case()
        except Exception as error:  # a case that crashes is a case that failed, not a script that did
            wrong = "raised %s: %s" % (error.__class__.__name__, error)
        if wrong:
            failures += 1
            print("selftest: FAILED (%s) -- %s" % (purpose, wrong))
        else:
            print("selftest: ok -- %s" % purpose)
    if failures:
        print("selftest: %d case(s) failed." % failures)
        return 1
    print("selftest: every case passed.")
    return 0


def real_sources():
    """(template text, contracts) of this repository."""
    return read_sources()


def read_sources(template=TEMPLATE):
    template_text = template.read_bytes().decode("utf-8")
    contracts, problems = drift.load_contracts(CONTRACTS)
    if problems:
        raise ValueError(problems[0])
    return template_text, contracts


def parse_arguments(arguments):
    """(mode, template, output, scores): "check", "selftest" or "write", and for a write the template to read, the
    file to write and the figures file to read, or None when the arguments are none of those."""
    if arguments == ["--selftest"]:
        return "selftest", TEMPLATE, CATALOG, SCORES
    if arguments == ["--check"]:
        return "check", TEMPLATE, CATALOG, SCORES
    paths = {"--template": TEMPLATE, "--output": CATALOG, "--scores": SCORES}
    wanted = list(paths)
    while arguments:
        if len(arguments) < 2 or arguments[0] not in wanted:
            return None
        paths[arguments[0]] = Path(arguments[1])
        wanted.remove(arguments[0])
        arguments = arguments[2:]
    return "write", paths["--template"], paths["--output"], paths["--scores"]


def main(argv=None):
    parsed = parse_arguments(list(sys.argv[1:] if argv is None else argv))
    if parsed is None:
        print("usage: generate_catalog.py [--check | --selftest | [--template FILE] [--output FILE] [--scores FILE]]")
        return 2
    mode, template, output, scores_path = parsed
    if mode == "selftest":
        return run_selftest()
    try:
        template_text, contracts = read_sources(template)
        names = entry_names(template_text)
    except (OSError, UnicodeDecodeError, ValueError, drift.RenderError, yaml.YAMLError) as error:
        print("The template or the router contracts are unreadable (%s)." % error.__class__.__name__)
        return 2
    scores, problems = drift.read_scores(scores_path, names)
    if problems:
        print("The figures file %s is refused:\n- %s\n\nThe weekly drift run writes it. By hand, take out of it the entries "
              "that are no longer in the template, and nothing else, then run `%s`." % (
                  scores_path.name, "\n- ".join(problems), COMMAND))
        return 1
    if mode == "check":
        try:
            committed = CATALOG.read_bytes().decode("utf-8") if CATALOG.exists() else None
            routage = (ROOT / LIMITS_FILE).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            print("docs/CATALOG.md or %s is unreadable (%s)." % (LIMITS_FILE, error.__class__.__name__))
            return 2
        if routage_problem(routage):
            print(routage_problem(routage))
            return 1
        status, message = check(template_text, contracts, scores, committed)
        if status:
            print(message)
            return status
        print("Catalogue: docs/CATALOG.md is what the template, the router contracts and the figures produce.")
        return 0
    try:
        text = build(template_text, contracts, scores)
    except (drift.RenderError, yaml.YAMLError) as error:
        print("The template cannot be read: %s" % error)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(text.encode("utf-8"))
    print("Catalogue: wrote %s (%d lines)." % (output, len(text.splitlines())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
