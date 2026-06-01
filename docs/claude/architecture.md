# Architecture Reference

## API Endpoints (REST)

**Account Management:**
- `POST /v1/auth/register` - Create new account
- `POST /v1/auth/login` - Authenticate and get API key
- `GET /v1/account` - Get account details
- `GET /v1/account/usage` - Get current usage

**Services (Hosting):**
- `POST /v1/services` - Provision hosting service
- `GET /v1/services/{service_id}` - Get service status
- `PATCH /v1/services/{service_id}` - Scale resources
- `DELETE /v1/services/{service_id}` - Deprovision service

**Deployments:**
- `POST /v1/deployments` - Deploy application from Git
- `GET /v1/deployments/{deployment_id}` - Get deployment status
- `GET /v1/deployments/{deployment_id}/logs` - Stream deployment logs (SSE)
- `POST /v1/deployments/{deployment_id}/rollback` - Rollback deployment

**Domains:**
- `POST /v1/domains` - Register domain
- `GET /v1/domains/{domain_id}` - Get domain status
- `POST /v1/domains/{domain_id}/dns` - Configure DNS records
- `GET /v1/domains/check` - Check domain availability

**SSL:**
- `POST /v1/ssl` - Provision SSL certificate
- `GET /v1/ssl/{cert_id}` - Get certificate status
- `POST /v1/ssl/{cert_id}/renew` - Renew certificate

**Integrations:**
- `POST /v1/integrations/stripe` - Setup Stripe account
- `POST /v1/integrations/shopify` - Setup Shopify store
- `POST /v1/integrations/sendgrid` - Setup SendGrid email
- `POST /v1/integrations/twilio` - Setup Twilio SMS
- `POST /v1/integrations/zendesk` - Setup Zendesk support
- `POST /v1/integrations/mailchimp` - Setup Mailchimp
- `POST /v1/integrations/typeform` - Setup Typeform

## Usage Tracking (Subscription-Based)

**Billing Model:** Monthly subscription with execution limits per billing period

**Subscription Tiers (MCPWorks Cloud):**
| Tier | Price | Agents | Executions/Month |
|------|-------|--------|------------------|
| 14-Day Pro Trial | $0 | 5 | 125,000 |
| Pro | $179/mo | 5 | 250,000 |
| Enterprise | $599/mo | 20 | 1,000,000 (fair use) |
| Dedicated | $999/mo | Unlimited | Unlimited (fair use) |

**Community Edition (Self-Hosted):** Free, BSL 1.1, `docker compose up`

**Usage Check Pattern:**
```python
async def execute_workflow(user_id: UUID, workflow_id: UUID):
    # 1. Check usage limit before execution
    usage = await get_current_usage(user_id)
    if usage.executions_count >= usage.executions_limit:
        raise UsageLimitExceededError(
            executions_count=usage.executions_count,
            executions_limit=usage.executions_limit,
            resets_at=usage.billing_period_end
        )

    # 2. Execute workflow
    result = await backend.execute(workflow_id, ...)

    # 3. Increment usage count on success
    await increment_usage(user_id)

    return result
```

## Streaming Architecture

Long-running operations use Server-Sent Events (SSE):

```python
# Tool returns stream URL
{
    "deployment_id": "dep_abc123",
    "stream_url": "https://api.mcpworks.io/v1/streams/dep_abc123",
    "status": "in_progress"
}
```

## Provider Abstraction Layer

All infrastructure operations go through provider-agnostic interfaces:

```python
# Good: Provider-agnostic
from multisphere_mcp.providers import ComputeProvider
provider = ComputeProvider.get_current()  # Returns DO, AWS, or bare-metal
instance = await provider.create_instance(spec)

# Bad: Direct provider coupling
from digitalocean import Manager
client = Manager(token=api_token)
droplet = client.create_droplet(...)
```
