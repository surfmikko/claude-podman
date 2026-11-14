# Environment

You always run inside a sandbox container, never on the host. `/project`
is the host's working directory, bind-mounted into the container (at a
different path on the host). Everything outside it is container-local
and disappears with the session. Sections below say whether a rule is
about the **sandbox** (where you run) or the **host** (where the user
runs the project's own tooling).

The sandbox is plain Linux: no GUI, Xcode/iOS, Max/Ableton, or
display/audio device (target-specific limits live in their own
instructions, e.g. the `android` command). Anything needing those
can't be verified here: see "Host verification" below.

# Sandbox rules (where you run)

## Files shared with the host

Host and sandbox differ in OS, arch and path, so never let both write
platform-specific content to the same location. That covers compiled
binaries, test executables, build output, caches, CMake/sdkconfig
state, toolchains and emulators, venvs, and anything with absolute
paths baked in. Only project files and cross-platform content
(sources, docs, portable downloads) are shared.

This holds whatever the tooling: Makefile variables, scripts or tool
defaults. Before running a build, setup or install step, check where it
writes (e.g. `$(CURDIR)/.esp`, `out/`, `build/`). If the location isn't
already separated per platform (e.g. keyed by `uname -sm`), redirect it
to `.claude-data/var/cache/` (or `/tmp` if it needn't persist), for example
`make BUILD=/tmp/build`, or fix the Makefile to key it per platform.

## Python virtualenv

The bind-mounted `/project/venv/` is the host's: wrong OS/arch, won't
run here. Never write to it. A venv is platform-specific, so any other
sandbox venv goes outside the shared tree: `.claude-data/opt/venv`
(created by `agent-test`; use it by default) or `/tmp/venv-claude` if
it's session-only. Treat it as disposable scratch: never commit it.

## Installing tools for yourself

Missing tools (databases, servers, CLIs) are installed per session by
helper scripts in `/opt/installer/`, one per tool (`mongodb`, ...).
When a task needs a tool that isn't installed, `ls` that directory and
run the matching script (`/opt/installer/<tool>`). The sandbox has no
sudo, so the scripts are the only way to install system tools. They
are idempotent and install under `~/.local`. Read a script's header
comment for usage. If none matches, say so instead of improvising an
install. Project packages (formatters, linters, test deps) go into the
sandbox venv with pip, or `node_modules`.

## Code search

The `semble` MCP server (`search`, `find_related`) is baked into the
image. For "where/how is X done" questions across the repo, call
`search` with `repo` set to `/project` before grepping or reading many
files; use `rg` for exact strings. The index lives in
`/project/.claude-index/` (gitignored) and refreshes itself when files
change.

# Host rules (what you write for the user's machine)

## Installing tools for host automation

Applies to Makefiles, scripts and docs the user runs on the host, not
to anything you run. Prefer installing tools inside the repo (a
project-local venv, `node_modules`, a downloaded toolchain under a
per-platform directory) over touching the system. If a tool really has
to be global on the host, install it with MacPorts (`port install
<name>`) and say so in the docs. Never use `/opt/installer/` for this.

# Both

## Docs and issues

`<repo>/doc/` is the documentation: specs, design, decisions, how
things work. `<repo>/issue/<issue name>.md` is the task list for one
piece of work. Don't put tasks in `doc/` or documentation in `issue/`.
Create either directory only when you have something to write there.

`doc/` stays high level: architecture, specs, decisions. Change it when
those change, not for every code change; bug fixes and other small
changes need only a commit message.

Issue files are committed. When an issue is done and verified, move
anything worth keeping (decisions, rejected alternatives, gotchas, how
it was verified) into `doc/` if it is architecture/spec level, else
into the commit message, then delete the issue file in the closing
commit. Git history keeps the rest.

Task marks in an issue file: `[ ]` not started, `[x]` done and
verified, `[~]` implemented but not verifiable here (see "Host
verification"). Only the agent doing the task sets `[x]`/`[~]`.

## Container data: `.claude-data/`

Everything transient or cached, shared between agents and sessions,
goes in `<repo>/.claude-data/`, never in `doc/` or `issue/`. It holds
a `.gitignore` containing `*`; create it on first use. It is
container-only: the host never writes here.

- `opt/venv/`: the sandbox Python virtualenv.
- `var/cache/`: platform-specific content (package download caches,
  build output).
- `var/report/`: CI summaries, exploration notes and review, security
  and UI findings. Name every file
  `<agent-or-command>-<topic>-<YYYYmmdd-HHMM>.md`.
- `var/log/`: raw command output, named the same way.

Review agents (`reviewer`, `security`, `ui-reviewer`) put the full
report in `var/report/` and turn each finding that needs action into a
task in a new `issue/<topic>-<agent>.md` (task list format as in
`tasks`), linking the report. Nothing needing action stays only in
`var/`.

## Running tests

Run tests only with `agent-test` (from the repo root), never `make
test`, `pytest` or `unittest` directly. It picks the first matching
harness (`make agent-test` / `make test`, then Python's
`pytest -svvv --sw tests`, which stops at the first failure and resumes
there next time), provisions the venv, runs the tests with a 5 minute
limit, and logs to `.claude-data/var/log/`. A Stop hook runs
`agent-test --full` (every test) when you finish after changing files;
if it fails you are sent back to fix it, so you need not run the full
suite yourself before finishing; run `agent-test` only to iterate on a
failure or verify a change. (A per-edit hook would run tests against
half-finished work, so the gate is at finish.) Exit 0 passed, 1
failed, 2 nothing to run or provisioning failed. A test that exceeds
the limit has failed (exit 1). Fix it only if your own change made it
slow or hang; otherwise stop and ask the user. Never raise the limit,
and never refactor tests beyond that without the user's approval. On
2: stop, do not retry; treat as unverifiable (below).

## Host verification

When something can't be verified in the sandbox (the limits above, or
`agent-test` exit 2): do what you can, then say explicitly what is left
for the host. In an issue file mark the task `[~]` with exactly what
to check on the host; with no task, say so in your report. Never mark
`[x]` for unverified work, and don't retry hoping it works.

## Python style defaults

Unless the project's own config/style says otherwise: PEP 8; type
hints on signatures; `pathlib` over `os.path`; f-strings; catch
specific exceptions, never bare `except:`; small, single-purpose
functions over clever abstractions; stdlib over a new dependency
unless there's a concrete reason not to; comments only for non-obvious
WHY, never WHAT.
