#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77 and the AI Docker stack Ansible deployment contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Write "docs/CATALOG.md", the overview of everything the LiteLLM gateway serves, and refuse a stale copy.

WHY THIS SCRIPT EXISTS
----------------------
What the gateway serves is spread over three places: the model list and the cascades in
"templates/LiteLLM_config.yaml.j2", the access groups that "check_compose_template.py" holds each entry to, and the
router contracts in ".github/LiteLLM_router_contracts.yaml". A person who wants the picture, which groups exist,
which routers there are and what is in them, which provider holds how many entries, has to read all three. An
overview written by hand is true on the day it is written and false the day after a model is added, which is what
"ROUTAGE.md" accepts for the reasons it gives. This one is generated, so that it cannot drift: the CI refuses a copy
that is not what the sources produce.

WHAT IT WRITES
--------------
The template, rendered the way "check_LiteLLM_model_drift.py" renders it (every provider key given, by Jinja2 alone),
and the contracts file, read with the same loader, in four sections:

1. The access groups and the LiteLLM types: the table "check_compose_template.py" reads ("LITELLM_ACCESS_GROUPS" and
   "LITELLM_KEPT_APART_GROUPS"), and any other group found on an entry, which is a group in addition to the one of
   its type, one row for each type group it sits on.
2. The routers: each one's cascade, "router_settings.fallbacks", in order; its head, "model_group_alias";
   its purpose, the first sentence of the comment that opens its cascade in the template, cut at its first colon; the ranking, the last
   resort members, the quota it shares and what it requires, from the contracts; the entry that picks a router by
   the complexity of the request, and the fallbacks of entries called by name.
3. The providers: the key variable (or none), a row for each router it appears in, and the quota the contracts
   declare for it.
4. The models: one row per entry of the model list with its provider, type, groups, routers, the level of
   reasoning (the static "reasoning_effort" of the template, else the level the contracts say the provider calls it
   at), the context window and the longest answer.

WHAT IT DELIBERATELY DOES NOT WRITE
-----------------------------------
No count, no total and no number of rank, and no list of names joined on one line, wherever a deletion would
rewrite it. The drift workflow's deletion pull request carries this file beside the template, and the gate that
merges it without a person lets the file lose lines and never gain one: a "99 entries" that becomes "98", or a
rank that moves up when the entry above it goes, is a line removed and a line added, and would send every deletion
to a person. So a row is one fact about one thing, in the order of its source, and an entry that goes takes its rows
and nothing else changes. A selftest case deletes entries from the real template and holds the result to it, so a
later change of format that rewrites a line fails CI instead of quietly ending the merges. The order of a cascade is
the order of its rows, and "ROUTAGE.md" keeps the ranks.

No figure a source does not hold. The contracts file holds no intelligence index and no time to the first token: the
weekly drift run reads those online from Artificial Analysis and puts them in its summary, so the catalogue has no
column for them, and no offer or quota prose of its own. Nothing here is dated, so that the same sources give the same
bytes on any day.

WHY THE CHECK COMPARES BYTES
----------------------------
"--check" regenerates the file in memory and compares it with the committed one, and refuses any difference, a
hand edit included: a copy that is edited by hand is a copy a regeneration silently reverts. A change to the template
or to the contracts file therefore regenerates the catalogue in the same commit, and so do the pull requests of
the drift workflow: its job that reads the providers' catalogues runs this script, with a template and an output file
of its own, on the template it edited and on each one it proposes, and the job that writes commits the two together.

Its verification cases are Python literals rather than fixture files, for the reason CLAUDE.md gives: a fixture on
disk is reachable by "ansible-lint --fix". Run it from the repository root:

    python3 .github/scripts/generate_catalog.py              # writes docs/CATALOG.md
    python3 .github/scripts/generate_catalog.py --check      # exits 1 when the committed file is stale
    python3 .github/scripts/generate_catalog.py --selftest
    python3 .github/scripts/generate_catalog.py --template FILE --output FILE   # another template, another file
"""

import collections
import difflib
import os
import re
import sys
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
QUOTAS = "Les quotas que déclarent les contrats"
NO_VALUE = "—"
# What an entry that calls no provider is shown as: the entry that picks a router.
GATEWAY = "LiteLLM"
# The narrow no-break space French groups digits with, which keeps a figure on one line.
THOUSANDS = "\u202f"

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
    quotas = ((contracts.get("inputs") or {}).get("quota") or {}) if isinstance(contracts.get("inputs"), dict) else {}
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
    rows = [(provider_label(name), "`%s`" % key_variable(name) if key_variable(name) else "sans clé") for name in names]
    appearances = [(provider_label(name), "`%s`" % public) for name in names for public in appears[name]]
    text = (
        "Un fournisseur est celui que lit l'entrée : la clé dont la variable est donnée, ou une passerelle qui n'en "
        "demande aucune. Un fournisseur dont la clé n'est pas donnée n'a aucune entrée dans la configuration "
        "rendue.\n\n" + table(("Fournisseur", "Variable de la clé"), rows)
        + "\n\nLes routeurs où figure chaque fournisseur, une ligne par routeur :\n\n"
        + table(("Fournisseur", "Routeur"), appearances)
    )
    declared = [(name, quotas[name.lower()]) for name in names if isinstance(quotas.get(name.lower()), str)]
    if declared:
        text += ("\n\n### %s\n\nCe que dit `.github/LiteLLM_router_contracts.yaml`, tel quel, des limites de chaque "
                 "fournisseur : ce sont des déclarations datées, qu'aucun contrôle ne vérifie.\n\n" % QUOTAS
                 + "\n".join("- **%s** : %s" % (provider_label(name), declaration) for name, declaration in declared))
    return text, ([QUOTAS] if declared else [])


def models_section(document, entries, contracts):
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
        ))
    return (
        "Une ligne par entrée de la liste des modèles, dans l'ordre du modèle. La fenêtre de contexte et la réponse "
        "la plus longue sont celles que le fournisseur sert, `model_info.max_input_tokens` et "
        "`model_info.max_output_tokens`. Le niveau est le `reasoning_effort` que le modèle fixe, sinon celui auquel "
        "les contrats disent que le fournisseur appelle l'entrée par défaut. Un tiret veut dire qu'aucune source ne "
        "donne la valeur. L'indice d'intelligence et le temps jusqu'au premier jeton n'ont pas de colonne : ils "
        "viennent d'Artificial Analysis, que la vérification hebdomadaire des modèles lit en ligne, et aucun fichier "
        "du dépôt ne les garde.\n\n"
        + table(("Entrée", "Fournisseur", "Type", "Groupes", "Routeurs", "Niveau", "Contexte", "Sortie max"), rows)
    )


def build(template_text, contracts):
    """The text of the catalogue for this template and these contracts (a mapping, or None for none)."""
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
        (SECTION_MODELS, models_section(document, entries, contracts), []),
    ]
    contents = []
    for title, _, subs in sections:
        contents.append("- [%s](#%s)" % (title, slug(title)))
        contents += ["  - [%s](#%s)" % (sub if sub in (NAMED_FALLBACKS, QUOTAS) else "`%s`" % sub, slug(sub))
                     for sub in subs]
    header = (
        SPDX_HEADER + "\n"
        "# %s\n\n"
        "> Ce fichier est généré par `%s` à partir du modèle de configuration de LiteLLM "
        "(`templates/LiteLLM_config.yaml.j2`) et des contrats des routeurs "
        "(`.github/LiteLLM_router_contracts.yaml`). Ne le modifiez pas à la main : la CI refuse un fichier qui n'est "
        "pas ce que ces sources produisent, et un changement de l'un ou de l'autre le régénère dans le même commit.\n\n"
        "Ce catalogue dit tout ce que la passerelle sert : les groupes d'accès, les routeurs et leurs membres, les "
        "fournisseurs, et chaque modèle. Il décrit la configuration rendue avec la clé de tous les fournisseurs "
        "donnée.\n\n"
        "## Sommaire\n\n%s\n"
    ) % (TITLE, COMMAND, "\n".join(contents))
    return header + "\n" + "\n".join(section(title, body, top) for title, body, _ in sections)


# ------------------------------------------------------------------------------------------------
# The check
# ------------------------------------------------------------------------------------------------

def check(template_text, contracts, committed):
    """(status, message) of a committed catalogue (None when absent) against what the sources produce: 0 when it is
    that, 1 when it is not, 2 when the sources cannot be read."""
    try:
        wanted = build(template_text, contracts)
    except (drift.RenderError, yaml.YAMLError) as error:
        return 2, "The template cannot be read: %s" % error
    if committed is None:
        return 1, "docs/CATALOG.md does not exist. Write it with `%s` and commit it." % COMMAND
    if committed == wanted:
        return 0, ""
    difference = list(difflib.unified_diff(committed.splitlines(), wanted.splitlines(), "docs/CATALOG.md (committed)",
                                           "docs/CATALOG.md (generated)", lineterm="", n=0))
    shown = difference[:14] + (["... (%d more lines)" % (len(difference) - 14)] if len(difference) > 14 else [])
    return 1, ("docs/CATALOG.md is not what the template and the router contracts produce. It is generated: run "
               "`%s` and commit the result in the same commit as the change.\n\n%s" % (COMMAND, "\n".join(shown)))


# ------------------------------------------------------------------------------------------------
# Its own verification
# ------------------------------------------------------------------------------------------------

SELFTEST_TEMPLATE = """\
model_list:
  - model_name: alpha
    model_info: {access_groups: ["LLM"], max_input_tokens: 1048576, max_output_tokens: 65536}
    litellm_params: {model: gemini/alpha, api_key: os.environ/GEMINI_API_KEY, reasoning_effort: high}
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
    "inputs": {"quota": {"gemini": "a declared quota"}},
    "routers": {"pro": {"ranking": {"criterion": "intelligence", "shared_quota_with": ["flash"]},
                        "last_resort": {"members": ["bravo"]}, "requires": ["tools"]}},
    "models": {"bravo": {"level": "medium"}},
}


def without_entry(template_text, name):
    """The template with the entry "name" taken out the way the drift script takes one out: its block and the blank
    line after it, each cascade slot that names it, and, for an entry called by name, its own list of fallbacks."""
    lines = template_text.split("\n")
    out = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line == "  - model_name: %s" % name:
            index += 1
            while index < len(lines) and lines[index].startswith("    "):
                index += 1
            if index < len(lines) and lines[index] == "":
                index += 1
            continue
        if line == "    - %s:" % name:
            index += 1
            while index < len(lines) and lines[index].startswith("        "):
                index += 1
            continue
        if re.fullmatch(r"\s{8,}- %s" % re.escape(name), line):
            index += 1
            continue
        out.append(line)
        index += 1
    return "\n".join(out)


def deletion_targets(template_text):
    """{what it is: the name of an entry of the real template that shows it}: one in the middle of a cascade, the last
    of a cascade, one called by name. An entry that is the head of a router or a last resort is left out, since
    deleting it rewrites the head of that router in the template itself, which no format of this file can avoid."""
    document = yaml.safe_load(drift.render_with_keys(template_text, None))
    lists = cascades(document)
    heads = set(aliases(document).values())
    contracts, _ = drift.load_contracts(CONTRACTS)
    last = {member for router in ((contracts or {}).get("routers") or {}).values() if isinstance(router, dict)
            for member in ((router.get("last_resort") or {}).get("members") or [])}
    in_routers = collections.Counter(member for public, members in lists.items()
                                     if public in drift.ROUTER_OF_PUBLIC_NAME for member in members)

    def free(members):
        return [member for member in members if member not in heads and member not in last]

    cascade = free([member for public, members in lists.items() if public in drift.ROUTER_OF_PUBLIC_NAME
                    for member in members])
    middle = next((member for member in cascade if in_routers[member] > 1), cascade[len(cascade) // 2])
    tail = free(next(members for public, members in lists.items() if public == "Auto-Flash-Lite"))[-1]
    named = [name for name in lists if name not in drift.ROUTER_OF_PUBLIC_NAME]
    targets = {"an entry in the middle of cascades": middle, "the last member of a cascade": tail}
    if named:
        targets["an entry called by name"] = named[0]
    return targets


def deletion_wrong(template_text, contracts, name):
    """Why deleting the entry "name" from this template does not leave a catalogue that only lost lines, or None."""
    before = build(template_text, contracts)
    after = build(without_entry(template_text, name), contracts)
    if before == after:
        return "the catalogue is the same without %s, so nothing was deleted" % name
    difference = list(difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0))
    added = [line for line in difference if line.startswith("+") and not line.startswith("+++")]
    if added:
        return "deleting %s adds %d line(s) to the catalogue, the first being %r" % (name, len(added), added[0][:120])
    return None


def selftest_cases():
    """(purpose, a function of the catalogue that returns what is wrong with it, or None)."""
    good = build(SELFTEST_TEMPLATE, SELFTEST_CONTRACTS)

    def expect(text, *phrases):
        missing = [phrase for phrase in phrases if phrase not in text]
        return "missing %r" % missing if missing else None

    def verdict(template, contracts, committed, wanted_status, phrase=""):
        status, message = check(template, contracts, committed)
        if status != wanted_status or phrase not in message:
            return "status %d (wanted %d): %s" % (status, wanted_status, message[:200])
        return None

    return [
        ("the same sources give the same bytes", lambda: None if build(SELFTEST_TEMPLATE, SELFTEST_CONTRACTS) == good
         and good.endswith("\n") and "\r" not in good else "the output differs between two runs"),
        ("the file starts with its SPDX header and says it is generated, and by which command",
         lambda: expect(good, "généré par `%s`" % COMMAND) if good.startswith(SPDX_HEADER + "\n# ")
         else "no SPDX header at the top"),
        ("a table of contents and a way back to the top after each section",
         lambda: expect(good, "- [Les routeurs](#les-routeurs)", "  - [`Auto-Pro`](#auto-pro)",
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
        ("a provider has its key variable, or none, its entries, its routers and its declared quota",
         lambda: expect(good, "| Gemini | `Artificial_Intelligence_LiteLLM_Gemini_API_key` |", "| Kilo | sans clé |",
                        "| Gemini | `Auto-Pro` |", "| Kilo | `Auto-Pro` |", "- **Gemini** : a declared quota")),
        ("a model has its type, groups, ranks, level and sizes, a dash where no source says",
         lambda: expect(good, "| `alpha` | Gemini | chat | `LLM` | `Auto-Pro` | `high` | 1\u202f048\u202f576 | 65\u202f536 |",
                        "| `whisper` | Groq | `audio_transcription` | `STT` | `Auto-TTS` | — | — | — |")),
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
        ("a template and an output file can be given, each once, and nothing else is a command line",
         lambda: None if (parse_arguments(["--template", "a", "--output", "b"]) == ("write", Path("a"), Path("b"))
                          and parse_arguments(["--output", "b"]) == ("write", TEMPLATE, Path("b"))
                          and parse_arguments([]) == ("write", TEMPLATE, CATALOG)
                          and all(parse_arguments(each) is None for each in (
                              ["--template"], ["--template", "a", "--template", "b"], ["--check", "x"], ["a"])))
         else "the arguments are not read as they should be"),
        ("deleting an entry of the real template, wherever it stands, only removes lines from the catalogue",
         lambda: next((wrong for wrong in (deletion_wrong(*real_sources(), name) for name in
                                           deletion_targets(real_sources()[0]).values()) if wrong), None)),
        ("the entries it deletes show a cascade of several routers, the end of one, and one called by name",
         lambda: None if len(deletion_targets(real_sources()[0])) == 3 else "got %r" % deletion_targets(real_sources()[0])),
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
    """(template text, contracts) of this repository, which the deletion cases are played on."""
    return read_sources()


def read_sources(template=TEMPLATE):
    template_text = template.read_bytes().decode("utf-8")
    contracts, problems = drift.load_contracts(CONTRACTS)
    if problems:
        raise ValueError(problems[0])
    return template_text, contracts


def parse_arguments(arguments):
    """(mode, template, output): "check", "selftest" or "write", and for a write the template to read and the file
    to write, or None when the arguments are none of those."""
    if arguments == ["--selftest"]:
        return "selftest", TEMPLATE, CATALOG
    if arguments == ["--check"]:
        return "check", TEMPLATE, CATALOG
    paths = {"--template": TEMPLATE, "--output": CATALOG}
    wanted = list(paths)
    while arguments:
        if len(arguments) < 2 or arguments[0] not in wanted:
            return None
        paths[arguments[0]] = Path(arguments[1])
        wanted.remove(arguments[0])
        arguments = arguments[2:]
    return "write", paths["--template"], paths["--output"]


def main(argv=None):
    parsed = parse_arguments(list(sys.argv[1:] if argv is None else argv))
    if parsed is None:
        print("usage: generate_catalog.py [--check | --selftest | [--template FILE] [--output FILE]]")
        return 2
    mode, template, output = parsed
    if mode == "selftest":
        return run_selftest()
    try:
        template_text, contracts = read_sources(template)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        print("The template or the router contracts are unreadable (%s)." % error.__class__.__name__)
        return 2
    if mode == "check":
        try:
            committed = CATALOG.read_bytes().decode("utf-8") if CATALOG.exists() else None
        except (OSError, UnicodeDecodeError) as error:
            print("docs/CATALOG.md is unreadable (%s)." % error.__class__.__name__)
            return 2
        status, message = check(template_text, contracts, committed)
        if status:
            print(message)
            return status
        print("Catalogue: docs/CATALOG.md is what the template and the router contracts produce.")
        return 0
    try:
        text = build(template_text, contracts)
    except (drift.RenderError, yaml.YAMLError) as error:
        print("The template cannot be read: %s" % error)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(text.encode("utf-8"))
    print("Catalogue: wrote %s (%d lines)." % (output, len(text.splitlines())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
