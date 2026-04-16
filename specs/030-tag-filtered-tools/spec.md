# Feature Specification: Tag-Filtered Tools List

**Feature Branch**: `030-tag-filtered-tools`  
**Created**: 2026-04-15  
**Status**: Draft  
**Input**: User description: "#41 — Filter visible functions by tag in MCP config. Allow MCP clients to pass a tags query parameter to filter which functions appear in tools/list."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Filter tools/list by tag (Priority: P1)

A namespace owner has 36 functions in `mcpworkssocial/social` but wants a specific agent to only see the 5 Bluesky-related functions. They configure the MCP connection URL with a `tags` query parameter. When the agent connects and requests `tools/list`, it only sees the functions tagged with the specified tags — reducing context window usage and improving tool selection accuracy.

**Why this priority**: This is the entire feature. Tag filtering on the tool list is the core and only user-facing change.

**Independent Test**: Connect to a namespace with `?tags=bluesky` and verify `tools/list` returns only functions tagged `bluesky`, while omitting untagged functions or functions with other tags.

**Acceptance Scenarios**:

1. **Given** a namespace with 10 functions where 3 are tagged "bluesky", **When** a client connects with `?tags=bluesky` and requests `tools/list`, **Then** only the 3 bluesky-tagged functions appear in the response.
2. **Given** a client connects with `?tags=bluesky,monitoring`, **When** `tools/list` is requested, **Then** functions tagged with EITHER "bluesky" OR "monitoring" appear (OR filter, not AND).
3. **Given** a client connects with no `tags` parameter, **When** `tools/list` is requested, **Then** ALL functions appear (full backward compatibility).
4. **Given** a client connects with `?tags=nonexistent`, **When** `tools/list` is requested, **Then** zero user functions appear (only system tools like `_env_status` remain).
5. **Given** a function has multiple tags including "bluesky", **When** the client filters by `?tags=bluesky`, **Then** that function appears in the list.

---

### User Story 2 - Tag filter applies only to tools/list, not tools/call (Priority: P2)

A caller filters tools/list by tag to reduce context, but can still call any function by name — the tag filter is a visibility filter, not an access control mechanism. This prevents the tag filter from accidentally blocking legitimate function calls.

**Why this priority**: Important correctness guarantee. If tag filtering blocked execution, it would break cross-function calls and procedures that invoke unfiltered functions.

**Independent Test**: Connect with `?tags=bluesky`, then call a function that is NOT tagged "bluesky" by name. Verify it executes successfully.

**Acceptance Scenarios**:

1. **Given** a client connected with `?tags=bluesky`, **When** the client calls `social.send-discord-report` (which is not tagged "bluesky"), **Then** the function executes normally — tag filtering is visibility only.

---

### Edge Cases

- What happens when tags parameter is empty string (`?tags=`)? Treat as no filter — show all functions.
- What happens when tags contain whitespace (`?tags= bluesky , social `)? Trim whitespace from each tag.
- What happens when tags parameter appears multiple times (`?tags=a&tags=b`)? Combine all values as OR filter.
- What happens with the SSE transport (not just JSON-RPC POST)? Tags are on the URL, so they apply to the SSE session for the entire connection lifetime.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The MCP run endpoint MUST accept an optional `tags` query parameter containing a comma-separated list of tag names.
- **FR-002**: When `tags` is provided, `tools/list` MUST return only functions that have at least one matching tag (OR semantics).
- **FR-003**: When `tags` is not provided or is empty, `tools/list` MUST return all functions (backward compatible).
- **FR-004**: Tag filtering MUST NOT affect `tools/call` — any function can be called by name regardless of the tag filter.
- **FR-005**: Tag matching MUST be case-insensitive.
- **FR-006**: System tools (e.g., `_env_status`) MUST always appear in `tools/list` regardless of tag filter.

### Key Entities

- **Tag Filter**: A set of tag strings extracted from the URL query parameter, applied as an OR filter against function tags during `tools/list` generation. Not persisted — it's a per-connection runtime filter.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A namespace with 36 functions filtered to 5 tags reduces the `tools/list` response size by at least 80%.
- **SC-002**: Existing MCP connections without `tags` parameter continue to work identically — zero breaking changes.
- **SC-003**: Tag filtering adds no measurable latency to `tools/list` responses (filtering is in-memory, not a database query change).

## Assumptions

- Functions already have a `tags` array field (ARRAY(String), nullable) in the data model — no schema changes needed.
- The tag filter is extracted from URL query parameters, which are preserved across the MCP session (SSE connections maintain the original URL).
- This is a visibility filter, not a security mechanism — it reduces noise, not access.
