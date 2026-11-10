# claude-podman

Run Claude Code in a sandboxed Podman container. It gets read-write
access to the project directory you point it at, and nothing else on
your machine: no host `~/.claude`, no host login, no `claude` on the
host at all. With `--mcp-podman` it can also manage a few throwaway
Podman containers.

The one standing credential is the long-lived token saved on first run
(see [Login](#login)); a sandboxed session could exfiltrate it.

## Requirements

- macOS or Linux
- [Podman](https://podman.io/) 4.1+ (`brew install podman` or
  `port install podman` on macOS)
- Python 3.9+ (3.10+ and `pip install ".[mcp]"` for `--mcp-podman`)

## Install

```sh
python3 -m venv venv
source venv/bin/activate
pip install .
```

## Usage

```sh
claude-podman                      # sandbox the current directory
claude-podman ~/projects/myapp     # sandbox a specific directory
claude-podman --type rust          # image type: base (default), python, rust
claude-podman --mcp-podman         # also give Claude session-scoped Podman tools
claude-podman --build              # rebuild the image (uses layer cache)
claude-podman --update             # rebuild without cache to get the latest Claude Code
claude-podman --login              # log in again and replace the saved token
```

The first run starts the Podman machine and builds the image; later
runs reuse both. Each run starts a fresh container with the project
mounted at `/project` and launches `claude --dangerously-skip-permissions`.
Exiting Claude removes the container and the session's temporary
config.

### Image types

Types live in `claude_podman/images/<type>.Containerfile` and build on
the `base` image. `python` adds a C toolchain and linters, `rust` adds
the Rust toolchain with Cargo output kept inside the container. Each
is built on first use as `claude-podman-<type>`. Adding a Containerfile
adds a type.

Claude Code is installed at build time and not version-pinned.
`--build` replays Podman's layer cache and so keeps the old version;
use `--update` periodically to pull a newer one.

### Tools the image doesn't have

Install scripts in `claude_podman/rootfs/opt/installer/` are copied
into the image at `/opt/installer/`, and the session's instructions
tell Claude to run them when a task needs a missing tool. They install
per session under `~/.local`, need no root, and vanish with the
container. Currently there is `mongodb` (`mongod` 8.0 by default, or
`mongodb 7.0` for another series), which is what libraries like
mongobox need. To add a tool, drop an executable script in that
directory and rebuild the image.

For services that run as separate containers (databases, queues), use
`--mcp-podman` and let Claude start an official image instead.

### Login

Nothing to do on the first run: when `~/.cache/claude-podman/auth/token`
is missing, claude-podman runs `claude setup-token` in a throwaway
container, asks you to paste the token it prints, and saves it. Every
later run injects it as `CLAUDE_CODE_OAUTH_TOKEN`. Use
`claude-podman --login` only to replace the saved token. You can paste
just the token or the whole `export CLAUDE_CODE_OAUTH_TOKEN=...` line.

## What a session gets

- **Mounts:** the project directory at `/project`, and a throwaway
  `.claude` directory under `~/.cache/claude-podman/`. Nothing else
  from the host.
- **Preset config:** the throwaway config is rebuilt every run, so the
  CLI seeds it to skip first-launch prompts: dark theme, onboarding
  done, `/project` pre-trusted, no dangerous-mode confirmation, no
  auto-compaction, `Concise` output style, and the status line footer
  plugin.
- **Agents and commands:** the subagents and slash commands in
  `claude_podman/agents` and `claude_podman/commands` are copied in
  (`/feature`, `/test`, `/lint`, ...).
- **`doc/`:** created in the project if missing, as a shared
  workspace for agents and you.
- **Sandbox rules:** `claude_podman/sandbox-rules.md` becomes the
  session's global memory. It covers the host/container file split,
  the `venv-claude/` virtualenv and the installer scripts.
- **Git identity:** `user.name` and `user.email` from the host's git
  config (per-project overrides apply) are passed as
  `GIT_AUTHOR_*`/`GIT_COMMITTER_*`. The host's `~/.gitconfig` is never
  mounted.
- **Model:** none is chosen. The session starts on your account's
  default, and a model picked with `/model` is forgotten on exit.

## How it works

`claude_podman` is the host CLI that manages the container lifecycle.
`mcp_podman` is an opt-in MCP server on the host that gives the
sandboxed Claude a narrow, session-scoped set of Podman tools. See
[doc/architecture.md](doc/architecture.md) for details.

## License

MIT. See [LICENSE](LICENSE).
