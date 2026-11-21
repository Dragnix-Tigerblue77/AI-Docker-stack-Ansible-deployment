#!/bin/bash
# SPDX-FileCopyrightText: 2026 Tigerblue77
# SPDX-License-Identifier: AGPL-3.0-only

# Installs what the CI gates on, so that a Claude Code on the web session can run the same checks a
# pull request will be judged by, instead of guessing, and gives the session the git identity its
# commits need to pass the "sign-off" job. Registered as a SessionStart hook in
# ".claude/settings.json".
#
# What it installs, and why each one is here rather than assumed present : every tool below is used
# by a job of ".github/workflows/ansible-ci.yml" or ".github/workflows/gitleaks.yml", and none of
# them ships in the remote image AT THE PINNED VERSION. PyYAML is the one that used to bite : the
# image carries Debian's 6.0.1, which is not the 6.0.3 pinned and cannot be removed to make way for
# it. The virtual environment of step 1 is what steps around it -- see the comment on "VENV_PATH".
#
#   1. requirements.txt   ansible-core, ansible-lint, yamllint, reuse, PyYAML, Jinja2, docker -- the
#                         yamllint, REUSE compliance, ansible-lint, syntax-check, home-made-checks and
#                         role-run jobs of ansible-ci.yml
#   2. requirements.yml   community.docker -- the ansible-lint and syntax-check jobs, since #76 needs
#                         "docker_host_info" and "docker_container_exec" to resolve
#   3. gitleaks           its own workflow, and the ".githooks/pre-commit" that CONTRIBUTING.md asks
#                         every clone to enable
#   4. core.hooksPath     the one thing CONTRIBUTING.md says to do once per clone, and a web session
#                         IS a fresh clone
#   5. ~/.ansible/roles/deploy_Artificial_Intelligence_Docker_stack   a symlink back at this checkout, so that
#                         "ansible-lint" and "ansible-playbook --syntax-check playbook.Artificial_Intelligence.example.yaml"
#                         can resolve the bare "- role: deploy_Artificial_Intelligence_Docker_stack" the example playbook
#                         calls. This repository IS the role since the flattening that moved "tasks/",
#                         "defaults/" and the rest up to its own root -- which is what a caller
#                         installs with Galaxy or a submodule -- but that also means nothing inside
#                         the checkout is named "deploy_Artificial_Intelligence_Docker_stack" any more for Ansible's own
#                         role search to find. "~/.ansible/roles" is one of its built-in search
#                         locations, so this needs no "ansible.cfg" entry, only the symlink itself.
#   6. git identity       "Claude" as the author and a "git signoff" alias carrying the maintainer's
#                         Signed-off-by, so that a commit made here passes the sign-off job of
#                         ".github/workflows/sign-off.yml". Only on the maintainer's copy.
#
# One step this hook deliberately does NOT take :
#
#   * no ".vault_pass". Nothing in this repository is vaulted, so no check exits 1 for the want of
#     one. Writing a dummy password for a vault that does not exist would be a file nobody reads and
#     a habit that outlives its reason.
#
# ! "ansible-galaxy collection install" is step 2, not folded into step 1's loop: it installs into
# the venv the pinned "ansible-core" builds (step 1 has to run first), and it is a repository, not a
# package -- "requirements.yml", read whole, not one pin at a time. There was nothing for it to
# install until #76 brought the file; #31's own comment said so, and it is #76 that made it wrong.
#
# ! It is deliberately BEST EFFORT, and that is not the same as sloppy. A session that starts with
# both tools is the good case, but a session that starts with one is still a session where most of
# the CI can be run -- so a step that fails says what it cost, on stderr, and the next one still
# runs. The only outcome this script refuses is a session that does not start at all. Hence no
# "set -e" : a non-zero exit here is a broken startup, and nothing this script does is worth that.
#
# ! It does nothing outside a remote session. A contributor's own machine is set up by hand, from
# the "Lancer ce que la CI lancera" section of CONTRIBUTING.md, and a hook that installed things
# there would be writing into a machine whose Python it does not own.
#
# Idempotent : every step checks before it acts, so a resumed or compacted session re-runs this in
# about a second and changes nothing. Non-interactive : nothing here reads stdin.
#
# Run it by hand exactly as Claude Code will:
#
#     CLAUDE_CODE_REMOTE=true ./.claude/hooks/session-start.sh

set -uo pipefail

# ! Only in Claude Code on the web. Absent or "false" means a local machine : do nothing at all.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
    exit 0
fi

REPOSITORY_ROOT="${CLAUDE_PROJECT_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)}"
if ! cd "$REPOSITORY_ROOT"; then
    printf '%s\n' "session-start: cannot enter $REPOSITORY_ROOT, nothing was installed." >&2
    exit 0
fi

LOCAL_BINARIES_PATH="$HOME/.local/bin"

MISSING=()

# Announces a step that did not work, on stderr, and records what it cost. Never exits.
note() {
    printf '%s\n' "session-start: $1" >&2
    MISSING+=("$2")
}

# 1. Python tooling ---------------------------------------------------------------------------------
# ! WHICH INTERPRETER, and it is not the default one. "python3" here is older than the one the CI
# gives itself through actions/setup-python, and "ansible-core" declares a "Requires-Python" floor
# above that default. Installed against it, it is simply refused, so a session used to start with
# no ansible-core at all and no way to run "ansible-playbook --syntax-check", one of the six checks
# that decide its push. CI never saw it: on its own interpreter the install succeeds, so every job
# stayed green over a gap that only existed where the repository is actually developed. That is #57.
#
# The image already carries 3.10, 3.11, 3.12 and 3.13 -- nothing has to be provisioned, the default
# is just the wrong one. The version is read from the CI workflow rather than written here, for the
# reason GITLEAKS_VERSION is: a second copy of a version number is a version number that drifts, and
# the entire point is that the session runs the interpreter the pull request will meet.
PYTHON_VERSION="$(sed -n 's/^ *python-version: *"\([^"]*\)".*/\1/p' .github/workflows/ansible-ci.yml | head -1)"
PYTHON_BINARY="python3"

if [ -z "$PYTHON_VERSION" ]; then
    note "no python-version found in .github/workflows/ansible-ci.yml, so the default $(python3 -V 2>&1) is used and pins requiring a newer one will be refused." \
        "the interpreter the CI uses"
elif command -v "python${PYTHON_VERSION}" > /dev/null 2>&1; then
    PYTHON_BINARY="python${PYTHON_VERSION}"
else
    note "python${PYTHON_VERSION} is what the CI uses and it is absent from this image, so the default $(python3 -V 2>&1) is used and pins requiring a newer one will be refused." \
        "the interpreter the CI uses"
fi

# ! A virtual environment rather than "pip install" into the interpreter, because a distribution's
# interpreter is marked externally managed by PEP 668: a plain install is
# refused, and "--break-system-packages" would write into an interpreter apt also uses. The venv
# touches nothing outside itself, and it costs about three seconds to create.
#
# It also settles the PyYAML problem the old code needed "--ignore-installed" for. The image carries
# Debian's PyYAML 6.0.1 in /usr/lib/python3/dist-packages, installed by dpkg and therefore without
# the RECORD file pip needs to remove it; a venv created without --system-site-packages simply does
# not see it, so the pinned 6.0.3 installs normally rather than beside a copy it could not replace.
VENV_PATH="$HOME/.cache/ansible-toolchain-venv"

if [ ! -x "$VENV_PATH/bin/pip" ] || ! "$VENV_PATH/bin/python" -V 2>&1 | grep -q " ${PYTHON_VERSION:-0}"; then
    rm -rf "$VENV_PATH"
    if ! "$PYTHON_BINARY" -m venv "$VENV_PATH" 2> /dev/null; then
        note "could not create a virtual environment with $PYTHON_BINARY, so nothing Python was installed." \
            "the whole Python toolchain"
        VENV_PATH=""
    fi
fi

pip_install() {
    [ -n "$VENV_PATH" ] || return 1
    "$VENV_PATH/bin/pip" install --quiet --disable-pip-version-check "$@"
}

pip_show_version() {
    [ -n "$VENV_PATH" ] || return 1
    "$VENV_PATH/bin/pip" show "$1" 2> /dev/null | sed -n 's/^Version: //p'
}

# ! The console scripts land in the venv's own bin, which is not on PATH, so they are linked into
# the directory gitleaks already uses -- first on PATH in this image. Symlinks and not copies: the
# script's shebang points at the venv's python, which is what makes it find its own packages.
link_venv_binaries() {
    [ -n "$VENV_PATH" ] || return 0
    mkdir -p "$LOCAL_BINARIES_PATH" || return 0
    for binary in "$VENV_PATH"/bin/*; do
        case "${binary##*/}" in
            python* | pip* | activate* | Activate*) continue ;;
        esac
        ln -sf "$binary" "$LOCAL_BINARIES_PATH/${binary##*/}"
    done
}

# ! One "pip install" per pin, not one transaction over "requirements.txt", and that is #57. pip
# resolves a requirements file as a single unit: ONE pin it cannot satisfy fails the whole thing, and
# the others are not installed either. Measured on this image -- "ansible-core==2.21.3" declares
# "Requires-Python >= 3.12" and the image has 3.11, so pip answers "No matching distribution found"
# and the session starts with no yamllint, no ansible-lint and no PyYAML, over a package the others
# do not need. Per pin, the same session keeps everything except ansible-core.
#
# CI is unaffected either way, which is exactly why this is worth doing here: "actions/setup-python"
# gives it the interpreter it wants, so the transaction succeeds there and the failure is invisible
# to every job.
#
# The cost is honest and small: installing one by one drops pip's cross-package resolution. A pin
# whose own dependencies pull a DIFFERENT version of another pin would go unnoticed, so the versions
# actually installed are read back below and any drift from the file is reported rather than assumed
# away.
#
# The pins are read from the file with a regular expression rather than parsed: this runs before
# anything is installed, so the step that installs PyYAML cannot itself depend on PyYAML.
PYTHON_PINS=()
while IFS= read -r pin; do
    PYTHON_PINS+=("$pin")
done < <(sed -n 's/^\([A-Za-z0-9_.-]*==[A-Za-z0-9_.+-]*\).*/\1/p' requirements.txt)

if [ ${#PYTHON_PINS[@]} -eq 0 ]; then
    note "no \"name==version\" pin found in requirements.txt, so nothing was installed." "the whole Python toolchain"
else
    PINS_INSTALLED=()
    PINS_FAILED=()
    for pin in "${PYTHON_PINS[@]}"; do
        if pip_install "$pin"; then
            PINS_INSTALLED+=("$pin")
        else
            PINS_FAILED+=("$pin")
        fi
    done

    link_venv_binaries

    # Read back what is actually importable, since a dependency of one pin can have moved another.
    for pin in "${PINS_INSTALLED[@]}"; do
        name="${pin%%==*}"
        wanted="${pin##*==}"
        got="$(pip_show_version "$name")"
        if [ -n "$got" ] && [ "$got" != "$wanted" ]; then
            note "$name is installed at $got, not the pinned $wanted -- another pin's dependencies moved it." \
                "$name at its pinned version"
        fi
    done

    if [ ${#PINS_FAILED[@]} -eq 0 ]; then
        printf 'Python tooling: %d/%d pins installed (%s)\n' \
            "${#PINS_INSTALLED[@]}" "${#PYTHON_PINS[@]}" "$(yamllint --version 2> /dev/null || echo 'yamllint absent')"
    else
        # ! A refused pin does not always mean the package is absent. Another pin's dependencies can
        # pull a version of it that pip WILL accept -- ansible-lint brings an ansible-core it can
        # live with -- so the tool works and only its version differs. Saying "not installed" there
        # would send a reader hunting for something that is in front of them; saying nothing would
        # let an unpinned version pass for a pinned one. Both are read back and named.
        for pin in "${PINS_FAILED[@]}"; do
            name="${pin%%==*}"
            got="$(pip_show_version "$name")"
            if [ -n "$got" ]; then
                note "$pin was refused, but $name $got is present -- pulled in as another pin's dependency. Results here are NOT the pinned version's." \
                    "$name at its pinned version"
            else
                note "$pin could not be installed, and $name is absent. Whatever depends on it cannot be run here." \
                    "$name"
            fi
        done
        printf 'Python tooling: %d/%d pins installed, %d refused\n' \
            "${#PINS_INSTALLED[@]}" "${#PYTHON_PINS[@]}" "${#PINS_FAILED[@]}"
    fi
fi

# 2. requirements.yml (Ansible collections) ----------------------------------------------------------
# ! Only through the venv's OWN "ansible-galaxy": the venv is what carries the pinned "ansible-core",
# and a collection installed against a different "ansible-galaxy" on the image lands in a
# collections path that pinned interpreter does not read from.
if [ -z "$VENV_PATH" ] || [ ! -x "$VENV_PATH/bin/ansible-galaxy" ]; then
    note "no venv ansible-galaxy, so requirements.yml was not installed." "community.docker"
elif [ ! -f requirements.yml ]; then
    note "no requirements.yml at the repository root, so no collection was installed." "community.docker"
elif "$VENV_PATH/bin/ansible-galaxy" collection install -r requirements.yml > /dev/null 2>&1; then
    printf 'Ansible collections: requirements.yml installed\n'
else
    note "\"ansible-galaxy collection install -r requirements.yml\" failed. ansible-lint and --syntax-check cannot resolve community.docker's modules here." \
        "community.docker"
fi

# 3. gitleaks ---------------------------------------------------------------------------------------
# ! The version is read from the workflow rather than written here. A second copy of a version number
# is a version number that drifts, and the whole value of running gitleaks locally is that it is the
# same gitleaks the pull request will meet.
GITLEAKS_VERSION="$(sed -n 's/^ *GITLEAKS_VERSION: *"\([^"]*\)".*/\1/p' .github/workflows/gitleaks.yml | head -1)"

if [ -z "$GITLEAKS_VERSION" ]; then
    note "no GITLEAKS_VERSION found in .github/workflows/gitleaks.yml, so gitleaks was not installed." "gitleaks"
elif [ "$("$LOCAL_BINARIES_PATH/gitleaks" version 2> /dev/null)" = "$GITLEAKS_VERSION" ]; then
    printf 'gitleaks: %s already installed\n' "$GITLEAKS_VERSION"
# ! Unpacked into a temporary directory and moved into place only once it runs. Piping curl straight
# into tar puts the binary at its final path as the bytes arrive, so a transfer cut in the middle --
# which this environment's own notes list as a known proxy behaviour, on an 8 MB download -- leaves a
# truncated file that is executable and broken. Step 3 below then reads it as "gitleaks is installed"
# and switches core.hooksPath on, and every commit of the session fails inside the pre-commit hook.
# "mv" within the same filesystem is atomic, so the final path is never a partial file.
elif GITLEAKS_STAGING="$(mktemp -d)" \
    && curl -sSfL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
        | tar -xz -C "$GITLEAKS_STAGING" gitleaks \
    && [ "$("$GITLEAKS_STAGING/gitleaks" version 2> /dev/null)" = "$GITLEAKS_VERSION" ] \
    && mkdir -p "$LOCAL_BINARIES_PATH" \
    && mv -f "$GITLEAKS_STAGING/gitleaks" "$LOCAL_BINARIES_PATH/gitleaks"; then
    rm -rf "$GITLEAKS_STAGING"
    printf 'gitleaks: %s installed in %s\n' "$GITLEAKS_VERSION" "$LOCAL_BINARIES_PATH"
else
    rm -rf "${GITLEAKS_STAGING:-}"
    note "could not install gitleaks $GITLEAKS_VERSION from its GitHub release. The secret scanning job cannot be run locally, and the pre-commit hook would refuse every commit." \
        "gitleaks"
fi

# ! "$HOME/.local/bin" is on PATH in the image this runs in, but that is the image's choice rather
# than a guarantee. Exported through CLAUDE_ENV_FILE when it is not, and only once : the guard is what
# keeps a resumed session from appending the same line again.
if [ -n "${CLAUDE_ENV_FILE:-}" ] && [ -x "$LOCAL_BINARIES_PATH/gitleaks" ] \
    && [[ ":$PATH:" != *":$LOCAL_BINARIES_PATH:"* ]] \
    && ! grep -qs "$LOCAL_BINARIES_PATH" "$CLAUDE_ENV_FILE"; then
    # "$PATH" is meant to stay literal here: it is expanded when Claude Code sources the file, not
    # when this line is written. ShellCheck's directive takes no trailing prose, hence the two lines.
    # shellcheck disable=SC2016
    printf 'export PATH="%s:$PATH"\n' "$LOCAL_BINARIES_PATH" >> "$CLAUDE_ENV_FILE"
fi

# 4. The repository's own git hooks ------------------------------------------------------------------
# CONTRIBUTING.md calls "git config core.hooksPath .githooks" the one thing to do once per clone, and
# a web session is a fresh clone every time -- so without this line every session commits with the
# repository's only real guard-rail switched off. The CI cannot take over for it: no check can be made
# required before merging on this plan, so ".githooks/pre-commit" is the only thing that refuses
# anything.
#
# ! Guarded on gitleaks actually RUNNING, and that guard is the whole point. The pre-commit hook
# REFUSES the commit when gitleaks is absent, deliberately -- a security hook that disables itself
# lies to the person who needs it most. Enabling it after a failed install would turn a missing tool
# into a session that cannot commit at all, which is a worse trade than the one it protects against.
#
# ! It asks the binary, not the filesystem. "[ -x file ]" was the first version and it is a false
# proxy in the one failure mode that leaves bytes behind : a truncated download unpacks to a file tar
# has already made executable, so "-x" is true and the guard opens on a gitleaks that cannot run.
# Step 3 now stages the download, which closes that hole at the source ; this asks anyway, because a
# guard that protects the commit path should not depend on another step having been careful.
if [ ! -d .githooks ]; then
    note "no .githooks/ directory, so core.hooksPath was left alone." "the pre-commit hook"
elif ! "$LOCAL_BINARIES_PATH/gitleaks" version > /dev/null 2>&1 && ! gitleaks version > /dev/null 2>&1; then
    note "gitleaks is missing, so core.hooksPath was left alone: .githooks/pre-commit refuses every commit without it." \
        "the pre-commit hook"
elif [ "$(git config --get core.hooksPath)" = ".githooks" ]; then
    printf 'git hooks: core.hooksPath already points at .githooks\n'
elif git config core.hooksPath .githooks; then
    printf 'git hooks: core.hooksPath set to .githooks\n'
else
    note "could not set core.hooksPath to .githooks. Commits in this session bypass the secret scan." \
        "the pre-commit hook"
fi

# 5. Role self-resolution ----------------------------------------------------------------------------
# Idempotent by construction: "ln -sfn" replaces whatever the symlink used to point at, so a resumed
# or compacted session lands on the same target rather than failing on "File exists".
if mkdir -p "$HOME/.ansible/roles" 2> /dev/null && ln -sfn "$REPOSITORY_ROOT" "$HOME/.ansible/roles/deploy_Artificial_Intelligence_Docker_stack" 2> /dev/null; then
    printf 'Role self-resolution: ~/.ansible/roles/deploy_Artificial_Intelligence_Docker_stack -> %s\n' "$REPOSITORY_ROOT"
else
    note "could not symlink ~/.ansible/roles/deploy_Artificial_Intelligence_Docker_stack, so \"- role: deploy_Artificial_Intelligence_Docker_stack\" in playbook.Artificial_Intelligence.example.yaml will not resolve." \
        "ansible-lint and --syntax-check on playbook.Artificial_Intelligence.example.yaml"
fi

# 6. The git identity and the "signoff" alias -------------------------------------------------------
# A commit made here carries two identities that answer different questions. The AUTHOR is who wrote
# the work, the tool: git log, git blame, git shortlog and the contributor graph read that field, so
# recording the tool anywhere else is not recording it. The Signed-off-by is who certifies it, and
# the Developer Certificate of Origin is first person -- "I certify" -- which a tool cannot say, so
# that one is the maintainer's, made true by their review and merge. CONTRIBUTING.md, on contributions
# written by an agent, is the full argument.
#
# ! The trailer cannot come from "git commit -s", which derives it from user.name and user.email --
# the very fields that have to stay the tool's. It is passed whole through an alias instead, so that
# it is a command and not something to remember. Not "trailer.<token>.key": spelled with its separator
# in it ("Signed-off-by: "), that config writes a line which looks right and which a keyed read of
# the trailers, the one ".github/scripts/check_sign_off.py" makes, returns empty -- a refusal with
# nothing visible to explain it.
#
# ! Only where origin is a repository of the organisation that holds this one, not of any one owner.
# This file is cloned with the tree, so a session on somebody's fork runs it exactly as the
# maintainer's does, and there the alias would put the maintainer's attestation on work the
# maintainer has never seen -- the one thing CONTRIBUTING.md tells a contributor not to do. The owner
# is read as the path segment right after the host, in three forms of clone URL,
# "https://github.com/<owner>/...", "git@github.com:<owner>/..." and a git proxy's
# ".../git/<owner>/...", and not as any segment of the URL. It is lower-cased because a clone URL
# keeps whatever case was typed while a login compares without it. Anything else, no origin
# included, reads as not this repository: the opposite default hands a stranger's session an
# identity that is not theirs.
#
# The two addresses are written in ".github/scripts/check_sign_off.py" too, which runs in a workflow
# that never sources this file; its --selftest holds the two together. Repository-local, so nothing
# reaches into a configuration the session may share with other work.
#
# REPOSITORY_OWNER is the line to change should the repository move to another owner: a copy under
# any other reads as a fork.
REPOSITORY_OWNER="dragnix-tigerblue77"
SIGN_OFF_NAME="Tigerblue77"
SIGN_OFF_EMAIL="37409593+tigerblue77@users.noreply.github.com"
AGENT_NAME="Claude"
AGENT_EMAIL="noreply@anthropic.com"

ORIGIN_URL="$(git remote get-url origin 2> /dev/null)"
ORIGIN_URL="${ORIGIN_URL,,}"

case "$ORIGIN_URL" in
    *[/@]github.com/"$REPOSITORY_OWNER"/* | *[/@]github.com:"$REPOSITORY_OWNER"/* | */git/"$REPOSITORY_OWNER"/*)
        if git config user.name "$AGENT_NAME" \
            && git config user.email "$AGENT_EMAIL" \
            && git config alias.signoff "commit --trailer \"Signed-off-by: $SIGN_OFF_NAME <$SIGN_OFF_EMAIL>\""; then
            printf 'git identity: commits are authored as %s and signed off as %s by "git signoff", never "git commit -s"\n' \
                "$AGENT_NAME" "$SIGN_OFF_NAME"
        else
            note "could not set the git identity and the \"signoff\" alias: a commit made here would be authored and signed off by whatever git defaults to, and fail the sign-off job." \
                "the git identity and the signoff alias"
        fi
        ;;
    *)
        # Not a gap to report: on a fork it is the intended outcome, and stdout is what the session
        # reads, so a contributor's own agent learns here and not from a red pull request.
        printf 'git identity: this is not the maintainer'"'"'s copy of the repository, so none was set: sign your own work, with your own name (CONTRIBUTING.md)\n'
        ;;
esac

# ---------------------------------------------------------------------------------------------------
# A SessionStart hook's stdout is handed to the session as context, so this last line is the one thing
# the agent reads. It says which checks can be trusted, which is the only question that matters here.
if [ ${#MISSING[@]} -eq 0 ]; then
    printf 'All CI-gating checks but the two role run jobs, which need a Docker daemon, can be run in this session. See the "Commands" section of CLAUDE.md.\n'
else
    # ! IFS=';' and not IFS='; ' : bash joins "${array[*]}" with the FIRST character of IFS only, so
    # the space in the two-character version was silently dropped. The space belongs in the format.
    printf 'NOT installed: %s. The checks depending on it cannot be run here -- say so rather than reporting them as passing. See "Working in a Claude Code web session" in CLAUDE.md.\n' \
        "$(IFS=';'; printf '%s' "${MISSING[*]}" | sed 's/;/; /g')"
fi

exit 0
