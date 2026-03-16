"""Allow-listed Python package registry for sandbox execution.

All packages in this registry are pre-installed in the sandbox Docker image.
Users specify requirements when creating functions; we validate against this
registry before accepting them.

Keeping packages pre-installed (rather than installing at runtime) gives us:
- Instant cold starts (no pip install delay)
- No supply-chain attacks via malicious setup.py
- Predictable, reproducible execution environment

To add a new package:
1. Add it to PACKAGE_REGISTRY below
2. Add the pip install name to the Dockerfile sandbox-builder stage
3. Rebuild and deploy
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PackageInfo:
    """Metadata for an allowed sandbox package."""

    pip_name: str
    description: str
    category: str
    aliases: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Package Registry
#
# Keyed by the user-facing name (what they put in requirements list).
# For most packages this matches the import name.
# ---------------------------------------------------------------------------

PACKAGE_REGISTRY: dict[str, PackageInfo] = {
    # ── HTTP & Networking ─────────────────────────────────────────────────
    "requests": PackageInfo(
        pip_name="requests",
        description="Simple HTTP client library",
        category="http",
    ),
    "httpx": PackageInfo(
        pip_name="httpx",
        description="Modern async/sync HTTP client",
        category="http",
    ),
    "urllib3": PackageInfo(
        pip_name="urllib3",
        description="Low-level HTTP client",
        category="http",
    ),
    "aiohttp": PackageInfo(
        pip_name="aiohttp",
        description="Async HTTP client/server framework",
        category="http",
    ),
    "websockets": PackageInfo(
        pip_name="websockets",
        description="WebSocket client and server library",
        category="http",
    ),
    # ── Data Formats & Serialization ──────────────────────────────────────
    "pyyaml": PackageInfo(
        pip_name="pyyaml",
        description="YAML parser and emitter",
        category="data_formats",
        aliases=("yaml",),
    ),
    "orjson": PackageInfo(
        pip_name="orjson",
        description="Fast JSON library (10x faster than stdlib json)",
        category="data_formats",
    ),
    "tomli": PackageInfo(
        pip_name="tomli",
        description="TOML parser",
        category="data_formats",
    ),
    "tomli-w": PackageInfo(
        pip_name="tomli-w",
        description="TOML writer",
        category="data_formats",
    ),
    "xmltodict": PackageInfo(
        pip_name="xmltodict",
        description="XML to Python dict and back",
        category="data_formats",
    ),
    "msgpack": PackageInfo(
        pip_name="msgpack",
        description="MessagePack binary serialization",
        category="data_formats",
    ),
    # ── Data Validation ───────────────────────────────────────────────────
    "pydantic": PackageInfo(
        pip_name="pydantic",
        description="Data validation using Python type hints",
        category="validation",
    ),
    "attrs": PackageInfo(
        pip_name="attrs",
        description="Classes without boilerplate",
        category="validation",
    ),
    "jsonschema": PackageInfo(
        pip_name="jsonschema",
        description="JSON Schema validation",
        category="validation",
    ),
    # ── Text & Content Processing ─────────────────────────────────────────
    "beautifulsoup4": PackageInfo(
        pip_name="beautifulsoup4",
        description="HTML and XML parser",
        category="text",
        aliases=("bs4",),
    ),
    "lxml": PackageInfo(
        pip_name="lxml",
        description="Fast XML and HTML processing",
        category="text",
    ),
    "markdownify": PackageInfo(
        pip_name="markdownify",
        description="Convert HTML to Markdown",
        category="text",
    ),
    "markdown": PackageInfo(
        pip_name="markdown",
        description="Markdown to HTML converter",
        category="text",
    ),
    "html2text": PackageInfo(
        pip_name="html2text",
        description="Convert HTML to plain text",
        category="text",
    ),
    "chardet": PackageInfo(
        pip_name="chardet",
        description="Character encoding detection",
        category="text",
    ),
    "python-slugify": PackageInfo(
        pip_name="python-slugify",
        description="URL slug generator",
        category="text",
        aliases=("slugify",),
    ),
    "jinja2": PackageInfo(
        pip_name="jinja2",
        description="Template engine",
        category="text",
    ),
    "regex": PackageInfo(
        pip_name="regex",
        description="Extended regular expressions (superset of stdlib re)",
        category="text",
    ),
    # ── Date & Time ───────────────────────────────────────────────────────
    "python-dateutil": PackageInfo(
        pip_name="python-dateutil",
        description="Powerful date parsing and manipulation",
        category="datetime",
        aliases=("dateutil",),
    ),
    "pytz": PackageInfo(
        pip_name="pytz",
        description="Timezone definitions",
        category="datetime",
    ),
    "arrow": PackageInfo(
        pip_name="arrow",
        description="Better dates and times for Python",
        category="datetime",
    ),
    # ── Data Science ──────────────────────────────────────────────────────
    "numpy": PackageInfo(
        pip_name="numpy",
        description="Numerical computing with arrays",
        category="data_science",
    ),
    "pandas": PackageInfo(
        pip_name="pandas",
        description="Data manipulation and analysis",
        category="data_science",
    ),
    "scipy": PackageInfo(
        pip_name="scipy",
        description="Scientific computing (optimization, stats, signal)",
        category="data_science",
    ),
    "scikit-learn": PackageInfo(
        pip_name="scikit-learn",
        description="Machine learning (classification, regression, clustering)",
        category="data_science",
        aliases=("sklearn",),
    ),
    "sympy": PackageInfo(
        pip_name="sympy",
        description="Symbolic mathematics",
        category="data_science",
    ),
    "statsmodels": PackageInfo(
        pip_name="statsmodels",
        description="Statistical models and tests",
        category="data_science",
    ),
    # ── Visualization ─────────────────────────────────────────────────────
    "matplotlib": PackageInfo(
        pip_name="matplotlib",
        description="Plotting and visualization",
        category="visualization",
    ),
    "pillow": PackageInfo(
        pip_name="pillow",
        description="Image processing (PIL fork)",
        category="visualization",
        aliases=("PIL",),
    ),
    # ── AI & LLM ──────────────────────────────────────────────────────────
    "openai": PackageInfo(
        pip_name="openai",
        description="OpenAI API client (GPT, embeddings, assistants)",
        category="ai",
    ),
    "anthropic": PackageInfo(
        pip_name="anthropic",
        description="Anthropic Claude API client",
        category="ai",
    ),
    "tiktoken": PackageInfo(
        pip_name="tiktoken",
        description="OpenAI tokenizer for token counting",
        category="ai",
    ),
    "cohere": PackageInfo(
        pip_name="cohere",
        description="Cohere API client (embeddings, rerank, generate)",
        category="ai",
    ),
    # ── Cloud & SaaS APIs ─────────────────────────────────────────────────
    "boto3": PackageInfo(
        pip_name="boto3",
        description="AWS SDK (S3, DynamoDB, Lambda, SES, etc.)",
        category="cloud",
    ),
    "stripe": PackageInfo(
        pip_name="stripe",
        description="Stripe payment processing API",
        category="cloud",
    ),
    "sendgrid": PackageInfo(
        pip_name="sendgrid",
        description="SendGrid email delivery API",
        category="cloud",
    ),
    "twilio": PackageInfo(
        pip_name="twilio",
        description="Twilio SMS and voice API",
        category="cloud",
    ),
    "google-cloud-storage": PackageInfo(
        pip_name="google-cloud-storage",
        description="Google Cloud Storage client",
        category="cloud",
    ),
    # ── File Formats ──────────────────────────────────────────────────────
    "openpyxl": PackageInfo(
        pip_name="openpyxl",
        description="Read/write Excel .xlsx files",
        category="file_formats",
    ),
    "xlsxwriter": PackageInfo(
        pip_name="xlsxwriter",
        description="Write Excel .xlsx files with formatting",
        category="file_formats",
    ),
    "tabulate": PackageInfo(
        pip_name="tabulate",
        description="Pretty-print tabular data",
        category="file_formats",
    ),
    "feedparser": PackageInfo(
        pip_name="feedparser",
        description="Parse RSS and Atom feeds",
        category="file_formats",
    ),
    "python-docx": PackageInfo(
        pip_name="python-docx",
        description="Read/write Word .docx files",
        category="file_formats",
    ),
    "pypdf": PackageInfo(
        pip_name="pypdf",
        description="Read and manipulate PDF files",
        category="file_formats",
    ),
    # ── Crypto & Security ─────────────────────────────────────────────────
    "cryptography": PackageInfo(
        pip_name="cryptography",
        description="Cryptographic primitives and recipes",
        category="security",
    ),
    "pyjwt": PackageInfo(
        pip_name="pyjwt",
        description="JSON Web Token encoding/decoding",
        category="security",
        aliases=("jwt",),
    ),
    "bcrypt": PackageInfo(
        pip_name="bcrypt",
        description="Password hashing",
        category="security",
    ),
    # ── Database Clients ──────────────────────────────────────────────────
    "psycopg2-binary": PackageInfo(
        pip_name="psycopg2-binary",
        description="PostgreSQL database client",
        category="database",
        aliases=("psycopg2",),
    ),
    "pymongo": PackageInfo(
        pip_name="pymongo",
        description="MongoDB client",
        category="database",
    ),
    "redis": PackageInfo(
        pip_name="redis",
        description="Redis client",
        category="database",
    ),
    # ── Utilities ─────────────────────────────────────────────────────────
    "humanize": PackageInfo(
        pip_name="humanize",
        description="Human-friendly data formatting (file sizes, dates, numbers)",
        category="utilities",
    ),
    "tqdm": PackageInfo(
        pip_name="tqdm",
        description="Progress bars for loops",
        category="utilities",
    ),
    "rich": PackageInfo(
        pip_name="rich",
        description="Rich text and formatting for terminal output",
        category="utilities",
    ),
    "typing-extensions": PackageInfo(
        pip_name="typing-extensions",
        description="Backported typing features",
        category="utilities",
    ),
}

# Build reverse-lookup for aliases (alias → canonical name)
_ALIAS_MAP: dict[str, str] = {}
for _name, _pkg in PACKAGE_REGISTRY.items():
    for _alias in _pkg.aliases:
        _ALIAS_MAP[_alias.lower()] = _name


def _resolve_name(name: str) -> str | None:
    """Resolve a package name (or alias) to its canonical registry key.

    Returns None if the package is not in the registry.
    """
    normalized = name.strip().lower()
    if normalized in PACKAGE_REGISTRY:
        return normalized
    return _ALIAS_MAP.get(normalized)


def validate_requirements(
    requirements: list[str],
) -> tuple[list[str], list[str]]:
    """Validate a list of package requirements against the allow-list.

    Args:
        requirements: Package names requested by the user.

    Returns:
        Tuple of (validated canonical names, error messages).
        If errors is non-empty, the requirements are invalid.
    """
    validated: list[str] = []
    errors: list[str] = []
    seen: set[str] = set()

    for req in requirements:
        canonical = _resolve_name(req)

        if canonical is None:
            errors.append(
                f"Package '{req}' is not in the allowed list. "
                "Use the list_packages tool to see available packages."
            )
            continue

        if canonical in seen:
            continue  # Skip duplicates silently
        seen.add(canonical)

        validated.append(canonical)

    return validated, errors


def get_registry_by_category() -> dict[str, list[dict[str, str]]]:
    """Get all packages grouped by category.

    Returns a dict of category → list of package info dicts.
    """
    by_category: dict[str, list[dict[str, str]]] = {}

    for name, pkg in sorted(PACKAGE_REGISTRY.items()):
        entry = {"name": name, "description": pkg.description}
        by_category.setdefault(pkg.category, []).append(entry)

    return by_category


def get_all_pip_names() -> list[str]:
    """Get all pip install names for Dockerfile generation.

    Returns deduplicated, sorted list of pip package names.
    """
    return sorted({pkg.pip_name for pkg in PACKAGE_REGISTRY.values()})


def validate_requirements_for_language(
    requirements: list[str],
    language: str = "python",
) -> tuple[list[str], list[str]]:
    """Dispatch requirement validation to the correct language registry.

    Args:
        requirements: Package names requested by the user.
        language: Programming language ('python' or 'typescript').

    Returns:
        Tuple of (validated canonical names, error messages).
    """
    if language == "typescript":
        from mcpworks_api.sandbox.packages_node import validate_node_requirements

        return validate_node_requirements(requirements)
    return validate_requirements(requirements)
