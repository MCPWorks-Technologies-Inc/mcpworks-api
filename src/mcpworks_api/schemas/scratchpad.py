"""Pydantic schemas for agent scratchpad."""

from pydantic import BaseModel, Field


class PublishScratchpadRequest(BaseModel):
    files: dict[str, str] = Field(
        ...,
        description="Map of filename to content. Text as-is, binary as 'base64:...' prefixed.",
    )
    mode: str = Field(
        default="replace",
        pattern="^(replace|append)$",
        description="replace: clear first. append: add/overwrite specified files.",
    )


class PublishScratchpadResponse(BaseModel):
    url: str
    files_written: int
    total_bytes: int
    quota_remaining_bytes: int


class ScratchpadInfoResponse(BaseModel):
    url: str | None
    files: list[str]
    total_bytes: int


class ClearScratchpadResponse(BaseModel):
    status: str = "cleared"
