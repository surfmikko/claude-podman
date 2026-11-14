# Trixie ships git 2.47; relative worktree links (doc/worktrees.md)
# need >= 2.48, so build one. Same version as the host's.
FROM python:3-slim-trixie AS git-build
ARG GIT_VERSION=2.50.1
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl xz-utils gcc make libc6-dev \
        libcurl4-openssl-dev libssl-dev zlib1g-dev libexpat1-dev \
    && curl -fsSL "https://mirrors.edge.kernel.org/pub/software/scm/git/git-${GIT_VERSION}.tar.xz" \
        | tar -xJ -C /tmp \
    && make -C "/tmp/git-${GIT_VERSION}" -j"$(nproc)" prefix=/usr/local \
        NO_GETTEXT=1 NO_TCLTK=1 NO_PERL=1 NO_PYTHON=1 install

FROM python:3-slim-trixie

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl make ripgrep neovim jq libcurl4 libexpat1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash claude \
    && mkdir -p /home/claude/.claude && chown -R claude:claude /home/claude/.claude

COPY --from=git-build /usr/local/ /usr/local/

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
