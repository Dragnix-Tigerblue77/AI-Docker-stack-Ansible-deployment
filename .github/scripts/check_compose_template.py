#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77
# SPDX-License-Identifier: AGPL-3.0-only
"""Render the Artificial Intelligence compose template, parse it, and hold it to the conventions #31 sets.

Why this exists
---------------
The README already says that reading a diff is not verification: a template change is verified when
the template has been RENDERED and the result PARSED. That sentence asked the reader for a
twenty-five line throwaway script every single time, which is the sort of step that gets skipped on
the change that needed it. This is that script, written once.

It renders the template in BOTH of its states -- published network set and unset -- because the
"off" state is the one nobody looks at, and a Jinja conditional that only works when the feature is
on is a defect that ships. It then holds the parsed result to the conventions the compose template's
own commented model documents. A comment is a reminder; a check is what makes a convention survive
the tenth service.

Every check below is vacuous today, because "services:" is an empty mapping. That is deliberate:
they are wired now so they bite on the first service block rather than being written after the
convention has already been broken.

It renders the template ONE MORE time with a "$" in the caller values (#155), because Compose and
"docker stack deploy" read the rendered file through their own "$VAR" / "${VAR}" interpolation after
Ansible: a "$" the template writes single reaches the container as whatever that names in THEIR
environment -- usually nothing, with a warning nobody reads. All nineteen secrets this role
interpolated were cut short that way, and no render here could see it: every other state renders
them empty, so there was no "$" for anything to trip on.

Which values get a "$" is derived rather than listed wherever it can be -- see "dollar_variables":
every variable the template reads that "defaults/main.yml" does not define (a mandatory one, a
secret or a host path) or defines as empty (an optional one, as the retired GitHub Models key is), so
a new service's secret is covered the day it is added, without anyone remembering this file. That is
NOT every caller value. A free-form value with a real default -- a login, a path, a model alias -- is
covered only once "FREE_FORM_WITH_A_DEFAULT" names it, and so is an optional one defaulting to
"false": nothing in a default says whether its grammar admits a "$", so that list is kept by hand,
and it is the one place where a value added without a thought for this file renders with no "$" and
passes unexamined.

What it deliberately does NOT flag
----------------------------------
* A published "ports:" mapping. Whether a service is web-facing is a deployment decision, not a
  property of the template, and a role that legitimately publishes one would have to fight this
  script rather than the reviewer. The convention lives in the template's model and in review.
* Host port numbers against Chromium's restricted list. That check needs to see every branch of the
  repository to be worth anything, and this one walks a single tree.
* Anything about the deployment role. It is named by the caller and this script never loads it.

Dependencies: jinja2 and PyYAML, both of which arrive with ansible-core, which CI installs anyway.
"""

import copy
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, meta

ROLE = Path(__file__).resolve().parents[2]

# The published network as a caller supplies it. The indentation is not cosmetic: the definition is
# a block string interpolated into the "networks:" mapping, so it carries its own continuation
# indent, exactly as a caller writes it in its playbook.
PUBLISHED_NETWORK = {
    "Artificial_Intelligence_published_Docker_network_name": "DMZ",
    "Artificial_Intelligence_published_Docker_network_definition": "DMZ:\n      external: true\n      name: DMZ\n",
}

# The checksums "tasks/main.yml" hands the deployment role for each configuration a container mounts
# (#161), which the template turns into the NAME of the Docker config that carries the file. Their
# default is "false", so the branch that writes them is one no default render ever evaluates -- the
# same blind spot as the Claude Code agent's toggle below. Fake but well-formed SHA-1s, distinct, so a
# name landing on the wrong service is told apart from one landing on the right one.
MOUNTED_CONFIG_CHECKSUMS = {
    "Artificial_Intelligence_LiteLLM_config_checksum": "0123456789abcdef0123456789abcdef01234567",
    "Artificial_Intelligence_LibreChat_config_checksum": "fedcba9876543210fedcba9876543210fedcba98",
}
# Per checksum: the service that reads the file, the name its Docker config has before any suffix, and
# where the container sees it. The suffix is "-" and the first 8 characters of the checksum.
MOUNTED_CONFIGS = {
    "Artificial_Intelligence_LiteLLM_config_checksum": ("litellm", "LiteLLM_config", "/app/config.yaml"),
    "Artificial_Intelligence_LibreChat_config_checksum": ("librechat", "LibreChat_config", "/app/librechat.yaml"),
}

# #13's service is off by default, which is exactly the branch "check_conventions" never exercises
# unless something asks for it: a Jinja "{% if %}" that is false at render time is not evaluated, so
# a defect inside it -- an undeclared volume, a missing memory limit -- would render and parse cleanly
# forever. Fake but well-formed values, just enough to turn the toggle on and let the branch run.
CLAUDE_CODE_TIGERBLUE77_ENABLED = {
    "Artificial_Intelligence_Claude_code_tigerblue77_enabled": True,
    "Artificial_Intelligence_Claude_code_tigerblue77_virtual_key": "sk-selftest",
    "Artificial_Intelligence_Claude_code_tigerblue77_GitHub_token": "ghp_selftest",
    "Artificial_Intelligence_Claude_code_tigerblue77_workspace_directory": "/srv/selftest/workspace",
}

# The values that HAVE a real default and whose grammar still admits a "$": a login, a model alias, a
# database role and name, a host path. The mandatory ones and the empty ones need no list -- see
# "dollar_variables". What is left out has a grammar with no "$" in it -- a Docker
# object name, a memory size, a number, a time zone -- and the template writes it without the
# "replace" for that reason. An optional free-form value whose default is "false", the role's idiom
# for "not set", belongs here too: "false" is also how a toggle is written, so it cannot be derived.
FREE_FORM_WITH_A_DEFAULT = (
    "Artificial_Intelligence_LiteLLM_UI_username",
    "Artificial_Intelligence_PostgreSQL_user",
    "Artificial_Intelligence_PostgreSQL_database",
    "Artificial_Intelligence_LiteLLM_config_file_destination_path",
    "Artificial_Intelligence_LibreChat_config_file_destination_path",
    "Artificial_Intelligence_Claude_code_tigerblue77_model",
)

# The places another open pull request is rewriting anyway, and that this check therefore lets carry
# a single "$" for now rather than have two branches edit the same lines. Each names its owner. An
# entry that no longer exempts anything -- the place fixed, or gone -- FAILS the check: an exemption
# outliving its reason is a hole with a label on it, and the first regression there walks through.
DOLLAR_LEFT_TO_OTHER_PULL_REQUESTS = {
    "services.postgres.environment.POSTGRES_DB": "#134, which rewrites the PostgreSQL identity",
    "services.litellm.environment.DATABASE_URL": "#134, which percent-encodes it",
    "services.litellm.environment.REDIS_URL": "#130, which removes it",
}


def load_defaults(overrides=None):
    """Read the role's defaults, resolving those that interpolate the others.

    Several defaults are derived -- a destination path is a directory plus a file name -- and
    "yaml.safe_load" has no reason to notice: it hands back the "{{ ... }}" as the literal string it
    is. Rendered into the template, that literal reaches the compose file, and a mount path written
    that way is read as naming something else entirely.

    This resolved one pair by hand while there was one pair. #1, #13 and #76 each added another --
    independently, on separate branches -- and the by-hand form reported the first as an undeclared
    volume and would have carried the others' literals into a mount path
    unnoticed, since nothing here reads those keys. All are findings about the CHECK, phrased as
    findings about the template, which is the shape that gets a real one waived. It resolves every
    default now, by rendering each one against the others until nothing moves.

    `overrides` is what a caller passes the role, applied BEFORE that resolution: Ansible reads a
    derived default lazily, so one built from a variable the caller overrides follows the override --
    the name of a Docker config is built from the checksum its file was written with (#161) -- where
    resolving first and overriding after would leave it on the value it had from the defaults alone.
    """
    defaults = yaml.safe_load((ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    defaults.update(overrides or {})
    environment = Environment()
    # Bounded rather than "while changed": a default that interpolates itself would otherwise spin
    # here forever. Ten passes is far past any real chain, and a value still carrying "{{" after them
    # is a defect the render below surfaces anyway.
    for _ in range(10):
        rendered = {
            key: environment.from_string(value).render(**defaults) if isinstance(value, str) and "{{" in value else value
            for key, value in defaults.items()
        }
        if rendered == defaults:
            break
        defaults = rendered
    return defaults


def render(context):
    environment = Environment(loader=FileSystemLoader(str(ROLE / "templates")), keep_trailing_newline=True)
    template = environment.get_template(f"{context['Artificial_Intelligence_Docker_compose_file_name']}.j2")
    return template.render(**context)


def mapping(container, key):
    """The mapping under `key`, treating a key present but empty as an absent one.

    YAML makes no difference between a key that is absent and one written with nothing under it:

        resources:            ->  {"resources": {"limits": None}}
          limits:

    ".get('limits', {})" answers None there, because the key IS present -- the default never fires --
    and the next ".get" raises AttributeError. Three places in this file had that shape and crashed
    on a service block someone was in the middle of writing, which is exactly when this script gets
    run. A traceback is the worst possible answer at that moment: it hides the finding the check
    exists to report.
    """
    value = container.get(key)
    return value if isinstance(value, dict) else {}


def volume_source(volume):
    """The declared volume a mount refers to, or None when it refers to none.

    Compose accepts two syntaxes for a mount and this has to read both, because the long one is the
    form the documentation recommends and the only one that carries options:

        - Artificial_Intelligence_data:/data:rw                                     the short one, a string
        - {type: volume, source: Artificial_Intelligence_data, target: /data}       the long one, a mapping

    Reading the long form as a string is how the first version of this script turned every mount
    written that way into "references undeclared volume \"{\'type\'\"" -- a false positive, which is
    worse than no check at all: it is what teaches a reader to run the script and ignore it.

    A bind mount and a tmpfs name no declared volume, so both answer None rather than a name that
    would never be found in "volumes:".
    """
    if isinstance(volume, dict):
        # "type" defaults to "volume" when the mount has a source and does not say otherwise.
        if volume.get("type", "volume") != "volume":
            return None
        return volume.get("source")
    source = str(volume).split(":", 1)[0]
    # A bind mount names a path rather than a declared volume. An anonymous volume is written as the
    # target alone, so it has no source to declare either.
    if source.startswith((".", "/")) or source == str(volume):
        return None
    return source


def check_conventions(document, state, failures):
    """Hold one rendered document to what the template's own commented model promises."""
    services = document.get("services") or {}
    declared_networks = set(mapping(document, "networks"))
    declared_volumes = set(mapping(document, "volumes"))

    for name, service in services.items():
        where = f"[{state}] service {name!r}"
        # A service key written with nothing under it parses as None, not as an empty mapping.
        service = service if isinstance(service, dict) else {}
        deploy = mapping(service, "deploy")

        # An image floats by default and is then written with NO tag, because no tag IS ":latest" and
        # writing it out says nothing more: an explicit ":latest" is refused for that reason. Any
        # other tag is a pin, which is the template's to keep for a database and to explain on the
        # line above -- no script can tell a deliberate one from a mistake, so none is judged. The
        # registry host may carry a colon for its port, so the tag is whatever follows the last colon
        # AFTER the last slash.
        image = service.get("image") or ""
        last_segment = image.rsplit("/", 1)[-1]
        if not image:
            failures.append(f"{where}: declares no image")
        elif "@" not in image and ":" in last_segment and last_segment.rsplit(":", 1)[-1] == "latest":
            failures.append(f"{where}: image {image!r} is tagged ':latest' -- write it with no tag, which means the same")

        # An image is pulled, never built here. Compose builds a service's image only when none by that
        # name exists and never compares it with its source, so a host that built it once goes on
        # running an image nobody checks against that source; and what builds it is one more
        # obligation on the deployer. "in" rather than ".get": "build:" written empty is still
        # the key, and a mapping, a bare path and nothing at all are all refused alike.
        if "build" in service:
            failures.append(f"{where}: declares build -- an image is pulled, never built here")

        # A memory limit on every service. Without one, a container running away takes the others
        # down by OOM and the kernel log names the victim rather than the culprit.
        if not mapping(mapping(deploy, "resources"), "limits").get("memory"):
            failures.append(f"{where}: no deploy.resources.limits.memory")

        # "any", never "on-failure": the orchestrator stops an unhealthy container CLEANLY, so it
        # exits 0, and "on-failure" never replaces a task that exited cleanly.
        condition = mapping(deploy, "restart_policy").get("condition")
        if condition != "any":
            failures.append(f"{where}: deploy.restart_policy.condition is {condition!r}, expected 'any'")

        # Swarm ignores it, so a hostname that only exists under Compose breaks at the switch.
        if "container_name" in service:
            failures.append(f"{where}: declares container_name, which Swarm ignores")

        # "depends_on" as a plain list of service names, and nothing else. "docker stack deploy"
        # validates the file against docker/cli's own schema before it reaches the daemon, and there
        # the key is an array of unique strings: the long form ("condition: service_healthy") gets
        # the WHOLE file refused, and "docker compose config" accepts it without a word, which is how
        # it shipped in #1 and sat in every render since (#154). Present but written empty is
        # refused by both, so "in" rather than ".get": None is a finding here, not an absence.
        if "depends_on" in service:
            depends_on = service["depends_on"]
            if not isinstance(depends_on, list) or not all(isinstance(entry, str) for entry in depends_on):
                failures.append(
                    f"{where}: depends_on must be a list of service names -- any other form, the long "
                    "one with 'condition:' included, makes 'docker stack deploy' refuse the whole file"
                )
            elif len(set(depends_on)) != len(depends_on):
                failures.append(f"{where}: depends_on names a service twice, which 'docker stack deploy' refuses")

        # The Definition of Done of #31: everything a service references has to be declared. The
        # orchestrator only says otherwise at deployment time.
        # "networks:" is a list of names, or a mapping of name to options (aliases, an address).
        # Iterating a dict yields its keys, so one loop reads both forms.
        for network in service.get("networks") or []:
            if network not in declared_networks:
                failures.append(f"{where}: references undeclared network {network!r}")

        for volume in service.get("volumes") or []:
            source = volume_source(volume)
            # None means the mount names no declared volume: a bind mount, a tmpfs, or a form with
            # no source at all. There is nothing to look up, so there is nothing to complain about.
            if source is not None and source not in declared_volumes:
                failures.append(f"{where}: references undeclared volume {source!r}")


def mounted_config_source(document, service_name, target):
    """The name of the Docker config the service mounts at `target`, or None when it mounts none there."""
    for entry in mapping(document, "services").get(service_name, {}).get("configs") or []:
        if isinstance(entry, dict) and entry.get("target") == target:
            return entry.get("source")
    return None


def check_mounted_configs(off, on, failures):
    """Hold each mounted configuration to a Docker config named after its content, and nothing else.

    A configuration a container reads at start is a file on the host, and changing it changes nothing
    in the compose file, which is all "docker compose up" and "docker stack deploy" compare: without
    something that moves with the content, neither recreates what they see no difference in, and the
    container keeps the old routing while Ansible reports the new one "changed" (#161). A Docker
    config is the object made for this, and its name is that something: Swarm configs are immutable,
    so a changed file is a NEW name and an ordinary service update, and Compose recreates a container
    whose "configs" source changed. The file is mounted through "configs", never as a bind mount in
    "volumes", where a changed file is invisible again -- the move that quietly undoes all of it.
    """
    normalised = copy.deepcopy(on)
    for variable, (name, base, target) in MOUNTED_CONFIGS.items():
        where = f"service {name!r}"
        for state, document in (("checksums unset", off), ("checksums set", on)):
            block = mapping(mapping(document, "services"), name)
            for volume in block.get("volumes") or []:
                mounted = volume.get("target") if isinstance(volume, dict) else str(volume).split(":")[1:2]
                if mounted == target or mounted == [target]:
                    failures.append(
                        f"[{state}] {where}: mounts {target!r} as a bind mount in 'volumes' -- a changed file is "
                        "invisible in the compose file there; mount it through 'configs'"
                    )
            source = mounted_config_source(document, name, target)
            if source is None:
                failures.append(f"[{state}] {where}: mounts no Docker config at {target!r}")
            elif "file" not in mapping(mapping(document, "configs"), source):
                failures.append(f"[{state}] {where}: its config {source!r} is not declared at the top level with a 'file'")
        off_source = mounted_config_source(off, name, target)
        on_source = mounted_config_source(on, name, target)
        if off_source is None or on_source is None:
            continue
        suffix = "-" + MOUNTED_CONFIG_CHECKSUMS[variable][:8]
        if off_source != base:
            failures.append(f"[checksums unset] {where}: its config is named {off_source!r}, expected {base!r}")
        if on_source != base + suffix:
            failures.append(
                f"[checksums set] {where}: its config is named {on_source!r}, expected {base + suffix!r} -- "
                f"the name must carry {variable}, or a changed file changes nothing Docker compares"
            )
            continue
        for entry in mapping(normalised, "services")[name]["configs"]:
            if entry.get("target") == target:
                entry["source"] = off_source
        configs = mapping(normalised, "configs")
        if on_source in configs:
            configs[off_source] = configs.pop(on_source)
    if normalised != off:
        failures.append(
            "setting the configuration checksums changed more than the names of the Docker configs: "
            "it must change nothing else"
        )


def check_states(off, on, failures):
    """Hold the two rendered states to differing by the published network and by nothing else.

    This is what catches a Jinja conditional that quietly changes the services or the volumes along
    with the network -- the failure mode where a feature being off produces a stack that no longer
    says what it meant. It is a function rather than inline code so that "--selftest" can feed it a
    pair it should reject; a check nobody has watched fail is a check nobody believes.
    """
    for key in ("services", "volumes"):
        if off.get(key) != on.get(key):
            failures.append(
                f"turning the published network on changed {key!r}: it must change 'networks' only"
            )
    published = PUBLISHED_NETWORK["Artificial_Intelligence_published_Docker_network_name"]
    off_networks = set((off.get("networks") or {}).keys())
    on_networks = set((on.get("networks") or {}).keys())
    if published in off_networks:
        failures.append(f"the published network {published!r} is declared while it is unset")
    if on_networks - off_networks != {published}:
        failures.append(
            f"turning the published network on added {sorted(on_networks - off_networks)}, "
            f"expected exactly ['{published}']"
        )


def dollar_sample(name):
    """A value for `name` carrying every character that has cost a secret something here.

    "$" alone, "${" -- the form that makes Compose refuse the whole file rather than empty the value --
    "$$" which must survive as two, and the "/", "@" and "#" a generated password is made of. A host
    path -- a variable whose name ends in "_directory" or "_path", as every one of this role's does --
    is given the shape of one, so that the render stays a stack a deployer would accept. The
    variable's own name goes into its value, so a finding can be traced back to where it came from.
    """
    short = name.replace("Artificial_Intelligence_", "")
    if name.endswith(("_directory", "_path")):
        return f"/srv/{short}/Ab$cd${{HOME}}$$e@f#g$"
    return f"{short}-Ab$cd${{HOME}}$$e/f@g#h$"


def template_reads(defaults):
    """Every variable the compose template reads, whether or not "defaults/main.yml" defines it."""
    environment = Environment(loader=FileSystemLoader(str(ROLE / "templates")))
    name = f"{defaults['Artificial_Intelligence_Docker_compose_file_name']}.j2"
    return meta.find_undeclared_variables(environment.parse(environment.loader.get_source(environment, name)[0]))


def dollar_variables(read, defaults, free_form):
    """Which of the variables in `read` the "$" render gives a "$" to.

    Two of the three sources are DERIVED, so that they cover the next service without this file
    being edited:

    * every variable "defaults/main.yml" does not define. A convention of this role -- no default
      for a secret, since a default password is a published one -- is what makes that set the
      secrets plus the host paths the role cannot presuppose;
    * every variable it defines as empty, "" or a bare "key:" -- an optional value left for the
      caller to fill, as the retired GitHub Models key is. The first version of this render took
      only the undefined ones, so that key was rendered empty and the "replace" on its line could be
      deleted with the check staying green. An empty default says "a caller value goes here" as
      plainly as a missing one does;
    * and every variable `free_form` names, since a real default says nothing about grammar.

    A default of "false" is deliberately none of these: it is the role's "not set", but it is also
    how a toggle is written, and giving "Artificial_Intelligence_Claude_code_tigerblue77_enabled" a
    string would turn a switch into a password. A free-form value defaulting to "false" goes in the
    list by hand. It takes its arguments rather than reading the constants so that "--selftest" can
    hold it to each of those rules.
    """
    empty = {variable for variable in read & set(defaults) if defaults[variable] in ("", None)}
    return (read - set(defaults)) | empty | (set(free_form) & read)


def dollar_context(defaults, failures):
    """The render context in which every value "dollar_variables" selects carries a "$".

    The Claude Code agent is switched on, so that its block is rendered too.
    """
    read = template_reads(defaults)
    for variable in FREE_FORM_WITH_A_DEFAULT:
        if variable not in read:
            failures.append(
                f"FREE_FORM_WITH_A_DEFAULT names {variable!r}, which the template does not read: "
                "rename or remove the entry, or the '$' render silently stops covering what it meant to"
            )
    context = dict(defaults, **CLAUDE_CODE_TIGERBLUE77_ENABLED)
    for variable in sorted(dollar_variables(read, defaults, FREE_FORM_WITH_A_DEFAULT)):
        context[variable] = dollar_sample(variable)
    return context


def strings(node, path=""):
    """Every string of a parsed document, with where it sits: "services.redis.command[2]"."""
    if isinstance(node, dict):
        for key, value in node.items():
            where = f"{path}.{key}" if path else str(key)
            if isinstance(key, str):
                yield f"{where} (the key itself)", key
            yield from strings(value, where)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from strings(value, f"{path}[{index}]")
    elif isinstance(node, str):
        yield path, node


def single_dollar(text):
    """Whether Compose would read a "$" in `text` as the start of an interpolation.

    Compose reads "$$" as one literal "$", left to right, so what is left once every pair is gone is
    what it interpolates: "$$" is clean, "$$$" is not.
    """
    return "$" in text.replace("$$", "")


def check_dollars(document, state, failures, left_elsewhere):
    """Refuse every string of `document` in which Compose would interpolate a "$".

    It is a function taking its exemptions as an argument rather than reading the constant, so that
    "--selftest" can feed it both a document it must refuse and an exemption it must call stale.
    """
    single = {where for where, text in strings(document) if single_dollar(text)}
    for where in sorted(single - set(left_elsewhere)):
        failures.append(
            f"[{state}] {where}: carries a single '$', which Compose would interpolate -- write the "
            "value with \"| replace('$', '$$')\""
        )
    for where, owner in sorted(left_elsewhere.items()):
        if where not in single:
            failures.append(
                f"{where} is left to {owner.split(',')[0]} in DOLLAR_LEFT_TO_OTHER_PULL_REQUESTS, and carries "
                "no single '$' any more: remove the entry, it would now hide a regression"
            )


# ------------------------------------------------------------------------------------------------
# Selftest
# ------------------------------------------------------------------------------------------------
# The two other checks under ".github/scripts/" carry one and CONTRIBUTING.md makes it a principle:
# a check whose failure nobody has ever seen is a check nobody believes. This one had none, which
# mattered more here than anywhere -- "services:" is an empty mapping, so every convention check
# below runs over nothing and reports success without reading a single service. It is green because
# there is nothing to judge, and that is indistinguishable from green because everything is right.
#
# ! The cases are built IN MEMORY rather than kept as fixture files, and that is deliberate. The
# sibling check keeps its faulty configurations on disk, and one of them --
# "15_fault_multiline_flow_fallback_litellm_config.yaml" -- was silently rewritten by
# "ansible-lint --fix", which collapsed onto one line the multi-line flow mapping the fixture exists
# to encode. Its name still says "multiline_flow", it no longer tests that, and the selftest kept
# passing. A Python literal is not reachable by a YAML formatter.
#
# Every case names the substring the check must report, so a check that fails for the RIGHT reason
# and a check that fails for another are not confused with each other.

COMPLIANT_SERVICE = {
    "image": "vendor/image:1.2.3",
    "deploy": {
        "restart_policy": {"condition": "any"},
        "resources": {"limits": {"memory": "512M"}},
    },
}


def service(**overrides):
    """The compliant block with one thing changed, so each case differs from it by exactly that."""
    block = {
        "image": COMPLIANT_SERVICE["image"],
        "deploy": {
            "restart_policy": dict(COMPLIANT_SERVICE["deploy"]["restart_policy"]),
            "resources": {"limits": dict(COMPLIANT_SERVICE["deploy"]["resources"]["limits"])},
        },
    }
    for key, value in overrides.items():
        if value is _ABSENT:
            block.pop(key, None)
        else:
            block[key] = value
    return block


class _Absent:
    """Marker for "this key is not in the block at all", which None cannot express here."""


_ABSENT = _Absent()

# (name, document, expected substring or None when the document must be accepted)
CONVENTION_CASES = [
    ("compliant service", {"services": {"svc": COMPLIANT_SERVICE}}, None),
    ("image tagged :latest", {"services": {"svc": service(image="vendor/image:latest")}},
     "is tagged ':latest'"),
    # No tag is the way a floating image is written, so it is an accepted case, and so is a pin.
    ("image with no tag", {"services": {"svc": service(image="vendor/image")}}, None),
    ("image pinned on a version", {"services": {"svc": service(image="vendor/image:1.2.3")}}, None),
    ("no image at all", {"services": {"svc": service(image=_ABSENT)}},
     "declares no image"),
    # A digest IS a pin, and a registry port is a colon that is not a tag separator. Both are
    # accepted cases: a check that cried wolf on them would be a check people learn to ignore.
    ("image pinned by digest", {"services": {"svc": service(image="vendor/image@sha256:abc123")}}, None),
    ("registry carrying a port", {"services": {"svc": service(image="registry:5000/vendor/image:1.2.3")}}, None),
    ("no memory limit", {"services": {"svc": service(deploy={"restart_policy": {"condition": "any"}})}},
     "no deploy.resources.limits.memory"),
    # "limits:" written with nothing under it parses as None, which is what made three earlier
    # versions of this file crash instead of reporting. A traceback hides the finding.
    ("limits written empty",
     {"services": {"svc": service(deploy={"restart_policy": {"condition": "any"},
                                          "resources": {"limits": None}})}},
     "no deploy.resources.limits.memory"),
    ("restart_policy on-failure",
     {"services": {"svc": service(deploy={"restart_policy": {"condition": "on-failure"},
                                          "resources": {"limits": {"memory": "512M"}}})}},
     "expected 'any'"),
    ("no restart_policy",
     {"services": {"svc": service(deploy={"resources": {"limits": {"memory": "512M"}}})}},
     "expected 'any'"),
    ("container_name declared", {"services": {"svc": service(container_name="svc")}},
     "declares container_name"),
    # A build context beside an image name. Refused in each spelling Compose accepts, because the
    # check reads the key and not what it holds.
    ("build with a context and an image",
     {"services": {"svc": service(build={"context": "/srv/svc"})}},
     "declares build"),
    ("build as a bare path", {"services": {"svc": service(build="/srv/svc")}},
     "declares build"),
    ("build written empty", {"services": {"svc": service(build=None)}},
     "declares build"),
    # Each verdict below is the one "docker stack config -c" gave on the same block (#154). The
    # first refused case is the one that matters: "docker compose config" accepts it, so nothing
    # else in CI would ever say a word about it.
    ("depends_on, short form", {"services": {"svc": service(depends_on=["db", "cache"])}}, None),
    ("depends_on, empty list", {"services": {"svc": service(depends_on=[])}}, None),
    ("depends_on, long form",
     {"services": {"svc": service(depends_on={"db": {"condition": "service_healthy"}})}},
     "depends_on must be a list of service names"),
    # A list, but of mappings, which is neither form: the long form written into the short form's
    # list, an easy slip between the two.
    ("depends_on, list of mappings",
     {"services": {"svc": service(depends_on=[{"db": {"condition": "service_healthy"}}])}},
     "depends_on must be a list of service names"),
    ("depends_on written empty", {"services": {"svc": service(depends_on=None)}},
     "depends_on must be a list of service names"),
    ("depends_on naming a service twice", {"services": {"svc": service(depends_on=["db", "db"])}},
     "depends_on names a service twice"),
    ("service written empty", {"services": {"svc": None}}, "declares no image"),
    ("undeclared network", {"services": {"svc": service(networks=["nope"])}},
     "references undeclared network"),
    ("declared network",
     {"services": {"svc": service(networks=["Artificial_Intelligence_internal"])}, "networks": {"Artificial_Intelligence_internal": None}}, None),
    # "networks:" as a mapping of name to options is the other legal form; iterating it yields the
    # same names, so one loop must read both.
    ("network as a mapping",
     {"services": {"svc": service(networks={"Artificial_Intelligence_internal": {"aliases": ["a"]}})},
      "networks": {"Artificial_Intelligence_internal": None}}, None),
    ("undeclared volume, short syntax", {"services": {"svc": service(volumes=["data:/data:rw"])}},
     "references undeclared volume"),
    ("undeclared volume, long syntax",
     {"services": {"svc": service(volumes=[{"type": "volume", "source": "data", "target": "/data"}])}},
     "references undeclared volume"),
    ("declared volume",
     {"services": {"svc": service(volumes=["data:/data"])}, "volumes": {"data": None}}, None),
    # A bind mount, a tmpfs and an anonymous volume name no declared volume, so there is nothing to
    # look up and nothing to complain about. The long-syntax bind is the case that produced the
    # false positive this script's own docstring records.
    ("bind mount, short syntax", {"services": {"svc": service(volumes=["/srv/data:/data"])}}, None),
    ("bind mount, long syntax",
     {"services": {"svc": service(volumes=[{"type": "bind", "source": "/srv/data", "target": "/data"}])}},
     None),
    ("anonymous volume", {"services": {"svc": service(volumes=["/data"])}}, None),
]

# (name, checksums unset, checksums set, expected substring or None). Each document is what the
# template really renders for the two services: the file mounted through "configs", the Docker config
# declared at the top level with the path of the file on the host.
_LITELLM = MOUNTED_CONFIG_CHECKSUMS["Artificial_Intelligence_LiteLLM_config_checksum"][:8]
_LIBRECHAT = MOUNTED_CONFIG_CHECKSUMS["Artificial_Intelligence_LibreChat_config_checksum"][:8]


def mounted(litellm_name, librechat_name, **changes):
    """The two consuming services as rendered, with the Docker config named as given."""
    document = {
        "services": {
            "litellm": service(configs=[{"source": litellm_name, "target": "/app/config.yaml"}]),
            "librechat": service(configs=[{"source": librechat_name, "target": "/app/librechat.yaml"}],
                                 volumes=["uploads:/app/uploads:rw"]),
        },
        "configs": {litellm_name: {"file": "/srv/LiteLLM_config.yaml"},
                    librechat_name: {"file": "/srv/librechat.yaml"}},
    }
    document.update(changes)
    return document


_UNSET = mounted("LiteLLM_config", "LibreChat_config")
_SET = mounted(f"LiteLLM_config-{_LITELLM}", f"LibreChat_config-{_LIBRECHAT}")
CONFIG_CHECKSUM_CASES = [
    ("each file named after its content", _UNSET, _SET, None),
    # The move that undoes it: a bind mount sees the new file in the compose file as nothing at all.
    ("file bind mounted as well, short syntax",
     _UNSET,
     dict(_SET, services=dict(_SET["services"], litellm=service(
         configs=[{"source": f"LiteLLM_config-{_LITELLM}", "target": "/app/config.yaml"}],
         volumes=["/srv/LiteLLM_config.yaml:/app/config.yaml:ro"]))),
     "mounts '/app/config.yaml' as a bind mount"),
    ("file bind mounted instead, long syntax",
     {"services": {"litellm": service(volumes=[{"type": "bind", "source": "/srv/c.yaml", "target": "/app/config.yaml"}]),
                   "librechat": _UNSET["services"]["librechat"]},
      "configs": _UNSET["configs"]},
     _SET,
     "mounts '/app/config.yaml' as a bind mount"),
    ("name that does not move with the content",
     _UNSET,
     mounted("LiteLLM_config", f"LibreChat_config-{_LIBRECHAT}"),
     "its config is named 'LiteLLM_config', expected"),
    ("the two suffixes swapped",
     _UNSET,
     mounted(f"LiteLLM_config-{_LIBRECHAT}", f"LibreChat_config-{_LITELLM}"),
     "the name must carry"),
    ("suffix written while unset",
     mounted(f"LiteLLM_config-{_LITELLM}", "LibreChat_config"),
     _SET,
     "[checksums unset] service 'litellm': its config is named"),
    ("config used but never declared",
     _UNSET,
     dict(_SET, configs={f"LibreChat_config-{_LIBRECHAT}": {"file": "/srv/librechat.yaml"}}),
     "is not declared at the top level with a 'file'"),
    ("a service mounting nothing at that path",
     _UNSET,
     dict(_SET, services=dict(_SET["services"], litellm=service())),
     "mounts no Docker config at '/app/config.yaml'"),
    ("setting the checksums changed something else",
     _UNSET,
     dict(_SET, services=dict(_SET["services"], litellm=service(
         image="vendor/image:9.9.9",
         configs=[{"source": f"LiteLLM_config-{_LITELLM}", "target": "/app/config.yaml"}]))),
     "it must change nothing else"),
]

# (name, off state, on state, expected substring or None)
STATE_CASES = [
    ("only the network differs",
     {"services": {"svc": COMPLIANT_SERVICE}, "networks": {"Artificial_Intelligence_internal": None}},
     {"services": {"svc": COMPLIANT_SERVICE}, "networks": {"Artificial_Intelligence_internal": None, "DMZ": None}},
     None),
    ("turning it on also changed the services",
     {"services": {"svc": COMPLIANT_SERVICE}, "networks": {"Artificial_Intelligence_internal": None}},
     {"services": {}, "networks": {"Artificial_Intelligence_internal": None, "DMZ": None}},
     "changed 'services'"),
    ("turning it on also changed the volumes",
     {"services": {}, "volumes": {}, "networks": {"Artificial_Intelligence_internal": None}},
     {"services": {}, "volumes": {"data": None}, "networks": {"Artificial_Intelligence_internal": None, "DMZ": None}},
     "changed 'volumes'"),
    ("published network declared while unset",
     {"services": {}, "networks": {"Artificial_Intelligence_internal": None, "DMZ": None}},
     {"services": {}, "networks": {"Artificial_Intelligence_internal": None, "DMZ": None}},
     "is declared while it is unset"),
    ("turning it on added something else too",
     {"services": {}, "networks": {"Artificial_Intelligence_internal": None}},
     {"services": {}, "networks": {"Artificial_Intelligence_internal": None, "DMZ": None, "extra": None}},
     "expected exactly ['DMZ']"),
]

# (name, document, places left to another pull request, expected substring or None)
DOLLAR_CASES = [
    ("every '$' doubled",
     {"services": {"svc": {"environment": {"KEY": "Ab$$cd$${HOME}"}, "command": ["--password", "Ab$$cd"]}}},
     {}, None),
    ("single '$' in an environment value",
     {"services": {"svc": {"environment": {"KEY": "Ab$cd"}}}},
     {}, "services.svc.environment.KEY: carries a single '$'"),
    # A list item is where a password sits on a command line, and the path has to say which one.
    ("single '$' in a command line",
     {"services": {"svc": {"command": ["--password", "Ab$cd"]}}},
     {}, "services.svc.command[1]: carries a single '$'"),
    # Three in a row is one literal and one interpolation, which is what Compose makes of it.
    ("three '$' in a row",
     {"services": {"svc": {"environment": {"KEY": "Ab$$$cd"}}}},
     {}, "carries a single '$'"),
    # The ".env" reference in disguise: the value is not the caller's, it is a variable of Compose's.
    ("a ${VAR} written into the template",
     {"services": {"svc": {"environment": {"KEY": "${POSTGRES_PASSWORD}"}}}},
     {}, "carries a single '$'"),
    ("single '$' at a place left to another pull request",
     {"services": {"svc": {"environment": {"KEY": "Ab$cd"}}}},
     {"services.svc.environment.KEY": "#0, selftest"}, None),
    ("exemption the place no longer needs",
     {"services": {"svc": {"environment": {"KEY": "Ab$$cd"}}}},
     {"services.svc.environment.KEY": "#0, selftest"}, "remove the entry"),
    ("exemption for a place that is gone",
     {"services": {"svc": {"environment": {}}}},
     {"services.svc.environment.KEY": "#0, selftest"}, "remove the entry"),
]

# (name, variables the template reads, defaults, free-form list, what the "$" render must give a "$")
# A value this selects wrongly is not a failure the '$' cases above can show: a variable left out is
# rendered from its default, carries no "$", and every line it reaches passes -- which is how the
# GitHub Models key's "replace" could be deleted with the check staying green.
DOLLAR_VARIABLE_CASES = [
    ("no default, a mandatory value", {"secret"}, {}, (), {"secret"}),
    ("empty default, an optional value", {"optional_key"}, {"optional_key": ""}, (), {"optional_key"}),
    ("bare key, which YAML reads as null", {"optional_key"}, {"optional_key": None}, (), {"optional_key"}),
    ("real default, not listed", {"image_tag"}, {"image_tag": "1.2.3"}, (), set()),
    ("real default, listed", {"login"}, {"login": "admin"}, ("login",), {"login"}),
    # A string in a toggle would switch it on, which is why "false" is left to the list.
    ("false default, a toggle", {"enabled"}, {"enabled": False}, (), set()),
    ("listed, but not read", set(), {"login": "admin"}, ("login",), set()),
    ("empty default, but not read", set(), {"optional_key": ""}, (), set()),
]


def selftest():
    """Confront the checks with cases whose verdict is known, and report every disagreement."""
    problems = []

    for name, document, expected in CONVENTION_CASES:
        failures = []
        try:
            check_conventions(document, "selftest", failures)
        except Exception as error:  # noqa: BLE001 - a crash IS the finding here
            problems.append(f"{name!r}: raised {type(error).__name__}: {error}")
            continue
        problems.extend(_verdict(name, failures, expected))

    for name, off, on, expected in CONFIG_CHECKSUM_CASES:
        failures = []
        try:
            check_mounted_configs(off, on, failures)
        except Exception as error:  # noqa: BLE001
            problems.append(f"{name!r}: raised {type(error).__name__}: {error}")
            continue
        problems.extend(_verdict(name, failures, expected))

    for name, off, on, expected in STATE_CASES:
        failures = []
        try:
            check_states(off, on, failures)
        except Exception as error:  # noqa: BLE001
            problems.append(f"{name!r}: raised {type(error).__name__}: {error}")
            continue
        problems.extend(_verdict(name, failures, expected))

    for name, document, left_elsewhere, expected in DOLLAR_CASES:
        failures = []
        try:
            check_dollars(document, "selftest", failures, left_elsewhere)
        except Exception as error:  # noqa: BLE001
            problems.append(f"{name!r}: raised {type(error).__name__}: {error}")
            continue
        problems.extend(_verdict(name, failures, expected))

    for name, read, defaults, free_form, expected in DOLLAR_VARIABLE_CASES:
        try:
            derived = dollar_variables(read, defaults, free_form)
        except Exception as error:  # noqa: BLE001
            problems.append(f"{name!r}: raised {type(error).__name__}: {error}")
            continue
        if derived != expected:
            problems.append(f"{name!r}: gives a '$' to {sorted(derived)}, expected {sorted(expected)}")

    if problems:
        print(f"{len(problems)} selftest problem(s):\n")
        for problem in problems:
            print(f"  {problem}")
        print("\nThe check does not do what this file says it does. Fix the check, not the case.")
        return 1

    print(
        f"check_compose_template selftest: {len(CONVENTION_CASES)} convention case(s), "
        f"{len(STATE_CASES)} two-state case(s), {len(DOLLAR_CASES)} '$' case(s) and "
        f"{len(DOLLAR_VARIABLE_CASES)} '$' selection case(s) all judged as expected."
    )
    return 0


def _verdict(name, failures, expected):
    """Compare what the check said against what the case says it should have said."""
    if expected is None:
        if failures:
            return [f"{name!r}: accepted case was refused -- {failures}"]
        return []
    if not failures:
        return [f"{name!r}: faulty case was accepted, expected a failure mentioning {expected!r}"]
    if not any(expected in failure for failure in failures):
        return [f"{name!r}: refused for the wrong reason -- expected {expected!r}, got {failures}"]
    return []


def main():
    defaults = load_defaults()
    failures = []
    documents = {}

    for state, extra in (
        ("published network unset", {}),
        ("published network set", PUBLISHED_NETWORK),
        ("Claude Code agent (tigerblue77) enabled", CLAUDE_CODE_TIGERBLUE77_ENABLED),
        ("mounted configuration checksums set", MOUNTED_CONFIG_CHECKSUMS),
    ):
        context = dict(load_defaults(extra), **extra)
        try:
            rendered = render(context)
        except Exception as error:  # noqa: BLE001 - the message is the whole point
            failures.append(f"[{state}] the template does not render: {error}")
            continue
        try:
            documents[state] = yaml.safe_load(rendered)
        except yaml.YAMLError as error:
            failures.append(f"[{state}] the rendered file is not valid YAML: {error}")
            continue
        check_conventions(documents[state], state, failures)

    if "published network unset" in documents and "mounted configuration checksums set" in documents:
        check_mounted_configs(
            documents["published network unset"], documents["mounted configuration checksums set"], failures
        )

    if "published network unset" in documents and "published network set" in documents:
        check_states(documents["published network unset"], documents["published network set"], failures)

    # Kept apart from the loop above rather than added to it: that loop holds every state to the
    # service conventions, this one holds a single state to something else, and "check_states" reads
    # only the first two either way.
    dollar_state = "caller values carrying '$'"
    try:
        dollar_document = yaml.safe_load(render(dollar_context(defaults, failures)))
    except Exception as error:  # noqa: BLE001 - a value breaking the render or the YAML is a finding
        failures.append(f"[{dollar_state}] the template does not render into valid YAML: {error}")
    else:
        check_dollars(dollar_document, dollar_state, failures, DOLLAR_LEFT_TO_OTHER_PULL_REQUESTS)

    if failures:
        print(f"{len(failures)} problem(s) in the Artificial Intelligence compose template:\n")
        for failure in failures:
            print(f"  {failure}")
        print(
            "\nEach of these is a convention the template's own commented model documents. Read it "
            "before waiving one: they are there because the failure they prevent is silent."
        )
        return 1

    services = len(documents["published network unset"].get("services") or {})
    print(
        f"Artificial Intelligence compose template: renders and parses in both states, {services} service(s) checked "
        "against the conventions of #31."
    )
    # Printed on every run, so the places still waiting on another pull request stay in view, and so
    # does how many values the render actually gave a "$" -- a number that drops is a value lost.
    owners = sorted({owner.split(",")[0] for owner in DOLLAR_LEFT_TO_OTHER_PULL_REQUESTS.values()})
    covered = len(dollar_variables(template_reads(defaults), defaults, FREE_FORM_WITH_A_DEFAULT))
    print(
        f"No '$' reaches Compose single from the {covered} caller value(s) rendered with one"
        + (f", {len(DOLLAR_LEFT_TO_OTHER_PULL_REQUESTS)} place(s) left to {', '.join(owners)}." if owners else ".")
    )
    return 0


if __name__ == "__main__":
    # "--selftest" checks the check; with no argument it checks the template. Deliberately not
    # argparse: one flag, and this file is read far more often than it is invoked.
    sys.exit(selftest() if "--selftest" in sys.argv[1:] else main())
