# Worktrees

Two uses, one mechanism:

1. **In-session**: the main Claude in a container creates worktrees
   for its subagents (Claude Code's own worktree feature), each
   subagent commits to its branch, the main session merges.
2. **Per-instance**: `claude-podman --worktree <branch>` starts a
   container whose workdir is its own worktree. Several such instances
   (planners, coders) can run side by side, and work and state persist
   in git across daily session resets.

Orchestrating many instances is out of scope here; see "Later".

## The path problem

A worktree's `.git` file and `.git/worktrees/<n>/gitdir` hold absolute
paths. The host sees `/home/u/scratch/project/...`, the container sees
`/project/...`, so one side always breaks. `git worktree repair` on one
side only moves the breakage to the other.

## Decision: relative worktree paths

Git >= 2.48 can store relative links (`worktree.useRelativePaths`).
They resolve identically on host and container provided the layout
under the project root is the same on both sides.

- Worktrees live at `.claude/worktrees/<name>/` (gitignored).
- The launcher sets `git config worktree.useRelativePaths true` in the
  repo before anything creates a worktree, and runs
  `git worktree repair --relative-paths` to convert existing ones.
  Without the config, a worktree created in the container gets
  `/project/...` links and breaks on the host.
- Requires git >= 2.48 on the host (MacPorts) and in the image. The
  base image is trixie with git 2.47.3, so it needs a newer git
  (backports or a pinned build). The launcher checks the host version
  and fails with a clear message.
- Rejected: mounting the project at its host path inside the container
  (works with any git, but breaks the fixed `/project` convention used
  by trust config and sandbox rules).

## `--worktree <branch>`

Host launcher steps:

1. Ensure the config above.
2. If `.claude/worktrees/<name>/` is missing, `git worktree add` it:
   new branch from the current branch, or the existing branch if it
   already exists. `<name>` is the branch name with `/` replaced by `-`.
3. Start the container as today (whole project at `/project`) with
   `--workdir /project/.claude/worktrees/<name>`. Claude is started
   with that cwd (no directory argument exists), so the trust entry in
   the generated config covers the worktree path as well as `/project`.
4. On exit nothing is removed; the worktree and branch are the state.
   Removal is explicit (`git worktree remove`).

Without `--worktree` nothing changes except that in-session worktrees
(use 1) work through the same relative-path config.

The whole project is mounted rather than only the worktree and `.git`:
it is the existing mount, so the launcher needs no new mount logic, and
use 1 needs the whole tree anyway. A narrower layout (only `.git` and
the one worktree, at matching paths under `/project`) is a possible
later hardening.

## Session reset and persistence

State lives only in git (branches, commits) and files in the worktree
(`doc/`, `issue/`), as the project rules already require. A fresh
session started on the same branch continues from the task files and
commit log. No status directory, JSON or database.

## Risks

- `.git` is rw, so an instance can plant `.git/hooks/*` or change
  `.git/config` (`core.hooksPath`, `core.fsmonitor`), which run on the
  host at the next git use. Already true today; only a per-instance
  clone that the host fetches from removes it.
- Claude Code walks up from the cwd, so a worktree session also loads
  `/project/CLAUDE.md` from the main checkout (possibly a different
  branch's version).
- The instance can reach the main checkout and sibling worktrees.
- `.claude/worktrees/` must be gitignored (or in `.git/info/exclude`),
  or the main checkout lists the worktrees as untracked.
- Per-worktree `.claude-data/` and `venv*/` are separate by
  construction; nothing is shared.
- Two instances on the same branch are refused by git.
- Old git on either side fails with an unhelpful error once the
  `relativeWorktrees` extension is set; hence the version check.

## Later: orchestration

Multi-session orchestration (planner/coder instances, task DAG with
`depends:` front matter, a plain-code scheduler on the host, review
gate before merging into an integration branch, label-scoped
containers) builds on `--worktree` and is designed separately, possibly
per project. Principles kept from the earlier draft: the scheduler is
plain code rather than an LLM, humans approve merges, and state is
derived from git so the scheduler can be killed and rebuilt.
