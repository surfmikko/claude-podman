import hmac
import os
import subprocess
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from claude_podman import SESSION_LABEL_KEY, session_image_repo

SESSION_ID = os.environ.get("CLAUDE_PODMAN_SESSION", "")
if not SESSION_ID:
    raise RuntimeError(
        "CLAUDE_PODMAN_SESSION must be set before starting the MCP server"
    )
_SESSION_LABEL = f"{SESSION_LABEL_KEY}={SESSION_ID}"

TOKEN = os.environ.get("CLAUDE_PODMAN_TOKEN", "")
if not TOKEN:
    raise RuntimeError(
        "CLAUDE_PODMAN_TOKEN must be set before starting the MCP server"
    )
_EXPECTED_AUTH = f"Bearer {TOKEN}".encode()

_PROJECT_DIR = os.environ.get("CLAUDE_PODMAN_PROJECT_DIR", "")
if not _PROJECT_DIR:
    raise RuntimeError(
        "CLAUDE_PODMAN_PROJECT_DIR must be set before starting the MCP server"
    )
_PROJECT_ROOT = Path(_PROJECT_DIR).resolve()
_SESSION_REPO = session_image_repo(SESSION_ID)

_ALLOWED_IMAGES = frozenset({
    "debian", "python", "node",
    "postgres", "redis", "mysql", "mariadb", "mongo",
    "nginx", "rabbitmq", "memcached",
})

mcp = MCPServer("podman-mcp")


def _podman(*args: str) -> tuple[int, str, str]:
    r = subprocess.run(
        ["podman", *args], capture_output=True, text=True
    )
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _resolve_in_project(rel: str) -> Path | None:
    """Translate a sandbox path to a host path inside _PROJECT_ROOT.

    Accepts /project-relative or bare-relative forms; rejects anything
    that resolves outside the project root.
    """
    p = rel.strip()
    if p == "/project" or p.startswith("/project/"):
        p = p[len("/project"):].lstrip("/") or "."
    candidate = (_PROJECT_ROOT / p).resolve()
    try:
        candidate.relative_to(_PROJECT_ROOT)
        return candidate
    except ValueError:
        return None


def _image_allowed(image: str) -> bool:
    repo = image.split(":")[0]
    if repo == _SESSION_REPO:
        return True
    host, sep, _ = repo.partition("/")
    if sep and ("." in host or ":" in host or host == "localhost"):
        return False
    return repo in _ALLOWED_IMAGES


def _is_session_container(name: str) -> bool:
    rc, out, _ = _podman(
        "inspect", name,
        "--format",
        f'{{{{index .Config.Labels "{SESSION_LABEL_KEY}"}}}}',
    )
    return rc == 0 and out == SESSION_ID


def _rewrite_volume(spec: str) -> str | None:
    """Rewrite a volume spec so the source path is on the host.

    Accepts specs of the form  source:target[:options]  where source is
    either a /project-relative path or a bare relative path.  Returns
    None if the source resolves outside the project root.

    Anonymous volumes (no colon) are passed through unchanged.
    """
    parts = spec.split(":", 2)
    if len(parts) == 1:
        return spec
    source = parts[0]
    host = _resolve_in_project(source)
    if host is None:
        return None
    parts[0] = str(host)
    return ":".join(parts)


@mcp.tool()
def container_run(
    image: str,
    name: str | None = None,
    ports: list[str] | None = None,
    env: dict[str, str] | None = None,
    volumes: list[str] | None = None,
) -> str:
    """Start a detached container for this session.

    Volume specs use /project-relative sources, e.g.
    "/project/data:/data" or "data:/data".
    """
    if not _image_allowed(image):
        return f"Image not in allowlist: {image}"
    cmd = ["run", "-d", f"--label={_SESSION_LABEL}"]
    if name:
        cmd += ["--name", name]
    for p in ports or []:
        cmd += ["-p", p]
    for k, v in (env or {}).items():
        cmd += ["-e", f"{k}={v}"]
    for v in volumes or []:
        rewritten = _rewrite_volume(v)
        if rewritten is None:
            return f"Volume source outside project: {v}"
        cmd += ["-v", rewritten]
    cmd.append(image)
    rc, out, err = _podman(*cmd)
    return out if rc == 0 else f"Error: {err}"


@mcp.tool()
def container_build(
    context: str = ".",
    containerfile: str | None = None,
    tag: str = "latest",
) -> str:
    """Build an image from a Containerfile inside /project.

    context and containerfile are paths relative to /project (or
    absolute /project/... paths). The resulting image is tagged for
    this session and can be passed directly to container_run.
    """
    ctx = _resolve_in_project(context)
    if ctx is None or not ctx.is_dir():
        return f"Build context outside project or not a directory: {context}"
    cmd = [
        "build", "-t", f"{_SESSION_REPO}:{tag}",
        f"--label={_SESSION_LABEL}",
    ]
    if containerfile:
        cf = _resolve_in_project(containerfile)
        if cf is None or not cf.is_file():
            return f"Containerfile outside project: {containerfile}"
        cmd += ["-f", str(cf)]
    cmd.append(str(ctx))
    rc, out, err = _podman(*cmd)
    return f"Built {_SESSION_REPO}:{tag}" if rc == 0 else f"Error: {err or out}"


@mcp.tool()
def container_stop(name: str) -> str:
    """Stop a session container."""
    if not _is_session_container(name):
        return f"Not a session container: {name}"
    rc, out, err = _podman("stop", name)
    return out if rc == 0 else f"Error: {err}"


@mcp.tool()
def container_remove(name: str, force: bool = False) -> str:
    """Remove a session container."""
    if not _is_session_container(name):
        return f"Not a session container: {name}"
    cmd = ["rm", "-f", name] if force else ["rm", name]
    rc, out, err = _podman(*cmd)
    return out if rc == 0 else f"Error: {err}"


@mcp.tool()
def container_logs(name: str, tail: int = 50) -> str:
    """Fetch recent logs from a session container."""
    if not _is_session_container(name):
        return f"Not a session container: {name}"
    rc, out, err = _podman("logs", "--tail", str(tail), name)
    return (out or err) if rc == 0 else f"Error: {err}"


@mcp.tool()
def container_list() -> str:
    """List all containers for this session (JSON)."""
    rc, out, err = _podman(
        "ps", "-a",
        "--filter", f"label={_SESSION_LABEL}",
        "--format", "json",
    )
    return out if rc == 0 else f"Error: {err}"


@mcp.tool()
def container_exec(name: str, command: list[str]) -> str:
    """Run a command inside a running session container."""
    if not _is_session_container(name):
        return f"Not a session container: {name}"
    rc, out, err = _podman("exec", name, *command)
    return (out or err) if rc == 0 else f"Error: {err}"


def _require_token(app: ASGIApp) -> ASGIApp:
    """Reject any HTTP request that doesn't carry our bearer token.

    The MCP server and its one client (the podman-claude container it was
    started for) are a fixed pair, so a single shared secret generated
    per-session is enough — this isn't meant to authorize anyone else.
    """

    async def wrapped(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = dict(scope["headers"])
            auth = headers.get(b"authorization", b"")
            if not hmac.compare_digest(auth, _EXPECTED_AUTH):
                response = PlainTextResponse("Unauthorized", status_code=401)
                await response(scope, receive, send)
                return
        await app(scope, receive, send)

    return wrapped


def main():
    import uvicorn

    host = os.environ.get("MCP_HOST", "0.0.0.0")
    app = _require_token(mcp.streamable_http_app(host=host))
    uvicorn.run(app, host=host, port=int(os.environ.get("MCP_PORT", "8000")))


if __name__ == "__main__":
    main()
