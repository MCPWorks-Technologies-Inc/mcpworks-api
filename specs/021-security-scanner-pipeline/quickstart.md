# Quickstart: Security Scanner Pipeline

## Key Files

| File | Purpose |
|------|---------|
| `src/mcpworks_api/core/scanner_pipeline.py` | Pipeline evaluator |
| `src/mcpworks_api/core/scanners/base.py` | Scanner interface + ScanVerdict |
| `src/mcpworks_api/core/scanners/pattern_scanner.py` | Refactored injection scan |
| `src/mcpworks_api/core/scanners/secret_scanner.py` | Refactored credential scan |
| `src/mcpworks_api/core/scanners/trust_boundary.py` | Refactored trust boundary |
| `src/mcpworks_api/core/scanners/webhook_scanner.py` | HTTP POST scanner |
| `src/mcpworks_api/core/scanners/python_scanner.py` | Importable callable scanner |
| `src/mcpworks_api/mcp/run_handler.py` | Pipeline integration in dispatch |
| `src/mcpworks_api/mcp/create_handler.py` | Scanner management tools |
| `tests/unit/test_scanner_pipeline.py` | Pipeline evaluation tests |

## Development Flow

```bash
pytest tests/unit/test_scanner_pipeline.py -v
pytest tests/unit/test_pattern_scanner.py -v
pytest tests/unit/ -q
```

## Quick Test

```
# Default pipeline (built-in scanners only)
# Execute a function that returns injection content → verify trust markers applied

# Add a webhook scanner
add_security_scanner(type="webhook", name="my-guard", direction="output",
    config={"url": "https://guard.internal/scan", "timeout_ms": 2000})

# List pipeline
list_security_scanners()

# Remove scanner
remove_security_scanner(scanner_id="s-abc123")
```

## Building a Webhook Scanner

Implement a single endpoint:

```python
from fastapi import FastAPI
app = FastAPI()

@app.post("/scan")
async def scan(request: dict):
    content = request["content"]
    # Your detection logic here
    if "ignore previous" in content.lower():
        return {"action": "flag", "score": 0.9, "reason": "injection pattern"}
    return {"action": "pass", "score": 0.0, "reason": "clean"}
```

Register: `add_security_scanner(type="webhook", name="my-scanner", direction="output", config={"url": "http://scanner:8001/scan"})`

## Building a Python Scanner

```python
# my_scanner.py (install in API's venv)
def scan(content: str, context: dict) -> dict:
    if "ignore previous" in content.lower():
        return {"action": "flag", "score": 0.9, "reason": "injection pattern"}
    return {"action": "pass", "score": 0.0, "reason": "clean"}
```

Register: `add_security_scanner(type="python", name="my-scanner", direction="output", config={"module": "my_scanner", "function": "scan"})`
