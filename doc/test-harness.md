# Test harness

## What

`agent-test` runs the project's tests inside the container. Agents run
tests only through it, never `pytest` or `make test` directly. It is one
script, `/opt/agent-test/agent-test`, on `PATH` (in the repo:
`claude_podman/rootfs/opt/agent-test/`).

## How it works

Run `agent-test [--full] [pytest args...]` from the repo root. It uses
the first harness that applies:

| Harness | Applies when | Provisioning | Test |
|---|---|---|---|
| make | Makefile has `agent-test` or `test` | `make venv VENV=...` if the Makefile has a `venv` target | `make agent-test`, else `make test` |
| python | a Python dependency file and `tests/` | see below | `pytest -svvv --sw tests` |
| rust (stub, untested) | `Cargo.toml` | `cargo fetch` | `cargo test` |

Each harness is a pair of functions in the script: one provisions, one
tests. Adding a language means adding the pair and a line in
`HARNESSES`.

Python provisioning follows the developer's `venv_install`:
`python -m venv`, `pip install --upgrade pip setuptools`, then
`pip install -e ".[dev,test]"` if there is a `pyproject.toml` (or
`setup.py` / `setup.cfg`), otherwise
`pip install --upgrade -r requirements.txt -r requirements_dev.txt`.
Last, `pip install pytest-reportlog`, which adds `--report-log=FILE`
(JSON lines, one per test event); pass it as an argument to try it. The
venv is `.claude-data/opt/venv`, never the host's `venv/`.

The Python harness runs pytest stepwise (`--sw`): it stops at the first
failing test, and the next run resumes at that test and skips the ones
that already passed (state in `.pytest_cache/`). This saves runtime and
output, and the agent concentrates on one failure until it is fixed.
Because tests that passed earlier are not rerun, a fix can break one of
them unnoticed. So before reporting "done", the agent runs
`agent-test --full`: every test, no early stop, and the stepwise state
is cleared. `--full` changes nothing for make and rust, which always
run everything.

The make harness runs `make venv` only if the target uses `$(VENV)`;
otherwise it stops, because the target would write the host's `venv/`.

Provisioning is skipped while the venv is newer than the dependency
files and the `agent-test` script itself. A lock makes parallel agents
in one checkout wait for each other instead of provisioning twice.
Tests run without the lock.

## Stop hook

`/opt/agent-test/agent-test-hook` is registered in the sandbox's
`settings.json` (`claude_podman/cli.py`) for the `SessionStart`, `Stop`,
`SubagentStart` and `SubagentStop` hook events. It controls when the
agent may finish, not the agent:

- `SessionStart` records a hash of the working tree (tracked changes plus
  untracked files, minus `IGNORED_GLOBS` in the hook (docs,
  issues, `.claude*`, `data/`, `tmp/`, `log/`, images and other media), so
  docs-only changes never trigger a run; a repo without git is skipped).
- `Stop` compares the tree with the last one it saw. If it changed, it
  runs `agent-test --full`. Failed tests (exit 1) block the stop and the
  output is sent back to the agent. The tree is remembered after every
  run, so the agent gets one block per change: stopping again without
  changing anything (to ask the user, say) is allowed.
- Provisioning failures (exit 2) show the user a message but never block.
  A project with nothing to run is silent. Passing is silent.
- The hook timeout is 15 minutes. Claude Code itself ends a turn after 8
  blocks in a row.
- Subagents: every subagent is held to the tests. `SubagentStart` records the baseline and `SubagentStop` works
  like `Stop`; the reason goes to the subagent. The main agent and each
  subagent have their own memory of the tree, so the main agent's `Stop`
  still catches changes a subagent left behind.
- Tested with simulated hook events and a scratch git repo. A real Claude
  Code session has not been tried.

## Rules

- Every command has a 5 minute limit (`AGENT_TEST_TIMEOUT`, seconds).
  A test that times out has failed, like any other failing test. The
  agent fixes it only if its own change caused the slowness; otherwise
  it stops and asks the user. Raising the limit or refactoring the test
  suite always needs the user's approval. The timeout message says so.
- Any command that exits non-zero ends the run. There are no fallbacks.
- Every line printed to the agent is cut to 200 characters (the log
  keeps the full text).
- A crash in the script is a failed run (Python exits 1 with the
  traceback).

| Exit | Meaning |
|---|---|
| 0 | passed |
| 1 | tests failed or timed out (the command's output is printed), or the script crashed |
| 2 | nothing to run, or provisioning failed (a provisioning command that times out counts) |

On 1 the agent fixes what its own change broke, nothing more. On 2 it
must stop, not retry, and report to the caller (the task is marked
`[~]`).

## Files

Everything is under `<repo>/.claude-data/` (it has a `.gitignore`
containing `*`):

```
opt/venv/                 Python virtualenv
opt/provision.lock        lock
var/log/agent-test-*.log  full output of each run; kept two days
```

## Out of scope

Node and other languages, running only tests for changed files,
format and lint, and integration tests (those run on the host).
