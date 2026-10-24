# syntax=docker/dockerfile:1.7

# --------------------------------------------------------------------------- #
# 1. geckodriver (built separately so the runtime image stays small)
# --------------------------------------------------------------------------- #
FROM python:3.13-slim-bookworm AS geckodriver

ARG GECKODRIVER_VERSION=v0.36.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
        amd64) target="linux64" ;; \
        arm64) target="linux-aarch64" ;; \
        *) echo "unsupported architecture: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /tmp/geckodriver.tar.gz \
        "https://github.com/mozilla/geckodriver/releases/download/${GECKODRIVER_VERSION}/geckodriver-${GECKODRIVER_VERSION}-${target}.tar.gz"; \
    tar -xzf /tmp/geckodriver.tar.gz -C /usr/local/bin geckodriver; \
    chmod 0755 /usr/local/bin/geckodriver; \
    rm -f /tmp/geckodriver.tar.gz; \
    /usr/local/bin/geckodriver --version | head -n 1

# --------------------------------------------------------------------------- #
# 2. Runtime: Firefox ESR + Selenium
# --------------------------------------------------------------------------- #
FROM python:3.13-slim-bookworm

LABEL org.opencontainers.image.title="ninja-defenders-free" \
      org.opencontainers.image.description="Claim the daily free Ruby Cat Stone on the Ninja Defenders web shop" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    ARTIFACTS_DIR=/app/artifacts \
    GECKODRIVER_PATH=/usr/local/bin/geckodriver

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        firefox-esr \
        fonts-noto-cjk \
        libdbus-glib-1-2 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man /tmp/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY --from=geckodriver /usr/local/bin/geckodriver /usr/local/bin/geckodriver
COPY claim.py ./

# Run unprivileged: the browser does not need root, and neither do we.
RUN useradd --create-home --uid 10001 runner \
    && mkdir -p "${ARTIFACTS_DIR}" \
    && chown -R runner:runner /app

USER runner

ENTRYPOINT ["python3", "claim.py"]
