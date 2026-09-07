#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77
# SPDX-License-Identifier: AGPL-3.0-only

"""Refuse any LiteLLM configuration where one person's quota can pay for another's call.

WHY THIS CHECK EXISTS
---------------------
The LiteLLM gateway has no reason to exist unless the two accounts' quotas stay watertight. And
that watertightness is lost in three ways, only one of which shows on a read-through (#2,
specification 4):

  1. a "fallbacks" that explicitly names a model belonging to the other person -- visible;
  2. two entries with the same "model_name" carrying different "api_key" values: the Router treats
     them as two deployments of a single group and spreads the load between them -- invisible, not
     one "fallbacks" line has been written;
  3. the automatic cooldown: inside a group, a deployment that takes a 429 is set aside and the
     traffic goes to the other deployments OF THE SAME GROUP. If the group holds both accounts,
     the two people relay each other the moment one is exhausted. That is the default behaviour,
     it needs no configuration whatsoever to happen, and it is exactly what a provider calls a
     quota circumvention.

Point 3 is the real motive for this file. Nothing else in this CI can see it: the offending
configuration is perfectly valid YAML, which yamllint and ansible-lint both accept without a single
remark. The day the 429s become tiresome, someone will add a fallback in good faith, and the
isolation will disappear without one test failing.

WHAT DECIDES AN ACCOUNT'S IDENTITY
----------------------------------
The name of the key's environment variable, and it alone: an "api_key" reading
"os.environ/GROQ_API_KEY_DRAGNIX" belongs to the "DRAGNIX" account. It is the key that spends the
quota; the "model_name" suffix and "model_info.access_groups" are only labels, and a label can lie.

This script knows no list of people: the account is the segment that follows "_API_KEY_" in the
variable's name, whatever it is. A third account, or #2's "SCI" billed project, work without one
line here changing. An entry whose key does NOT allow a conclusion (a Jinja variable, a variable
name outside the convention, or no "api_key" at all) is not silently ignored: it is reported,
because an entry the check cannot attribute is exactly an entry on which it protects nothing.

One shape of "no conclusion" is not reported, and is not the same as the others: a LITERAL, non-empty
"api_key" -- neither "os.environ/..." nor a Jinja expression. This repository's own rule is that a
real secret is NEVER written in clear text, so such a value can only be a marker for a backend that
needs no credential at all, never an oversight. #2 uses exactly this shape for OmniRoute, which is
deliberately shared and reachable by every account: there is no quota behind it to attribute, and
none to protect. It is exempt from rules 1 and 2 (nothing to group, nothing to attribute), and it
never appears in "accounts_seen" -- a real account's grouping and labelling rules are unaffected by
its presence.

WHY THE YAML IS PARSED, AND NO LONGER READ LINE BY LINE
-------------------------------------------------------
The first version of this file read lines with regular expressions, so as to carry no dependency.
It was replaced after measurement: the same cross-account fallback written in BLOCK style rather
than in FLOW style went unseen.

    router_settings:                     router_settings:
      fallbacks:                           fallbacks:
        - a: ["b"]          <- seen          - a:             <- NOT seen
                                                 - b

Both forms produce the same object, "yamllint" accepts them both, and the second is the one every
YAML serialiser produces -- so Ansible's "to_nice_yaml" filter, so the repository's majority style.
A guard rail that depends on the writing style of what it watches is not one. The price paid is a
dependency on PyYAML and a "pip install" step in the job; that is the right side of the trade-off,
and it is taken knowingly here rather than discovered on the day of a quota incident.

The file being targeted is a Jinja TEMPLATE rendered by an Ansible role, which "yaml.safe_load"
would refuse: "{{ ... }}" opens a brace that YAML reads as the start of a dictionary. The Jinja is
therefore neutralised before the parsing (see "neutralise_jinja"). If a file stays unreadable even
so, it is REPORTED and not skipped: a file nobody managed to read is not a compliant file.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
* It does not read the gateway's actual state. A virtual key created by hand in "/ui" is invisible
  to it: that is covered by #2's executable negative test, not by a file check.
* It does not see a fallback passed in the BODY of a request ("extra_body={'fallbacks': [...]}").
  No file check can. The counter to that is "disable_fallbacks" on the virtual keys.
* It no longer sees what is COMMENTED OUT, since a YAML parser throws comments away. That is a
  change from the line-by-line version, and it is the sound call: a commented-out fallback is not
  active, and the old version accused a correct entry because of a revoked key kept on record.
* It delivers no verdict on a file it has not found. Until #2 has landed there is nothing to read,
  and it says so rather than returning a green that means nothing.
"""

import argparse
import os
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "PyYAML is required by this check (see requirements.txt): pip install -r requirements.txt\n"
    )
    raise SystemExit(2)

# LiteLLM's four fallback keys. "fallbacks" on its own is not enough: the three others produce the
# same effect by another route, and are declared under "router_settings" just as readily as under
# "litellm_settings".
FALLBACK_KEYS = (
    "fallbacks",
    "default_fallbacks",
    "context_window_fallbacks",
    "content_policy_fallbacks",
)
SETTINGS_SECTIONS = ("router_settings", "litellm_settings")

# "os.environ/GROQ_API_KEY_DRAGNIX" -> account "DRAGNIX".
ENVIRONMENT_REFERENCE = re.compile(r"^os\.environ/(?P<variable>[A-Za-z0-9_]+)$")
ACCOUNT_FROM_VARIABLE = re.compile(r"_API_KEY_(?P<account>[A-Za-z0-9_]+)$")

# A sentinel, not a string: it must never compare equal to an account name, be sortable next to one,
# or land in an f-string as if it were one. Every call site that can receive it is written to
# exclude it explicitly rather than rely on it behaving like a normal account.
SHARED = object()

JINJA_EXPRESSION = re.compile(r"\{\{.*?\}\}", re.DOTALL)
JINJA_STATEMENT = re.compile(r"\{%.*?%\}", re.DOTALL)
JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)

# A candidate file is a YAML, rendered by Jinja or not. The NAME is not what identifies it: LiteLLM
# calls its configuration "config.yaml", and a check demanding "litellm" in the name would quietly
# announce "no configuration found" on a repository that has one.
CANDIDATE_SUFFIXES = (".yml", ".yaml", ".yml.j2", ".yaml.j2")
SKIPPED_DIRECTORIES = {".git", ".venv", "venv", "node_modules", "__pycache__", ".ansible"}

SELFTEST_DIRECTORY = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "LiteLLM_account_isolation"
)


def neutralise_jinja(text):
    """Make a Jinja template parsable by a YAML reader.

    Expressions become an ordinary scalar, statements and comments disappear. This is not a render:
    a "{% for %}" loop does not produce its elements, so what gets parsed is the file's static
    SKELETON. That is enough here -- a "model_list" entry produced by a loop would be undecidable
    on a read-through anyway -- and it is said rather than assumed.
    """
    text = JINJA_COMMENT.sub("", text)
    text = JINJA_STATEMENT.sub("", text)
    text = JINJA_EXPRESSION.sub("JINJA", text)
    lines = [line for line in text.splitlines() if line.strip() != ""]
    return "\n".join(lines)


def account_of_reference(value):
    """The account that owns an "api_key" -- "SHARED" if it deliberately owns none, and why when no
    conclusion at all can be drawn.

    A LITERAL value here -- neither "os.environ/..." nor a Jinja expression -- can only legitimately
    be a backend that needs no credential at all: this repository's own rule is that a real secret is
    NEVER written in clear text, so a literal, non-empty string is a marker rather than an oversight.
    Such a deployment has no quota behind it to protect, which is exactly OmniRoute's role in #2 --
    shared and reachable by every account on purpose, precisely because nothing is at stake.
    """
    if not isinstance(value, str):
        return None, "the value is not a string"
    stripped = value.strip()
    reference = ENVIRONMENT_REFERENCE.match(stripped)
    if not reference:
        if "JINJA" in value:
            return None, "the key comes from a Jinja variable, unreadable here"
        if stripped:
            return SHARED, None
        return None, "the key is not read through \"os.environ/...\""
    account = ACCOUNT_FROM_VARIABLE.search(reference.group("variable"))
    if not account:
        return None, (
            "the name \"%s\" does not follow the \"<PROVIDER>_API_KEY_<ACCOUNT>\" convention of #2"
            % reference.group("variable")
        )
    return account.group("account"), None


def normalise_fallbacks(section):
    """Every fallback mapping of a section, however it is written.

    Returns (key, source, [targets]). The source is None for "default_fallbacks", which has none:
    its list applies to ALL the groups at once.

    This is where the YAML parsing pays for itself: block style, flow style and flow style spread
    over several lines all three arrive in the same shape, and there is only one case left to
    handle instead of three to miss.
    """
    found = []
    if not isinstance(section, dict):
        return found
    for key in FALLBACK_KEYS:
        if key not in section:
            continue
        value = section[key]
        if key == "default_fallbacks":
            targets = value if isinstance(value, list) else [value]
            found.append((key, None, [t for t in targets if isinstance(t, str)]))
            continue
        entries = value if isinstance(value, list) else [value]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for source, targets in entry.items():
                if not isinstance(targets, list):
                    targets = [targets]
                found.append((key, source, [t for t in targets if isinstance(t, str)]))
    return found


def read_entries(document):
    """The "model_list" entries, in a usable shape."""
    entries = []
    model_list = document.get("model_list") if isinstance(document, dict) else None
    if not isinstance(model_list, list):
        return entries
    for entry in model_list:
        if not isinstance(entry, dict):
            continue
        parameters = entry.get("litellm_params") or {}
        information = entry.get("model_info") or {}
        groups = information.get("access_groups") if isinstance(information, dict) else None
        entries.append({
            "model_name": entry.get("model_name"),
            "api_key": parameters.get("api_key") if isinstance(parameters, dict) else None,
            "access_groups": [g for g in (groups or []) if isinstance(g, str)],
        })
    return entries


def check_document(path, document):
    """The problems of an already parsed configuration."""
    problems = []
    entries = read_entries(document)
    if not entries:
        return problems

    accounts_seen = set()
    for entry in entries:
        account, _ = account_of_reference(entry["api_key"])
        if account and account is not SHARED:
            accounts_seen.add(account)

    # Rule 1 -- a "model_name" never groups two accounts together.
    # This is the one that closes the automatic cooldown, so the most important of the four.
    # "SHARED" is excluded from the grouping itself, not just from "accounts_seen": it is not a
    # second account to detect a mix with, it is the absence of one, same as an entry the check
    # cannot read at all -- and unlike a real account, it cannot be sorted next to one.
    by_name = {}
    for entry in entries:
        if isinstance(entry["model_name"], str):
            by_name.setdefault(entry["model_name"], []).append(entry)

    account_of_model = {}
    for name, group in sorted(by_name.items()):
        accounts = sorted({
            account for account, _ in
            (account_of_reference(entry["api_key"]) for entry in group)
            if account and account is not SHARED
        })
        if len(accounts) == 1:
            account_of_model[name] = accounts[0]
        elif len(accounts) > 1:
            problems.append(
                "%s: the model_name \"%s\" groups deployments from several accounts (%s).\n"
                "    The Router treats them as a single group: it spreads the load between them, and\n"
                "    automatically puts the one that takes a 429 into cooldown so as to route to the\n"
                "    other. The two people therefore relay each other the moment one is exhausted,\n"
                "    without one \"fallbacks\" line having been written. Give each account a distinct\n"
                "    model_name."
                % (path, name, ", ".join(accounts))
            )

    # Rule 2 -- an entry the check cannot attribute is reported, not ignored.
    for entry in entries:
        account, reason = account_of_reference(entry["api_key"])
        if account:
            continue
        problems.append(
            "%s: the entry \"%s\" has no identifiable account: %s.\n"
            "    None of the isolation rules can apply to it. Write the key in the form\n"
            "    \"api_key: os.environ/<PROVIDER>_API_KEY_<ACCOUNT>\", as #2 prescribes."
            % (path, entry["model_name"], reason)
        )

    # Rule 3 -- the label has to say the same thing as the key.
    # A mislabelled entry is not a typo: it is what makes rule 4 unreadable, since a reviewer
    # judges a fallback on the name they see.
    for entry in entries:
        account, _ = account_of_reference(entry["api_key"])
        if not account or account is SHARED or not isinstance(entry["model_name"], str):
            continue
        suffix = entry["model_name"].rsplit("-", 1)[-1].upper()
        if suffix != account and suffix in accounts_seen:
            problems.append(
                "%s: the model_name \"%s\" announces account \"%s\" but its key belongs to \"%s\".\n"
                "    The label lies: a reviewer judging a fallback on the name they read gets it wrong."
                % (path, entry["model_name"], suffix, account)
            )
        for group in entry["access_groups"]:
            if group.upper() != account and group.upper() in accounts_seen:
                problems.append(
                    "%s: \"%s\" is in the access_group \"%s\" but its key belongs to \"%s\".\n"
                    "    One team's allow list would hand out access to the other's key."
                    % (path, entry["model_name"], group, account)
                )

    # Rule 4 -- the fallbacks.
    for section_name in SETTINGS_SECTIONS:
        section = document.get(section_name) if isinstance(document, dict) else None
        for key, source, targets in normalise_fallbacks(section):
            if source is None:
                problems.append(
                    "%s: \"%s.%s\" applies to ALL the model groups at once, so also to those of the\n"
                    "    other account: it crosses every boundary in one go. Write the fallbacks one by\n"
                    "    one under \"fallbacks\", or have none at all."
                    % (path, section_name, key)
                )
                continue
            source_account = account_of_model.get(source)
            if source_account is None:
                continue
            for target in targets:
                target_account = account_of_model.get(target)
                if target_account is not None and target_account != source_account:
                    problems.append(
                        "%s: \"%s.%s\" makes \"%s\" (account %s) fall back on \"%s\" (account %s).\n"
                        "    A legitimate call by one would spend the other's quota. A fallback stays\n"
                        "    inside the keys of ONE SINGLE person."
                        % (path, section_name, key, source, source_account, target, target_account)
                    )
    return problems


def load(path):
    """(document, error). One of the two is None."""
    try:
        with open(path, encoding="utf-8") as handle:
            raw = handle.read()
    except (OSError, UnicodeDecodeError) as error:
        return None, "unreadable (%s)" % error.__class__.__name__
    try:
        return yaml.safe_load(neutralise_jinja(raw)), None
    except yaml.YAMLError as error:
        return None, "invalid YAML even once the Jinja is neutralised (%s)" % (
            str(error).splitlines()[0] if str(error) else error.__class__.__name__
        )


def check_file(path):
    """The problems of a file. A file that cannot be read IS a problem."""
    document, error = load(path)
    if error:
        if not is_litellm_configuration_by_text(path):
            return []
        return [
            "%s: %s.\n"
            "    A file the check cannot read is not a compliant file: for as long as it is not\n"
            "    parsable, nobody at all is verifying the isolation of the accounts in it."
            % (path, error)
        ]
    return check_document(path, document)


def is_litellm_configuration_by_text(path):
    """Last resort when the parsing fails: does the file TALK about model_list?"""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return "model_list" in handle.read()
    except OSError:
        return False


def configuration_files(root):
    """The files that declare a "model_list", recognised by their CONTENT."""
    paths = []
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [d for d in subdirectories if d not in SKIPPED_DIRECTORIES]
        if os.path.abspath(directory).startswith(SELFTEST_DIRECTORY):
            continue
        for name in sorted(files):
            if not name.endswith(CANDIDATE_SUFFIXES):
                continue
            path = os.path.join(directory, name)
            document, error = load(path)
            if error:
                if is_litellm_configuration_by_text(path):
                    paths.append(path)
                continue
            if isinstance(document, dict) and "model_list" in document:
                paths.append(path)
    return sorted(paths)


def run_selftest():
    """Prove that the check catches what it claims to catch.

    #32's Definition of Done asks that the check "fail on a deliberately faulty configuration --
    tested, not assumed". That is what this function does, and it is also what gives the file a
    value TODAY, before #2 has produced the slightest real configuration to read.

    Each fixture announces, in its first few lines, the number of problems expected AND a fragment
    the first of them has to contain. Comparing a NUMBER alone was not enough: half of the watched
    surface could disappear without the count moving.
    """
    if not os.path.isdir(SELFTEST_DIRECTORY):
        print("selftest: fixture directory not found: %s" % SELFTEST_DIRECTORY)
        return 1

    failures = 0
    names = sorted(name for name in os.listdir(SELFTEST_DIRECTORY)
                   if os.path.isfile(os.path.join(SELFTEST_DIRECTORY, name)))
    if not names:
        print("selftest: no fixture")
        return 1

    for name in names:
        path = os.path.join(SELFTEST_DIRECTORY, name)
        # The declaration is looked for in the first few lines rather than on line 1, so that a
        # fixture can carry a NORMAL SPDX header like every other file of the repository.
        #
        # It used to share line 1 with both SPDX tags, and "reuse lint" saw a copyright there but no
        # licence. The reason is NOT that a tag must start its line -- measured, a tag placed mid-line
        # after a "--" IS read. It is that a tag's value runs to the END of its line, so the
        # copyright tag swallowed the licence tag that followed it on the same line as part of the
        # holder's name, and no licence tag was left. Two tags cannot share one line. The nine
        # fixtures were the only files the tool reported.
        #
        # ! The paragraph above quoted that malformed line in full, and "reuse lint" then read the
        #   quotation as a REAL tag and failed on the prose that followed it as an invalid licence
        #   expression -- the comment explaining the trap fell into it. REUSE's own escape hatch is
        #   a REUSE-IgnoreStart / REUSE-IgnoreEnd pair, which is what the homelab repository uses in
        #   its ".yamllint" for the same reason. Here the quotation is simply gone instead: not
        #   naming the tag says the same thing and costs nothing.
        with open(path, encoding="utf-8") as handle:
            head = "".join(handle.readline() for _ in range(6))
        expected = re.search(r"EXPECTED\s*:\s*(\d+)", head)
        fragment = re.search(r"CONTAINS\s*:\s*(.+?)\s*$", head, re.MULTILINE)
        if not expected:
            print("selftest: %s does not announce its expected number of problems" % name)
            failures += 1
            continue
        problems = check_file(path)
        count = int(expected.group(1))
        if len(problems) != count:
            failures += 1
            print("selftest: %s -> %d problem(s), %d expected" % (name, len(problems), count))
            for problem in problems:
                print("    " + problem.splitlines()[0])
            continue
        if count and fragment:
            wanted = fragment.group(1)
            if not any(wanted in problem for problem in problems):
                failures += 1
                print("selftest: %s -> the right NUMBER of problems, but none of them contains \"%s\""
                      % (name, wanted))
                for problem in problems:
                    print("    " + problem.splitlines()[0])
                continue
        print("selftest: %s -> %d problem(s), conforming" % (name, len(problems)))
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="verify the check against its fixtures instead of reading the repository",
    )
    parser.add_argument("--root", default=".", help="root of the repository to walk")
    arguments = parser.parse_args()

    if arguments.selftest:
        return run_selftest()

    paths = configuration_files(arguments.root)
    if not paths:
        # Green, but talkative: nobody is to believe this check has validated anything at all.
        print(
            "No LiteLLM configuration found: #2 has not produced it yet, so there is nothing to\n"
            "read. This check becomes effective without anyone touching it the day the file exists,\n"
            "whatever its name -- it is recognised by its \"model_list\", not by its file name.\n"
            "Its ability to spot a fault is verified right now by \"--selftest\"."
        )
        return 0

    problems = []
    for path in paths:
        problems.extend(check_file(path))

    if problems:
        print("LiteLLM account isolation: %d problem(s).\n" % len(problems))
        for problem in problems:
            print(problem + "\n")
        return 1

    print("LiteLLM account isolation: %d file(s) read, no problem." % len(paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
