"""Agent visual scratchpad — per-agent web scratch space."""

from mcpworks_api.scratchpad.base import ScratchpadBackend

_backend: ScratchpadBackend | None = None


def get_scratchpad_backend() -> ScratchpadBackend:
    global _backend
    if _backend is None:
        from mcpworks_api.config import get_settings
        from mcpworks_api.scratchpad.filesystem import FilesystemBackend

        _backend = FilesystemBackend(get_settings().scratchpad_base_path)
    return _backend
