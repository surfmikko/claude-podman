FROM python:3-slim-trixie

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends \
        nodejs git make ripgrep neovim \
    && rm -rf /var/lib/apt/lists/*

ENV EDITOR=nvim
ENV VISUAL=nvim
ENV TERM=xterm-256color

RUN useradd -m -s /bin/bash node \
    && mkdir -p /home/node/.claude && chown -R node:node /home/node/.claude

USER node
ENV PATH=/home/node/.local/bin:$PATH
RUN curl -fsSL https://claude.ai/install.sh | bash

WORKDIR /project
CMD ["claude", "--dangerously-skip-permissions"]
