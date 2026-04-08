# Data Model: Namespace Telemetry Webhook

**Date**: 2026-04-08

## Entity Changes

### Namespace (MODIFIED)

**Table**: `namespaces`
**Change**: Add 3 columns for webhook configuration

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| **telemetry_webhook_url** | **Text** | **NULL** | **NEW: Destination URL for telemetry events (HTTPS required, HTTP allowed for localhost)** |
| **telemetry_webhook_secret_encrypted** | **LargeBinary** | **NULL** | **NEW: HMAC secret ciphertext (AES-256-GCM envelope encryption)** |
| **telemetry_webhook_secret_dek** | **LargeBinary** | **NULL** | **NEW: Encrypted DEK for the HMAC secret** |

**Batching config** (stored in existing JSONB patterns or as additional columns — TBD in implementation):
- `telemetry_batch_enabled`: boolean, default false
- `telemetry_batch_interval_seconds`: integer, default 10

**Note**: Batching config can be stored as a JSONB column `telemetry_config` to avoid column proliferation, following the pattern used by `scanner_pipeline` JSONB on the same table.

### Telemetry Event (TRANSIENT — not persisted)

Constructed in memory per execution, serialized as JSON for delivery. Never stored in the database.

| Field | Type | Description |
|-------|------|-------------|
| event | string | Always "tool_call" for v1 |
| namespace | string | Namespace name |
| data.function | string | `service.function` qualified name |
| data.execution_id | string | UUID of the execution |
| data.execution_time_ms | integer | Wall-clock execution time |
| data.success | boolean | Whether execution succeeded |
| data.backend | string | Backend type (e.g., "code_sandbox") |
| data.version | integer | Function version number |
| data.timestamp | string | ISO 8601 timestamp (UTC) |

**Excluded** (per FR-003): input_data, result_data, error_message, stderr, stdout.

**Estimated size**: ~300-500 bytes per event.

## Migration

**File**: `alembic/versions/20260408_000002_add_telemetry_webhook_columns.py`

```sql
ALTER TABLE namespaces ADD COLUMN telemetry_webhook_url TEXT NULL;
ALTER TABLE namespaces ADD COLUMN telemetry_webhook_secret_encrypted BYTEA NULL;
ALTER TABLE namespaces ADD COLUMN telemetry_webhook_secret_dek BYTEA NULL;
ALTER TABLE namespaces ADD COLUMN telemetry_config JSONB NULL;
```

**Rollback**: Drop all 4 columns.
**Risk**: Low — additive nullable columns, no data migration.
