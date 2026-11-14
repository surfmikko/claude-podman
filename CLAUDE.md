# claude-podman

Run Claude Code in a sandboxed Podman container with read-write access
to the project directory and nothing else. There is no `claude` on the
host; it only runs inside the container. Lifecycle, auth, session
directory, image files and the MCP server are described in
`doc/architecture.md`; read it before changing those areas.

## Python conventions

- Python 3.9+ for the host CLI; `mcp_podman` needs 3.10+.
- Flat layout: package dirs at repo root, no `src/` wrapper.
- Host virtualenv at `venv/`; on the host use `venv/bin/python` and
  `venv/bin/pip`. In the container use `.claude-data/opt/venv` (created by
  `agent-test`) instead.
- 80-character line limit.
- Do not run tests unless explicitly asked. When asked, run them only
  through `agent-test` (see `doc/test-harness.md`).

## Images

- Adding `claude_podman/images/<type>.Containerfile` adds an image type.
- For other project images prefer `debian:bookworm-slim` or an official
  service image; avoid Alpine (musl libc compatibility risk).
