#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77
# SPDX-License-Identifier: AGPL-3.0-only
"""Render the AIS compose template, parse it, and hold it to the conventions #31 sets.

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

ROLE = Path(__file__).resolve().parents[2] / "roles" / "deploy_AIS_Docker_stack"

# The published network as a caller supplies it. The indentation is not cosmetic: the definition is
# a block string interpolated into the "networks:" mapping, so it carries its own continuation
# indent, exactly as "Homelab_Ansible_deployment" writes it in its playbook.
PUBLISHED_NETWORK = {
    "AIS_published_Docker_network_name": "DMZ",
    "AIS_published_Docker_network_definition": "DMZ:\n      external: true\n      name: DMZ\n",
}


def load_defaults():
    """Read the role's defaults, resolving the two that interpolate each other."""
    defaults = yaml.safe_load((ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    defaults["AIS_Docker_compose_file_destination_path"] = (
        defaults["AIS_Docker_compose_file_destination_directory"]
        + defaults["AIS_Docker_compose_file_name"]
    )
    return defaults


def render(context):
    environment = Environment(loader=FileSystemLoader(str(ROLE / "templates")), keep_trailing_newline=True)
    template = environment.get_template(f"{context['AIS_Docker_compose_file_name']}.j2")
    return template.render(**context)


def check_conventions(document, state, failures):
    """Hold one rendered document to what the template's own commented model promises."""
    services = document.get("services") or {}
    declared_networks = set((document.get("networks") or {}).keys())
    declared_volumes = set((document.get("volumes") or {}).keys())

    for name, service in services.items():
        where = f"[{state}] service {name!r}"
        deploy = service.get("deploy") or {}

        # Pinned by version, never ":latest" -- nor the implicit tag, which IS ":latest". A digest
        # counts as pinned. The registry host may carry a colon for its port, so the tag is whatever
        # follows the last colon AFTER the last slash.
        image = service.get("image", "")
        last_segment = image.rsplit("/", 1)[-1]
        if "@" not in image:
            if ":" not in last_segment:
                failures.append(f"{where}: image {image!r} carries no tag, which means ':latest'")
            elif last_segment.rsplit(":", 1)[-1] == "latest":
                failures.append(f"{where}: image {image!r} is pinned on ':latest'")

        # A memory limit on every service. Without one, a container running away takes the others
        # down by OOM and the kernel log names the victim rather than the culprit.
        if not (deploy.get("resources") or {}).get("limits", {}).get("memory"):
            failures.append(f"{where}: no deploy.resources.limits.memory")

        # "any", never "on-failure": the orchestrator stops an unhealthy container CLEANLY, so it
        # exits 0, and "on-failure" never replaces a task that exited cleanly.
        condition = (deploy.get("restart_policy") or {}).get("condition")
        if condition != "any":
            failures.append(f"{where}: deploy.restart_policy.condition is {condition!r}, expected 'any'")

        # Swarm ignores it, so a hostname that only exists under Compose breaks at the switch.
        if "container_name" in service:
            failures.append(f"{where}: declares container_name, which Swarm ignores")

        # The Definition of Done of #31: everything a service references has to be declared. The
        # orchestrator only says otherwise at deployment time.
        for network in service.get("networks") or []:
            if network not in declared_networks:
                failures.append(f"{where}: references undeclared network {network!r}")
        for volume in service.get("volumes") or []:
            source = str(volume).split(":", 1)[0]
            # A bind mount names a path rather than a declared volume.
            if not source.startswith((".", "/")) and source not in declared_volumes:
                failures.append(f"{where}: references undeclared volume {source!r}")


def main():
    defaults = load_defaults()
    failures = []
    documents = {}

    for state, extra in (("published network unset", {}), ("published network set", PUBLISHED_NETWORK)):
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

    # The two states have to differ by the published network and by nothing else. This is what
    # catches a Jinja conditional that quietly changes the services or the volumes along with it --
    # the failure mode where a feature being off produces a stack that no longer says what it meant.
    if len(documents) == 2:
        off, on = documents["published network unset"], documents["published network set"]
        for key in ("services", "volumes"):
            if off.get(key) != on.get(key):
                failures.append(
                    f"turning the published network on changed {key!r}: it must change 'networks' only"
                )
        published = PUBLISHED_NETWORK["AIS_published_Docker_network_name"]
        off_networks = set((off.get("networks") or {}).keys())
        on_networks = set((on.get("networks") or {}).keys())
        if published in off_networks:
            failures.append(f"the published network {published!r} is declared while it is unset")
        if on_networks - off_networks != {published}:
            failures.append(
                f"turning the published network on added {sorted(on_networks - off_networks)}, "
                f"expected exactly ['{published}']"
            )

    if failures:
        print(f"{len(failures)} problem(s) in the AIS compose template:\n")
        for failure in failures:
            print(f"  {failure}")
        print(
            "\nEach of these is a convention the template's own commented model documents. Read it "
            "before waiving one: they are there because the failure they prevent is silent."
        )
        return 1

    services = len(documents["published network unset"].get("services") or {})
    print(
        f"AIS compose template: renders and parses in both states, {services} service(s) checked "
        "against the conventions of #31."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
