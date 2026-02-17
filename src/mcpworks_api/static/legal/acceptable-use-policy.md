# Acceptable Use Policy

**MCPWORKS TECHNOLOGIES INC.**

**Version:** 1.0.0
**Effective Date:** February 17, 2026
**Last Updated:** February 16, 2026

---

This Acceptable Use Policy ("AUP") defines what you can and cannot do on the MCPWorks namespace-based function hosting platform (the "Service"). It supplements our [Terms of Service](https://www.mcpworks.io/terms) ("ToS") and [Privacy Policy](https://www.mcpworks.io/privacy). Capitalized terms not defined here have the meanings given in the ToS.

We wrote this document so you can look up "can I do X?" quickly. It is organized by category, not severity.

If something is not explicitly prohibited here, that does not mean it is permitted. We reserve the right to take action against any use that threatens the security, availability, or integrity of the Service or violates applicable law.

**Reporting violations:** abuse@mcpworks.io

---

## 1. Prohibited Content

You must not use the Service to create, store, process, or distribute:

- **Child sexual abuse material (CSAM).** This is a bright-line rule. Violation results in immediate, permanent termination and referral to law enforcement, including the Canadian Centre for Child Protection and the RCMP. No warnings. No appeals.
- **Malware, ransomware, or exploit kits.** Code designed to damage, disable, or gain unauthorized access to any computer system, whether ours or a third party's.
- **Spam or bulk unsolicited messages.** Functions that generate, send, or facilitate spam email, SMS, or messaging of any kind, including through third-party integrations.
- **Credential harvesting.** Phishing pages, fake login forms, or any mechanism designed to trick users into revealing passwords, API keys, or personal information.
- **Illegal goods or services.** Functions that facilitate the sale, purchase, or exchange of controlled substances, weapons, stolen data, or other items prohibited under Canadian federal or provincial law.
- **Disinformation for hire.** Functions purpose-built to generate fake reviews, astroturf social media, or produce synthetic content misrepresented as human-authored for deceptive commercial purposes.
- **Content violating Canadian Criminal Code provisions.** Including but not limited to hate propaganda (Sections 318-320), harassment (Section 264), and fraud (Section 380).

---

## 2. Prohibited Conduct

### 2.1 Sandbox Abuse

The following are prohibited regardless of intent:

- **Sandbox escape attempts.** Any code that probes, tests, or attempts to bypass nsjail isolation, seccomp filters, filesystem restrictions, or process boundaries. This is a terminable offense. If we determine the attempt was deliberate, we will refer the matter to law enforcement.
- **Cryptocurrency mining or proof-of-work computation.** Including any form of blockchain mining, hash computation for token generation, or similar resource-intensive cryptographic work.
- **Fork bombs, memory bombs, or resource exhaustion attacks.** Code deliberately designed to consume CPU, memory, or disk to degrade the platform for other users.
- **Denial-of-service generation.** Using sandbox executions to generate network floods, SYN floods, amplification attacks, or any traffic intended to overwhelm a target system.
- **Kernel and system-level probing.** Attempting to load kernel modules, mount filesystems, access `/proc` or `/sys` in unauthorized ways, or modify system configuration.

### 2.2 Network Abuse

- **Outbound attacks from sandbox.** The sandbox has no internet access by design. Attempting to circumvent network restrictions to launch attacks against external systems is prohibited.
- **Port scanning or network reconnaissance.** Scanning MCPWorks infrastructure or any third-party systems from within sandbox executions or through the API.
- **Automated vulnerability scanning.** Running security scanners, fuzzers, or penetration testing tools against MCPWorks infrastructure without prior written authorization. See Section 7 (Security Research) for our responsible disclosure program.

### 2.3 API and Rate Limit Abuse

- **Ignoring 429 responses.** When you receive an HTTP 429 (Too Many Requests) response, you must respect the `Retry-After` header. Clients that continuously hammer endpoints after receiving 429s will be throttled, then suspended.
- **API key rotation to circumvent rate limits.** Creating multiple API keys, accounts, or namespaces to bypass per-account rate limits is prohibited. We detect and aggregate usage across keys.
- **Multiple free accounts.** Each individual may maintain one free-tier account. Creating additional free accounts to circumvent usage limits is grounds for termination of all such accounts (see ToS Section 3).
- **Automated account creation.** Using scripts or bots to create MCPWorks accounts in bulk.

### 2.4 Code Patterns Beyond the Bright-Line Rules

The ToS (Section 6.3) defines five bright-line prohibited code categories. The following additional patterns are also prohibited:

- **Code designed to attack, exploit, or harm other systems.** Including but not limited to: network scanners, brute-force tools, password crackers, and exploit frameworks — even if the sandbox prevents their execution.
- **Code that processes personal data without lawful authority.** If your function processes third-party personal information, you must have a lawful basis under applicable privacy law (PIPEDA, GDPR, CCPA, or equivalent). See Section 5 (Data Processing Responsibilities).
- **Code that violates export controls or economic sanctions.** You must not use the Service to process data or perform computations in violation of Canadian export controls (Export and Import Permits Act), US EAR/ITAR, or applicable international sanctions regimes.
- **Obfuscated code designed to hide prohibited behavior.** We may inspect function source code as described in the ToS (Section 7.4). Deliberate obfuscation to hide violations will be treated as an aggravating factor.

---

## 3. Resource Usage

### 3.1 Tier Limits Are Hard Caps

Each tier has defined limits for functions, executions, namespaces, and sandbox resources (see ToS Section 5.5 and [Pricing](https://www.mcpworks.io/pricing)). When you hit a limit, executions pause. You are not charged extra. Circumventing these limits by any means is a violation of this AUP.

### 3.2 Free Tier: Evaluation Only

The free tier is for evaluating the Service. Running production workloads on the free tier — including commercial automation, customer-facing services, or revenue-generating functions — is prohibited. If your use case requires production reliability, upgrade to a paid tier.

### 3.3 Enterprise "Unlimited" Fair Use

Enterprise tier accounts with "Unlimited" functions, executions, and namespaces are subject to fair use. Fair use means:

- Usage is consistent with the purpose described in your Enterprise agreement or account registration
- Usage does not degrade the Service for other customers
- Execution patterns are consistent with legitimate business automation, not stress testing or benchmarking

If we determine that Enterprise usage materially impacts platform performance, we will contact you to discuss a custom arrangement before taking any enforcement action. We will not suspend Enterprise accounts for fair use concerns without first engaging in good-faith discussion.

### 3.4 Inactivity

Free-tier accounts with no API activity for 180 consecutive days may have functions and execution history deleted after 30 days written notice, as described in the ToS (Section 5.4).

---

## 4. Namespace Rules

Your namespace (`{namespace}.create.mcpworks.io` and `{namespace}.run.mcpworks.io`) is your identity on the platform. The following naming rules apply:

- **No impersonation.** Namespaces that impersonate other companies, products, or individuals are prohibited. Examples: `stripe`, `openai`, `anthropic`, `google-cloud` — unless you are that entity.
- **No trademark infringement.** Namespaces that use trademarks you do not own or have authorization to use. We will honor valid trademark claims submitted to legal@mcpworks.io.
- **No offensive names.** Namespaces containing slurs, hate speech, sexually explicit terms, or content that would violate Canadian human rights legislation.
- **No misleading names.** Namespaces designed to confuse users into thinking they are official MCPWorks services (e.g., `mcpworks-billing`, `mcpworks-admin`, `mcpworks-official`).
- **Reserved prefixes.** `mcpworks-*`, `admin-*`, and `system-*` are reserved. We may reclaim namespaces that use reserved prefixes.

We may require you to rename a namespace that violates these rules. If you do not comply within 7 days of notice, we may reassign or disable the namespace.

---

## 5. Data Processing Responsibilities

When you use MCPWorks to process personal information belonging to third parties, you are the data controller and MCPWorks is the data processor (see Privacy Policy Section 10). You are responsible for:

- **Lawful basis.** Having a legal basis for processing the data under applicable privacy law (consent, contract, legitimate interest, or other lawful basis under PIPEDA, GDPR, CCPA, or equivalent).
- **Data minimization.** Not processing more personal data than necessary for your stated purpose.
- **No sensitive data without appropriate safeguards.** If you process health data, financial data, biometric data, or other sensitive categories, you must ensure your use complies with sector-specific regulations. MCPWorks does not provide HIPAA BAAs, PCI DSS attestations, or equivalent compliance certifications at this time.
- **Data subject rights.** Responding to access, correction, and deletion requests from the individuals whose data you process. MCPWorks will assist with data deletion upon request as described in the Privacy Policy.
- **Breach notification.** Notifying affected individuals and relevant authorities if you become aware of a breach involving data you processed through the Service, to the extent required by applicable law.

If you require a Data Processing Agreement (DPA), contact privacy@mcpworks.io.

---

## 6. Monitoring and Enforcement

### 6.1 How We Monitor

We use automated systems to detect prohibited activity, including:

- Resource consumption anomalies (CPU spikes, memory pressure patterns)
- Rate limit violation patterns
- Automated malware scanning of function source code
- Namespace naming validation

We do not routinely review the content of your function source code or execution data. We access it only in the circumstances described in the ToS (Section 7.4): at your request, during automated scanning, during active security incidents, or pursuant to legal orders.

### 6.2 Enforcement Escalation

We use a graduated enforcement process. The level of response depends on the severity and nature of the violation.

**Level 1 — Warning.** We notify you by email describing the violation and what you need to change. You have 7 days to cure.

**Level 2 — Temporary Suspension.** If the violation is not cured within the warning period, or if the violation is recurring, we suspend your account. Functions stop executing but your data is preserved. You can still export your data.

**Level 3 — Permanent Termination.** If the violation persists after suspension, or for serious violations (see below), we permanently terminate your account with 14 days written notice. Your data export window begins when you receive notice.

**Immediate Termination (no warning).** The following bypass the graduated process entirely:

- CSAM — Immediate termination, law enforcement referral
- Deliberate sandbox escape attempts — Immediate termination, potential law enforcement referral
- Active security attacks against MCPWorks or third-party infrastructure
- Use of the Service for any activity constituting an indictable offence under the Criminal Code of Canada
- Court order or legal requirement mandating account termination

### 6.3 Appeals

If you believe an enforcement action was made in error, email legal@mcpworks.io within 14 days of the action. Include your account identifier, a description of the action taken, and your explanation. We will respond within 10 business days with a written decision. The decision is final.

---

## 7. Security Research

We value the security research community and want to make it safe to report vulnerabilities in good faith.

### 7.1 Safe Harbor

If you discover a security vulnerability in MCPWorks infrastructure, we will not take enforcement action against you under this AUP provided that:

- You report the vulnerability to security@mcpworks.io before disclosing it publicly or to any third party
- You do not access, modify, or delete data belonging to other users
- You do not degrade the Service for other users (no denial-of-service testing)
- You do not use the vulnerability for any purpose other than demonstrating it in your report
- You give us a reasonable period (minimum 90 days) to address the issue before any public disclosure

### 7.2 What to Include in a Report

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Your suggested remediation (optional but appreciated)

### 7.3 Our Commitment

- We will acknowledge your report within 48 hours
- We will provide a status update within 10 business days
- We will credit you in any public security advisory (unless you prefer anonymity)
- We will not pursue legal action against researchers acting in good faith under this safe harbor

We do not currently operate a paid bug bounty program. We may introduce one in the future.

### 7.4 What Is Not Covered

This safe harbor does not apply to:

- Social engineering attacks against MCPWorks employees or contractors
- Physical attacks against MCPWorks infrastructure
- Denial-of-service testing against production systems
- Testing on accounts you do not own (unless using the free tier with test data)
- Vulnerabilities in third-party services we use (report those to the respective vendor)

---

## 8. Changes to This Policy

We may update this AUP more frequently than the ToS or Privacy Policy, as we discover new abuse patterns or adjust operational boundaries. When we make changes:

- **Material changes** (new categories of prohibited activity, changes to enforcement process): 14 days notice by email and posting at [https://www.mcpworks.io/aup](https://www.mcpworks.io/aup).
- **Non-material changes** (clarifications, examples, formatting): Updated immediately with a revised "Last Updated" date.

The current version is always available at:
- **Web:** [https://www.mcpworks.io/aup](https://www.mcpworks.io/aup)
- **API:** `GET https://api.mcpworks.io/legal/aup`

Previous versions are maintained in version control and available upon request.

---

## 9. Contact

**Report abuse:** abuse@mcpworks.io
**Security vulnerabilities:** security@mcpworks.io
**Legal questions:** legal@mcpworks.io
**Privacy concerns:** privacy@mcpworks.io
**General support:** support@mcpworks.io

**MCPWORKS TECHNOLOGIES INC.**
Vancouver, British Columbia, Canada

---

*This Acceptable Use Policy is effective as of February 17, 2026.*
*Version 1.0.0*
