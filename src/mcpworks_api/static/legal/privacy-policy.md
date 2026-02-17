# Privacy Policy

**MCPWORKS TECHNOLOGIES INC.**

**Version:** 1.0.0
**Effective Date:** February 17, 2026
**Last Updated:** February 16, 2026

---

## 1. Introduction

This Privacy Policy explains how MCPWORKS TECHNOLOGIES INC. ("MCPWorks," "we," "us," or "our") collects, uses, discloses, and protects your personal information when you use our namespace-based function hosting platform and related services (the "Service").

MCPWorks is incorporated in British Columbia, Canada (BC1568752). We are subject to the British Columbia Personal Information Protection Act (BC PIPA) for provincial matters and the federal Personal Information Protection and Electronic Documents Act (PIPEDA) for inter-provincial and international data flows. We also comply with applicable privacy laws in the jurisdictions where we operate, including the California Consumer Privacy Act (CCPA/CPRA) and the EU General Data Protection Regulation (GDPR).

We have written this policy in plain language. If something is unclear, contact us at privacy@mcpworks.io.

---

## 2. Privacy Officer

MCPWorks has designated a Privacy Officer responsible for our compliance with this policy and applicable privacy laws:

**Simon Carr**
Privacy Officer, MCPWORKS TECHNOLOGIES INC.
Email: simon.carr@mcpworks.io
Mailing Address: MCPWORKS TECHNOLOGIES INC., Vancouver, British Columbia, Canada V5K 0A1

You may contact the Privacy Officer with any questions, concerns, or requests related to your personal information.

---

## 3. What We Collect and Why

We collect personal information only when it is necessary to provide and operate the Service. Below is a specific accounting of each category of information we collect, the purpose for collection, our lawful basis, and how long we retain it.

### 3.1 Account Information

| Data | Purpose | Lawful Basis | Retention |
|------|---------|-------------|-----------|
| Email address | Account identification, login, transactional communications (e.g., billing receipts, security alerts) | Contract performance; PIPEDA consent at registration | Duration of account + 30 days after deletion request |
| Password hash (argon2) | Authentication. We never store your plaintext password. | Contract performance | Duration of account; deleted upon account deletion |
| Account tier (free, founder, founder_pro, enterprise) | Subscription management and enforcement of usage limits | Contract performance | Duration of account + 90 days for billing records |
| Account status (active, suspended, deleted) | Service administration | Contract performance | Duration of account + 90 days |
| Email verification status | Account security and communications integrity | Legitimate interest (security) | Duration of account |

### 3.2 Authentication and Security Data

| Data | Purpose | Lawful Basis | Retention |
|------|---------|-------------|-----------|
| API key hashes (argon2) | Authenticate API and MCP protocol requests. We store only the hash, not the plaintext key. | Contract performance | Until key is revoked or account is deleted |
| API key metadata (name, scopes, creation date, last used date, expiration) | Key management and audit | Contract performance | Until key is revoked or account is deleted + 90 days |
| JWT refresh tokens | Session management and token rotation | Contract performance | 7 days from issuance (automatic expiry) |
| IP addresses | Rate limiting, abuse prevention, security event logging | Legitimate interest (security and fraud prevention) | Security events: 1 year. Rate limiting data: 24 hours. |
| Security events (login attempts, failed authentications, permission violations) | Threat detection, abuse prevention, incident investigation | Legitimate interest (security) | 1 year |

### 3.3 Code Execution Data

This is the data most specific to our Service. When you use MCPWorks, you submit Python code for execution in our sandboxed environment.

| Data | Purpose | Lawful Basis | Retention |
|------|---------|-------------|-----------|
| Function source code | Store and execute functions you create | Contract performance | Duration of account; deleted upon account or function deletion |
| Function metadata (name, description, input/output schemas, version history, package requirements) | Function management and versioning | Contract performance | Duration of account |
| Execution inputs (the data you send when calling a function) | Pass to your function for execution | Contract performance | 90 days |
| Execution outputs (the data your function returns) | Return results to you; execution history | Contract performance | 90 days |
| Execution metadata (status, timing, error messages, tokens used) | Debugging, usage tracking, billing enforcement | Contract performance; legitimate interest (service reliability) | 90 days |

**Important: Your code may process personal information.** If you submit code that processes personal data belonging to third parties (for example, a function that analyzes customer email addresses), you are the data controller for that information and MCPWorks acts as a data processor. You are responsible for ensuring you have the legal authority to process that data through our Service. See Section 10 (Data Processor Role) for more detail.

**Sandbox isolation.** Your code executes in an isolated nsjail sandbox. Each execution runs in its own isolated process with restricted system access. Your code cannot access other users' data, our database, or our internal systems.

### 3.4 Billing and Payment Data

| Data | Purpose | Lawful Basis | Retention |
|------|---------|-------------|-----------|
| Stripe customer ID | Link your MCPWorks account to your Stripe billing record | Contract performance | Duration of account + 7 years (tax/accounting requirement) |
| Subscription status and tier | Enforce usage limits, manage billing lifecycle | Contract performance | Duration of account + 7 years |
| Billing period dates | Usage quota tracking | Contract performance | Duration of account + 7 years |

**We never see, store, or process your payment card number, CVV, or banking details.** All payment card data is collected and processed exclusively by Stripe. See Stripe's privacy policy at [https://stripe.com/privacy](https://stripe.com/privacy).

### 3.5 Audit Logs

| Data | Purpose | Lawful Basis | Retention |
|------|---------|-------------|-----------|
| Audit log entries (user ID, action performed, resource type, resource ID, timestamp, additional details) | Regulatory compliance, security investigation, debugging | Legal obligation (PIPEDA accountability); legitimate interest (security) | 2 years |

### 3.6 Usage and Operational Data

| Data | Purpose | Lawful Basis | Retention |
|------|---------|-------------|-----------|
| Execution counts per billing period | Quota enforcement, billing | Contract performance | Duration of current billing period + 90 days |
| API request metadata (endpoint called, response status, correlation ID, timestamp) | Service reliability, debugging, performance monitoring | Legitimate interest (service operation) | 30 days |
| Error reports (stack traces, request context) | Bug identification and resolution, sent to Sentry | Legitimate interest (service reliability) | 90 days (Sentry retention policy) |

### 3.7 Data We Do Not Collect

- **Cookies.** MCPWorks is currently an API-only service. We do not set browser cookies or use web analytics trackers. If we introduce a web dashboard in the future, we will update this policy before deploying any cookies.
- **Device fingerprints or advertising identifiers.** We do not collect these.
- **Biometric data.** We do not collect this.
- **Location data** beyond IP address. We do not use GPS or precise geolocation.
- **Data from children.** MCPWorks is not directed at individuals under 16. We do not knowingly collect personal information from children. If we learn we have collected information from a child under 16, we will delete it promptly.

---

## 4. How We Use Your Information

We use your personal information for the following specific purposes:

1. **Provide the Service** -- create and manage your account, execute your functions in sandboxed environments, return execution results, and enforce usage quotas.
2. **Process payments** -- manage subscriptions, track billing periods, and coordinate with Stripe for payment processing.
3. **Secure the Service** -- detect and prevent unauthorized access, rate-limit API requests, log security events, and investigate incidents.
4. **Communicate with you** -- send transactional emails about your account (billing receipts, security alerts, service disruptions). We do not currently send marketing emails. If we begin doing so, we will obtain your separate consent.
5. **Maintain and improve the Service** -- monitor error rates, debug issues, track performance, and plan capacity.
6. **Comply with legal obligations** -- respond to lawful requests from authorities, maintain records required by tax and corporate law, and fulfill breach notification obligations.

We do not use your personal information for:
- Selling to third parties
- Targeted advertising
- Automated decision-making that produces legal effects
- Profiling for purposes unrelated to the Service
- Training AI or machine learning models on your code or execution data

---

## 5. Who We Share Your Information With

We share personal information only as described below. We do not sell personal information.

### 5.1 Sub-processors

We use the following third-party service providers to operate the Service. Each processes personal information only on our behalf and subject to contractual obligations:

| Sub-processor | Purpose | Data Shared | Location | Privacy Policy |
|--------------|---------|-------------|----------|---------------|
| **Stripe, Inc.** | Payment processing, subscription management | Email address, Stripe customer ID, subscription events | San Francisco, CA, USA | [stripe.com/privacy](https://stripe.com/privacy) |
| **DigitalOcean, LLC** | Cloud infrastructure hosting (compute, database, networking) | All data stored on our servers (encrypted at rest) | NYC1 datacenter, New York, USA | [digitalocean.com/legal/privacy-policy](https://www.digitalocean.com/legal/privacy-policy) |
| **Functional Software, Inc. (Sentry)** | Error tracking and monitoring | Error reports including request context, stack traces, and correlation IDs. We configure Sentry to exclude execution inputs/outputs. | San Francisco, CA, USA | [sentry.io/privacy](https://sentry.io/privacy/) |

We will update this list if we add new sub-processors and will notify you of material changes to our sub-processor list by email or by posting a notice at api.mcpworks.io.

### 5.2 Legal and Regulatory Disclosures

We may disclose personal information if required to do so by law, regulation, legal process, or enforceable governmental request. Before disclosing, we will:

- Verify the legal validity of the request
- Limit disclosure to the minimum required
- Notify you unless prohibited by law from doing so

### 5.3 Business Transfers

If MCPWorks is involved in a merger, acquisition, or sale of assets, your personal information may be transferred as part of that transaction. We will notify you before your information becomes subject to a different privacy policy.

### 5.4 With Your Consent

We may share information with third parties when you have given us explicit consent to do so.

---

## 6. Cross-Border Data Transfers

MCPWorks is a Canadian company. However, our infrastructure is hosted on DigitalOcean servers located in the United States (NYC1 datacenter, New York). Our sub-processors Stripe and Sentry are also based in the United States.

This means your personal information is transferred from Canada to the United States for processing and storage.

**For Canadian users:** Under PIPEDA, we are accountable for the protection of your personal information when it is transferred to a third party in another jurisdiction for processing. Our contracts with DigitalOcean, Stripe, and Sentry require them to provide a comparable level of protection. However, when your data is in the United States, it may be accessible to US law enforcement and national security agencies under US law (including the USA PATRIOT Act and FISA).

**For EU/EEA users:** Transfers from the EU/EEA to the United States are conducted under Standard Contractual Clauses (SCCs) where applicable, or on the basis of adequacy decisions. DigitalOcean and Stripe maintain EU SCCs as part of their data processing agreements. If you are located in the EU/EEA and have concerns about data transfers, please contact us.

**For California users:** See Section 9 (California Privacy Rights) for additional disclosures.

---

## 7. Data Security

We implement the following technical and organizational measures to protect your personal information:

**Authentication and access control:**
- Passwords are hashed using argon2 (a memory-hard hashing algorithm resistant to GPU-based attacks) before storage. We never store plaintext passwords.
- API keys are hashed using argon2 before storage. The plaintext key is shown once at creation and never stored.
- JWT access tokens use ES256 (ECDSA with P-256 curve) signing and expire after 60 minutes.
- Refresh tokens expire after 7 days and are rotated on use.
- Scope-based authorization restricts API key access to specific operations.

**Infrastructure security:**
- All data in transit is encrypted via TLS 1.2 or higher.
- PostgreSQL database is not exposed to the public internet.
- Redis cache is not exposed to the public internet.
- User-submitted code executes in nsjail sandboxes with process isolation, restricted system calls, resource limits, and no access to our database or other users' data.

**Operational security:**
- Rate limiting on authentication endpoints to prevent brute-force attacks.
- Correlation IDs for distributed request tracing.
- Structured logging for security event detection.
- CI/CD pipeline with automated testing before deployment.

No system is perfectly secure. If you discover a security vulnerability, please report it to security@mcpworks.io. We commit to acknowledging reports within 48 hours.

---

## 8. Your Privacy Rights

Depending on where you are located, you have some or all of the following rights regarding your personal information. We honor these rights for all users regardless of jurisdiction, unless doing so would conflict with a legal obligation.

### 8.1 Right of Access

You may request a copy of the personal information we hold about you. We will provide it in a structured, commonly used, machine-readable format (JSON).

**How to exercise:** Email privacy@mcpworks.io with subject line "Data Access Request."
**Response time:** Within 30 days of receiving your verified request.
**Cost:** Free for the first request in any 12-month period.

### 8.2 Right of Correction

You may request that we correct inaccurate personal information. You can update your email address and account details directly through the API. For other corrections, contact us.

**How to exercise:** Email privacy@mcpworks.io with subject line "Data Correction Request."
**Response time:** Within 30 days.

### 8.3 Right of Deletion

You may request that we delete your personal information. Upon receiving a verified deletion request, we will:

1. Delete your account, namespaces, services, functions, function versions, and execution history.
2. Delete your API keys and refresh tokens.
3. Request deletion of your Stripe customer record (subject to Stripe's own retention policies).
4. Retain only what we are legally required to keep (audit logs for up to 2 years, billing records for up to 7 years for tax compliance).

**How to exercise:** Email privacy@mcpworks.io with subject line "Data Deletion Request."
**Response time:** We will confirm deletion within 30 days. Actual deletion from all systems (including backups) may take up to an additional 60 days.

### 8.4 Right to Data Portability

You may request a copy of your data in a portable format. This includes your account information, function source code, function metadata, and execution history.

**How to exercise:** Email privacy@mcpworks.io with subject line "Data Portability Request."
**Response time:** Within 30 days.
**Format:** JSON export.

### 8.5 Right to Withdraw Consent

Where we rely on your consent as the lawful basis for processing, you may withdraw consent at any time. Withdrawal does not affect the lawfulness of processing that occurred before withdrawal. Note that withdrawing consent for processing that is necessary to provide the Service may require us to close your account.

### 8.6 Right to Object

You may object to processing based on our legitimate interests. We will stop processing unless we have compelling legitimate grounds that override your interests.

### 8.7 Verifying Your Identity

To protect your privacy, we will verify your identity before fulfilling any rights request. We will ask you to confirm your request from the email address associated with your MCPWorks account. For deletion requests, we may require additional verification.

---

## 9. California Privacy Rights (CCPA/CPRA)

If you are a California resident, you have additional rights under the California Consumer Privacy Act and the California Privacy Rights Act.

### 9.1 Categories of Personal Information Collected

In the preceding 12 months, we have collected the following categories of personal information as defined by the CCPA:

| CCPA Category | Examples from MCPWorks | Business Purpose |
|---------------|----------------------|-----------------|
| Identifiers | Email address, IP address, Stripe customer ID | Account management, security, billing |
| Commercial information | Subscription tier, billing period, execution counts | Billing and service delivery |
| Internet or network activity | API request logs, execution history, security events | Service operation and security |
| Professional or employment-related information | None collected | N/A |
| Geolocation data | IP-derived approximate location (city/region level) | Rate limiting, abuse prevention |
| Sensitive personal information | Account login credentials (email + password hash) | Authentication |

### 9.2 Sale and Sharing of Personal Information

**We do not sell your personal information.** We have not sold personal information in the preceding 12 months.

**We do not share your personal information for cross-context behavioral advertising.**

Because we do not sell or share personal information, we are not required to offer a "Do Not Sell or Share" opt-out. However, if you believe we are engaging in activity that constitutes a "sale" under the CCPA, please contact us and we will address your concern.

### 9.3 Retention

See Section 3 for specific retention periods for each category of data.

### 9.4 Non-Discrimination

We will not discriminate against you for exercising your CCPA rights. We will not deny you the Service, charge you different prices, or provide a different quality of service because you exercised a privacy right.

---

## 10. Data Processor Role (User-Submitted Code and Data)

MCPWorks occupies two roles with respect to personal information:

**Data Controller:** For your account information, authentication data, billing data, and usage data, MCPWorks decides what to collect and how to use it. We are the data controller for this information.

**Data Processor:** For data that you submit through your functions (execution inputs and outputs), MCPWorks processes it on your behalf according to your instructions. You are the data controller and we are the data processor for this information. We:

- Process execution inputs and outputs solely to execute your functions and return results to you
- Do not use your execution data for any purpose other than providing the Service
- Do not access or review your execution data except as necessary for debugging (at your request) or security incident investigation
- Delete execution data according to the retention periods in Section 3
- Implement the security measures described in Section 7

If you process personal information of EU/EEA data subjects through our Service and require a Data Processing Agreement (DPA), please contact privacy@mcpworks.io.

---

## 11. Data Retention Summary

| Data Category | Retention Period | Basis |
|---------------|-----------------|-------|
| Account information (email, password hash, tier) | Duration of account + 30 days after deletion | Contract; deletion grace period |
| API key hashes and metadata | Until revoked or account deleted + 90 days | Contract; audit trail |
| JWT refresh tokens | 7 days from issuance | Technical expiry |
| IP addresses (rate limiting) | 24 hours | Legitimate interest |
| IP addresses (security events) | 1 year | Legitimate interest (security) |
| Function source code and metadata | Duration of account | Contract |
| Execution inputs and outputs | 90 days | Contract |
| Execution metadata | 90 days | Contract; service reliability |
| Stripe customer ID, subscription data | Duration of account + 7 years | Legal obligation (tax records) |
| Audit logs | 2 years | Legal obligation (PIPEDA accountability) |
| Security events | 1 year | Legitimate interest (security) |
| Error reports (Sentry) | 90 days | Legitimate interest (service reliability) |
| API request metadata | 30 days | Legitimate interest (service operation) |

When retention periods expire, data is deleted or anonymized within 30 days of the expiry date. If you request account deletion (Section 8.3), all data categories listed as "Duration of account" or with rolling retention windows (e.g., 90 days) are deleted immediately upon processing the deletion request, except where a specific legal obligation requires longer retention (e.g., billing records for tax compliance).

---

## 12. Breach Notification

In the event of a security breach involving your personal information that creates a real risk of significant harm to you, we will:

1. **Notify the Office of the Privacy Commissioner of Canada (OPC)** as soon as feasible after determining that a breach has occurred, as required by PIPEDA Division 1.1.
2. **Notify you directly** by email as soon as feasible, describing:
   - What happened
   - What personal information was involved
   - What we have done and are doing to address the breach
   - What you can do to protect yourself
   - How to contact us for more information
3. **Notify relevant supervisory authorities** in other jurisdictions if required (e.g., within 72 hours for GDPR-covered breaches).
4. **Maintain a record** of all breaches for at least 2 years, as required by PIPEDA.

---

## 13. Changes to This Policy

We may update this Privacy Policy from time to time. When we make changes:

- **Material changes** (new categories of data collection, new sub-processors, changes to your rights): We will notify you by email at least 14 days before the changes take effect.
- **Non-material changes** (clarifications, formatting, correcting typos): We will update the "Last Updated" date at the top of this policy.

The current version of this policy is always available at:
- **Web:** [https://www.mcpworks.io/privacy](https://www.mcpworks.io/privacy)
- **API:** `GET https://api.mcpworks.io/legal/privacy`

Previous versions are maintained in our version control system and available upon request.

---

## 14. Complaints

If you are not satisfied with our response to a privacy concern, you have the right to file a complaint with the appropriate regulatory authority:

**Canada:**
Office of the Privacy Commissioner of Canada
30 Victoria Street, Gatineau, Quebec K1A 1H3
Toll-free: 1-800-282-1376
Website: [https://www.priv.gc.ca](https://www.priv.gc.ca)

**European Union:**
You may lodge a complaint with the supervisory authority in your member state of residence. A list of supervisory authorities is available at [https://edpb.europa.eu/about-edpb/about-edpb/members_en](https://edpb.europa.eu/about-edpb/about-edpb/members_en).

**California:**
Office of the Attorney General, California Department of Justice
Website: [https://oag.ca.gov/privacy](https://oag.ca.gov/privacy)

We encourage you to contact us first at privacy@mcpworks.io so we can attempt to resolve your concern directly.

---

## 15. Contact Us

For any questions about this Privacy Policy or our data practices:

**Email:** privacy@mcpworks.io
**Privacy Officer:** Simon Carr, simon.carr@mcpworks.io
**Company:** MCPWORKS TECHNOLOGIES INC.
**Jurisdiction:** British Columbia, Canada

---

## 16. Interpretation

This policy is governed by the laws of British Columbia, Canada. If any provision of this policy is found to be unenforceable, the remaining provisions continue in full force and effect.

Where this policy uses the term "personal information," it includes "personal data" as defined by the GDPR and "personal information" as defined by the CCPA, unless the context requires otherwise.

---

*This Privacy Policy is effective as of February 17, 2026.*
*Version 1.0.0*
