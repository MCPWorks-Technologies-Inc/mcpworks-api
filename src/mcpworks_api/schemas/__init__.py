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
from mcpworks_api.schemas.credit import (
    AddCreditsRequest,
    AddCreditsResponse,
    CommitRequest,
    CommitResponse,
    CreditBalance,
    HoldRequest,
    HoldResponse,
    ReleaseRequest,
    ReleaseResponse,
    TransactionList,
    TransactionSummary,
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
    PurchaseCreditsRequest,
    SubscriptionInfo,
    WebhookResponse,
)
from mcpworks_api.schemas.user import (
    ApiKeyCreated,
    ApiKeyList,
    ApiKeySummary,
    CreateApiKeyRequest,
    UserProfile,
    UserProfileWithCredits,
)
# A0 Namespace Platform Schemas
from mcpworks_api.schemas.namespace import (
    NamespaceBase,
    NamespaceCreate,
    NamespaceUpdate,
    NamespaceResponse,
    NamespaceList,
)
from mcpworks_api.schemas.namespace_service import (
    NamespaceServiceBase,
    NamespaceServiceCreate,
    NamespaceServiceUpdate,
    NamespaceServiceResponse,
    NamespaceServiceList,
)
from mcpworks_api.schemas.function import (
    FunctionBase,
    FunctionCreate,
    FunctionUpdate,
    FunctionResponse,
    FunctionList,
    FunctionVersionCreate,
    FunctionVersionResponse,
)
from mcpworks_api.schemas.security_event import (
    SecurityEventResponse,
    SecurityEventList,
)
from mcpworks_api.schemas.webhook import (
    WebhookBase,
    WebhookCreate,
    WebhookUpdate,
    WebhookResponse as WebhookEndpointResponse,
    WebhookList,
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
    "UserProfileWithCredits",
    "ApiKeySummary",
    "ApiKeyCreated",
    "ApiKeyList",
    "CreateApiKeyRequest",
    # Credits
    "CreditBalance",
    "HoldRequest",
    "HoldResponse",
    "CommitRequest",
    "CommitResponse",
    "ReleaseRequest",
    "ReleaseResponse",
    "AddCreditsRequest",
    "AddCreditsResponse",
    "TransactionList",
    "TransactionSummary",
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
    "PurchaseCreditsRequest",
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
