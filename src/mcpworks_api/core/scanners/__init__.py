"""Security scanner registry."""

from mcpworks_api.core.scanners.base import (
    BaseScanner,
    PipelineResult,
    ScanContext,
    ScanVerdict,
)
from mcpworks_api.core.scanners.pattern_scanner import PatternScanner
from mcpworks_api.core.scanners.secret_scanner import SecretScanner
from mcpworks_api.core.scanners.trust_boundary_scanner import TrustBoundaryScanner

BUILTIN_SCANNERS: dict[str, type[BaseScanner]] = {
    "pattern_scanner": PatternScanner,
    "secret_scanner": SecretScanner,
    "trust_boundary": TrustBoundaryScanner,
}

__all__ = [
    "BaseScanner",
    "BUILTIN_SCANNERS",
    "PatternScanner",
    "PipelineResult",
    "ScanContext",
    "ScanVerdict",
    "SecretScanner",
    "TrustBoundaryScanner",
]
