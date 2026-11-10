ARG BASE=claude-podman
FROM ${BASE}

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/*

USER claude
ENV RUSTUP_HOME=/home/claude/.rustup
ENV CARGO_HOME=/home/claude/.cargo
ENV PATH=/home/claude/.cargo/bin:$PATH
# /project is shared with the host, so build output must stay in the
# container.
ENV CARGO_TARGET_DIR=/tmp/target
RUN curl -fsSL https://sh.rustup.rs \
    | sh -s -- -y --profile minimal -c clippy -c rustfmt
