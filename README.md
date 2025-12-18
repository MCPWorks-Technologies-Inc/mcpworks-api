# mcpworks API

API Gateway for mcpworks platform - authentication, credit accounting, and service routing.

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
