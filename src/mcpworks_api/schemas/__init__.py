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
]
