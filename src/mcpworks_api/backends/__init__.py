"""Backend registry and factory.

Provides a registry for function execution backends and factory
functions to retrieve them by name.

Available Backends:
- code_sandbox: Secure sandboxed Python/TypeScript execution
- activepieces: Visual workflow automation (A1 milestone)
- nanobot: Definition TBD (A2 milestone)
- github_repo: GitHub repository-based functions (A3 milestone)
"""

from mcpworks_api.backends.base import Backend, ExecutionResult, ValidationResult

# Registry of available backends
_backends: dict[str, Backend] = {}


def register_backend(backend: Backend) -> None:
    """Register a backend.

    Args:
        backend: Backend instance to register.

    Raises:
        ValueError: If a backend with the same name is already registered.
    """
    if backend.name in _backends:
        raise ValueError(f"Backend '{backend.name}' is already registered")
    _backends[backend.name] = backend


def unregister_backend(name: str) -> None:
    """Unregister a backend.

    Args:
        name: Name of the backend to unregister.
    """
    _backends.pop(name, None)


def get_backend(name: str) -> Backend | None:
    """Get a backend by name.

    Args:
        name: Backend identifier (code_sandbox, activepieces, etc.)

    Returns:
        Backend instance or None if not found.
    """
    return _backends.get(name)


def list_backends() -> list[str]:
    """List available backend names.

    Returns:
        List of registered backend names.
    """
    return list(_backends.keys())


def get_all_backends() -> dict[str, Backend]:
    """Get all registered backends.

    Returns:
        Dict of backend name to Backend instance.
    """
    return dict(_backends)


def is_backend_available(name: str) -> bool:
    """Check if a backend is available.

    Args:
        name: Backend identifier.

    Returns:
        True if backend is registered, False otherwise.
    """
    return name in _backends


# Register code_sandbox backend
# Uses development mode (subprocess) by default; nsjail in production
from mcpworks_api.backends.sandbox import SandboxBackend

register_backend(SandboxBackend())

# Stub backend available for testing
from mcpworks_api.backends.stub import StubBackend

# Future milestones:
# A1: register_backend(ActivepiecesBackend())
# A2: register_backend(NanobotBackend())
# A3: register_backend(GitHubRepoBackend())

__all__ = [
    # Base
    "Backend",
    "ExecutionResult",
    "ValidationResult",
    # Backends
    "SandboxBackend",
    "StubBackend",
    # Registry
    "register_backend",
    "unregister_backend",
    "get_backend",
    "list_backends",
    "get_all_backends",
    "is_backend_available",
]
