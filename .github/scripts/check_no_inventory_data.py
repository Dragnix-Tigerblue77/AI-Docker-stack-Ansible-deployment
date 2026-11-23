#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77 and the AI Docker stack Ansible deployment contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Refuse an IP address or a domain name hardcoded into the repository, and a person's name in the role's interface.

WHY THIS CHECK EXISTS
---------------------
This repository's role is parameterisable: it is the caller that supplies the inventory, the FQDNs,
the Traefik labels and the network (#22, #31, #33). An address or a host name written here is
therefore not only a leak of information about the homelab -- it is a functional regression, since
the role stops being reusable by anyone else. Nothing else in this CI can see it: a hardcoded FQDN
is valid YAML, and yamllint and ansible-lint alike let it through.

WHY AN ALLOWLIST, AND NOT A DENYLIST
------------------------------------
It is the only possible shape. A denylist would have to enumerate the forbidden domains -- so to
WRITE the homelab's domain into a versioned file, which is exactly what the rule forbids. The check
is therefore the other way round: everything that looks like a host is refused, except the few
upstream hosts the repository has to name in order to work, each with its reason below.

The corollary is accepted: the allowlist will grow. That is intended. Adding an upstream host is a
one-line gesture, which leaves a trace in a diff and asks for its justification; that is precisely
the control one wants to have over this category of value.

WHAT IT DOES NOT DO
-------------------
* It does not see a host name WITHOUT a dot ("myhost01"), which the rule nonetheless names first. No
  mechanical rule tells such a name from an ordinary word; that one is a human read-through.
* It does not read the issues. Neither does gitleaks, and GitHub's secret scanning would want a
  plan the organisation does not have. The content of the issues remains a human vigilance.

A PERSON'S NAME IN THE ROLE'S INTERFACE
----------------------------------------
The role is used by third parties, so nothing it exposes may name a person: a variable, an
environment variable, a service, a label, a volume or a task name that carries a maintainer's name
makes every other caller write that name into their inventory. The same hunt as above, on another
category of value: PERSON_NAMES lists the names to refuse (case-insensitively, so an upper-case
environment variable is caught too), and INTERFACE_PATHS says where the role's interface lives --
"defaults/", "tasks/", "templates/", "vars/", "handlers/", "files/", "meta/", the example playbook,
and the table rows of the README, where the variables are documented. A comment in those files is
read like the rest: a rendered file's comments are deployed, and a name written there is the first
thing the next identifier copies.

This one IS a denylist, unlike the hosts above, and for the opposite reason: the names to refuse are
the maintainers' public handles, which are already written all over the repository (signatures,
licence, copyright), so listing them leaks nothing. The price is that a name that is not listed is
not seen: a new maintainer's handle is added to PERSON_NAMES in the commit that adds them. The
exceptions are in PERSON_ALLOWED, each with its reason; prose elsewhere (the README outside its
tables, CLAUDE.md, CONTRIBUTING.md, NOTICE, .claude/) is out of scope, since it is not the interface.

HOW A NAME IS RECOGNISED
------------------------
A "label.label[.label]" token whose LAST label appears in TOP_LEVEL_DOMAINS. That list is
deliberately short and does not try to be exhaustive: it keeps out the file extensions that are
also top-level domains and that would make the check scream over the whole repository -- ".sh"
(Saint Helena), ".py" (Paraguay), ".md" (Moldova), ".io" for a file, ".pl", ".so". A domain in
".sh" would therefore slip through; that is the price to pay for a check that does not shout at
"functions.sh", and it is the right side of the trade-off for a repository that will not have one.
"""

import os
import re
import sys

# The upstream hosts this repository is allowed to name. Every entry carries its reason: without it,
# the list becomes a catch-all and the check no longer means anything.
ALLOWED_HOSTS = {
    "github.com": "downloading releases and actions",
    "raw.githubusercontent.com": "raw content of a public repository",
    "api.github.com": "GitHub API",
    "objects.githubusercontent.com": "release download redirection",
    "docs.github.com": "documentation cited in a comment",
    "pypi.org": "installation of the tools in requirements.txt",
    "files.pythonhosted.org": "artefacts served by PyPI",
    "galaxy.ansible.com": "Ansible collections",
    "ghcr.io": "image registry",
    "docker.io": "image registry",
    "hub.docker.com": "image registry",
    "quay.io": "image registry",
    "docs.litellm.ai": "gateway documentation, cited in a comment",
    "code.claude.com": "Claude Code documentation, cited in .claude/README.md",
    "claude.ai": "address of a Claude Code session, in the signature CLAUDE.md prescribes for what a session posts on GitHub",
    "anthropic.com": "domain of the address a Claude Code session commits under, which check_sign_off.py refuses as a certifier",
    "users.noreply.github.com": "domain of the GitHub noreply addresses: the maintainer's, which check_sign_off.py expects on a commit a session authored, and the Actions bot's, author of the model-list deletion commit",
    "json.schemastore.org": "JSON schema referenced by .claude/settings.json for editor validation",
    "ai.google.dev": "Gemini terms of use, cited in #2",
    "generativelanguage.googleapis.com": "Google AI Studio's OpenAI-compatible endpoint, and the model catalogue check_LiteLLM_model_drift.py reads",
    "api.sambanova.ai": "SambaNova's API endpoint, in the entries the model list keeps commented out, and its keyless model catalogue check_LiteLLM_model_drift.py reads",
    "api.deepseek.com": "DeepSeek's own API endpoint, named in a comment -- LiteLLM already knows it and needs no \"api_base\" -- and the model catalogue check_LiteLLM_model_drift.py reads",
    "api-docs.deepseek.com": "DeepSeek's own API documentation, cited in a comment (#101)",
    "docs.mistral.ai": "Mistral AI's own model documentation, cited in comments (#112)",
    "mistral.ai": "Mistral AI's own pricing page, the one place its Free mode credit is stated, cited in a comment (#200)",
    "cloud.sambanova.ai": "SambaNova's own console plans page, cited in a comment for what a new account meets (#200)",
    "docs.sambanova.ai": "SambaNova's own rate-limits documentation, cited in a comment (#200)",
    "inference-docs.cerebras.ai": "Cerebras' own model documentation and deprecation notice, cited in comments (#110)",
    "console.groq.com": "Groq's own deprecation notice, rate limits and built-in tools documentation, cited in comments (#169)",
    "openrouter.ai": "OpenRouter's own live model catalog, cited in a comment and read by check_LiteLLM_model_drift.py",
    "api.cerebras.ai": "Cerebras' keyless public model catalogue, read by check_LiteLLM_model_drift.py",
    "api.groq.com": "Groq's model catalogue, read by check_LiteLLM_model_drift.py when its key is set",
    "api.mistral.ai": "Mistral's model catalogue, read by check_LiteLLM_model_drift.py when its key is set",
    "api.cloudflare.com": "Cloudflare's API, whose model catalogue of Workers AI check_LiteLLM_model_drift.py reads when its token and account identifier are set",
    "tbench.ai": "an independent coding-agent leaderboard, cited in a comment",
    "artificialanalysis.ai": "Artificial Analysis's free ranking API, read by check_LiteLLM_model_drift.py when its key is set, and the source its terms ask the report to cite",
    "epoch.ai": "Epoch AI's benchmark data, the source of code quality in the router contracts, read by check_LiteLLM_model_drift.py (CC BY 4.0, to be cited)",
    "developers.cloudflare.com": "Cloudflare's own Workers AI pricing, limits, data usage and model pages, cited in the README ledger of free providers and in the comments of the model list",
    "www.cloudflare.com": "Cloudflare's own terms of service page, cited in the README ledger of free providers and in the comments of the role's variables and of the model list",
    "docs.z.ai": "Z AI's own pricing, model, introduction and terms of use pages, cited in the README ledger of free providers and in the comments of the role's variables and of the model list",
    "router.eu.requesty.ai": "Requesty's own European OpenAI-compatible endpoint, the api_base of its entries in the model list: a public service address, not the caller's",
    "api.cent-ai.dev": "Cent AI's own OpenAI-compatible endpoint, the api_base of its entry in the model list: a public service address, not the caller's",
    "api.z.ai": "Z AI's own model catalogue, read by check_LiteLLM_model_drift.py when its key is set",
    "integrate.api.nvidia.com": "NVIDIA's own keyless model catalogue, read by check_LiteLLM_model_drift.py",
    "build.nvidia.com": "NVIDIA's own API catalogue home page, where its free offer is stated, linked by check_LiteLLM_model_drift.py",
    "cent-ai.dev": "Cent AI's own home page, where its free model is announced, linked by check_LiteLLM_model_drift.py",
    "requesty.ai": "Requesty's own domain, which the api_base of its entries in the model list is matched on by check_LiteLLM_model_drift.py and the builder of its workflow",
    "router.requesty.ai": "Requesty's other, American OpenAI-compatible endpoint, which check_LiteLLM_model_drift.py attributes to Requesty as it does the European one",
    "kilo.ai": "Kilo's own gateway models page and terms, cited in the README ledger of free providers",
    "ai-gateway.kilo.ai": "Kilo's own OpenAI-compatible gateway, the api_base of its entries in the model list: a public service address, not the caller's",
    "oai.endpoints.kepler.ai.cloud.ovh.net": "OVHcloud AI Endpoints' own keyless OpenAI-compatible endpoint, the api_base of its entries in the model list: a public service address, not the caller's",
    "www.ovhcloud.com": "OVHcloud's own AI Endpoints service and catalogue pages, cited in the README ledger of free providers",
    "assets.ngc.nvidia.com": "NVIDIA's own API trial terms of service, cited in the README ledger of free providers",
    "docs.cohere.com": "Cohere's own rate limits page, cited in the README ledger of free providers",
    "www.cohere.com": "Cohere's own terms of use page, cited in the README ledger of free providers",
    "docs.ovhcloud.com": "OVHcloud's own AI Endpoints getting started page, cited in the README ledger of free providers",
    "huggingface.co": "Hugging Face's own Inference Providers pricing page, cited in the README ledger of free providers",
    "chutes.ai": "Chutes' own pricing page, cited in the README ledger of free providers",
    "ollama.com": "Ollama's own pricing page, cited in the README ledger of free providers",
    "platform.kimi.ai": "Moonshot's own pricing limits page, cited in the README ledger of free providers",
    "www.alibabacloud.com": "Alibaba Cloud's own Model Studio free quota page, cited in the README ledger of free providers",
    "www.siliconflow.com": "SiliconFlow's own pricing page, cited in the README ledger of free providers",
    "vercel.com": "Vercel's own AI Gateway pricing page, cited in the README ledger of free providers",
    "www.together.ai": "Together AI's own pricing page, cited in the README ledger of free providers",
    "docs.fireworks.ai": "Fireworks' own rate limits page, cited in the README ledger of free providers",
    "developercertificate.org": "official text of the Developer Certificate of Origin, cited in CONTRIBUTING.md",
    "fsf.org": "licence text",
    "www.gnu.org": "licence text",
    "spdx.org": "licence identifiers",
    "reuse.software": "specification of the licence headers",
}

# The addresses that designate no machine and that a configuration file has to be able to write:
# they say nothing about the homelab.
ALLOWED_ADDRESSES = {
    "0.0.0.0": "listen on every interface",
    "127.0.0.1": "loopback",
    "255.255.255.255": "broadcast",
    "::1": "IPv6 loopback",
}

# Deliberately short: see the docstring. Every file extension used in this repository is kept out of
# it, even when it is a genuine top-level domain.
TOP_LEVEL_DOMAINS = {
    # Generic
    "com", "net", "org", "io", "dev", "ai", "cloud", "info", "tech", "xyz", "tv", "cc",
    # Countries and regions plausible for this household and its providers
    "fr", "eu", "be", "ch", "de", "uk", "nl", "es", "it", "nf", "re", "pm", "yt", "ovh",
    "co", "me",
    # Local-network pseudo-domains: THESE are the ones a homelab writes by accident
    "lan", "local", "home", "internal", "intranet", "box", "arpa",
}

# The top-level domains that are also ordinary WORDS -- "email", "services", "tools", "network",
# "systems", "digital", "zone", "host", "site", "space", "link", "live", "app", "online",
# "website" -- are deliberately absent. Measured: including them makes "git config user.email" in
# a workflow of this repository be refused, and the same collision would happen on any dotted
# identifier. They are also the least plausible TLDs for a household's domain: little coverage is
# lost, and much precision is gained.

# The paths the check does not read, with their reason.
SKIPPED_PATHS = {
    # ! "LICENSES/AGPL-3.0-only.txt" is a SYMLINK to "LICENSE" and is NOT skipped: the check reads
    #   the whole AGPL text through it on every run. It passes because "fsf.org" and
    #   "www.gnu.org" are in ALLOWED_HOSTS, which is a real reason and not luck -- but it is worth
    #   knowing that the licence text is scanned rather than assuming this entry still covers it.
    "LICENSE": "upstream AGPL text, neither written nor editable here",
    ".git": "git's internal data",
    # None of this is versioned, and all of it exists on a contributor's machine. Without these
    # lines, the command CONTRIBUTING.md asks to run goes red over thousands of files from the very
    # first "python3 -m venv .venv" (measured: 1457 findings).
    ".venv": "local virtual environment, not versioned",
    "venv": "local virtual environment, not versioned",
    "node_modules": "local dependencies, not versioned",
    "__pycache__": "Python cache",
    ".ansible": "ansible-lint's cache",
    ".mypy_cache": "local cache",
    ".pytest_cache": "local cache",
}

# The names no identifier of the role's interface may carry, matched case-insensitively as substrings
# so that "Claude_code_<name>_enabled", "<NAME>_API_KEY" and "claude-code-<name>" are all caught.
# Add a maintainer's handle here in the commit that adds the maintainer.
PERSON_NAMES = ("tigerblue77", "dragnix")

# Where the role's interface lives: a path is in scope when it starts with one of these directories
# or is one of these files. The README is handled separately (its table rows only, where the
# variables are documented), and the checks, the workflows, CLAUDE.md, CONTRIBUTING.md, NOTICE and
# .claude/ are deliberately outside: none of them is something a caller reads or writes.
INTERFACE_DIRECTORIES = ("defaults/", "tasks/", "templates/", "vars/", "handlers/", "files/", "meta/")
INTERFACE_FILES = ("playbook.Artificial_Intelligence.example.yaml",)
README_PATH = "README.md"

# What may carry a name in those files, each with its reason: the pattern is removed from the line
# before the names are looked for, so it exempts that text and nothing else on the line.
PERSON_ALLOWED = (
    (re.compile(r"SPDX-FileCopyrightText:.*", re.IGNORECASE),
     "the copyright holder is a legal fact, not an identifier"),
    (re.compile(r"ghcr\.io/dragnix-tigerblue77/claude-code-docker-container", re.IGNORECASE),
     "the image is published under the organisation's namespace, which the role has to name to pull it"),
    (re.compile(r"Dragnix-Tigerblue77/Claude-Code-Docker-container", re.IGNORECASE),
     "the repository that builds and publishes that image, cited where the template pulls it"),
    (re.compile(r"^\s*author:.*"),
     "galaxy_info.author of meta/main.yml names the author, as Galaxy asks; it is not an interface"),
)

# A region the check skips, delimited in the file itself. It exists for ONE case: a block whose
# content IS a counter-example, like the verification cases further down -- this file reads itself,
# and without this it would refuse its own test cases.
#
# ! This is a bounded exemption, not an excluded file. The difference is the heart of the matter:
#   skipping the whole file would make it the one place in the repository where a real address would
#   go unnoticed, and it would be the check's own file. A delimited region, on the other hand, shows
#   up in a diff, and the count of the regions traversed is printed on every run so that they do not
#   multiply in silence.
#
# The two markers are assembled from two pieces, and that is not an affectation: written whole, they
# would open a region on their own definition line -- the check would then skip the two lines that
# configure it, with nothing to say so. Measured.
IGNORE_START = "CONTROLE-" + "IgnoreStart"
IGNORE_END = "CONTROLE-" + "IgnoreEnd"

# A token that looks like a host name. The last label is then filtered against TOP_LEVEL_DOMAINS;
# the regex alone does not tell a file name from a host name.
#
# ! Do not write an example domain in this file, not even in a comment: the check reads itself
#   and would refuse it, which is the intended behaviour (measured).
HOSTNAME = re.compile(r"\b(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}\b")

IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# IPv6: only the forms that cannot be anything else. Requiring a "::" or eight groups rules out
# "20:25:30", which is a time of day, and "12:34:56:78", which is a truncated MAC address.
IPV6 = re.compile(
    r"(?<![0-9A-Za-z:])(?:"
    r"(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,7}:(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,6})?"
    r"|::(?:[0-9A-Fa-f]{1,4}:){0,6}[0-9A-Fa-f]{1,4}"
    r")(?![0-9A-Za-z:])"
)


def is_ipv4(candidate):
    parts = candidate.split(".")
    return len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts)


def is_person_scope(relative_path, line):
    """Is this line of this file part of the role's interface?"""
    path = relative_path.replace(os.sep, "/")
    if path == README_PATH:
        return line.lstrip().startswith("|")
    return path in INTERFACE_FILES or path.startswith(INTERFACE_DIRECTORIES)


def person_findings_in_line(relative_path, line):
    """The person names a line of the role's interface carries: [name]."""
    if not is_person_scope(relative_path, line):
        return []
    for pattern, _reason in PERSON_ALLOWED:
        line = pattern.sub("", line)
    lowered = line.lower()
    return [name for name in PERSON_NAMES if name in lowered]


def is_skipped(relative_path):
    parts = relative_path.split(os.sep)
    return any(part in SKIPPED_PATHS for part in parts)


def is_binary(path):
    try:
        with open(path, "rb") as handle:
            return b"\0" in handle.read(4096)
    except OSError:
        return True


def findings_in_line(line, file_names=frozenset()):
    """The findings of one line: (category, value)."""
    found = []

    for match in IPV4.finditer(line):
        value = match.group(0)
        if is_ipv4(value) and value not in ALLOWED_ADDRESSES:
            found.append(("IPv4 address", value))

    for match in IPV6.finditer(line):
        value = match.group(0)
        if value not in ALLOWED_ADDRESSES:
            found.append(("IPv6 address", value))

    for match in HOSTNAME.finditer(line):
        value = match.group(0)
        if is_ipv4(value):
            continue  # already handled above, and an IP is not a name
        if value.rsplit(".", 1)[-1].lower() not in TOP_LEVEL_DOMAINS:
            continue
        if value.lower() in ALLOWED_HOSTS:
            continue
        if value in file_names:
            continue
        found.append(("domain name", value))

    return found


def repository_file_names(root):
    """The file names present in the tree.

    They serve to avoid mistaking a file for a host: a README in ".org", a logo in ".ai", a
    Dockerfile in ".dev" all carry a suffix that is a genuine top-level domain, and none of them
    is an address.

    The trade-off is accepted and symmetrical: a file someone named like a domain would escape the
    check. That is a case nobody has ever seen, against false positives one would get on every
    file added.

    ! The examples above are spelled out in words rather than as "name.suffix" because this file
      reads itself: writing them normally would have them refused. Wrapping the paragraph in an
      ignored region would have worked too, and would have been worse -- one more exemption, for
      a comment.
    """
    names = set()
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [name for name in subdirectories if name not in SKIPPED_PATHS]
        names.update(files)
        names.update(subdirectories)
    return names


def walk(root):
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [name for name in subdirectories if name not in SKIPPED_PATHS]
        for name in sorted(files):
            path = os.path.join(directory, name)
            relative = os.path.relpath(path, root)
            if is_skipped(relative) or is_binary(path):
                continue
            yield path, relative


# The verification cases, built IN MEMORY rather than in fixture files.
# The reason is direct: a fixture containing an address would have to be excluded from the walk for
# the check to stay green, and that excluded directory would become the one place in the repository
# where a real leak would go unnoticed. An in-memory case does not create that blind spot.
# CONTROLE-IgnoreStart
SELFTEST_CASES = (
    # (line, number of findings expected, what the case proves)
    ("  serveur: 192.168.1.42", 1, "a private address is refused"),
    ("  bind: 0.0.0.0", 0, "listening on every interface stays allowed"),
    ("  boucle: 127.0.0.1", 0, "the loopback stays allowed"),
    ("  hote: 2001:0db8:85a3:0000:0000:8a2e:0370:7334", 1, "a full IPv6 is refused"),
    ("  abrege: fe80::1ff:fe23:4567", 1, "an abbreviated IPv6 is refused"),
    ("  heure: 20:25:30", 0, "a time of day is not an IPv6"),
    ("  version: 8.30.1", 0, "a version number is not an address"),
    ("  fichier: requirements.txt", 0, "a file name is not a domain"),
    ("  script: functions.sh", 0, "an extension that is also a TLD does not count"),
    ("  module: ansible.builtin.assert", 0, "a module name is not a domain"),
    ("  cle: os.environ/GEMINI_API_KEY_TEAM_A", 0, "a variable is not a domain"),
    ("  playbook: playbook.Artificial_Intelligence.example.yaml", 0, "a playbook name is not a domain"),
    ("  regle: traefik.http.routers.ais.rule", 0, "a Traefik label is not a domain"),
    ("  url: https://github.com/gitleaks/gitleaks", 0, "an upstream host in the allowlist passes"),
    ("  fqdn: ais.un-domaine-quelconque.fr", 1, "an FQDN outside the allowlist is refused"),
    ("  # commente: ais.un-domaine-quelconque.fr", 1, "a comment is read like the rest"),
)
# CONTROLE-IgnoreEnd

# (path, line, number of findings expected, what the case proves). In an ignored region for the same
# reason as the cases above: this file is not in scope itself, but the names would be read as a leak
# by anything that greps the tree.
# CONTROLE-IgnoreStart
SELFTEST_PERSON_CASES = (
    ("defaults/main.yml", "Artificial_Intelligence_Claude_code_tigerblue77_enabled: false", 1,
     "a variable that names a person is refused"),
    ("templates/Artificial_Intelligence.docker-compose.yml.j2", "      GEMINI_API_KEY_TIGERBLUE77: x", 1,
     "an upper-case environment variable is refused as well"),
    ("templates/Artificial_Intelligence.docker-compose.yml.j2", "  claude_code_tigerblue77:", 1,
     "a service name is refused"),
    ("tasks/main.yml", "# Dragnix adds his own models later", 1,
     "a comment is read like the rest"),
    ("playbook.Artificial_Intelligence.example.yaml", "  username: Dragnix", 1,
     "the example playbook is part of the interface"),
    ("README.md", "| `Artificial_Intelligence_LibreChat_Dragnix_email` | aucun | Dépréciée. |", 1,
     "a README table row, where the variables are documented, is refused"),
    ("README.md", "décision de Dragnix, validée par tigerblue77", 0,
     "README prose outside its tables is not the interface"),
    ("CONTRIBUTING.md", "| `tigerblue77` |", 0, "a file outside the interface is not read"),
    (".claude/agents/doc-keeper.md", "tigerblue77", 0, "agent instructions are not the interface"),
    ("defaults/main.yml", "# SPDX-FileCopyrightText: 2026 Tigerblue77", 0,
     "the copyright line is allowed"),
    ("templates/Artificial_Intelligence.docker-compose.yml.j2",
     "    image: ghcr.io/dragnix-tigerblue77/claude-code-docker-container", 0,
     "the published image path is allowed"),
    ("templates/Artificial_Intelligence.docker-compose.yml.j2",
     "    # Built and published by Dragnix-Tigerblue77/Claude-Code-Docker-container, which", 0,
     "the repository that publishes the image is allowed"),
    ("meta/main.yml", "  author: tigerblue77", 0, "the galaxy author field is allowed"),
    ("defaults/main.yml", "image: ghcr.io/dragnix-tigerblue77/claude-code-docker-container # tigerblue77", 1,
     "an allowed text exempts only itself, not the rest of the line"),
    ("defaults/main.yml", "Artificial_Intelligence_Claude_code_enabled: false", 0,
     "a neutral variable passes"),
)
# CONTROLE-IgnoreEnd


def run_selftest():
    """Prove that the check refuses what it claims to refuse, and accepts the rest.

    A check whose failure nobody has ever seen is a check nobody believes -- and this one carries
    an allowlist, so its own risk is to let everything through in silence.
    """
    failures = 0
    for line, expected, purpose in SELFTEST_CASES:
        found = findings_in_line(line)
        if len(found) != expected:
            failures += 1
            print("selftest: FAILED (%s) -- %d finding(s), %d expected: %s"
                  % (purpose, len(found), expected, line.strip()))
        else:
            print("selftest: ok -- %s" % purpose)
    for path, line, expected, purpose in SELFTEST_PERSON_CASES:
        found = person_findings_in_line(path, line)
        if len(found) != expected:
            failures += 1
            print("selftest: FAILED (%s) -- %d finding(s), %d expected: %s: %s"
                  % (purpose, len(found), expected, path, line.strip()))
        else:
            print("selftest: ok -- %s" % purpose)
    return 1 if failures else 0


def main():
    arguments = [argument for argument in sys.argv[1:] if argument != "--selftest"]
    if "--selftest" in sys.argv[1:]:
        return run_selftest()
    root = arguments[0] if arguments else "."
    problems = []
    person_problems = []
    ignored_regions = []
    file_names = repository_file_names(root)

    for path, relative in walk(root):
        try:
            with open(path, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        except OSError as error:
            problems.append((relative, 0, "unreadable file", error.__class__.__name__))
            continue
        except UnicodeDecodeError:
            # ! Reported, and not skipped in silence. A file this check cannot decode is a file
            #   where an address can hide without anyone seeing it: it is the one blind spot it
            #   must not grant itself. Measured: a latin-1 file containing a private address came
            #   back "no finding", exit 0.
            problems.append((
                relative, 0, "non-UTF-8 file",
                "not decodable, therefore not checked; convert it to UTF-8",
            ))
            continue

        ignoring = False
        opened_at = None
        for number, line in enumerate(lines, start=1):
            if IGNORE_START in line:
                ignoring = True
                opened_at = number
                ignored_regions.append((relative, number))
                continue
            if IGNORE_END in line:
                ignoring = False
                opened_at = None
                continue
            if ignoring:
                continue
            for category, value in findings_in_line(line, file_names):
                problems.append((relative, number, category, value))
            for name in person_findings_in_line(relative, line):
                person_problems.append((relative, number, name))

        if ignoring:
            # A region never closed again swallows the whole rest of the file. Without this check
            # here, accidentally deleting an end marker silently disables half a file -- and the
            # count of the regions, for its part, would not have moved.
            problems.append((
                relative, opened_at, "ignored region never closed again",
                "the whole rest of the file was skipped; add the end marker",
            ))

    if ignored_regions:
        # Printed on BOTH paths, green as well as red: an ignored region is an exemption, and an
        # exemption that is only visible half the time ends up covering others.
        print("%d explicitly ignored region(s):" % len(ignored_regions))
        for relative, number in ignored_regions:
            print("  %s:%d" % (relative, number))
        print("")

    if problems:
        print("Hardcoded inventory data: %d finding(s).\n" % len(problems))
        for relative, number, category, value in problems:
            print("%s:%d: %s \"%s\"" % (relative, number, category, value))
        print(
            "\nThese values belong to the caller's inventory, not to this repository: a role that\n"
            "carries them stops being reusable, and publishes the homelab on the way. Pass\n"
            "them as variables.\n"
            "\n"
            "If this is an UPSTREAM host the repository legitimately has to name, add it to\n"
            "ALLOWED_HOSTS in %s WITH ITS REASON, in the same commit."
            % os.path.relpath(os.path.abspath(__file__), os.path.abspath(root))
        )
        return 1

    if person_problems:
        print("A person's name in the role's interface: %d finding(s).\n" % len(person_problems))
        for relative, number, name in person_problems:
            print("%s:%d: person name \"%s\"" % (relative, number, name))
        print(
            "\nThe role is used by third parties: nothing it exposes -- a variable, an environment\n"
            "variable, a service, a label, a volume, a task name, a comment of a rendered file -- may\n"
            "name a person. Name what the thing IS, not who it was written for.\n"
            "\n"
            "If a name legitimately has to appear (a publisher's namespace, say), add it to\n"
            "PERSON_ALLOWED in %s WITH ITS REASON, in the same commit."
            % os.path.relpath(os.path.abspath(__file__), os.path.abspath(root))
        )
        return 1

    print("No hardcoded IP address or domain name, and no person's name in the role's interface.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
