Drive a feature from spec to implemented. Use $ARGUMENTS as the
feature name, or a `doc/<feature>.md` or `issue/<feature>.md` path. The
spec lives in `doc/<feature>.md`, the task list in
`issue/<feature>.md`.

1. Interview the user (you, the main agent, not a subagent) about the
   feature: ask one question at a time until intent, scope, behavior
   and edge cases are unambiguous. Skip what an existing spec already
   answers.
2. Write or update `doc/<feature>.md` (dispatch `designer` if useful),
   then `issue/<feature>.md` (dispatch `tasks`). Show both to the user
   and wait for approval before implementing.
3. For each task still marked `[ ]`, in order, dispatch `coder` with
   the issue file path and that task, one task per dispatch. It comes
   back `[x]` (done and verified) or `[~]` (needs host verification).
   Don't start a task that depends on an unfinished one; re-check the
   issue file's dependency notes. On `[~]`, note what the user must
   check and continue with tasks that don't depend on it.
4. Present the result to the user for approval: what changed per task,
   what waits on host verification, anything coder reported as blocked.
   Reviews are not part of this flow; the user can run `reviewer`,
   `security`, `ui-reviewer` or `tester` afterwards, and those open
   their own `issue/` files.
5. After approval, if every task is `[x]`, fold what is worth keeping
   into `doc/<feature>.md` (architecture/spec level) or the commit
   message and delete the issue file in the closing commit. Skip this
   while any task is `[~]` or open.
