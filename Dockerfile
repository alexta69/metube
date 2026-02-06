FROM node:lts-alpine AS builder

WORKDIR /metube
COPY ui ./
RUN corepack enable && corepack prepare pnpm --activate
RUN CI=true pnpm install && pnpm run build


FROM rust:1.93-slim AS bgutil-builder

WORKDIR /src

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      curl \
      ca-certificates \
      build-essential \
      pkg-config \
      libssl-dev \
      python3 && \
    BGUTIL_TAG="$(curl -Ls -o /dev/null -w '%{url_effective}' https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs/releases/latest | sed 's#.*/tag/##')" && \
    curl -L "https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs/archive/refs/tags/${BGUTIL_TAG}.tar.gz" \
      | tar -xz --strip-components=1 && \
    cargo build --release


FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml uv.lock docker-entrypoint.sh ./

# Use sed to strip carriage-return characters from the entrypoint script (in case building on Windows)
# Install dependencies
RUN sed -i 's/\r$//g' docker-entrypoint.sh && \
    chmod +x docker-entrypoint.sh && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      ffmpeg \
      unzip \
      aria2 \
      coreutils \
      gosu \
      curl \
      tini \
      file \
      gdbmtool \
      sqlite3 \
      build-essential && \
    curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh && \
    UV_PROJECT_ENVIRONMENT=/usr/local uv sync --frozen --no-dev --compile-bytecode && \
    uv cache clean && \
    rm -f /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/uvw && \
    curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh -s -- -y && \
    apt-get purge -y --auto-remove build-essential && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir /.cache && chmod 777 /.cache

COPY --from=bgutil-builder /src/target/release/bgutil-pot /usr/local/bin/bgutil-pot

RUN BGUTIL_TAG="$(curl -Ls -o /dev/null -w '%{url_effective}' https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs/releases/latest | sed 's#.*/tag/##')" && \
    PLUGIN_DIR="$(python3 -c 'import site; print(site.getsitepackages()[0])')" && \
    curl -L -o /tmp/bgutil-ytdlp-pot-provider-rs.zip \
      "https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs/releases/download/${BGUTIL_TAG}/bgutil-ytdlp-pot-provider-rs.zip" && \
    unzip -q /tmp/bgutil-ytdlp-pot-provider-rs.zip -d "${PLUGIN_DIR}" && \
    rm /tmp/bgutil-ytdlp-pot-provider-rs.zip

COPY app ./app
COPY --from=builder /metube/dist/metube ./ui/dist/metube

ENV PUID=1000
ENV PGID=1000
ENV UMASK=022

ENV DOWNLOAD_DIR /downloads
ENV STATE_DIR /downloads/.metube
ENV TEMP_DIR /downloads
VOLUME /downloads
EXPOSE 8081

# Add build-time argument for version
ARG VERSION=dev
ENV METUBE_VERSION=$VERSION

ENTRYPOINT ["/usr/bin/tini", "-g", "--", "./docker-entrypoint.sh"]
