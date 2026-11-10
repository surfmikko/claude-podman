ARG BASE=claude-podman
FROM ${BASE}

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential pkg-config libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir pylint pyflakes ruff

USER claude
