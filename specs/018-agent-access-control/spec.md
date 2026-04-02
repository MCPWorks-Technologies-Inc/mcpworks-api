# Feature Specification: Per-Agent Function Visibility and State Access Control

**Feature Branch**: `018-agent-access-control`  
**Created**: 2026-04-01  
**Status**: Draft  
**Input**: User description: "Per-agent function visibility and state access control (issue #34)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Restrict Agent to Specific Services (Priority: P1)

A namespace owner configures an agent so it can only call functions within specific services. For example, a social-media posting agent should only access the "social" and "content" services, not "billing" or "admin" services. The owner sets up service-level allow rules, and when the agent attempts to call a function outside its allowed services, the call is denied with a clear error.

**Why this priority**: This is the core value proposition — least-privilege enforcement for agents. Without it, any agent can call any function, creating security and operational risk.

**Independent Test**: Can be fully tested by creating an agent, configuring service-level allow rules, and verifying that function calls to allowed services succeed while calls to disallowed services are denied.

**Acceptance Scenarios**:

1. **Given** an agent with an allow rule for services "social" and "content", **When** the agent calls a function in the "social" service, **Then** the call proceeds normally.
2. **Given** an agent with an allow rule for services "social" and "content", **When** the agent calls a function in the "billing" service, **Then** the call is denied with an error indicating the function is not accessible to this agent.
3. **Given** an agent with no access rules configured, **When** the agent calls any function, **Then** the call proceeds normally (backwards compatible).

---

### User Story 2 - Restrict Agent State Key Access (Priority: P2)

A namespace owner configures an agent so it can only read and write specific state keys. For example, a content agent should be able to access "content.*" and "cache.*" state keys but not "secrets.*" or "billing.*" keys. When the agent attempts to read or write a restricted key, the operation is denied.

**Why this priority**: State keys can contain sensitive data (API tokens, billing info, secrets). Restricting state access prevents agents from accessing data outside their intended scope.

**Independent Test**: Can be fully tested by creating an agent, configuring state key rules, and verifying that state read/write operations to allowed keys succeed while operations on restricted keys are denied.

**Acceptance Scenarios**:

1. **Given** an agent with an allow rule for state keys "content.*" and "cache.*", **When** the agent reads the key "content.posts", **Then** the read succeeds.
2. **Given** an agent with an allow rule for state keys "content.*" and "cache.*", **When** the agent writes to "secrets.api_token", **Then** the write is denied with an error.
3. **Given** an agent with a deny rule for state keys "secrets.*", **When** the agent lists all state keys, **Then** keys matching "secrets.*" are excluded from the listing.
4. **Given** an agent with no state access rules configured, **When** the agent reads or writes any state key, **Then** the operation proceeds normally (backwards compatible).

---

### User Story 3 - Function-Level Deny Rules with Glob Patterns (Priority: P2)

A namespace owner blocks an agent from calling specific functions using glob patterns, even within otherwise-allowed services. For example, an agent allowed to use the "admin" service might be blocked from "admin.delete_*" functions. Deny rules take precedence over allow rules.

**Why this priority**: Provides fine-grained control beyond service-level restrictions. Critical for services that contain a mix of safe and dangerous operations.

**Independent Test**: Can be fully tested by configuring a deny rule with glob patterns and verifying that matching functions are blocked while non-matching functions in the same service proceed.

**Acceptance Scenarios**:

1. **Given** an agent with a deny rule for functions "admin.delete_*", **When** the agent calls "admin.delete_user", **Then** the call is denied.
2. **Given** an agent with a deny rule for functions "admin.delete_*", **When** the agent calls "admin.list_users", **Then** the call proceeds normally.
3. **Given** an agent with both an allow rule for service "admin" and a deny rule for "admin.delete_*", **When** the agent calls "admin.delete_user", **Then** the deny rule takes precedence and the call is denied.

---

### User Story 4 - View and Manage Access Rules (Priority: P3)

A namespace owner can view, add, and remove access rules for any agent in their namespace. Each rule has a unique identifier so individual rules can be removed without affecting others.

**Why this priority**: Management tooling is necessary for usability but not for core enforcement.

**Independent Test**: Can be fully tested by adding rules, listing them, removing specific rules by ID, and verifying the changes take effect.

**Acceptance Scenarios**:

1. **Given** an agent with three access rules configured, **When** the owner lists the agent's access rules, **Then** all three rules are returned with their IDs, types, and patterns.
2. **Given** an agent with a rule, **When** the owner removes the rule by its ID, **Then** the rule is removed and the agent's access is updated accordingly.
3. **Given** an agent with no access rules, **When** the owner lists the agent's access rules, **Then** an empty list is returned indicating unrestricted access.

---

### Edge Cases

- What happens when conflicting allow and deny rules exist for the same function? Deny takes precedence.
- What happens when an agent's access rules reference a service that doesn't exist? The rule is stored but has no effect until the service exists.
- What happens when a function is called via a procedure step and the agent executing the procedure lacks access? The step fails with an access denied error, and the procedure execution records the failure.
- What happens when an agent has state key allow rules and another agent (without restrictions) writes to a key the first agent can't read? The write succeeds — rules are per-agent, not global.
- How does this interact with MCP server plugin rules? They are separate systems. MCP server rules filter third-party MCP server tools. Agent access rules filter native functions and state. Both can apply simultaneously.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support per-agent access rules that restrict which native functions the agent can call.
- **FR-002**: System MUST support per-agent access rules that restrict which state keys the agent can read and write.
- **FR-003**: Access rules MUST support glob pattern matching (fnmatch-style) for service names, function names, and state keys.
- **FR-004**: System MUST support both allow-list and deny-list rule types for functions and state keys.
- **FR-005**: When both allow and deny rules apply to the same resource, deny MUST take precedence.
- **FR-006**: When no access rules are configured for an agent, the agent MUST have unrestricted access (backwards compatible).
- **FR-007**: Access rules MUST only apply to agents. The namespace owner (MCP user with API key) MUST always retain full access regardless of agent rules.
- **FR-008**: System MUST provide tools to add, list, and remove access rules for agents.
- **FR-009**: Each access rule MUST have a unique identifier for targeted removal.
- **FR-010**: When an agent is denied access to a function or state key, the system MUST return a clear error indicating the denial and the rule that caused it.
- **FR-011**: State key listing operations MUST filter out keys that the agent is denied access to.
- **FR-012**: Access rules MUST be enforced at the execution layer, before function dispatch and before state read/write operations.
- **FR-013**: Access rules MUST be enforced when functions are called within procedure steps executed by an agent.

### Key Entities

- **Access Rule**: A per-agent restriction defining allowed or denied access to functions or state keys. Contains: rule ID, agent reference, rule type (allow/deny), target type (function/state), pattern (glob), and optional scope (read/write for state).
- **Agent**: Extended with an optional set of access rules. An agent with no rules has unrestricted access.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Namespace owners can configure function access rules for an agent and see them enforced on the next function call with no delay.
- **SC-002**: Namespace owners can configure state access rules for an agent and see them enforced on the next state operation with no delay.
- **SC-003**: Access rule evaluation adds less than 5ms overhead per function call or state operation.
- **SC-004**: 100% of function calls and state operations by agents with configured rules are checked against the rules before execution.
- **SC-005**: Existing agents with no access rules configured continue to operate with no change in behavior.
- **SC-006**: Rule management operations (add, list, remove) complete in under 1 second.

## Assumptions

- Function names follow the pattern "service_name.function_name" for matching purposes.
- The existing fnmatch glob matching from the rule engine is sufficient for pattern matching needs.
- Access rules are stored alongside agent configuration, not in a separate global policy system.
- Rule evaluation order: deny rules are checked first; if any deny rule matches, access is denied regardless of allow rules.
- State key restrictions apply to get, set, delete, and list state key operations.
