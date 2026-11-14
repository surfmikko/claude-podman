import argparse
import io
import json
import os
import secrets
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import types
import uuid
from pathlib import Path
from typing import Optional

from claude_podman import SESSION_LABEL_KEY, SESSION_IMAGE_PREFIX
from claude_podman.__version__ import __version__

IMAGE_BASE = "claude-podman"
DEFAULT_TYPE = "base"
_CACHE_ROOT = Path(
    os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
) / "claude-podman"
_PKG_DIR = Path(__file__).parent
_AGENTS_DIR = _PKG_DIR / "agents"
_COMMANDS_DIR = _PKG_DIR / "commands"
_IMAGES_DIR = _PKG_DIR / "images"
_SANDBOX_RULES = _PKG_DIR / "sandbox-rules.md"
_STATUSLINE = _PKG_DIR / "statusline.sh"
_AUTH_DIR = _CACHE_ROOT / "auth"
_TOKEN_FILE = _AUTH_DIR / "token"
# The container's `claude` user; owner of the files copied in.
_CONTAINER_UID = 1000
_CONTAINER_HOME = "/home/claude"

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


def _image_types() -> list[str]:
    return sorted(
        p.name.removesuffix(".Containerfile")
        for p in _IMAGES_DIR.glob("*.Containerfile")
    )


def _image_name(image_type: str) -> str:
    if image_type == DEFAULT_TYPE:
        return IMAGE_BASE
    return f"{IMAGE_BASE}-{image_type}"


def _image_exists(image_type: str) -> bool:
    r = subprocess.run(
        ["podman", "image", "exists", _image_name(image_type)],
        capture_output=True,
    )
    return r.returncode == 0


def _build(image_type: str, no_cache: bool = False) -> None:
    # Claude Code is installed in the base image, so every other type
    # builds on top of it and needs it present (or refreshed for
    # --update).
    if image_type != DEFAULT_TYPE and (
        no_cache or not _image_exists(DEFAULT_TYPE)
    ):
        _build(DEFAULT_TYPE, no_cache)
    cmd = [
        "podman", "build",
        "-t", _image_name(image_type),
        "-f", str(_IMAGES_DIR / f"{image_type}.Containerfile"),
        "--build-arg", f"BASE={IMAGE_BASE}",
    ]
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


def _claude_config(mcp: Optional[tuple[int, str]]) -> str:
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
        "mcpServers": {
            "semble": {"type": "stdio", "command": "semble", "args": []},
        },
    }
    if mcp:
        port, token = mcp
        config["mcpServers"]["podman"] = {
            "type": "http",
            "url": f"http://host.containers.internal:{port}/mcp",
            "headers": {"Authorization": f"Bearer {token}"},
        }
    return json.dumps(config, indent=2)


def _settings() -> str:
    settings = {
        "theme": "dark",
        "skipDangerousModePermissionPrompt": True,
        "autoCompactEnabled": False,
        "idleCompaction": False,
        "awaySummaryEnabled": False,
        "outputStyle": "Concise",
        "permissions": {"defaultMode": "dontAsk"},
        "worktree": {"baseRef": "fresh"},
        "dialogExpiry": "never",
        "pluginConfigs": {
            "cc-plugin-agents-md@builtin": {
                "options": {"instructionFiles": "claude-md-or-agents-md"},
            },
        },
        "editorMode": "normal",
        "preferredNotifChannel": "auto",
        "terminalProgressBarEnabled": False,
        "remoteControlAtStartup": False,
        "crossSessionInbound": "accept",
        "attribution": {"commit": "", "pr": ""},
    }
    return json.dumps(settings, indent=2)


# Relative path -> (content, mode) for files copied into the container.
_Files = dict[str, tuple[bytes, int]]


def _text(content: str, mode: int = 0o644) -> tuple[bytes, int]:
    return content.encode(), mode


def _file(path: Path) -> tuple[bytes, int]:
    return path.read_bytes(), path.stat().st_mode & 0o777


def _dir_files(src_dir: Path, dst_name: str) -> _Files:
    if not src_dir.is_dir():
        return {}
    return {
        f"{dst_name}/{src.name}": _file(src)
        for src in sorted(src_dir.glob("*.md"))
    }


def _home_tar(files: _Files) -> bytes:
    """Tar stream for `podman cp - <name>:/home/claude`."""
    buf = io.BytesIO()
    dirs: set[str] = set()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, (data, mode) in files.items():
            # Explicit entries, or implicit parents would be root-owned.
            for parent in reversed(list(Path(name).parents)[:-1]):
                if str(parent) not in dirs:
                    dirs.add(str(parent))
                    d = tarfile.TarInfo(str(parent))
                    d.type = tarfile.DIRTYPE
                    d.mode = 0o755
                    d.uid = d.gid = _CONTAINER_UID
                    tar.addfile(d)
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = mode
            info.uid = info.gid = _CONTAINER_UID
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _podman_checked(
    args: list[str], what: str, input: Optional[bytes] = None
) -> None:
    r = subprocess.run(["podman", *args], input=input)
    if r.returncode:
        sys.exit(f"error: {what} failed (exit {r.returncode})")


def _login(image: str) -> None:
    print(
        "Starting container for `claude setup-token` — follow the "
        "browser (or paste-code) prompts it prints, then copy the "
        "token it gives you at the end.",
        flush=True,
    )
    subprocess.run(
        ["podman", "run", "--rm", "-it", image, "claude", "setup-token"]
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


def _gitconfig(project_dir: Path) -> str:
    # Only the identity, written to a container-local file, rather than
    # mounting ~/.gitconfig, which would expose credential helpers and
    # other host config to the sandbox.
    lines: list[str] = []
    for key, field in (("user.name", "name"), ("user.email", "email")):
        try:
            r = subprocess.run(
                ["git", "config", "--get", key],
                cwd=project_dir,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return ""
        value = r.stdout.strip()
        if value:
            lines.append(f"\t{field} = {json.dumps(value)}")
    return "[user]\n" + "\n".join(lines) + "\n" if lines else ""


def _run(project_dir: Path, image: str, use_mcp: bool) -> None:
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

    name = f"claude-{session_id}"

    try:
        files: _Files = {
            ".claude.json": _text(_claude_config(mcp)),
            ".claude/settings.json": _text(_settings()),
            ".claude/CLAUDE.md": _text(_SANDBOX_RULES.read_text()),
            ".claude/statusline.sh": _file(_STATUSLINE),
            ".claude/project-name": _text(project_dir.name),
            **_dir_files(_AGENTS_DIR, ".claude/agents"),
            **_dir_files(_COMMANDS_DIR, ".claude/commands"),
        }
        if gitconfig := _gitconfig(project_dir):
            files[".gitconfig"] = _text(gitconfig)

        cmd = [
            "podman", "create", "--rm", "-it", "--name", name,
            "-v", f"{project_dir}:/project",
            "--workdir", "/project",
        ]
        if sys.platform == "linux":
            # Rootless Podman maps the container's claude user to a
            # subuid, so bind mounts owned by the host user would be
            # unreadable; SELinux would deny them as well.
            cmd += [
                "--userns=keep-id:uid=1000,gid=1000",
                "--security-opt", "label=disable",
            ]
        if mcp:
            cmd += ["--add-host=host.containers.internal:host-gateway"]

        oauth_token = _TOKEN_FILE.read_text().strip()
        # Via stdin, so the token isn't in the host process arguments.
        cmd += ["--env-file", "/dev/stdin"]

        cmd += [
            image, "claude", "--dangerously-skip-permissions",
            "--plugin-dir", "/opt/statusline-footer",
        ]

        _podman_checked(
            cmd[1:],
            "podman create",
            input=f"CLAUDE_CODE_OAUTH_TOKEN={oauth_token}\n".encode(),
        )
        _podman_checked(
            ["cp", "-", f"{name}:{_CONTAINER_HOME}"],
            "podman cp",
            input=_home_tar(files),
        )
        subprocess.run(["podman", "start", "-ai", name])
    finally:
        if mcp_proc:
            mcp_proc.terminate()
            mcp_log.unlink(missing_ok=True)
        subprocess.run(["podman", "rm", "-f", name], capture_output=True)
        _cleanup_session(session_id)


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
        "--type",
        choices=_image_types(),
        default=DEFAULT_TYPE,
        help="Container image type (default: %(default)s)",
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

    image_type = args.type
    image = _image_name(image_type)

    if args.build:
        _build(image_type)
        return

    if args.update:
        _build(image_type, no_cache=True)
        return

    if not _image_exists(image_type):
        _build(image_type)

    if args.login:
        _login(image)
        return

    if not _TOKEN_FILE.exists():
        _login(image)

    _run(project_dir, image, args.mcp_podman)
