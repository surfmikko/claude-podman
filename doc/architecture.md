# Architecture

## Lifecycle

`claude_podman` (host CLI) starts the Podman machine, builds the image
on first run, generates a per-session bearer token, creates the container,
copies the generated config in and starts it, then cleans up on exit.
The project directory is bind-mounted as `/project`; it is the only
mount.

## Auth

If `~/.cache/claude-podman/auth/token` is missing, the CLI runs
`claude setup-token` in a throwaway container and saves the resulting
token there. Every session injects it as `CLAUDE_CODE_OAUTH_TOKEN`.
`claude-podman --login` redoes the login to replace the token.

## Session config

Nothing is staged on the host. The CLI builds the MCP config
(`~/.claude.json`) and the container's `~/.claude` dir (settings,
memory, agents, commands, status line) in memory and streams them as
a tar into the created container with `podman cp -` before
`podman start`. Files are owned by the container's `claude` user
(uid 1000). Copying instead of bind-mounting avoids single-file mount
breakage when Claude replaces `.claude.json` by rename, and keeps the
MCP bearer token off the host disk.

## Host `venv/`

The bind mount also exposes the host's `venv/`, which has the wrong
OS/arch for the container. `claude_podman/sandbox-rules.md` is
injected into the session's global memory and tells Claude to use
`venv-claude/` instead.

## Image files (`rootfs/`)

`claude_podman/rootfs/` mirrors the container's filesystem root and is
copied in one layer (`COPY rootfs/ /`). Adding a file there needs no
Containerfile edit; it does need an image rebuild.

- `opt/statusline-footer`: the status line plugin, loaded with
  `--plugin-dir`.
- `opt/installer/<tool>`: per-session install scripts (no root,
  installs under `~/.local`). `sandbox-rules.md` tells Claude to run
  these for missing tools such as `mongod`.

## `mcp_podman` (opt-in, `--mcp-podman`)

MCP server on the host, reached via `host.containers.internal`. It
gives the sandboxed Claude a narrow, session-scoped set of tools:
`container_run`, `container_build`, `container_stop`,
`container_remove`, `container_logs`, `container_list`,
`container_exec`. Requests need the session's bearer token, and
containers/images are labeled with the session ID so a session can
only manage what it created.

## Images

Base image: `python:3-slim-trixie` plus tools, with `claude` installed
by the official script, running as the `claude` user. Other types
(`--type rust`, `--type python`) are
`claude_podman/images/<type>.Containerfile` layered on the base.

## Code search (`semble`)

Semble (local MCP server, tree-sitter chunks, static embeddings, BM25 +
vector) is installed in the base image with its model, using uv-managed
Python 3.13 (tree-sitter has no wheels for the newest Python). It is
registered as a stdio server in the session's Claude config. The index
is written to `/project/.claude-index/linux-<arch>/`, which is
gitignored and keyed by architecture so a project shared between
differently-built containers never mixes indexes. The host never runs
it. Research: `issue/local-code-search.md`.
