#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77 and the AI Docker stack Ansible deployment contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Flag a pull request with a commit that carries no usable Signed-off-by.

WHY THIS CHECK EXISTS
---------------------
CONTRIBUTING.md asks for a Signed-off-by on every commit. It is the contributor's statement of the
Developer Certificate of Origin: their right to submit the work under the repository's open licence,
AGPL-3.0-only. It says nothing of the commercial arm, which the grant in CONTRIBUTING.md covers on
submission, signed off or not. A rule stated and checked nowhere is held by whoever happens to
remember it.

WHAT IT CAN AND CANNOT STOP
---------------------------
It reports and stops nothing by itself. What stops a merge is the imported ruleset, which names
this job among the contexts of ".github/rulesets/main.json", so GitHub refuses any merge, a human's
included, while it is red or has not started. dependabot-auto-merge.yml reads the same contexts to
decide Dependabot's merge and the model-deletion pull request's. Nothing in .githooks reads a
sign-off.

ON THE PULL REQUEST, AND ONLY THERE
-----------------------------------
The history already on the default branch carries no sign-off, Dependabot's commits apart, and
cannot be signed without rewriting a published branch: run on a push to it, this check would be red
for ever. It reads the commits of one pull request, "base..head", and so covers what arrives from
here on. That is also why its workflow has no "workflow_dispatch": a run started by hand has no
range.

WHAT IT CHECKS
--------------
Every commit of the range except merge commits. Git writes a merge itself -- the default branch
brought into a branch, GitHub's "Update branch" -- it has no contribution of its own to certify, and
everything it brings in was signed where it was written.

1. A Signed-off-by TRAILER, read by git's own parser, whose value has the SHAPE "Name <address>".
   Each half closes a hole the other leaves. A search of the message body passes a commit that only
   QUOTES the rule, on which git reports no trailer. A trailer read without its value passes
   "Signed-off-by:" followed by nothing, or by a name with no address, which is what a broken git
   configuration writes. Whether a mailbox is reachable cannot be decided from here, so the address
   only has to look like one. One well-formed value is enough: a co-author's malformed line does not
   undo the author's.
2. A sign-off that names only the agent (AGENT_EMAIL) is refused. The certificate is first person,
   "I certify", which a tool cannot say. It is matched on the address, never on the name, which any
   contributor may bear.
3. A commit the agent authored needs the maintainer's sign-off (MAINTAINER_EMAIL) among its values.
   The author field says who wrote the work and the trailer who answers for it; naming a look-alike
   identity, or somebody who never saw the work, would satisfy rule 1 and certify nothing. The rule
   fires on the agent's address and stays silent on everyone else, because "author equals signer"
   is the normal shape for a person certifying their own work, and a commit a session wrote under
   the maintainer's own name cannot be told from one he typed.
4. It fails closed. A range git cannot read, which is what a shallow checkout looks like, and an
   empty one, which is what a wrong base or head looks like, both exit 1, and so does any exception
   in the script itself, that being Python's own exit status for one. A false red is read by a
   person who can look at the commits; a false green lets through what this exists to refuse, on a
   run that looks fine. Exit 0 means every commit passed, 1 a refusal or an unreadable range, 2 a
   wrong call.

WHAT IT DELIBERATELY DOES NOT CHECK
-----------------------------------
* Co-Authored-By. Naming the agent as a co-author of a commit somebody else authored is a question
  of attribution and not of the licence grant, and a commit made at the keyboard with the trailer
  Claude Code adds is validly signed. Refusing it would turn such a commit red for nothing.
* Whether the person behind a sign-off read anything. Their review and merge are what make it true,
  and no workflow can tell the difference.
* A well-formed quotation at the very END of a message: git parses it as a trailer, so it passes.
  The bound is known, and written down so that the next reader who finds it knows it was.

Its verification cases build throwaway repositories in a temporary directory, never under the tree,
for the reason CLAUDE.md gives for keeping fixtures out of it. They also run the session-start hook
against a sandbox, because the two files state the same addresses and nothing else keeps them in
step.

Run it from the repository root, with the range a pull request gives:

    python3 .github/scripts/check_sign_off.py --selftest
    python3 .github/scripts/check_sign_off.py <base-sha> <head-sha>
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude" / "hooks" / "session-start.sh"

# The identity .claude/hooks/session-start.sh authors a session's commits under, and the one it puts
# on their trailer. Written here as well as there because this runs in a workflow that never sources
# the hook; the selftest holds the two together, so that changing one without the other fails
# instead of quietly refusing every commit a session makes.
AGENT_EMAIL = "noreply@anthropic.com"
MAINTAINER_EMAIL = "37409593+tigerblue77@users.noreply.github.com"

# The value of a Signed-off-by trailer, once git has consumed the key (which it matches without
# regard to case). The address is the last angle-bracketed group.
SIGN_OFF_VALUE = re.compile(r"(?P<name>.+) <(?P<address>[^\s<>]+@[^\s<>]+)>\s*")

UNSIGNED = "unsigned"
AGENT_ONLY = "agent only"
NOT_MAINTAINER = "not the maintainer"

REFUSALS = {
    UNSIGNED: 'carries no Signed-off-by of the form "Name <address>"',
    AGENT_ONLY: "is signed off under the agent identity only, which certifies nobody",
    NOT_MAINTAINER: "is authored by the agent and not signed off by the maintainer",
}


def git(arguments, cwd=None, env=None):
    return subprocess.run(["git", *arguments], cwd=cwd, env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def refusal(author_email, values):
    """Why a commit is refused, or None. "values" are the lines of its Signed-off-by trailers."""
    addresses = []
    for value in values:
        match = SIGN_OFF_VALUE.fullmatch(value)
        if match:
            addresses.append(match.group("address").lower())
    if not addresses:
        return UNSIGNED
    if all(address == AGENT_EMAIL for address in addresses):
        return AGENT_ONLY
    if author_email.lower() == AGENT_EMAIL and MAINTAINER_EMAIL not in addresses:
        return NOT_MAINTAINER
    return None


def commits_between(base, head, cwd=None, env=None):
    """The non-merge commits of base..head, or None when git cannot read the range."""
    # "--end-of-options": the two ends come from the caller, and neither may be read as an option.
    result = git(["rev-list", "--no-merges", "--end-of-options", "%s..%s" % (base, head)], cwd, env)
    return result.stdout.split() if result.returncode == 0 else None


def describe(commit, cwd=None, env=None):
    """(author address, subject, Signed-off-by values) of one commit."""
    result = git(["log", "-1", "--format=%ae%x00%s%x00%(trailers:key=Signed-off-by,valueonly)",
                  commit], cwd, env)
    if result.returncode != 0:
        raise RuntimeError("git could not read commit %s: %s" % (commit, result.stderr.strip()))
    author, subject, trailers = result.stdout.split("\0", 2)
    return author, subject, trailers.splitlines()


def check(base, head, cwd=None, env=None):
    """Exit status for the range base..head, with the verdict printed."""
    commits = commits_between(base, head, cwd, env)
    if commits is None:
        print("::error::Could not read the commits between %s and %s. Checking out with "
              "fetch-depth 0 is what makes both ends of that range present" % (base, head),
              file=sys.stderr)
        return 1
    # Refused rather than passed: a pull request that adds nothing needs nobody's opinion, while a
    # range that resolves to nothing because a base or head was computed wrong is the shape of a
    # false green, and from here the two cannot be told apart.
    if not commits:
        print("::error::No commit between %s and %s. A range that resolves to nothing is refused "
              "rather than reported clean, since a base or head computed wrong looks exactly like "
              "this" % (base, head), file=sys.stderr)
        return 1

    # Told apart by who wrote the commit, because they are repaired apart: telling one to apply the
    # other's remedy is how a contributor ends up force-pushing for nothing.
    by_person = 0
    by_agent = 0
    for commit in reversed(commits):
        author, subject, values = describe(commit, cwd, env)
        reason = refusal(author, values)
        if reason is None:
            continue
        print('::error::%s "%s" %s' % (commit[:8], subject, REFUSALS[reason]), file=sys.stderr)
        if author.lower() == AGENT_EMAIL:
            by_agent += 1
        else:
            by_person += 1

    total = len(commits)
    if not by_person and not by_agent:
        print("All %d commit(s) carry a sign-off" % total)
        return 0

    if by_person:
        print("\n%d of the %d commits in this pull request lack a usable sign-off.\n\n"
              "Adding one is your statement of the Developer Certificate of Origin, your right to\n"
              "submit the work under the repository's open licence. See CONTRIBUTING.md. To sign\n"
              "the commits already on this branch:\n\n"
              "  git rebase --signoff %s\n"
              "  git push --force-with-lease\n\n"
              'and "git commit -s" from here on, or "git commit --amend -s" for the last one.'
              % (by_person, total, base), file=sys.stderr)
    if by_agent:
        print("\n%d of the %d commits in this pull request are authored by the agent without the\n"
              "maintainer's sign-off.\n\n"
              "A tool certifies nothing, so the trailer has to name the person who answers for\n"
              "the work while the author field keeps saying who wrote it. See CONTRIBUTING.md, on\n"
              'contributions written by an agent. "git commit -s" derives the trailer from\n'
              "user.name and user.email, which in a session are the tool's, and would write this\n"
              "same commit again. On Claude Code on the web, .claude/hooks/session-start.sh sets\n"
              'the "git signoff" alias that carries the right one, so the usual cause is a\n'
              "session that started before the hook did, or ran an older one. Re-run it, then\n"
              "re-commit:\n\n"
              "  CLAUDE_CODE_REMOTE=true bash .claude/hooks/session-start.sh\n"
              "  git signoff --amend --no-edit          # for the last commit\n"
              "  git rebase %s --exec 'git signoff --amend --no-edit'      # for several"
              % (by_agent, total, base), file=sys.stderr)
    return 1


# The verification cases: each builds a repository, then the script runs against it the way the
# workflow calls it.
AGENT = ("Claude", AGENT_EMAIL)
AGENT_VERSIONED = ("Claude Model-X", AGENT_EMAIL)
MAINTAINER = ("Tigerblue77", MAINTAINER_EMAIL)
CONTRIBUTOR = ("Random J Developer", "random@example.invalid")
SOMEBODY_ELSE = ("Somebody Else", "somebody@example.invalid")
LOOK_ALIKE = ("Claude Code", "claude@example.invalid")
DEPENDABOT = ("dependabot[bot]", "support@github.com")
# The author and the sign-off of the commit the model-drift workflow makes through the API.
ACTIONS_BOT = ("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com")


def identity(person):
    return "%s <%s>" % person


class Repository:
    """A git repository nobody's configuration reaches into: the global and system configs are
    switched off, so that an alias, a signing key or an identity on the machine running the check
    cannot decide what a commit here looks like."""

    def __init__(self, path):
        self.path = path
        path.mkdir(parents=True)
        self.env = {name: value for name, value in os.environ.items()
                    if not name.startswith("GIT_")}
        self.env.update(HOME=str(path.parent), XDG_CONFIG_HOME=str(path.parent),
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        self.run("init", "--quiet")
        self.run("symbolic-ref", "HEAD", "refs/heads/trunk")
        self.base = self.commit("The base the pull request starts from", sign_offs=[CONTRIBUTOR])

    def run(self, *arguments, person=CONTRIBUTOR):
        env = dict(self.env, GIT_AUTHOR_NAME=person[0], GIT_AUTHOR_EMAIL=person[1],
                   GIT_COMMITTER_NAME=person[0], GIT_COMMITTER_EMAIL=person[1])
        result = git(arguments, self.path, env)
        if result.returncode != 0:
            raise RuntimeError("git %s failed: %s" % (" ".join(arguments), result.stderr.strip()))
        return result.stdout.strip()

    def head(self):
        return self.run("rev-parse", "HEAD")

    def commit(self, subject, author=CONTRIBUTOR, sign_offs=(), co_author=None, paragraphs=()):
        arguments = ["commit", "--quiet", "--allow-empty", "--no-verify", "--no-gpg-sign",
                     "-m", subject]
        for paragraph in paragraphs:
            arguments += ["-m", paragraph]
        for person in sign_offs:
            arguments += ["--trailer", "Signed-off-by: %s" % identity(person)]
        if co_author:
            arguments += ["--trailer", "Co-Authored-By: %s" % identity(co_author)]
        self.run(*arguments, person=author)
        return self.head()

    def sign_offs(self):
        return self.run("log", "-1", "--format=%(trailers:key=Signed-off-by,valueonly)")


def selftest_cases():
    """(what it proves, builder, exit status expected, text the output holds, text it lacks).

    A builder receives the repository and returns the arguments to call the script with, or nothing
    for the range from the base to the head."""
    cases = []

    def case(purpose, status, holds=(), lacks=()):
        def register(builder):
            cases.append((purpose, builder, status, holds, lacks))
            return builder
        return register

    @case("every commit signed by its own author is accepted", 0, holds=("All 2 commit(s)",))
    def _(repo):
        repo.commit("The first change", sign_offs=[CONTRIBUTOR])
        repo.commit("The second change", sign_offs=[CONTRIBUTOR])

    @case("an unsigned commit among signed ones fails the branch, and only it is named", 1,
          holds=("The one that forgot", "1 of the 3 commits"), lacks=("The one that remembered",))
    def _(repo):
        repo.commit("The one that remembered", sign_offs=[CONTRIBUTOR])
        repo.commit("The one that forgot")
        repo.commit("The other one that remembered", sign_offs=[CONTRIBUTOR])

    @case("every unsigned commit is reported, not only the first", 1,
          holds=("The first one that forgot", "The second one that forgot", "2 of the 2 commits"))
    def _(repo):
        repo.commit("The first one that forgot")
        repo.commit("The second one that forgot")

    @case("a sign-off merely quoted inside the message certifies nobody", 1,
          holds=("Explain the sign-off",))
    def _(repo):
        quote = "Signed-off-by: %s" % identity(CONTRIBUTOR)
        repo.commit("Explain the sign-off", paragraphs=[
            "The line reads:\n%s\nin the middle of a paragraph." % quote,
            "And the message goes on."])
        assert repo.sign_offs() == "", "the premise: git records no trailer on this commit"
        assert quote in repo.run("log", "-1", "--format=%B"), "while the line is in the message"

    @case("a Signed-off-by with nothing after it is refused", 1)
    def _(repo):
        repo.commit("A change", paragraphs=["Signed-off-by:"])

    @case("a Signed-off-by naming nobody reachable is refused", 1)
    def _(repo):
        repo.commit("A change", paragraphs=["Signed-off-by: %s" % CONTRIBUTOR[0]])

    @case("a Signed-off-by with an address and no name is refused", 1)
    def _(repo):
        repo.commit("A change", paragraphs=["Signed-off-by: <%s>" % CONTRIBUTOR[1]])

    @case("a Signed-off-by whose address has no @ is refused", 1)
    def _(repo):
        repo.commit("A change", paragraphs=["Signed-off-by: %s <nobody>" % CONTRIBUTOR[0]])

    @case("one well-formed sign-off is enough beside a malformed one", 0)
    def _(repo):
        repo.commit("A change", paragraphs=["Signed-off-by: %s\nSigned-off-by: %s"
                                            % (SOMEBODY_ELSE[0], identity(CONTRIBUTOR))])

    @case("a bot whose name carries brackets is accepted, as Dependabot signs its commits", 0)
    def _(repo):
        repo.commit("Bump a tool", author=DEPENDABOT, sign_offs=[DEPENDABOT])

    @case("the commit the model-drift workflow makes, the Actions bot's under its own sign-off, is "
          "accepted", 0, holds=("All 1 commit(s)",))
    def _(repo):
        repo.commit("Delete the models their provider has retired", author=ACTIONS_BOT,
                    paragraphs=["A first paragraph of prose.", "A second one, which ends the body."],
                    sign_offs=[ACTIONS_BOT])
        assert repo.sign_offs() == identity(ACTIONS_BOT), "the premise: git reads that trailer"

    @case("the same commit without the bot's sign-off is refused: a bot is no exemption", 1,
          holds=("carries no Signed-off-by",))
    def _(repo):
        repo.commit("Delete the models their provider has retired", author=ACTIONS_BOT)

    @case("a sign-off naming only the agent is refused on a commit somebody else authored", 1,
          holds=("agent identity only",))
    def _(repo):
        repo.commit("A change", author=CONTRIBUTOR, sign_offs=[AGENT])

    @case("an unsigned commit the agent authored is sent to \"git signoff\", not to \"-s\"", 1,
          holds=("carries no Signed-off-by", "git signoff --amend --no-edit"),
          lacks=("git rebase --signoff",))
    def _(repo):
        repo.commit("A session's change", author=AGENT)

    @case("a commit the agent authored and certified under itself is refused", 1,
          holds=("agent identity only", "git signoff"), lacks=("carries no Signed-off-by",))
    def _(repo):
        repo.commit("A session's change", author=AGENT, sign_offs=[AGENT])

    @case("a person alongside the agent is a person certifying, and is accepted", 0)
    def _(repo):
        repo.commit("A change", author=CONTRIBUTOR, sign_offs=[AGENT, CONTRIBUTOR])

    @case("the maintainer's sign-off on a commit the agent authored is accepted", 0)
    def _(repo):
        repo.commit("A session's change", author=AGENT, sign_offs=[MAINTAINER])

    @case("the same with the Co-Authored-By trailer naming the agent, the shape of this "
          "repository's commits", 0)
    def _(repo):
        repo.commit("A session's change", author=AGENT, sign_offs=[MAINTAINER],
                    co_author=AGENT_VERSIONED)

    @case("a commit the agent authored, signed off by somebody other than the maintainer, "
          "is refused", 1, holds=("not signed off by the maintainer",))
    def _(repo):
        repo.commit("A session's change", author=AGENT, sign_offs=[SOMEBODY_ELSE])

    @case("a commit the agent authored, signed off under a look-alike identity, is refused", 1,
          holds=("not signed off by the maintainer",))
    def _(repo):
        repo.commit("A session's change", author=AGENT, sign_offs=[LOOK_ALIKE])

    @case("a person certifying their own work is left alone", 0,
          lacks=("not signed off by the maintainer",))
    def _(repo):
        repo.commit("A contribution", author=CONTRIBUTOR, sign_offs=[CONTRIBUTOR])

    @case("the agent as co-author of a signed commit somebody else authored is not this check's "
          "business", 0)
    def _(repo):
        repo.commit("A change", author=MAINTAINER, sign_offs=[MAINTAINER],
                    co_author=AGENT_VERSIONED)

    @case("a merge commit is not asked for a sign-off, nor is what it brings in", 0,
          holds=("All 1 commit(s)",))
    def _(repo):
        repo.run("checkout", "--quiet", "-b", "branch")
        repo.commit("The branch, signed as it should be", sign_offs=[CONTRIBUTOR])
        repo.run("checkout", "--quiet", "trunk")
        moved = repo.commit("The base moves on meanwhile, unsigned like the history before")
        repo.run("checkout", "--quiet", "branch")
        repo.run("merge", "--quiet", "--no-ff", "--no-edit", "trunk")
        assert repo.run("rev-list", "--merges", "--count", "%s..HEAD" % moved) == "1", \
            "the premise: the range holds a merge commit"
        return moved, repo.head()

    @case("a range holding no commit is refused rather than reported clean", 1,
          holds=("No commit",))
    def _(repo):
        return repo.head(), repo.head()

    @case("a range that cannot be read fails closed", 1, holds=("fetch-depth",))
    def _(repo):
        return "0" * 40, repo.head()

    @case("a range end that looks like an option is refused, not obeyed", 1)
    def _(repo):
        return "--all", repo.head()

    @case("no range at all is a wrong call", 2, holds=("Usage",))
    def _(repo):
        return ()

    @case("a base without a head is a wrong call", 2, holds=("Usage",))
    def _(repo):
        return (repo.base,)

    @case("three arguments are a wrong call", 2, holds=("Usage",))
    def _(repo):
        return repo.base, repo.head(), repo.head()

    return cases


def run_script(arguments, repo):
    """The script, run the way the workflow calls it, from inside "repo"."""
    return subprocess.run([sys.executable, str(Path(__file__).resolve()), *arguments],
                          cwd=repo.path, env=repo.env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def hook_value(name):
    """The value the session-start hook assigns to "name", or None."""
    match = re.search(r'^%s="([^"]*)"$' % name, HOOK.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else None


def hook_cases(directory):
    """The hook against sandboxes: (what it proves, problem or None)."""
    results = []

    def record(purpose, problem):
        results.append((purpose, problem))

    problems = [name for name, expected in (("AGENT_EMAIL", AGENT_EMAIL),
                                            ("SIGN_OFF_EMAIL", MAINTAINER_EMAIL))
                if hook_value(name) != expected]
    record("the hook and the check state the same two addresses",
           "%s differ between %s and the script" % (", ".join(problems), HOOK.name)
           if problems else None)

    # The hook's other steps need the network and install tools; with no workflow, no requirements
    # file and a python3 that fails, each one reports on stderr and moves on, which leaves the
    # identity step to run alone. HOME is the sandbox's, so nothing lands in the real one.
    stubs = directory / "stubs"
    stubs.mkdir()
    (stubs / "python3").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (stubs / "python3").chmod(0o755)

    def run_hook(name, origin):
        repo = Repository(directory / name)
        if origin:
            repo.run("remote", "add", "origin", origin)
        env = dict(repo.env, CLAUDE_CODE_REMOTE="true", CLAUDE_PROJECT_DIR=str(repo.path),
                   PATH=str(stubs) + os.pathsep + os.environ["PATH"])
        result = subprocess.run(["bash", str(HOOK)], cwd=repo.path, env=env, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=120)
        return repo, env, result

    repository = "Dragnix-Tigerblue77/ai-docker-stack-ansible-deployment"
    for form, origin in (("https", "https://github.com/" + repository),
                         ("ssh", "git@github.com:%s.git" % repository),
                         ("proxy", "http://local_proxy@127.0.0.1:8080/git/" + repository)):
        repo, env, result = run_hook("copy-" + form, origin)
        run_hook_again = subprocess.run(["bash", str(HOOK)], cwd=repo.path, env=env,
                                        capture_output=True, text=True, timeout=120)
        base = repo.head()
        commit = subprocess.run(["git", "signoff", "--quiet", "--allow-empty", "--no-verify",
                                 "-m", "A session's change"], cwd=repo.path, env=env,
                                capture_output=True, text=True)
        problem = None
        if result.returncode != 0 or run_hook_again.returncode != 0:
            problem = "the hook exited non-zero: %s" % (result.stderr or run_hook_again.stderr)
        elif commit.returncode != 0:
            problem = "git signoff failed: %s" % commit.stderr.strip()
        elif repo.run("log", "-1", "--format=%an <%ae>") != identity(AGENT) \
                or repo.sign_offs() != identity(MAINTAINER):
            problem = "the commit is not authored by the agent and signed off by the maintainer"
        elif run_script([base, repo.head()], repo).returncode != 0:
            problem = "the check refuses the commit the alias makes"
        record("a commit made with the hook's alias passes the check, origin over %s, run twice"
               % form, problem)

    # The owner has to be the segment right after the host: the organisation's name further along a
    # URL is somebody else's path, whatever it spells.
    for name, origin in (
            ("fork", "https://github.com/somebody-else/ai-docker-stack-ansible-deployment"),
            ("owner not first, https", "https://github.com/somebody-else/" + repository),
            ("owner not first, ssh", "git@github.com:somebody-else/%s.git" % repository),
            ("no-origin", None)):
        repo, env, result = run_hook(name, origin)
        configured = git(["config", "--local", "--get-regexp", r"^(alias\.signoff|user\.)"],
                         repo.path, env).stdout
        problem = None
        if configured:
            problem = "the hook configured a copy that is not the maintainer's: %s" % configured
        elif "sign your own work" not in result.stdout:
            problem = "the hook did not tell the session to sign its own work"
        record("a copy that is not the maintainer's is given no identity (%s)" % name, problem)

    return results


def run_selftest():
    """Prove that the check refuses what it claims to refuse, and lets the rest through."""
    failures = 0

    def report(purpose, problem):
        nonlocal failures
        if problem is None:
            print("selftest: ok -- %s" % purpose)
        else:
            failures += 1
            print("selftest: FAILED (%s) -- %s" % (purpose, problem))

    with tempfile.TemporaryDirectory(prefix="check_sign_off-") as directory:
        directory = Path(directory)
        for number, (purpose, builder, status, holds, lacks) in enumerate(selftest_cases()):
            case_directory = directory / ("case-%d" % number)
            case_directory.mkdir()
            try:
                repo = Repository(case_directory / "repository")
                arguments = builder(repo)
                if arguments is None:
                    arguments = (repo.base, repo.head())
                result = run_script(arguments, repo)
            except Exception as error:  # a broken premise is a failure of the case, not a crash
                report(purpose, "the case could not be built: %s" % error)
                continue
            output = result.stdout + result.stderr
            if result.returncode != status:
                report(purpose, "exit status %d, expected %d: %s"
                       % (result.returncode, status, output.strip()))
            elif [text for text in holds if text not in output]:
                report(purpose, "the output lacks %r: %s"
                       % ([text for text in holds if text not in output], output.strip()))
            elif [text for text in lacks if text in output]:
                report(purpose, "the output holds %r: %s"
                       % ([text for text in lacks if text in output], output.strip()))
            else:
                report(purpose, None)

        hook_directory = directory / "hook"
        hook_directory.mkdir()
        try:
            hook_results = hook_cases(hook_directory)
        except Exception as error:
            hook_results = [("the session-start hook could be run against a sandbox",
                             "it could not: %s" % error)]
        for purpose, problem in hook_results:
            report(purpose, problem)

    return 1 if failures else 0


def main(arguments):
    if arguments == ["--selftest"]:
        return run_selftest()
    if len(arguments) != 2:
        print("Usage: check_sign_off.py <base-sha> <head-sha>\n"
              "       check_sign_off.py --selftest", file=sys.stderr)
        return 2
    return check(*arguments)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
