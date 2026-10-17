Run a full local CI check: format verification, lint, and tests. Report a
single structured summary at the end.

Run each stage in order. Do not stop early on failure — run all stages and
collect all results.

Stage 1 — Format check (read-only, do not modify files):
- Python: `black --check .`, `isort --check .`
- Node: `npx prettier --check .`

Stage 2 — Lint:
- Python: `ruff check .` (or `flake8 .`), `mypy .` if configured
- Node: `npx eslint .`, `npx tsc --noEmit` if typescript present

Stage 3 — Tests:
- Python: `pytest`
- Node: `npm test`

Skip any tool that is not available — do not install anything. If
neither `pyproject.toml`/`setup.py` nor `package.json` is present,
report that no recognized toolchain was found instead of an empty
PASS — don't let "nothing to check" read as "nothing wrong."

Final report format:

```
CI Summary
──────────
format   PASS / FAIL   (files with formatting issues, if any)
lint     PASS / FAIL   (error count, if any)
tests    PASS / FAIL   (passed/failed/skipped counts)
──────────
Overall  PASS / FAIL
```

If any stage failed, list the individual failures below the summary table,
grouped by stage, compact (one line per issue where possible).
Write the full summary to `doc/ci-latest.md` so agents can reference
the current project health.
