Run linters and type checkers on the project. Detect the stack from project
files and run the appropriate tools.

Detection order:
- `pyproject.toml` or `setup.py` present → Python project
  - Run `ruff check .` if ruff is available
  - Run `flake8 .` if ruff is not available but flake8 is
  - Run `mypy .` if mypy is available and a `mypy.ini`, `[mypy]` section
    in `pyproject.toml`, or `py.typed` marker exists
- `package.json` present → Node project
  - Run `npx eslint .` if eslint is listed in dependencies
  - Run `npx tsc --noEmit` if typescript is listed in dependencies
- Both present → run both stacks

Collect all output. Report a structured summary:
- Which tools ran
- Pass / fail status per tool
- For failures: file, line, error code, and message (compact, one line each)
- Which tools were skipped and why

If neither stack is detected, say so explicitly rather than reporting
nothing. Do not install missing tools — only run what is already
available.
