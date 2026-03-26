"""Pydantic schemas for namespace Git export/import operations."""

from pydantic import BaseModel, Field


class ConfigureRemoteResponse(BaseModel):
    status: str = "configured"
    git_url: str
    git_branch: str
    verified: bool


class RemoveRemoteResponse(BaseModel):
    status: str = "removed"


class ExportSummary(BaseModel):
    services: int = 0
    functions: int = 0
    agents: int = 0


class ExportResponse(BaseModel):
    status: str = "exported"
    commit_sha: str
    git_url: str
    git_branch: str
    files_changed: int
    summary: ExportSummary


class ExportServiceResponse(BaseModel):
    status: str = "exported"
    commit_sha: str
    service: str
    files_changed: int
    functions: int


class ImportCounts(BaseModel):
    services: int = 0
    functions: int = 0
    agents: int = 0


class ImportResponse(BaseModel):
    status: str = "imported"
    namespace: str
    created: ImportCounts = Field(default_factory=ImportCounts)
    skipped: ImportCounts = Field(default_factory=ImportCounts)
    warnings: list[str] = Field(default_factory=list)


class ImportServiceResponse(BaseModel):
    status: str = "imported"
    service: str
    namespace: str
    created: ImportCounts = Field(default_factory=ImportCounts)
    skipped: ImportCounts = Field(default_factory=ImportCounts)
    warnings: list[str] = Field(default_factory=list)
