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

import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

ROLE = Path(__file__).resolve().parents[2]

# The published network as a caller supplies it. The indentation is not cosmetic: the definition is
# a block string interpolated into the "networks:" mapping, so it carries its own continuation
# indent, exactly as "Homelab_Ansible_deployment" writes it in its playbook.
PUBLISHED_NETWORK = {
    "Artificial_Intelligence_published_Docker_network_name": "DMZ",
    "Artificial_Intelligence_published_Docker_network_definition": "DMZ:\n      external: true\n      name: DMZ\n",
}

# #13's service is off by default, which is exactly the branch "check_conventions" never exercises
# unless something asks for it: a Jinja "{% if %}" that is false at render time is not evaluated, so
# a defect inside it -- an undeclared volume, an unpinned image -- would render and parse cleanly
# forever. Fake but well-formed values, just enough to turn the toggle on and let the branch run.
CLAUDE_CODE_TIGERBLUE77_ENABLED = {
    "Artificial_Intelligence_Claude_code_tigerblue77_enabled": True,
    "Artificial_Intelligence_Claude_code_tigerblue77_virtual_key": "sk-selftest",
    "Artificial_Intelligence_Claude_code_tigerblue77_GitHub_token": "ghp_selftest",
    "Artificial_Intelligence_Claude_code_tigerblue77_workspace_directory": "/srv/selftest/workspace",
}


def load_defaults():
    """Read the role's defaults, resolving those that interpolate the others.

    Several defaults are derived -- a destination path is a directory plus a file name -- and
    "yaml.safe_load" has no reason to notice: it hands back the "{{ ... }}" as the literal string it
    is. Rendered into the template, that literal reaches the compose file, and a mount or a build
    context written that way is read as naming something else entirely.

    This resolved one pair by hand while there was one pair. #1, #13 and #76 each added another --
    independently, on separate branches -- and the by-hand form reported the first as an undeclared
    volume and would have carried the others' literals into "build.context" and a mount path
    unnoticed, since nothing here reads those keys. All are findings about the CHECK, phrased as
    findings about the template, which is the shape that gets a real one waived. It resolves every
    default now, by rendering each one against the others until nothing moves.
    """
    defaults = yaml.safe_load((ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
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


# The checksum "tasks/main.yml" hands the deployment role for the Dockerfile it renders (#189), and
# the service whose image TAG must carry it. Its default is "false", so the branch that appends it is
# one no default render evaluates -- the blind spot of the agent's own toggle, one level further in.
# A fake but well-formed SHA-1.
DOCKERFILE_CHECKSUM_VARIABLE = "Artificial_Intelligence_Claude_code_tigerblue77_Dockerfile_checksum"
DOCKERFILE_CHECKSUM = "89abcdef0123456789abcdef0123456789abcdef"
DOCKERFILE_CHECKSUM_CONSUMER = "claude_code_tigerblue77"


def check_dockerfile_checksum(unset, checksum_set, base_tag, failures):
    """Hold the agent's image to "<Claude Code tag>-<Dockerfile SHA-1>", and everything else to nothing.

    The suffix is the whole mechanism of #189. Compose builds a service's image only when no image by
    its name exists, and never compares the Dockerfile with what an existing image was built from.
    Under the Claude Code tag alone, a changed Dockerfile left the compose file identical, so nothing
    was built and nothing recreated: the container kept running the old image while Ansible reported
    the Dockerfile "changed". A new name is what gets it built, which is why the checksum has to be
    in the TAG. A label -- what #161 does for a mounted configuration, and so the obvious thing to
    copy -- recreates the container on the OLD image, and is refused here as surely as no suffix.

    Unset, the tag must be the Claude Code tag alone, exactly as before #189: that is what the
    defaults and a "--check" run render. An interpolation left unguarded would write "-False" into
    it instead -- a name that never changes with the Dockerfile again, which is the defect itself.
    """
    name = DOCKERFILE_CHECKSUM_CONSUMER
    unset_services = mapping(unset, "services")
    set_services = mapping(checksum_set, "services")
    if name not in unset_services or name not in set_services:
        failures.append(
            f"service {name!r} is not rendered with the agent enabled: there is no image tag to check "
            f"{DOCKERFILE_CHECKSUM_VARIABLE} against"
        )
        return
    unset_image = str(mapping(unset_services, name).get("image") or "")
    set_image = str(mapping(set_services, name).get("image") or "")
    if unset_image.rsplit(":", 1)[-1] != base_tag:
        failures.append(
            f"[Dockerfile checksum unset] service {name!r}: image {unset_image!r} is not tagged {base_tag!r} "
            f"alone, while {DOCKERFILE_CHECKSUM_VARIABLE} is false"
        )
    expected = f"{unset_image}-{DOCKERFILE_CHECKSUM}"
    if set_image != expected:
        failures.append(
            f"[Dockerfile checksum set] service {name!r}: image is {set_image!r}, expected {expected!r} -- "
            "the checksum appended to the TAG, never a label, which recreates the container on the old image"
        )
    # Put the unset image back and compare the whole documents: the checksum renames the image and
    # does nothing else.
    services = dict(set_services)
    services[name] = dict(mapping(set_services, name), image=unset_image)
    if dict(checksum_set, services=services) != unset:
        failures.append(
            f"setting {DOCKERFILE_CHECKSUM_VARIABLE} changed more than the agent's image tag: "
            "it must change nothing else"
        )


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

        # Pinned by version, never ":latest" -- nor the implicit tag, which IS ":latest". A digest
        # counts as pinned. The registry host may carry a colon for its port, so the tag is whatever
        # follows the last colon AFTER the last slash.
        image = service.get("image") or ""
        last_segment = image.rsplit("/", 1)[-1]
        if not image:
            # Said separately rather than folded into the tag check below: "image '' carries no tag"
            # is a true sentence about a service that has no image at all, and a confusing one.
            failures.append(f"{where}: declares no image")
        elif "@" not in image:
            if ":" not in last_segment:
                failures.append(f"{where}: image {image!r} carries no tag, which means ':latest'")
            elif last_segment.rsplit(":", 1)[-1] == "latest":
                failures.append(f"{where}: image {image!r} is pinned on ':latest'")

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

# (name, checksum unset, checksum set, expected substring or None) for "check_dockerfile_checksum"
# (#189). Bare blocks rather than compliant ones: that check reads the image and compares the rest,
# and holds nothing else to a convention. The agent's block sits beside another service, so that a
# change leaking out of it is told apart from the rename itself.
_AGENT = DOCKERFILE_CHECKSUM_CONSUMER
_AGENT_TAG = "2.1.236"
_AGENT_IMAGE = f"ais-claude-code-tigerblue77:{_AGENT_TAG}"
_OTHER = {"image": "vendor/image:1.2.3"}
_AGENT_UNSET = {"services": {"litellm": _OTHER, _AGENT: {"image": _AGENT_IMAGE}}}
DOCKERFILE_CHECKSUM_CASES = [
    ("checksum appended to the tag",
     _AGENT_UNSET,
     {"services": {"litellm": _OTHER, _AGENT: {"image": f"{_AGENT_IMAGE}-{DOCKERFILE_CHECKSUM}"}}},
     None),
    ("checksum left out of the tag",
     _AGENT_UNSET,
     {"services": {"litellm": _OTHER, _AGENT: {"image": _AGENT_IMAGE}}},
     "appended to the TAG"),
    # The move #161 invites: the same image, and a label that changes nothing Compose builds from.
    ("checksum written as a label",
     _AGENT_UNSET,
     {"services": {"litellm": _OTHER,
                   _AGENT: {"image": _AGENT_IMAGE, "labels": {"artificial_intelligence.config_checksum": DOCKERFILE_CHECKSUM}}}},
     "never a label"),
    # "+" is SemVer's separator for build metadata, and a character a Docker tag cannot hold.
    ("checksum joined with '+'",
     _AGENT_UNSET,
     {"services": {"litellm": _OTHER, _AGENT: {"image": f"{_AGENT_IMAGE}+{DOCKERFILE_CHECKSUM}"}}},
     "appended to the TAG"),
    ("'-False' written while unset",
     {"services": {"litellm": _OTHER, _AGENT: {"image": f"{_AGENT_IMAGE}-False"}}},
     {"services": {"litellm": _OTHER, _AGENT: {"image": f"{_AGENT_IMAGE}-{DOCKERFILE_CHECKSUM}"}}},
     f"is not tagged '{_AGENT_TAG}' alone"),
    ("setting the checksum changed something else",
     _AGENT_UNSET,
     {"services": {"litellm": {"image": "vendor/image:9.9.9"},
                   _AGENT: {"image": f"{_AGENT_IMAGE}-{DOCKERFILE_CHECKSUM}"}}},
     "it must change nothing else"),
    ("agent not rendered",
     {"services": {"litellm": _OTHER}},
     {"services": {"litellm": _OTHER}},
     "is not rendered with the agent enabled"),
]

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
    ("image pinned on :latest", {"services": {"svc": service(image="vendor/image:latest")}},
     "is pinned on ':latest'"),
    ("image with no tag", {"services": {"svc": service(image="vendor/image")}},
     "carries no tag"),
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

    for name, unset, checksum_set, expected in DOCKERFILE_CHECKSUM_CASES:
        failures = []
        try:
            check_dockerfile_checksum(unset, checksum_set, _AGENT_TAG, failures)
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

    if problems:
        print(f"{len(problems)} selftest problem(s):\n")
        for problem in problems:
            print(f"  {problem}")
        print("\nThe check does not do what this file says it does. Fix the check, not the case.")
        return 1

    print(
        f"check_compose_template selftest: {len(CONVENTION_CASES)} convention case(s) and "
        f"{len(STATE_CASES)} two-state case(s) all judged as expected."
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
        ("Claude Code agent (tigerblue77) Dockerfile checksum set",
         dict(CLAUDE_CODE_TIGERBLUE77_ENABLED, **{DOCKERFILE_CHECKSUM_VARIABLE: DOCKERFILE_CHECKSUM})),
    ):
        context = dict(defaults, **extra)
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

    agent, agent_checksum = (
        "Claude Code agent (tigerblue77) enabled",
        "Claude Code agent (tigerblue77) Dockerfile checksum set",
    )
    if agent in documents and agent_checksum in documents:
        check_dockerfile_checksum(
            documents[agent],
            documents[agent_checksum],
            defaults["Artificial_Intelligence_Claude_code_Docker_image_tag"],
            failures,
        )

    if "published network unset" in documents and "published network set" in documents:
        check_states(documents["published network unset"], documents["published network set"], failures)

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
    return 0


if __name__ == "__main__":
    # "--selftest" checks the check; with no argument it checks the template. Deliberately not
    # argparse: one flag, and this file is read far more often than it is invoked.
    sys.exit(selftest() if "--selftest" in sys.argv[1:] else main())
