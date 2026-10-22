# claude-podman

Run Claude Code in a sandboxed Podman container. The container gets
read-write access to the project directory and nothing else.

## Setup

```sh
python3 -m venv venv
source venv/bin/activate
pip install .
claude-podman                  # run in the current directory
claude-podman ~/projects/myapp # run in a specific directory
```

The CLI starts the Podman machine and builds the container image on
first run; no separate build step is needed.

Requires macOS, Podman 4.1+ (`brew install podman`), Python 3.9+.
There is no `claude` on the host — it only runs inside the container,
so each sandboxed session logs in on its own by default (run
`claude /login` inside it the first time you use it). Run
`claude-podman --login` once to skip that for good: it runs
`claude setup-token` in a throwaway container and saves the resulting
token to `~/.cache/claude-podman/auth/token`, which every later
session injects as `CLAUDE_CODE_OAUTH_TOKEN`.

## Architecture

- `claude_podman` — host CLI that manages the container lifecycle
  (start Podman, generate a per-session bearer token, run the
  container, clean up on exit).
- `mcp_podman` — opt-in (`--mcp-podman`) MCP server on the host, reached via
  `host.containers.internal`, giving the sandboxed Claude a narrow,
  session-scoped set of Podman tools (`container_run`, `container_build`,
  `container_stop`, `container_remove`, `container_logs`,
  `container_list`, `container_exec`). Requests need the session's
  bearer token; containers/images are labeled with the session ID so
  a session can only manage what it created.
- Each run gets a throwaway `~/.cache/claude-podman/<project>-<session>/`
  directory holding the MCP config and the container's `.claude` dir —
  never the project directory, so it can't leak into the repo.
- The project directory is bind-mounted as `/project`; since that also
  exposes the host's `venv/` (wrong OS/arch for the container),
  `claude_podman/sandbox-rules.md` is injected into the session's
  global memory telling it to use `venv-claude/` instead.

## Python conventions

- Flat layout — package dirs at repo root, no `src/` wrapper.
- Virtualenv at `venv/`; use `venv/bin/python` and `venv/bin/pip`.
- PEP 8, 80-character line limit.
- Simple implementations over clever abstractions.
- No comments unless the WHY is non-obvious.
- Do not run tests unless explicitly asked.

## Container

Base image: `python:3-slim-trixie`, with Node 22 (via NodeSource),
git, make, ripgrep, and neovim (`$EDITOR`/`$VISUAL`) installed on top,
and `claude` itself installed via the official install script. Runs
as the `node` user.
For other project images prefer `debian:bookworm-slim` or an official
service image; avoid Alpine (musl libc compatibility risk).
