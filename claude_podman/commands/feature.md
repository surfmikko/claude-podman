Drive a feature from spec to implemented, reviewed, and tested. Use
$ARGUMENTS as the feature name or `doc/<feature>.md` path.

1. If `doc/<feature>.md` doesn't exist yet, dispatch the `designer`
   agent to write it. Otherwise read it.
2. If the doc has no `## Tasks` section yet, dispatch the `tasks`
   agent to split it.
3. For each task still marked `[ ]`, in order:
   - Dispatch `coder` with the feature doc path and that task. It may
     come back `[x]` (done and verified) or `[~]` (implemented, needs
     host verification — the sandbox can't build/run that platform).
   - If it came back `[~]`: stop looping on this task. Report what
     coder needs verified on the host, then move on to the next task
     that doesn't depend on it — don't retry the same build hoping it
     works, and don't leave the user waiting on something only they
     can check.
   - If it came back `[x]`: dispatch `reviewer` on the resulting diff.
     If the task touched security-sensitive surface (auth, input
     handling, secrets, dependencies), also dispatch `security`. If
     it touched UI, also dispatch `ui-reviewer`. Then dispatch
     `tester`.
   - Only move to the next task once the current one is `[x]` with
     review/test findings resolved or acknowledged, or `[~]` reported.
4. Report a short summary: tasks completed and verified, tasks
   waiting on host verification (and what to check), any findings
   left open, and what's still unstarted.

Don't dispatch tasks that depend on an unchecked one out of order,
even if `tasks` listed them that way — re-check the doc's own
dependency notes first.
