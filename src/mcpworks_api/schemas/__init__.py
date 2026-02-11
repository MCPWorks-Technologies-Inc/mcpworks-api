"""Pydantic schemas for API request/response validation."""

from mcpworks_api.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    TokenRequest,
    TokenResponse,
    UserInfo,
)
from mcpworks_api.schemas.common import ErrorResponse, PaginatedResponse, SuccessResponse
from mcpworks_api.schemas.function import (
    FunctionBase,
    FunctionCreate,
    FunctionList,
    FunctionResponse,
    FunctionUpdate,
    FunctionVersionCreate,
    FunctionVersionResponse,
)

# A0 Namespace Platform Schemas
from mcpworks_api.schemas.namespace import (
    NamespaceBase,
    NamespaceCreate,
    NamespaceList,
    NamespaceResponse,
    NamespaceUpdate,
)
from mcpworks_api.schemas.namespace_service import (
    NamespaceServiceBase,
    NamespaceServiceCreate,
    NamespaceServiceList,
    NamespaceServiceResponse,
    NamespaceServiceUpdate,
)
from mcpworks_api.schemas.security_event import (
    SecurityEventList,
    SecurityEventResponse,
)
from mcpworks_api.schemas.service import (
    AgentCallbackRequest,
    AgentCallbackResponse,
    AgentExecuteRequest,
    AgentExecuteResponse,
    ExecutionInfo,
    ExecutionList,
    MathHelpRequest,
    MathHelpResponse,
    MathVerifyRequest,
    MathVerifyResponse,
    ServiceCatalog,
    ServiceInfo,
    ServiceProxyResponse,
)
from mcpworks_api.schemas.subscription import (
    CancelSubscriptionResponse,
    CheckoutSessionResponse,
    CreateSubscriptionRequest,
    SubscriptionInfo,
    WebhookResponse,
)
from mcpworks_api.schemas.user import (
    ApiKeyCreated,
    ApiKeyList,
    ApiKeySummary,
    CreateApiKeyRequest,
    UserProfile,
)
from mcpworks_api.schemas.webhook import (
    WebhookBase,
    WebhookCreate,
    WebhookList,
    WebhookUpdate,
)
from mcpworks_api.schemas.webhook import (
    WebhookResponse as WebhookEndpointResponse,
)

__all__ = [
    # Common
    "ErrorResponse",
    "SuccessResponse",
    "PaginatedResponse",
    # Auth
    "RegisterRequest",
    "RegisterResponse",
    "LoginRequest",
    "LoginResponse",
    "TokenRequest",
    "TokenResponse",
    "RefreshRequest",
    "RefreshResponse",
    "UserInfo",
    # User
    "UserProfile",
    "ApiKeySummary",
    "ApiKeyCreated",
    "ApiKeyList",
    "CreateApiKeyRequest",
    # Services
    "ServiceInfo",
    "ServiceCatalog",
    "MathVerifyRequest",
    "MathVerifyResponse",
    "MathHelpRequest",
    "MathHelpResponse",
    "ServiceProxyResponse",
    # Agent Execution
    "AgentExecuteRequest",
    "AgentExecuteResponse",
    "AgentCallbackRequest",
    "AgentCallbackResponse",
    "ExecutionInfo",
    "ExecutionList",
    # Subscriptions
    "CreateSubscriptionRequest",
    "CheckoutSessionResponse",
    "SubscriptionInfo",
    "CancelSubscriptionResponse",
    "WebhookResponse",
    # A0 Namespace Platform
    "NamespaceBase",
    "NamespaceCreate",
    "NamespaceUpdate",
    "NamespaceResponse",
    "NamespaceList",
    "NamespaceServiceBase",
    "NamespaceServiceCreate",
    "NamespaceServiceUpdate",
    "NamespaceServiceResponse",
    "NamespaceServiceList",
    "FunctionBase",
    "FunctionCreate",
    "FunctionUpdate",
    "FunctionResponse",
    "FunctionList",
    "FunctionVersionCreate",
    "FunctionVersionResponse",
    "SecurityEventResponse",
    "SecurityEventList",
    "WebhookBase",
    "WebhookCreate",
    "WebhookUpdate",
    "WebhookEndpointResponse",
    "WebhookList",
]
