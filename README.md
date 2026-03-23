# mcpworks API

Open-source (BSL 1.1) backend for the MCPWorks platform — namespace-based function hosting and autonomous agent runtime for AI assistants.

## Quick Start

```bash
# Start services
docker compose up -d

# Run migrations
alembic upgrade head

# Seed initial data
python scripts/seed_data.py
```

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run server
uvicorn mcpworks_api.main:app --reload
```

## API Endpoints

- `POST /v1/auth/token` - Exchange API key for JWT tokens
- `POST /v1/auth/refresh` - Refresh access token
- `GET /v1/users/me` - Get current user profile
- `GET /v1/health` - Health check

## Self-Hosting

See [docs/SELF-HOSTING.md](docs/SELF-HOSTING.md) for step-by-step deployment instructions.

## License

MCPWorks API is licensed under the [Business Source License 1.1](LICENSE). After the Change Date (2030-03-22), the license converts to Apache License 2.0.

See [LICENSE](LICENSE) for details.
