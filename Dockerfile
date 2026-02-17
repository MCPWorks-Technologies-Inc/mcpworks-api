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

RUN pip install --no-cache-dir --target=/sandbox-packages \
    # ── HTTP & Networking ──
    requests \
    httpx \
    urllib3 \
    aiohttp \
    websockets \
    # ── Data Formats ──
    pyyaml \
    orjson \
    tomli \
    tomli-w \
    xmltodict \
    msgpack \
    # ── Data Validation ──
    pydantic \
    attrs \
    jsonschema \
    # ── Text & Content Processing ──
    beautifulsoup4 \
    lxml \
    markdownify \
    markdown \
    html2text \
    chardet \
    python-slugify \
    jinja2 \
    regex \
    # ── Date & Time ──
    python-dateutil \
    pytz \
    arrow \
    # ── Data Science ──
    numpy \
    pandas \
    scipy \
    scikit-learn \
    sympy \
    statsmodels \
    # ── Visualization ──
    matplotlib \
    pillow \
    # ── AI & LLM ──
    openai \
    anthropic \
    tiktoken \
    cohere \
    # ── Cloud & SaaS APIs ──
    boto3 \
    stripe \
    sendgrid \
    twilio \
    google-cloud-storage \
    # ── File Formats ──
    tabulate \
    feedparser \
    openpyxl \
    xlsxwriter \
    python-docx \
    pypdf \
    # ── Crypto & Security ──
    cryptography \
    pyjwt \
    bcrypt \
    # ── Database Clients ──
    psycopg2-binary \
    pymongo \
    redis \
    # ── Utilities ──
    humanize \
    tqdm \
    rich \
    typing-extensions

# =============================================================================
# Stage 2: nsjail — compile from source
# =============================================================================
FROM debian:bookworm-slim AS nsjail-builder

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

RUN git clone --depth 1 https://github.com/google/nsjail.git /nsjail \
    && cd /nsjail \
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

WORKDIR /app

# Install runtime dependencies (postgres client + nsjail runtime libs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libprotobuf32 \
    libnl-3-200 \
    libnl-route-3-200 \
    iptables \
    && rm -rf /var/lib/apt/lists/*

# Copy API virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy nsjail binary
COPY --from=nsjail-builder /usr/local/bin/nsjail /usr/local/bin/nsjail

# Copy curated sandbox packages
COPY --from=sandbox-builder /sandbox-packages /opt/mcpworks/sandbox-root/site-packages

# Copy sandbox scripts and rootfs
COPY deploy/nsjail/execute.py /opt/mcpworks/bin/execute.py
COPY deploy/nsjail/spawn-sandbox.sh /opt/mcpworks/bin/spawn-sandbox.sh
COPY deploy/nsjail/setup-cgroups.sh /opt/mcpworks/bin/setup-cgroups.sh
COPY deploy/nsjail/rootfs/ /opt/mcpworks/rootfs/
COPY deploy/nsjail/python.cfg /etc/mcpworks/sandbox.cfg
COPY deploy/nsjail/seccomp.policy /etc/mcpworks/seccomp.policy

RUN chmod +x /opt/mcpworks/bin/spawn-sandbox.sh /opt/mcpworks/bin/setup-cgroups.sh

# Copy application code
COPY src/ ./src/
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
