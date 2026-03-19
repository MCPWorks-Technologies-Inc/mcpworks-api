"""Filesystem-based scratchpad backend.

Stores files at {base_path}/{agent_id}/ on the local filesystem.
Uses asyncio.to_thread() for all I/O to avoid blocking the event loop.
Atomic replace via temp directory + rename.

Single-writer constraint: assumes one API process writes per agent directory.
On k3s with single node, ReadWriteOnce PVC is sufficient.
Multi-replica requires the R2 backend.
"""

import asyncio
import re
import shutil
import uuid as uuid_mod
from pathlib import Path, PurePosixPath
from uuid import UUID

import structlog

from mcpworks_api.scratchpad.base import ScratchpadBackend

logger = structlog.get_logger(__name__)

FILENAME_REGEX = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,254}$")
MAX_PATH_DEPTH = 3
MAX_FILES = 100


class FilesystemBackend(ScratchpadBackend):
    def __init__(self, base_path: str) -> None:
        self.base_path = Path(base_path)

    def _agent_dir(self, agent_id: UUID) -> Path:
        return self.base_path / str(agent_id)

    def _validate_path(self, filename: str, agent_base: Path) -> Path:
        """Validate filename and return resolved safe path.

        Raises ValueError on invalid filenames or path traversal attempts.
        """
        if not filename or not FILENAME_REGEX.match(filename):
            raise ValueError(f"Invalid filename: {filename!r}")

        if "\x00" in filename:
            raise ValueError("Filename contains null bytes")

        parts = PurePosixPath(filename).parts
        if ".." in parts:
            raise ValueError("Path traversal not allowed")
        if any(p.startswith("/") for p in parts):
            raise ValueError("Absolute paths not allowed")
        if len(parts) > MAX_PATH_DEPTH:
            raise ValueError(f"Path too deep (max {MAX_PATH_DEPTH} levels): {filename}")

        target = agent_base / filename
        resolved = target.resolve()
        agent_resolved = agent_base.resolve()

        if not str(resolved).startswith(str(agent_resolved) + "/") and resolved != agent_resolved:
            raise ValueError("Path traversal detected after resolution")

        return target

    async def write_files(self, agent_id: UUID, files: dict[str, bytes], mode: str) -> int:
        agent_dir = self._agent_dir(agent_id)

        def _write() -> int:
            if mode == "replace":
                tmp_dir = agent_dir.parent / f".tmp-{uuid_mod.uuid4()}"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                try:
                    for filename, content in files.items():
                        target = self._validate_path(filename, tmp_dir)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(content)

                    if agent_dir.exists():
                        shutil.rmtree(agent_dir)
                    tmp_dir.rename(agent_dir)
                except Exception:
                    if tmp_dir.exists():
                        shutil.rmtree(tmp_dir)
                    raise
            else:
                agent_dir.mkdir(parents=True, exist_ok=True)
                for filename, content in files.items():
                    target = self._validate_path(filename, agent_dir)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)

            return self._calc_size(agent_dir)

        return await asyncio.to_thread(_write)

    async def read_file(self, agent_id: UUID, path: str) -> bytes | None:
        agent_dir = self._agent_dir(agent_id)

        def _read() -> bytes | None:
            try:
                target = self._validate_path(path, agent_dir)
            except ValueError:
                return None
            if not target.is_file():
                return None
            return target.read_bytes()

        return await asyncio.to_thread(_read)

    async def list_files(self, agent_id: UUID) -> list[str]:
        agent_dir = self._agent_dir(agent_id)

        def _list() -> list[str]:
            if not agent_dir.exists():
                return []
            return sorted(
                str(f.relative_to(agent_dir))
                for f in agent_dir.rglob("*")
                if f.is_file() and not f.name.startswith(".")
            )

        return await asyncio.to_thread(_list)

    async def get_total_size(self, agent_id: UUID) -> int:
        agent_dir = self._agent_dir(agent_id)
        return await asyncio.to_thread(self._calc_size, agent_dir)

    async def clear(self, agent_id: UUID) -> None:
        agent_dir = self._agent_dir(agent_id)

        def _clear() -> None:
            if agent_dir.exists():
                shutil.rmtree(agent_dir)
                agent_dir.mkdir(parents=True, exist_ok=True)

        await asyncio.to_thread(_clear)

    async def delete_all(self, agent_id: UUID) -> None:
        agent_dir = self._agent_dir(agent_id)

        def _delete() -> None:
            if agent_dir.exists():
                shutil.rmtree(agent_dir)

        await asyncio.to_thread(_delete)

    @staticmethod
    def _calc_size(directory: Path) -> int:
        if not directory.exists():
            return 0
        return sum(f.stat().st_size for f in directory.rglob("*") if f.is_file())
