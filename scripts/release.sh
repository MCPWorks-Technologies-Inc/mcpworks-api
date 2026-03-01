#!/usr/bin/env bash
set -euo pipefail

# Cut a release. Tags the current HEAD and pushes.
# The release.yml workflow creates the GitHub Release with auto-generated changelog.
#
# Usage:
#   ./scripts/release.sh v0.2.0
#   ./scripts/release.sh v0.2.0 "Namespace sharing, deploy hardening"
#
# The tag triggers:
#   1. release.yml  → GitHub Release with changelog + Docker image to GHCR
#   2. deploy.yml   → already ran when these commits were pushed to main
#
# Convention:
#   v0.Y.Z while pre-1.0
#   Bump minor (Y) for features, patch (Z) for fixes/infra

VERSION="${1:-}"
TITLE="${2:-}"

if [ -z "$VERSION" ]; then
    echo "Usage: $0 <version> [title]"
    echo "  e.g. $0 v0.2.0 \"Namespace sharing, deploy hardening\""
    echo ""
    echo "Recent tags:"
    git tag --sort=-version:refname | head -5 || echo "  (none)"
    echo ""
    echo "Commits since last tag:"
    LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
    if [ -n "$LAST_TAG" ]; then
        git log --oneline "${LAST_TAG}..HEAD"
    else
        git log --oneline | head -20
    fi
    exit 1
fi

if [[ ! "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Error: version must match vX.Y.Z (e.g. v0.2.0)"
    exit 1
fi

# Ensure we're on main and up to date
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "main" ]; then
    echo "Error: must be on main branch (currently on $BRANCH)"
    exit 1
fi

# Check for uncommitted changes
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Error: uncommitted changes. Commit or stash first."
    exit 1
fi

# Check tag doesn't already exist
if git rev-parse "$VERSION" >/dev/null 2>&1; then
    echo "Error: tag $VERSION already exists"
    exit 1
fi

# Show what's going in
echo "=== Release $VERSION ==="
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
if [ -n "$LAST_TAG" ]; then
    echo "Changes since $LAST_TAG:"
    git log --oneline "${LAST_TAG}..HEAD"
else
    echo "First release. All commits:"
    git log --oneline | head -30
fi
echo ""

# Confirm
read -rp "Tag and push $VERSION? [y/N] " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Tag
if [ -n "$TITLE" ]; then
    git tag -a "$VERSION" -m "$TITLE"
else
    git tag -a "$VERSION" -m "Release $VERSION"
fi

# Push tag (triggers release.yml)
git push origin "$VERSION"

echo ""
echo "=== Tagged $VERSION and pushed ==="
echo "GitHub Actions will create the release: https://github.com/MCPWorks-Technologies-Inc/mcpworks-api/actions"
echo "Release page: https://github.com/MCPWorks-Technologies-Inc/mcpworks-api/releases/tag/$VERSION"
