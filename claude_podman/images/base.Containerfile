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
ENV PATH=/home/claude/.local/bin:$PATH
RUN curl -fsSL https://claude.ai/install.sh | bash

WORKDIR /project
CMD ["claude", "--dangerously-skip-permissions", \
     "--plugin-dir", "/opt/statusline-footer"]
