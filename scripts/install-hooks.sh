#!/bin/bash
# Install lightweight git pre-commit hook.
# Runs ruff format check if ruff is available, skips silently if not.
# Does NOT require the pre-commit framework.

HOOK_PATH="$(git rev-parse --git-dir)/hooks/pre-commit"

cat > "$HOOK_PATH" << 'HOOK'
#!/bin/bash
# MCPWorks pre-commit hook
# Checks formatting on staged Python files. Skips if ruff is not installed.

if ! command -v ruff &>/dev/null; then
    exit 0
fi

STAGED=$(git diff --cached --name-only --diff-filter=ACM -- '*.py')
if [ -z "$STAGED" ]; then
    exit 0
fi

if ! ruff format --check $STAGED 2>/dev/null; then
    echo ""
    echo "ruff format check failed. Run:"
    echo "  ruff format \$(git diff --cached --name-only -- '*.py')"
    echo ""
    exit 1
fi

if ! ruff check $STAGED 2>/dev/null; then
    echo ""
    echo "ruff lint check failed. Run:"
    echo "  ruff check --fix \$(git diff --cached --name-only -- '*.py')"
    echo ""
    exit 1
fi
HOOK

chmod +x "$HOOK_PATH"
echo "Pre-commit hook installed at $HOOK_PATH"
