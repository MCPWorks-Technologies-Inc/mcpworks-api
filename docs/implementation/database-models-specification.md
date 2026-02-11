# Database Models and Schemas Specification

**Version:** 1.0.0
**Last Updated:** 2026-02-09
**Status:** Active
**Related Documents:**
- [Namespace Architecture](../../../mcpworks-internals/docs/implementation/namespace-architecture.md)
- [Code Execution Sandbox Specification](../../../mcpworks-internals/docs/implementation/code-execution-sandbox-specification.md)

---

## Table of Contents

1. [Overview](#overview)
2. [Design Principles](#design-principles)
3. [SQLAlchemy Models](#sqlalchemy-models)
4. [Pydantic Schemas](#pydantic-schemas)
5. [Alembic Migrations](#alembic-migrations)
6. [Integration Notes](#integration-notes)
7. [Security Considerations](#security-considerations)
8. [Performance Optimizations](#performance-optimizations)

---

## Overview

This specification defines the database models and schemas for the MCPWorks A0 platform, extending the existing `mcpworks-api` codebase to support namespace-based function hosting.

**New Functionality:**
- Namespace management with network security controls
- Service organization within namespaces
- Function versioning with immutable deployments
- Multi-backend function execution (Code Sandbox, Activepieces, etc.)
- Security event logging for SOC 2 compliance
- Webhook delivery system

**Existing Models to Extend:**
- `User` - Email, tier, status, API relationships
- `Account` - Billing entity (assumed to exist based on namespace FK)
- `APIKey` - Authentication tokens
- `AuditLog` - Action tracking
- `UsageRecord` - Usage accounting per billing period
- `Execution` - Function execution records
- `Subscription` - Billing tiers

---

## Design Principles

### 1. Async-First Architecture
All models use SQLAlchemy 2.0+ async patterns with `Mapped[]` type annotations.

### 2. Mixin-Based Composition
Common patterns extracted into reusable mixins:
- `UUIDMixin` - UUID primary keys
- `TimestampMixin` - `created_at`, `updated_at` fields
- `SoftDeleteMixin` - Soft delete support

### 3. Immutable Versioning
Function versions are immutable once created. Updates create new versions.

### 4. Security-First Design
- Network whitelisting with rate limits
- Security event logging for all sensitive operations
- Encrypted sensitive fields (webhook secrets)
- IP hashing for privacy

### 5. Multi-Tenancy Isolation
All resources scoped to namespaces → accounts → users for complete isolation.

### 6. Performance Optimization
- Strategic indexes on query patterns
- JSONB for flexible metadata
- Partial indexes for filtered queries
- Composite indexes for common joins

---

## SQLAlchemy Models

### Base Mixins

```python
# src/mcpworks_api/models/base.py

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


class UUIDMixin:
    """Provides UUID primary key."""

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        doc="UUID primary key"
    )


class TimestampMixin:
    """Provides created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Timestamp when record was created"
    )

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
        doc="Timestamp when record was last updated"
    )


class SoftDeleteMixin:
    """Provides soft delete functionality."""

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp when record was soft deleted"
    )

    @property
    def is_deleted(self) -> bool:
        """Check if record is soft deleted."""
        return self.deleted_at is not None
```

### Namespace Model

```python
# src/mcpworks_api/models/namespace.py

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from .base import Base, TimestampMixin, UUIDMixin


class Namespace(Base, UUIDMixin, TimestampMixin):
    """
    Namespace model for organizing functions and services.

    Namespaces provide:
    - Unique DNS subdomain ({namespace}.create.mcpworks.io, {namespace}.run.mcpworks.io)
    - Resource isolation between accounts
    - Network security controls (IP whitelisting)
    - Organizational boundary for services and functions

    Relationships:
    - account: The billing account that owns this namespace
    - services: Services organized within this namespace
    - api_keys: API keys scoped to this namespace
    """

    __tablename__ = "namespaces"

    # Core Fields
    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Account that owns this namespace"
    )

    name: Mapped[str] = mapped_column(
        String(63),
        nullable=False,
        unique=True,
        doc="Namespace name (DNS-compliant, 1-63 chars)"
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Human-readable description of namespace purpose"
    )

    # Network Security
    network_whitelist: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String),
        nullable=True,
        doc="List of allowed IP addresses/CIDR ranges"
    )

    whitelist_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Last time whitelist was modified"
    )

    whitelist_changes_today: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Number of whitelist changes in last 24h (rate limit)"
    )

    # Relationships
    account: Mapped["Account"] = relationship(
        "Account",
        back_populates="namespaces"
    )

    services: Mapped[List["Service"]] = relationship(
        "Service",
        back_populates="namespace",
        cascade="all, delete-orphan",
        order_by="Service.name"
    )

    api_keys: Mapped[List["APIKey"]] = relationship(
        "APIKey",
        back_populates="namespace",
        cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "name ~ '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$'",
            name="namespace_name_format"
        ),
        CheckConstraint(
            "whitelist_changes_today >= 0",
            name="whitelist_changes_positive"
        ),
        Index("ix_namespaces_account_id", "account_id"),
        Index("ix_namespaces_name", "name"),
    )

    @validates("name")
    def validate_name(self, key: str, value: str) -> str:
        """
        Validate namespace name follows DNS naming rules.

        Rules:
        - 1-63 characters
        - Lowercase alphanumeric and hyphens only
        - Must start and end with alphanumeric
        """
        if not value:
            raise ValueError("Namespace name cannot be empty")

        if len(value) > 63:
            raise ValueError("Namespace name must be 63 characters or less")

        import re
        if not re.match(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", value):
            raise ValueError(
                "Namespace name must be lowercase alphanumeric with hyphens, "
                "starting and ending with alphanumeric character"
            )

        return value.lower()

    def can_update_whitelist(self) -> bool:
        """Check if whitelist can be updated (rate limit check)."""
        # Allow 5 changes per 24 hours
        return self.whitelist_changes_today < 5

    def __repr__(self) -> str:
        return f"<Namespace(id={self.id}, name={self.name}, account_id={self.account_id})>"
```

### Service Model

```python
# src/mcpworks_api/models/service.py

from typing import List, Optional

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from .base import Base, TimestampMixin, UUIDMixin


class Service(Base, UUIDMixin, TimestampMixin):
    """
    Service model for organizing functions within a namespace.

    Services provide:
    - Logical grouping of related functions
    - Organization unit for function management
    - Namespace for function routing (/{service}/{function})

    Relationships:
    - namespace: The namespace this service belongs to
    - functions: Functions organized under this service
    """

    __tablename__ = "services"

    # Core Fields
    namespace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("namespaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Namespace this service belongs to"
    )

    name: Mapped[str] = mapped_column(
        String(63),
        nullable=False,
        doc="Service name (URL-safe, 1-63 chars)"
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Human-readable description of service purpose"
    )

    # Relationships
    namespace: Mapped["Namespace"] = relationship(
        "Namespace",
        back_populates="services"
    )

    functions: Mapped[List["Function"]] = relationship(
        "Function",
        back_populates="service",
        cascade="all, delete-orphan",
        order_by="Function.name"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "namespace_id",
            "name",
            name="uq_service_namespace_name"
        ),
        CheckConstraint(
            "name ~ '^[a-z0-9]([a-z0-9-_]{0,61}[a-z0-9])?$'",
            name="service_name_format"
        ),
        Index("ix_services_namespace_id", "namespace_id"),
        Index("ix_services_name", "name"),
    )

    @validates("name")
    def validate_name(self, key: str, value: str) -> str:
        """
        Validate service name follows URL-safe naming rules.

        Rules:
        - 1-63 characters
        - Lowercase alphanumeric, hyphens, and underscores
        - Must start and end with alphanumeric
        """
        if not value:
            raise ValueError("Service name cannot be empty")

        if len(value) > 63:
            raise ValueError("Service name must be 63 characters or less")

        import re
        if not re.match(r"^[a-z0-9]([a-z0-9-_]{0,61}[a-z0-9])?$", value):
            raise ValueError(
                "Service name must be lowercase alphanumeric with hyphens/underscores, "
                "starting and ending with alphanumeric character"
            )

        return value.lower()

    def __repr__(self) -> str:
        return f"<Service(id={self.id}, name={self.name}, namespace_id={self.namespace_id})>"
```

### Function Model

```python
# src/mcpworks_api/models/function.py

from typing import List, Optional

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from .base import Base, TimestampMixin, UUIDMixin


class Function(Base, UUIDMixin, TimestampMixin):
    """
    Function model representing a deployable function.

    Functions provide:
    - Named, versioned executable units
    - Multi-backend support (Code Sandbox, Activepieces, etc.)
    - Immutable version history
    - Tag-based organization and discovery

    Relationships:
    - service: The service this function belongs to
    - versions: Immutable versions of this function
    - executions: Execution history for this function
    """

    __tablename__ = "functions"

    # Core Fields
    service_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Service this function belongs to"
    )

    name: Mapped[str] = mapped_column(
        String(63),
        nullable=False,
        doc="Function name (URL-safe, 1-63 chars)"
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Human-readable description of function purpose"
    )

    tags: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String),
        nullable=True,
        doc="Tags for categorization and discovery"
    )

    active_version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        doc="Currently active/deployed version number"
    )

    # Relationships
    service: Mapped["Service"] = relationship(
        "Service",
        back_populates="functions"
    )

    versions: Mapped[List["FunctionVersion"]] = relationship(
        "FunctionVersion",
        back_populates="function",
        cascade="all, delete-orphan",
        order_by="desc(FunctionVersion.version)"
    )

    executions: Mapped[List["Execution"]] = relationship(
        "Execution",
        back_populates="function",
        order_by="desc(Execution.created_at)"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "service_id",
            "name",
            name="uq_function_service_name"
        ),
        CheckConstraint(
            "name ~ '^[a-z0-9]([a-z0-9-_]{0,61}[a-z0-9])?$'",
            name="function_name_format"
        ),
        CheckConstraint(
            "active_version > 0",
            name="function_active_version_positive"
        ),
        Index("ix_functions_service_id", "service_id"),
        Index("ix_functions_name", "name"),
        Index("ix_functions_tags", "tags", postgresql_using="gin"),
    )

    @validates("name")
    def validate_name(self, key: str, value: str) -> str:
        """
        Validate function name follows URL-safe naming rules.

        Rules:
        - 1-63 characters
        - Lowercase alphanumeric, hyphens, and underscores
        - Must start and end with alphanumeric
        """
        if not value:
            raise ValueError("Function name cannot be empty")

        if len(value) > 63:
            raise ValueError("Function name must be 63 characters or less")

        import re
        if not re.match(r"^[a-z0-9]([a-z0-9-_]{0,61}[a-z0-9])?$", value):
            raise ValueError(
                "Function name must be lowercase alphanumeric with hyphens/underscores, "
                "starting and ending with alphanumeric character"
            )

        return value.lower()

    @validates("active_version")
    def validate_active_version(self, key: str, value: int) -> int:
        """Validate active version is positive."""
        if value < 1:
            raise ValueError("Active version must be positive")
        return value

    def get_active_version_obj(self) -> Optional["FunctionVersion"]:
        """Get the active FunctionVersion object."""
        for version in self.versions:
            if version.version == self.active_version:
                return version
        return None

    def __repr__(self) -> str:
        return f"<Function(id={self.id}, name={self.name}, service_id={self.service_id}, active_v={self.active_version})>"
```

### FunctionVersion Model

```python
# src/mcpworks_api/models/function_version.py

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from .base import Base, UUIDMixin


class FunctionVersion(Base, UUIDMixin):
    """
    FunctionVersion model representing an immutable function deployment.

    Function versions provide:
    - Immutable code snapshots
    - Backend-specific configuration
    - Input/output schema definitions
    - Deployment history

    IMPORTANT: Function versions are IMMUTABLE once created.
    Any changes require creating a new version.

    Relationships:
    - function: The parent function this version belongs to
    """

    __tablename__ = "function_versions"

    # Core Fields
    function_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("functions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Function this version belongs to"
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Version number (1, 2, 3, ...)"
    )

    backend: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Function backend (code_sandbox, activepieces, nanobot, github_repo)"
    )

    # Backend-Specific Data
    code: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Function code (for code_sandbox backend)"
    )

    config: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        doc="Backend-specific configuration (workflow ID, repo URL, etc.)"
    )

    # Schema Definitions
    input_schema: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        doc="JSON Schema for function input validation"
    )

    output_schema: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        doc="JSON Schema for function output validation"
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        String(36),
        nullable=False,
        server_default="CURRENT_TIMESTAMP",
        doc="Timestamp when version was created (immutable)"
    )

    # Relationships
    function: Mapped["Function"] = relationship(
        "Function",
        back_populates="versions"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "function_id",
            "version",
            name="uq_function_version_number"
        ),
        CheckConstraint(
            "version > 0",
            name="function_version_positive"
        ),
        CheckConstraint(
            "backend IN ('code_sandbox', 'activepieces', 'nanobot', 'github_repo')",
            name="function_version_backend_valid"
        ),
        Index("ix_function_versions_function_id", "function_id"),
        Index("ix_function_versions_version", "function_id", "version"),
        Index("ix_function_versions_backend", "backend"),
    )

    @validates("backend")
    def validate_backend(self, key: str, value: str) -> str:
        """Validate backend is one of supported types."""
        allowed_backends = {"code_sandbox", "activepieces", "nanobot", "github_repo"}
        if value not in allowed_backends:
            raise ValueError(f"Backend must be one of {allowed_backends}")
        return value

    @validates("version")
    def validate_version(self, key: str, value: int) -> int:
        """Validate version is positive."""
        if value < 1:
            raise ValueError("Version must be positive")
        return value

    def __repr__(self) -> str:
        return f"<FunctionVersion(id={self.id}, function_id={self.function_id}, v={self.version}, backend={self.backend})>"
```

### SecurityEvent Model

```python
# src/mcpworks_api/models/security_event.py

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    JSON,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column, validates

from .base import Base, UUIDMixin


class SecurityEvent(Base, UUIDMixin):
    """
    SecurityEvent model for tracking security-relevant events.

    Security events provide:
    - Audit trail for SOC 2 compliance
    - Incident detection and response data
    - Access pattern analysis
    - Security monitoring and alerting

    Event Types:
    - auth.login_failed
    - auth.api_key_created
    - auth.api_key_revoked
    - namespace.whitelist_updated
    - function.execution_blocked
    - admin.user_suspended
    - etc.

    Severity Levels:
    - info: Normal operations
    - warning: Suspicious but not malicious
    - error: Failed operations requiring review
    - critical: Security incidents requiring immediate action
    """

    __tablename__ = "security_events"

    # Event Metadata
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        doc="When the event occurred"
    )

    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        doc="Event type in namespace format (e.g., auth.login_failed)"
    )

    # Actor Information
    actor_ip: Mapped[Optional[str]] = mapped_column(
        INET,
        nullable=True,
        doc="IP address of actor (hashed for privacy if needed)"
    )

    actor_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        doc="User ID, API key ID, or other actor identifier"
    )

    # Event Details
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        doc="Event-specific details (sanitized, no PII)"
    )

    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        doc="Event severity (info, warning, error, critical)"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "severity IN ('info', 'warning', 'error', 'critical')",
            name="security_event_severity_valid"
        ),
        Index("ix_security_events_timestamp", "timestamp"),
        Index("ix_security_events_event_type", "event_type"),
        Index("ix_security_events_severity", "severity"),
        Index("ix_security_events_actor_id", "actor_id"),
        Index(
            "ix_security_events_timestamp_severity",
            "timestamp",
            "severity"
        ),
    )

    @validates("severity")
    def validate_severity(self, key: str, value: str) -> str:
        """Validate severity is one of allowed values."""
        allowed_severities = {"info", "warning", "error", "critical"}
        if value not in allowed_severities:
            raise ValueError(f"Severity must be one of {allowed_severities}")
        return value

    @validates("event_type")
    def validate_event_type(self, key: str, value: str) -> str:
        """Validate event type follows namespace format."""
        if not value or "." not in value:
            raise ValueError("Event type must be in format 'category.action'")
        return value

    def __repr__(self) -> str:
        return f"<SecurityEvent(id={self.id}, type={self.event_type}, severity={self.severity}, timestamp={self.timestamp})>"
```

### Webhook Model

```python
# src/mcpworks_api/models/webhook.py

from typing import List, Optional

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from .base import Base, TimestampMixin, UUIDMixin


class Webhook(Base, UUIDMixin, TimestampMixin):
    """
    Webhook model for event notification delivery.

    Webhooks provide:
    - Real-time event notifications to external URLs
    - Filtered event subscriptions
    - Signature-based authentication
    - Enable/disable control

    Event Types:
    - function.execution.completed
    - function.execution.failed
    - function.created
    - function.updated
    - service.created
    - namespace.created
    - etc.

    Relationships:
    - account: The account that owns this webhook
    """

    __tablename__ = "webhooks"

    # Core Fields
    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Account that owns this webhook"
    )

    url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Webhook delivery URL (HTTPS required for production)"
    )

    secret_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Hashed webhook secret for HMAC signature verification"
    )

    events: Mapped[List[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        doc="List of event types to subscribe to"
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        doc="Whether webhook is enabled"
    )

    # Relationships
    account: Mapped["Account"] = relationship(
        "Account",
        back_populates="webhooks"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "url ~ '^https://'",
            name="webhook_url_https"
        ),
        Index("ix_webhooks_account_id", "account_id"),
        Index("ix_webhooks_enabled", "enabled"),
        Index("ix_webhooks_events", "events", postgresql_using="gin"),
    )

    @validates("url")
    def validate_url(self, key: str, value: str) -> str:
        """Validate webhook URL is HTTPS."""
        if not value.startswith("https://"):
            raise ValueError("Webhook URL must use HTTPS")
        return value

    @validates("events")
    def validate_events(self, key: str, value: List[str]) -> List[str]:
        """Validate events list is not empty."""
        if not value or len(value) == 0:
            raise ValueError("Webhook must subscribe to at least one event")
        return value

    def __repr__(self) -> str:
        return f"<Webhook(id={self.id}, account_id={self.account_id}, enabled={self.enabled}, events={len(self.events)})>"
```

### Extended Execution Model

```python
# src/mcpworks_api/models/execution.py

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from .base import Base, UUIDMixin


class Execution(Base, UUIDMixin):
    """
    Execution model for tracking function invocations.

    EXTENDED for A0 with:
    - Function relationship (instead of generic service)
    - Version tracking
    - Backend-specific metadata
    - Detailed timing metrics

    Relationships:
    - function: The function that was executed
    - user: The user who initiated execution (via API key)
    """

    __tablename__ = "executions"

    # Foreign Keys
    function_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("functions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Function that was executed"
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="User who initiated execution"
    )

    # Execution Metadata
    function_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Function version that was executed"
    )

    backend: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Backend that executed the function"
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        doc="Execution status (pending, running, completed, failed, timeout)"
    )

    # Timing Metrics
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        doc="When execution was initiated"
    )

    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When execution started running"
    )

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When execution completed or failed"
    )

    duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Execution duration in milliseconds"
    )

    # Input/Output Data
    input_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        doc="Function input parameters"
    )

    result_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        doc="Function output or error details"
    )

    # Backend-Specific Metadata
    backend_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        doc="Backend-specific execution metadata"
    )

    # Execution is counted against user's usage limit
    # No per-execution cost tracking needed with subscription model

    # Relationships
    function: Mapped["Function"] = relationship(
        "Function",
        back_populates="executions"
    )

    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="executions"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'timeout')",
            name="execution_status_valid"
        ),
        CheckConstraint(
            "backend IN ('code_sandbox', 'activepieces', 'nanobot', 'github_repo')",
            name="execution_backend_valid"
        ),
        CheckConstraint(
            "duration_ms >= 0",
            name="execution_duration_positive"
        ),
        Index("ix_executions_function_id", "function_id"),
        Index("ix_executions_user_id", "user_id"),
        Index("ix_executions_status", "status"),
        Index("ix_executions_created_at", "created_at"),
        Index("ix_executions_function_created", "function_id", "created_at"),
    )

    @validates("status")
    def validate_status(self, key: str, value: str) -> str:
        """Validate status is one of allowed values."""
        allowed_statuses = {"pending", "running", "completed", "failed", "timeout"}
        if value not in allowed_statuses:
            raise ValueError(f"Status must be one of {allowed_statuses}")
        return value

    @validates("backend")
    def validate_backend(self, key: str, value: str) -> str:
        """Validate backend is one of supported types."""
        allowed_backends = {"code_sandbox", "activepieces", "nanobot", "github_repo"}
        if value not in allowed_backends:
            raise ValueError(f"Backend must be one of {allowed_backends}")
        return value

    def __repr__(self) -> str:
        return f"<Execution(id={self.id}, function_id={self.function_id}, status={self.status}, v={self.function_version})>"
```

---

## Pydantic Schemas

### Namespace Schemas

```python
# src/mcpworks_api/schemas/namespace.py

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
import re


class NamespaceBase(BaseModel):
    """Base namespace fields."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=63,
        description="Namespace name (DNS-compliant)",
        examples=["acme", "my-company", "prod-env"]
    )

    description: Optional[str] = Field(
        None,
        max_length=1000,
        description="Human-readable description"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate namespace name follows DNS rules."""
        if not re.match(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", v):
            raise ValueError(
                "Namespace name must be lowercase alphanumeric with hyphens, "
                "starting and ending with alphanumeric character"
            )
        return v.lower()


class NamespaceCreate(NamespaceBase):
    """Schema for creating a namespace."""

    network_whitelist: Optional[List[str]] = Field(
        None,
        description="Optional IP whitelist (CIDR format)",
        examples=[["192.168.1.0/24", "10.0.0.1"]]
    )


class NamespaceUpdate(BaseModel):
    """Schema for updating a namespace."""

    description: Optional[str] = Field(None, max_length=1000)
    network_whitelist: Optional[List[str]] = None


class NamespaceResponse(NamespaceBase):
    """Schema for namespace responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    network_whitelist: Optional[List[str]] = None
    whitelist_updated_at: Optional[datetime] = None
    whitelist_changes_today: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Computed fields
    create_endpoint: str = Field(
        ...,
        description="Management endpoint URL"
    )
    run_endpoint: str = Field(
        ...,
        description="Execution endpoint URL"
    )

    @property
    def create_endpoint(self) -> str:
        """Compute create endpoint URL."""
        return f"https://{self.name}.create.mcpworks.io"

    @property
    def run_endpoint(self) -> str:
        """Compute run endpoint URL."""
        return f"https://{self.name}.run.mcpworks.io"


class NamespaceList(BaseModel):
    """Schema for paginated namespace list."""

    namespaces: List[NamespaceResponse]
    total: int
    page: int = 1
    page_size: int = 50
    has_more: bool
```

### Service Schemas

```python
# src/mcpworks_api/schemas/service.py

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
import re


class ServiceBase(BaseModel):
    """Base service fields."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=63,
        description="Service name (URL-safe)",
        examples=["auth", "payment-processing", "data_sync"]
    )

    description: Optional[str] = Field(
        None,
        max_length=1000,
        description="Human-readable description"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate service name is URL-safe."""
        if not re.match(r"^[a-z0-9]([a-z0-9-_]{0,61}[a-z0-9])?$", v):
            raise ValueError(
                "Service name must be lowercase alphanumeric with hyphens/underscores"
            )
        return v.lower()


class ServiceCreate(ServiceBase):
    """Schema for creating a service."""
    pass


class ServiceUpdate(BaseModel):
    """Schema for updating a service."""

    description: Optional[str] = Field(None, max_length=1000)


class ServiceResponse(ServiceBase):
    """Schema for service responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    namespace_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    function_count: int = Field(
        default=0,
        description="Number of functions in this service"
    )


class ServiceList(BaseModel):
    """Schema for service list."""

    services: List[ServiceResponse]
    total: int
```

### Function Schemas

```python
# src/mcpworks_api/schemas/function.py

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
import re


class FunctionBase(BaseModel):
    """Base function fields."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=63,
        description="Function name (URL-safe)",
        examples=["authenticate_user", "process-payment", "sync_data"]
    )

    description: Optional[str] = Field(
        None,
        max_length=1000,
        description="Human-readable description"
    )

    tags: Optional[List[str]] = Field(
        None,
        description="Tags for categorization",
        examples=[["auth", "security"], ["payment", "stripe"]]
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate function name is URL-safe."""
        if not re.match(r"^[a-z0-9]([a-z0-9-_]{0,61}[a-z0-9])?$", v):
            raise ValueError(
                "Function name must be lowercase alphanumeric with hyphens/underscores"
            )
        return v.lower()


class FunctionVersionCreate(BaseModel):
    """Schema for creating a function version."""

    backend: str = Field(
        ...,
        description="Function backend",
        examples=["code_sandbox", "activepieces"]
    )

    code: Optional[str] = Field(
        None,
        description="Function code (for code_sandbox backend)"
    )

    config: Optional[Dict[str, Any]] = Field(
        None,
        description="Backend-specific configuration"
    )

    input_schema: Optional[Dict[str, Any]] = Field(
        None,
        description="JSON Schema for input validation"
    )

    output_schema: Optional[Dict[str, Any]] = Field(
        None,
        description="JSON Schema for output validation"
    )

    @field_validator("backend")
    @classmethod
    def validate_backend(cls, v: str) -> str:
        """Validate backend is supported."""
        allowed = {"code_sandbox", "activepieces", "nanobot", "github_repo"}
        if v not in allowed:
            raise ValueError(f"Backend must be one of {allowed}")
        return v


class FunctionCreate(FunctionBase):
    """Schema for creating a function."""

    initial_version: FunctionVersionCreate = Field(
        ...,
        description="Initial function version"
    )


class FunctionUpdate(BaseModel):
    """Schema for updating a function (creates new version)."""

    description: Optional[str] = Field(None, max_length=1000)
    tags: Optional[List[str]] = None
    new_version: Optional[FunctionVersionCreate] = Field(
        None,
        description="New function version (creates and activates)"
    )


class FunctionVersionResponse(BaseModel):
    """Schema for function version responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    function_id: str
    version: int
    backend: str
    code: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    created_at: datetime


class FunctionResponse(FunctionBase):
    """Schema for function responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    service_id: str
    active_version: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Optional expanded fields
    active_version_details: Optional[FunctionVersionResponse] = None
    execution_count: int = Field(
        default=0,
        description="Total number of executions"
    )


class FunctionList(BaseModel):
    """Schema for function list."""

    functions: List[FunctionResponse]
    total: int
    page: int = 1
    page_size: int = 50
    has_more: bool
```

### Execution Schemas

```python
# src/mcpworks_api/schemas/execution.py

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class ExecutionCreate(BaseModel):
    """Schema for creating an execution."""

    input_data: Dict[str, Any] = Field(
        ...,
        description="Function input parameters"
    )


class ExecutionResponse(BaseModel):
    """Schema for execution responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    function_id: str
    user_id: Optional[str] = None
    function_version: int
    backend: str
    status: str

    # Timing
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None

    # Data
    input_data: Optional[Dict[str, Any]] = None
    result_data: Optional[Dict[str, Any]] = None
    backend_metadata: Optional[Dict[str, Any]] = None


class ExecutionList(BaseModel):
    """Schema for execution list."""

    executions: List[ExecutionResponse]
    total: int
    page: int = 1
    page_size: int = 50
    has_more: bool
```

### Webhook Schemas

```python
# src/mcpworks_api/schemas/webhook.py

from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WebhookBase(BaseModel):
    """Base webhook fields."""

    url: str = Field(
        ...,
        description="Webhook delivery URL (HTTPS required)",
        examples=["https://api.example.com/webhooks/mcpworks"]
    )

    events: List[str] = Field(
        ...,
        min_length=1,
        description="Event types to subscribe to",
        examples=[["function.execution.completed", "function.execution.failed"]]
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate webhook URL is HTTPS."""
        if not v.startswith("https://"):
            raise ValueError("Webhook URL must use HTTPS")
        return v


class WebhookCreate(WebhookBase):
    """Schema for creating a webhook."""

    secret: str = Field(
        ...,
        min_length=32,
        description="Webhook secret for signature verification (will be hashed)"
    )


class WebhookUpdate(BaseModel):
    """Schema for updating a webhook."""

    url: Optional[str] = None
    events: Optional[List[str]] = None
    enabled: Optional[bool] = None
    secret: Optional[str] = Field(
        None,
        min_length=32,
        description="New webhook secret (will be hashed)"
    )


class WebhookResponse(BaseModel):
    """Schema for webhook responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    url: str
    events: List[str]
    enabled: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


class WebhookList(BaseModel):
    """Schema for webhook list."""

    webhooks: List[WebhookResponse]
    total: int
```

### Security Event Schemas

```python
# src/mcpworks_api/schemas/security_event.py

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SecurityEventResponse(BaseModel):
    """Schema for security event responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    timestamp: datetime
    event_type: str
    actor_ip: Optional[str] = None
    actor_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    severity: str


class SecurityEventList(BaseModel):
    """Schema for security event list."""

    events: List[SecurityEventResponse]
    total: int
    page: int = 1
    page_size: int = 50
    has_more: bool
```

---

## Alembic Migrations

### Migration: Add A0 Platform Models

```python
# alembic/versions/001_add_a0_platform_models.py

"""Add A0 platform models (namespaces, services, functions, security)

Revision ID: 001_a0_platform
Revises: <previous_revision>
Create Date: 2026-02-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_a0_platform'
down_revision: Union[str, None] = '<previous_revision>'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create namespaces table
    op.create_table(
        'namespaces',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('account_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=63), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('network_whitelist', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('whitelist_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('whitelist_changes_today', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('name'),
        sa.CheckConstraint(
            "name ~ '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$'",
            name='namespace_name_format'
        ),
        sa.CheckConstraint(
            'whitelist_changes_today >= 0',
            name='whitelist_changes_positive'
        )
    )
    op.create_index('ix_namespaces_account_id', 'namespaces', ['account_id'])
    op.create_index('ix_namespaces_name', 'namespaces', ['name'])

    # Create services table
    op.create_table(
        'services',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('namespace_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=63), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['namespace_id'], ['namespaces.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('namespace_id', 'name', name='uq_service_namespace_name'),
        sa.CheckConstraint(
            "name ~ '^[a-z0-9]([a-z0-9-_]{0,61}[a-z0-9])?$'",
            name='service_name_format'
        )
    )
    op.create_index('ix_services_namespace_id', 'services', ['namespace_id'])
    op.create_index('ix_services_name', 'services', ['name'])

    # Create functions table
    op.create_table(
        'functions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('service_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=63), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('tags', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('active_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('service_id', 'name', name='uq_function_service_name'),
        sa.CheckConstraint(
            "name ~ '^[a-z0-9]([a-z0-9-_]{0,61}[a-z0-9])?$'",
            name='function_name_format'
        ),
        sa.CheckConstraint(
            'active_version > 0',
            name='function_active_version_positive'
        )
    )
    op.create_index('ix_functions_service_id', 'functions', ['service_id'])
    op.create_index('ix_functions_name', 'functions', ['name'])
    op.create_index('ix_functions_tags', 'functions', ['tags'], postgresql_using='gin')

    # Create function_versions table
    op.create_table(
        'function_versions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('function_id', sa.String(length=36), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('backend', sa.String(length=50), nullable=False),
        sa.Column('code', sa.Text(), nullable=True),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('input_schema', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('output_schema', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['function_id'], ['functions.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('function_id', 'version', name='uq_function_version_number'),
        sa.CheckConstraint(
            'version > 0',
            name='function_version_positive'
        ),
        sa.CheckConstraint(
            "backend IN ('code_sandbox', 'activepieces', 'nanobot', 'github_repo')",
            name='function_version_backend_valid'
        )
    )
    op.create_index('ix_function_versions_function_id', 'function_versions', ['function_id'])
    op.create_index('ix_function_versions_version', 'function_versions', ['function_id', 'version'])
    op.create_index('ix_function_versions_backend', 'function_versions', ['backend'])

    # Create security_events table
    op.create_table(
        'security_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('actor_ip', postgresql.INET(), nullable=True),
        sa.Column('actor_id', sa.String(length=255), nullable=True),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'error', 'critical')",
            name='security_event_severity_valid'
        )
    )
    op.create_index('ix_security_events_timestamp', 'security_events', ['timestamp'])
    op.create_index('ix_security_events_event_type', 'security_events', ['event_type'])
    op.create_index('ix_security_events_severity', 'security_events', ['severity'])
    op.create_index('ix_security_events_actor_id', 'security_events', ['actor_id'])
    op.create_index('ix_security_events_timestamp_severity', 'security_events', ['timestamp', 'severity'])

    # Create webhooks table
    op.create_table(
        'webhooks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('account_id', sa.String(length=36), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('secret_hash', sa.String(length=255), nullable=False),
        sa.Column('events', postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.CheckConstraint(
            "url ~ '^https://'",
            name='webhook_url_https'
        )
    )
    op.create_index('ix_webhooks_account_id', 'webhooks', ['account_id'])
    op.create_index('ix_webhooks_enabled', 'webhooks', ['enabled'])
    op.create_index('ix_webhooks_events', 'webhooks', ['events'], postgresql_using='gin')

    # Extend executions table with A0 fields
    op.add_column('executions', sa.Column('function_id', sa.String(length=36), nullable=True))
    op.add_column('executions', sa.Column('function_version', sa.Integer(), nullable=True))
    op.add_column('executions', sa.Column('backend', sa.String(length=50), nullable=True))
    op.add_column('executions', sa.Column('started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('executions', sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('executions', sa.Column('duration_ms', sa.Integer(), nullable=True))
    op.add_column('executions', sa.Column('backend_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_foreign_key(
        'fk_executions_function_id',
        'executions',
        'functions',
        ['function_id'],
        ['id'],
        ondelete='CASCADE'
    )
    op.create_index('ix_executions_function_id', 'executions', ['function_id'])
    op.create_index('ix_executions_function_created', 'executions', ['function_id', 'created_at'])

    # Add relationship to Account model
    # (Assumes accounts table exists with back_populates configuration)


def downgrade() -> None:
    # Drop indexes and foreign keys from executions
    op.drop_index('ix_executions_function_created', table_name='executions')
    op.drop_index('ix_executions_function_id', table_name='executions')
    op.drop_constraint('fk_executions_function_id', 'executions', type_='foreignkey')

    # Drop columns from executions
    op.drop_column('executions', 'backend_metadata')
    op.drop_column('executions', 'duration_ms')
    op.drop_column('executions', 'completed_at')
    op.drop_column('executions', 'started_at')
    op.drop_column('executions', 'backend')
    op.drop_column('executions', 'function_version')
    op.drop_column('executions', 'function_id')

    # Drop webhooks table
    op.drop_index('ix_webhooks_events', table_name='webhooks')
    op.drop_index('ix_webhooks_enabled', table_name='webhooks')
    op.drop_index('ix_webhooks_account_id', table_name='webhooks')
    op.drop_table('webhooks')

    # Drop security_events table
    op.drop_index('ix_security_events_timestamp_severity', table_name='security_events')
    op.drop_index('ix_security_events_actor_id', table_name='security_events')
    op.drop_index('ix_security_events_severity', table_name='security_events')
    op.drop_index('ix_security_events_event_type', table_name='security_events')
    op.drop_index('ix_security_events_timestamp', table_name='security_events')
    op.drop_table('security_events')

    # Drop function_versions table
    op.drop_index('ix_function_versions_backend', table_name='function_versions')
    op.drop_index('ix_function_versions_version', table_name='function_versions')
    op.drop_index('ix_function_versions_function_id', table_name='function_versions')
    op.drop_table('function_versions')

    # Drop functions table
    op.drop_index('ix_functions_tags', table_name='functions')
    op.drop_index('ix_functions_name', table_name='functions')
    op.drop_index('ix_functions_service_id', table_name='functions')
    op.drop_table('functions')

    # Drop services table
    op.drop_index('ix_services_name', table_name='services')
    op.drop_index('ix_services_namespace_id', table_name='services')
    op.drop_table('services')

    # Drop namespaces table
    op.drop_index('ix_namespaces_name', table_name='namespaces')
    op.drop_index('ix_namespaces_account_id', table_name='namespaces')
    op.drop_table('namespaces')
```

---

## Integration Notes

### Existing Model Relationships

The A0 models integrate with existing `mcpworks-api` models as follows:

#### Account Model Extension

```python
# Add to existing Account model (src/mcpworks_api/models/account.py)

from sqlalchemy.orm import relationship

class Account(Base, UUIDMixin, TimestampMixin):
    # ... existing fields ...

    # New A0 relationships
    namespaces: Mapped[List["Namespace"]] = relationship(
        "Namespace",
        back_populates="account",
        cascade="all, delete-orphan"
    )

    webhooks: Mapped[List["Webhook"]] = relationship(
        "Webhook",
        back_populates="account",
        cascade="all, delete-orphan"
    )
```

#### User Model Extension

```python
# Add to existing User model (src/mcpworks_api/models/user.py)

from sqlalchemy.orm import relationship

class User(Base, UUIDMixin, TimestampMixin):
    # ... existing fields ...

    # New A0 relationship
    executions: Mapped[List["Execution"]] = relationship(
        "Execution",
        back_populates="user",
        order_by="desc(Execution.created_at)"
    )
```

#### APIKey Model Extension

```python
# Add to existing APIKey model (src/mcpworks_api/models/api_key.py)

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

class APIKey(Base, UUIDMixin, TimestampMixin):
    # ... existing fields ...

    # New A0 field - scope to namespace
    namespace_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("namespaces.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        doc="Optional namespace scope for this API key"
    )

    # New A0 relationship
    namespace: Mapped[Optional["Namespace"]] = relationship(
        "Namespace",
        back_populates="api_keys"
    )
```

### Data Hierarchy

```
Account
  ├── Subscription (existing)
  ├── UsageRecord (usage per billing period)
  ├── Namespace (A0 new)
  │     ├── APIKey (scoped to namespace)
  │     └── Service (A0 new)
  │           └── Function (A0 new)
  │                 ├── FunctionVersion (A0 new, immutable)
  │                 └── Execution (A0 extended)
  └── Webhook (A0 new)

User
  ├── APIKey (existing)
  └── Execution (A0 relationship)

SecurityEvent (A0 new, global audit log)
```

### Multi-Tenancy Pattern

All resources follow this isolation pattern:

1. **Account** - Billing boundary
2. **Namespace** - DNS boundary, organizational unit
3. **Service** - Logical grouping within namespace
4. **Function** - Executable unit within service

Query pattern for isolation:

```python
# Example: Get all functions for a specific account
async def get_account_functions(
    session: AsyncSession,
    account_id: str
) -> List[Function]:
    stmt = (
        select(Function)
        .join(Service)
        .join(Namespace)
        .where(Namespace.account_id == account_id)
    )
    result = await session.execute(stmt)
    return result.scalars().all()
```

---

## Security Considerations

### 1. Network Whitelisting

**Rate Limiting:**
- Max 5 whitelist changes per 24 hours per namespace
- `whitelist_changes_today` counter resets daily via background task
- Prevents rapid whitelist manipulation attacks

**Implementation:**

```python
async def update_namespace_whitelist(
    session: AsyncSession,
    namespace: Namespace,
    new_whitelist: List[str]
) -> None:
    if not namespace.can_update_whitelist():
        raise TooManyWhitelistChanges(
            "Maximum 5 whitelist changes per 24 hours"
        )

    namespace.network_whitelist = new_whitelist
    namespace.whitelist_updated_at = datetime.utcnow()
    namespace.whitelist_changes_today += 1

    # Log security event
    await log_security_event(
        session=session,
        event_type="namespace.whitelist_updated",
        severity="info",
        actor_id=namespace.account_id,
        details={"namespace_id": namespace.id}
    )
```

### 2. Webhook Secret Hashing

**Never store webhook secrets in plaintext:**

```python
import hashlib
import secrets

def hash_webhook_secret(secret: str) -> str:
    """Hash webhook secret using SHA-256."""
    return hashlib.sha256(secret.encode()).hexdigest()

def verify_webhook_signature(
    payload: bytes,
    signature: str,
    secret_hash: str
) -> bool:
    """Verify webhook HMAC signature."""
    import hmac

    # Note: In production, you'd need to store the secret separately
    # for signature generation. This is a simplified example.
    expected = hmac.new(
        secret_hash.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected)
```

### 3. Security Event Logging

**Log all security-relevant events:**

```python
async def log_security_event(
    session: AsyncSession,
    event_type: str,
    severity: str,
    actor_ip: Optional[str] = None,
    actor_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> SecurityEvent:
    """
    Create security event log entry.

    Event types:
    - auth.* (login_failed, api_key_created, etc.)
    - namespace.* (created, whitelist_updated, etc.)
    - function.* (created, execution_blocked, etc.)
    - admin.* (user_suspended, etc.)
    """
    event = SecurityEvent(
        event_type=event_type,
        severity=severity,
        actor_ip=actor_ip,
        actor_id=actor_id,
        details=details or {}
    )

    session.add(event)
    await session.flush()

    # Critical events trigger immediate alerts
    if severity == "critical":
        await trigger_security_alert(event)

    return event
```

### 4. IP Hashing for Privacy

**Hash IP addresses for long-term storage:**

```python
def hash_ip_address(ip: str, salt: str) -> str:
    """Hash IP address for privacy while maintaining analytics."""
    return hashlib.sha256(f"{ip}{salt}".encode()).hexdigest()[:16]
```

### 5. Function Code Sandboxing

**Never execute user code without sandboxing:**

- Code Sandbox backend uses nsjail isolation
- Separate process with resource limits
- Network restrictions
- File system isolation

See: [Code Execution Sandbox Specification](../../../mcpworks-internals/docs/implementation/code-execution-sandbox-specification.md)

---

## Performance Optimizations

### 1. Strategic Indexes

**Query Pattern Analysis:**

```python
# Common queries and their indexes:

# 1. List namespaces for account
# Index: ix_namespaces_account_id
SELECT * FROM namespaces WHERE account_id = ?

# 2. Lookup namespace by name
# Index: ix_namespaces_name (unique)
SELECT * FROM namespaces WHERE name = ?

# 3. List services in namespace
# Index: ix_services_namespace_id
SELECT * FROM services WHERE namespace_id = ?

# 4. List functions in service
# Index: ix_functions_service_id
SELECT * FROM functions WHERE service_id = ?

# 5. Get function by service + name
# Index: uq_function_service_name (unique constraint)
SELECT * FROM functions WHERE service_id = ? AND name = ?

# 6. Get active function version
# Index: ix_function_versions_version (composite: function_id, version)
SELECT * FROM function_versions
WHERE function_id = ? AND version = ?

# 7. List executions for function
# Index: ix_executions_function_created (composite: function_id, created_at)
SELECT * FROM executions
WHERE function_id = ?
ORDER BY created_at DESC

# 8. Find functions by tag
# Index: ix_functions_tags (GIN index for array containment)
SELECT * FROM functions WHERE tags @> ARRAY['auth']

# 9. Security event queries
# Index: ix_security_events_timestamp_severity (composite)
SELECT * FROM security_events
WHERE timestamp > ? AND severity = 'critical'
```

### 2. JSONB for Flexible Metadata

**Use JSONB for schema-flexible data:**

- `function_versions.config` - Backend-specific configuration
- `function_versions.input_schema` / `output_schema` - JSON Schema definitions
- `executions.backend_metadata` - Backend-specific execution details
- `security_events.details` - Event-specific data

**JSONB supports indexing:**

```sql
-- Index specific JSONB keys if needed
CREATE INDEX ix_executions_backend_metadata_job_id
ON executions ((backend_metadata->>'job_id'));
```

### 3. Partial Indexes

**Index only relevant rows:**

```sql
-- Index only active webhooks
CREATE INDEX ix_webhooks_enabled_true
ON webhooks (account_id)
WHERE enabled = true;

-- Index only recent security events
CREATE INDEX ix_security_events_recent
ON security_events (timestamp, severity)
WHERE timestamp > NOW() - INTERVAL '30 days';
```

### 4. Connection Pooling

**Use asyncpg with connection pooling:**

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Create engine with pool configuration
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,  # Base pool size
    max_overflow=10,  # Additional connections under load
    pool_pre_ping=True,  # Verify connections before use
    pool_recycle=3600,  # Recycle connections after 1 hour
)

# Create async session factory
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)
```

### 5. Eager Loading for Relationships

**Avoid N+1 queries with selectinload:**

```python
from sqlalchemy.orm import selectinload

# Load functions with their active version in one query
async def get_functions_with_versions(
    session: AsyncSession,
    service_id: str
) -> List[Function]:
    stmt = (
        select(Function)
        .where(Function.service_id == service_id)
        .options(selectinload(Function.versions))
    )
    result = await session.execute(stmt)
    return result.scalars().all()
```

### 6. Query Result Caching

**Cache expensive queries with Redis:**

```python
import json
from typing import Optional
import redis.asyncio as redis

redis_client = redis.from_url("redis://localhost:6379")

async def get_namespace_cached(
    session: AsyncSession,
    namespace_name: str
) -> Optional[Namespace]:
    # Check cache first
    cache_key = f"namespace:{namespace_name}"
    cached = await redis_client.get(cache_key)

    if cached:
        # Return cached result (would need deserialization)
        return Namespace(**json.loads(cached))

    # Query database
    stmt = select(Namespace).where(Namespace.name == namespace_name)
    result = await session.execute(stmt)
    namespace = result.scalar_one_or_none()

    if namespace:
        # Cache for 5 minutes
        await redis_client.setex(
            cache_key,
            300,
            json.dumps(namespace.to_dict())
        )

    return namespace
```

---

## Example Usage

### Creating a Complete Function

```python
from sqlalchemy.ext.asyncio import AsyncSession
from mcpworks_api.models import Namespace, Service, Function, FunctionVersion
from mcpworks_api.schemas import (
    NamespaceCreate,
    ServiceCreate,
    FunctionCreate,
    FunctionVersionCreate
)

async def create_complete_function(
    session: AsyncSession,
    account_id: str
) -> Function:
    """Example: Create namespace → service → function → version."""

    # 1. Create namespace
    namespace = Namespace(
        account_id=account_id,
        name="acme-prod",
        description="ACME Corp production environment"
    )
    session.add(namespace)
    await session.flush()

    # 2. Create service
    service = Service(
        namespace_id=namespace.id,
        name="auth",
        description="Authentication service"
    )
    session.add(service)
    await session.flush()

    # 3. Create function
    function = Function(
        service_id=service.id,
        name="verify_token",
        description="Verify JWT token",
        tags=["auth", "security"],
        active_version=1
    )
    session.add(function)
    await session.flush()

    # 4. Create initial version
    version = FunctionVersion(
        function_id=function.id,
        version=1,
        backend="code_sandbox",
        code="""
def verify_token(token: str) -> dict:
    import jwt
    return jwt.decode(token, verify=False)
""",
        input_schema={
            "type": "object",
            "properties": {
                "token": {"type": "string"}
            },
            "required": ["token"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "sub": {"type": "string"},
                "exp": {"type": "number"}
            }
        }
    )
    session.add(version)
    await session.commit()

    return function
```

### Executing a Function

```python
from mcpworks_api.models import Execution
from datetime import datetime

async def execute_function(
    session: AsyncSession,
    function: Function,
    user_id: str,
    input_data: dict
) -> Execution:
    """Example: Execute a function and track execution."""

    # Get active version
    active_version = function.get_active_version_obj()

    # Create execution record
    execution = Execution(
        function_id=function.id,
        user_id=user_id,
        function_version=active_version.version,
        backend=active_version.backend,
        status="pending",
        input_data=input_data
    )
    session.add(execution)
    await session.flush()

    try:
        # Mark as running
        execution.status = "running"
        execution.started_at = datetime.utcnow()
        await session.flush()

        # Execute via backend (pseudo-code)
        result = await execute_on_backend(
            backend=active_version.backend,
            code=active_version.code,
            input_data=input_data
        )

        # Mark as completed
        execution.status = "completed"
        execution.completed_at = datetime.utcnow()
        execution.duration_ms = int(
            (execution.completed_at - execution.started_at).total_seconds() * 1000
        )
        execution.result_data = result

    except Exception as e:
        # Mark as failed
        execution.status = "failed"
        execution.completed_at = datetime.utcnow()
        execution.result_data = {"error": str(e)}

        # Log security event for failures
        await log_security_event(
            session=session,
            event_type="function.execution.failed",
            severity="warning",
            actor_id=user_id,
            details={
                "function_id": function.id,
                "execution_id": execution.id,
                "error": str(e)
            }
        )

    await session.commit()
    return execution
```

---

## File Locations

This specification assumes the following directory structure in `mcpworks-api`:

```
mcpworks-api/
├── src/
│   └── mcpworks_api/
│       ├── models/
│       │   ├── __init__.py
│       │   ├── base.py              # UUIDMixin, TimestampMixin, Base
│       │   ├── account.py           # Account (existing + extensions)
│       │   ├── user.py              # User (existing + extensions)
│       │   ├── api_key.py           # APIKey (existing + extensions)
│       │   ├── namespace.py         # Namespace (A0 new)
│       │   ├── service.py           # Service (A0 new)
│       │   ├── function.py          # Function (A0 new)
│       │   ├── function_version.py  # FunctionVersion (A0 new)
│       │   ├── execution.py         # Execution (A0 extended)
│       │   ├── security_event.py    # SecurityEvent (A0 new)
│       │   └── webhook.py           # Webhook (A0 new)
│       │
│       └── schemas/
│           ├── __init__.py
│           ├── namespace.py         # Namespace schemas
│           ├── service.py           # Service schemas
│           ├── function.py          # Function schemas
│           ├── execution.py         # Execution schemas
│           ├── webhook.py           # Webhook schemas
│           └── security_event.py    # SecurityEvent schemas
│
├── alembic/
│   └── versions/
│       └── 001_add_a0_platform_models.py
│
└── docs/
    └── implementation/
        └── database-models-specification.md  # This file
```

---

## Next Steps

1. **Implementation Order:**
   - [ ] Create base mixins (UUIDMixin, TimestampMixin)
   - [ ] Implement Namespace model and schemas
   - [ ] Implement Service model and schemas
   - [ ] Implement Function and FunctionVersion models
   - [ ] Extend Execution model
   - [ ] Implement SecurityEvent model
   - [ ] Implement Webhook model
   - [ ] Create Alembic migration
   - [ ] Add relationship extensions to existing models
   - [ ] Write unit tests for models and schemas

2. **Testing Strategy:**
   - Model validation tests (field constraints, validators)
   - Relationship tests (cascade deletes, back_populates)
   - Migration tests (upgrade/downgrade)
   - Query performance tests (index effectiveness)
   - Schema serialization tests (Pydantic validation)

3. **Documentation:**
   - API endpoint documentation using these schemas
   - Database schema diagram (ERD)
   - Query optimization guide
   - Security event catalog

4. **Integration:**
   - Update existing Account/User models with new relationships
   - Create database seeding scripts for development
   - Add monitoring for query performance
   - Implement security event alerting

---

## Changelog

**Version 1.0.0** (2026-02-09)
- Initial specification
- Complete SQLAlchemy models for A0 platform
- Pydantic schemas for all models
- Alembic migration for database setup
- Integration notes with existing models
- Security and performance guidance

---

**End of Specification**