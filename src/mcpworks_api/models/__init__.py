"""SQLAlchemy models for mcpworks API."""

from mcpworks_api.models.account import Account
from mcpworks_api.models.agent import (
    Agent,
    AgentChannel,
    AgentReplica,
    AgentRun,
    AgentSchedule,
    AgentState,
    AgentWebhook,
    ScheduledJob,
)
from mcpworks_api.models.agent_tool_call import AgentToolCall
from mcpworks_api.models.api_key import APIKey
from mcpworks_api.models.audit_log import AuditAction, AuditLog
from mcpworks_api.models.base import Base, TimestampMixin, UUIDMixin
from mcpworks_api.models.email_log import EmailLog
from mcpworks_api.models.execution import Execution, ExecutionStatus
from mcpworks_api.models.function import Function
from mcpworks_api.models.function_version import ALLOWED_BACKENDS, FunctionVersion
from mcpworks_api.models.mcp_execution_stat import McpExecutionStat
from mcpworks_api.models.mcp_proxy_call import McpProxyCall
from mcpworks_api.models.namespace import Namespace
from mcpworks_api.models.namespace_git_remote import NamespaceGitRemote
from mcpworks_api.models.namespace_mcp_server import NamespaceMcpServer
from mcpworks_api.models.namespace_service import NamespaceService
from mcpworks_api.models.namespace_share import NamespaceShare, ShareStatus
from mcpworks_api.models.oauth_account import OAuthAccount
from mcpworks_api.models.procedure import Procedure, ProcedureExecution, ProcedureVersion
from mcpworks_api.models.schedule_fire import ScheduleFire
from mcpworks_api.models.security_event import ALLOWED_SEVERITIES, SecurityEvent
from mcpworks_api.models.service import Service, ServiceStatus
from mcpworks_api.models.subscription import (
    AGENT_TIER_CONFIG,
    Subscription,
    SubscriptionStatus,
    SubscriptionTier,
)
from mcpworks_api.models.user import User, UserStatus, UserTier
from mcpworks_api.models.webhook import Webhook

__all__ = [
    # Base
    "Base",
    "TimestampMixin",
    "UUIDMixin",
    # Account (A0)
    "Account",
    # Agent (Containerized Agents)
    "Agent",
    "AgentRun",
    "AgentSchedule",
    "AgentWebhook",
    "AgentState",
    "AgentChannel",
    "AgentReplica",
    "AgentToolCall",
    "ScheduledJob",
    "AGENT_TIER_CONFIG",
    # User
    "User",
    "UserTier",
    "UserStatus",
    # APIKey
    "APIKey",
    # Namespace (A0)
    "Namespace",
    # McpProxyCall / McpExecutionStat (analytics)
    "McpProxyCall",
    "McpExecutionStat",
    # NamespaceGitRemote
    "NamespaceGitRemote",
    # NamespaceMcpServer
    "NamespaceMcpServer",
    # NamespaceService (A0)
    "NamespaceService",
    # NamespaceShare
    "NamespaceShare",
    "ShareStatus",
    # Function (A0)
    "Function",
    "FunctionVersion",
    "ALLOWED_BACKENDS",
    # Service (Backend Registry)
    "Service",
    "ServiceStatus",
    # Execution
    "Execution",
    "ExecutionStatus",
    # Subscription
    "Subscription",
    "SubscriptionStatus",
    "SubscriptionTier",
    # AuditLog
    "AuditLog",
    "AuditAction",
    # EmailLog
    "EmailLog",
    # OAuthAccount
    "OAuthAccount",
    # SecurityEvent (A0)
    "SecurityEvent",
    "ALLOWED_SEVERITIES",
    # Procedure
    "Procedure",
    "ProcedureVersion",
    "ProcedureExecution",
    # ScheduleFire (Orchestration Observability)
    "ScheduleFire",
    # Webhook (A0)
    "Webhook",
]
