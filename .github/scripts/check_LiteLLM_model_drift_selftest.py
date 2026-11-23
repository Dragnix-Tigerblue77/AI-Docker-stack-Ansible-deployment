#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77
# SPDX-License-Identifier: AGPL-3.0-only

"""The verification cases of "check_LiteLLM_model_drift.py": its data, its cases and the loop that
judges them, kept apart from the script so that a change to either is read without the other.

The script's "--selftest" runs this module, and it can be run directly, from anywhere:

    python3 .github/scripts/check_LiteLLM_model_drift_selftest.py

It exits 0 when every case judged as expected and 1 otherwise. The cases are Python literals rather
than fixture files, for the reason the script gives: a fixture on disk is reachable by
"ansible-lint --fix". The scripts directory is flat and not a package, so the script is imported by
its file name, which is what puts this directory on the path whichever way this module was started.
"""

import collections
import contextlib
import difflib
import http.client
import http.server
import io
import json
import os
import re
import runpy
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_LiteLLM_model_drift as drift  # noqa: E402
from check_LiteLLM_model_drift import (
    ADDITION_ID, DEFAULT_BASES, FREE_READINGS, FREE_SUFFIX, KEYLESS_GATEWAYS, OPENAI_COMPATIBLE,
    PROVIDER_LABELS, addition_anchor, addition_entries, provider_basis, snippet, ADDITION_NAME,
    ADDITION_NAME_LIMIT, CLOUDFLARE_PER_PAGE, NAME_SUFFIXES, SAFE_MODEL_ID, BANNER_RULE, CONFIG,
    CONTRACTS, CRASH_STATUS,
    DRIFT_IGNORE_START, EPOCH_ECI_KEY, EPOCH_ECI_MEMBER, EPOCH_FILES, EPOCH_KEYS,
    EPOCH_MAX_ARCHIVE, EPOCH_URL, FREE_CATALOGUES, FREE_READABLE, FREE_TIER_CHECKS, FetchError,
    JINJA_PLACEHOLDER, LOOKUPS, LOOKUP_LIMIT, MAX_PAGES, PRICING_PAGES, PROPOSAL_LIMIT,
    PROPOSAL_SIGNATURE, PROVIDERS, PROVIDER_KEY_VARIABLES, PROVIDER_NAMES, Path, RANKING_LISTED,
    RANKING_URL, REASON, REFUSALS, REVIEW_HEADING, SETTINGS_SECTIONS, TIMEOUT, UNCARRIED_HEADING,
    WORD, absent_names, addition_name, addition_problem, alias_drift, anchor_floor, anchor_scale,
    apply_removals, apply_to_result, ask_for, attribute, build_additions, carried_sections,
    catalogue_command, catalogue_url, changed_heads, chat_like, chosen_level, code_figure, code_points,
    code_span, comment_content, confirm_absences, contract_order, contracts_problems, time_worth, shared_quota_names,
    contracts_report, contracts_section, derivation_differences, derivation_lines, describe_entry,
    eci_scale, eci_to_index, epoch_member_name, epoch_position, error_class, exit_status,
    fallback_lists, fetch_json, floor_text, given_text, guarded, index_to_position, is_bare,
    is_comment, is_complete, is_zero, jinja_balance, jinja_refusal, keyed, keyset_documents,
    left_behind, left_outside_pull_requests, main, match_ranking, median_position, member_quality,
    offline_contract_notices, offline_contract_problems, place, plan_lines, pricing_page_problems,
    propose_additions, propose_name, proposed, ranking_families, read_catalogue, read_epoch, read_head,
    read_layout, read_ranking_models, read_template, refusal_text, render_commit_message,
    render_pr_body, render_summary, render_text, render_with_keys, rewrite_heads, router_quality,
    run_online, seconds_figure, slots_text, split_level, squash, TEMPLATE_SWITCHES, time_ties,
    undeleted_count, unreadable_providers, urllib_opener, verify_removal,
)


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

  - model_name: kilo-one
    litellm_params:
      model: openai/vendor/kilo-one:free
      api_base: "https://ai-gateway.kilo.ai/api/v1"
      api_key: "kilo-selftest-marker"
      extra_headers:
        Authorization: ""

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
    ("a switch of the configuration is read at its default and is no finding",
     ("router_settings:\n",
      "general_settings:\n{% if Artificial_Intelligence_LiteLLM_disable_env_credential_login %}\n"
      "  disable_env_credential_login: true\n{% endif %}\nrouter_settings:\n"), None),
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


def kilo_model(identifier, free=True, outputs=("text",), expiration=None):
    return {"id": identifier, "name": identifier, "isFree": free, "mayTrainOnYourPrompts": free,
            "architecture": {"output_modalities": list(outputs)}, "expiration_date": expiration}


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
        "kilo": {"data": [
            kilo_model("vendor/kilo-one:free"),
            kilo_model("vendor/kilo-paid", free=False),
            kilo_model("vendor/kilo-painter:free", outputs=("image",)),
            kilo_model("vendor/kilo-voice-tts:free"),
        ]},
        # SELFTEST_TEMPLATE has no Cloudflare entry: its catalogue holds a model that is no chat model.
        "cloudflare": [{"result": [{"name": "@cf/vendor/embed-9", "task": {"name": "Text Embeddings"}}],
                        "success": True}],
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
        "kilo": {"data": [kilo_model(i) for i in sorted(ids["kilo"])]},
        "cloudflare": [{"result": [{"name": i, "task": {"name": "Text Generation"}}
                                   for i in sorted(ids["cloudflare"])], "success": True}],
    }


SELFTEST_KEYS = {
    "MODEL_DRIFT_GEMINI_API_KEY": "selftest-gemini-key-SECRET",
    "MODEL_DRIFT_GROQ_API_KEY": "selftest-groq-key-SECRET",
    "MODEL_DRIFT_MISTRAL_API_KEY": "selftest-mistral-key-SECRET",
    "MODEL_DRIFT_DEEPSEEK_API_KEY": "selftest-deepseek-key-SECRET",
    "MODEL_DRIFT_CLOUDFLARE_API_KEY": "selftest-cloudflare-key-SECRET",
    "MODEL_DRIFT_CLOUDFLARE_ACCOUNT_ID": "0123456789abcdef0123456789abcdef",
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
        if "/ai/models/search?" in url:
            # Cloudflare's, paged "?page=N" like the ranking source's: a page nobody wrote is a read too far.
            answer = answers["cloudflare"]
            if isinstance(answer, list):
                number = int(re.search(r"[?&]page=(\d+)", url).group(1))
                if number > len(answer):
                    raise AssertionError("Cloudflare was asked for page %d of %d" % (number, len(answer)))
                answer = answer[number - 1]
            if isinstance(answer, Exception):
                raise answer
            return answer if isinstance(answer, bytes) else json.dumps(answer).encode()
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

    def kilo_with(*extra, without=(), replacing=()):
        data = [model for model in base["kilo"]["data"] if model["id"] not in without
                and model["id"] not in [each["id"] for each in replacing]]
        return {"data": data + list(replacing) + list(extra)}

    def kilo_asked_without_a_key(result, calls, report, body):
        asked = [headers for url, headers in calls if "ai-gateway.kilo.ai" in url]
        if not asked:
            return "the Kilo catalogue was never read"
        if any("authorization" in key.lower() or "key" in key.lower() for headers in asked for key in headers):
            return "a keyless catalogue was asked with a credential"
        if len(asked) != 1:
            return "Kilo was asked %d times, where its list is all a deletion rests on" % len(asked)
        return None

    def kilo_notice(wanted_report, wanted_body):
        def check(result, calls, report, body):
            if wanted_report not in report:
                return "the report lacks %r" % wanted_report
            if wanted_body not in body:
                return "the summary lacks %r" % wanted_body
            return None
        return check

    real = CONFIG.read_text(encoding="utf-8")
    listing = answers_listing(real)

    def kilo_of_the_real_list(result, calls, report, body):
        kilo = next(each for each in result["providers"] if each["name"] == "kilo")
        if kilo["active"] < 5 or kilo["status"] != "read":
            return "the Kilo entries of the real list are not attributed to Kilo: %r" % kilo
        if any(each["findings"] for each in result["providers"]):
            return "a catalogue that lists what the real file holds reports a finding"
        return None

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
            return "the summary body does not name the missing secret"
        return None

    def french_body(result, calls, report, body):
        for needle in ("Rapport de `.github/workflows/LiteLLM_model_drift.yml`", "## Retirés : à supprimer",
                       "`openrouter/vendor/one:free`",
                       "## Couverture"):
            if needle not in body:
                return "the summary body lacks %r" % needle
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
            return "the summary body does not say the file could not be read, nor why"
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
        ("every Kilo entry of the real model list is attributed to Kilo, and a catalogue that lists them reports "
         "nothing, the virtual models the file sets aside included",
         real, SELFTEST_KEYS, dict(listing, kilo={"data": listing["kilo"]["data"] + [
             kilo_model("kilo-auto/free"), kilo_model("openrouter/free")]}), no_drift, 0, kilo_of_the_real_list),
        ("an active Kilo id the catalogue no longer lists is RETIRED, read without a key",
         SELFTEST_TEMPLATE, SELFTEST_KEYS, changed("kilo", kilo_with(without=("vendor/kilo-one:free",))),
         [("retired", "vendor/kilo-one:free")], 1, kilo_asked_without_a_key),
        ("an active Kilo id that is still listed but no longer free is a NOTICE, and no retirement",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         changed("kilo", kilo_with(replacing=(kilo_model("vendor/kilo-one:free", free=False),))),
         [("notice", "vendor/kilo-one:free")], 1,
         kilo_notice("openai/vendor/kilo-one:free on Kilo Gateway (kilo-one): no longer flagged free",
                     "`openai/vendor/kilo-one:free` chez Kilo Gateway (`kilo-one`) : n'est plus gratuit")),
        ("an expiration date on an active Kilo id that is free is a NOTICE",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         changed("kilo", kilo_with(replacing=(kilo_model("vendor/kilo-one:free", expiration="2026-12-11"),))),
         [("notice", "vendor/kilo-one:free")], 1,
         kilo_notice("expires on 2026-12-11", "expiration annoncée (`2026-12-11`)")),
        ("a new free Kilo text model is NEW and free; a paid one, an image one and a speech one are not",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         changed("kilo", kilo_with(kilo_model("vendor/kilo-fresh:free"), kilo_model("vendor/kilo-fresh-paid", free=False),
                                   kilo_model("vendor/kilo-fresh-painter:free", outputs=("text", "image")))),
         [("new", "vendor/kilo-fresh:free")], 1,
         lambda result, calls, report, body: (
             "a free model of Kilo was listed as one to examine" if "## Nouveaux modèles à examiner" in body
             else None if "openai/vendor/kilo-fresh:free on Kilo Gateway: free" in report
             else "the report does not list the new Kilo model as free")),
        ("a Kilo answer that flags no model as free or paid is an error, and no notice on every entry",
         SELFTEST_TEMPLATE, SELFTEST_KEYS,
         changed("kilo", {"data": [{"id": "vendor/kilo-one:free"}, {"id": "vendor/kilo-other"}]}), no_drift, 2,
         lambda result, calls, report, body: (
             None if 'the answer lists no "isFree" flag' in report and "NOTICE" not in report
             else "the report does not say that the Kilo answer could not be read")),
        ("a Kilo catalogue that is down is an error, not a catalogue of zero models",
         SELFTEST_TEMPLATE, SELFTEST_KEYS, changed("kilo", urllib.error.URLError("selftest: no route")), no_drift, 2,
         None),
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
         "summary: the status is all that is shown",
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
             else "the broken rule is not in the summary body")),
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
        vars(drift)["rewrite_heads"] = lambda text, trusted: (text, [])
        new_text, outcomes = apply_removals(HEAD_TEMPLATE, [("openrouter", "vendor/one:free", "retired")])
    finally:
        vars(drift)["rewrite_heads"] = real
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
    return result, calls, render_text(result, "selftest"), render_summary(result, "selftest")


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
                "the source's text carried markup into the summary")))

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
            ("## Classements non lus" in body and "Rien d'autre n'en dépend" in body, "the summary does not say it"),
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
                       (len(body) < 47000, "the body is %d characters long" % len(body))))

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
        vars(drift)["plan_lines"] = careless
        new_text, outcomes = apply_removals(APPLY_TEMPLATE, wanted)
    finally:
        vars(drift)["plan_lines"] = real
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
    # key given and another for the set that gives one provider alone is refused.
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
                    runpy.run_path(drift.__file__, run_name="__main__")
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
        summary = apply_run(SELFTEST_TEMPLATE, answers)[3]
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    cases.append(("the summary names the branch of the deletions, and links the pull request found by it",
                  "sur la branche `claude/selftest-branch`" in summary
                  and "(https://selftest.invalid/owner/repo/pulls?q=is%3Apr+is%3Aopen+head%3A"
                      "claude%2Fselftest-branch)" in summary))

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
    """One whole online run with --apply, on canned catalogues: (result, new text, report, summary
    body, pull request body, commit message). The last two are None when nothing was deleted."""
    calls = []
    result = run_online(text, SELFTEST_KEYS if environment is None else environment,
                        canned_opener(answers, calls), "2026-01-01")
    new_text = apply_to_result(text, result)
    report = render_text(result, "selftest")
    summary = render_summary(result, "selftest", link=None)
    changed = result["removals"]["changed"]
    return (result, new_text, report, summary,
            render_pr_body(result) if changed else None,
            render_commit_message(result) if changed else None)


def hostile_lines(*texts):
    """The first line, if any, a workflow command could be read from at the head of: GitHub reads
    "::command::" after trimming the left of a log line, and any markup that makes a mention, a
    tag or a link from a catalogue's text is as unwelcome in a summary."""
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
    """(what the case proves, template, answers, a check on (result, new_text, report, summary, pr,
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

    def deletes_fast(result, new_text, report, summary, pr, commit):
        if "groq/vendor/fast" in new_text or "model_name: fast\n" in new_text:
            return "the retired entry is still in the file"
        if undeleted_count(result) != 0:
            return "a model that was deleted is counted as left to a person"
        for name, needle in (("summary", "## Supprimés par la pull request"),
                             ("summary", "`groq/vendor/fast`"),
                             ("pr", "`groq/vendor/fast` chez Groq"),
                             ("pr", "<https://api.groq.com/openai/v1/models>, lu le 2026-01-01"),
                             ("pr", "ansible-ci.yml"),
                             ("commit", "found 1 id it no longer lists, from Groq (1)")):
            if needle not in " ".join({"summary": summary, "pr": pr, "commit": commit}[name].split()):
                return "the %s lacks %r" % (name, needle)
        if "## Retirés" in summary:
            return "a deletion the pull request makes is still listed as to do by hand"
        if commit.splitlines()[0] != ("Delete the models their provider has retired from the "
                                      "LiteLLM model list (#243)"):
            return "the commit subject is %r" % commit.splitlines()[0]
        return None

    def nothing_to_read(result, new_text, report, summary, pr, commit):
        # "dependabot-auto-merge.yml" lets the pull request merge itself only when its body has no
        # "À relire" section: this is the case where it has none.
        if "groq/vendor/fast" in new_text:
            return "the retired entry is still in the file"
        if pr is None or re.search(r"^## À relire\s*$", pr, re.MULTILINE):
            return "the pull request asks a person to read something although nothing is left over"
        return None

    def something_to_read(result, new_text, report, summary, pr, commit):
        # ... and the case where it has one, which has to be a person's to merge.
        if "groq/vendor/fast" in new_text:
            return "the retired entry is still in the file"
        if pr is None or not re.search(r"^## À relire\s*$", pr, re.MULTILINE):
            return "the prose left above a deleted entry is not listed under \"À relire\""
        return None

    def keeps_free_one(result, new_text, report, summary, pr, commit):
        if new_text != SELFTEST_TEMPLATE:
            return "the file changed although the only retired model is behind an alias"
        if undeleted_count(result) != 1:
            return "the model that was refused is not counted as left to a person"
        if pr is not None or commit is not None:
            return "a pull request body was written although nothing was deleted"
        for needle in ("## Retirés : à supprimer à la main", "non supprimé par le workflow",
                       "l'alias \"auto-hidden\" pointe vers lui", "`openrouter/vendor/one:free`"):
            if needle not in summary:
                return "the summary lacks %r" % needle
        if "NOT DELETED, left to a person: the alias" not in report:
            return "the report does not say the model was left alone"
        return None

    def empty_not_believed(result, new_text, report, summary, pr, commit):
        if new_text != SELFTEST_TEMPLATE:
            return "an empty catalogue was taken for everything retired"
        if "catalogue ne liste aucun modèle" not in summary:
            return "the summary does not say why"
        if undeleted_count(result) != 1:
            return "a commented-out model that was refused is not counted as left to a person"
        return None

    def error_deletes_nothing_else(result, new_text, report, summary, pr, commit):
        if "deepseek/deepseek-v9" not in new_text:
            return "the entry of the provider that could not be read was deleted"
        if "## Catalogues non lus" not in pr or "`deepseek`" not in pr.split("## Catalogues non lus")[1]:
            return "the pull request does not say which catalogue was not read"
        if "groq/vendor/fast" in new_text:
            return "what could be read was not deleted"
        return hostile_lines(report, summary, pr, commit) or (
            "a key or an echoed key reached the output"
            if any("SECRET" in (text or "") for text in (report, summary, pr, commit)) else None)

    def idempotent(result, new_text, report, summary, pr, commit):
        again, second, _, _, again_pr, _ = apply_run(new_text, changed(groq=groq_without_fast))
        if second != new_text or again_pr is not None:
            return "a second run deleted something more"
        if [f for r in again["providers"] for f in r["findings"] if f["kind"] == "retired"]:
            return "the second run still finds the model retired"
        return None

    def decisions_untouched(result, new_text, report, summary, pr, commit):
        kinds = sorted({f["kind"] for r in result["providers"] for f in r["findings"]})
        if kinds != ["back", "new", "notice"]:
            return "the findings are %r, expected an announced retirement, a BACK and a NEW" % kinds
        if new_text != SELFTEST_TEMPLATE or pr is not None or commit is not None:
            return "an announced retirement, a model free again or a new model changed the file"
        if any("removal" in f for r in result["providers"] for f in r["findings"]):
            return "a finding that is a decision was given an outcome"
        return None

    def snippets(result, new_text, report, summary, pr, commit):
        blocks = re.findall(r"  ```yaml\n(.*?)\n  ```", summary, re.DOTALL)
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
        if "ne s'accordent pas" in summary:
            return "the summary says a provider's entries disagree on the api_base, and none does"
        if "insérer `# ` après les deux espaces d'indentation de chaque ligne" not in summary:
            return "the summary does not say how to comment a snippet out"
        return None

    def mixed_api_base_said(result, new_text, report, summary, pr, commit):
        if "Les entrées existantes de `gemini` ne s'accordent pas toutes sur l'`api_base`" \
                not in summary:
            return "the summary does not say that the Gemini entries disagree on the api_base"
        if "Les entrées existantes de `groq`" in summary:
            return "the summary says so of a provider whose entries agree"
        return None

    def snippets_dropped_when_too_long(result, new_text, report, summary, pr, commit):
        if "```yaml" in summary:
            return "the snippets were kept in a body past the limit"
        if len(summary) > 65536:
            return "the body is %d characters, past GitHub's limit" % len(summary)
        if "- `openrouter/vendor/bulk-0:free`" not in summary:
            return "the findings themselves were dropped with the snippets"
        return None

    def commented_form_is_read(result, new_text, report, summary, pr, commit):
        block = next((b for b in re.findall(r"  ```yaml\n(.*?)\n  ```", summary, re.DOTALL)
                      if "vendor/fresh:free" in b), None)
        if block is None:
            return "no snippet for the new OpenRouter id"
        # What the summary says to do: a "# " after the two spaces of indentation of each line.
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

    def too_short_not_believed(result, new_text, report, summary, pr, commit):
        outcomes = groq_outcomes(result)
        if new_text != APPLY_TEMPLATE or pr is not None or commit is not None:
            return "a catalogue that omits most of what the file holds changed the file"
        if len(outcomes) != 4 or any(o["status"] != "refused" or o["reason"][0] != "implausible"
                                     for o in outcomes):
            return "outcomes %r" % [(o["status"], o["reason"]) for o in outcomes]
        if "omits 4 of the 7 ids this file holds for that provider" not in report:
            return "the report does not say why"
        if "ne liste pas 4 des 7 identifiants" not in summary:
            return "the summary does not say why"
        return None

    def three_of_seven_believed(result, new_text, report, summary, pr, commit):
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

    def commented_ids_count_as_held(result, new_text, report, summary, pr, commit):
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

    def half_believed(result, new_text, report, summary, pr, commit):
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

    def three_of_four_not_believed(result, new_text, report, summary, pr, commit):
        outcomes = groq_outcomes(result)
        if new_text != quartet or pr is not None:
            return "a catalogue that omits three of the four ids the file holds changed the file"
        if len(outcomes) != 3 or any(o["status"] != "refused" or o["reason"][0] != "implausible"
                                     for o in outcomes):
            return "outcomes %r" % [(o["status"], o["reason"]) for o in outcomes]
        return None

    def small_provider_believed(result, new_text, report, summary, pr, commit):
        outcomes = [finding["removal"] for r in result["providers"] if r["name"] == "cerebras"
                    for finding in r["findings"] if "removal" in finding]
        if len(outcomes) != 2 or any(o["status"] != "applied" for o in outcomes):
            return "outcomes %r" % [(o["status"], o["reason"]) for o in outcomes]
        if "cerebras/cb-" in new_text:
            return "the two Cerebras entries were not deleted"
        return None

    def hostile(result, new_text, report, summary, pr, commit):
        problem = hostile_lines(report, summary, pr, commit)
        if problem:
            return problem
        if any(spelling in summary for spelling in (
                "vendor/evil", "vendor/tick", "vendor//slashes", "vendor/colon")):
            return "an id spelt out of the ordinary became a NEW candidate"
        okay = [line for line in summary.splitlines()
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
        ("a retired model nobody routes to is deleted, and the summary, the pull request and the "
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
        ("a retired model an alias points at is left alone, and the summary says why in French",
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
        ("the commented-out form the summary documents is one the check reads as an entry",
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
        ("snippets are dropped, findings kept, when the summary body would pass GitHub's limit",
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
    """(what the case proves, template, answers, a check on (result, new_text, report, summary, pr,
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
        def check(result, new_text, report, summary, pr, commit):
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
            section = summary.split("## Absents de la liste, mais toujours servis")
            if len(section) != 2 or "`%s` (`%s`)" % (label, config_name) not in section[1]:
                return "the summary does not name the model under the section for the served ones"
            return None
        return check

    def deleted_and_confirmed(result, new_text, report, summary, pr, commit):
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
        def check(result, new_text, report, summary, pr, commit):
            if new_text != SELFTEST_TEMPLATE or pr is not None:
                return "a deletion nobody confirmed was made"
            if undeleted_count(result) != 1:
                return "the model that was not deleted is not counted as left to a person"
            wanted = ("NOT DELETED, left to a person: its provider's list omits it, and asking the "
                      "provider for the model itself did not confirm that it is gone: " + reason)
            if wanted not in report:
                return "the report lacks %r" % wanted
            if "**non supprimé par le workflow** : la liste de son fournisseur l'omet" not in summary:
                return "the summary does not say, in French, that the workflow left it alone"
            if reason not in summary:
                return "the summary does not give the answer the provider made"
            return hostile_lines(report, summary) or (
                "a key reached the output"
                if any("SECRET" in (text or "") for text in (report, summary)) else None)
        return check

    def not_a_lookup_provider(result, new_text, report, summary, pr, commit):
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
# a literal and one whose base is no https address, which no proposal may be modelled on, and a keyless
# gateway's, whose literal key is a marker and which blanks the Authorization header.
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
  - model_name: gw-one
    litellm_params:
      model: openai/vendor/gw-one:free
      api_base: "https://ai-gateway.kilo.ai/api/v1"
      api_key: "gw-no-key"
      extra_headers:
        Authorization: ""

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
    "-"). The ranking also knows the Gemini one for certain, which does not make its free tier known. Kilo has
    two free ones, one the ranking matches for certain and one it does not know."""
    answers = answers_listing(text)
    fresh = openrouter_model("vendor/fresh:free")
    fresh["name"] = "Vendor: Fresh @bob <img src=x> `x` ::error:: (free)"
    answers["openrouter"]["data"] += [fresh, openrouter_model("~vendor/odd:free"),
                                      openrouter_model("vendor/rough-cut:free"),
                                      openrouter_model("vendor/unmeasured:free")]
    answers["rankings"] = ranking_page(ranking_model("fresh", "Fresh", 40, 30, 200, 0.0),
                                       ranking_model("rough.cut", "Rough Cut (Reasoning)", 35, 25, 150, 0.0),
                                       ranking_model("gemini-10-pro", "Gemini 10 Pro", 60, 50, 100, 1.0),
                                       ranking_model("gateway-fresh", "Gateway Fresh", 45, 35, 110, 0.0))
    answers["gemini"][0]["models"] += [
        {"name": "models/gemini-10-pro", "displayName": "Gemini 10 Pro",
         "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-odd-", "supportedGenerationMethods": ["generateContent"]}]
    answers["groq"]["data"].append({"id": "vendor/quick", "active": True, "owned_by": "Vendor"})
    answers["mistral"]["data"].append({"id": "magistral-9", "capabilities": {"completion_chat": True}})
    answers["deepseek"]["data"].append({"id": "deepseek-v10"})
    answers["sambanova"]["data"].append({"id": "SN-Two"})
    answers["cerebras"]["data"].append({"id": "cb-new"})
    answers["kilo"]["data"] += [kilo_model("vendor/gateway-fresh:free"), kilo_model("vendor/gateway-plain")]
    return answers


def proposal_run(text, answers, environment=RANKING_KEYS):
    result = run_online(text, environment, canned_opener(answers, []), "2026-01-01")
    return result, propose_additions(text, result)


def run_proposal_cases():
    """The two pull requests of additions: what is proposed in which, the files with the entries added,
    the bodies and their checklists, what the summary keeps, and what is refused."""
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
    summary = render_summary(result, "selftest")
    unproposed = {(report["name"], finding["id"]): finding.get("unproposed") for report in result["providers"]
                  for finding in report["findings"] if finding["kind"] == "new"}
    missing = {(report["name"], finding["id"]): [what for what, _ in finding.get("missing", [])]
               for report in result["providers"] for finding in report["findings"] if finding["kind"] == "new"}
    judged("a model the run knows everything of is ready; one with a fact missing, whatever its provider, is to verify",
           first_wrong(
               (ids(ready) == [("openrouter", "vendor/fresh:free"), ("kilo", "vendor/gateway-fresh:free")],
                "ready: %r" % ids(ready)),
               (ids(to_verify) == [("openrouter", "vendor/rough-cut:free"), ("openrouter", "vendor/unmeasured:free"),
                                   ("sambanova", "SN-Two"), ("gemini", "gemini-10-pro"), ("groq", "vendor/quick"),
                                   ("mistral", "magistral-9"), ("deepseek", "deepseek-v10"),
                                   ("kilo", "vendor/gateway-plain")],
                "to verify: %r" % ids(to_verify)),
               ([item["name"] for item in to_verify["items"]] == [
                   "rough-cut-free", "unmeasured-free", "sn-two-sambanova", "gemini-10-pro", "quick-groq",
                   "magistral-9", "deepseek-v10-direct", "gateway-plain-kilo"],
                "the names are %r" % [item["name"] for item in to_verify["items"]]),
               (missing[("openrouter", "vendor/fresh:free")] == [], "the ready model misses %r"
                % missing[("openrouter", "vendor/fresh:free")]),
               (missing[("openrouter", "vendor/rough-cut:free")] == ["match"], "an approximate match is not said"),
               (missing[("openrouter", "vendor/unmeasured:free")] == ["ranking"], "an unmeasured model is not said"),
               (missing[("gemini", "gemini-10-pro")] == ["free"], "a certain match made a free tier known"),
               (missing[("kilo", "vendor/gateway-fresh:free")] == [], "the ready Kilo model misses %r"
                % missing[("kilo", "vendor/gateway-fresh:free")]),
               (missing[("kilo", "vendor/gateway-plain")] == ["ranking"], "an unmeasured Kilo model is not said"),
               (ready["complete"] and to_verify["complete"], "a kind is said incomplete")))
    judged("a model of a provider with no entry, or of a spelling the file is not written with, is left to the summary",
           first_wrong(
               ("aucune entrée de ce fournisseur" in (unproposed.get(("cerebras", "cb-new")) or ""),
                "cerebras: %r" % unproposed.get(("cerebras", "cb-new"))),
               ("forme" in (unproposed.get(("openrouter", "~vendor/odd:free")) or ""), "the odd id was proposed"),
               ("forme" in (unproposed.get(("gemini", "gemini-odd-")) or ""), "the odd Gemini id was proposed"),
               ("`cerebras/cb-new`" in summary and "pas proposé par pull request" in summary,
                "the summary does not list what is not proposed"),
               ("vendor/fresh:free" not in summary and "gemini-10-pro" not in summary and "rough-cut" not in summary
                and "gateway-fresh" not in summary and "gateway-plain" not in summary,
                "the summary still lists a proposed model"),
               ("## Ajouts proposés par pull request" in summary and ": 2 modèles." in summary
                and "comment l'obtenir : 8 modèles." in summary, "the summary does not point at the pull requests"),
               (exit_status(result) == 1 and left_outside_pull_requests(result), "the status moved, or what no "
                "pull request carries is not said to be left outside them")))
    added = [line for line in difflib.ndiff(SELFTEST_TEMPLATE.split("\n"), to_verify["text"].split("\n"))
             if line.startswith(("+ ", "- "))]
    judged("each entry follows its provider's last entry, modelled on it, active or commented out like it",
           first_wrong(
               (not any(line.startswith("- ") for line in added), "a line of the file was changed: %r" % added[:3]),
               ('      api_key: "os.environ/OPENROUTER_API_KEY_SELFTEST"\n\n  # Proposed by the weekly drift run '
                'on 2026-01-01: listed free by "openrouter.ai/api/v1/models" that day.\n  - model_name: fresh-free\n'
                '    model_info:\n      access_groups: ["LLM"]\n'
                '    litellm_params:\n      model: openrouter/vendor/fresh:free\n'
                '      api_key: "os.environ/OPENROUTER_API_KEY_SELFTEST"\n' in ready["text"],
                "the OpenRouter entry is not after free-one"),
               ("fresh-free" not in ready["text"].split("\nrouter_settings:")[1], "a ready model was placed"),
               ('      extra_headers:\n        Authorization: ""\n\n  # Proposed by the weekly drift run on 2026-01-01: '
                'listed free by "ai-gateway.kilo.ai/api/v1/models" that day.\n  - model_name: gateway-fresh-kilo\n'
                '    model_info:\n      access_groups: ["LLM"]\n'
                '    litellm_params:\n      model: openai/vendor/gateway-fresh:free\n'
                '      api_base: "https://ai-gateway.kilo.ai/api/v1"\n      api_key: "kilo-selftest-marker"\n'
                '      extra_headers:\n        Authorization: ""\n' in ready["text"],
                "the Kilo entry is not after kilo-one, with its marker and the header that blanks Authorization"),
               ("  - model_name: gateway-plain-kilo\n" in to_verify["text"]
                and to_verify["text"].count('Authorization: ""') == 2,
                "the Kilo entry to verify is wrong, or another entry lost its header"),
               ('  #     api_key: "os.environ/SAMBANOVA_API_KEY_SELFTEST"\n\n  # Not routed to: proposed by the '
                'weekly drift run on 2026-01-01, its free tier on SambaNova not verified yet.\n'
                '  # - model_name: sn-two-sambanova\n  #   model_info:\n  #     access_groups: ["LLM"]\n'
                '  #   litellm_params:\n  #     model: openai/SN-Two\n'
                '  #     api_base: "https://api.sambanova.ai/v1"\n' in to_verify["text"],
                "the SambaNova entry is not a commented-out one after sn-one, with its base"),
               ("  - model_name: quick-groq\n    model_info:\n      access_groups: [\"LLM\"]\n"
                "    litellm_params:\n      model: groq/vendor/quick\n"
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
               # The signature is the one link a body writes on purpose; the summary links pricing pages.
               (hostile_lines(vbody.replace(PROPOSAL_SIGNATURE, ""), body.replace(PROPOSAL_SIGNATURE, "")) is None,
                str(hostile_lines(vbody.replace(PROPOSAL_SIGNATURE, ""), body.replace(PROPOSAL_SIGNATURE, "")))),
               ("@bob" not in summary and "<img" not in summary and "::error" not in summary, "markup reached the summary"),
               (vbody.endswith(PROPOSAL_SIGNATURE), "the body is not signed")))
    judged("the commits say what they add, in English, under the summary",
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
               (ids(again_proposals["ready"]) == [("openrouter", "vendor/fresh:free"),
                                                  ("kilo", "vendor/gateway-fresh:free")], "the other kind moved"),
               (ids(aside_proposals["ready"]) == [("kilo", "vendor/gateway-fresh:free")],
                "a model set aside came back, or the other one of its kind moved"),
               (len(aside_proposals["to_verify"]["items"]) == 8, "the other kind moved")))

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
    # not know is to verify, not placed, with its line; and the summary ranks neither.
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
               ("## Classement des nouveaux modèles" not in render_summary(ranked, "selftest"),
                "the summary still ranks the proposed models"),
               (not left_outside_pull_requests(ranked) and exit_status(ranked) == 1
                and "Aucune dérive." in render_summary(ranked, "selftest"),
                "a week whose only news is proposed says something is left outside the pull requests")))

    # The caps: entries per pull request, and the size of a body.
    many = answers_listing(RANKING_TEMPLATE)
    many["openrouter"]["data"] += [openrouter_model("vendor/m%02d:free" % number) for number in range(30)]
    capped_result = run_online(RANKING_TEMPLATE, SELFTEST_KEYS, canned_opener(many, []), "2026-01-01")
    capped_proposals = propose_additions(RANKING_TEMPLATE, capped_result)
    capped = capped_proposals["to_verify"]
    left = [finding.get("unproposed") for report in capped_result["providers"] for finding in report["findings"]
            if finding.get("unproposed")]
    # The section of what no entry is made of comes after the entries are chosen, and a body too long
    # for its entries alone is what loses one.
    carried_section = capped["body"][capped["body"].find(UNCARRIED_HEADING):capped["body"].find("## Classement")]
    kept_limit = drift.BODY_LIMIT
    try:
        drift.BODY_LIMIT = len(capped["body"]) - len(carried_section) - 1
        shrunk_result = run_online(RANKING_TEMPLATE, SELFTEST_KEYS, canned_opener(many, []), "2026-01-01")
        shrunk = propose_additions(RANKING_TEMPLATE, shrunk_result)
        # Room for the section without its entries to complete, and not with them.
        bare = "\n".join(carried_sections(capped_result, "to_verify", None, False)) + "\n"
        drift.BODY_LIMIT = len(capped["body"]) - len(carried_section) + len(bare) + 10
        bare_result = run_online(RANKING_TEMPLATE, SELFTEST_KEYS, canned_opener(many, []), "2026-01-01")
        bared = propose_additions(RANKING_TEMPLATE, bare_result)["to_verify"]
        bare_limit = drift.BODY_LIMIT
    finally:
        drift.BODY_LIMIT = kept_limit
    bare_section = bared["body"][bared["body"].find(UNCARRIED_HEADING):bared["body"].find("## Classement")]
    judged("a pull request carries %d entries at most, and fewer when its body would be too long" % PROPOSAL_LIMIT,
           first_wrong(
               (len(capped["items"]) == PROPOSAL_LIMIT, "it carries %d" % len(capped["items"])),
               (len(left) == 30 - PROPOSAL_LIMIT and all("au-delà des 25" in reason for reason in left),
                "the rest is not left to the summary: %r" % left[:2]),
               (0 < len(shrunk["to_verify"]["items"]) < PROPOSAL_LIMIT
                and len(shrunk["to_verify"]["body"]) <= len(capped["body"]) - len(carried_section) - 1,
                "a body too long was not shortened"),
               (carried_section.startswith(UNCARRIED_HEADING) and carried_section.count("```yaml") == 5
                and all("`openrouter/vendor/m%02d:free`" % number in carried_section for number in range(25, 30))
                and "au-delà des 25 entrées" in carried_section,
                "the models past the cap are not in the body of the one to verify, with their entry and why"),
               (len(bared["items"]) == PROPOSAL_LIMIT and bare_section.startswith(UNCARRIED_HEADING)
                and "```yaml" not in bare_section and "`openrouter/vendor/m29:free`" in bare_section
                and len(bared["body"]) <= bare_limit,
                "a section too long with its entries to complete is not kept without them"),
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

    # The summary keeps what the files break, and the commands read the right header and route.
    broken = SELFTEST_TEMPLATE.replace("  # Served at $0, but not routed to: a guardrail, not a generator.\n", "")
    rules = run_online(broken, SELFTEST_KEYS, canned_opener(dict(answers_listing(broken), openrouter={"data": [
        openrouter_model(i) for i in ("vendor/one:free", "vendor/paid-one", "vendor/paid-two",
                                      "vendor/guardrail:free", "vendor/new-one:free")]}), []), "2026-01-01")
    propose_additions(broken, rules)
    groq = to_verify["body"].split("### `groq/vendor/quick`")[1].split("\n### ")[0]
    judged("a file that breaks a rule is left outside the pull requests, whatever is proposed; each command its own header",
           first_wrong(
               (rules["rules"] and proposed(rules, "openrouter", "vendor/new-one:free") and left_outside_pull_requests(rules)
                and "Aucune dérive." not in render_summary(rules, "selftest"),
                "the summary would say there is no drift over a broken rule"),
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
               ("Aucune dérive." in render_summary(blanked, "selftest"),
                "a summary whose only news is proposed does not say there is no drift")))

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

    # A keyless gateway's entry: the literal marker copied from its last entry, the header that blanks
    # Authorization written after it, whatever the spelling of the id, and the name of the gateway.
    kilo_items = [{"provider": "kilo", "id": "vendor/gw-two:free", "name": "gw-two-kilo"},
                  {"provider": "kilo", "id": "vendor/gw-three", "name": "gw-three-kilo"}]
    kilo_text, kilo_problem = build_additions(ADDITIONS_TEMPLATE, "2026-01-01", "ready", kilo_items)
    kilo_entry = ('      api_base: "https://ai-gateway.kilo.ai/api/v1"\n      api_key: "gw-no-key"\n'
                  '      extra_headers:\n        Authorization: ""\n')
    judged("a keyless gateway's entries are written with the literal marker and the header that blanks Authorization",
           first_wrong(
               (kilo_problem is None and kilo_text, "refused for %r" % kilo_problem),
               (("  - model_name: gw-two-kilo\n    model_info:\n      access_groups: [\"LLM\"]\n"
                 "    litellm_params:\n      model: openai/vendor/gw-two:free\n"
                 + kilo_entry) in kilo_text, "the entry with a :free id is wrong"),
               (("  - model_name: gw-three-kilo\n    model_info:\n      access_groups: [\"LLM\"]\n"
                 "    litellm_params:\n      model: openai/vendor/gw-three\n"
                 + kilo_entry) in kilo_text, "the entry without :free is wrong, or was refused for it"),
               (addition_problem(ADDITIONS_TEMPLATE, kilo_text, kilo_items) is None, "the file does not read back")))
    head = ("  - model_name: gw-two-kilo\n    model_info:\n      access_groups: [\"LLM\"]\n"
            "    litellm_params:\n      model: openai/vendor/gw-two:free\n")
    unblanked = kilo_text.replace(head + kilo_entry, head + kilo_entry.split("      extra_headers")[0])
    judged("a file whose entry of a keyless gateway does not blank the Authorization header is refused",
           None if unblanked != kilo_text and "does not blank the Authorization header" in (
               addition_problem(ADDITIONS_TEMPLATE, unblanked, kilo_items) or "")
           else "an entry that the gateway answers 401 to was let through")
    environment_key = ADDITIONS_TEMPLATE.replace('api_key: "gw-no-key"', 'api_key: "os.environ/KILO_API_KEY"')
    problem = build_additions(environment_key, "2026-01-01", "ready", kilo_items[:1])[1]
    judged("a keyless gateway's entry is not modelled on one that reads a key from the environment",
           None if problem and "is not a plain marker" in problem else "refused for %r" % problem)
    entries = addition_entries(ADDITIONS_TEMPLATE.split("\n"))
    basis = provider_basis(read_template(ADDITIONS_TEMPLATE)[0]["active"], "kilo")
    taken = set(WORD.findall(ADDITIONS_TEMPLATE)) | {"gw-one-kilo"}
    snippet_lines = snippet("kilo", "vendor/gw-four:free", basis, "gw-four-kilo")
    judged("the names and the snippets of a keyless gateway are the file's",
           first_wrong(
               ([addition_name("kilo", identifier, set()) for identifier in (
                   "reflection/beam-free", "stealth/glyph-cluster", "particle-ai/particle-1:free",
                   "nvidia/nemotron-3.5-lightning:free")]
                == ["beam-kilo", "glyph-cluster-kilo", "particle-1-kilo", "nemotron-3-5-lightning-kilo"],
                "the names of Kilo's ids are not the file's"),
               (addition_name("kilo", "vendor/gw-one:free", taken) == "gw-one-kilo-kilo",
                "a name that is taken did not get another"),
               (snippet_lines[-3:] == ['      api_key: "gw-no-key"', "      extra_headers:", '        Authorization: ""'],
                "the snippet of a keyless gateway is not the entry's shape: %r" % snippet_lines),
               (entries and addition_anchor(entries, "kilo")["name"] == "gw-one", "the entry of Kilo is not found")))

    # The tables the bodies read, against the providers they serve.
    commands = [catalogue_command(name, "vendor/model-1", "os.environ/%s_API_KEY" % name.upper())
                for name in PROVIDER_NAMES]
    judged("each provider listed to verify has what to look for, and each command quotes nothing it should not",
           first_wrong(
               (set(FREE_TIER_CHECKS) == set(PRICING_PAGES), "FREE_TIER_CHECKS and PRICING_PAGES differ"),
               (set(FREE_CATALOGUES) == FREE_READABLE, "FREE_CATALOGUES and FREE_READABLE differ"),
               (set(FREE_READINGS) == set(FREE_CATALOGUES), "FREE_READINGS and FREE_CATALOGUES differ"),
               (set(FREE_SUFFIX) <= set(FREE_CATALOGUES), "FREE_SUFFIX names a provider that states no free tier"),
               (set(PROVIDER_LABELS) == set(NAME_SUFFIXES) == set(PROVIDER_NAMES),
                "PROVIDER_LABELS, NAME_SUFFIXES and PROVIDERS differ"),
               (set(OPENAI_COMPATIBLE) | set(DEFAULT_BASES) | KEYLESS_GATEWAYS <= set(PROVIDER_NAMES)
                and not any(keyed(name) for name in KEYLESS_GATEWAYS),
                "OPENAI_COMPATIBLE, DEFAULT_BASES or KEYLESS_GATEWAYS name a provider that is not read, or a keyed one"),
               (all(command.count("'") == 2 for command in commands), "a command holds a quote of its own"),
               (all(("docker exec" in command) == keyed(name) for name, command in zip(PROVIDER_NAMES, commands)),
                "a keyed command does not run in the container, or a keyless one does")))
    return failures


def run_carried_cases():
    """What the issue used to carry, now that only an unreadable catalogue opens one: an announced
    retirement in the body of the deletion pull request, a model free again in the body of the pull
    request of additions that concerns it, a NEW model no pull request proposes in the body of the one to
    verify, and all of it, with the rest, in the run's summary, which is where it stays in a week with no
    pull request to carry it."""
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

    def section(body, heading):
        """The text of a section of "body", from its heading to the next one, or ""."""
        if heading not in body:
            return ""
        return body.split(heading, 1)[1].split("\n## ", 1)[0]

    def week(answers):
        result = run_online(SELFTEST_TEMPLATE, RANKING_KEYS, canned_opener(answers, []), "2026-01-01")
        new_text = apply_to_result(SELFTEST_TEMPLATE, result)
        proposals = propose_additions(SELFTEST_TEMPLATE, result)
        return (result, new_text, proposals, render_summary(result, "selftest"),
                render_pr_body(result) if result["removals"]["changed"] else None)

    def news(answers, fresh=True):
        """"answers" with a model free again (paid-one), an announced retirement (free-one) and, unless
        "fresh" is false, the one model the run knows everything of."""
        listing = [openrouter_model("vendor/one:free", expiration="2026-02-01") if model["id"] == "vendor/one:free"
                   else model for model in answers["openrouter"]["data"]
                   if fresh or model["id"] != "vendor/fresh:free"]
        kilo = [model for model in answers["kilo"]["data"] if fresh or model["id"] != "vendor/gateway-fresh:free"]
        return dict(answers, openrouter={"data": listing + [openrouter_model("vendor/paid-one:free")]},
                    kilo={"data": kilo})

    retiring = proposal_answers()
    retiring["groq"] = {"data": [model for model in retiring["groq"]["data"] if model["id"] != "vendor/fast"]}
    result, new_text, proposals, summary, pr = week(news(retiring))
    ready, to_verify = proposals["ready"]["body"], proposals["to_verify"]["body"]
    notice = section(pr or "", "## Retraits annoncés")
    judged("an announced retirement is in the body of the deletion pull request, under a heading that does not hold its merge",
           first_wrong(
               (pr is not None and "model: groq/vendor/fast" not in new_text, "nothing was deleted"),
               ("`openrouter/vendor/one:free` (`free-one`) : expiration annoncée (`2026-02-01`)" in notice,
                "the deletion pull request does not carry it: %r" % notice[:300]),
               ("`groq/vendor/fast`" not in notice, "a deletion is listed as announced"),
               (REVIEW_HEADING not in (pr or ""), "the announcement asks for a reading, which holds the merge back")))
    judged("a model free again is in the body of the pull request of ready additions, and not in the other one",
           first_wrong(
               ("`openrouter/vendor/paid-one:free` (`paid-one`)" in section(ready, "## De nouveau gratuits sur OpenRouter"),
                "the ready pull request does not carry it"),
               ("## De nouveau gratuits" not in to_verify, "the one to verify carries it too")))
    left = section(to_verify, UNCARRIED_HEADING)
    judged("a NEW model no pull request proposes is in the body of the one to verify, with why and its entry",
           first_wrong(
               ("`cerebras/cb-new`" in left and "aucune entrée de ce fournisseur" in left,
                "a provider with no entry is not carried: %r" % left[:300]),
               ("`openrouter/~vendor/odd:free`" in left and "`gemini/gemini-odd-`" in left and "forme" in left,
                "an id of another spelling is not carried"),
               (left.count("```yaml") == 3 and "model: cerebras/cb-new" in left
                and 'api_key: "os.environ/CEREBRAS_API_KEY_<ACCOUNT>"' in left, "the entries to complete are missing"),
               ("vendor/fresh:free" not in left and "gemini-10-pro" not in left, "a proposed model is listed as not proposed"),
               (UNCARRIED_HEADING not in ready, "the ready pull request carries them")))
    judged("the run's summary has all of it, the router contracts' place and the coverage included",
           first_wrong(
               (all(heading in summary for heading in ("## Supprimés par la pull request", "## Retraits annoncés",
                                                       "## De nouveau gratuits sur OpenRouter",
                                                       "## Nouveaux modèles à examiner", "## Couverture")),
                "a section is missing from the summary"),
               ("`cerebras/cb-new`" in summary and "Aucune dérive." not in summary, "what nothing carries is not there"),
               ("<!--" not in summary, "the summary carries the marker of the issue")))

    result, _, proposals, summary, _ = week(news(proposal_answers(), fresh=False))
    judged("a model free again goes to the pull request of the models to verify when no ready one is opened",
           first_wrong(
               (proposals["ready"]["items"] == [], "a model is ready"),
               ("`openrouter/vendor/paid-one:free` (`paid-one`)" in section(proposals["to_verify"]["body"],
                                                          "## De nouveau gratuits sur OpenRouter"),
                "the pull request to verify does not carry it")))

    result, new_text, proposals, summary, pr = week(news(dict(answers_listing(SELFTEST_TEMPLATE),
                                                              rankings=ranking_page()), fresh=False))
    judged("a week with no pull request to carry them leaves the announcement and the model free again to the summary",
           first_wrong(
               (pr is None and new_text == SELFTEST_TEMPLATE, "something was deleted"),
               (not any(part["items"] for part in proposals.values()), "something was proposed"),
               ("`openrouter/vendor/one:free`" in section(summary, "## Retraits annoncés")
                and "`openrouter/vendor/paid-one:free` (`paid-one`)" in section(summary, "## De nouveau gratuits sur OpenRouter"),
                "the summary does not carry them"),
               (exit_status(result) == 1 and unreadable_providers(result) == [],
                "a week of drift alone names a catalogue as unreadable")))

    failing = dict(answers_listing(SELFTEST_TEMPLATE), groq=leaky_401("groq"))
    result = run_online(SELFTEST_TEMPLATE, SELFTEST_KEYS, canned_opener(failing, []), "2026-01-01")
    summary = render_summary(result, "selftest")
    judged("a catalogue that could not be read is named with the class of its status, and the summary says when the issue opens",
           first_wrong(
               (unreadable_providers(result) == [("groq", "4xx")], "unreadable: %r" % unreadable_providers(result)),
               ("n'ouvre son issue que si la dernière tentative ne le lit toujours pas" in section(summary, "## Erreurs"),
                "the summary does not say what the error leads to"),
               ("SECRET" not in summary, "a key reached the summary")))
    unreadable_file = run_online("model_list: [\n", SELFTEST_KEYS, canned_opener(failing, []), "2026-01-01")
    judged("a model list that cannot be read names no catalogue either way",
           None if unreadable_providers(unreadable_file) is None else "it named %r" % unreadable_providers(unreadable_file))
    judged("the class of a failure is that of its status, and says nothing else",
           first_wrong(*[(error_class(error) == expected, "%r gave %r" % (error, error_class(error))) for error, expected in (
               (FetchError("HTTP 404", 404), "4xx"), (FetchError("HTTP 302", 302), "3xx"),
               (FetchError("HTTP 503", 503), "5xx"), (FetchError("HTTP 999", 999), "answer"),
               (FetchError("network error: timed out"), "network"),
               (FetchError("the answer is not JSON"), "answer"))]))
    return failures


def run_proposal_command_line_cases():
    """"--proposals" and "--unreadable" end to end: the files the workflow reads are written, the ones of
    a run with nothing to propose are taken back, and the catalogues that could not be read are named
    with the class of their failure and nothing else."""
    failures = 0
    with tempfile.TemporaryDirectory() as directory:
        config = os.path.join(directory, "config.yaml.j2")
        folder = os.path.join(directory, "proposals")
        unread_file = os.path.join(directory, "unreadable.txt")
        Path(config).write_text(SELFTEST_TEMPLATE, encoding="utf-8")
        arguments = ["--online", "--config", config, "--proposals", folder, "--unreadable", unread_file]

        def run(answers, flags=arguments):
            environment = RANKING_KEYS if "rankings" in answers else SELFTEST_KEYS
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                try:
                    return main(flags, opener=canned_opener(answers, []), environment=environment)
                except SystemExit as error:
                    return error.code

        def files():
            return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

        def unread():
            return Path(unread_file).read_text(encoding="utf-8") if os.path.exists(unread_file) else None

        status = run(proposal_answers())
        data = json.loads(Path(folder, "proposals.json").read_text(encoding="utf-8"))
        steps = [
            ("--proposals writes the data, and the body, commit and file of each pull request",
             status == 1 and files() == ["proposals.json", "ready_body.md", "ready_commit.txt",
                                         "ready_template.j2", "to_verify_body.md", "to_verify_commit.txt",
                                         "to_verify_template.j2"]
             and sorted(data) == ["date", "ready", "to_verify"]
             and data["ready"] == {"complete": True, "items": [
                 {"provider": "openrouter", "id": "vendor/fresh:free", "name": "fresh-free"},
                 {"provider": "kilo", "id": "vendor/gateway-fresh:free", "name": "gateway-fresh-kilo"}]}
             and Path(config).read_text(encoding="utf-8") == SELFTEST_TEMPLATE),
            ("--unreadable is an empty file when every catalogue was read, whatever drifted", unread() == ""),
        ]
        only_new = answers_listing(SELFTEST_TEMPLATE)
        only_new["groq"]["data"] = [model for model in only_new["groq"]["data"] if model["id"] != "vendor/fast"]
        only_new["groq"]["data"].append({"id": "vendor/quick", "active": True})
        status = run(only_new, arguments + ["--apply"])
        steps += [
            ("--apply does not change what is proposed on, and names no catalogue for a deletion",
             status == 1 and unread() == ""
             and "groq/vendor/fast" not in Path(config).read_text(encoding="utf-8")
             and "model: groq/vendor/fast" in Path(folder, "to_verify_template.j2").read_text(encoding="utf-8")),
        ]
        Path(config).write_text(SELFTEST_TEMPLATE, encoding="utf-8")
        failing = dict(answers_listing(SELFTEST_TEMPLATE), groq=leaky_401("groq"), mistral=http_error(503),
                       cerebras=urllib.error.URLError("selftest-groq-key-SECRET"),
                       deepseek=b"not json selftest-deepseek-key-SECRET")
        status = run(failing)
        steps.append(("--unreadable names each catalogue not read with the class of its failure, and no key",
                      status == 2 and unread() == "cerebras network\ngroq 4xx\nmistral 5xx\ndeepseek answer\n"))
        Path(config).write_text("model_list: [\n", encoding="utf-8")
        status = run(failing)
        steps.append(("--unreadable writes no file when the model list itself cannot be read",
                      status == 2 and unread() is None))
        Path(config).write_text(SELFTEST_TEMPLATE, encoding="utf-8")
        status = run(answers_listing(SELFTEST_TEMPLATE))
        data = json.loads(Path(folder, "proposals.json").read_text(encoding="utf-8"))
        steps += [
            ("a run with nothing to propose takes back the files of the last one",
             status == 0 and files() == ["proposals.json"]
             and data["ready"]["items"] == [] and data["to_verify"]["items"] == [] and unread() == ""),
            ("--proposals without --online is refused", run({}, ["--config", config, "--proposals", folder]) == 2),
            ("--unreadable without --online is refused",
             run({}, ["--config", config, "--unreadable", unread_file]) == 2),
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
                 for name in ("summary", "pr", "commit", "coverage", "undeleted")}
        arguments = ["--online", "--config", config, "--summary", paths["summary"]]

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
            ("with --apply, the summary, the pull request and the commit are written",
             all(read(name) for name in ("summary", "pr", "commit"))
             and "DELETED from the file" in out
             and "1 deletion(s) made, 0 left to a person" in out),
        ]
        status, out = run(arguments + ["--apply", "--pr-body", paths["pr"],
                                       "--commit-message", paths["commit"]], directory)
        steps += [
            ("a second run deletes nothing, finds no drift, and takes back the stale texts",
             status == 0 and Path(config).read_bytes().decode("utf-8") == rewritten
             and read("pr") is None and read("commit") is None
             and "Aucune dérive." in (read("summary") or "")),
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
# A statement of the file that reads one provider's key and no other: the only kind of condition the
# bounded sets of keys below can stand in for every set of.
ONE_KEY_CONDITION = re.compile(r"\{%-?\s*(?:el)?if\s+(?:not\s+)?has\.\w+\s*-?%\}")


def bounded_keyset_documents(text):
    """keyset_documents over each key alone, every key, and every key but one, rather than every set of
    them: 2n + 1 renderings for n keys where every set is 2^n - 1, which doubled with each provider. A
    condition of the file that reads one key decides the same way whatever the other keys are, and a
    head of the "head" table is the value of the first provider given along its chain, so a cascade left
    empty, a slot or an alias left naming nothing, show with a key alone or a key missing. A file with
    any other condition, two keys read at once say, gets every set, as the weekly run always does."""
    import jinja2.meta
    from jinja2.sandbox import SandboxedEnvironment
    tree = SandboxedEnvironment().parse(text)
    read = jinja2.meta.find_undeclared_variables(tree) & set(PROVIDER_KEY_VARIABLES)
    names = [variable for variable in PROVIDER_KEY_VARIABLES if variable in read]
    conditions = re.findall(r"\{%-?\s*(?:el)?if\b.*?%\}", text, re.DOTALL)
    if len(names) < 3 or not all(ONE_KEY_CONDITION.fullmatch(condition) or "has." not in condition
                                 and not any(name in condition for name in names)
                                 for condition in conditions):
        return keyset_documents(text)
    sets = [(name,) for name in names] + [tuple(names)] + [
        tuple(other for other in names if other != name) for name in names]
    return [(given, drift.render_keyset(text, given)) for given in sets]


@contextlib.contextmanager
def bounded_key_sets():
    """keyset_documents bounded as bounded_keyset_documents says, for the script and for this module,
    while the real model list is deleted from: each deletion renders the file for its sets of keys."""
    plain = vars(drift)["keyset_documents"]
    vars(drift)["keyset_documents"] = globals()["keyset_documents"] = bounded_keyset_documents
    try:
        yield
    finally:
        vars(drift)["keyset_documents"] = globals()["keyset_documents"] = plain


@contextlib.contextmanager
def quick_rendering():
    """A deletion renders the file for every set of keys, several times over, and parsing the results is
    most of the time: here a text is compiled and parsed once, by the C loader where there is one. The
    first rendering of a text is the plain one, which the quick one is held to. What every scenario reads,
    cached while the real file is set up, is kept; what one scenario caches is forgotten once it is
    checked, since the next never reads it, and kept it outgrew a runner shared with other jobs."""
    import jinja2
    from jinja2.sandbox import SandboxedEnvironment
    environment = SandboxedEnvironment(undefined=jinja2.StrictUndefined, trim_blocks=True,
                                       keep_trailing_newline=True)
    plain, loaded = render_with_keys, yaml.safe_load
    rendered, compiled, parsed = {}, {}, {}

    def quick(text, given):
        return compiled[text].render({**{name: "" if given is not None and name not in given
                                         else "placeholder" for name in PROVIDER_KEY_VARIABLES},
                                      **TEMPLATE_SWITCHES})

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

    lasting = set()

    def keep_what_is_cached():
        lasting.update((id(cache), key) for cache in (rendered, compiled, parsed) for key in cache)

    def forget_the_rest():
        for cache in (rendered, compiled, parsed):
            for key in [key for key in cache if (id(cache), key) not in lasting]:
                del cache[key]

    vars(drift)["render_with_keys"], yaml.safe_load = render, load
    try:
        yield keep_what_is_cached, forget_the_rest
    finally:
        vars(drift)["render_with_keys"], yaml.safe_load = plain, loaded


def real_scenarios(layout):
    """The sets of (provider, id) to delete: each entry alone, active or commented out; each run of
    commented-out entries whole and minus each of its members; each provider whole; the two ends of
    the list together; and the pairs of neighbours, one in REAL_PAIR_STEP."""
    keys = [entry["key"] for entry in sorted(layout["entries"], key=lambda entry: entry["start"])
            if entry["key"]]
    # A commented-out entry of no catalogue here (a keyless provider's) has no key and nothing to delete.
    runs = [[key for key in (layout["commented"][index]["key"] for index in run) if key]
            for run in layout["runs"]]
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


def run_bounded_key_set_cases():
    """bounded_keyset_documents renders 2n + 1 sets for a file whose conditions each read one key, and
    every set for one with a condition that reads two: four keys, where the two counts differ."""
    keys = PROVIDER_KEY_VARIABLES[:4]
    head = "{%% set has = {%s} %%}\n" % ", ".join("'%s': %s" % pair for pair in zip("ABCD", keys))
    one = head + "{% if has.A %}a: 1\n{% endif %}{% if not has.B %}b: 1\n{% endif %}" \
                 "{% if has.C %}c: 1\n{% endif %}{% if has.D %}d: 1\n{% endif %}"
    two = head + "{% if has.A and has.B %}a: 1\n{% endif %}{% if has.C %}c: 1\n{% endif %}" \
                 "{% if has.D %}d: 1\n{% endif %}"
    failures = 0
    for text, wanted, what in ((one, 2 * 4 + 1, "one key per condition"), (two, 2 ** 4 - 1, "a condition on two keys")):
        got = len(bounded_keyset_documents(text))
        if got != wanted:
            failures += 1
            print("selftest: FAILED (bounded sets of keys, %s) -- %d sets rendered, %d wanted" % (what, got, wanted))
        else:
            print("selftest: ok -- the bounded sets of keys of a file with %s are %d" % (what, wanted))
    return failures


def run_real_list_cases():
    """Each scenario of real_scenarios deleted from the real file (each key asked for twice, which is
    one deletion) and read back by real_failure; then the first of them with CRLF line endings. Each is
    rendered for the bounded sets of keys of bounded_keyset_documents."""
    failures = 0
    with quick_rendering() as (keep_what_is_cached, forget_the_rest), bounded_key_sets():
        for ending, bound in (("\n", None), ("\r\n", REAL_CRLF_CASES)):
            text = CONFIG.read_text(encoding="utf-8").replace("\n", ending)
            template, problems = read_template(text)
            layout = read_layout(text, template)[0] if template else None
            if layout is None:
                print("selftest: FAILED (the real model list) -- it cannot be read: %s" % problems)
                return 1
            known = dangling(text)
            scenarios = real_scenarios(layout)
            keep_what_is_cached()
            for keys in scenarios[:bound]:
                wanted = [(provider, name, "gone") for provider, name in sorted(keys)] * 2
                new_text, outcomes = apply_removals(text, wanted)
                why = real_failure(text, keys, new_text, outcomes, layout, known)
                forget_the_rest()
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
    # What the weekly workflow sets in the job that runs this check makes the summary carry a link to
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
                   "deepseek": "api-docs.deepseek.com", "cloudflare": "developers.cloudflare.com"}

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


def code_anchor(name, **versions):
    """A floor anchor on the code scale: the model versions of benchmark files that stand for "name"."""
    return {"name": name, "code_epoch": versions}


def contract_router(anchor, rate, criterion="intelligence", last_resort=(), candidates=None, margin=None):
    ranking = {"criterion": criterion, "reason": "selftest"}
    if criterion != "intelligence_for_time":
        ranking["tie_margin_points"] = 2
    if criterion == "code_quality":
        ranking.update(source="Epoch AI selftest source", source_status="read", stand_in="intelligence")
    contract = {"intelligence_floor": {"anchor": anchor, "reason": "selftest"},
                "level_gain": {"min_points_per_second": rate, "reason": "selftest"},
                "ranking": ranking, "last_resort": {"members": list(last_resort), "reason": "selftest"}}
    if candidates:
        contract["intelligence_floor"]["candidates"] = list(candidates)
    if margin is not None:
        contract["intelligence_floor"]["margin"] = margin
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
        "code_fallback": {"source": "Epoch selftest code", "status": "not read yet", "method": "selftest",
                          "uncertainty": "selftest", "points": [[0, 90], [20, 50], [40, 10]]},
        "routers": {
            "pro": contract_router({"entry": "alpha", "level": "low"}, 0.2, last_resort=("juliet", "foxtrot"),
                                   candidates=({"entry": "sierra"}, {"entry": "alpha", "level": "low"},
                                               {"entry": "alpha", "level": "high"})),
            "flash": contract_router({"entry": "mike"}, 0.5,
                                     candidates=({"entry": "mike"}, {"entry": "charlie", "level": "non-reasoning"})),
            "flash-lite": dict(contract_router({"entry": "india"}, 1.5, criterion="intelligence_for_time"),
                               ranking={"criterion": "intelligence_for_time", "shared_quota_with": ["pro"], "reason": "selftest"}),
            "code": contract_router(code_anchor("Alpha code", deepswe_external=["alpha_medium"],
                                                swe_bench_verified=["alpha_medium"]), 0.2, criterion="code_quality"),
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
               (code["sierra"]["kind"] == "conforming" and code["sierra"]["verdict"] == "conforme",
                "sierra, slow and weak, was judged against a floor of the code scale that nothing read: %r" % code["sierra"]["verdict"])))
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
    judged("the order the contract gives puts the conforming first, by quality with the time deciding within the margin or by worth for the time for flash-lite, then the last resort tier, and leaves the rest out",
           first_wrong(
               (pro_order["proposed"] == ["alpha", "india", "juliet", "foxtrot"], "pro: %r" % pro_order["proposed"]),
               (flash_order["proposed"] == ["lima", "papa", "bravo", "kilo", "mike", "romeo"], "flash: %r" % flash_order["proposed"]),
               (lite_order["proposed"] == ["bravo", "kilo", "lima", "india"],
                "flash-lite goes by worth for its time (6, 4.5, -75) and ends with india, which shares pro's quota: %r" % lite_order["proposed"]),
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
               (played(lite_order) == [{"floor": 8, "main": ["bravo", "kilo", "lima", "india"], "last": []}],
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
    judged("a floor whose anchor cannot be read judges nothing: no member is under it, the floor has no value, the candidates still readable are compared, and the summary says that the anchor is not found",
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
         '"criterion" among: intelligence, intelligence_for_time, code_quality'),
        ("a shared quota on a router that does not value time", set_in(("routers", "pro", "ranking", "shared_quota_with"), ["flash"]),
         'is not ranked on "intelligence_for_time"'),
        ("a shared quota with the router itself", set_in(("routers", "flash-lite", "ranking", "shared_quota_with"), ["flash-lite"]),
         'has a "shared_quota_with" that is not a list of other routers'),
        ("a shared quota with a router that does not exist", set_in(("routers", "flash-lite", "ranking", "shared_quota_with"), ["ghost"]),
         'has a "shared_quota_with" that is not a list of other routers'),
        ("a shared quota with a router that derives from another", set_in(("routers", "flash-lite", "ranking", "shared_quota_with"), ["claude-code"]),
         'has a "shared_quota_with" that is not a list of other routers'),
        ("a shared quota that is no list", set_in(("routers", "flash-lite", "ranking", "shared_quota_with"), "pro"),
         'has a "shared_quota_with" that is not a list of other routers'),
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

        # The summary: the section from the command line, end to end, on a template and a contracts file.
        config = os.path.join(directory, "config.yaml.j2")
        Path(config).write_text(CONTRACT_TEMPLATE, encoding="utf-8")
        summary = os.path.join(directory, "summary.md")
        listing = answers_listing(CONTRACT_TEMPLATE)

        def run(arguments, environment=RANKING_KEYS, version=5.0):
            page = ranking_page(*contract_records())
            page["intelligence_index_version"] = version
            out = io.StringIO()
            Path(summary).unlink(missing_ok=True)
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                try:
                    status = main(arguments, opener=canned_opener(dict(listing, rankings=page), []),
                                  environment=environment)
                except SystemExit as error:
                    status = error.code
            return status, out.getvalue(), Path(summary).read_text(encoding="utf-8") if os.path.exists(summary) else ""

        online = ["--online", "--config", config, "--summary", summary, "--contracts", path]
        status, out, body = run(online)
        section = body.split("## Contrats par routeur")[1].split("\n## ")[0] if "## Contrats par routeur" in body else ""
        judged("with the ranking read, the summary carries a section of contracts: a table per router, the two orders, the floors side by side and what the mapping does not cover, and nothing else changes",
               first_wrong(
                   (status == 0 and "Aucune dérive." in body, "the section changed the status or the drift: %d" % status),
                   ("### `pro`" in section and "### `flash-lite`" in section and "### `claude-code`" in section, "a router has no table"),
                   ("Plancher 20 (Alpha (Low)), un niveau de plus tant qu'il rapporte au moins 0.2 points d'indice par seconde de plus, classé par l'indice d'intelligence, "
                    "le délai départageant deux membres à moins de 2 points d'écart." in section, "pro's contract is not said"),
                   ("Plancher 8 (India), un niveau de plus tant qu'il rapporte au moins 1.5 points d'indice par seconde de plus, classé par l'indice d'intelligence moins 1.5 points par seconde de délai moyen avant le premier jeton de la réponse, le plus grand en tête ; un membre qui a un délai et pas d'indice vient après ceux qui ont les deux, le plus rapide d'abord ; un membre qui est le même modèle chez le même fournisseur qu'un membre de `pro`, donc sur le même quota, passe après tous les autres, dans le même ordre." in section,
                    "flash-lite's criterion is not said"),
                   ("Plancher introuvable (Alpha code (Epoch, position de code) : archive d'Epoch AI non lue), aucun membre n'est jugé sous le plancher, "
                    "un niveau de plus tant qu'il rapporte au moins 0.2 points d'indice par seconde de plus, classé par la position de code "
                    "(source : Epoch AI selftest source, non lue (HTTP 404)) ; Artificial Analysis n'a pas d'indice de code, l'indice "
                    "d'intelligence en tient lieu à titre provisoire, le délai départageant deux membres à moins de 2 points d'écart." in section,
                    "code's ranking is not said as a stand-in, nor its floor as one nothing read"),
                   ("Dérivé de `code` : mêmes plancher (introuvable (Alpha code (Epoch, position de code) : archive d'Epoch AI non lue), "
                    "aucun membre n'est jugé sous le plancher), taux d'échange (0.2 points par seconde) et classement, et les modèles sans "
                    "appels d'outils en sont exclus." in section, "the derived router is not said"),
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
        judged("what a record's name carries into the summary is cut to plain words",
               first_wrong((hostile_lines(body) is None, str(hostile_lines(body))),
                           ("@bob" not in body and "<img" not in body, "markup reached the summary")))
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
        status_other, _, body_other = run(["--online", "--config", config, "--summary", summary])
        judged("without the ranking, or with another template and no contracts of its own, no section is written and the status is the same",
               first_wrong(("## Contrats par routeur" not in body_none, "a section without the ranking"),
                           ("## Contrats par routeur" not in body_other, "the repository's contracts were read against another template"),
                           (status_none == status and status_other == status, "the status moved")))
        broken_document = contract_document()
        del broken_document["routers"]["pro"]["level_gain"]["reason"]
        Path(path).write_text(yaml.safe_dump(broken_document), encoding="utf-8")
        status_bad, _, body_bad = run(online)
        judged("a contracts file with a structural problem says so in the summary, computes nothing, and changes neither the status nor the rest",
               first_wrong(("n'a pas la forme attendue" in body_bad and '"level_gain", has no "reason"' in body_bad, "the problem is not said"),
                           ("### `pro`" not in body_bad, "a table was written from a file that is wrong"),
                           (status_bad == status and "Aucune dérive." in body_bad, "the status or the drift moved")))
        Path(path).write_text(yaml.safe_dump(contract_document()), encoding="utf-8")
        real = vars(drift)["contracts_report"]

        def exploding(*arguments):
            raise RuntimeError("selftest: the computation failed with SECRET")

        vars(drift)["contracts_report"] = exploding
        try:
            status_boom, _, body_boom = run(online)
        finally:
            vars(drift)["contracts_report"] = real
        judged("a computation that fails says the kind of the error and nothing of its message, and never fails the run",
               first_wrong(("Le calcul a échoué (`RuntimeError`)" in body_boom, "the failure is not said"),
                           ("SECRET" not in body_boom, "the message of the error reached the summary"),
                           (status_boom == status and "Aucune dérive." in body_boom, "the status moved")))

        # A deleted entry leaves its row: reported as stale in the summary and as a notice in the plain run,
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
                    "- `zulu` (correspondance)\n- `zulu` (dernier recours de `code`)\n" in body_stale, "the summary does not list them"),
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

# The scores of the made-up archive, by benchmark file, and the positions they give (one more than the number
# of models that did strictly better, over the number of models of the file, as a percentage): DeepSWE has ten
# models, the position of y is 10 and of x3 50, of q and r 60 (a tie) and of p 80; SWE-bench has five (s 20, p
# 60, q 80); CursorBench has four (q 75); Terminal-Bench has four (s 50); ALE-Bench has ten (v 20, r 40, x3 50,
# p 60, q 70). "x1" to "x5" are models no entry lists, which are there to give the files the size they have.
EPOCH_SCORES = {
    "deepswe_external": {"p_high": 0.5, "q_high": 0.6, "r_high": 0.6, "v_high": 0.9, "y_high": 0.99,
                         "x1": 0.95, "x2": 0.8, "x3": 0.7, "x4": 0.4, "x5": 0.3},
    "swe_bench_verified": {"s_high": 0.9, "p_high": 0.7, "q_high": 0.5, "x1": 0.8, "x2": 0.1},
    "cursorbench_external": {"q_high": 0.3, "x1": 0.9, "x2": 0.6, "x3": 0.2},
    "terminalbench_external": {"s_high": 0.8, "x1": 0.9, "x2": 0.5, "x3": 0.1},
    "ale_bench_external": {"v_high": 1500, "r_high": 1200, "p_high": 1000, "p_low": 900, "q_high": 900,
                           "x1": 1600, "x2": 1400, "x3": 1100, "x4": 800, "x5": 700},
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
# The floor of "code" in the made-up archive: the model x3, at 50 in both files that hold it.
EPOCH_FLOOR = code_anchor("Floor Model", deepswe_external=["x3"], ale_bench_external=["x3"])


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

    saved = {name: vars(drift)[name] for name in limits}
    vars(drift).update(limits)
    try:
        return read_epoch(opener, "2026-01-02"), calls
    finally:
        vars(drift).update(saved)


def epoch_archive(scores=None, eci=None):
    """The state of an archive that was read, built from "scores" and "eci" without a zip: what
    read_epoch gives."""
    scores = EPOCH_SCORES if scores is None else scores
    return {"status": "read", "date": "2026-01-02", "skipped": {}, "eci": dict(EPOCH_ECI if eci is None else eci),
            "files": {key: {"scores": dict(found), "rows": len(found), "bad": 0} for key, found in scores.items()}}


def epoch_document():
    """The contracts of "code" and of "claude-code" over the cascades of EPOCH_TEMPLATE: a floor at the code
    position of EPOCH_FLOOR (and two other anchors to compare), z exempt from it, the made-up model versions
    of EPOCH_IDS, and a conversion that gives 70 at an index of 10 and 14 from an index of 20 up."""
    document = {"routers": {"code": contract_router(
                    EPOCH_FLOOR, 0.2, criterion="code_quality", last_resort=("z",),
                    candidates=(EPOCH_FLOOR, code_anchor("Pee Code", deepswe_external=["p_high"], swe_bench_verified=["p_high"]),
                                code_anchor("Vee Code", deepswe_external=["v_high"], ale_bench_external=["v_high"]))),
                            "claude-code": {"derives_from": "code", "requires": ["tools"], "reason": "selftest"}},
                "models": {name: contract_mapping(name, "n/a") for name in "pqrstuvwyz"},
                "code_fallback": {"source": "Epoch selftest code", "status": "read", "flag": "estimated", "method": "selftest",
                                  "uncertainty": "selftest", "points": [[0, 100], [10, 70], [20, 14]]},
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
    """A template and a contracts file written into "directory", and (run, config, path, summary): run(arguments,
    served, environment, opener) is the command line on them, with the ranking of contract_records() read and
    "served" as the archive of Epoch AI (nothing served is a 404), and gives (status, output, the summary written,
    the requests made for the archive)."""
    config, path, summary = (os.path.join(directory, name) for name in ("config.yaml.j2", "contracts.yaml", "summary.md"))
    Path(config).write_text(template_text, encoding="utf-8")
    Path(path).write_text(yaml.safe_dump(document), encoding="utf-8")
    listing = answers_listing(template_text)
    page = ranking_page(*contract_records())
    page["intelligence_index_version"] = 5.0

    def run(arguments, served=None, environment=RANKING_KEYS, opener=None):
        calls, out = [], io.StringIO()
        Path(summary).unlink(missing_ok=True)
        answers = dict(listing, rankings=page, **({} if served is None else {"epoch": served}))
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            status = main(arguments, opener=opener or canned_opener(answers, calls), environment=environment)
        return (status, out.getvalue(), Path(summary).read_text(encoding="utf-8") if os.path.exists(summary) else "",
                [url for url, _ in calls if url == EPOCH_URL])

    return run, config, path, summary


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
               (good["files"]["ale_bench_external"]["rows"] == 10 and good["files"]["ale_bench_external"]["bad"] == 0, "rows counted"),
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

    # The position of a score in a file: smaller is better, and models with one score share one position.
    scores_ten = EPOCH_SCORES["deepswe_external"]
    judged("the position of a score is one more than the number of models of the file that did strictly better, over the number of models of the file, as a percentage, and models with the same score share it",
           first_wrong((epoch_position(0.99, scores_ten) == 10, "the best of ten is not at a tenth"),
                       (epoch_position(0.3, scores_ten) == 100, "the last of ten is not at the end"),
                       (epoch_position(0.6, scores_ten) == 60 and epoch_position(0.7, scores_ten) == 50, "a tie shares its best place"),
                       (epoch_position(0.5, scores_ten) == 80, "the place after a tie of two skips both"),
                       (epoch_position(5, {"a": 5, "b": 5, "c": 5, "d": 5}) == 25, "all equal"),
                       (epoch_position(7, {"a": 7}) == 100, "a file of one model"),
                       (epoch_position(0.25, {"a": 0.1, "b": 0.3, "c": 0.2, "d": 0.4}) == 75, "a score no model has, between two"),
                       (epoch_position(0.1, {"a": 0.1, "b": 0.3}) == 100, "the last of two"),
                       (epoch_position(0.3, {"a": 0.1, "b": 0.3}) == 50, "the first of two")))
    archive = epoch_archive()
    mappings = epoch_document()["models"]

    def quality_of(name, given=archive):
        return member_quality(mappings[name], given)

    judged("the positions of an entry are those of the best of the versions it lists in each file, and its code position is their median",
           first_wrong((quality_of("p")["positions"] == {"deepswe_external": 80, "swe_bench_verified": 60, "ale_bench_external": 60}
                        and quality_of("p")["position"] == 60 and quality_of("p")["why"] is None, "p: %r" % quality_of("p")),
                       (quality_of("q")["positions"] == {"deepswe_external": 60, "swe_bench_verified": 80, "cursorbench_external": 75,
                                                         "ale_bench_external": 70} and quality_of("q")["position"] == 72.5,
                        "q, whose four positions have a median that is the middle of the two: %r" % quality_of("q")),
                       (quality_of("r")["position"] == 50 and quality_of("s")["position"] == 35 and quality_of("v")["position"] == 25,
                        "r, s, v: %r %r %r" % (quality_of("r")["position"], quality_of("s")["position"], quality_of("v")["position"]))))
    judged("a model listed under several versions in one file counts by the best of them, and a version the file lacks counts for nothing",
           first_wrong((quality_of("p")["positions"]["ale_bench_external"] == 60, "p_low, at 70, was taken for its best"),
                       (member_quality(dict(mappings["p"], epoch={"deepswe_external": ["nowhere", "p_high"], "swe_bench_verified": ["p_high"]}), archive)["positions"]
                        == {"deepswe_external": 80, "swe_bench_verified": 60}, "a version the file lacks changed the position"),
                       (member_quality(dict(mappings["p"], epoch={"deepswe_external": ["p_high"], "swe_bench_verified": ["nowhere"]}), archive)["why"] == "few_files",
                        "a file where none of the versions is counted")))
    judged("a code position needs two files at least, and a member that has none says why: no version listed, none found, or too few files",
           first_wrong((quality_of("y")["positions"] == {"deepswe_external": 10} and quality_of("y")["position"] is None
                        and quality_of("y")["why"] == "few_files", "y, in one file: %r" % quality_of("y")),
                       (quality_of("t")["position"] is None and quality_of("t")["why"] == "no_ids", "t: %r" % quality_of("t")),
                       (quality_of("u")["position"] is None and quality_of("u")["why"] == "no_scores" and quality_of("u")["positions"] == {},
                        "u: %r" % quality_of("u")),
                       (quality_of("z")["why"] == "no_ids" and member_quality(None, archive)["why"] == "no_ids", "a member with no epoch, or no mapping"),
                       (member_quality(dict(mappings["p"], epoch={"webdev_arena_external": ["p_high"]}), archive)["positions"] == {},
                        "another arena was read"),
                       (member_quality(mappings["q"], epoch_archive({"deepswe_external": {"q_high": 0.1}}))["why"] == "few_files",
                        "a file the archive lacks was invented"),
                       (median_position({"a": 10, "b": 40}) == 25 and median_position({"a": 10}) is None and median_position({}) is None,
                        "the median of two, of one and of none")))
    judged("a router is ranked on code quality only on a router that says so and with the archive read, and a position is the member's alone: no pool",
           first_wrong((router_quality(["p", "q"], {"ranking": {"criterion": "intelligence"}}, mappings, archive) is None, "a router that is not on code"),
                       (router_quality(["p", "q"], {"ranking": {"criterion": "code_quality"}}, mappings, None) is None, "an archive that was not read"),
                       (router_quality(["p"], {"ranking": {"criterion": "code_quality"}}, mappings, archive)["p"]["position"] == 60, "a pool of one"),
                       (router_quality(["p", "q", "r"], {"ranking": {"criterion": "code_quality"}}, mappings, archive)["p"]
                        == router_quality(["p"], {"ranking": {"criterion": "code_quality"}}, mappings, archive)["p"], "a position depends on the pool")))

    # The conversion of the index into a code position: the line through the points, clamped beyond them.
    points = [(0.0, 100.0), (10.0, 70.0), (20.0, 14.0)]
    judged("an index is turned into a code position by the line through the declared points, and kept at the first and the last position beyond them",
           first_wrong((index_to_position(0, points) == 100 and index_to_position(10, points) == 70 and index_to_position(20, points) == 14, "a point is not itself"),
                       (index_to_position(5, points) == 85 and abs(index_to_position(15, points) - 42) < 1e-9, "inside a segment"),
                       (index_to_position(-3, points) == 100 and index_to_position(-0.001, points) == 100, "below the first point is the first position"),
                       (index_to_position(35, points) == 14 and index_to_position(20.001, points) == 14, "above the last point is the last position"),
                       (index_to_position(10.0001, points) < 70 and index_to_position(9.9999, points) > 70, "a point is not continuous")))
    judged("the points of the conversion are read from the contracts, and none where they are not well formed",
           first_wrong((code_points(epoch_document()) == points, "points: %r" % (code_points(epoch_document()),)),
                       (code_points({}) is None and code_points({"code_fallback": "x"}) is None, "no block"),
                       (code_points({"code_fallback": {"points": [[0, 90]]}}) is None, "one point"),
                       (code_points({"code_fallback": {"points": [[0, 90], [10, "5"]]}}) is None, "a point that is no number"),
                       (code_points({"code_fallback": {"points": [[0, 90], [10]]}}) is None, "a point that is no pair")))
    judged("a member's code figure is its measured position, else the one its index estimates and said so, else none",
           first_wrong((code_figure(quality_of("p"), 5, points) == (60, False), "a measured position was replaced by an estimate"),
                       (code_figure(quality_of("t"), 15, points) == (42, True), "t: %r" % (code_figure(quality_of("t"), 15, points),)),
                       (code_figure(quality_of("t"), None, points) == (None, False), "no index, no position"),
                       (code_figure(quality_of("t"), 15, None) == (None, False), "no conversion declared, no estimate"),
                       (code_figure(quality_of("y"), 12, points) == (index_to_position(12, points), True), "a member in one file is estimated")))

    # The anchor of a floor on the code scale: the versions it names, computed as a member's, and what it says when it cannot be read.
    def anchored(anchor, given=archive):
        return anchor_floor(anchor, {}, {}, {}, None, given)

    judged("a floor anchored on model versions of benchmark files has the code position those versions have, as a member's is computed, and says it is read in the archive of Epoch AI",
           first_wrong((anchored(EPOCH_FLOOR) == (50, "Floor Model (Epoch, position de code)"), "the floor: %r" % (anchored(EPOCH_FLOOR),)),
                       (anchored(code_anchor("Pee", deepswe_external=["p_high"], swe_bench_verified=["p_high"], ale_bench_external=["p_low", "p_high"]))[0] == 60,
                        "an anchor of three files with two versions in one"),
                       (anchored(code_anchor("Mix", deepswe_external=["nowhere", "x3"], ale_bench_external=["x3"]))[0] == 50, "a version the file lacks"),
                       (anchor_scale(EPOCH_FLOOR) == "code" and anchor_scale({"entry": "a"}) == "index" and anchor_scale({"epoch": "A"}) == "index",
                        "the scale of an anchor")))
    judged("a floor on model versions that cannot be read has no value and says why: the archive not read, versions in too few files, or in none",
           first_wrong((anchored(EPOCH_FLOOR, None) == (None, "Floor Model (Epoch, position de code) : archive d'Epoch AI non lue"), "unread: %r" % (anchored(EPOCH_FLOOR, None),)),
                       (anchored(code_anchor("One", deepswe_external=["x3"], ale_bench_external=["nowhere"])) == (
                           None, "One (Epoch, position de code) : trouvé dans moins de 2 benchmarks de l'archive"), "one file only"),
                       (anchored(code_anchor("None", deepswe_external=["nowhere"], ale_bench_external=["nowhere"]))[0] is None, "no version found"),
                       (anchored(code_anchor("Lacks", webdev_arena_external=["x3"], cursorbench_external=["x3"]))[0] is None, "another arena, and a file the archive lacks"),
                       (anchored(EPOCH_FLOOR, epoch_archive({"deepswe_external": EPOCH_SCORES["deepswe_external"]}))[0] is None,
                        "a file the archive lacks was invented")))

    # The order a router's contract gives: the members that have a position first, measured or estimated, smallest first.
    template, problems = read_template(EPOCH_TEMPLATE)
    if template is None or problems:
        print("selftest: BROKEN CASE (the template of the code quality) -- %r" % problems)
        return failures + 1
    document, ranking = epoch_document(), epoch_ranking()
    report = contracts_report(template, ranking, document, archive)
    code, code_order = contract_rows(report, "code")
    claude, claude_order = contract_rows(report, "claude-code")
    judged("code is ordered by code position: the members that have one, measured or estimated, smallest first, then the last resort and the members past the floor in the order of the cascade",
           first_wrong((code_order["proposed"] == ["v", "s", "t", "r", "p", "q", "u", "z"], "code: %r" % code_order["proposed"]),
                       (code_order["contract"]["intelligence_floor"]["value"] == 50 and code_order["contract"]["intelligence_floor"]["scale"] == "code",
                        "the floor: %r" % code_order["contract"]["intelligence_floor"]),
                       ([code[name]["code_position"] for name in "vstrpq"] == [25, 35, 42, 50, 60, 72.5], "positions: %r" % [code[name]["code_position"] for name in "vstrpq"]),
                       (code["z"]["last_resort"] and code["z"]["code_estimated"], "z"),
                       (code_order["current"] == ["p", "q", "r", "s", "t", "u", "v", "z"], "the current order moved")))
    judged("a member at the floor conforms, one past it is under the floor with its figures said, an estimated one is judged like a measured one and said estimated",
           first_wrong((code["r"]["kind"] == "conforming" and code["r"]["verdict"] == "conforme", "r, at the floor: %r" % code["r"]["verdict"]),
                       (code["p"]["verdict"] == "sous le plancher (60 % contre 50 %) : dernier recours" and code["q"]["kind"] == "below_floor",
                        "p: %r" % code["p"]["verdict"]),
                       (code["u"]["kind"] == "below_floor" and code["u"]["verdict"] == "sous le plancher (58.8 % estimé contre 50 %) : dernier recours",
                        "u, estimated and past the floor: %r" % code["u"]["verdict"]),
                       (code["t"]["kind"] == "conforming" and code["t"]["verdict"] == "conforme (estimé)" and code["t"]["code_estimated"],
                        "t, estimated and inside: %r" % code["t"]["verdict"]),
                       (code["v"]["verdict"] == "conforme" and not code["v"]["code_estimated"], "v is measured"),
                       (code["z"]["verdict"] == "conforme (dernier recours)", "z is exempt from the floor")))
    judged("an estimated member is placed between measured ones by its figure, and has no time of its own, where a measured one keeps the time of its record",
           first_wrong((code_order["proposed"].index("s") < code_order["proposed"].index("t") < code_order["proposed"].index("r"),
                        "t, estimated at 42, is not between s at 35 and r at 50"),
                       (code["t"]["first_answer"] is None and code["s"]["first_answer"] == 3, "t: %r s: %r" % (code["t"]["first_answer"], code["s"]["first_answer"]))))
    judged("claude-code is ranked as code is, on the positions of its own members: the same positions, the same floor, the order of the members they share",
           first_wrong((claude_order["proposed"] == ["s", "t", "y", "p", "q"], "claude-code: %r" % claude_order["proposed"]),
                       (claude["y"]["code_estimated"] and abs(claude["y"]["code_position"] - 47.6) < 1e-9 and claude["y"]["verdict"] == "conforme (estimé)",
                        "y, in one file, is estimated from its index: %r" % claude["y"]["code_position"]),
                       ([name for name in claude_order["proposed"] if name in code_order["proposed"]]
                        == [name for name in code_order["proposed"] if name in claude_order["proposed"]], "the order of the common members differs"),
                       (all(claude[name]["code_position"] == code[name]["code_position"] for name in "pqst"), "a member's position differs"),
                       (claude_order["contract"]["intelligence_floor"]["value"] == 50, "the floor")))
    judged("each floor the contract compares is played side by side on the code scale, named by the anchor, and the proposed one is marked",
           first_wrong(([effect["floor"] for effect in code_order["floors"]] == [50, 70, 25], "floors: %r" % [effect["floor"] for effect in code_order["floors"]]),
                       ([effect["text"] for effect in code_order["floors"]] == ["Floor Model (Epoch, position de code)", "Pee Code (Epoch, position de code)",
                                                                                 "Vee Code (Epoch, position de code)"], "texts"),
                       (code_order["floors"][1]["main"] == ["v", "s", "t", "r", "p", "u"] and code_order["floors"][1]["last"] == ["q", "z"],
                        "at 70, only q is past it, u being estimated at 58.8: %r" % code_order["floors"][1]),
                       (code_order["floors"][2]["main"] == ["v"] and code_order["floors"][2]["last"] == ["p", "q", "r", "s", "t", "u", "z"],
                        "at 25, only v is inside: %r" % code_order["floors"][2])))

    def order_rows(*members):
        return [{"name": name, "position": number, "kind": "conforming", "last_resort": False,
                 "intelligence": 9, "first_answer": seconds, "code_position": place, "code_estimated": estimated,
                 "record": {"intelligence": 9, "first_answer": seconds}, "quality": {"position": place}}
                for number, (name, place, seconds, estimated) in enumerate(members)]

    contract_ranking_block = {"criterion": "code_quality", "tie_margin_points": 2}
    judged("equal positions are ordered by time, a member with no time after the others, then by position in the cascade",
           first_wrong((contract_order(order_rows(("a", 20, 5, False), ("b", 20, 3, False), ("c", 20, None, False), ("d", 20, 3, False)), contract_ranking_block)
                        == ["b", "d", "a", "c"], "ties"),
                       (contract_order(order_rows(("a", 30, 1, False), ("b", 5, 9, False), ("c", 10, 9, False), ("d", 1.5, 9, False)), contract_ranking_block)
                        == ["d", "b", "c", "a"], "the smallest first, whatever the order of the cascade or the time"),
                       (contract_order(order_rows(("a", 1, 5, False)) + [dict(order_rows(("z", 0.5, 1, False))[0], last_resort=True)], contract_ranking_block)
                        == ["a", "z"], "the last resort stays at the tail whatever its position")))
    judged("positions less than the margin apart are taken as tied and ordered by time, an estimated one last among them, and a gap of the margin or more is no tie",
           first_wrong((contract_order(order_rows(("a", 20, 9, False), ("b", 21.5, 3, False), ("c", 23.5, 1, False)), contract_ranking_block)
                        == ["b", "a", "c"], "b is within 2 of a and faster, c is 3.5 from the start of the group"),
                       (contract_order(order_rows(("a", 20, 9, False), ("b", 22, 3, False)), contract_ranking_block) == ["a", "b"],
                        "a gap of exactly the margin is no tie"),
                       (contract_order(order_rows(("a", 20, 9, False), ("e", 19, None, True)), contract_ranking_block) == ["a", "e"],
                        "an estimated member within the margin has no time and goes after the measured one"),
                       (contract_order(order_rows(("a", 20, 9, False), ("e", 15, None, True)), contract_ranking_block) == ["e", "a"],
                        "an estimated member clear of the margin is ahead"),
                       (contract_order(order_rows(("e", 20, None, True), ("f", 20.5, None, True), ("a", 21, 9, False)), contract_ranking_block)
                        == ["a", "e", "f"], "two estimated members of one group keep the order of the cascade")))
    judged("a router with no code quality read is ordered as before, on the intelligence index alone",
           first_wrong((contract_order([dict(row, quality=None, intelligence=index) for row, index in zip(
               order_rows(("a", 1, 1, False), ("b", 9, 1, False)), (5, 30))], contract_ranking_block) == ["b", "a"],
                        "a member with a position was ranked on it without the archive"),
                       (contract_order([{key: value for key, value in row.items() if key != "quality"}
                                        for row in order_rows(("a", 1, 1, False), ("b", 9, 1, False))], contract_ranking_block) == ["a", "b"],
                        "rows with no quality at all, whose index is equal")))
    # A router that values time: what a member is worth for its time, and the members that share a quota last.
    def worth_rows(*members):
        """(name, intelligence, seconds, shared quota, last resort) -> rows as router_rows makes them."""
        return [{"name": name, "position": number, "kind": "conforming", "last_resort": resort, "shared_quota": shared,
                 "intelligence": index, "first_answer": seconds, "record": {"intelligence": index, "first_answer": seconds},
                 "worth": time_worth(index, seconds, 3)}
                for number, (name, index, seconds, shared, resort) in enumerate(members)]

    timed_ranking = {"criterion": "intelligence_for_time"}
    judged("a member is worth its index less the rate times its time, and one with no index or no time has no worth",
           first_wrong((time_worth(26.9, 7.62, 3) == 26.9 - 3 * 7.62, "the worth of Gemini 4 Hydrogen at Low"),
                       (time_worth(None, 5, 3) is None and time_worth(5, None, 3) is None, "a missing figure was given a worth"),
                       (time_worth(0, 2, 3) == -6, "an index of zero is a figure")))
    judged("a router that values time puts the greatest worth first, then the members with a time and no index by shortest time, the current order settling a tie",
           first_wrong((contract_order(worth_rows(("a", 6, 9, False, False), ("b", 20, 4, False, False), ("c", 10, 1, False, False),
                                                 ("d", 10, 1, False, False)), timed_ranking) == ["b", "c", "d", "a"],
                        "worth first (8, 7, 7, -21), c and d tied on 7 in the current order"),
                       (contract_order(worth_rows(("a", None, 3, False, False), ("b", None, 1, False, False), ("c", 4, 2, False, False),
                                                 ("d", None, 1, False, False)), timed_ranking) == ["c", "b", "d", "a"],
                        "no index: after those that have both, shortest time first, a tie in the current order"),
                       (contract_order(worth_rows(("a", 5, 9, False, False), ("b", None, 1, False, False)), timed_ranking) == ["a", "b"],
                        "a worth below zero still comes before a member with no index")))
    judged("the members that share a quota come after every member that has one of its own, in the same order, and the last resort closes the cascade",
           first_wrong((contract_order(worth_rows(("hydrogen", 27, 7, True, False), ("lite", 6, 3, False, False), ("flash", 22, 5, True, False),
                                                 ("bare", None, 1, False, False)), timed_ranking) == ["lite", "bare", "flash", "hydrogen"],
                        "the best worth of the router is last, behind a member with no index that has its own quota"),
                       (contract_order(worth_rows(("shared", 27, 7, True, False), ("paid", None, 1, False, True), ("lite", 6, 3, False, False)),
                                       timed_ranking) == ["lite", "shared", "paid"], "the last resort closes the cascade, after the shared members"),
                       (contract_order(worth_rows(("sa", None, 1, True, False), ("sb", 5, 9, True, False)), timed_ranking) == ["sb", "sa"],
                        "among the shared members, the same order")))
    drawing = {name: {"name": name, "model": model, "api_base": base}
               for name, model, base in (("hydrogen", "gemini/h", None), ("hydrogen-low", "gemini/h", None), ("lite", "gemini/l", None),
                                         ("twin", "openai/h", "https://one"), ("twin-two", "openai/h", "https://two"),
                                         ("nameless", None, None), ("pro-twin", "openai/h", "https://one"))}
    fallbacks = {("router_settings.fallbacks", "pro"): ["hydrogen", "pro-twin", "nameless", "missing"]}
    judged("a member shares a quota when it is the same model of the same provider as a member of a router the ranking names, whatever its name, and not otherwise",
           first_wrong((shared_quota_names(["hydrogen-low", "lite", "twin", "hydrogen"], {"shared_quota_with": ["pro"]}, fallbacks, drawing)
                        == {"hydrogen-low", "hydrogen", "twin"}, "same model and base: shared, another model: not"),
                       (shared_quota_names(["twin-two"], {"shared_quota_with": ["pro"]}, fallbacks, drawing) == frozenset(),
                        "the same model id at another address is another quota"),
                       (shared_quota_names(["hydrogen-low"], {}, fallbacks, drawing) == frozenset(), "a ranking that names no router shares nothing"),
                       (shared_quota_names(["nameless", "ghost"], {"shared_quota_with": ["pro"]}, fallbacks, drawing) == frozenset(),
                        "an entry with no model, or no entry, shares nothing"),
                       (shared_quota_names(["hydrogen"], {"shared_quota_with": ["flash"]}, fallbacks, drawing) == frozenset(),
                        "a router with no cascade shares nothing")))
    lite_document_shared = contract_document()
    lite_document_shared["routers"]["flash-lite"]["intelligence_floor"] = {"none": True, "reason": "selftest"}
    sharing = contracts_report(read_template(CONTRACT_TEMPLATE.replace("    - flash-lite: [kilo, india, bravo, lima, quebec]\n",
                                                                        "    - flash-lite: [kilo, india, bravo, lima, quebec, sierra]\n").replace(
        "groq/vendor/sierra-model", "groq/vendor/alpha-model"))[0], contract_ranking(), lite_document_shared)
    shared_rows, shared_order = contract_rows(sharing, "flash-lite")
    judged("the report finds the members that share a quota by itself in the template: india is pro's own entry and sierra is pro's alpha under another name, and both are said so and end the cascade",
           first_wrong((shared_rows["india"]["shared_quota"] and shared_rows["sierra"]["shared_quota"]
                        and not any(shared_rows[name]["shared_quota"] for name in ("kilo", "bravo", "lima", "quebec")),
                        "shared: %r" % [name for name, row in shared_rows.items() if row["shared_quota"]]),
                       (shared_order["proposed"] == ["bravo", "kilo", "lima", "india", "sierra"],
                        "the shared members come last, in the order of their worth: %r" % shared_order["proposed"]),
                       (shared_rows["india"]["verdict"] == "conforme ; quota partagé : en dernier", "said in the verdict: %r" % shared_rows["india"]["verdict"])))
    stand_in = contracts_report(template, ranking, document)
    failed_read = contracts_report(template, ranking, document, {"status": "error", "date": "2026-01-02", "error": "HTTP 404"})
    stand_code, stand_order = contract_rows(stand_in, "code")
    judged("without the archive, read or failed, code and claude-code keep the intelligence index as their order, with no quality on any row and a floor that is not found",
           first_wrong((stand_order["proposed"] == ["q", "p", "r", "s", "t", "u", "v", "z"], "code: %r" % stand_order["proposed"]),
                       (contract_rows(stand_in, "claude-code")[1]["proposed"] == ["q", "p", "s", "y", "t"],
                        "claude-code: %r" % contract_rows(stand_in, "claude-code")[1]["proposed"]),
                       (all(row["quality"] is None and row["code_position"] is None for row in stand_code.values()) and stand_order["quality"] is None,
                        "a quality without the archive"),
                       (stand_order["contract"]["intelligence_floor"]["value"] is None
                        and not any(row["kind"] == "below_floor" for row in stand_code.values()), "a floor read without the archive"),
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
    no_conversion = dict(epoch_document())
    del no_conversion["code_fallback"]
    bare_code, bare_order = contract_rows(contracts_report(template, ranking, no_conversion, archive), "code")
    judged("without a conversion declared a member that has no code position is not placed, and a member with neither a position nor an index stays where it is, flagged",
           first_wrong((bare_order["proposed"] == ["v", "s", "r", "p", "q", "z"], "code: %r" % bare_order["proposed"]),
                       (bare_code["t"]["kind"] == "unrankable" and bare_code["t"]["verdict"] == "inclassable : pas de position de code", "t: %r" % bare_code["t"]["verdict"])))
    unindexed = contracts_report(template, contract_ranking([timed_model(name, name.upper(), None if name == "t" else index, 2)
                                                             for name, index in (("p", 30), ("q", 30), ("r", 25), ("s", 20), ("t", 15), ("u", 12),
                                                                                 ("v", 5), ("z", 50))]), epoch_document(), archive)
    unindexed_code, unindexed_order = contract_rows(unindexed, "code")
    judged("a member with neither a code position nor an index is unrankable and not placed, and the others are placed as they were",
           first_wrong((unindexed_code["t"]["kind"] == "unrankable" and unindexed_code["t"]["code_position"] is None
                        and unindexed_code["t"]["verdict"] == "inclassable : pas de position de code", "t: %r" % unindexed_code["t"]["verdict"]),
                       ("t" not in unindexed_order["proposed"] and unindexed_order["proposed"] == ["v", "s", "r", "p", "q", "u", "z"], "code: %r" % unindexed_order["proposed"])))

    # The margin of a floor: a member conforms while it is no more than the margin from the floor, on the worse side.
    margin_code = epoch_document()
    margin_code["routers"]["code"]["intelligence_floor"]["margin"] = 10
    margin_report = contracts_report(template, ranking, margin_code, archive)
    margin_rows, margin_order = contract_rows(margin_report, "code")
    judged("on the code scale a member is past the floor only when its position is over the floor plus the margin, and the margin is said with the floor",
           first_wrong((margin_rows["p"]["kind"] == "conforming" and margin_rows["p"]["verdict"] == "conforme", "p, at 60 for a floor of 50 and a margin of 10: %r" % margin_rows["p"]["verdict"]),
                       (margin_rows["q"]["kind"] == "below_floor" and margin_rows["q"]["verdict"] == "sous le plancher (72.5 % contre 50 %, marge 10) : dernier recours",
                        "q, at 72.5: %r" % margin_rows["q"]["verdict"]),
                       (margin_rows["u"]["kind"] == "conforming" and margin_rows["u"]["verdict"] == "conforme (estimé)",
                        "u, estimated at 58.8, inside the margin: %r" % margin_rows["u"]["verdict"]),
                       (margin_order["proposed"] == ["v", "s", "t", "r", "p", "u", "q", "z"], "code: %r" % margin_order["proposed"]),
                       (floor_text(margin_order["contract"]["intelligence_floor"]) == "50 % (Floor Model (Epoch, position de code)), marge 10", "the floor is said without its margin")))
    edge_code = epoch_document()
    edge_code["routers"]["code"]["intelligence_floor"]["margin"] = 9.9
    edge_rows, _ = contract_rows(contracts_report(template, ranking, edge_code, archive), "code")
    judged("a member exactly the margin from the floor conforms, and one just over is past it",
           first_wrong((margin_rows["p"]["kind"] == "conforming", "exactly at the margin is refused"),
                       (edge_rows["p"]["kind"] == "below_floor", "a hair over the margin is accepted"),
                       (contract_rows(contracts_report(template, ranking, epoch_document(), archive), "code")[0]["p"]["kind"] == "below_floor", "no margin")))

    # The summary.
    section = "\n".join(contracts_section({"contracts": report}))
    code_block = section.split("### `code`")[1].split("### `claude-code`")[0]
    claude_block = section.split("### `claude-code`")[1]
    judged("the summary says, for code and claude-code, the position of each member in each benchmark, its code position, the place it gives, which members are placed on an estimate, with the attribution and the day of the reading",
           first_wrong(
               ("Position de code, d'après Epoch AI, benchmark data, CC BY 4.0 (<https://epoch.ai/benchmarks>, archive lue le 2026-01-02)." in code_block
                and "Position de code, d'après Epoch AI, benchmark data, CC BY 4.0" in claude_block, "the attribution or the day is missing"),
               ("| Membre | DeepSWE | SWE-bench Verified | CursorBench | Terminal-Bench | ALE-Bench | Position de code | Place |" in code_block, "the table"),
               ("| `v` | 30 % | — | — | — | 20 % | 25 % | 1 |" in code_block and "| `s` | — | 20 % | — | 50 % | — | 35 % | 2 |" in code_block,
                "v and s: %s" % code_block[:3000]),
               ("| `t` | — | — | — | — | — | 42 % (estimé) | 3 |" in code_block, "t, estimated, in its place"),
               ("| `r` | 60 % | — | — | — | 40 % | 50 % | 4 |" in code_block, "r"),
               ("| `p` | 80 % | 60 % | — | — | 60 % | 60 % | sous le plancher |" in code_block
                and "| `q` | 60 % | 80 % | 75 % | — | 70 % | 72.5 % | sous le plancher |" in code_block, "p and q"),
               ("| `u` | — | — | — | — | — | 58.8 % (estimé) | sous le plancher |" in code_block, "u, estimated and under the floor"),
               ("| `z` | — | — | — | — | — | 14 % (estimé) | dernier recours |" in code_block, "z"),
               ("Sans position de code mesurée, placés sur une position estimée d'après leur indice d'intelligence : "
                "`t` (aucun identifiant Epoch connu), `u` (aucun score dans l'archive pour ses identifiants), `z` (aucun identifiant Epoch connu)." in code_block,
                "the estimated: %s" % code_block[-1500:]),
               ("| `y` | 10 % | — | — | — | — | 47.6 % (estimé) | 3 |" in claude_block
                and "`y` (moins de 2 benchmarks où il a un score)" in claude_block,
                "y, in one file: %s" % claude_block[:2500]),
               ("Ordre des contrats : `v` > `s` > `t` > `r` > `p` > `q` > `u` > `z`." in code_block, "the order"),
               ("WebDev Arena et toute arène de design ou d'interface ne sont pas lues." in code_block, "the exclusion is not said"),
               ("Plancher 50 % (Floor Model (Epoch, position de code)), un niveau de plus" in code_block
                and "Dérivé de `code` : mêmes plancher (50 % (Floor Model (Epoch, position de code)))" in claude_block, "the floor is not said as a position"),
               ("(source : Epoch AI selftest source, lue le 2026-01-02), la médiane des positions sur les benchmarks, la plus petite en tête, "
                "le délai départageant deux membres à moins de 2 points de position d'écart ; un membre qui n'en a pas reçoit une position estimée d'après son indice d'intelligence"
                in code_block, "the ranking is not said: %s" % code_block[:900]),
               ("| 50 % (Floor Model (Epoch, position de code)) (proposé) |" in code_block and "| 70 % (Pee Code (Epoch, position de code)) |" in code_block
                and "| 25 % (Vee Code (Epoch, position de code)) |" in code_block, "the floors side by side"),
               ("non lue" not in section, "an archive that was read is said not to be")))
    skipped = dict(archive, skipped={"swe_bench_verified": "absent from the archive"})
    skipped["files"] = {key: found for key, found in archive["files"].items() if key != "swe_bench_verified"}
    skipped_section = "\n".join(contracts_section({"contracts": contracts_report(template, ranking, document, skipped)}))
    judged("a file of the archive that was not read is said, and its figures are not used",
           first_wrong(("Fichiers de l'archive non lus : SWE-bench Verified (`absent from the archive`)." in skipped_section, "the skipped file is not said"),
                       ("| `s` | — | — | — | 50 % | — | " in skipped_section and "| `s` | — | 20 % |" not in skipped_section, "s was placed on a file that was not read")))
    unread_section = "\n".join(contracts_section({"contracts": stand_in}))
    failed_section = "\n".join(contracts_section({"contracts": failed_read}))
    judged("an archive that was not read leaves the stand-in, and the summary says that the source is not read: no quality block, no position, and a floor that is not found",
           first_wrong(("(source : Epoch AI selftest source, non lue) ; Artificial Analysis n'a pas d'indice de code, l'indice d'intelligence en tient lieu à titre provisoire"
                        in unread_section, "unread: %s" % unread_section[:500]),
                       ("(source : Epoch AI selftest source, non lue (HTTP 404)) ; Artificial Analysis n'a pas d'indice de code" in failed_section,
                        "failed: %s" % failed_section[:500]),
                       ("Position de code, d'après" not in unread_section and "Position de code, d'après" not in failed_section, "a quality block without the archive"),
                       ("Plancher introuvable (Floor Model (Epoch, position de code) : archive d'Epoch AI non lue), aucun membre n'est jugé sous le plancher" in unread_section,
                        "the floor that nothing read is not said"),
                       ("Ordre des contrats : `q` > `p` > `r` > `s` > `t` > `u` > `v` > `z`." in unread_section, "the order moved without the archive"),
                       ("CC BY" not in unread_section and "CC BY" not in failed_section, "an attribution for a source that was not read")))
    judged("what the archive carries into the summary is cut to plain words",
           first_wrong((hostile_lines("\n".join(contracts_section({"contracts": contracts_report(template, ranking, document, dict(
               archive, skipped={"deepswe_external": "@bob <img src=x> ::error:: `x`"}))}))) is None, "markup from a reason reached the summary")))
    hostile_document = epoch_document()
    hostile_document["routers"]["code"]["intelligence_floor"]["anchor"] = code_anchor(
        "@bob <img src=x> ::error:: `x`", deepswe_external=["x3"], ale_bench_external=["x3"])
    hostile_section = "\n".join(contracts_section({"contracts": contracts_report(template, ranking, hostile_document, archive)}))
    judged("the name of an anchor on the code scale is cut to plain words in the summary, and the floor is still read",
           first_wrong((hostile_lines(hostile_section) is None, str(hostile_lines(hostile_section))),
                       ("@bob" not in hostile_section and "<img" not in hostile_section, "markup from a name reached the summary"),
                       ("Plancher 50 % (" in hostile_section, "the floor was not read")))
    no_fallback_section = "\n".join(contracts_section({"contracts": contracts_report(template, ranking, no_conversion, archive)}))
    judged("a file that declares no conversion says that a member with no measured position is not placed",
           first_wrong(("Le fichier ne déclare aucune conversion de l'indice en position : un membre sans position de code mesurée n'est pas placé." in no_fallback_section,
                        "the absence of a conversion is not said"),
                       ("Inclassables, faute de position de code (mesurée, ou estimée d'après un indice d'intelligence), donc non placés : `t`, `u`."
                        in no_fallback_section.split("### `claude-code`")[0], "the unplaced are not listed: %s" % no_fallback_section[-1500:]),
                       ("| `t` | — | — | — | — | — | — | inclassable : pas de position de code |" in no_fallback_section.split("### `claude-code`")[0],
                        "the place of an unplaced member")))

    # The run: the archive is read by the online run that has the contracts, after the ranking, and by no other.
    with tempfile.TemporaryDirectory() as directory:
        run_document = contract_document()
        run_document["models"]["alpha"]["epoch"] = {key: ["alpha_medium"] for key in ("deepswe_external", "swe_bench_verified", "cursorbench_external")}
        run_document["models"]["oscar"]["epoch"] = {key: ["oscar_high"] for key in ("deepswe_external", "swe_bench_verified", "cursorbench_external")}
        run_document["routers"]["code"]["intelligence_floor"]["anchor"] = code_anchor(
            "Floor Model", deepswe_external=["floor_model"], swe_bench_verified=["floor_model"])
        run, config, path, summary = contracts_runner(directory, run_document)
        run_archive = epoch_zip(epoch_members({
            "deepswe_external": {"oscar_high": 0.8, "other": 0.6, "alpha_medium": 0.4, "floor_model": 0.3},
            "swe_bench_verified": {"alpha_medium": 0.9, "other": 0.7, "oscar_high": 0.5, "floor_model": 0.1},
            "cursorbench_external": {"alpha_medium": 0.9, "other": 0.5, "floor_model": 0.2, "oscar_high": 0.1}}))
        online = ["--online", "--config", config, "--summary", summary, "--contracts", path]
        status, out, body, asked = run(online, run_archive)
        status_none, out_none, body_none, asked_none = run(online)
        section = body.split("## Contrats par routeur")[1].split("\n## ")[0]
        none_section = body_none.split("## Contrats par routeur")[1].split("\n## ")[0]
        judged("the online run that has the contracts reads the archive once, and the summary orders code on it",
               first_wrong((asked == [EPOCH_URL], "asked: %r" % asked),
                           ("Plancher 100 % (Floor Model (Epoch, position de code)), un niveau de plus" in section, "the floor of code: %s" % section[:300]),
                           ("Ordre des contrats : `alpha` > `oscar` > `sierra`." in section, "the order of code: %s" % section[:200]),
                           ("(source : Epoch AI selftest source, lue le " in section and "Epoch AI, benchmark data, CC BY 4.0" in section, "the source"),
                           ("| `alpha` | 75 % | 25 % | 25 % | — | — | 25 % | 1 |" in section and "| `oscar` | 25 % | 75 % | 100 % | — | — | 75 % | 2 |" in section
                            and "| `sierra` | — | — | — | — | — | 80 % (estimé) | 3 |" in section, "the positions of the three: %s" % section),
                           ("epoch " in out and "read, 3 of the 5 benchmark file(s)" in out and "Epoch AI, benchmark data, CC BY 4.0" in out, "the log: %s" % out)))
        judged("an archive nobody serves is a read that failed: the summary and the log say so, the order is the stand-in's, and nothing else of the run moves",
               first_wrong((asked_none == [EPOCH_URL], "asked: %r" % asked_none),
                           ("Ordre des contrats : `oscar` > `alpha` > `sierra`." in none_section, "the stand-in order: %s" % none_section[:200]),
                           ("non lue (HTTP 404)" in none_section and "Position de code, d'après" not in none_section, "the failure is not said"),
                           ("Plancher introuvable (Floor Model (Epoch, position de code) : archive d'Epoch AI non lue)" in none_section, "the floor is not said unread"),
                           ("ERROR, not read: HTTP 404" in out_none, "the log: %s" % out_none),
                           (status_none == status and "Aucune dérive." in body_none and "Aucune dérive." in body, "the status or the drift moved"),
                           (body.split("## Contrats par routeur")[0] == body_none.split("## Contrats par routeur")[0], "the rest of the summary moved")))
        status_bad, _, body_bad, _ = run(online, b"not an archive")
        status_boom, _, body_boom, _ = run(online, RuntimeError("selftest: SECRET"))
        judged("an answer that is no archive, or a reader that fails, is a read that failed and never the run's failure",
               first_wrong(("non lue (the answer is not a zip archive)" in body_bad, "not an archive: %s" % body_bad[-600:]),
                           ("non lue (failed: RuntimeError)" in body_boom and "SECRET" not in body_boom, "a failing opener"),
                           (status_bad == status and status_boom == status, "the status moved")))
        status_off, _, body_off, asked_off = run(online, run_archive, environment=SELFTEST_KEYS)
        status_other, _, body_other, asked_other = run(["--online", "--config", config, "--summary", summary], run_archive)
        judged("the archive is not read where there is no section to use it: without the ranking, or with another template and no contracts",
               first_wrong((asked_off == [] and asked_other == [], "asked: %r %r" % (asked_off, asked_other)),
                           ("## Contrats par routeur" not in body_off and "## Contrats par routeur" not in body_other, "a section without its inputs")))

        def refusing(url, headers, limit=None):
            raise AssertionError("the plain run reached the network: %s" % url)

        status_plain, out_plain, _, _ = run(["--config", config, "--contracts", path], opener=refusing)
        judged("the plain run stays offline with a floor on the code scale and no archive: it reads the contracts, never the archive, and passes",
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
    judged("with the archive not read, an anchor on the capabilities index has no value, nothing is judged against it and the summary says introuvable and why, as for an entry that cannot be read",
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
    judged("an archive read without its capabilities index gives no estimate and no floor on it, and says why in the summary",
           first_wrong((contract_rows(lost, "pro")[1]["contract"]["intelligence_floor"]["value"] is None, "a floor from nothing"),
                       (contract_rows(lost, "pro")[0]["echo"]["estimated"] is False and contract_rows(lost, "pro")[0]["echo"]["intelligence"] is None, "an estimate from nothing"),
                       ("n'est pas lu (absent from the archive)" in "\n".join(contracts_section({"contracts": lost})), "the missing member is not said"),
                       (lost["eci_stale"] == [], "a name was called stale before the index was read")))
    section = "\n".join(contracts_section({"contracts": report}))
    pro_block = section.split("### `pro`")[1].split("### `flash`")[0]
    judged("the summary says the capabilities index was read from the same archive, with the attribution and the day, shows each estimate as estimated and each floor with its anchor named, the candidates side by side",
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
                        and "- ancre d'un plancher : `Floor Model`\n" in thin_section, "the summary does not list them: %s" % thin_section[-1500:]),
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
                       (held_order["proposed"] == ["bravo", "kilo", "lima", "india", "sierra"], "with a floor: %r" % held_order["proposed"]),
                       (free["echo"]["kind"] == "conforming" and free["echo"]["verdict"] == "conforme ; quota partagé : en dernier"
                        and not free["echo"]["estimated"], "echo, with no index, in a router that needs none, and in pro: %r" % free["echo"]["verdict"]),
                       (free["sierra"]["kind"] == "conforming", "sierra, under the old floor: %r" % free["sierra"]["verdict"]),
                       (not any(row["kind"] == "below_floor" for row in free.values()), "a member went under a floor that does not exist"),
                       (free["quebec"]["kind"] == "unrankable" and free["quebec"]["verdict"] == "inclassable : pas de délai", "a member with no time was placed"),
                       (free_order["proposed"] == ["bravo", "kilo", "sierra", "lima", "india", "echo"],
                        "worth for the time first (6, 4.5, -70, -75), then india (5) and echo (no index), both pro's entries and so last: %r" % free_order["proposed"]),
                       (free_order["contract"]["intelligence_floor"]["value"] is None and free_order["contract"]["intelligence_floor"]["candidates"] == []
                        and free_order["floors"] == [], "the floor has a value or candidates: %r" % free_order["floors"])))
    judged("the summary says that a router has no floor, in its sentence and not as a floor that could not be found",
           first_wrong(("Aucun plancher, un niveau de plus tant qu'il rapporte au moins 1.5 points d'indice par seconde de plus, classé par l'indice d'intelligence moins 1.5 points par seconde de délai moyen avant le premier jeton de la réponse, le plus grand en tête ; un membre qui a un délai et pas d'indice vient après ceux qui ont les deux, le plus rapide d'abord ; un membre qui est le même modèle chez le même fournisseur qu'un membre de `pro`, donc sur le même quota, passe après tous les autres, dans le même ordre." in free_section,
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

    # claude-code follows code, estimates included: members with no code position are placed on the one their index gives.
    floor_archive = epoch_archive({"deepswe_external": {"alpha_medium": 0.5, "f1": 0.9, "f2": 0.8, "f3": 0.1},
                                   "swe_bench_verified": {"alpha_medium": 0.5, "g1": 0.9, "g2": 0.1, "g3": 0.05}}, EPOCH_ECI)
    estimates = contracts_report(template, ranking, document, floor_archive)
    code, code_order = contract_rows(estimates, "code")
    claude, claude_order = contract_rows(estimates, "claude-code")
    judged("claude-code is ordered as code is on the estimates too: the same floor, the same figures, the same order for the members they share",
           first_wrong((code_order["proposed"] == ["oscar", "alpha", "delta", "sierra"], "code: %r" % code_order["proposed"]),
                       (claude_order["proposed"] == ["echo", "alpha", "quebec", "delta"], "claude-code: %r" % claude_order["proposed"]),
                       (claude["echo"]["code_estimated"] and claude["echo"]["code_position"] == 20 and claude["echo"]["verdict"] == "conforme (estimé)",
                        "echo, whose index is itself estimated from the capabilities index: %r" % claude["echo"]["verdict"]),
                       (claude["delta"]["verdict"] == "sous le plancher (66 % estimé contre 62.5 %) : dernier recours"
                        and code["delta"]["verdict"] == claude["delta"]["verdict"], "delta: %r" % claude["delta"]["verdict"]),
                       (code["alpha"]["code_estimated"] and code["alpha"]["code_position"] == 30 and code["alpha"]["quality"]["why"] == "few_files",
                        "alpha, in one file, is estimated from its index: %r" % code["alpha"]["code_position"]),
                       (claude["november"]["kind"] == "no_tools", "a member with no tools was placed on an estimate"),
                       (code["november"]["kind"] == "stale" and "november" not in code_order["proposed"], "a member with neither a position nor an index was placed"),
                       (code_order["contract"]["intelligence_floor"]["value"] == claude_order["contract"]["intelligence_floor"]["value"] == 62.5, "the floor"),
                       ([name for name in claude_order["proposed"] if name in code_order["proposed"]]
                        == [name for name in code_order["proposed"] if name in claude_order["proposed"]], "the order of the shared members differs")))
    judged("an archive that holds no benchmark file has no floor on the code scale to give and measures nobody, and the members are all placed on estimates",
           first_wrong((contract_rows(contracts_report(template, ranking, document, archive), "code")[1]["contract"]["intelligence_floor"]["value"] is None,
                        "a floor from nothing"),
                       (all(row["code_estimated"] for name, row in contract_rows(contracts_report(template, ranking, document, archive), "code")[0].items()
                            if row["code_position"] is not None), "a position measured from nothing")))

    # The margin of a floor on the index: a member conforms while its figure is no more than the margin under the floor.
    def margined(margin):
        margin_document = eci_document()
        margin_document["routers"]["pro"]["intelligence_floor"]["margin"] = margin
        return contracts_report(template, ranking, margin_document, archive)

    bounded, bounded_order = contract_rows(margined(8), "pro")
    short, _ = contract_rows(margined(7.9), "pro")
    wide, _ = contract_rows(margined(12), "pro")
    judged("a member whose figure is exactly the margin under the floor conforms, one a hair under it is below, and the verdict says the margin beside the floor",
           first_wrong((bounded["delta"]["kind"] == "conforming" and bounded["delta"]["verdict"] == "conforme (estimé)", "delta, estimated at 12 for a floor of 20 and a margin of 8: %r" % bounded["delta"]["verdict"]),
                       (short["delta"]["kind"] == "below_floor" and short["delta"]["verdict"] == "sous le plancher (12.0 estimé contre 20, marge 7.9) : dernier recours",
                        "delta with a margin of 7.9: %r" % short["delta"]["verdict"]),
                       (bounded["india"]["kind"] == "below_floor" and bounded["india"]["verdict"] == "sous le plancher (8.0 contre 20, marge 8) : dernier recours",
                        "india, at 8: %r" % bounded["india"]["verdict"]),
                       (wide["india"]["kind"] == "conforming" and wide["india"]["verdict"] == "conforme", "india, exactly 12 under with a margin of 12: %r" % wide["india"]["verdict"]),
                       (pro["india"]["verdict"] == "sous le plancher (8.0 contre 20) : dernier recours", "a floor with no margin says one")))
    judged("a margin moves who is in front and who goes to the last resort tier, the floors side by side keep their anchors, each judged with the margin of the floor",
           first_wrong((pro_order["floors"][0]["main"] == ["echo", "alpha", "charlie"] and pro_order["floors"][0]["last"] == ["delta", "india", "juliet", "foxtrot"],
                        "with no margin: %r" % pro_order["floors"][0]),
                       (bounded_order["floors"][0]["main"] == ["echo", "alpha", "charlie", "delta"] and bounded_order["floors"][0]["last"] == ["india", "juliet", "foxtrot"],
                        "delta, 8 under the floor, is in front with a margin of 8: %r" % bounded_order["floors"][0]),
                       ([effect["main"] for effect in bounded_order["floors"]] == [["echo", "alpha", "charlie", "delta"], ["echo"], ["echo", "alpha", "charlie", "delta", "india"]],
                        "every floor is judged with the margin: %r" % bounded_order["floors"]),
                       ([effect["text"] for effect in bounded_order["floors"]] == ["Floor Model (Epoch, estimé)", "Alpha (High)", "Pee Model (Epoch, estimé)"],
                        "the anchors are not named"),
                       (bounded_order["proposed"] == ["echo", "alpha", "charlie", "delta", "india", "juliet", "foxtrot"], "pro with a margin of 8: %r" % bounded_order["proposed"])))
    margin_section = "\n".join(contracts_section({"contracts": margined(8)}))
    margin_block = margin_section.split("### `pro`")[1].split("### `flash`")[0]
    judged("the summary says the margin wherever it says the floor: beside the floor of the router, in the verdicts and above the floors side by side, and nothing of it for a floor that has none",
           first_wrong(("Plancher 20 (Floor Model (Epoch, estimé)), marge 8, un niveau de plus tant qu'il rapporte au moins 0.2 points d'indice par seconde de plus" in margin_block,
                        "the floor: %s" % margin_block[:400]),
                       ("sous le plancher (8.0 contre 20, marge 8) : dernier recours |" in margin_block, "the verdict"),
                       ("Effet de chaque plancher, avec la marge de 8 :" in margin_block and "Effet de chaque plancher :" not in margin_block, "the table of floors"),
                       ("marge" not in section.split("### `pro`")[1].split("### `flash`")[0], "a margin was said for a floor that has none"),
                       ("Un membre sous le plancher passe au dernier recours, et la marge d'un plancher, quand il en a une, est tolérée" in margin_section,
                        "the margin is not explained")))

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
    code_floor = ("routers", "code", "intelligence_floor")
    structural = (
        ("an anchor on the capabilities index", set_in(floor_path + ("anchor",), {"epoch": "Pee Model"}), None),
        ("a router with no floor", set_in(floor_path, {"none": True, "reason": "x"}), None),
        ("a router with no floor and an anchor", set_in(floor_path, {"none": True, "reason": "x", "anchor": {"epoch": "Pee Model"}}), 'says "none" and so names no "anchor" and no "candidates"'),
        ("a router with no floor and candidates", set_in(floor_path, {"none": True, "reason": "x", "candidates": []}), 'says "none" and so names no "anchor" and no "candidates"'),
        ("a router with no floor and no reason", set_in(floor_path, {"none": True}), '"intelligence_floor", has no "reason"'),
        ("a no-floor that is false", set_in(floor_path, {"none": False, "reason": "x"}), 'has a "none" that is not true'),
        ("a no-floor that is a word", set_in(floor_path, {"none": "yes", "reason": "x"}), 'has a "none" that is not true'),
        ("an anchor naming an entry and a model", set_in(floor_path + ("anchor",), {"entry": "alpha", "epoch": "Pee Model"}), 'names more than one of "entry", "epoch" and "code_epoch": exactly one'),
        ("an anchor with a blank model", set_in(floor_path + ("anchor",), {"epoch": " "}), 'has an "epoch" that is no model name'),
        ("an anchor with a model that is no text", set_in(floor_path + ("anchor",), {"epoch": 5}), 'has an "epoch" that is no model name'),
        ("an anchor on a model with a level", set_in(floor_path + ("anchor",), {"epoch": "Pee Model", "level": "low"}), 'names an "epoch" model, which has no "level"'),
        ("an anchor naming nothing", set_in(floor_path + ("anchor",), {"level": "low"}), 'must be a mapping that names an "entry", an "epoch" model or a "code_epoch"'),
        ("a candidate naming a model that is no text", set_in(floor_path + ("candidates",), [{"epoch": ["x"]}]), 'candidate 1 has an "epoch" that is no model name'),
        ("a mapping with an eci that is blank", set_in(("models", "echo", "eci"), " "), 'has an "eci" that is no model name of the capabilities index'),
        ("a mapping with an eci that is no text", set_in(("models", "echo", "eci"), 150), 'has an "eci" that is no model name of the capabilities index'),
        ("the capabilities index used with no calibration", drop("fallback_index"), 'declares no "fallback_index" calibration'),
        ("a calibration of one point", set_in(("fallback_index", "points"), [[140, 4]]), 'must list its calibration "points" as pairs of numbers, two at least'),
        ("a margin on an index floor", set_in(floor_path + ("margin",), 2), None),
        ("a margin of zero", set_in(floor_path + ("margin",), 0), None),
        ("a margin that is a fraction", set_in(floor_path + ("margin",), 0.5), None),
        ("a margin that is a word", set_in(floor_path + ("margin",), "2"), 'has a "margin" that is not a number from 0 up'),
        ("a margin that is a boolean", set_in(floor_path + ("margin",), True), 'has a "margin" that is not a number from 0 up'),
        ("a margin below zero", set_in(floor_path + ("margin",), -1), 'has a "margin" that is not a number from 0 up'),
        ("a margin that is nothing", set_in(floor_path + ("margin",), None), 'has a "margin" that is not a number from 0 up'),
        ("a margin on a router with no floor", set_in(floor_path, {"none": True, "reason": "x", "margin": 1}), 'says "none" and so has no "margin"'),
        ("a floor on the code scale", set_in(code_floor + ("anchor",), code_anchor("A", deepswe_external=["a"], swe_bench_verified=["a"])), None),
        ("a floor on the code scale with five files", set_in(code_floor + ("anchor",), code_anchor("A", **{key: ["a"] for key in EPOCH_KEYS})), None),
        ("a code floor with a margin", set_in(code_floor + ("margin",), 5), None),
        ("code candidates that are anchors on the code scale", set_in(code_floor + ("candidates",), [code_anchor("A", deepswe_external=["a"], swe_bench_verified=["b", "c"])]), None),
        ("a code anchor with no name", set_in(code_floor + ("anchor",), {"code_epoch": {"deepswe_external": ["a"], "swe_bench_verified": ["a"]}}),
         'names a "code_epoch" with no "name" to show'),
        ("a code anchor with a name of blanks", set_in(code_floor + ("anchor",), code_anchor(" ", deepswe_external=["a"], swe_bench_verified=["a"])),
         'names a "code_epoch" with no "name" to show'),
        ("a code anchor with a name that is no text", set_in(code_floor + ("anchor",), code_anchor(5, deepswe_external=["a"], swe_bench_verified=["a"])),
         'names a "code_epoch" with no "name" to show'),
        ("a code anchor on one file", set_in(code_floor + ("anchor",), code_anchor("A", deepswe_external=["a"])),
         'has a "code_epoch" that is not 2 benchmark files at least and their model versions'),
        ("a code anchor on no file", set_in(code_floor + ("anchor",), code_anchor("A")),
         'has a "code_epoch" that is not 2 benchmark files at least and their model versions'),
        ("a code anchor that is a list", set_in(code_floor + ("anchor",), {"name": "A", "code_epoch": ["a", "b"]}),
         'has a "code_epoch" that is not 2 benchmark files at least and their model versions'),
        ("a code anchor with versions that are no list", set_in(code_floor + ("anchor",), code_anchor("A", deepswe_external="a", swe_bench_verified=["a"])),
         'has a "code_epoch" that is not 2 benchmark files at least and their model versions'),
        ("a code anchor with an empty list of versions", set_in(code_floor + ("anchor",), code_anchor("A", deepswe_external=[], swe_bench_verified=["a"])),
         'has a "code_epoch" that is not 2 benchmark files at least and their model versions'),
        ("a code anchor with a version of blanks", set_in(code_floor + ("anchor",), code_anchor("A", deepswe_external=[" "], swe_bench_verified=["a"])),
         'has a "code_epoch" that is not 2 benchmark files at least and their model versions'),
        ("a code anchor with a version that is no text", set_in(code_floor + ("anchor",), code_anchor("A", deepswe_external=["a", 3], swe_bench_verified=["a"])),
         'has a "code_epoch" that is not 2 benchmark files at least and their model versions'),
        ("a code anchor on an arena of web interfaces", set_in(code_floor + ("anchor",), code_anchor("A", deepswe_external=["a"], webdev_arena_external=["a"])),
         'has a "code_epoch" on a benchmark file that is not read: only deepswe_external, swe_bench_verified'),
        ("a code anchor with a level", set_in(code_floor + ("anchor",), dict(code_anchor("A", deepswe_external=["a"], swe_bench_verified=["a"]), level="low")),
         'names a "code_epoch", which has no "level"'),
        ("a code anchor that names an entry too", set_in(code_floor + ("anchor",), dict(code_anchor("A", deepswe_external=["a"], swe_bench_verified=["a"]), entry="alpha")),
         'names more than one of "entry", "epoch" and "code_epoch": exactly one'),
        ("a code anchor that names a model of the index too", set_in(code_floor + ("anchor",), dict(code_anchor("A", deepswe_external=["a"], swe_bench_verified=["a"]), epoch="Pee Model")),
         'names more than one of "entry", "epoch" and "code_epoch": exactly one'),
        ("a bad code anchor among the candidates", set_in(code_floor + ("candidates",), [code_anchor("A", deepswe_external=["a"])]),
         'candidate 1 has a "code_epoch" that is not 2 benchmark files at least'),
        ("a router ranked on code with an anchor on the index", set_in(code_floor + ("anchor",), {"entry": "alpha"}),
         'must be on one scale, the code scale ("code_epoch" anchors) for a router ranked on "code_quality"'),
        ("a router ranked on code with a candidate on the index", set_in(code_floor + ("candidates",), [{"entry": "alpha"}]),
         'must be on one scale'),
        ("a router ranked on code with a floor on the capabilities index", set_in(code_floor + ("anchor",), {"epoch": "Pee Model"}),
         'must be on one scale'),
        ("a router that is not ranked on code with an anchor on the code scale", set_in(floor_path + ("anchor",), code_anchor("A", deepswe_external=["a"], swe_bench_verified=["a"])),
         'must be on one scale, the code scale ("code_epoch" anchors) for a router ranked on "code_quality" and the intelligence index for any other'),
        ("a router that is not ranked on code with a candidate on the code scale", set_in(floor_path + ("candidates",), [code_anchor("A", deepswe_external=["a"], swe_bench_verified=["a"])]),
         'must be on one scale'),
        ("a floor of the code scale that mixes with another", set_in(code_floor + ("candidates",), [code_anchor("A", deepswe_external=["a"], swe_bench_verified=["a"]), {"epoch": "Pee Model"}]),
         'must be on one scale'),
        ("a conversion of the code position", set_in(("code_fallback", "points"), [[0, 90], [10, 90], [30, 20]]), None),
        ("a conversion declared by no file", drop("code_fallback"), None),
        ("a conversion that is no mapping", set_in(("code_fallback",), "estimate"), '"code_fallback" is not a mapping'),
        ("a conversion with no source", drop("code_fallback", "source"), '"code_fallback" has no "source", in words'),
        ("a conversion with no status", set_in(("code_fallback", "status"), " "), '"code_fallback" has no "status", in words'),
        ("a conversion with no method", drop("code_fallback", "method"), '"code_fallback" has no "method", in words'),
        ("a conversion with no uncertainty", drop("code_fallback", "uncertainty"), '"code_fallback" has no "uncertainty", in words'),
        ("a conversion with no points", drop("code_fallback", "points"), '"code_fallback" must list its calibration "points" as pairs of numbers, two at least'),
        ("a conversion with one point", set_in(("code_fallback", "points"), [[0, 90]]), '"code_fallback" must list its calibration "points" as pairs of numbers, two at least'),
        ("a conversion with points that are no list", set_in(("code_fallback", "points"), "0 90 10 50"), '"code_fallback" must list its calibration "points" as pairs of numbers'),
        ("a conversion with a point that is no pair", set_in(("code_fallback", "points"), [[0, 90], [10]]), '"code_fallback" must list its calibration "points" as pairs of numbers'),
        ("a conversion with a point that has three numbers", set_in(("code_fallback", "points"), [[0, 90], [10, 50, 1]]), '"code_fallback" must list its calibration "points" as pairs of numbers'),
        ("a conversion with a position that is a word", set_in(("code_fallback", "points"), [[0, 90], [10, "50"]]), '"code_fallback" must list its calibration "points" as pairs of numbers'),
        ("a conversion with an index that is a boolean", set_in(("code_fallback", "points"), [[0, 90], [True, 50]]), '"code_fallback" must list its calibration "points" as pairs of numbers'),
        ("a conversion whose position goes up", set_in(("code_fallback", "points"), [[0, 50], [10, 60]]),
         '"code_fallback" has calibration "points" whose index does not go up, or whose position goes up with it'),
        ("a conversion whose position goes up after a fall", set_in(("code_fallback", "points"), [[0, 90], [10, 50], [20, 60]]),
         '"code_fallback" has calibration "points" whose index does not go up, or whose position goes up with it'),
        ("a conversion whose index stays the same", set_in(("code_fallback", "points"), [[0, 90], [0, 50]]),
         '"code_fallback" has calibration "points" whose index does not go up'),
        ("a conversion whose index goes down", set_in(("code_fallback", "points"), [[10, 90], [5, 50]]),
         '"code_fallback" has calibration "points" whose index does not go up'),
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
        run, config, path, summary = contracts_runner(directory, run_document)
        online = ["--online", "--config", config, "--summary", summary, "--contracts", path]
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


# ------------------------------------------------------------------------------------------------
# Cloudflare Workers AI: the one catalogue whose address carries a secret of its own
# ------------------------------------------------------------------------------------------------

CLOUDFLARE_ACCOUNT = SELFTEST_KEYS["MODEL_DRIFT_CLOUDFLARE_ACCOUNT_ID"]
CLOUDFLARE_ENVIRONMENT = SELFTEST_KEYS
# SELFTEST_TEMPLATE with a Cloudflare entry in the "flash" cascade and a commented-out one under its reason.
CLOUDFLARE_BLOCK = """\
  - model_name: cf-large
    litellm_params:
      model: cloudflare/@cf/vendor/large
      api_key: "os.environ/CLOUDFLARE_API_KEY"

  # Served, but not routed to: needs a paid plan.
  # - model_name: cf-paid
  #   litellm_params:
  #     model: cloudflare/@cf/vendor/paid
  #     api_key: "os.environ/CLOUDFLARE_API_KEY"

"""
assert SELFTEST_TEMPLATE.count("  - model_name: local\n") == 1 and SELFTEST_TEMPLATE.count("        - large\n") == 1
CLOUDFLARE_TEMPLATE = SELFTEST_TEMPLATE.replace(
    "  - model_name: local\n", CLOUDFLARE_BLOCK + "  - model_name: local\n", 1).replace(
    "        - large\n", "        - cf-large\n        - large\n", 1)


def cloudflare_model(name, task="Text Generation", planned=None, deprecated=None):
    """One model as the documentation's own catalogue holds it: the "@cf/..." id is the "name"."""
    properties = [{"property_id": "context_window", "value": "128000"}]
    if planned is not None:
        properties.append({"property_id": "planned_deprecation_date", "value": planned})
    model = {"id": "00000000-0000-4000-8000-000000000000", "source": 1, "name": name,
             "description": "A model.", "task": {"id": "t", "name": task, "description": "A task."},
             "tags": [], "properties": properties}
    if deprecated is not None:
        model["deprecated"] = deprecated
    return model


def cloudflare_page(*models):
    return {"result": list(models), "success": True, "errors": [], "messages": []}


def cloudflare_catalogue(*extra, without=()):
    """The models the template routes to or sets aside, and the ones that are no chat model."""
    models = [cloudflare_model("@cf/vendor/large"), cloudflare_model("@cf/vendor/paid"),
              cloudflare_model("@cf/vendor/embed-9", task="Text Embeddings"),
              cloudflare_model("@cf/vendor/hear-9", task="Automatic Speech Recognition"),
              cloudflare_model("@cf/vendor/guard-9")]
    return [cloudflare_page(*[model for model in models if model["name"] not in without], *extra)]


def cloudflare_answers(pages):
    answers = selftest_answers()
    answers["cloudflare"] = pages
    return answers


def run_cloudflare_cases():
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

    def run(pages, environment=CLOUDFLARE_ENVIRONMENT):
        calls = []
        result = run_online(CLOUDFLARE_TEMPLATE, environment,
                            canned_opener(cloudflare_answers(pages), calls), "2026-01-01")
        return (result, [(url, headers) for url, headers in calls if "/ai/models/search?" in url],
                render_text(result, "selftest"), render_summary(result, "selftest", link=None))

    def found(result):
        return sorted((finding["kind"], finding["id"]) for report in result["providers"]
                      for finding in report["findings"])

    def cloudflare_report(result):
        return next(report for report in result["providers"] if report["name"] == "cloudflare")

    def hides_account(*texts):
        return first_wrong(
            (not any(CLOUDFLARE_ACCOUNT in text for text in texts), "the account identifier reached the output"),
            (not any("SECRET" in text for text in texts), "a key reached the output"))

    def no_mention(*texts):
        # An "@cf/" id is safe in a code span and nowhere else: a mention is made of it outside one.
        for text in texts:
            outside = re.sub(r"`[^`\n]*`", "", re.sub(r"```.*?```", "", text, flags=re.S))
            if "@cf" in outside:
                return "an @cf/ id reached the output outside a code span: %r" % outside[outside.index("@cf") - 20:][:60]
        return None

    result, asked, report, body = run(cloudflare_catalogue())
    url, headers = asked[0] if asked else ("", {})
    judged("Cloudflare is read: the route, the deprecated models asked for, the token in a header and the "
           "account in the path only, and nothing of either in the report",
           first_wrong(
               (len(asked) == 1, "%d catalogue requests" % len(asked)),
               (url == "https://api.cloudflare.com/client/v4/accounts/%s/ai/models/search"
                       "?include_deprecated=true&per_page=50&page=1" % CLOUDFLARE_ACCOUNT, "the address is %s" % url),
               (headers.get("Authorization") == "Bearer selftest-cloudflare-key-SECRET", "the token is not a bearer"),
               (not any("SECRET" in value for key, value in headers.items() if key != "Authorization"),
                "the token is in another header"),
               (found(result) == [] and exit_status(result) == 0, "findings %r" % found(result)),
               ("cloudflare  read, 5 model(s), 2 chat candidate(s); 1 active, 1 commented-out id(s) here" in report,
                "the report: %s" % report),
               (result["unattributed"] == ["openai/auto/best-free"], "an entry of Cloudflare is of no catalogue"),
               (hides_account(report, body) is None, hides_account(report, body))))
    result, _, report, body = run(cloudflare_catalogue(
        cloudflare_model("@cf/vendor/new-text"), cloudflare_model("@cf/vendor/new-embed", task="Text Embeddings"),
        cloudflare_model("@cf/vendor/old-text", deprecated=True),
        cloudflare_model("@cf/vendor/ending-text", planned="2026-12-01")))
    examine = body.split("## Nouveaux modèles à examiner")[1].split("\n## ")[0] if "## Nouveaux modèles à examiner" in body else ""
    judged("a Text Generation model the file does not know is NEW, to examine against Cloudflare's pricing page, "
           "and never claimed free; one of another task or that is deprecated or ending is not offered",
           first_wrong(
               (found(result) == [("new", "@cf/vendor/new-text")], "findings %r" % found(result)),
               ("`cloudflare/@cf/vendor/new-text`" in examine, "the model is not listed to examine"),
               ("[cloudflare](https://developers.cloudflare.com/workers-ai/platform/pricing/)" in examine,
                "the pricing page is not linked"),
               ("Leur gratuité ne se lit pas dans l'API du fournisseur" in examine, "it is not said that free is unread"),
               ("cloudflare/@cf/vendor/new-text: to examine, its free tier is not machine-readable" in report,
                "the model is not said to be one to examine: %s" % report),
               (no_mention(body) is None, no_mention(body))))
    judged("a deprecated flag or a planned deprecation date on an active entry is a NOTICE with its date",
           first_wrong(
               (found(run([cloudflare_page(cloudflare_model("@cf/vendor/large", planned="2026-12-01"),
                                           cloudflare_model("@cf/vendor/paid"))])[0])
                == [("notice", "@cf/vendor/large")], "a planned date is not a notice"),
               (found(run([cloudflare_page(cloudflare_model("@cf/vendor/large", deprecated=True),
                                           cloudflare_model("@cf/vendor/paid"))])[0])
                == [("notice", "@cf/vendor/large")], "a deprecated flag is not a notice")))
    result, _, report, body = run([cloudflare_page(
        cloudflare_model("@cf/vendor/large", planned="2026-12-01"), cloudflare_model("@cf/vendor/paid"))])
    judged("the notice says the date, in the report and in French in the summary",
           first_wrong(("cloudflare/@cf/vendor/large (cf-large): deprecated on 2026-12-01" in report, report),
                       ("`cloudflare/@cf/vendor/large` (`cf-large`) : déprécié (`2026-12-01`)" in body, body)))
    result, _, report, body = run(cloudflare_catalogue(without=("@cf/vendor/large", "@cf/vendor/paid")))
    judged("an active id the catalogue no longer lists is RETIRED, and a commented-out one is GONE",
           first_wrong((found(result) == [("gone", "@cf/vendor/paid"), ("retired", "@cf/vendor/large")],
                        "findings %r" % found(result)),
                       (exit_status(result) == 1, "the status")))

    # A list of 50 on its first page goes on: the second is asked for, with the same parameters.
    fillers = [cloudflare_model("@cf/vendor/filler-%d" % number, task="Text Embeddings") for number in range(46)]
    first = cloudflare_page(cloudflare_model("@cf/vendor/large"), cloudflare_model("@cf/vendor/paid"),
                            cloudflare_model("@cf/vendor/hear-9", task="Automatic Speech Recognition"),
                            cloudflare_model("@cf/vendor/embed-9", task="Text Embeddings"),
                            cloudflare_model("@cf/vendor/guard-9"), *fillers[:45])
    assert len(first["result"]) == 50
    result, asked, report, body = run([first, cloudflare_page(cloudflare_model("@cf/vendor/second-page"))])
    judged("a full page is followed by the next, and a model found on it is NEW",
           first_wrong(
               ([url.rsplit("&", 1)[1] for url, _ in asked] == ["page=1", "page=2"], "asked %r" % [url for url, _ in asked]),
               (all("include_deprecated=true&per_page=50" in url for url, _ in asked), "the parameters did not follow"),
               (found(result) == [("new", "@cf/vendor/second-page")], "findings %r" % found(result)),
               (hides_account(report, body) is None, hides_account(report, body))))
    result, asked, _, _ = run(cloudflare_catalogue())
    judged("a short page is the last", first_wrong((len(asked) == 1, "%d requests" % len(asked))))
    result, _, report, body = run(first)
    judged("a server that ignores the page asked for, and serves the same one again, is that provider's error",
           first_wrong((cloudflare_report(result)["status"] == "error" and exit_status(result) == 2, "status"),
                       ("pages of the answer repeat a model" in report, report)))
    endless = [cloudflare_page(*[cloudflare_model("@cf/vendor/p%d-%d" % (page, number), task="Text Embeddings")
                                 for number in range(CLOUDFLARE_PER_PAGE)]) for page in range(MAX_PAGES)]
    result, asked, report, body = run(endless)
    judged("a list still going after the last page this check reads is an error, never a catalogue read in part",
           first_wrong((len(asked) == MAX_PAGES, "%d requests" % len(asked)),
                       (cloudflare_report(result)["status"] == "error" and exit_status(result) == 2, "status"),
                       ("goes on past the last page" in report, report), (found(result) == [], "a finding")))
    judged("an answer with no list, or one that says it failed, is an error",
           first_wrong(*[(cloudflare_report(run(page)[0])["status"] == "error",
                          "%r was read" % (page,)) for page in ({"result": None, "success": True},
                                                                {"result": [], "success": False}, {"models": []})]))
    judged("a model with no name, or of a shape nobody documented, is skipped and no crash",
           first_wrong((found(run([cloudflare_page(*cloudflare_catalogue()[0]["result"], {"id": "x"}, 5,
                                                   {"name": "@cf/vendor/odd", "task": 5, "properties": 5})])[0])
                        == [], "an odd model was a finding"),))

    # Without both values the provider is not covered, and is never called.
    for variables, said, french in (
            (("MODEL_DRIFT_CLOUDFLARE_API_KEY",), "MODEL_DRIFT_CLOUDFLARE_ACCOUNT_ID is unset",
             "secret `MODEL_DRIFT_CLOUDFLARE_ACCOUNT_ID`"),
            (("MODEL_DRIFT_CLOUDFLARE_ACCOUNT_ID",), "MODEL_DRIFT_CLOUDFLARE_API_KEY is unset",
             "secret `MODEL_DRIFT_CLOUDFLARE_API_KEY`"),
            ((), "MODEL_DRIFT_CLOUDFLARE_API_KEY and MODEL_DRIFT_CLOUDFLARE_ACCOUNT_ID are unset",
             "secrets `MODEL_DRIFT_CLOUDFLARE_API_KEY` et `MODEL_DRIFT_CLOUDFLARE_ACCOUNT_ID`")):
        environment = {name: value for name, value in SELFTEST_KEYS.items()
                       if not name.startswith("MODEL_DRIFT_CLOUDFLARE_") or name in variables}
        result, asked, report, body = run(cloudflare_catalogue(), environment)
        judged("Cloudflare is not covered, never called, and the report names what is unset: %s" % (
            " and ".join(variables) or "neither"),
               first_wrong((asked == [], "the catalogue was called with one of the two values missing"),
                           ("not covered (no key): " + said in report, report),
                           ("non couvert (pas de clé : %s)" % french in body, body),
                           (exit_status(result) == 0 and not is_complete(result), "the status or the coverage")))
    for account in ("not-an-identifier", CLOUDFLARE_ACCOUNT[:-1], CLOUDFLARE_ACCOUNT + "0", "../" + CLOUDFLARE_ACCOUNT[3:],
                    CLOUDFLARE_ACCOUNT[:31] + "g", CLOUDFLARE_ACCOUNT[:16] + "/" + CLOUDFLARE_ACCOUNT[:15]):
        result, asked, report, body = run(cloudflare_catalogue(), dict(
            CLOUDFLARE_ENVIRONMENT, MODEL_DRIFT_CLOUDFLARE_ACCOUNT_ID=account))
        judged("an account identifier that is not 32 hexadecimal characters is an error, named, never shown or "
               "put in an address: %r" % account[:20],
               first_wrong((asked == [], "it was put in an address"),
                           (cloudflare_report(result)["status"] == "error" and exit_status(result) == 2, "status"),
                           ("MODEL_DRIFT_CLOUDFLARE_ACCOUNT_ID is not an account identifier" in report, report),
                           (account not in report + body, "its value was shown")))

    # The identifier is in the path of the address, so a message that carries the address carries it too.
    carried = "https://api.cloudflare.com/client/v4/accounts/%s/ai refused selftest-cloudflare-key-SECRET"
    result, _, report, body = run(urllib.error.URLError(carried % CLOUDFLARE_ACCOUNT))
    judged("an error that carries the address, with the account identifier and the token in it, is shown with "
           "neither: both are replaced",
           first_wrong((cloudflare_report(result)["status"] == "error" and exit_status(result) == 2, "status"),
                       (hides_account(report, body) is None, hides_account(report, body)),
                       ("accounts/***/ai refused ***" in report, report)))
    result, _, report, body = run(urllib.error.HTTPError(
        "https://api.cloudflare.com/client/v4/accounts/%s/ai/models/search" % CLOUDFLARE_ACCOUNT, 403,
        "Forbidden for " + CLOUDFLARE_ACCOUNT, None, io.BytesIO(b'{"errors": ["' + CLOUDFLARE_ACCOUNT.encode() + b'"]}')))
    judged("a 403 is its status and nothing else: neither its reason phrase nor its body, which can carry the account",
           first_wrong((hides_account(report, body) is None, hides_account(report, body)),
                       ("HTTP 403" in report and cloudflare_report(result)["error_class"] == "4xx", report)))
    result, _, report, body = run(cloudflare_catalogue(), dict(CLOUDFLARE_ENVIRONMENT, MODEL_DRIFT_CLOUDFLARE_ACCOUNT_ID="  "
                                                              + CLOUDFLARE_ACCOUNT + "\n"))
    judged("an identifier with whitespace round it, as a secret is often pasted, is read as it is without it",
           first_wrong((cloudflare_report(result)["status"] == "read", cloudflare_report(result)["status"])))
    judged("the address that the report and the summary can cite keeps the placeholder, never an account",
           first_wrong(("{account_id}" in catalogue_url("cloudflare"), catalogue_url("cloudflare")),
                       (hides_account(catalogue_url("cloudflare")) is None, "an account in PROVIDERS")))

    # A deletion and its cascade slot, and the refusal of one made on a list that holds nothing.
    outputs = apply_run(CLOUDFLARE_TEMPLATE, cloudflare_answers(cloudflare_catalogue(without=("@cf/vendor/large",))),
                        CLOUDFLARE_ENVIRONMENT)
    new_text = outputs[1]
    judged("a Cloudflare entry its catalogue no longer lists is deleted with its cascade slot, and the pull request "
           "names it and the account nowhere",
           first_wrong(("cloudflare/@cf/vendor/large" not in new_text and "cf-large" not in new_text, "it is still there"),
                       ("cf-paid" in new_text and "- large\n" in new_text, "something else was taken"),
                       (outputs[4] is not None and "`cloudflare/@cf/vendor/large`" in outputs[4], "the pull request"),
                       (hides_account(*[text for text in outputs[2:] if text]) is None, "the account reached a text")))
    outputs = apply_run(CLOUDFLARE_TEMPLATE, cloudflare_answers([cloudflare_page()]), CLOUDFLARE_ENVIRONMENT)
    judged("a catalogue that lists no model at all deletes nothing: an empty answer is a failed read",
           first_wrong((outputs[1] == CLOUDFLARE_TEMPLATE and outputs[4] is None, "something was deleted"),
                       (undeleted_count(outputs[0]) == 2, "the findings are not left to a person")))

    # An addition: the entry is modelled on the file's own, "@cf/" and all, and is never ready.
    result, proposals = proposal_run(CLOUDFLARE_TEMPLATE, cloudflare_answers(cloudflare_catalogue(
        cloudflare_model("@cf/vendor/new-text"))), CLOUDFLARE_ENVIRONMENT)
    part = proposals["to_verify"]
    judged("a NEW Cloudflare model is proposed in the pull request of the models to verify only, under the "
           "file's own naming, key and no base, and the file it builds reads back",
           first_wrong(
               (proposals["ready"]["items"] == [], "a Cloudflare model was ready"),
               (part["items"] == [{"provider": "cloudflare", "id": "@cf/vendor/new-text", "name": "new-text-cloudflare"}],
                "items %r" % part["items"]),
               ('  - model_name: new-text-cloudflare\n    model_info:\n      access_groups: ["LLM"]\n'
                '    litellm_params:\n      model: cloudflare/@cf/vendor/new-text\n'
                '      api_key: "os.environ/CLOUDFLARE_API_KEY"\n' in part["text"], "the entry"),
               ("api_base" not in part["text"].split("new-text-cloudflare")[1].split("\n\n")[0], "an api_base was invented"),
               (addition_problem(CLOUDFLARE_TEMPLATE, part["text"], part["items"]) is None, "it does not read back"),
               ("[ ] **Gratuité.** Ouvrir <https://developers.cloudflare.com/workers-ai/platform/pricing/>" in part["body"],
                "the pricing page is not what the draft sends to"),
               ("docker exec" in part["body"] and "CLOUDFLARE_ACCOUNT_ID" in part["body"]
                and "os.environ" in part["body"] and CLOUDFLARE_ACCOUNT not in part["body"],
                "the command to read the model does not take the account from the container"),
               (no_mention(part["body"]) is None, no_mention(part["body"]))))
    judged("an id with an @ anywhere but in front of \"cf/\" is no id: it is not offered, and is not proposed",
           first_wrong(*[(not ADDITION_ID.fullmatch(identifier) and not SAFE_MODEL_ID.fullmatch(identifier), identifier)
                         for identifier in ("@evil/x", "x@cf/y", "@cf/@cf/x", "@cf/", "@cf/x@y", "@@cf/x", "@cf//x",
                                            "@cf/x::y", " @cf/x", "@cf/x ")]
                       + [(ADDITION_ID.fullmatch("@cf/meta/x-9") and SAFE_MODEL_ID.fullmatch("@cf/meta/x-9"), "good")]))
    judged("an entry's \"cloudflare/@cf/...\" is attributed to Cloudflare, and a catalogue id is the \"@cf/...\" part",
           first_wrong((attribute("cloudflare/@cf/openai/gpt-oss-120b", None) == ("cloudflare", "@cf/openai/gpt-oss-120b"),
                        "attribute"),
                       ("cloudflare" in PROVIDER_NAMES and NAME_SUFFIXES["cloudflare"] == "-cloudflare", "the suffix"),
                       (propose_name("cloudflare", "@cf/openai/gpt-oss-120b", set()) == "gpt-oss-120b-cloudflare", "the name")))
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
        body = render_summary(result, "selftest", link=None)
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

    failures += run_cloudflare_cases()
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
    failures += run_carried_cases()
    failures += run_proposal_command_line_cases()
    failures += run_bounded_key_set_cases()
    failures += run_real_list_cases()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run_selftest())
