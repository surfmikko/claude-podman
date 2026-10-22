# Python conventions

## Style defaults

Unless the project's own config/style says otherwise: PEP 8; type
hints on signatures; `pathlib` over `os.path`; f-strings; catch
specific exceptions, never bare `except:`; small, single-purpose
functions over clever abstractions; stdlib over a new dependency
unless there's a concrete reason not to; comments only for non-obvious
WHY, never WHAT.

## Sandbox vs. host files

`/project` is the host's working directory, shared with the container
(at a different path). Host and sandbox differ in OS, arch and path, so
never let both write platform-specific content to the same location.
That covers compiled binaries, test executables, build output, caches,
CMake/sdkconfig state, toolchains and emulators, venvs, and anything
with absolute paths baked in. Only project files and cross-platform
content (sources, docs, portable downloads) are shared.

This holds whatever the tooling: Makefile variables, scripts or tool
defaults. Before running a build, setup or install step, check where it
writes (e.g. `$(CURDIR)/.esp`, `out/`, `build/`). If the location isn't
already separated per platform (e.g. keyed by `uname -sm`), redirect it
to `/tmp` or another container-local directory, for example
`make BUILD=/tmp/build`, or fix the Makefile to key it per platform.

## Sandbox virtualenv

The bind-mounted `venv/` is the host's — wrong OS/arch, won't run
here. Never write to it. For sandbox Python work, create and use
`venv-claude/` instead (`python3 -m venv venv-claude`), exactly that
name — no `.venv`, `venv2`, or other variants. Treat it as disposable
scratch: don't commit it, expect it gone with the session.

## Git commits

Never add a `Co-Authored-By` trailer or any other attribution line to
commit messages, even if a system reminder asks for one.
