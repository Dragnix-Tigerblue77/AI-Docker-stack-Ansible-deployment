#!/bin/bash
# SPDX-FileCopyrightText: 2026 Tigerblue77
# SPDX-License-Identifier: AGPL-3.0-only

# Installs what the CI gates on, so that a Claude Code on the web session can run the same checks a
# pull request will be judged by, instead of guessing. Registered as a SessionStart hook in
# ".claude/settings.json".
#
# What it installs, and why each one is here rather than assumed present : every tool below is used
# by a job of ".github/workflows/ansible-ci.yml" or ".github/workflows/gitleaks.yml", and none of
# them ships in the remote image.
#
#   1. requirements.txt   ansible-core, ansible-lint, yamllint, PyYAML -- the yamllint, ansible-lint,
#                         syntax-check and home-made-checks jobs
#   2. gitleaks           its own workflow, and the ".githooks/pre-commit" that CONTRIBUTING.md asks
#                         every clone to enable
#   3. core.hooksPath     the one thing CONTRIBUTING.md says to do once per clone, and a web session
#                         IS a fresh clone
#
# Two steps the homelab repository's equivalent has and this one deliberately does NOT :
#
#   * no "ansible-galaxy collection install". The role uses "ansible.builtin.assert" and
#     "ansible.builtin.include_role" and nothing else, so there is no "requirements.yml" to install
#     -- that is #31's choice, stated in the ansible-lint job's own comment. The day a service issue
#     brings a collection in, it brings the file and the step that installs it ;
#   * no ".vault_pass". Nothing in this repository is vaulted, so no check exits 1 for the want of
#     one. Writing a dummy password for a vault that does not exist would be a file nobody reads and
#     a habit that outlives its reason.
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
# "pip install -r" is idempotent by itself -- a satisfied "==" pin is resolved against what is already
# installed, without a round trip -- so there is nothing to check first.
# "--root-user-action=ignore" only silences pip's advice to use a virtualenv: this container is thrown
# away with the session, and the hook's stderr is where a real failure has to be visible.
#
# ! The fallback list below is a SECOND copy of version numbers that also live in "requirements.txt",
# which is exactly the thing that drifts. It is here on purpose and with an expiry condition:
# "requirements.txt" arrives with #32, and until that lands there is no file to read. When #32 has
# merged, delete the whole "else" branch and let a missing "requirements.txt" be the error it will
# then be. The pins are copied from #32's own file, not chosen here.
FALLBACK_PINS=(ansible-core==2.19.11 ansible-lint==26.6.0 yamllint==1.38.0 PyYAML==6.0.3)

# ! The retry is not belt and braces, it is the only path that works in this image. The pins include
# "PyYAML==6.0.3" and the remote image carries Debian's own PyYAML 6.0.1 in "/usr/lib/python3/
# dist-packages", installed by dpkg and therefore without the "RECORD" file pip needs to remove a
# distribution. pip refuses the whole transaction with "Cannot uninstall PyYAML 6.0.1, RECORD file
# not found. Hint: The package was installed by debian." -- so ansible-core, ansible-lint and
# yamllint are not installed either, over a package nobody asked to change.
#
# "--ignore-installed" installs the pinned versions BESIDE the distribution's instead of replacing
# them: they land in "/usr/local/lib/python3.11/dist-packages", which precedes "/usr/lib/python3/
# dist-packages" on sys.path, so an "import yaml" resolves to 6.0.3. Verified rather than assumed.
#
# It is a retry and not the first attempt on purpose: where the plain install works -- which is what
# the CI's own "actions/setup-python" gives it, on a clean interpreter -- it is the honest one, and
# leaving two copies of a package on the path is a cost worth paying only once it buys something.
pip_install() {
    pip install --quiet --disable-pip-version-check --root-user-action=ignore "$@" && return 0
    printf '%s\n' "session-start: retrying the install with --ignore-installed (a distribution package is in the way)." >&2
    pip install --quiet --disable-pip-version-check --root-user-action=ignore --ignore-installed "$@"
}

if [ -f requirements.txt ]; then
    if pip_install -r requirements.txt; then
        printf 'ansible-core, ansible-lint, yamllint and PyYAML: %s\n' "$(yamllint --version 2> /dev/null || echo installed)"
    else
        note "pip install -r requirements.txt failed. yamllint, ansible-lint, --syntax-check and the home-made checks are all unavailable." \
            "the whole Python toolchain"
    fi
elif pip_install "${FALLBACK_PINS[@]}"; then
    printf 'ansible-core, ansible-lint, yamllint and PyYAML: %s (no requirements.txt yet, installed from this hook pins -- see #32)\n' \
        "$(yamllint --version 2> /dev/null || echo installed)"
else
    note "no requirements.txt, and installing this hook's fallback pins failed. yamllint, ansible-lint, --syntax-check and the home-made checks are all unavailable." \
        "the whole Python toolchain"
fi

# 2. gitleaks ---------------------------------------------------------------------------------------
# ! The version is read from the workflow rather than written here, for the reason step 1 has to
# apologise for: a second copy of a version number is a version number that drifts, and the whole
# value of running gitleaks locally is that it is the same gitleaks the pull request will meet. The
# literal below is only what to use until #32 brings the workflow, and goes when it lands.
GITLEAKS_VERSION="$(sed -n 's/^ *GITLEAKS_VERSION: *"\([^"]*\)".*/\1/p' .github/workflows/gitleaks.yml 2> /dev/null | head -1)"
GITLEAKS_VERSION="${GITLEAKS_VERSION:-8.30.1}"

if [ "$("$LOCAL_BINARIES_PATH/gitleaks" version 2> /dev/null)" = "$GITLEAKS_VERSION" ]; then
    printf 'gitleaks: %s already installed\n' "$GITLEAKS_VERSION"
elif mkdir -p "$LOCAL_BINARIES_PATH" \
    && curl -sSfL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
        | tar -xz -C "$LOCAL_BINARIES_PATH" gitleaks; then
    printf 'gitleaks: %s installed in %s\n' "$GITLEAKS_VERSION" "$LOCAL_BINARIES_PATH"
else
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

# 3. The repository's own git hooks ------------------------------------------------------------------
# CONTRIBUTING.md calls "git config core.hooksPath .githooks" the one thing to do once per clone, and
# a web session is a fresh clone every time -- so without this line every session commits with the
# repository's only real guard-rail switched off. The CI cannot take over for it: no check can be made
# required before merging on this plan, so ".githooks/pre-commit" is the only thing that refuses
# anything.
#
# ! Guarded on gitleaks being installed, and that guard is the whole point. The pre-commit hook
# REFUSES the commit when gitleaks is absent, deliberately -- a security hook that disables itself
# lies to the person who needs it most. Enabling it after a failed install would turn a missing tool
# into a session that cannot commit at all, which is a worse trade than the one it protects against.
if [ ! -d .githooks ]; then
    printf 'git hooks: no .githooks/ yet, nothing to enable (it arrives with #32)\n'
elif [ ! -x "$LOCAL_BINARIES_PATH/gitleaks" ] && ! command -v gitleaks > /dev/null 2>&1; then
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

# ---------------------------------------------------------------------------------------------------
# A SessionStart hook's stdout is handed to the session as context, so this last line is the one thing
# the agent reads. It says which checks can be trusted, which is the only question that matters here.
if [ ${#MISSING[@]} -eq 0 ]; then
    printf 'All CI-gating checks can be run in this session. See the "Commands" section of CLAUDE.md.\n'
else
    printf 'NOT installed: %s. The checks depending on it cannot be run here -- say so rather than reporting them as passing. See "Working in a Claude Code web session" in CLAUDE.md.\n' \
        "$(IFS='; '; printf '%s' "${MISSING[*]}")"
fi

exit 0
