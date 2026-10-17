SESSION_LABEL_KEY = "claude-podman-session"
SESSION_IMAGE_PREFIX = "claude-podman-session-"


def session_image_repo(session_id: str) -> str:
    return f"{SESSION_IMAGE_PREFIX}{session_id}"
