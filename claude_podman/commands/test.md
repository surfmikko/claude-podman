Run the test suite with the harness: `agent-test $ARGUMENTS` from the repo
root. Never run `pytest`, `make test` or `unittest` directly.

`agent-test` uses the first matching harness (`make agent-test` /
`make test`, then Python's `pytest -svvv --sw tests`), sets up its venv,
and runs it under a 5 minute limit. The Python harness stops at the
first failure and resumes there next time; `--full` runs every test; a Stop hook
does that when the agent finishes. Other $ARGUMENTS reach the Python harness
only.

Exit codes: 0 passed, 1 failed (the failing command's output and the
log path are printed), 2 nothing to run or provisioning failed. A test
that exceeds the time limit has failed (exit 1). Fix it only if your own
change made it slow or hang; otherwise stop and ask the user. Do not
raise the limit, and do not refactor tests without the user's
approval. On 2, stop: do not retry; report to the caller.

Report: overall pass/fail, and for failures the test name, file, line
and assertion message (the full output is in the printed log path).
