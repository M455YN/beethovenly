FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

ARG TARGETARCH

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        mpv \
        libopus0 \
        ca-certificates \
        curl \
        unzip \
        tini \
    && case "${TARGETARCH}" in \
         amd64) DENO_ARCH=x86_64 ;; \
         arm64) DENO_ARCH=aarch64 ;; \
         *) echo "unsupported arch: ${TARGETARCH}" >&2; exit 1 ;; \
       esac \
    && curl -fsSL "https://github.com/denoland/deno/releases/download/v2.5.6/deno-${DENO_ARCH}-unknown-linux-gnu.zip" \
         -o /tmp/deno.zip \
    && unzip -q /tmp/deno.zip -d /usr/local/bin \
    && chmod +x /usr/local/bin/deno \
    && rm -f /tmp/deno.zip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh \
    && mkdir -p /app/data

RUN useradd --create-home --uid 1000 beethoven \
    && chown -R beethoven:beethoven /app
USER beethoven
ENV PATH="/home/beethoven/.local/bin:${PATH}"

ENTRYPOINT ["tini", "--", "/docker-entrypoint.sh"]
