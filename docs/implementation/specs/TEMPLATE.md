# [Component Name] - Specification

**Version:** 0.1.0 (Draft)
**Created:** YYYY-MM-DD
**Status:** Draft | Logic Check | Review | Approved
**Spec Author:** [Name]
**Reviewers:** [Names]

---

## 1. Overview

### 1.1 Purpose

[1-2 sentences: What is this component and why does it exist?]

### 1.2 User Value

[What problem does this solve for users? What pain point does it address?]

### 1.3 Success Criteria

**This spec is successful when:**
- [ ] Measurable outcome 1
- [ ] Measurable outcome 2
- [ ] Measurable outcome 3

### 1.4 Scope

**In Scope:**
- Feature/capability 1
- Feature/capability 2

**Out of Scope:**
- Future feature 1 (will be addressed in separate spec)
- Future feature 2

---

## 2. User Scenarios

### 2.1 Primary Scenario: [Name]

**Actor:** [AI Assistant / Developer / Customer]
**Goal:** [What they want to accomplish]
**Context:** [Situation/preconditions]

**Workflow:**
1. User action 1
2. System response 1
3. User action 2
4. System response 2
5. Outcome

**Success:** [What success looks like]
**Failure:** [What failure looks like and how it's handled]

### 2.2 Secondary Scenario: [Name]

[Repeat structure above]

---

## 3. Functional Requirements

### 3.1 Core Capabilities

**REQ-[ID]-001: [Requirement Name]**
- **Description:** Must do X when Y happens
- **Priority:** Must Have | Should Have | Nice to Have
- **Rationale:** Why this is important
- **Acceptance:** How we know it's implemented correctly

**REQ-[ID]-002: [Next Requirement]**
[Repeat structure]

### 3.2 Data Requirements

**What data must be stored:**
- Data element 1 (format, constraints)
- Data element 2 (relationships)

**What data must be exposed:**
- Via MCP tool X: fields A, B, C
- Via MCP resource Y: fields D, E, F

### 3.3 Integration Requirements

**Upstream Dependencies:**
- System A provides: data/events X
- System B provides: data/events Y

**Downstream Consumers:**
- System C consumes: data/events Z
- System D consumes: data/events W

---

## 4. Non-Functional Requirements

### 4.1 Performance

- **Response Time:** p95 < X ms for operation Y
- **Throughput:** Must handle X operations/second
- **Token Efficiency:** Average response < X tokens

### 4.2 Security

- **Authentication:** How users/systems authenticate
- **Authorization:** Who can access what
- **Data Protection:** Encryption, PII handling
- **Audit:** What must be logged

### 4.3 Reliability

- **Availability:** Target uptime percentage
- **Error Handling:** How failures are detected and handled
- **Recovery:** How system recovers from failures
- **Data Integrity:** How data consistency is maintained

### 4.4 Scalability

- **Current Scale:** Expected load for Phase 1
- **Future Scale:** Expected load for Phase 2/3
- **Bottlenecks:** Known scaling limitations

---

## 5. Constraints & Assumptions

### 5.1 Technical Constraints

- Constraint 1: Must use X because Y
- Constraint 2: Cannot use Z because W

### 5.2 Business Constraints

- Budget: Max $X for this component
- Timeline: Must be ready by [date]
- Resources: Solo developer vs team

### 5.3 Assumptions

- Assumption 1: Users will behave like X
- Assumption 2: Integration Y will be available
- **Risk if wrong:** What breaks if assumption is false

---

## 6. Error Scenarios & Edge Cases

### 6.1 Error Scenario: [Name]

**Trigger:** What causes this error
**Expected Behavior:** How system should respond
**User Experience:** What user sees
**Recovery:** How user can recover
**Logging:** What gets logged
**Monitoring:** What alert fires

### 6.2 Edge Case: [Name]

**Scenario:** Unusual but valid situation
**Expected Behavior:** How system should handle it
**Rationale:** Why this matters

---

## 7. Token Efficiency Analysis

### 7.1 Tool Definitions

**Estimated tokens for tool schemas:** X tokens total

### 7.2 Typical Responses

**Operation:** Do X
**Response Size:** Y tokens (summary) | Z tokens (detailed)
**Optimization Strategy:** [How we keep it small]

### 7.3 Worst Case

**Largest possible response:** X tokens
**Mitigation:** Pagination, streaming, compression

---

## 8. Security Analysis

### 8.1 Threat Model

**Threat:** Attacker does X
**Impact:** [Confidentiality | Integrity | Availability]
**Mitigation:** We prevent this by Y
**Residual Risk:** [Low | Medium | High]

### 8.2 PII/Sensitive Data

**What sensitive data is involved:**
- Data type 1: How it's protected
- Data type 2: How it's protected

### 8.3 Compliance

**Relevant regulations:**
- PIPEDA (Canada): Requirement X
- GDPR (if EU customers): Requirement Y

---

## 9. Observability Requirements

### 9.1 Metrics

**Key metrics to track:**
- Metric 1: What it measures, why it matters
- Metric 2: What it measures, why it matters

### 9.2 Logging

**What must be logged:**
- Event type 1: Fields to include
- Event type 2: Fields to include

**What must NOT be logged:**
- PII, secrets, sensitive data

### 9.3 Tracing

**Operations to trace:**
- Operation 1: Key spans
- Operation 2: Key spans

### 9.4 Alerting

**Alerts to configure:**
- Alert 1: Condition, severity, who gets notified
- Alert 2: Condition, severity, who gets notified

---

## 10. Testing Requirements

### 10.1 Unit Tests

**Must test:**
- Business logic function 1
- Business logic function 2
- Error handling scenarios

### 10.2 Integration Tests

**Must test:**
- Component A → Component B integration
- Error propagation across components

### 10.3 E2E Tests

**User workflows to test:**
- Happy path: User does X, expects Y
- Error path: User does X when Y unavailable, expects Z

### 10.4 Performance Tests

**Load tests:**
- Scenario 1: X concurrent users doing Y
- Scenario 2: Sustained load for Z minutes

---

## 11. Future Considerations

### 11.1 Phase 2 Enhancements

**Not in this spec, but planned:**
- Enhancement 1: Brief description
- Enhancement 2: Brief description

### 11.2 Known Limitations

**What this spec doesn't address:**
- Limitation 1: Why it's acceptable for now
- Limitation 2: When we'll address it

---

## 12. Spec Completeness Checklist

**Before moving to Plan phase:**

- [ ] Clear user value proposition stated
- [ ] Success criteria defined and measurable
- [ ] All functional requirements enumerated
- [ ] All constraints documented
- [ ] Error scenarios identified
- [ ] Security requirements specified
- [ ] Performance requirements quantified
- [ ] Token efficiency requirements stated
- [ ] Testing requirements defined
- [ ] Observability requirements defined
- [ ] Reviewed for Constitution compliance
- [ ] Logic checked (internally consistent)
- [ ] Peer reviewed (if team > 1)

---

## 13. Approval

**Status:** Draft | Approved | Superseded

**Approvals:**
- [ ] CTO (Simon Carr)
- [ ] CEO (if business impact)
- [ ] Security Review (if sensitive data/operations)

**Approved Date:** YYYY-MM-DD
**Next Review:** YYYY-MM-DD (or when requirements change)

---

## Changelog

**v0.1.0 (YYYY-MM-DD):**
- Initial draft

**v1.0.0 (YYYY-MM-DD):**
- Approved for Plan phase
