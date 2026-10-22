import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import types
import uuid
from pathlib import Path
from typing import Optional

from claude_podman import SESSION_LABEL_KEY, SESSION_IMAGE_PREFIX
from claude_podman.__version__ import __version__

IMAGE_NAME = "claude-podman"
_CACHE_ROOT = Path(
    os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
) / "claude-podman"
_PKG_DIR = Path(__file__).parent
_AGENTS_DIR = _PKG_DIR / "agents"
_COMMANDS_DIR = _PKG_DIR / "commands"
_SANDBOX_RULES = _PKG_DIR / "sandbox-rules.md"
_AUTH_DIR = _CACHE_ROOT / "auth"
_TOKEN_FILE = _AUTH_DIR / "token"

_DOC_README = """\
# doc/

Shared workspace between agents and the developer: one markdown file
per feature, decision, or finding worth keeping (e.g. `doc/login.md`,
`doc/rate-limiting.md`).

Agents read this directory for context before starting work and write
their findings and decisions here. You can add files directly — agents
will pick them up on their next run.
"""


def _wait_for_podman_ready(timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = subprocess.run(
                ["podman", "info"], capture_output=True, timeout=10
            )
        except subprocess.TimeoutExpired:
            r = types.SimpleNamespace(returncode=1)
        if r.returncode == 0:
            return True
        time.sleep(1)
    return False


def _ensure_podman() -> None:
    try:
        r = subprocess.run(
            ["podman", "info"], capture_output=True, timeout=10
        )
    except FileNotFoundError:
        sys.exit("error: podman not found — install Podman 4.1+")
    except subprocess.TimeoutExpired:
        r = types.SimpleNamespace(returncode=1)
    if r.returncode == 0:
        return

    r = subprocess.run(
        ["podman", "machine", "list", "--format", "json"],
        capture_output=True, text=True,
    )
    machines = (
        json.loads(r.stdout)
        if r.returncode == 0 and r.stdout.strip()
        else []
    )

    if not machines:
        print("Initializing Podman machine...", flush=True)
        subprocess.run(["podman", "machine", "init"], check=True)
        subprocess.run(["podman", "machine", "start"], check=True)
    else:
        # "Default" marks the machine `podman machine start` (no name)
        # would target; fall back to the first entry if none is
        # marked, which matches Podman's own behavior.
        default = next(
            (m for m in machines if m.get("Default")), machines[0]
        )
        if default.get("Running", False):
            return
        name = default.get("Name", "podman-machine-default")
        print(f"Starting Podman machine '{name}'...", flush=True)
        subprocess.run(["podman", "machine", "start", name], check=True)

    if not _wait_for_podman_ready():
        sys.exit("error: Podman machine did not become ready in time")


def _image_exists() -> bool:
    r = subprocess.run(
        ["podman", "image", "exists", IMAGE_NAME],
        capture_output=True,
    )
    return r.returncode == 0


def _build(no_cache: bool = False) -> None:
    cmd = ["podman", "build", "-t", IMAGE_NAME]
    if no_cache:
        cmd.append("--no-cache")
    cmd.append(str(_PKG_DIR))
    subprocess.run(cmd, check=True)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _cleanup_session(session_id: str):
    subprocess.run(
        [
            "podman", "rm", "-f",
            "--filter",
            f"label={SESSION_LABEL_KEY}={session_id}",
        ],
        capture_output=True,
    )
    r = subprocess.run(
        [
            "podman", "images",
            "--filter", f"reference={SESSION_IMAGE_PREFIX}{session_id}*",
            "--format", "{{.ID}}",
        ],
        capture_output=True, text=True,
    )
    ids = r.stdout.split()
    if ids:
        subprocess.run(
            ["podman", "rmi", "-f", *ids], capture_output=True
        )


def _start_mcp_server(
    session_id: str, port: int, project_dir: Path, token: str
) -> tuple[subprocess.Popen, Path]:
    env = {
        **os.environ,
        "CLAUDE_PODMAN_SESSION": session_id,
        "CLAUDE_PODMAN_PROJECT_DIR": str(project_dir),
        "CLAUDE_PODMAN_TOKEN": token,
        "MCP_PORT": str(port),
        "MCP_HOST": "0.0.0.0",
    }
    fd, log_path = tempfile.mkstemp(prefix="claude-podman-mcp-")
    log = os.fdopen(fd, "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "mcp_podman.server"],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log.close()
    return proc, Path(log_path)


def _write_claude_config(
    mcp: Optional[tuple[int, str]], path: Path
) -> None:
    config = {
        # Skips the first-launch wizard (theme picker, trust dialog,
        # login screen), which otherwise runs unconditionally whenever
        # this is unset/false, regardless of settings.json/projects
        # below or a CLAUDE_CODE_OAUTH_TOKEN already being valid.
        "hasCompletedOnboarding": True,
        # "/project" is the fixed mount point inside the container
        # (see _run), not the host path — always safe to pre-trust.
        "projects": {
            "/project": {"hasTrustDialogAccepted": True},
        },
    }
    if mcp:
        port, token = mcp
        config["mcpServers"] = {
            "podman": {
                "type": "http",
                "url": f"http://host.containers.internal:{port}/mcp",
                "headers": {"Authorization": f"Bearer {token}"},
            },
        }
    path.write_text(json.dumps(config, indent=2))


def _write_settings(session_claude: Path) -> None:
    settings = {
        "theme": "dark",
        "skipDangerousModePermissionPrompt": True,
    }
    (session_claude / "settings.json").write_text(
        json.dumps(settings, indent=2)
    )


def _init_doc_dir(project_dir: Path) -> None:
    doc = project_dir / "doc"
    if doc.exists():
        return
    doc.mkdir()
    (doc / "README.md").write_text(_DOC_README)


def _inject_dir(src_dir: Path, dst_parent: Path) -> None:
    if not src_dir.is_dir():
        return
    dst = dst_parent / src_dir.name
    dst.mkdir(exist_ok=True)
    for src in src_dir.glob("*.md"):
        target = dst / src.name
        if not target.exists():
            shutil.copy2(src, target)


def _inject_global_memory(session_claude: Path) -> None:
    # session_claude is a freshly created directory (see _run), so
    # CLAUDE.md can never already exist here — no merge needed.
    rules = _SANDBOX_RULES.read_text()
    (session_claude / "CLAUDE.md").write_text(rules)


def _login() -> None:
    print(
        "Starting container for `claude setup-token` — follow the "
        "browser (or paste-code) prompts it prints, then copy the "
        "token it gives you at the end.",
        flush=True,
    )
    subprocess.run(
        ["podman", "run", "--rm", "-it", IMAGE_NAME, "claude", "setup-token"]
    )
    token = input("Paste the token here: ").strip().strip("'\"")
    # `claude setup-token` also prints a ready-to-run
    # `export CLAUDE_CODE_OAUTH_TOKEN=...` line — accept that pasted
    # verbatim too, not just the bare token.
    name, _, value = token.partition("=")
    if name.strip().endswith("CLAUDE_CODE_OAUTH_TOKEN") and value:
        token = value.strip().strip("'\"")
    if not token:
        sys.exit("error: no token entered, nothing saved")
    _AUTH_DIR.mkdir(parents=True, exist_ok=True)
    _TOKEN_FILE.write_text(token)
    _TOKEN_FILE.chmod(0o600)
    print(
        f"Token saved to {_TOKEN_FILE} — "
        "future sessions log in automatically."
    )


def _git_identity_env(project_dir: Path) -> list[str]:
    # Env vars rather than mounting ~/.gitconfig, which would expose
    # credential helpers and other host config to the sandbox.
    args: list[str] = []
    for key, var in (("user.name", "NAME"), ("user.email", "EMAIL")):
        try:
            r = subprocess.run(
                ["git", "config", "--get", key],
                cwd=project_dir,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return []
        value = r.stdout.strip()
        if value:
            args += [
                "-e", f"GIT_AUTHOR_{var}={value}",
                "-e", f"GIT_COMMITTER_{var}={value}",
            ]
    return args


def _run(project_dir: Path, use_mcp: bool) -> None:
    session_id = uuid.uuid4().hex
    mcp_proc = None
    mcp_log = None
    mcp = None

    if use_mcp:
        try:
            import mcp  # noqa: F401
        except ImportError:
            sys.exit(
                "error: --mcp-podman needs the MCP dependencies "
                "(Python 3.10+): pip install '.[mcp]'"
            )
        port = _free_port()
        token = secrets.token_hex(32)
        print(f"Starting MCP server on port {port}...", flush=True)
        mcp_proc, mcp_log = _start_mcp_server(
            session_id, port, project_dir, token
        )

        if not _wait_for_port(port):
            mcp_proc.terminate()
            output = mcp_log.read_text(errors="replace").strip()
            mcp_log.unlink(missing_ok=True)
            if output:
                print(output, file=sys.stderr)
            sys.exit("error: MCP server did not start in time")
        mcp = (port, token)

    _CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    session_dir = _CACHE_ROOT / f"{project_dir.name}-{session_id}"

    try:
        session_dir.mkdir()
        config_file = session_dir / "claude.json"
        _write_claude_config(mcp, config_file)

        session_claude = session_dir / "claude"
        session_claude.mkdir()

        _init_doc_dir(project_dir)
        _inject_dir(_AGENTS_DIR, session_claude)
        _inject_dir(_COMMANDS_DIR, session_claude)
        _inject_global_memory(session_claude)
        _write_settings(session_claude)

        cmd = [
            "podman", "run", "--rm", "-it",
            "-v", f"{project_dir}:/project",
            "-v", f"{session_claude}:/home/node/.claude",
            "-v", f"{config_file}:/home/node/.claude.json",
            "--workdir", "/project",
        ]
        if sys.platform == "linux":
            # Rootless Podman maps the container's node user to a
            # subuid, so bind mounts owned by the host user would be
            # unreadable; SELinux would deny them as well.
            cmd += [
                "--userns=keep-id:uid=1000,gid=1000",
                "--security-opt", "label=disable",
            ]
        if mcp:
            cmd += ["--add-host=host.containers.internal:host-gateway"]
        cmd += _git_identity_env(project_dir)

        oauth_token = _TOKEN_FILE.read_text().strip()
        cmd += ["-e", f"CLAUDE_CODE_OAUTH_TOKEN={oauth_token}"]

        cmd += [IMAGE_NAME, "claude", "--dangerously-skip-permissions"]

        subprocess.run(cmd)
    finally:
        if mcp_proc:
            mcp_proc.terminate()
            mcp_log.unlink(missing_ok=True)
        _cleanup_session(session_id)
        shutil.rmtree(session_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(
        description="Run Claude Code in a sandboxed Podman container",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "project_dir",
        nargs="?",
        default=".",
        help="Project directory to mount (default: .)",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Force rebuild the container image",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help=(
            "Rebuild the container image without cache, to pull the "
            "latest Claude Code version"
        ),
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help=(
            "Log in once via `claude setup-token` and save the token for "
            "all future sessions"
        ),
    )
    parser.add_argument(
        "--mcp-podman",
        action="store_true",
        help=(
            "Start the Podman MCP server and give the sandboxed Claude "
            "its session-scoped container tools (disabled by default)"
        ),
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        sys.exit(f"error: {project_dir} is not a directory")

    _ensure_podman()

    if args.build:
        _build()
        return

    if args.update:
        _build(no_cache=True)
        return

    if not _image_exists():
        _build()

    if args.login:
        _login()
        return

    if not _TOKEN_FILE.exists():
        _login()

    _run(project_dir, args.mcp_podman)
