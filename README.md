# claude-podman

Run Claude Code in a sandboxed Podman container. The container gets
read-write access to the project directory you point it at, and
nothing else on your machine.

## Why

`claude --dangerously-skip-permissions` lets Claude run any command
without asking first. That's useful, but it means Claude can touch
anything your user account can touch. claude-podman puts that session
inside a container instead: it can read and write the project
directory, and manage a small set of throwaway Podman containers
through an MCP server, but it can't reach the rest of your filesystem
or credentials. It also doesn't inherit your host's Claude login:
there's no `claude` on the host at all, only inside the container.

By default each sandboxed session authenticates on its own and the
login is thrown away when it exits. Run `claude-podman --login` once
to skip that: it saves a long-lived token to disk and every future
session reuses it. That trades away some isolation — the saved token
is a standing credential a sandboxed session could exfiltrate — for
not having to log in every run.

## Requirements

- macOS
- [Podman](https://podman.io/) 4.1+ (`port install podman`)
- Python 3.10+

## Install

Install it into the project you want to sandbox, like any other
Python tool:

```sh
python3 -m venv venv
source venv/bin/activate
pip install .
```

## Usage

```sh
claude-podman                  # sandbox the current directory
claude-podman ~/projects/myapp # sandbox a specific directory
claude-podman --build          # force a rebuild of the container image
claude-podman --update         # rebuild without cache, to pull the latest Claude Code
claude-podman --login          # log in once, reused by every future session
```

The first run starts the Podman machine and builds the container
image if it isn't already built; later runs reuse both. Each run then
starts a fresh container, mounts the target directory at `/project`,
and launches `claude --dangerously-skip-permissions` inside it.

Claude Code itself is installed at image build time and isn't version
pinned, so it goes stale as new releases ship. `--build` reuses Podman's
layer cache, which usually just replays the old install step, so it
won't fetch a newer version — use `--update` periodically instead,
which rebuilds with `--no-cache` to force a fresh install.

Without `--login`, the container starts logged out — run
`claude /login` inside it, same as you would on a new machine; exiting
Claude tears the container (and that login) down, so the next run
starts logged out again. `claude-podman --login` avoids that: it runs
`claude setup-token` in a throwaway container, asks you to paste back
the token it prints, and saves it to
`~/.cache/claude-podman/auth/token`. Every later run injects that
token automatically, so you only log in once.

## How it works

Two packages:

- `claude_podman` — the host-side CLI that manages the container
  lifecycle.
- `mcp_podman` — an MCP server that runs on the host and gives the
  sandboxed Claude a narrow set of Podman operations (`container_run`,
  `container_build`, `container_stop`, `container_remove`,
  `container_logs`, `container_list`, `container_exec`), scoped to
  containers/images its own session created.

Each run starts the Podman machine if needed, starts the MCP server
with a per-session bearer token, and launches a container — mounting
only the project directory and a throwaway, per-session `.claude`
config directory under `~/.cache/claude-podman/` (never a host
`~/.claude`, since there isn't one). Exiting Claude tears the
container, the MCP server, and that session directory back down.

Because that `.claude` config is thrown away and rebuilt every run,
the CLI also pre-seeds it each time so you don't hit first-launch
prompts on every session: `settings.json` sets dark mode
(`"theme": "dark"`) and silences the extra confirmation dialog for
`--dangerously-skip-permissions` (`"skipDangerousModePermissionPrompt": true`);
`.claude.json` marks onboarding complete
(`"hasCompletedOnboarding": true`) and pre-trusts `/project`
(`"projects": {"/project": {"hasTrustDialogAccepted": true}}`) — safe
since that's always the container's fixed mount point, never the host
path.

So that `git commit` works inside the container, the CLI reads
`user.name` and `user.email` from the host's git config (as seen from
the project directory, so per-project overrides apply) and passes them
as `GIT_AUTHOR_*`/`GIT_COMMITTER_*` environment variables. The host's
`~/.gitconfig` itself is never mounted, so credential helpers and
other host git settings stay out of the sandbox.

claude-podman doesn't choose a model: the session starts on whatever
default Claude Code resolves for your account. Since the `.claude`
config is fresh every run, a model picked with `/model` is forgotten on
exit. The startup announcement (e.g. "Opus 5.5 is now your default
model…") is a generic notice and may not match the model the session
actually started on — run `/model` to see what's selected.

The one thing that *does* persist across sessions, if you've run
`claude-podman --login`, is `~/.cache/claude-podman/auth/token` — a
long-lived OAuth token injected into each container as
`CLAUDE_CODE_OAUTH_TOKEN`. When logging in, paste just the token
`claude setup-token` prints (pasting the whole
`export CLAUDE_CODE_OAUTH_TOKEN=...` convenience line it also prints
works too — the CLI strips that prefix for you).

## License

MIT. See [LICENSE](LICENSE).
