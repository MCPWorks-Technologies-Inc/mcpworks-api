# Contributing to MCPWorks

Thank you for your interest in contributing to MCPWorks! This guide will help you get started.

## Getting Started

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Git

### Development Setup

```bash
# Clone the repository
git clone https://github.com/MCPWorks-Technologies-Inc/mcpworks-api.git
cd mcpworks-api

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies (including dev tools)
pip install -e ".[dev]"

# Start infrastructure services
docker compose up -d postgres redis

# Generate JWT keys for development
mkdir -p keys
openssl ecparam -genkey -name prime256v1 -noout -out keys/private.pem
openssl ec -in keys/private.pem -pubout -out keys/public.pem

# Copy example environment file
cp .env.example .env

# Run database migrations
alembic upgrade head

# Start the development server
uvicorn mcpworks_api.main:app --reload --port 8000
```

### Running Tests

```bash
# Run unit tests (fast, no database needed)
pytest tests/unit/ -q

# Run integration tests (requires running Postgres — used in CI)
pytest tests/integration/ -v

# Run with coverage
pytest tests/unit/ -v --cov=src

# Run a specific test file
pytest tests/unit/test_example.py -v
```

### Linting and Formatting

We use [Ruff](https://docs.astral.sh/ruff/) for both linting and formatting:

```bash
# Check for lint issues
ruff check src/

# Auto-fix lint issues
ruff check src/ --fix

# Format code
ruff format src/
```

Pre-commit hooks run automatically on `git commit` to enforce these checks.

## How to Contribute

### Reporting Bugs

Use the [Bug Report](https://github.com/MCPWorks-Technologies-Inc/mcpworks-api/issues/new?template=bug_report.yml) issue template. Include:

- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version, Docker version)
- Relevant logs

### Suggesting Features

Use the [Feature Request](https://github.com/MCPWorks-Technologies-Inc/mcpworks-api/issues/new?template=feature_request.yml) issue template. Describe:

- The problem you're trying to solve
- Your proposed solution
- Alternatives you've considered

### Bug Fixes, Docs, and Refactors

For small changes that don't add new features:

1. **Fork** the repository
2. **Create a branch** from `main`: `fix/description`, `docs/description`, or `refactor/description`
3. **Make your changes**, write tests if applicable
4. **Ensure CI passes** (`ruff check src/` and `pytest tests/ -v`)
5. **Submit a pull request** against `main`

### New Features (Spec-First Workflow)

Features require a specification before code. This project uses the **speckit** methodology — specs define *what*, plans define *how*, tasks define *when*.

1. **Fork** the repository
2. **Create a branch** named `NNN-feature-name` (e.g., `008-webhook-retry`)
3. **Write the spec** in `specs/NNN-feature-name/spec.md` — what the feature does, user scenarios, requirements, edge cases. Use `docs/implementation/specs/TEMPLATE.md` as a starting point.
4. **Open a draft PR** with just the spec for early feedback
5. **Create the plan** in `specs/NNN-feature-name/plan.md` — tech choices, data model, architecture
6. **Break into tasks** in `specs/NNN-feature-name/tasks.md` — ordered, atomic, 2-8 hours each
7. **Implement** following the task list
8. **Mark the PR as ready** when implementation is complete

If you use Claude Code or another AI assistant with speckit commands:
```
/speckit.specify    → Generate spec from a description
/speckit.clarify    → Find and resolve ambiguities in the spec
/speckit.plan       → Generate implementation plan + research
/speckit.tasks      → Generate task breakdown
/speckit.implement  → Execute the task list
```

The full artifact flow:
```
Constitution → Specification (WHAT) → Plan (HOW) → Tasks (WHO/WHEN) → Code
```

### Commit Messages

Write descriptive commit messages that explain *why* the change was made:

```
Fix sandbox timeout not respecting tier limits

The code_sandbox backend was using a hardcoded 30s timeout instead of
reading the tier-specific timeout from TIER_CONFIG. This caused
pro-tier users to hit timeouts on legitimate long-running functions.

Co-Authored-By: Your Name <your@email.com>
```

### Pull Request Process

1. PRs require at least one review before merging
2. All CI checks must pass (lint, test, build, security scan)
3. Keep PRs focused — one logical change per PR
4. Update documentation if your change affects public APIs
5. **Feature PRs** must include spec artifacts in `specs/NNN-feature-name/`

## Architecture Notes

Before making architectural changes, please read:

- `docs/implementation/specs/CONSTITUTION.md` — Development principles
- `SPEC.md` — API specification
- `AGENTS.md` — LLM coding standards (also useful for humans)

### Key Design Decisions

- **Spec-first**: All features require an approved specification before implementation
- **Token efficiency**: MCP responses should be 200-1000 tokens
- **Provider abstraction**: Never couple directly to infrastructure providers
- **Usage safety**: Always check subscription limits before execution

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold this code.

## Questions?

- Open a [Discussion](https://github.com/MCPWorks-Technologies-Inc/mcpworks-api/discussions) for general questions
- File an [Issue](https://github.com/MCPWorks-Technologies-Inc/mcpworks-api/issues) for bugs or feature requests
- Email support@mcpworks.io for private inquiries

## License

By contributing, you agree that your contributions will be licensed under the [BSL 1.1 License](LICENSE).
