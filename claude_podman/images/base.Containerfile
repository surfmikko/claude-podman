FROM python:3-slim-trixie

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl git make ripgrep neovim jq \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash claude \
    && mkdir -p /home/claude/.claude && chown -R claude:claude /home/claude/.claude

ENV EDITOR=nvim
ENV VISUAL=nvim
ENV TERM=xterm-256color

COPY --chmod=755 rootfs/ /

USER claude
ENV PATH=/opt/agent-test:/home/claude/.local/bin:$PATH
RUN curl -fsSL https://claude.ai/install.sh | bash

# Local code search (MCP server). Pinned to Python 3.13 because
# tree-sitter has no wheels for the base image's newest Python. The
# model is fetched at build time so sessions work offline.
RUN pip install --user --no-cache-dir uv \
    && uv tool install --python 3.13 "semble[mcp]" \
    && ~/.local/share/uv/tools/semble/bin/python -c \
        "from semble.index.dense import load_model; load_model()" \
    && uv cache clean \
    && pip uninstall -y uv
# /project is shared with the host: keep the index per architecture.
ARG TARGETARCH
ENV SEMBLE_CACHE_LOCATION=/project/.claude-index/linux-${TARGETARCH}

WORKDIR /project
CMD ["claude", "--dangerously-skip-permissions", \
     "--plugin-dir", "/opt/statusline-footer"]
