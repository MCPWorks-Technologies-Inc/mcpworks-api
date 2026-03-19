"""Abstract base class for scratchpad storage backends."""

from abc import ABC, abstractmethod
from uuid import UUID


class ScratchpadBackend(ABC):
    @abstractmethod
    async def write_files(self, agent_id: UUID, files: dict[str, bytes], mode: str) -> int:
        """Write files to scratchpad.

        Args:
            agent_id: Agent UUID.
            files: Map of relative path to file content bytes.
            mode: 'replace' clears existing files first; 'append' adds/overwrites.

        Returns:
            Total bytes now stored in the scratchpad.
        """

    @abstractmethod
    async def read_file(self, agent_id: UUID, path: str) -> bytes | None:
        """Read a single file. Returns None if not found."""

    @abstractmethod
    async def list_files(self, agent_id: UUID) -> list[str]:
        """List all file paths in the scratchpad."""

    @abstractmethod
    async def get_total_size(self, agent_id: UUID) -> int:
        """Get total bytes used by all files."""

    @abstractmethod
    async def clear(self, agent_id: UUID) -> None:
        """Delete all files but keep the agent directory."""

    @abstractmethod
    async def delete_all(self, agent_id: UUID) -> None:
        """Remove the agent's entire scratchpad storage (agent destruction)."""
