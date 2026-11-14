# Environment

You always run inside a sandbox container, never on the host. `/project`
is the host's working directory, bind-mounted into the container (at a
different path on the host). Everything outside it is container-local
and disappears with the session. Sections below say whether a rule is
about the **sandbox** (where you run) or the **host** (where the user
runs the project's own tooling).

The sandbox is plain Linux: no GUI, Xcode/iOS, Android beyond a CLI
Gradle build, Max/Ableton, or display/audio device. Anything needing
those can't be verified here: do what you can, and say explicitly what
is left for host verification.

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
to `.claude-tmp/cache/` (or `/tmp` if it needn't persist), for example
`make BUILD=/tmp/build`, or fix the Makefile to key it per platform.

## Python virtualenv

The bind-mounted `venv/` is the host's: wrong OS/arch, won't run here.
Never write to it. For sandbox Python work, create and use
`venv-claude`: at `.claude-tmp/cache/venv-claude` if it should be
shared between sessions, or `/tmp/venv-claude` if it's session-only.
No `.venv`, `venv2`, or other variants, and none at the repo root.
Treat it as disposable scratch: never commit it.

## Installing tools for yourself

Missing tools (databases, servers, CLIs) are installed per session by
helper scripts in `/opt/installer/`, one per tool (`mongodb`, ...).
When a task needs a tool that isn't installed, `ls` that directory and
run the matching script (`/opt/installer/<tool>`) instead of using sudo
or apt. Scripts are idempotent and install under `~/.local`. Read a
script's header comment for usage. If none matches, say so instead of
improvising an install.

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

Issue files are committed. When an issue is done and verified, move
anything worth keeping (decisions, rejected alternatives, gotchas, how
it was verified) into `doc/` or the commit message, then delete the
issue file in the closing commit. Git history keeps the rest.

## Temporary files: `.claude-tmp/`

Everything transient or cached, shared between agents and sessions,
goes in `<repo>/.claude-tmp/`, never in `doc/` or `issue/`. On first use
create it with a `.gitignore` containing `*`; cleanup is
`git clean -fdx .claude-tmp`.

- `cache/`: container-only, platform-specific content (package download
  caches, virtualenvs, build output). The host never writes here. Key
  shared installs by a lockfile hash, and build them in a temp directory
  then rename atomically so parallel sessions can't corrupt each other.
- `report/`: CI summaries and review, security and UI findings. Name
  files `<agent-or-command>-<topic>.md` (add a timestamp if the name
  could recur) so parallel agents never write the same file. Findings
  that need action get added by the caller to the relevant `issue/`
  file.
- `log/`: raw command output (build, test, install logs), named the same
  way, so reports can point to them instead of pasting them.

`agent-test` prunes `.claude-tmp/` on each run: old logs and reports,
and anything in `cache/` unused for a week. Don't clean it by hand, and write
only under the names above so pruning can find your files.

## Python style defaults

Unless the project's own config/style says otherwise: PEP 8; type
hints on signatures; `pathlib` over `os.path`; f-strings; catch
specific exceptions, never bare `except:`; small, single-purpose
functions over clever abstractions; stdlib over a new dependency
unless there's a concrete reason not to; comments only for non-obvious
WHY, never WHAT.
