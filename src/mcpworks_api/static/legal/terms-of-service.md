# Terms of Service

**MCPWORKS TECHNOLOGIES INC.**

**Version:** 1.0.0
**Effective Date:** February 17, 2026
**Last Updated:** February 16, 2026

---

## Developer Bill of Rights

Before the legal language begins, here is what you can count on:

1. **You own your code. Always.** We never claim ownership of code you create or execute on MCPWorks.
2. **We never train on your code.** Your functions, inputs, and outputs are never used to train AI or machine learning models.
3. **Your data is portable.** You can export your functions, metadata, and execution history at any time.
4. **No surprise bills.** Hard caps, not overages. When you hit your limit, executions pause. Your card is not charged extra.
5. **Pricing is clear and public.** Current pricing is always published at mcpworks.io/pricing with no hidden fees.
6. **We tell you before things change.** Material changes to these terms require 30 days notice.
7. **You can leave anytime.** Cancel your account, export your data, and walk away. No exit fees.

---

## 1. Agreement to Terms

By creating an account or using the MCPWorks namespace-based function hosting platform (the "Service"), you agree to these Terms of Service ("Terms"), our [Privacy Policy](https://www.mcpworks.io/privacy), and our [Acceptable Use Policy](https://www.mcpworks.io/aup) ("AUP"). If you do not agree, do not use the Service.

"MCPWorks," "we," "us," and "our" refer to MCPWORKS TECHNOLOGIES INC., a British Columbia corporation (BC1568752). "You" and "your" refer to the individual or entity using the Service.

These Terms are governed by the laws of British Columbia and the federal laws of Canada applicable therein.

---

## 2. The Service

MCPWorks provides namespace-based function hosting for AI assistants. You create functions through a management interface (`{namespace}.create.mcpworks.io`) and execute them through a run interface (`{namespace}.run.mcpworks.io`). Functions execute on one of several backends (Code Sandbox, Activepieces, nanobot.ai, or GitHub Repo).

We may offer the Service in alpha, beta, or preview stages. Features in those stages may change or be removed with 14 days notice.

---

## 3. Account Terms

**Eligibility.** You must be at least 16 years old. By creating an account, you represent that you meet this requirement.

**One person, one account.** Each individual may maintain one free-tier account. Creating multiple free accounts to circumvent usage limits is grounds for termination of all such accounts.

**Account security.** You are responsible for maintaining the confidentiality of your credentials and API keys. Notify us immediately at security@mcpworks.io if you believe your account has been compromised.

**Accuracy.** You must provide accurate registration information and keep it current.

---

## 4. Billing and Payment

### 4.1 Pricing and Currency

All prices are in Canadian Dollars (CAD) and are exclusive of applicable taxes. GST/HST and other sales taxes are calculated and collected via Stripe Tax based on your location.

Current pricing is published at [https://www.mcpworks.io/pricing](https://www.mcpworks.io/pricing) and in our [Pricing Documentation](https://docs.mcpworks.io/pricing).

### 4.2 Billing Cycle

Subscriptions are billed monthly or annually. Annual billing provides two months free (pay for 10 months, receive 12). Subscriptions auto-renew at the end of each billing period unless you cancel before the renewal date.

**Auto-renewal disclosure:** Your subscription will automatically renew at the then-current rate for your tier. You authorize us to charge your payment method on file at each renewal. You may cancel auto-renewal at any time through your account settings or by contacting support@mcpworks.io.

### 4.3 Failed Payments

If a payment fails, we will retry for up to 7 days. If payment is not resolved within 30 days, your account will be suspended (functions stop executing but data is preserved). After 90 days of suspension, your account and all associated data will be permanently deleted.

### 4.4 Refunds

We offer a 14-day money-back guarantee on your first payment only. To request a refund, contact support@mcpworks.io within 14 days of your first charge. No prorated refunds are provided for annual subscriptions cancelled mid-term, except as described in Section 15 (Amendments).

### 4.5 Upgrades and Downgrades

Upgrades take effect immediately and are prorated for the remainder of the billing period. Downgrades take effect at the start of the next billing period.

---

## 5. Usage Limits and Execution Metering

### 5.1 Hard Caps, Not Overages

Each tier has defined limits for functions, executions per month, namespaces, and sandbox resources. When you reach a limit, additional executions are paused until the next billing period. We do not charge overage fees.

### 5.2 What Counts as an Execution

Each function invocation counts as one execution, including:

- Successful executions
- Failed executions (including timeouts and errors)
- Retries (each retry is a separate execution)
- Scheduled triggers (each trigger is a separate execution)

### 5.3 No Rollover

Unused executions do not carry over between billing periods.

### 5.4 Free Tier Inactivity

Free-tier accounts with no API activity for 180 consecutive days may have their functions and execution history deleted after 30 days written notice. Account credentials are preserved.

### 5.5 Resource Limits by Tier

| Resource | Free ($0) | Builder ($49) | Pro ($149) | Enterprise ($499+) |
|----------|-----------|---------------|------------|---------------------|
| Functions | 5 | 25 | Unlimited | Unlimited |
| Executions/month | 100 | 2,500 | 15,000 | 100,000 (fair use) |
| Namespaces | 1 | 3 | Unlimited | Unlimited |
| Sandbox timeout | 10s | 30s | 90s | 300s |
| Sandbox memory | 128 MB | 256 MB | 512 MB | 2 GB |
| Sandbox CPU time | 5s | 15s | 45s | 120s |
| Concurrent executions | 1 | 3 | 10 | 50 |

Enterprise tier operates under a fair use policy. Accounts consistently exceeding 100,000 executions/month will be contacted to discuss custom pricing. Custom arrangements are available by contacting enterprise@mcpworks.io.

---

## 6. Code Execution and Sandbox

### 6.1 Sandbox Environment

Your code executes in an isolated nsjail sandbox. Each execution runs in its own process with the following restrictions:

- **No internet access.** Your code cannot make outbound network requests.
- **No filesystem access outside `/tmp`.** Writes are limited to a temporary directory that is destroyed after execution.
- **No process inspection.** Your code cannot view or interact with other processes on the host.
- **No kernel operations.** System calls are restricted via seccomp. Your code cannot load kernel modules, mount filesystems, or modify system configuration.
- **Resource-bounded.** Each execution is subject to the timeout, memory, and CPU limits of your tier.

### 6.2 Your Responsibility for Your Code

**You are solely responsible for the code you submit to MCPWorks.** We execute your code as instructed. We do not review, validate, or endorse the logic, output, or fitness of your functions.

MCPWorks is a platform for code execution, not a publisher of your code. We do not control what your functions compute, return, or how you use the results.

<!-- VOYER LAW REVIEW #1: Platform vs. publisher distinction — confirm this framing
     provides adequate liability protection under Canadian law for user-submitted code
     that may produce harmful outputs or be used to process third-party data. -->

### 6.3 Prohibited Code

You must not submit code that:

- Attempts to escape the sandbox or access resources outside the sandbox boundary
- Mines cryptocurrency or performs proof-of-work computation
- Generates denial-of-service attacks or network floods
- Deliberately exhausts platform resources (memory bombs, fork bombs, infinite loops designed to consume CPU)
- Generates, stores, or distributes child sexual abuse material (CSAM)

Detailed operational boundaries, including namespace naming rules and API usage guidelines, are defined in the [Acceptable Use Policy](https://www.mcpworks.io/aup).

Violation of these rules may result in immediate suspension without prior notice.

---

## 7. Intellectual Property

### 7.1 Your Code

**You retain all intellectual property rights in your code.** Creating or executing functions on MCPWorks does not transfer any ownership to us.

We require a limited license to operate the Service: you grant MCPWorks a non-exclusive, revocable license to store, execute, cache, back up, and display (to you) your functions and execution data solely for the purpose of providing the Service. This license terminates when you delete a function or close your account.

**We do not obtain any license to:**
- Train AI or machine learning models on your code or data
- Share your code with other users or third parties
- Create derivative works based on your code
- Sublicense your code to anyone

### 7.2 MCPWorks Property

The Service, its infrastructure, documentation, APIs, and branding are the property of MCPWORKS TECHNOLOGIES INC. These Terms do not grant you any rights to our intellectual property beyond the right to use the Service as described here.

### 7.3 Feedback

If you voluntarily provide suggestions, ideas, or feedback about the Service, you grant us a non-exclusive, royalty-free, perpetual license to use that feedback for any purpose. This applies only to feedback about the Service, never to your code or execution data.

### 7.4 When We May Access Your Code

We will access or inspect your code only in the following circumstances:

- **At your request** for debugging or support purposes
- **Automated malware scanning** applied uniformly across the platform
- **Active security incident** where your account is involved
- **Legal order** requiring disclosure, subject to Section 5.2 of our [Privacy Policy](https://www.mcpworks.io/privacy)

<!-- VOYER LAW REVIEW #2: Confirm the code inspection carve-outs are appropriately
     narrow and align with PIPEDA requirements for purpose limitation. -->

---

## 8. Service Levels

### 8.1 Free, Builder, and Pro Tiers

We do not offer service level commitments for Free, Builder, or Pro tiers. We aim for high availability but make no guarantees. We will provide reasonable notice of planned maintenance.

### 8.2 Enterprise Tier SLA

Enterprise tier subscribers receive a 99.9% monthly uptime commitment measured by our health endpoint (`status.mcpworks.io`). If we fail to meet this commitment in a calendar month, you are eligible for service credits:

| Monthly Uptime | Credit |
|---------------|--------|
| 99.0% - 99.9% | 10% of monthly fee |
| 95.0% - 99.0% | 25% of monthly fee |
| Below 95.0% | 50% of monthly fee |

Credits are applied to future invoices and do not exceed 50% of a single month's fee. Credits are your sole remedy for failure to meet the uptime commitment.

### 8.3 Maintenance

We perform routine maintenance on Sundays from 06:00 to 10:00 UTC. Planned downtime exceeding 15 minutes will be announced at least 48 hours in advance via status.mcpworks.io and email to affected accounts.

### 8.4 API Changes

- **Non-breaking changes** (new endpoints, optional parameters, additional response fields): 30 days notice.
- **Breaking changes** (endpoint removal, changed required parameters, altered response structure): 90 days notice.
- **Alpha/beta features:** 14 days notice.
- **Package updates** to the sandbox runtime environment may occur at any time. Removal of packages from the runtime will be announced 7 days in advance.

---

## 9. Warranties and Disclaimers

### 9.1 What We Warrant

We warrant that:

- We will provide the Service in a professional and workmanlike manner
- We have the legal right to provide the Service
- We will comply with laws applicable to our operation of the Service
- We implement reasonable security measures as described in our [Privacy Policy](https://www.mcpworks.io/privacy)

### 9.2 What We Disclaim

**THE SERVICE IS PROVIDED "AS IS" AND "AS AVAILABLE."** TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, INCLUDING THE BRITISH COLUMBIA SALE OF GOODS ACT AND ANY ANALOGOUS LEGISLATION, MCPWORKS DISCLAIMS ALL WARRANTIES NOT EXPRESSLY STATED IN SECTION 9.1, WHETHER EXPRESS, IMPLIED, STATUTORY, OR OTHERWISE, INCLUDING IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, TITLE, AND NON-INFRINGEMENT.

Without limiting the above, we do not warrant that:

- The Service will be uninterrupted or error-free
- The sandbox environment will be perfectly secure against all attacks
- The results produced by your code will be accurate, complete, or fit for any particular purpose
- The runtime environment will include any specific package or library version

---

## 10. Limitation of Liability

### 10.1 Exclusion of Consequential Damages

**TO THE MAXIMUM EXTENT PERMITTED BY LAW, MCPWORKS WILL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, OR LOSS OF PROFITS, REVENUE, DATA, OR BUSINESS OPPORTUNITY** ARISING OUT OF OR RELATED TO THESE TERMS OR THE SERVICE, REGARDLESS OF THE THEORY OF LIABILITY AND EVEN IF WE HAVE BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.

### 10.2 Liability Cap

OUR TOTAL AGGREGATE LIABILITY ARISING OUT OF OR RELATED TO THESE TERMS OR THE SERVICE WILL NOT EXCEED THE **GREATER OF (A) THE AMOUNTS YOU PAID TO MCPWORKS IN THE 12 MONTHS PRECEDING THE CLAIM, OR (B) ONE HUNDRED CANADIAN DOLLARS ($100 CAD).**

### 10.3 Carve-Outs

The limitations in Sections 10.1 and 10.2 do not apply to:

- Liability arising from fraud or intentional misconduct
- Liability arising from gross negligence
- Death or personal injury caused by our negligence
- Our obligations under PIPEDA and applicable privacy legislation

<!-- VOYER LAW REVIEW #3: Confirm the liability cap structure and carve-outs are
     enforceable under BC law. Particular attention to whether the $100 CAD floor
     is adequate for free-tier users and whether the PIPEDA carve-out is
     appropriately scoped. -->

---

## 11. Indemnification

You agree to indemnify, defend, and hold harmless MCPWorks, its officers, directors, and employees from and against any third-party claims, damages, costs, and expenses (including reasonable legal fees) arising from:

- Code you submit or execute on the Service
- Your violation of these Terms or the AUP
- Personal data you process through the Service where you are the data controller
- Your misrepresentation of your identity or authority
- Third-party claims arising from your use of function outputs
- Your violation of any applicable law or regulation

<!-- VOYER LAW REVIEW #4: Confirm one-way indemnification is enforceable under BC law
     and that the scope is not overbroad (particularly the "code you submit" clause).
     Consider whether mutual indemnification for IP infringement is needed. -->

---

## 12. Termination

### 12.1 Termination by You

You may close your account at any time through your account settings or by emailing support@mcpworks.io. Upon cancellation:

- Your subscription remains active until the end of the current billing period
- You may export your data before the account is closed (see Privacy Policy Section 8.4)
- After the billing period ends, your account and all associated data will be deleted within 30 days, subject to our legal retention obligations

### 12.2 Termination by MCPWorks

**For critical violations** (illegal activity, active security threats, CSAM): we may suspend your account immediately without prior notice.

**For non-critical violations** (AUP violations, payment disputes, Terms violations): we will follow this escalation:

1. Written warning with description of the violation
2. 7-day cure period to resolve the violation
3. Suspension if not cured (functions stop executing, data preserved)
4. 14 days written notice before permanent termination

**For convenience** (no cause required): we may terminate your account with 30 days written notice and a pro-rata refund of any prepaid fees for the unused portion of your billing period.

### 12.3 Effect of Termination

Upon termination:
- Your right to use the Service ends immediately (or at the end of your billing period for user-initiated cancellation)
- We will preserve your data for 30 days after termination to allow export
- After 30 days, all data is permanently deleted except as required by law
- Sections 7 (Intellectual Property), 9 (Warranties), 10 (Limitation of Liability), 11 (Indemnification), 13 (Dispute Resolution), and 16 (General) survive termination

---

## 13. Dispute Resolution

### 13.1 Informal Resolution

Before initiating formal proceedings, you and MCPWorks agree to attempt to resolve any dispute through good-faith negotiation for a period of 30 days. Send dispute notices to legal@mcpworks.io.

### 13.2 Binding Arbitration

If negotiation does not resolve the dispute, either party may submit the dispute to binding arbitration administered by the British Columbia International Commercial Arbitration Centre (BCICAC) under its rules then in effect. The arbitration will be conducted by a single arbitrator in Vancouver, British Columbia. The language of arbitration will be English.

### 13.3 Exceptions

The following disputes are not subject to arbitration:

- **Small claims.** Either party may bring a claim in the BC Provincial Court (Small Claims) for disputes under $5,000 CAD.
- **Injunctive relief.** Either party may seek injunctive or equitable relief from a court of competent jurisdiction to prevent irreparable harm.

### 13.4 Class Action Waiver

To the extent permitted by law, you and MCPWorks agree that disputes will be resolved on an individual basis. Neither party will bring or participate in a class action, class arbitration, or representative proceeding.

---

## 14. Privacy

Our collection, use, and disclosure of personal information is governed by our [Privacy Policy](https://www.mcpworks.io/privacy), which is incorporated into these Terms by reference.

By using the Service, you consent to the collection and use of your information as described in the Privacy Policy. Where you process personal data of third parties through the Service, you are the data controller and MCPWorks acts as a data processor. See Privacy Policy Section 10 for details.

You may exercise your privacy rights (access, correction, deletion, portability) as described in the Privacy Policy.

---

## 15. Amendments

We may modify these Terms at any time. For material changes, we will provide at least 30 days notice by email and by posting the updated Terms at [https://www.mcpworks.io/terms](https://www.mcpworks.io/terms).

Your continued use of the Service after the effective date of a modification constitutes acceptance of the updated Terms. If you do not agree with a material change, you may terminate your account before the change takes effect and receive a pro-rata refund of any prepaid fees for the unused portion of your billing period.

The current and previous versions of these Terms are maintained in our version control system and are available upon request.

---

## 16. General

### 16.1 Governing Law

These Terms are governed by the laws of the Province of British Columbia and the federal laws of Canada applicable therein, without regard to conflict of laws principles.

### 16.2 Force Majeure

Neither party is liable for failure to perform obligations due to events beyond its reasonable control, including: natural disasters, war, terrorism, government actions, pandemic, power outages, internet infrastructure failures, or cloud provider outages. If a force majeure event continues for more than 60 days, either party may terminate the affected portion of these Terms with written notice.

### 16.3 Assignment

You may not assign these Terms without our written consent. MCPWorks may assign these Terms without your consent in connection with a merger, acquisition, corporate reorganization, or sale of all or substantially all of our assets. We will notify you of any such assignment.

<!-- VOYER LAW REVIEW #5: Confirm the assignment clause is enforceable and
     sufficiently protective of user rights upon M&A. Consider whether notice
     should be given before or after the assignment takes effect. -->

### 16.4 Severability

If any provision of these Terms is held unenforceable, that provision will be modified to the minimum extent necessary to make it enforceable, and the remaining provisions continue in full force and effect.

### 16.5 Entire Agreement

These Terms, together with the Privacy Policy and the AUP, constitute the entire agreement between you and MCPWorks regarding the Service and supersede all prior agreements.

### 16.6 Waiver

Our failure to enforce any right or provision of these Terms does not constitute a waiver of that right or provision.

### 16.7 Export Control

You represent that you are not located in a country subject to Canadian or applicable international sanctions, and that you are not on any applicable denied-party list. We reserve the right to deny service where required by law.

### 16.8 Notices

Notices to MCPWorks must be sent to legal@mcpworks.io. Notices to you will be sent to the email address associated with your account. Email notices are deemed received 24 hours after sending.

---

## 17. Contact

**MCPWORKS TECHNOLOGIES INC.**
Email: legal@mcpworks.io
Support: support@mcpworks.io
Security: security@mcpworks.io
Privacy: privacy@mcpworks.io

Vancouver, British Columbia, Canada

---

*These Terms of Service are effective as of February 17, 2026.*
*Version 1.0.0*
