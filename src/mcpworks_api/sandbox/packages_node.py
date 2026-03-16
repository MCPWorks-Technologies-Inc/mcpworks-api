"""Allow-listed Node.js package registry for TypeScript sandbox execution.

All packages in this registry are pre-installed in the sandbox Docker image.
Users specify requirements when creating TypeScript functions; we validate
against this registry before accepting them.

Same security model as Python packages (packages.py):
- Pre-installed (no npm install at runtime)
- No supply-chain attacks via postinstall scripts
- Predictable, reproducible execution environment

To add a new package:
1. Add it to NODE_PACKAGE_REGISTRY below
2. Add the npm package name to deploy/nsjail/package.json
3. Rebuild and deploy
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NodePackageInfo:
    """Metadata for an allowed sandbox npm package."""

    npm_name: str
    description: str
    category: str
    aliases: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Node.js Package Registry
#
# Keyed by the user-facing name (what they put in requirements list).
# Node.js built-ins (crypto, url, path, buffer, util, etc.) are always
# available and do NOT need to be listed here.
# ---------------------------------------------------------------------------

NODE_PACKAGE_REGISTRY: dict[str, NodePackageInfo] = {
    # ── Utilities ─────────────────────────────────────────────────────────
    "lodash": NodePackageInfo(
        npm_name="lodash",
        description="Utility functions for arrays, objects, strings",
        category="utilities",
    ),
    "uuid": NodePackageInfo(
        npm_name="uuid",
        description="RFC-compliant UUID generation",
        category="utilities",
    ),
    # ── Date & Time ───────────────────────────────────────────────────────
    "date-fns": NodePackageInfo(
        npm_name="date-fns",
        description="Modern date utility library",
        category="datetime",
    ),
    # ── Data Validation ───────────────────────────────────────────────────
    "zod": NodePackageInfo(
        npm_name="zod",
        description="TypeScript-first schema validation",
        category="validation",
    ),
    "ajv": NodePackageInfo(
        npm_name="ajv",
        description="JSON Schema validator (fast)",
        category="validation",
    ),
    # ── Data Formats & Serialization ──────────────────────────────────────
    "csv-parse": NodePackageInfo(
        npm_name="csv-parse",
        description="CSV parser with streaming support",
        category="data_formats",
    ),
    "csv-stringify": NodePackageInfo(
        npm_name="csv-stringify",
        description="CSV serializer",
        category="data_formats",
    ),
    "yaml": NodePackageInfo(
        npm_name="yaml",
        description="YAML parser and serializer",
        category="data_formats",
    ),
    "xml2js": NodePackageInfo(
        npm_name="xml2js",
        description="XML to JavaScript object converter",
        category="data_formats",
    ),
    # ── Text & Content Processing ─────────────────────────────────────────
    "cheerio": NodePackageInfo(
        npm_name="cheerio",
        description="HTML parser (jQuery-like API for server)",
        category="text",
    ),
    "marked": NodePackageInfo(
        npm_name="marked",
        description="Markdown to HTML converter",
        category="text",
    ),
    # ── HTTP & Networking ─────────────────────────────────────────────────
    "axios": NodePackageInfo(
        npm_name="axios",
        description="HTTP client (alternative to built-in fetch)",
        category="http",
    ),
    # ── Crypto & Security ─────────────────────────────────────────────────
    "jsonwebtoken": NodePackageInfo(
        npm_name="jsonwebtoken",
        description="JSON Web Token signing and verification",
        category="security",
        aliases=("jwt",),
    ),
    "bcryptjs": NodePackageInfo(
        npm_name="bcryptjs",
        description="Password hashing (pure JS, no native deps)",
        category="security",
        aliases=("bcrypt",),
    ),
    # ── AI & LLM ──────────────────────────────────────────────────────────
    "openai": NodePackageInfo(
        npm_name="openai",
        description="OpenAI API client",
        category="ai",
    ),
    "@anthropic-ai/sdk": NodePackageInfo(
        npm_name="@anthropic-ai/sdk",
        description="Anthropic Claude API client",
        category="ai",
        aliases=("anthropic",),
    ),
}

# Build reverse-lookup for aliases (alias → canonical name)
_ALIAS_MAP: dict[str, str] = {}
for _name, _pkg in NODE_PACKAGE_REGISTRY.items():
    for _alias in _pkg.aliases:
        _ALIAS_MAP[_alias.lower()] = _name


def _resolve_name(name: str) -> str | None:
    """Resolve a package name (or alias) to its canonical registry key.

    Returns None if the package is not in the registry.
    """
    normalized = name.strip().lower()
    if normalized in NODE_PACKAGE_REGISTRY:
        return normalized
    return _ALIAS_MAP.get(normalized)


def validate_node_requirements(
    requirements: list[str],
) -> tuple[list[str], list[str]]:
    """Validate a list of npm package requirements against the allow-list.

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
                "Use list_packages(language='typescript') to see available packages."
            )
            continue

        if canonical in seen:
            continue
        seen.add(canonical)

        validated.append(canonical)

    return validated, errors


def get_node_registry_by_category() -> dict[str, list[dict[str, str]]]:
    """Get all Node.js packages grouped by category.

    Returns a dict of category → list of package info dicts.
    """
    by_category: dict[str, list[dict[str, str]]] = {}

    for name, pkg in sorted(NODE_PACKAGE_REGISTRY.items()):
        entry = {"name": name, "description": pkg.description}
        by_category.setdefault(pkg.category, []).append(entry)

    return by_category


def get_all_npm_names() -> list[str]:
    """Get all npm install names for package.json generation.

    Returns deduplicated, sorted list of npm package names.
    """
    return sorted({pkg.npm_name for pkg in NODE_PACKAGE_REGISTRY.values()})
