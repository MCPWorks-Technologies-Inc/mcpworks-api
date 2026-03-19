"""Scratchpad service — business logic for agent visual scratchpads."""

import base64
import re
import secrets
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.models.agent import Agent
from mcpworks_api.scratchpad import get_scratchpad_backend
from mcpworks_api.scratchpad.base import ScratchpadBackend

logger = structlog.get_logger(__name__)

FILENAME_REGEX = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,254}$")
MAX_PATH_DEPTH = 3

SCRATCHPAD_QUOTA_BYTES: dict[str, int] = {
    "trial-agent": 0,
    "pro-agent": 100 * 1024 * 1024,
    "enterprise-agent": 1024 * 1024 * 1024,
    "dedicated-agent": 10 * 1024 * 1024 * 1024,
}

DEFAULT_QUOTA_BYTES = 100 * 1024 * 1024


def generate_scratchpad_token() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()


class ScratchpadError(Exception):
    pass


class ScratchpadQuotaExceeded(ScratchpadError):
    def __init__(self, current_bytes: int, limit_bytes: int, requested_bytes: int):
        self.current_bytes = current_bytes
        self.limit_bytes = limit_bytes
        self.requested_bytes = requested_bytes
        super().__init__(
            f"Scratchpad quota exceeded: {current_bytes}/{limit_bytes} bytes, "
            f"requested {requested_bytes}"
        )


class ScratchpadNotAvailable(ScratchpadError):
    pass


class ScratchpadValidationError(ScratchpadError):
    pass


class ScratchpadService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.backend: ScratchpadBackend = get_scratchpad_backend()

    async def publish(
        self,
        agent: Agent,
        files: dict[str, str],
        mode: str = "replace",
        tier: str = "pro-agent",
    ) -> dict:
        quota = self._get_quota_bytes(tier)
        if quota == 0:
            raise ScratchpadNotAvailable(
                "Scratchpad is not available on the Trial tier. Upgrade to Pro."
            )

        self._validate_filenames(list(files.keys()))

        decoded: dict[str, bytes] = {}
        for filename, content in files.items():
            decoded[filename] = self._decode_file_content(content)

        new_bytes = sum(len(v) for v in decoded.values())

        if mode == "replace":
            if new_bytes > quota:
                raise ScratchpadQuotaExceeded(0, quota, new_bytes)
        else:
            current = agent.scratchpad_size_bytes or 0
            if current + new_bytes > quota:
                raise ScratchpadQuotaExceeded(current, quota, new_bytes)

        token = self._ensure_token(agent)

        total_bytes = await self.backend.write_files(agent.id, decoded, mode)

        agent.scratchpad_size_bytes = total_bytes
        agent.scratchpad_updated_at = datetime.now(UTC)
        await self.db.flush()

        url = self._build_url(agent.name, token)

        logger.info(
            "scratchpad_publish",
            agent_id=str(agent.id),
            file_count=len(decoded),
            total_bytes=total_bytes,
            mode=mode,
        )

        return {
            "url": url,
            "files_written": len(decoded),
            "total_bytes": total_bytes,
            "quota_remaining_bytes": max(0, quota - total_bytes),
        }

    async def get_url(self, agent: Agent) -> dict:
        if not agent.scratchpad_token or not agent.scratchpad_size_bytes:
            return {"url": None, "files": [], "total_bytes": 0}

        file_list = await self.backend.list_files(agent.id)
        url = self._build_url(agent.name, agent.scratchpad_token)

        return {
            "url": url,
            "files": file_list[:50],
            "total_bytes": agent.scratchpad_size_bytes,
        }

    async def clear(self, agent: Agent) -> None:
        await self.backend.clear(agent.id)
        old_size = agent.scratchpad_size_bytes
        agent.scratchpad_size_bytes = 0
        agent.scratchpad_updated_at = None
        await self.db.flush()

        logger.info(
            "scratchpad_clear",
            agent_id=str(agent.id),
            bytes_freed=old_size,
        )

    async def read_file(self, agent_id: UUID, path: str) -> bytes | None:
        return await self.backend.read_file(agent_id, path)

    async def resolve_agent_by_token(self, token: str) -> Agent | None:
        result = await self.db.execute(select(Agent).where(Agent.scratchpad_token == token))
        return result.scalar_one_or_none()

    def _ensure_token(self, agent: Agent) -> str:
        if not agent.scratchpad_token:
            agent.scratchpad_token = generate_scratchpad_token()
        return agent.scratchpad_token

    @staticmethod
    def _build_url(agent_name: str, token: str) -> str:
        return f"https://{agent_name}.agent.mcpworks.io/view/{token}/"

    @staticmethod
    def _validate_filenames(filenames: list[str]) -> None:
        if len(filenames) > 100:
            raise ScratchpadValidationError(f"Too many files: {len(filenames)} (max 100)")
        if not filenames:
            raise ScratchpadValidationError("No files provided")

        for filename in filenames:
            if not filename or not FILENAME_REGEX.match(filename):
                raise ScratchpadValidationError(f"Invalid filename: {filename!r}")
            if "\x00" in filename:
                raise ScratchpadValidationError("Filename contains null bytes")

            from pathlib import PurePosixPath

            parts = PurePosixPath(filename).parts
            if ".." in parts:
                raise ScratchpadValidationError("Path traversal not allowed")
            if len(parts) > MAX_PATH_DEPTH:
                raise ScratchpadValidationError(
                    f"Path too deep (max {MAX_PATH_DEPTH} levels): {filename}"
                )

    @staticmethod
    def _decode_file_content(content: str) -> bytes:
        if content.startswith("base64:"):
            try:
                return base64.b64decode(content[7:])
            except Exception as e:
                raise ScratchpadValidationError(f"Invalid base64 content: {e}") from e
        return content.encode("utf-8")

    @staticmethod
    def _get_quota_bytes(tier: str) -> int:
        return SCRATCHPAD_QUOTA_BYTES.get(tier, DEFAULT_QUOTA_BYTES)
