# =============================================================================
# Stage 1: Sandbox packages — allow-listed Python packages for user code
#
# All packages from the package registry (src/mcpworks_api/sandbox/packages.py)
# are pre-installed here. Keep this list in sync with PACKAGE_REGISTRY.
# =============================================================================
FROM python:3.11-slim AS sandbox-builder

# Install build deps for packages with C extensions (lxml, cryptography, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libffi-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Pin every package to ensure reproducible builds.  To update, install
# unpinned in a temp container, copy versions, and test in sandbox.
RUN pip install --no-cache-dir --target=/sandbox-packages \
    # ── HTTP & Networking ──
    requests==2.32.5 \
    httpx==0.28.1 \
    urllib3==2.6.3 \
    aiohttp==3.13.3 \
    websockets==16.0 \
    # ── Data Formats ──
    pyyaml==6.0.3 \
    orjson==3.11.7 \
    tomli==2.4.0 \
    tomli-w==1.2.0 \
    xmltodict==1.0.3 \
    msgpack==1.1.2 \
    # ── Data Validation ──
    pydantic==2.12.5 \
    attrs==25.4.0 \
    jsonschema==4.26.0 \
    # ── Text & Content Processing ──
    beautifulsoup4==4.14.3 \
    lxml==6.0.2 \
    markdownify==1.2.2 \
    markdown==3.10.2 \
    html2text==2025.4.15 \
    chardet==5.2.0 \
    python-slugify==8.0.4 \
    jinja2==3.1.6 \
    regex==2026.1.15 \
    # ── Date & Time ──
    python-dateutil==2.9.0.post0 \
    pytz==2025.2 \
    arrow==1.4.0 \
    # ── Data Science ──
    numpy==2.4.2 \
    pandas==3.0.0 \
    scipy==1.17.0 \
    scikit-learn==1.8.0 \
    sympy==1.14.0 \
    statsmodels==0.14.6 \
    # ── Visualization ──
    matplotlib==3.10.8 \
    pillow==12.1.1 \
    # ── AI & LLM ──
    openai==2.21.0 \
    anthropic==0.79.0 \
    tiktoken==0.12.0 \
    cohere==5.20.5 \
    # ── Cloud & SaaS APIs ──
    boto3==1.42.49 \
    stripe==14.3.0 \
    sendgrid==6.12.5 \
    twilio==9.10.1 \
    google-cloud-storage==3.9.0 \
    # ── File Formats ──
    tabulate==0.9.0 \
    feedparser==6.0.12 \
    openpyxl==3.1.5 \
    xlsxwriter==3.2.9 \
    python-docx==1.2.0 \
    pypdf==6.7.0 \
    # ── Crypto & Security ──
    cryptography==46.0.5 \
    pyjwt==2.11.0 \
    bcrypt==5.0.0 \
    # ── Database Clients ──
    psycopg2-binary==2.9.11 \
    pymongo==4.16.0 \
    redis==7.1.1 \
    # ── Utilities ──
    humanize==4.15.0 \
    tqdm==4.67.3 \
    rich==14.3.2 \
    typing-extensions==4.15.0

# =============================================================================
# Stage 1b: Node.js sandbox packages — pre-installed npm packages for TypeScript
#
# All packages from the Node.js package registry
# (src/mcpworks_api/sandbox/packages_node.py) are pre-installed here.
# Keep this list in sync with NODE_PACKAGE_REGISTRY.
# =============================================================================
FROM node:22-slim AS node-sandbox-builder

WORKDIR /node-packages
COPY deploy/nsjail/package.json .
RUN npm install --production --no-optional \
    && rm -rf /node-packages/node_modules/.package-lock.json

# =============================================================================
# Stage 2: nsjail — compile from source (pinned commit)
#
# IMPORTANT: Pin to a specific commit.  The bundled kafel determines which
# syscall names are valid in seccomp policies.  See deploy/nsjail/seccomp.policy
# for compatibility notes.
# =============================================================================
FROM debian:bookworm-slim AS nsjail-builder

# nsjail commit d20ea0a58ab5 (2026-02-02) — known-good with our seccomp policy.
# kafel in this build does NOT recognise: stat, fstat, lstat, sendfile, uname.
# kafel arg-filter syntax (arg0) is also broken.
# Update this SHA only after verifying the seccomp policy still compiles.
ARG NSJAIL_COMMIT=d20ea0a58ab57e8b5d2d37418ebbc2a57ddb8c2a

RUN apt-get update && apt-get install -y --no-install-recommends \
    autoconf \
    bison \
    flex \
    gcc \
    g++ \
    git \
    libprotobuf-dev \
    libnl-3-dev \
    libnl-route-3-dev \
    make \
    pkg-config \
    protobuf-compiler \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/google/nsjail.git /nsjail \
    && cd /nsjail \
    && git checkout ${NSJAIL_COMMIT} \
    && make -j$(nproc) \
    && cp /nsjail/nsjail /usr/local/bin/nsjail

# =============================================================================
# Stage 3: API venv — existing build stage
# =============================================================================
FROM python:3.11-slim AS builder

ARG DEV_MODE=0

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir --upgrade pip && \
    if [ "$DEV_MODE" = "1" ]; then \
        pip install --no-cache-dir ".[dev]"; \
    else \
        pip install --no-cache-dir .; \
    fi

# =============================================================================
# Stage 4: Production image
# =============================================================================
FROM python:3.11-slim

# SECURITY NOTE: This container runs as root intentionally.
# nsjail requires CAP_SYS_ADMIN to create Linux namespaces for sandbox isolation.
# User-submitted code runs inside nsjail with dropped privileges (UID 65534/nobody).
# The API process itself needs root only for nsjail namespace creation.

WORKDIR /app

# Install runtime dependencies (postgres client + nsjail runtime libs + Infisical CLI)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libprotobuf32 \
    libnl-3-200 \
    libnl-route-3-200 \
    iproute2 \
    iptables \
    uidmap \
    curl \
    bash \
    gnupg \
    && curl -1sLf 'https://dl.cloudsmith.io/public/infisical/infisical-cli/setup.deb.sh' | bash \
    && apt-get install -y infisical \
    && rm -rf /var/lib/apt/lists/* \
    && echo "root:65533:2" >> /etc/subuid \
    && echo "root:65533:2" >> /etc/subgid

# Copy API virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy nsjail binary
COPY --from=nsjail-builder /usr/local/bin/nsjail /usr/local/bin/nsjail

# Copy curated sandbox packages (Python)
COPY --from=sandbox-builder /sandbox-packages /opt/mcpworks/sandbox-root/site-packages

# Copy Node.js binary for TypeScript sandbox execution
COPY --from=node:22-slim /usr/local/bin/node /opt/mcpworks/sandbox-root/usr/local/bin/node

# Copy curated sandbox packages (Node.js/TypeScript)
COPY --from=node-sandbox-builder /node-packages/node_modules /opt/mcpworks/sandbox-root/node_modules

# Install esbuild on host for TypeScript transpilation (runs on host, not in sandbox)
RUN curl -fsSL https://esbuild.github.io/dl/v0.25.0 | sh \
    && mv esbuild /usr/local/bin/esbuild \
    || echo "esbuild install failed - TypeScript transpilation will be unavailable"

# Copy sandbox scripts and rootfs
COPY deploy/nsjail/execute.py /opt/mcpworks/bin/execute.py
RUN python3 -c "import py_compile; py_compile.compile('/opt/mcpworks/bin/execute.py', '/opt/mcpworks/bin/execute.pyc', doraise=True)" \
    && rm /opt/mcpworks/bin/execute.py
COPY deploy/nsjail/execute.js /opt/mcpworks/bin/execute.js
COPY deploy/nsjail/spawn-sandbox.sh /opt/mcpworks/bin/spawn-sandbox.sh
COPY deploy/nsjail/setup-cgroups.sh /opt/mcpworks/bin/setup-cgroups.sh
COPY deploy/nsjail/smoketest.py /opt/mcpworks/bin/smoketest.py
COPY deploy/nsjail/run-smoketest.sh /opt/mcpworks/bin/run-smoketest.sh
COPY deploy/nsjail/rootfs/ /opt/mcpworks/rootfs/
COPY deploy/nsjail/python.cfg /etc/mcpworks/sandbox.cfg
COPY deploy/nsjail/seccomp.policy /etc/mcpworks/seccomp.policy

RUN chmod +x /opt/mcpworks/bin/spawn-sandbox.sh /opt/mcpworks/bin/setup-cgroups.sh /opt/mcpworks/bin/run-smoketest.sh

# Copy application code
COPY src/ ./src/
COPY docs/guide.md docs/llm-reference.md ./docs/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/ ./scripts/

# Make startup script executable
RUN chmod +x ./scripts/start.sh

# Set Python path
ENV PYTHONPATH=/app/src

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/v1/health')" || exit 1

# Run application via startup script (handles migrations)
CMD ["./scripts/start.sh"]
