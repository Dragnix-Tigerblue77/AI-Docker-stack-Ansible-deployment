#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77 and the AI Docker stack Ansible deployment contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Refuse "ROUTAGE.md" when it says something the LiteLLM template does not.

WHY THIS CHECK EXISTS
---------------------
"ROUTAGE.md" is kept by hand: it records which model sits where in each router, at which reasoning
level and why. A document nobody holds to the template is true on the day it is written and false the
day after, silently, and its readers are the people who decide what to change next. The two things in
it that the template can contradict are the ones this check holds it to; the figures and the reasons
are prose, and a person reads them.

WHAT IT CHECKS
--------------
The template is rendered with every provider key given, the way "check_LiteLLM_model_drift.py" renders
it, and each of its text routers ("Auto-Pro", "Auto-Flash", "Auto-Flash-Lite", "Auto-Code",
"Auto-Claude-Code") is read off "router_settings.fallbacks". The document has, for each of them, a
section headed "### `Auto-Pro`" (the router's published name) with a table whose columns include "Rang",
"Entrée" and "Niveau". Then:

1. Every router of the template has its section and its table, and no table is written twice.
2. The entries of the table are the members of the cascade, the same entries in the same order. A
   missing member, an extra one, a member out of place and a member written twice are each refused, and
   the message says which. A row for an entry the template no longer has is NOT refused: the
   deletion pull request removes retired entries from the template alone and must stay green to merge
   itself, so the check says such a row in a notice, to be removed by a person, and compares the others.
3. The "Niveau" cell of an entry says what the template sets. A cell that starts with a level between
   backticks (`high`) is a static "reasoning_effort", and the template must set that very value on that
   entry; any other cell says the level is not set, and must start with "défaut du fournisseur" or
   "non fixé", and the template must then set no "reasoning_effort" on the entry.
4. Every entry of the template that sets a static "reasoning_effort" is in the document, in a router
   table or in the section "### Entrées appelées par leur nom", which holds the entries in no cascade
   and is read the same way (an entry of that section that is in a cascade is refused).
5. The entries of that section are exactly the ones "check_compose_template.py" declares called by name
   ("LITELLM_CALLED_BY_NAME"): a row for an entry not declared there and a declared entry with no row are
   each refused, since that check is what refuses every other entry that no router reaches.

WHAT IT DELIBERATELY DOES NOT CHECK
-----------------------------------
The ranks (a deletion leaves a gap), the figures (index, time, quota), the provider and billing columns and the reasons: they come from
sources that revise themselves and from judgements, so a check would only make them stale on a schedule
nobody chose. Nor the routers of speech ("stt", "tts"), which have no ranking to record. Nor whether the
prose around the tables says what the contracts say.

Its verification cases are Python literals rather than fixture files, for the reason CLAUDE.md gives: a
fixture on disk is reachable by "ansible-lint --fix", which has rewritten one here before. Run it from
the repository root:

    python3 .github/scripts/check_routing_document.py --selftest
    python3 .github/scripts/check_routing_document.py
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_LiteLLM_model_drift as drift  # noqa: E402  (the one place that knows how to render the template)
import check_compose_template  # noqa: E402  (the one place that declares the entries called by name)

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = ROOT / "ROUTAGE.md"
TEMPLATE = drift.CONFIG
ROUTERS = tuple(router for router, _ in drift.RANKING_ROUTERS)
NAMED_SECTION = "Entrées appelées par leur nom"
NOT_SET = ("défaut du fournisseur", "non fixé")
HEADING = re.compile(r"^#{1,6}\s+(?P<title>.*?)\s*$")
SECTION_TITLE = re.compile(r"^###\s+(?P<title>.*?)\s*$")
STATIC_LEVEL = re.compile(r"^`(?P<level>[a-z]+)`")
ENTRY_CELL = re.compile(r"^`(?P<name>[^`]+)`$")


def split_row(line):
    """The cells of a table row, without the bars at its ends."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def read_sections(text):
    """({title: [(rank, entry, level cell)]}, problems) of the sections of the document this check reads: a
    router's, headed "### `router`", and the section of the entries called by name. The other tables of the
    document are prose. A table read must have the columns "Rang", "Entrée" and "Niveau"."""
    sections, problems = {}, []
    title, header = None, None
    for line in text.splitlines():
        heading = HEADING.match(line)
        if heading:
            match = SECTION_TITLE.match(line)
            heading_name = match.group("title").strip("`") if match else None
            # A router's section is headed by the name it is published under, and the rest of the check reads
            # a router by its short id: a section headed by the short id is none, so that the document says
            # the name a client types.
            title = None if heading_name in drift.ROUTER_PUBLIC_NAMES else drift.ROUTER_OF_PUBLIC_NAME.get(
                heading_name, heading_name)
            header = None
            continue
        if title not in ROUTERS + (NAMED_SECTION,) or not line.lstrip().startswith("|"):
            continue
        cells = split_row(line)
        if header is None:
            header = cells
            missing = [name for name in ("Rang", "Entrée", "Niveau") if name not in header]
            if missing:
                problems.append('the table of "%s" has no column %s' % (title, ", ".join('"%s"' % name for name in missing)))
            elif title in sections:
                problems.append('the document has two tables for "%s"' % title)
            sections.setdefault(title, [])
            continue
        if all(set(cell) <= set("-: ") for cell in cells) or len(cells) != len(header) or any(
                name not in header for name in ("Rang", "Entrée", "Niveau")):
            continue
        sections[title].append((cells[header.index("Rang")], cells[header.index("Entrée")], cells[header.index("Niveau")]))
    return sections, problems


def entry_name(cell, where, problems):
    match = ENTRY_CELL.match(cell)
    if not match:
        problems.append('%s has an "Entrée" cell that is not an entry name between backticks: %r' % (where, cell))
        return None
    return match.group("name")


def level_problem(name, cell, set_by_template, where):
    """What is wrong with the "Niveau" cell of an entry, or None."""
    static = STATIC_LEVEL.match(cell)
    if static:
        if set_by_template is None:
            return '%s says "%s" is fixed at %s and the template sets no reasoning_effort on it' % (
                where, name, static.group("level"))
        if static.group("level") != set_by_template:
            return '%s says "%s" is fixed at %s and the template sets %s' % (
                where, name, static.group("level"), set_by_template)
        return None
    if not cell.startswith(NOT_SET):
        return '%s gives "%s" a "Niveau" that is neither a level between backticks nor one of: %s' % (
            where, name, ", ".join('"%s"' % phrase for phrase in NOT_SET))
    if set_by_template is not None:
        return '%s says the level of "%s" is not set and the template sets %s' % (where, name, set_by_template)
    return None


def order_problem(router, wanted, found):
    """What is wrong with the members of a table against the cascade, or None."""
    where = 'the table of "%s"' % router
    if len(set(found)) != len(found):
        return "%s writes %s twice" % (where, ", ".join('"%s"' % name for name in sorted({n for n in found if found.count(n) > 1})))
    missing = [name for name in wanted if name not in found]
    extra = [name for name in found if name not in wanted]
    if missing or extra:
        return "%s differs from the cascade of the template:%s%s" % (
            where, " missing %s." % ", ".join('"%s"' % name for name in missing) if missing else "",
            " not in the cascade: %s." % ", ".join('"%s"' % name for name in extra) if extra else "")
    if wanted != found:
        number = next(index for index, (before, after) in enumerate(zip(wanted, found)) if before != after)
        return '%s has the members in another order than the template: its rank %d is "%s" and the template has "%s"' % (
            where, number + 1, found[number], wanted[number])
    return None


def document_problems(template, text, by_name=None):
    """(problems, notices) of a document against a template read by read_template: a notice is a row for
    an entry the template no longer has, which is left for a person to remove and fails nothing. `by_name` is the
    set of entries declared called by name, which the section of them has to list exactly."""
    if by_name is None:
        by_name = set(check_compose_template.LITELLM_CALLED_BY_NAME)
    problems = []
    lists = drift.fallback_lists(template["document"])
    efforts = {entry["name"]: entry["item"].get("litellm_params", {}).get("reasoning_effort")
               for entry in template["active"] if isinstance(entry["name"], str)}
    sections, problems_read = read_sections(text)
    problems += problems_read
    notices = []
    in_cascade, seen = set(), set()
    for router in ROUTERS:
        wanted = lists.get((drift.CONTRACT_FALLBACKS, router))
        if wanted is None:
            continue
        in_cascade.update(wanted)
        where = 'the table of "%s"' % router
        rows = sections.get(router)
        if not rows:
            problems.append('the document has no table for the router "%s" (a section headed "### `%s`")' % (
                router, drift.ROUTER_PUBLIC_NAMES.get(router, router)))
            continue
        found = [entry_name(entry, where, problems) for _, entry, _ in rows]
        if None in found:
            continue
        gone = [name for name in found if name not in efforts]
        if gone:
            notices.append("%s has a row for %s, which %s no entry of the template any more: remove it." % (
                where, ", ".join('"%s"' % name for name in gone), "is" if len(gone) == 1 else "are"))
        seen.update(found)
        message = order_problem(router, wanted, [name for name in found if name in efforts])
        if message:
            problems.append(message)
        for (_, _, cell), name in zip(rows, found):
            if name in efforts:
                message = level_problem(name, cell, efforts[name], where)
                if message:
                    problems.append(message)
    named = sections.get(NAMED_SECTION, [])
    listed = set()
    for _, entry, cell in named:
        name = entry_name(entry, 'the section "%s"' % NAMED_SECTION, problems)
        if name is None:
            continue
        listed.add(name)
        seen.add(name)
        if name not in efforts:
            notices.append('the section "%s" has a row for "%s", which is no entry of the template any more: remove it.' % (
                NAMED_SECTION, name))
        elif name in in_cascade:
            problems.append('the section "%s" names "%s", which is in a cascade: it belongs in its router\'s table' % (NAMED_SECTION, name))
        else:
            message = level_problem(name, cell, efforts[name], 'the section "%s"' % NAMED_SECTION)
            if message:
                problems.append(message)
    for name in sorted(listed - set(by_name)):
        problems.append('the section "%s" lists "%s", which LITELLM_CALLED_BY_NAME of check_compose_template.py does not '
                        "declare: an entry in no cascade is declared there, with its reason, or is routed, deleted or "
                        "commented out" % (NAMED_SECTION, name))
    for name in sorted(set(by_name) - listed):
        problems.append('LITELLM_CALLED_BY_NAME of check_compose_template.py declares "%s", which the section "%s" does '
                        "not list" % (name, NAMED_SECTION))
    for name, effort in efforts.items():
        if effort is not None and name not in seen:
            problems.append('"%s" sets reasoning_effort %s in the template and is in no table of the document' % (name, effort))
    return problems, notices


def check(template_text, document_text, by_name=None):
    """(status, problems, notices): 0 or 1 and what is wrong with the document against the template, or
    2 and why the template could not be read."""
    template, problems = drift.read_template(template_text)
    if template is None:
        return 2, problems, []
    found, notices = document_problems(template, document_text, by_name)
    return (1 if found else 0), found, notices


SELFTEST_TEMPLATE = """\
model_list:
  - model_name: alpha
    litellm_params: {model: acme/alpha, api_key: "k", reasoning_effort: high}
  - model_name: alpha-low
    litellm_params: {model: acme/alpha, api_key: "k", reasoning_effort: low}
  - model_name: alpha-max
    litellm_params: {model: acme/alpha, api_key: "k", reasoning_effort: xhigh}
  - model_name: bravo
    litellm_params: {model: acme/bravo, api_key: "k"}
  - model_name: charlie
    litellm_params: {model: acme/charlie, api_key: "k"}
router_settings:
  fallbacks:
    - Auto-Pro: [alpha, bravo]
    - Auto-Flash: [alpha-low, bravo, charlie]
    - alpha-max: [alpha]
  model_group_alias:
    "Auto-Pro": "alpha"
    "Auto-Flash": "alpha-low"
"""

SELFTEST_TABLE = """\
### `{router}`

| Rang | Entrée | Fournisseur | Niveau | Raison |
| --- | --- | --- | --- | --- |
{rows}
"""
SELFTEST_NAMED = """\
### Entrées appelées par leur nom

| Rang | Entrée | Fournisseur | Niveau | Raison |
| --- | --- | --- | --- | --- |
| 1 | `alpha-max` | Acme | `xhigh` | par son nom |
"""


# What the cases declare called by name unless a case says otherwise below.
SELFTEST_BY_NAME = {"alpha-max"}
GHOST_ROW = "| 2 | `ghost` | Acme | défaut du fournisseur | non |\n"
GHOST_DECLARED = "a row for an entry the template no longer has, in the section of named entries: said, and no failure"
BY_NAME_OF_CASE = {
    GHOST_DECLARED: SELFTEST_BY_NAME | {"ghost"},
    "a declared entry that the section does not list": SELFTEST_BY_NAME | {"bravo"},
}


def selftest_row(number, name, level):
    return "| %s | `%s` | Acme | %s | une raison |" % (number, name, level)


def selftest_document(pro=(("alpha", "`high`"), ("bravo", "défaut du fournisseur")),
                      flash=(("alpha-low", "`low`"), ("bravo", "non fixé : non vérifié chez ce fournisseur"),
                             ("charlie", "défaut du fournisseur")), named=SELFTEST_NAMED):
    tables = []
    for router, members in (("Auto-Pro", pro), ("Auto-Flash", flash)):
        if members is not None:
            tables.append(SELFTEST_TABLE.format(router=router, rows="\n".join(
                selftest_row(number, name, level) for number, (name, level) in enumerate(members, 1))))
    return "# Routage\n\nDu texte avant | et une barre.\n\n" + "\n".join(tables) + "\n" + (named or "")


def selftest_cases():
    """(purpose, template, document, a phrase of the refusal or None, a phrase of a notice), the notice
    being optional."""
    good = selftest_document()
    return [
        ("a document that says what the template says", SELFTEST_TEMPLATE, good, None),
        ("a member out of place", SELFTEST_TEMPLATE,
         selftest_document(pro=(("bravo", "défaut du fournisseur"), ("alpha", "`high`"))), "another order"),
        ("a member of the cascade left out of its table", SELFTEST_TEMPLATE,
         selftest_document(flash=(("alpha-low", "`low`"), ("bravo", "défaut du fournisseur"))), 'missing "charlie"'),
        ("a member that is not in the cascade", SELFTEST_TEMPLATE,
         selftest_document(pro=(("alpha", "`high`"), ("bravo", "défaut du fournisseur"), ("charlie", "défaut du fournisseur"))),
         'not in the cascade: "charlie"'),
        ("a member written twice", SELFTEST_TEMPLATE,
         selftest_document(pro=(("alpha", "`high`"), ("alpha", "`high`"), ("bravo", "défaut du fournisseur"))), 'writes "alpha" twice'),
        ("a router with no table", SELFTEST_TEMPLATE, selftest_document(flash=None), 'no table for the router "flash"'),
        ("a router table headed by the short id, which is no name a client types", SELFTEST_TEMPLATE,
         good.replace("### `Auto-Flash`", "### `flash`"), 'no table for the router "flash" (a section headed "### `Auto-Flash`")'),
        ("a static level that is not the template's", SELFTEST_TEMPLATE,
         selftest_document(pro=(("alpha", "`medium`"), ("bravo", "défaut du fournisseur"))), 'is fixed at medium and the template sets high'),
        ("a level said fixed on an entry that sets none", SELFTEST_TEMPLATE,
         selftest_document(pro=(("alpha", "`high`"), ("bravo", "`low`"))), "sets no reasoning_effort on it"),
        ("a level said not set on an entry that sets one", SELFTEST_TEMPLATE,
         selftest_document(pro=(("alpha", "défaut du fournisseur"), ("bravo", "défaut du fournisseur"))), "is not set and the template sets high"),
        ("a level cell that says nothing of the level", SELFTEST_TEMPLATE,
         selftest_document(pro=(("alpha", "`high`"), ("bravo", "à voir"))), "neither a level between backticks"),
        ("an entry with a static level that is in no table", SELFTEST_TEMPLATE, selftest_document(named=""),
         '"alpha-max" sets reasoning_effort xhigh in the template and is in no table'),
        ("an entry of the section of named entries that is in a cascade", SELFTEST_TEMPLATE,
         selftest_document(named=SELFTEST_NAMED + "| 2 | `bravo` | Acme | défaut du fournisseur | non |\n"), "which is in a cascade"),
        ("a row for an entry the template no longer has, in a router table: said, and no failure", SELFTEST_TEMPLATE,
         selftest_document(pro=(("alpha", "`high`"), ("ghost", "`low`"), ("bravo", "défaut du fournisseur"))), None,
         'has a row for "ghost"'),
        (GHOST_DECLARED, SELFTEST_TEMPLATE,
         selftest_document(named=SELFTEST_NAMED + GHOST_ROW), None, 'has a row for "ghost"'),
        ("a row of the section of named entries that is not declared called by name", SELFTEST_TEMPLATE,
         selftest_document(named=SELFTEST_NAMED + GHOST_ROW), "does not declare", 'has a row for "ghost"'),
        ("a declared entry that the section does not list", SELFTEST_TEMPLATE, good, "does not list"),
        ("a declared entry with no row in the section of named entries", SELFTEST_TEMPLATE,
         selftest_document(named=SELFTEST_NAMED.split("| 1 |")[0]), 'declares "alpha-max"'),
        ("a row for a deleted entry does not hide a member out of place", SELFTEST_TEMPLATE,
         selftest_document(pro=(("bravo", "défaut du fournisseur"), ("ghost", "`low`"), ("alpha", "`high`"))), "another order",
         'has a row for "ghost"'),
        ("a rank that skips a number is no failure, a deletion leaves one", SELFTEST_TEMPLATE,
         good.replace("| 2 | `bravo` | Acme | défaut du fournisseur | une raison |\n",
                      "| 3 | `bravo` | Acme | défaut du fournisseur | une raison |\n", 1), None),
        ("a table with no Niveau column", SELFTEST_TEMPLATE, good.replace("| Rang | Entrée | Fournisseur | Niveau | Raison |",
                                                                           "| Rang | Entrée | Fournisseur | Raison |", 1), 'has no column "Niveau"'),
        ("a router table written twice", SELFTEST_TEMPLATE, good + "\n" + SELFTEST_TABLE.format(
            router="Auto-Pro", rows=selftest_row(1, "alpha", "`high`")), 'two tables for "pro"'),
        ("a template that does not render", "model_list: [", good, "not valid YAML"),
    ]


def run_selftest():
    failures = 0
    for purpose, template, document, expected, *notice in selftest_cases():
        status, problems, notices = check(template, document, BY_NAME_OF_CASE.get(purpose, SELFTEST_BY_NAME))
        shown = " ".join(problems)
        if expected is None:
            wrong = None if status == 0 and not problems else "refused: %s" % shown
        elif expected == "not valid YAML":
            wrong = None if status == 2 and expected in shown else "status %d: %s" % (status, shown)
        else:
            wrong = None if status == 1 and expected in shown else "status %d, wanted a refusal saying %r: %s" % (status, expected, shown)
        if not wrong and notice and not any(notice[0] in text for text in notices):
            wrong = "no notice saying %r: %r" % (notice[0], notices)
        if not wrong and not notice and notices:
            wrong = "a notice nobody asked for: %r" % notices
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


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if arguments == ["--selftest"]:
        return run_selftest()
    if arguments:
        print("usage: check_routing_document.py [--selftest]")
        return 2
    try:
        template_text = TEMPLATE.read_bytes().decode("utf-8")
        document_text = DOCUMENT.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print("%s: unreadable (%s)." % ("ROUTAGE.md or the template", error.__class__.__name__))
        return 2
    status, problems, notices = check(template_text, document_text)
    if status == 2:
        print("The template cannot be read: %s" % problems[0])
        return 2
    if problems:
        print("Routing document: %d problem(s) in ROUTAGE.md.\n" % len(problems))
        for problem in problems:
            print("- " + problem)
        print("\nROUTAGE.md is kept by hand: edit it to say what the template says (see this check's docstring).")
        return 1
    for notice in notices:
        print("Notice: " + notice)
    template, _ = drift.read_template(template_text)
    lists = drift.fallback_lists(template["document"])
    fixed = sum(1 for entry in template["active"] if entry["item"].get("litellm_params", {}).get("reasoning_effort") is not None)
    print("Routing document: ROUTAGE.md holds the cascade of each of the %d routers of the template, in its order, "
          "and the %d static levels the template sets."
          % (sum(1 for router in ROUTERS if (drift.CONTRACT_FALLBACKS, router) in lists), fixed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
