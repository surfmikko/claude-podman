Run code formatters on the project. Detect the stack from project files and
run the appropriate tools in-place.

Detection order:
- `pyproject.toml` or `setup.py` present → Python project
  - Run `black .` if black is available, else skip with a note
  - Run `isort .` if isort is available, else skip with a note
- `package.json` present → Node project
  - Run `npx prettier --write .` if prettier is listed in dependencies,
    else skip with a note
- Both present → run both stacks

After running, report which formatters ran, which files were changed
(from their output), and any that were skipped with the reason why.
If neither stack is detected, say so explicitly rather than reporting
nothing. Do not install missing tools — only run what is already
available.
