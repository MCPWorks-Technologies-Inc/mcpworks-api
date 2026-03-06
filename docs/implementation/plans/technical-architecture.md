# mcpworks Infrastructure MCP Technical Architecture

**Version:** 2.0
**Created:** 2025-10-19
**Last Updated:** 2025-10-30
**Status:** Planning Phase - Production-Grade Spec
**Purpose:** Acquisition-ready technical documentation

**Changelog v2.0:**
- Updated from 8 tools to 19 tools (added deployment, Zendesk)
- Added Streaming Architecture (SSE) for real-time progress
- Added State Management & Sessions (stateful transactions)
- Added subscription-based billing with usage tracking
- Enhanced Provider Abstraction with transaction safety
- Updated scalability considerations for streaming

---

## Overview

mcpworks Infrastructure MCP is a production-grade AI-native infrastructure platform accessible via the Model Context Protocol (MCP). This document outlines the technical architecture designed for enterprise-level scalability, transaction safety, security, and acquisition readiness.

**Key Design Principles:**
- **AI-First:** MCP protocol integration with 19 tools for complete application lifecycle
- **Streaming Architecture:** Real-time progress updates via SSE (not batch/polling like competitors)
- **State Management:** Stateful sessions with transaction safety and automatic rollback
- **Subscription Billing:** Monthly subscription tiers with usage limits (no credits complexity)
- **Provider Abstraction:** Backend-agnostic (DigitalOcean Phase 1, multi-provider Phase 2+)
- **Security by Default:** Port restrictions, monitoring, guardrails without limiting AI creativity
- **Transparent Pricing:** Usage limits and tier info disclosed in real-time for AI

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     AI Assistant Layer                       │
│  (Claude Code, GitHub Copilot, Cursor, Custom MCP Clients)  │
└──────────────────────┬──────────────────────────────────────┘
                       │ MCP Protocol (HTTPS)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   mcpworks Infrastructure MCP Server                     │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  MCP API   │  │Usage Tracking│  │ Auth & Security  │   │
│  │ (19 Tools) │  │(Subscription)│  │  (JWT, API Keys) │   │
│  └────────────┘  └──────────────┘  └──────────────────┘   │
│  ┌────────────────────────────────────────────────────┐   │
│  │         Provider Abstraction Layer                  │   │
│  │  (Unified API for Infrastructure Operations)       │   │
│  └────────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┬──────────────┐
         ▼             ▼             ▼              ▼
   ┌──────────┐  ┌─────────┐  ┌──────────┐  ┌──────────────┐
   │DigitalOcean│ │Cloudflare│ │  Stripe  │  │ Shopify/etc  │
   │  (Hosting) │  │  (DNS)   │  │(Payments)│  │(Integrations)│
   └──────────┘  └─────────┘  └──────────┘  └──────────────┘
```

---

## Core Components

### 1. MCP Server

**Technology Stack:** Python 3.11+, FastAPI, Pydantic
**Protocol:** MCP over HTTPS (JSON-RPC-like)
**Authentication:** JWT tokens, API keys

**19 MCP Tools:**

**Infrastructure Provisioning (4 tools):**
1. `provision_service` - Create hosting instances
2. `get_service_status` - Query service health & metrics
3. `scale_service` - Modify resource allocation
4. `deprovision_service` - Terminate services

**Application Deployment (3 tools):**
5. `deploy_application` - Deploy from Git with streaming logs
6. `get_deployment_logs` - Stream/retrieve deployment logs
7. `rollback_deployment` - Zero-downtime rollback

**Domain & SSL (3 tools):**
8. `register_domain` - Register domains
9. `provision_ssl` - Provision SSL certificates
10. `get_domain_status` - Query domain/DNS status

**Third-Party Integrations (9 tools):**
11. `setup_stripe_account` - Stripe payment processing
12. `create_stripe_product` - Stripe products/subscriptions
13. `setup_shopify_store` - Shopify e-commerce
14. `add_shopify_product` - Shopify product management
15. `connect_stripe_to_shopify` - Integration linking
16. `setup_sendgrid_email` - Transactional email
17. `setup_twilio_sms` - SMS notifications
18. `setup_zendesk_support` - Customer support/ticketing
19. `get_account_status` - Subscription tier, usage, billing

**Scalability:**
- Stateful session design with persistent state (database-backed)
- SSE streaming for long-running operations (non-blocking)
- Request queue with checkpointing (resume on reconnection)
- Rate limiting per customer (prevents abuse)
- Horizontal scaling with session affinity (sticky sessions)

### 2. Usage Tracking System

**Database:** PostgreSQL (transactional integrity)
**Features:**
- Monthly subscription billing (Stripe integration)
- Real-time execution count tracking
- Usage resets each billing period
- Usage limits API (AI-readable tier info)

**Schema (Simplified):**
```sql
customers (id, email, created_at)
subscriptions (id, customer_id, tier, status, current_period_start, current_period_end)
usage_records (id, customer_id, billing_period_start, billing_period_end, executions_count, executions_limit)
services (id, customer_id, type, config, created_at)
```

### 3. Provider Abstraction Layer

**Design Pattern:** Strategy pattern for provider swapping
**Phase 1:** DigitalOcean only
**Phase 2+:** Multi-provider (AWS, GCP, bare-metal)

**Interface Example:**
```python
class HostingProvider(ABC):
    @abstractmethod
    def create_server(self, spec: ServerSpec) -> Server:
        pass

    @abstractmethod
    def delete_server(self, server_id: str) -> None:
        pass

    # ...other methods
```

**Benefit for Acquirers:** Backend can be swapped to acquirer's infrastructure (e.g., Cloudflare → migrate to Cloudflare Workers, DigitalOcean → migrate to DO's own infra).

### 4. Security Architecture

**Authentication:**
- JWT tokens (1-hour expiry, refresh tokens)
- API keys for programmatic access
- MFA optional (recommended for production)

**Port Restrictions:**
- Blocked by default: 25 (SMTP spam), 445 (SMB security)
- Approval required: 22 (SSH key-based only), database ports on public IP
- Monitored: All unusual port usage flagged

**Encryption:**
- TLS 1.2+ for all API traffic
- Data at rest encryption (provider-level: DigitalOcean volumes)
- Customer secrets encrypted with AES-256

**Monitoring:**
- Real-time abuse detection (excessive resource usage, port scanning)
- Security events logged (audit trail for compliance)
- Alerts for suspicious activity (email + dashboard)

### 5. Data Storage

**Primary Database:** PostgreSQL 14+
- Customer accounts, usage records, service configs
- Hosted on DigitalOcean Managed Database (Phase 1)
- Daily automated backups (7-day retention)

**Object Storage:** DigitalOcean Spaces (S3-compatible)
- Customer uploaded files (if applicable)
- Backups, logs

**Redis:** Caching layer
- Session management, rate limiting
- Usage count caching (invalidated on execution)

---

## Infrastructure Provisioning Flow

### Example: Hosting Provision via MCP

1. **AI Assistant Request:**
   ```json
   {
     "tool": "get_hosting_service",
     "params": {
       "plan": "standard-4gb",
       "region": "tor1",
       "os": "ubuntu-22-04"
     }
   }
   ```

2. **MCP Server Processing:**
   - Check subscription tier and usage limits
   - Check account standing (not suspended, valid payment method)
   - Call Provider Abstraction Layer

3. **DigitalOcean API Call:**
   - Create Droplet with specified configuration
   - Configure firewall rules (port restrictions)
   - Setup monitoring agent

4. **Response to AI:**
   ```json
   {
     "server_id": "droplet-12345",
     "ip_address": "192.0.2.1",
     "ssh_key": "[key data]",
     "tier": "pro",
     "executions_remaining": 248500
   }
   ```

5. **Usage Tracking:**
   - Increment execution count on each operation
   - Customer notified when usage at 80% of tier limit
   - Prompt to upgrade when limit reached

---

## Scalability Design

### Current Capacity (Phase 1 - MVP)
- **Customers:** 1,500-2,000 (Month 12 target)
- **Concurrent API Requests:** 100/sec
- **Database:** Single PostgreSQL instance (DigitalOcean Managed)
- **Application Servers:** 2-4 instances (behind load balancer)

### Scale to 10K Customers (Month 24)
- **Database:** Read replicas (2+), connection pooling
- **Application:** Auto-scaling (10-20 instances)
- **Caching:** Redis cluster (3-node)
- **Monitoring:** Prometheus + Grafana

### Scale to 100K+ Customers (Acquisition Scenario)
- **Database:** Sharding by customer ID, separate write/read clusters
- **Application:** Kubernetes deployment (50-100 pods)
- **Multi-Region:** US East, US West, EU, Canada
- **CDN:** Cloudflare for static assets, API acceleration

**Acquirer Benefit:** Architecture designed for 100x scale without major rewrite.

---

## Security Guardrails

### Abuse Prevention

1. **Free Tier Validation:**
   - Credit card required (Stripe SetupIntent, $0 charge)
   - Geographic restrictions (India blocked from free tier)
   - One free tier account per credit card

2. **Rate Limiting:**
   - API: 100 requests/minute per customer (burst: 200)
   - Infrastructure provisioning: 10 new services/hour
   - Domain registration: 5 domains/day

3. **Monitoring Alerts:**
   - Unusual port activity (port scanning detected)
   - Excessive bandwidth (10x normal usage)
   - Failed authentication attempts (>10/hour)
   - Credit fraud patterns (multiple cards, same IP)

### Incident Response

**See `docs/operations/incident-response-runbook.md` (to be created)**

**Security Incident Types:**
- Data breach, unauthorized access
- DDoS attack, service disruption
- Customer abuse (spam, malware hosting)
- Payment fraud

**Response Timeline:**
- Detection: Real-time monitoring
- Containment: <1 hour (suspend affected services)
- Investigation: 24-48 hours
- Customer notification: 72 hours (if data breach)
- Remediation: Varies by severity

---

## Disaster Recovery

### Backup Strategy

**Database Backups:**
- Automated daily backups (DigitalOcean Managed Database)
- 7-day retention (Phase 1), 30-day retention (Phase 2+)
- Encrypted backups stored in separate region

**Application Backups:**
- Infrastructure-as-code (Terraform) for reproducible environments
- Docker images versioned and stored in registry
- Configuration files in Git (encrypted secrets)

**Recovery Time Objectives:**
- **RTO (Recovery Time):** 4 hours (database restore + app redeployment)
- **RPO (Recovery Point):** 24 hours (daily backups, hourly point-in-time available)

### High Availability (Phase 2+)

- Multi-AZ database deployment
- Load balancer with health checks (automatic failover)
- Geographic redundancy (US + Canada data centers)
- 99.9% uptime target (not guaranteed, see Terms of Service)

---

## Technology Stack Summary

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Backend** | Python 3.11+, FastAPI | Fast development, MCP SDK availability, async support |
| **Database** | PostgreSQL 14+ | Transactional integrity, JSON support, proven scale |
| **Caching** | Redis 7+ | Session management, rate limiting, usage count caching |
| **Infrastructure** | DigitalOcean (Phase 1) | Cost-effective, good API, Canadian presence |
| **DNS** | Cloudflare | Free tier, excellent API, DDoS protection |
| **Payments** | Stripe | Industry standard, excellent API, fraud detection |
| **Monitoring** | Prometheus, Grafana | Open-source, powerful, industry standard |
| **Logging** | Structured logs → S3 | Cost-effective, long-term retention, searchable |
| **Deployment** | Docker, Terraform | Reproducible, infrastructure-as-code, multi-cloud portable |

**Acquirer Compatibility:**
- **Anthropic:** Python stack familiar, easy to integrate with Claude infrastructure
- **Cloudflare:** Can migrate to Workers (JS) or keep Python backend
- **DigitalOcean:** Trivial integration into DO's own infrastructure
- **Microsoft/GitHub:** Azure-compatible stack, Copilot integration straightforward

---

## API Design

### RESTful API (Public-facing)

**Base URL:** `https://api.mcpworks.io/v1/`

**Endpoints:**
- `POST /customers` - Create account
- `GET /customers/{id}` - Get account details
- `GET /usage` - Get current usage and limits
- `POST /subscriptions` - Manage subscription tier
- `GET /services` - List customer services
- `POST /services/hosting` - Provision hosting
- `DELETE /services/{id}` - Deprovision service

**Authentication:** `Authorization: Bearer <jwt_token>`

### MCP Protocol API

**Base URL:** `https://mcp.multisphere.ca/`

**MCP Protocol Specifics:**
- JSON-RPC-like request/response
- Tools, Resources, Prompts exposed
- Client libraries: Python, TypeScript (provided by Anthropic MCP SDK)

---

## Acquisition Due Diligence Readiness

### Technical DD Checklist

**Architecture Documentation:**
- ✅ System architecture diagram (this document)
- ✅ Technology stack justified (this document)
- ✅ Scalability design (10x, 100x customer growth)
- ✅ Security architecture (authentication, encryption, monitoring)
- ✅ Disaster recovery plan (backup, RTO, RPO)

**Code Quality (To Be Demonstrated):**
- ✅ Infrastructure-as-code (Terraform)
- ✅ Automated testing (>80% coverage target)
- ✅ CI/CD pipeline (GitHub Actions or equivalent)
- ✅ Code review process (all PRs reviewed)
- ✅ Security scanning (automated vulnerability detection)

**Scalability Evidence:**
- ✅ Load testing results (target: 100 req/sec sustained)
- ✅ Database performance benchmarks
- ✅ Cost per customer analysis (infrastructure + operating costs)

**Security Audit:**
- 🔄 Penetration testing (quarterly, starting Month 6)
- 🔄 Security audit report (third-party, before acquisition DD)
- ✅ Incident response procedures documented

**IP Protection:**
- ✅ All code owned by company (founder agreement assigns IP)
- ✅ No GPL or restrictive licenses (permissive licenses only: MIT, Apache)
- ✅ Third-party dependency audit (license compliance)

### Acquirer-Specific Technical Fit

**Anthropic:**
- ✅ MCP protocol compliance (first-class integration)
- ✅ Python stack (familiar to Anthropic engineering)
- ✅ Usage tracking (subscription tiers for AI optimization)
- **Integration effort:** Low (2-4 weeks to migrate to Anthropic infrastructure)

**Cloudflare:**
- ✅ Cloudflare DNS already integrated
- ✅ Containerized architecture (portable to Cloudflare Workers)
- ✅ API-first design (aligns with Cloudflare developer platform)
- **Integration effort:** Medium (4-8 weeks to migrate to Workers/R2/D1)

**DigitalOcean:**
- ✅ DigitalOcean API-native (trivial integration)
- ✅ Managed Database, Spaces already used
- **Integration effort:** Minimal (1-2 weeks, mostly organizational)

**Microsoft/GitHub:**
- ✅ Azure-compatible stack (Python on Linux, PostgreSQL)
- ✅ GitHub Copilot MCP integration potential
- **Integration effort:** Medium (6-12 weeks to migrate to Azure)

---

## Roadmap & Evolution

### Phase 1: MVP (Month 1-3)
- Single-provider backend (DigitalOcean)
- 8 MCP tools functional
- Usage tracking operational
- Basic security (auth, encryption, monitoring)

### Phase 2: Market Validation (Month 4-12)
- Multi-provider abstraction (AWS, GCP options)
- Advanced security (MFA, audit logging, pen testing)
- Scalability improvements (read replicas, caching)
- Additional integrations (more third-party APIs)

### Phase 3: Scale & Acquisition Prep (Month 13-18)
- Multi-region deployment
- 99.9% uptime infrastructure
- SOC 2 Type I compliance (started)
- Full technical DD documentation

---

## Changelog

**v1.0 (2025-10-19):**
- Initial architecture documentation
- Acquisition-ready technical design
- Scalability roadmap (1K → 10K → 100K customers)
- Security architecture and guardrails
- Disaster recovery plan
- Acquirer technical fit analysis
