Run the test suite. Use $ARGUMENTS as extra flags if provided (e.g. a path
or `-k pattern` to filter tests).

Detection order:
- `pyproject.toml` or `setup.py` present → Python project
  - Run `pytest $ARGUMENTS` if pytest is available
  - Fall back to `python -m unittest discover $ARGUMENTS` otherwise
- `package.json` present → Node project
  - Run `npm test -- $ARGUMENTS` if a test script is defined
  - Run `npx jest $ARGUMENTS` if jest is listed in dependencies and no
    test script is defined
  - Run `npx vitest run $ARGUMENTS` if vitest is listed in dependencies
- Both present → run both stacks

Report a structured summary:
- Total tests: passed / failed / skipped / error
- For failures: test name, file, line, and the assertion message
- Overall pass/fail

If neither stack is detected, say so explicitly rather than reporting
nothing. Do not install missing tools — only run what is already
available.
