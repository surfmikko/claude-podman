# Python conventions

## Style defaults

Unless the project's own config/style says otherwise: PEP 8; type
hints on signatures; `pathlib` over `os.path`; f-strings; catch
specific exceptions, never bare `except:`; small, single-purpose
functions over clever abstractions; stdlib over a new dependency
unless there's a concrete reason not to; comments only for non-obvious
WHY, never WHAT.

## Sandbox virtualenv

The bind-mounted `venv/` is the host's — wrong OS/arch, won't run
here. Never write to it. For sandbox Python work, create and use
`venv-claude/` instead (`python3 -m venv venv-claude`), exactly that
name — no `.venv`, `venv2`, or other variants. Treat it as disposable
scratch: don't commit it, expect it gone with the session.
