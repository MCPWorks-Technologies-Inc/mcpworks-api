# mcpworks Infrastructure MCP Server - Phase 2 Specification

**Version:** 2.1.0
**Created:** 2025-10-31
**Last Updated:** 2025-10-31
**Status:** Ready for Plan Phase
**Spec Author:** Simon Carr (CTO)
**Dependencies:** Phase 1 Spec v1.3.0

---

## 1. Overview

### 1.1 Purpose

This specification extends the mcpworks Infrastructure MCP Server (Phase 1 v1.3.0) with multi-region deployment capabilities and database managed services. These features enable AI assistants to provision globally distributed applications with production-grade data persistence.

### 1.2 Relationship to Phase 1

**Phase 1 Foundation (v1.3.0):**
- Single-region hosting (Toronto datacenter)
- Application deployment and scaling
- Domain, SSL, third-party integrations
- Credit system with hold/commit/release

**Phase 2 Additions (v2.0.0):**
- Multi-region deployment (5 regions: Toronto, New York, London, Singapore, Frankfurt)
- Database managed services (PostgreSQL, MySQL, Redis)
- Cross-region traffic routing and failover
- Database backups and point-in-time recovery

**What remains Phase 1-compatible:**
- All 19 Phase 1 tools continue to work unchanged
- Single-region services default to Toronto (backward compatible)
- Credit system extends with new burn rates for regions/databases

### 1.3 User Value

**Problem Solved:** Phase 1 enables fast application deployment but lacks:
1. Global latency optimization (users in London experience 80ms+ latency from Toronto)
2. Production-grade data persistence (databases run in containers, not managed services)
3. High availability and failover (single datacenter = single point of failure)

**Solution:** Phase 2 adds:
1. **Multi-region deployments** → 20-50ms latency worldwide (vs 80-200ms single-region)
2. **Managed databases** → 99.95% uptime SLA, automated backups, zero ops burden
3. **Traffic routing** → Intelligent failover and latency-based routing

**Use Cases:**
- E-commerce store serving US + Europe → Deploy NYC + London, route by geo
- SaaS app requiring <50ms latency → Deploy 3+ regions with latency-based routing
- High-availability service → Primary + standby regions with automatic failover
- Database-heavy app → Managed PostgreSQL with daily backups and read replicas

---

## 2. Multi-Region Deployments

### 2.1 Available Regions

**Phase 2 Launch Regions (DigitalOcean):**
- `tor1` - Toronto, Canada (Phase 1 default)
- `nyc3` - New York, USA
- `lon1` - London, UK
- `sgp1` - Singapore
- `fra1` - Frankfurt, Germany

**Region Selection Criteria:**
- Geographic coverage: North America, Europe, Asia-Pacific
- Latency zones: <50ms for 80% of global internet users
- Provider availability: DigitalOcean datacenter presence
- Cost efficiency: Similar pricing across regions

**Future Expansion (post-Phase 2):**
- `sfo3` - San Francisco, USA
- `ams3` - Amsterdam, Netherlands
- `blr1` - Bangalore, India
- `syd1` - Sydney, Australia

### 2.2 New MCP Tools (Multi-Region)

#### Tool 20: `deploy_to_region`

Deploy application to additional geographic region (beyond primary).

**Parameters:**
- `service_id` (string, required): Existing service ID from `provision_service`
- `region` (string, required): Target region code (`nyc3`, `lon1`, `sgp1`, `fra1`)
- `traffic_weight` (integer, optional): Percentage of traffic to route to this region (0-100, default: 0 for standby)

**Returns:**
```json
{
  "deployment_id": "dep_london_abc123",
  "region": "lon1",
  "url": "https://app.multisphere.net",
  "region_endpoint": "https://lon1-app.multisphere.net",
  "status": "deploying",
  "traffic_weight": 0,
  "credits_held": 50.0,
  "estimated_completion": "2025-10-31T10:05:00Z"
}
```

**Credit Model:**
- Hold: 50 credits (deployment operation)
- Burn: 25 credits (actual deployment cost)
- Monthly burn: Same as primary region (e.g., 2 CPU / 4GB = 1,200 credits/month per region, equivalent to $12/month)

**Error Codes:**
- `service_not_found` - service_id doesn't exist
- `region_invalid` - Unsupported region code
- `region_already_deployed` - Service already exists in target region
- `insufficient_credits` - Cannot hold 50 credits for deployment

**Streaming:** Yes (SSE events: progress, log, credit_update, completed, error)

**SSE Event Payloads:**
```json
// Event: progress
{"type": "progress", "stage": "provisioning_infrastructure", "percent": 25, "message": "Creating droplet in lon1 region...", "timestamp": "2025-10-31T10:03:00Z"}

// Event: log
{"type": "log", "level": "info", "message": "Configuring network interfaces...", "timestamp": "2025-10-31T10:03:15Z"}

// Event: credit_update
{"type": "credit_update", "credits_consumed": 12.5, "credits_remaining": 487.5, "burn_rate_hourly": 0.5, "timestamp": "2025-10-31T10:03:30Z"}

// Event: completed
{"type": "completed", "deployment_id": "dep_london_abc123", "url": "https://lon1-app.multisphere.net", "credits_burned": 25.0, "duration_sec": 180, "timestamp": "2025-10-31T10:05:00Z"}

// Event: error
{"type": "error", "code": "region_capacity_full", "message": "Region lon1 at capacity. Try fra1 or wait 1-2 hours.", "credits_released": 50.0, "timestamp": "2025-10-31T10:03:45Z"}
```

**Token Estimate:** ~800 tokens (includes SSE stream documentation)

---

#### Tool 21: `list_regions`

List all available regions with latency estimates and pricing.

**Parameters:**
- `user_location` (string, optional): ISO 3166-1 alpha-2 country code for latency estimates (e.g., "US", "GB", "SG")

**Returns:**
```json
{
  "regions": [
    {
      "code": "tor1",
      "name": "Toronto, Canada",
      "continent": "North America",
      "estimated_latency_ms": 45,
      "available": true,
      "pricing_multiplier": 1.0
    },
    {
      "code": "nyc3",
      "name": "New York, USA",
      "continent": "North America",
      "estimated_latency_ms": 20,
      "available": true,
      "pricing_multiplier": 1.0
    },
    {
      "code": "lon1",
      "name": "London, UK",
      "continent": "Europe",
      "estimated_latency_ms": 80,
      "available": true,
      "pricing_multiplier": 1.0
    },
    {
      "code": "sgp1",
      "name": "Singapore",
      "continent": "Asia-Pacific",
      "estimated_latency_ms": 220,
      "available": true,
      "pricing_multiplier": 1.05
    },
    {
      "code": "fra1",
      "name": "Frankfurt, Germany",
      "continent": "Europe",
      "estimated_latency_ms": 95,
      "available": true,
      "pricing_multiplier": 1.0
    }
  ]
}
```

**Credit Model:** Free (no credit charge for listing regions)

**Error Codes:** None (always returns available regions)

**Token Estimate:** ~400 tokens

---

#### Tool 22: `configure_traffic_routing`

Configure how traffic is distributed across deployed regions.

**Parameters:**
- `service_id` (string, required): Service ID
- `routing_policy` (string, required): `round_robin`, `latency_based`, `weighted`, `failover`
- `weights` (object, optional): For `weighted` policy - `{"tor1": 50, "nyc3": 30, "lon1": 20}`
- `primary_region` (string, optional): For `failover` policy - primary region code
- `failover_regions` (array, optional): For `failover` policy - ordered list of failover regions

**Returns:**
```json
{
  "service_id": "svc_abc123",
  "routing_policy": "latency_based",
  "active_regions": ["tor1", "nyc3", "lon1"],
  "traffic_distribution": {
    "tor1": 35,
    "nyc3": 40,
    "lon1": 25
  },
  "health_check_interval_sec": 30,
  "failover_threshold_errors": 3
}
```

**Credit Model:** Free (routing configuration, no resource usage)

**Routing Policies:**

**1. `round_robin`**: Distribute traffic evenly across all regions (simple load balancing)
  - Use case: Equal capacity, no latency optimization

**2. `latency_based`**: Route users to nearest region based on geographic proximity (DNS-based)
  - Use case: Global SaaS app optimizing for latency
  - Implementation: GeoDNS with latency-based routing

**3. `weighted`**: Manual traffic distribution percentages (A/B testing, gradual rollouts)
  - Use case: Blue-green deployments, canary releases
  - Requires: `weights` object with percentages summing to 100

**4. `failover`**: Primary region handles all traffic, failover to standby on failure
  - Use case: High availability with cost optimization (only 1 region active)
  - Requires: `primary_region` and `failover_regions` array

**Parameter Validation:**

**For `weighted` policy:**
- `weights` object is required (error if missing: `missing_weights`)
- All keys in `weights` must be deployed region codes (error if not: `region_not_deployed`)
- All values must be integers 0-100
- Sum of all weight values must equal exactly 100 (error if not: `invalid_weights`)
- Example valid: `{"tor1": 50, "nyc3": 30, "lon1": 20}` (sum = 100)
- Example invalid: `{"tor1": 50, "nyc3": 40}` (sum = 90, missing 10%)

**For `failover` policy:**
- `primary_region` is required (error if missing: `missing_primary_region`)
- `failover_regions` array is required (error if missing: `missing_failover_regions`)
- `primary_region` must be a deployed region code (error if not: `region_not_deployed`)
- All regions in `failover_regions` must be deployed (error if not: `region_not_deployed`)
- `failover_regions` must have at least 1 region (error if empty: `empty_failover_regions`)
- `primary_region` cannot appear in `failover_regions` (error if duplicate: `primary_in_failover_list`)

**For `round_robin` and `latency_based` policies:**
- No additional parameters required
- `weights`, `primary_region`, and `failover_regions` are ignored if provided

**Error Codes:**
- `service_not_found` - service_id doesn't exist
- `region_not_deployed` - Specified region not deployed for this service
- `invalid_weights` - Weights don't sum to 100
- `missing_weights` - Weighted policy requires weights object
- `missing_primary_region` - Failover policy requires primary_region parameter
- `missing_failover_regions` - Failover policy requires failover_regions array
- `empty_failover_regions` - Failover policy requires at least 1 failover region
- `primary_in_failover_list` - primary_region cannot also be in failover_regions

**Token Estimate:** ~600 tokens

---

#### Tool 23: `get_region_status`

Get health and performance metrics for a specific region deployment.

**Parameters:**
- `service_id` (string, required): Service ID
- `region` (string, required): Region code

**Returns:**
```json
{
  "service_id": "svc_abc123",
  "region": "lon1",
  "status": "running",
  "health": "healthy",
  "deployment_id": "dep_london_abc123",
  "url": "https://lon1-app.multisphere.net",
  "metrics": {
    "cpu_pct": 45,
    "mem_pct": 62,
    "disk_pct": 38,
    "net_in_mbps": 12.5,
    "net_out_mbps": 8.3,
    "req_per_sec": 145,
    "avg_response_time_ms": 42,
    "error_rate_pct": 0.2
  },
  "traffic_weight": 25,
  "uptime_pct_30d": 99.97,
  "last_health_check": "2025-10-31T10:02:15Z",
  "burn_rate_monthly": 1200.0
}
```

**Credit Model:** Free (status check, no resource usage)

**Health States:**
- `healthy` - All health checks passing, accepting traffic
- `degraded` - Some health checks failing, accepting reduced traffic
- `unhealthy` - Health checks failing, removed from traffic rotation
- `maintenance` - Intentionally offline for updates

**Error Codes:**
- `service_not_found` - service_id doesn't exist
- `region_not_deployed` - Service not deployed in this region

**Token Estimate:** ~500 tokens

---

#### Tool 24: `remove_region_deployment`

Remove service deployment from a specific region (scale down multi-region).

**Parameters:**
- `service_id` (string, required): Service ID
- `region` (string, required): Region to remove
- `drain_traffic_sec` (integer, optional): Seconds to drain active connections (default: 60, max: 300)

**Returns:**
```json
{
  "service_id": "svc_abc123",
  "region": "lon1",
  "status": "draining",
  "remaining_connections": 23,
  "drain_timeout": "2025-10-31T10:03:00Z",
  "credits_released": 0.5
}
```

**Credit Model:**
- Release: Prorated credits for unused monthly burn (e.g., 15 days remaining → release 50% of held credits)

**Error Codes:**
- `service_not_found` - service_id doesn't exist
- `region_not_deployed` - Service not in this region
- `last_region` - Cannot remove last region (use `deprovision_service` instead)
- `primary_region_active` - Cannot remove primary region while failover configured

**Token Estimate:** ~400 tokens

---

### 2.3 Multi-Region Workflows

#### Workflow 1: Deploy Global SaaS App

**User:** "Deploy my app globally for low latency"

**Steps:**
1. `provision_service` → Toronto (default, primary region)
2. `deploy_application` → Deploy code to Toronto
3. `deploy_to_region` → New York (North America coverage)
4. `deploy_to_region` → London (Europe coverage)
5. `deploy_to_region` → Singapore (Asia-Pacific coverage)
6. `configure_traffic_routing` → `latency_based` (route users to nearest region)

**Result:**
- 4 regions active (Toronto, NYC, London, Singapore)
- <50ms latency for 85% of global users
- Automatic geo-routing via DNS

**Credit Burn:**
- Deployment: 25 credits × 3 regions = 75 credits (one-time)
- Monthly: 1,200 credits/month × 4 regions = 4,800 credits/month (equivalent to $48/month)

---

#### Workflow 2: Blue-Green Deployment (Gradual Rollout)

**User:** "Deploy new version gradually - test with 10% traffic first"

**Steps:**
1. `deploy_to_region` → `region: "nyc3"` (new region for blue-green)
2. `configure_traffic_routing` → `policy: "weighted"`, `weights: {"tor1": 90, "nyc3": 10}`
3. **Monitor metrics for 1 hour**
4. If successful: `configure_traffic_routing` → `weights: {"tor1": 0, "nyc3": 100}`
5. `remove_region_deployment` → `region: "tor1"` (old version)

**Result:**
- Zero-downtime deployment
- 10% canary testing phase
- Complete traffic migration after validation

---

#### Workflow 3: High Availability with Failover

**User:** "Set up high availability - primary in NYC, failover to Toronto"

**Steps:**
1. `provision_service` + `deploy_application` → Toronto (already exists)
2. `deploy_to_region` → `region: "nyc3"`, `traffic_weight: 0` (standby)
3. `configure_traffic_routing` → `policy: "failover"`, `primary_region: "nyc3"`, `failover_regions: ["tor1"]`

**Result:**
- NYC handles 100% of traffic
- Toronto stays warm (deployed but idle)
- Automatic failover if NYC health checks fail (30-second detection)
- Monthly cost: 2,400 credits/month (2 regions × 1,200 credits/month, equivalent to $24/month)

---

### 2.4 Multi-Region Credit Model

**Deployment Costs (one-time per region):**
- Deploy to region: 50 credit hold → 25 credit burn (same as initial deployment)

**Monthly Burn Rates (per region):**
- Same pricing as single-region (e.g., 2 CPU / 4GB = 1,200 credits/month, equivalent to $12/month)
- Multiplied by number of active regions
- Example: 3 regions × 1,200 credits/month = 3,600 credits/month (equivalent to $36/month)

**Data Transfer Costs (cross-region):**
- **Intra-region:** Free (traffic within same datacenter)
- **Cross-region (same continent):** $0.01/GB
- **Cross-region (different continents):** $0.02/GB
- **Egress to internet:** Included in monthly burn (up to 1TB/month per service)

**Failover Standby Regions:**
- Full monthly burn rate (deployed services consume resources even if idle)
- Rationale: Instant failover requires warm standby (can't provision on-demand during outage)

**Traffic Routing:**
- Free (DNS-based routing, no compute cost)

---

### 2.5 Multi-Region Error Scenarios

#### Scenario 1: Region Deployment Failure

**Trigger:** `deploy_to_region` fails due to provider capacity exhaustion in target region

**Expected Behavior:**
- SSE stream sends error event: `{"type": "error", "message": "Region lon1 at capacity", "code": "region_capacity_full"}`
- Credits released automatically (hold reversed)
- Service continues running in existing regions (no impact)

**User Experience:**
AI assistant shows: "Deployment to London failed: region at capacity. Try Frankfurt (fra1) or wait 1-2 hours for capacity. No charges incurred. (Hold released: 50 credits)"

**Recovery:** User selects alternative region or retries after capacity becomes available

**Logging:** Log region_deployment_failure with service_id, region, failure_reason=capacity_full, retry_after_seconds, credits_released

**Monitoring:** Alert if >10% of regional deployments fail in 1 hour (indicates provider-wide capacity issue)

---

#### Scenario 2: Cross-Region Network Partition

**Trigger:** Network issue causes Toronto <-> London connectivity loss (split-brain risk)

**Expected Behavior:**
- Health checks detect partition within 30 seconds
- Traffic routing removes affected region from rotation
- Region stays deployed but receives no traffic
- Alert triggered: "Region lon1 network unreachable from control plane"

**User Experience:**
AI assistant shows: "London region temporarily removed from traffic rotation due to network issues. Traffic automatically routed to NYC and Toronto. No action required - will auto-recover."

**Recovery:** Automatic when connectivity restored, region re-added after 3 consecutive successful health checks

**Logging:** Log network_partition_detected with service_id, affected_region, partition_duration_sec, traffic_redistributed_to

**Monitoring:** Alert if any region unreachable for >5 minutes (indicates sustained network issue)

---

#### Scenario 3: Latency-Based Routing Misconfiguration

**Trigger:** User in Australia routed to Toronto (220ms) instead of Singapore (20ms) due to DNS cache

**Expected Behavior:**
- GeoDNS routing uses MaxMind GeoIP2 database (99.8% accuracy)
- DNS TTL set to 60 seconds (minimizes stale routing)
- Fallback: If Singapore unhealthy, route to next-nearest (Frankfurt 180ms)

**User Experience:**
Temporary suboptimal latency during DNS cache TTL (max 60 seconds). Next request correctly routed to Singapore.

**Recovery:** Automatic after DNS TTL expires (60 seconds), GeoDNS database updates nightly for accuracy

**Logging:** Log suboptimal_routing_detected with service_id, client_ip, routed_to_region, optimal_region, latency_ms_actual, latency_ms_optimal

**Monitoring:** Alert if >5% of requests routed to non-optimal region in 1 hour (indicates GeoDNS database issue or regional health check problem)

---

#### Scenario 4: Uneven Traffic Distribution (Weighted Routing)

**Trigger:** User configures `weights: {"tor1": 10, "nyc3": 90}` but Toronto receives 40% of traffic

**Expected Behavior:**
- Weighted routing is statistical (not strict per-request)
- Over 10,000 requests, distribution converges to ±2% of target
- Small request volumes (<100) may show high variance

**User Experience:**
AI assistant shows: "Traffic distribution stabilizing. Current: TOR 42%, NYC 58%. Expected: TOR 10%, NYC 90%. Monitor for 5 minutes as DNS caches expire (TTL: 60 sec)."

**Recovery:** Automatic convergence over time as request volume increases and DNS caches expire

**Logging:** Log traffic_distribution_variance with service_id, configured_weights, actual_distribution, request_sample_size, variance_percent

**Monitoring:** Alert if actual distribution differs from configured weights by >10% over 10,000+ requests (indicates DNS resolver caching issue or routing policy misconfiguration)

---

## 3. Database Managed Services

### 3.1 Supported Databases

**Phase 2 Launch:**
- **PostgreSQL** - Versions: 15, 16, 17 (latest stable)
- **MySQL** - Versions: 8.0, 8.4
- **Redis** - Versions: 7.0, 7.2

**Configuration Tiers:**

**Tier 1: Development (Single Node)**
- Use case: Development, testing, low-traffic apps
- SLA: 99.5% uptime (no replication)
- Backups: Daily automated (7-day retention)
- Sizes: 1GB, 2GB, 4GB RAM

**Tier 2: Production (High Availability)**
- Use case: Production apps, critical data
- SLA: 99.95% uptime (primary + standby replica)
- Backups: Daily automated + point-in-time recovery (30-day retention)
- Sizes: 4GB, 8GB, 16GB, 32GB, 64GB RAM
- Automatic failover: <30 seconds

**Tier 3: Cluster (Redis Only)**
- Use case: High throughput, horizontal scaling
- SLA: 99.99% uptime (multi-master cluster)
- Sizes: 3-node, 6-node, 9-node clusters
- Read replicas: Up to 5 per cluster

---

### 3.2 New MCP Tools (Databases)

#### Tool 25: `provision_database`

Create a managed database instance.

**Parameters:**
- `database_type` (string, required): `postgresql`, `mysql`, `redis`
- `version` (string, required): Database version (e.g., "17" for PostgreSQL, "8.4" for MySQL, "7.2" for Redis)
- `tier` (string, required): `development`, `production`, `cluster` (Redis only)
- `size` (string, required): RAM allocation - `1gb`, `2gb`, `4gb`, `8gb`, `16gb`, `32gb`, `64gb`
- `region` (string, optional): Region code (default: `tor1`)
- `name` (string, required): Database instance name (lowercase, alphanumeric + hyphens, 3-63 chars)
- `initial_databases` (array, optional): Database names to create (PostgreSQL/MySQL only, max 10)
- `node_count` (integer, optional): Number of nodes for cluster tier (Redis only, valid: 3, 6, 9, default: 3)
- `read_replicas` (integer, optional): Number of read replicas for production tier (0-5, default: 0)
- `replica_regions` (array, optional): Region codes for cross-region read replicas (e.g., ["nyc3", "lon1"], requires read_replicas > 0)

**Returns:**
```json
{
  "database_id": "db_postgres_abc123",
  "name": "production-db",
  "database_type": "postgresql",
  "version": "17",
  "tier": "production",
  "size": "8gb",
  "region": "tor1",
  "node_count": null,
  "read_replicas": 0,
  "replica_regions": [],
  "status": "provisioning",
  "connection": {
    "host": "db-abc123.multisphere.net",
    "port": 25060,
    "ssl_required": true,
    "connection_limit": 97
  },
  "credentials": {
    "username": "doadmin",
    "password": "XKHF2jk9#nKJH3jk",
    "default_database": "defaultdb"
  },
  "created_databases": ["app_production", "analytics"],
  "credits_held": 100.0,
  "burn_rate_monthly": 15500.0,
  "estimated_ready": "2025-10-31T10:08:00Z"
}
```

**Credit Model:**
- Hold: 100 credits (provisioning operation)
- Burn: 50 credits (actual provisioning cost)
- Monthly burn rates (see Section 3.3)

**Error Codes:**
- `database_type_invalid` - Unsupported database type
- `version_unsupported` - Version not available
- `tier_invalid` - Invalid tier for database type (e.g., cluster for PostgreSQL)
- `size_invalid` - Size not supported for tier (e.g., 1gb for production tier)
- `name_taken` - Database name already exists in account
- `region_invalid` - Unsupported region
- `node_count_invalid` - Invalid node_count for cluster tier (must be 3, 6, or 9)
- `read_replicas_invalid` - Invalid read_replicas count (must be 0-5)
- `replica_regions_invalid` - replica_regions specified without read_replicas > 0
- `replica_region_unsupported` - One or more replica_regions not available
- `insufficient_credits` - Cannot hold 100 credits

**Streaming:** Yes (SSE events: progress, completed, error)

**SSE Event Payloads:**
```json
// Event: progress
{"type": "progress", "stage": "provisioning_database", "percent": 40, "message": "Creating PostgreSQL 17 instance (8GB, production tier)...", "timestamp": "2025-10-31T10:06:00Z"}

// Event: log
{"type": "log", "level": "info", "message": "Allocated droplet db-abc123 in tor1 (8GB RAM, 160GB SSD)", "timestamp": "2025-10-31T10:06:15Z"}

// Event: progress
{"type": "progress", "stage": "configuring_replication", "percent": 75, "message": "Configuring standby replica for high availability...", "timestamp": "2025-10-31T10:07:00Z"}

// Event: log
{"type": "log", "level": "info", "message": "Standby replica synchronized, replication lag 0.2 seconds", "timestamp": "2025-10-31T10:07:45Z"}

// Event: credit_update
{"type": "credit_update", "credits_held": 100.0, "credits_burned": 35.0, "credits_remaining": 65.0, "timestamp": "2025-10-31T10:07:50Z"}

// Event: completed
{"type": "completed", "database_id": "db_postgres_abc123", "connection": {"host": "db-abc123.multisphere.net", "port": 25060}, "credentials": {"username": "doadmin", "password": "XKHF2jk9#nKJH3jk"}, "credits_burned": 50.0, "duration_sec": 300, "timestamp": "2025-10-31T10:08:00Z"}

// Event: error
{"type": "error", "code": "name_taken", "message": "Database name 'production-db' already exists. Choose a different name.", "credits_released": 100.0, "timestamp": "2025-10-31T10:06:30Z"}
```

**Token Estimate:** ~900 tokens

**Security:**
- Credentials returned once (not retrievable later - store securely)
- SSL/TLS required for all connections
- Private networking only (not exposed to public internet)
- Password auto-generated (bcrypt equivalent strength)

---

#### Tool 26: `scale_database`

Resize database instance (vertical scaling).

**Parameters:**
- `database_id` (string, required): Database instance ID
- `new_size` (string, required): Target RAM size - `2gb`, `4gb`, `8gb`, `16gb`, `32gb`, `64gb`

**Returns:**
```json
{
  "database_id": "db_postgres_abc123",
  "current_size": "8gb",
  "new_size": "16gb",
  "status": "scaling",
  "downtime_expected_sec": 30,
  "burn_rate_monthly_old": 15500.0,
  "burn_rate_monthly_new": 29500.0,
  "burn_change": 14000.0,
  "credits_held": 25.0,
  "estimated_completion": "2025-10-31T10:12:00Z"
}
```

**Credit Model:**
- Hold: 25 credits (scaling operation)
- Burn: 10 credits (actual scaling cost)
- Monthly burn increases/decreases based on new size

**Downtime:**
- **PostgreSQL/MySQL:** 15-30 seconds (failover to replica for production tier, restart for development tier)
- **Redis:** Zero downtime (cluster redistribution for cluster tier, 15-second restart for single-node)

**Error Codes:**
- `database_not_found` - database_id doesn't exist
- `invalid_size` - Size not supported or same as current
- `downgrade_not_allowed` - Cannot downgrade production tier (data safety)
- `insufficient_credits` - Cannot hold 25 credits

**Token Estimate:** ~600 tokens

---

#### Tool 27: `backup_database`

Create an on-demand backup of database.

**Parameters:**
- `database_id` (string, required): Database instance ID
- `backup_name` (string, required): Backup label (alphanumeric + hyphens, max 64 chars)

**Returns:**
```json
{
  "backup_id": "bak_abc123xyz",
  "database_id": "db_postgres_abc123",
  "backup_name": "pre-migration-2025-10-31",
  "status": "creating",
  "size_gb": 0,
  "created_at": "2025-10-31T10:05:00Z",
  "expires_at": "2025-11-30T10:05:00Z",
  "retention_days": 30,
  "credits_held": 15.0,
  "estimated_completion": "2025-10-31T10:07:00Z"
}
```

**Credit Model:**
- Hold: 15 credits (backup operation)
- Burn: 5 credits + storage cost ($0.05/GB/month for backup storage)
- Example: 10GB database → 5 credits + $0.50/month storage

**Backup Retention:**
- **On-demand backups:** 30 days default, max 90 days (user configurable)
- **Automated daily backups:** 7 days (development), 30 days (production)
- **Point-in-time recovery:** Available for production tier (restore to any second in last 7 days)

**Error Codes:**
- `database_not_found` - database_id doesn't exist
- `backup_in_progress` - Another backup already running (max 1 concurrent)
- `backup_limit_reached` - Max 50 backups per database
- `insufficient_credits` - Cannot hold 15 credits

**Token Estimate:** ~500 tokens

---

#### Tool 28: `list_backups`

List all backups for a database instance.

**Parameters:**
- `database_id` (string, required): Database instance ID

**Returns:**
```json
{
  "database_id": "db_postgres_abc123",
  "backups": [
    {
      "backup_id": "bak_abc123xyz",
      "backup_name": "pre-migration-2025-10-31",
      "backup_type": "on_demand",
      "status": "completed",
      "size_gb": 12.5,
      "created_at": "2025-10-31T10:05:00Z",
      "expires_at": "2025-11-30T10:05:00Z",
      "retention_days": 30
    },
    {
      "backup_id": "bak_auto_daily_20251030",
      "backup_name": "automated-daily-2025-10-30",
      "backup_type": "automated",
      "status": "completed",
      "size_gb": 12.3,
      "created_at": "2025-10-30T04:00:00Z",
      "expires_at": "2025-11-29T04:00:00Z",
      "retention_days": 30
    }
  ],
  "point_in_time_available": true,
  "pitr_earliest": "2025-10-24T10:05:00Z",
  "pitr_latest": "2025-10-31T10:05:00Z"
}
```

**Credit Model:** Free (listing operation)

**Error Codes:**
- `database_not_found` - database_id doesn't exist

**Token Estimate:** ~400 tokens

---

#### Tool 29: `restore_backup`

Restore database from backup to a new instance.

**Parameters:**
- `backup_id` (string, optional): Backup ID to restore from (mutually exclusive with timestamp)
- `timestamp` (string, optional): ISO 8601 timestamp for point-in-time recovery (mutually exclusive with backup_id, requires production tier)
- `database_id` (string, required when using timestamp): Source database ID for PITR
- `new_database_name` (string, required): Name for restored instance
- `region` (string, optional): Region for restored instance (default: same as source)
- `size` (string, optional): RAM size for restored instance (default: same as source)

**Returns:**
```json
{
  "database_id": "db_postgres_restored_abc123",
  "name": "production-db-restored",
  "status": "restoring",
  "restore_type": "backup",
  "source_backup_id": "bak_abc123xyz",
  "source_timestamp": null,
  "source_database_id": "db_postgres_abc123",
  "size": "8gb",
  "region": "tor1",
  "credits_held": 150.0,
  "estimated_completion": "2025-10-31T10:15:00Z"
}
```

**Credit Model:**
- Hold: 150 credits (provision new instance + restore operation)
- Burn: 50 credits (provisioning) + 25 credits (restore operation)
- Monthly burn: Same as original database (charged from restoration)

**Restore Behavior:**
- Creates NEW database instance (original remains unchanged)
- Point-in-time restore (production tier): Specify timestamp instead of backup_id
- Cross-region restore supported (restore Toronto backup to London)

**Error Codes:**
- `backup_not_found` - backup_id doesn't exist
- `backup_expired` - Backup past retention period
- `missing_restore_source` - Neither backup_id nor timestamp provided
- `conflicting_restore_source` - Both backup_id and timestamp provided
- `pitr_not_available` - Timestamp specified but source database is not production tier
- `timestamp_out_of_range` - Timestamp outside 7-day PITR window
- `database_not_found` - database_id doesn't exist (when using timestamp)
- `name_taken` - new_database_name already exists
- `insufficient_credits` - Cannot hold 150 credits

**Token Estimate:** ~600 tokens

---

#### Tool 30: `get_database_status`

Get health, performance metrics, and connection info for database.

**Parameters:**
- `database_id` (string, required): Database instance ID

**Returns:**
```json
{
  "database_id": "db_postgres_abc123",
  "name": "production-db",
  "database_type": "postgresql",
  "version": "17",
  "tier": "production",
  "size": "8gb",
  "region": "tor1",
  "status": "running",
  "health": "healthy",
  "connection": {
    "host": "db-abc123.multisphere.net",
    "port": 25060,
    "ssl_required": true,
    "connection_limit": 97,
    "active_connections": 23
  },
  "metrics": {
    "cpu_pct": 34,
    "mem_pct": 58,
    "disk_used_gb": 12.5,
    "disk_total_gb": 160,
    "disk_pct": 7.8,
    "queries_per_sec": 342,
    "cache_hit_rate_pct": 98.5,
    "replication_lag_ms": 2
  },
  "high_availability": {
    "enabled": true,
    "primary_node": "db-abc123-primary",
    "standby_node": "db-abc123-standby",
    "last_failover": null
  },
  "backups": {
    "last_backup": "2025-10-31T04:00:00Z",
    "next_backup": "2025-11-01T04:00:00Z",
    "total_backups": 7,
    "point_in_time_available": true
  },
  "burn_rate_monthly": 15500.0,
  "uptime_pct_30d": 99.97
}
```

**Credit Model:** Free (status check)

**Error Codes:**
- `database_not_found` - database_id doesn't exist

**Token Estimate:** ~700 tokens

---

#### Tool 31: `deprovision_database`

Delete database instance and all backups (destructive, irreversible).

**Parameters:**
- `database_id` (string, required): Database instance ID
- `confirmation_name` (string, required): Must exactly match database name (safety check)

**Returns:**
```json
{
  "database_id": "db_postgres_abc123",
  "name": "production-db",
  "status": "deprovisioning",
  "backups_deleted": 7,
  "credits_released": 22.5,
  "final_bill_credits": 2.5
}
```

**Credit Model:**
- Release: Prorated monthly burn credits (unused days)
- Charge: Prorated usage for current month
- Example: 15 days into month → release 50% of held monthly credits, charge 50% of monthly burn

**Backup Handling:**
- All automated backups deleted immediately
- On-demand backups deleted after 7-day grace period (safety buffer)

**Error Codes:**
- `database_not_found` - database_id doesn't exist
- `confirmation_mismatch` - confirmation_name doesn't match database name
- `database_in_use` - Active connections prevent deletion (drain first)

**Token Estimate:** ~400 tokens

---

### 3.3 Database Credit Model

**Monthly Burn Rates (Development Tier - Single Node):**
| Size | PostgreSQL | MySQL | Redis | Storage |
|------|------------|-------|-------|---------|
| 1GB  | $15/mo     | $15/mo | $10/mo | 10GB included |
| 2GB  | $25/mo     | $25/mo | $18/mo | 25GB included |
| 4GB  | $45/mo     | $45/mo | $30/mo | 40GB included |

**Monthly Burn Rates (Production Tier - High Availability):**
| Size | PostgreSQL | MySQL | Redis | Storage |
|------|------------|-------|-------|---------|
| 4GB  | $85/mo     | $85/mo | $60/mo  | 80GB included |
| 8GB  | $155/mo    | $155/mo | $110/mo | 160GB included |
| 16GB | $295/mo    | $295/mo | $210/mo | 320GB included |
| 32GB | $565/mo    | $565/mo | $410/mo | 640GB included |
| 64GB | $1,095/mo  | $1,095/mo | $790/mo | 1,280GB included |

**Monthly Burn Rates (Cluster Tier - Redis Only):**
| Nodes | Size per Node | Monthly Burn | Storage |
|-------|---------------|--------------|---------|
| 3     | 4GB           | $210/mo      | 120GB total |
| 3     | 8GB           | $390/mo      | 240GB total |
| 6     | 4GB           | $420/mo      | 240GB total |
| 6     | 8GB           | $780/mo      | 480GB total |
| 9     | 4GB           | $630/mo      | 360GB total |

**Additional Costs:**
- **Extra storage:** $0.10/GB/month beyond included (e.g., 4GB database needs 60GB → +$2/month for extra 20GB)
- **Backup storage:** $0.05/GB/month (automated backups included, on-demand backups charged)
- **Point-in-time recovery:** Included in production tier (no extra charge)
- **Cross-region replication:** +100% monthly burn (e.g., Toronto primary + London replica = 2× base cost)

**Provisioning Costs (one-time):**
- Development tier: 50 credits
- Production tier: 75 credits
- Cluster tier: 100 credits

---

### 3.4 Database Workflows

#### Workflow 1: Provision PostgreSQL for Production App

**User:** "Set up a production PostgreSQL database for my app"

**Steps:**
1. `provision_database` → `type: "postgresql"`, `version: "17"`, `tier: "production"`, `size: "8gb"`, `name: "app-prod-db"`
2. AI assistant receives credentials (username, password, host, port)
3. Configure application environment variables: `DATABASE_URL=postgresql://doadmin:password@db-abc123.multisphere.net:25060/defaultdb?sslmode=require`

**Result:**
- High-availability PostgreSQL (primary + standby replica)
- 99.95% uptime SLA
- 160GB storage included
- Automated daily backups (30-day retention)
- Point-in-time recovery available
- Monthly burn: 15,500 credits/month (equivalent to $155/month)

---

#### Workflow 2: Scale Database During Traffic Spike

**User:** "Database is slow, need more resources"

**Steps:**
1. `get_database_status` → Confirm high resource usage (CPU 85%, memory 92%)
2. `scale_database` → `database_id`, `new_size: "16gb"`
3. **30-second downtime** (failover to standby replica)
4. Database resized, monthly burn: 15,500 → 29,500 credits/month (equivalent to $155 → $295/month)

**Result:**
- Vertical scaling completed in 2 minutes
- Minimal downtime (30 seconds)
- Double RAM and storage capacity
- Application automatically reconnects

---

#### Workflow 3: Disaster Recovery (Restore from Backup)

**User:** "Production database corrupted, restore from last night's backup"

**Steps:**
1. `list_backups` → Identify backup from last night: `bak_xyz_2025-10-30`
2. `restore_backup` → `backup_id: "bak_xyz_2025-10-30"`, `new_database_name: "app-prod-db-restored"`
3. **Verify restored database** (query data, run tests)
4. Update application environment variables to new connection string
5. `deprovision_database` → Delete corrupted original database

**Result:**
- Database restored to last night's state (data loss: 12 hours)
- New instance provisioned in 8 minutes
- Original database preserved during verification
- Total cost: 75 credits (restore) + prorated monthly burn

---

#### Workflow 4: Point-in-Time Recovery (Production Tier)

**User:** "Accidental DELETE query at 2:30 PM, restore to 2:29 PM"

**Steps:**
1. `restore_backup` → `database_id`, `timestamp: "2025-10-31T14:29:00Z"`, `new_database_name: "app-prod-db-pitr"`
2. Database restored to exact state at 2:29 PM
3. Query restored database to verify data intact
4. Swap connection strings, deprovision corrupted database

**Result:**
- Data loss: 0 seconds (restored to 1 minute before incident)
- Recovery time: 10 minutes
- No backup required (continuous replication logs)

---

### 3.5 Database Error Scenarios

#### Scenario 1: Connection Limit Exceeded

**Trigger:** Application opens 100 connections, PostgreSQL 8GB instance limit is 97 connections

**Expected Behavior:**
- Connection attempts fail with: `FATAL: too many connections for role "doadmin"`
- Existing connections remain stable
- Metric `active_connections` shows 97/97

**User Experience:**
AI assistant shows: "Database connection limit reached (97/97). Options: (1) Scale to 16GB (195 connection limit, $295/month), (2) Implement connection pooling (PgBouncer), or (3) Close idle connections. Current: $155/month."

**Recovery:** Scale database or optimize application connection management

**Logging:** Log connection_limit_exceeded with database_id, active_connections, max_connections, rejected_connection_attempts, database_tier, database_size

**Monitoring:** Alert if connection usage >90% for >10 minutes (indicates application leak or insufficient capacity)

---

#### Scenario 2: Disk Full (Storage Exceeded)

**Trigger:** Database grows to 161GB, exceeding 160GB included storage on 8GB instance

**Expected Behavior:**
- Write operations blocked, read operations continue
- Alert triggered: "Database storage 99% full"
- Auto-scaling: System automatically provisions +10GB (+$1/month)

**User Experience:**
AI assistant shows: "Database storage exceeded included 160GB. Auto-provisioned +10GB temporary storage (+$1/month). Recommend: (1) Scale to 16GB instance (320GB included, $295/month), (2) Archive old data, or (3) Enable compression."

**Recovery:** Automatic (temporary storage added), manual optimization recommended

**Logging:** Log storage_exceeded with database_id, storage_used_gb, storage_included_gb, storage_auto_added_gb, additional_cost_monthly

**Monitoring:** Alert if storage usage >80% (warning) or >95% (critical), alert if auto-scaling triggered >3 times in 7 days (indicates persistent growth requiring manual intervention)

---

#### Scenario 3: Replication Lag (High Availability)

**Trigger:** Standby replica lags 15 seconds behind primary due to heavy write load

**Expected Behavior:**
- Replication continues (eventual consistency)
- If lag exceeds 60 seconds: Alert triggered
- If lag exceeds 5 minutes: Standby marked unhealthy (failover disabled)

**User Experience:**
AI assistant shows: "Database replica lagging 15 seconds (normal under heavy write load). Replication healthy. If persistent, consider scaling to 16GB for better I/O throughput."

**Recovery:** Typically self-healing as write load decreases. Scaling improves replication performance.

**Logging:** Log replication_lag_detected with database_id, lag_seconds, write_rate_per_sec, replica_status, failover_enabled

**Monitoring:** Alert if replication lag >60 seconds (warning) or >300 seconds (critical, failover disabled), alert if lag >10 seconds persists for >30 minutes (indicates sustained I/O bottleneck)

---

#### Scenario 4: Automatic Failover (Primary Node Failure)

**Trigger:** Primary PostgreSQL node crashes due to hardware failure

**Expected Behavior:**
- Health checks detect failure within 30 seconds
- Automatic failover to standby replica
- Standby promoted to primary (30-second promotion time)
- DNS updated to point to new primary
- New standby provisioned from promoted primary

**User Experience:**
AI assistant shows: "Database failover completed. Primary node failed (hardware), standby promoted to primary in 28 seconds. Application reconnected automatically. New standby provisioning (5 minutes). Total downtime: 28 seconds."

**Recovery:** Automatic, full high-availability restored in 5 minutes

**Logging:** Log automatic_failover_triggered with database_id, failure_reason, detection_time_sec, failover_duration_sec, old_primary_node_id, new_primary_node_id, dns_updated

**Monitoring:** Alert on every failover event (critical incident), alert if failover duration >60 seconds (exceeds SLA target), alert if >1 failover per 7 days (indicates hardware instability requiring investigation)

---

#### Scenario 5: Backup Corruption Detected During Restore

**Trigger:** User attempts to restore from backup `bak_abc123xyz` but backup file is corrupted (checksum mismatch detected)

**Expected Behavior:**
- Restore operation begins, backup file downloaded from object storage
- Checksum verification fails (stored checksum doesn't match downloaded file)
- Restore aborted immediately (before provisioning new database instance)
- Error logged with backup_id, corruption type (checksum_mismatch), and timestamp
- User notified with list of alternative backups

**User Experience:**
AI assistant shows: "Backup restore failed: backup file corrupted (checksum mismatch). Backup ID: bak_abc123xyz created on 2025-10-30. Available alternatives: bak_auto_daily_20251029 (1 day older), bak_auto_daily_20251028 (2 days older). Recommend: Use most recent uncorrupted backup or contact support if all recent backups are affected. No charges incurred."

**Recovery:**
- User selects alternative backup from list_backups
- If all backups corrupted: Use point-in-time recovery (production tier) to restore from transaction logs
- System automatically retries failed backup (backup_id marked as corrupted in metadata, excluded from future restore attempts)

**Logging:** Log backup_corruption_detected with backup_id, corruption_type, file_size_expected, file_size_actual, checksum_expected, checksum_actual

**Monitoring:** Alert if >1% of backups fail checksum verification over 24 hours (indicates storage system issue)

---

## 4. Combined Multi-Region + Database Architecture

### 4.1 Reference Architecture: Global E-Commerce Platform

**Requirements:**
- Serve US and Europe customers (<50ms latency)
- High availability (99.95% uptime)
- PostgreSQL database with read replicas for analytics

**Architecture:**

**Application Tier:**
- Region 1: New York (primary, 60% traffic)
- Region 2: London (secondary, 40% traffic)
- Routing policy: `latency_based`

**Database Tier:**
- Primary: PostgreSQL 16GB in New York (write master)
- Read replica: PostgreSQL 16GB in London (analytics queries)
- Replication lag: <2 seconds (cross-region)

**Cost Breakdown:**
- App hosting: 2 regions × 2,400 credits/month = 4,800 credits/month (equivalent to $48/month)
- Database primary: 29,500 credits/month (NYC, equivalent to $295/month)
- Database replica: 29,500 credits/month (LON, equivalent to $295/month)
- Cross-region data transfer: ~1,000 credits/month (1GB/day replication, equivalent to ~$10/month)
- **Total: 64,800 credits/month (equivalent to $648/month)**

**Performance:**
- US users: 20ms latency (NYC app + NYC database)
- EU users: 25ms latency (LON app + LON read replica)
- Write latency: EU users see 85ms for writes (LON app → NYC primary)
- Read latency: <25ms globally (local read replicas)

---

### 4.2 Database Placement Strategies

**Strategy 1: Single Database with Multi-Region Apps**
- Use case: Small dataset (<10GB), low write volume
- Architecture: Apps in 3 regions, database in 1 region
- Tradeoff: Higher database latency for distant regions, lower cost
- Cost: 3× app burn + 1× database burn

**Strategy 2: Primary + Read Replicas**
- Use case: Read-heavy workload (90% reads, 10% writes)
- Architecture: Primary database in 1 region, read replicas in others
- Tradeoff: Eventual consistency (2-5 second replication lag), optimized read latency
- Cost: 3× app burn + 3× database burn (primary + 2 replicas)

**Strategy 3: Multi-Master (Not Phase 2)**
- Use case: Write-heavy workload across regions
- Architecture: Database writes accepted in multiple regions with conflict resolution
- Tradeoff: Complex conflict resolution, highest consistency guarantees
- Status: Future consideration (post-Phase 2)

---

## 5. Observability

### 5.1 New Metrics (Multi-Region)

**Region Health Metrics:**
- `region_health_status` (gauge, labels: service_id, region) - 0=unhealthy, 1=degraded, 2=healthy
- `region_traffic_percentage` (gauge, labels: service_id, region) - Actual traffic distribution (0-100)
- `region_response_time_p95` (histogram, labels: service_id, region) - 95th percentile response time
- `cross_region_data_transfer_gb` (counter, labels: source_region, dest_region) - Data transfer volume

**Deployment Metrics:**
- `multi_region_deployment_duration_sec` (histogram, labels: region) - Time to deploy to additional region
- `region_failover_count` (counter, labels: service_id, from_region, to_region) - Automatic failover events

### 5.2 New Metrics (Database)

**Database Health Metrics:**
- `database_connection_count` (gauge, labels: database_id) - Active connections
- `database_connection_limit` (gauge, labels: database_id) - Maximum connections allowed
- `database_cpu_pct` (gauge, labels: database_id) - CPU utilization
- `database_mem_pct` (gauge, labels: database_id) - Memory utilization
- `database_disk_used_gb` (gauge, labels: database_id) - Disk space used
- `database_disk_total_gb` (gauge, labels: database_id) - Total disk space available (included storage)
- `database_queries_per_sec` (gauge, labels: database_id) - Query throughput

**Database Replication Metrics:**
- `database_replication_lag_ms` (gauge, labels: database_id, replica_id) - Standby replica lag
- `database_replication_status` (gauge, labels: database_id, replica_id) - 0=broken, 1=lagging, 2=healthy

**Database Backup Metrics:**
- `database_backup_count` (gauge, labels: database_id) - Total backups stored
- `database_backup_size_gb` (gauge, labels: database_id) - Total backup storage used
- `database_last_backup_age_hours` (gauge, labels: database_id) - Hours since last backup
- `database_backup_failures` (counter, labels: database_id, failure_reason) - Failed backup attempts

### 5.3 New Alerts

**Alert 11: Region Unhealthy**
- Condition: `region_health_status{region=X} == 0` for 2 minutes
- Severity: HIGH
- Action: Remove region from traffic rotation, notify on-call
- Rationale: Unhealthy region causes customer errors

**Alert 12: High Cross-Region Latency**
- Condition: `region_response_time_p95{region=X} > 200ms` for 10 minutes
- Severity: MEDIUM
- Action: Check for network issues, consider routing changes
- Rationale: Latency spike indicates misrouting or network degradation

**Alert 13: Database Connection Limit Warning**
- Condition: `database_connection_count / database_connection_limit > 0.8` for 5 minutes
- Severity: MEDIUM
- Action: Alert customer to scale database or optimize connections
- Rationale: Prevents hard connection limit failures

**Alert 14: Database Replication Lag High**
- Condition: `database_replication_lag_ms > 60000` (1 minute) for 5 minutes
- Severity: HIGH
- Action: Check primary load, consider scaling, disable automatic failover if lag >5 minutes
- Rationale: High lag risks data loss on failover

**Alert 15: Database Backup Failed**
- Condition: `database_backup_failures > 0`
- Severity: CRITICAL
- Action: Immediate investigation, retry backup, notify customer
- Rationale: Failed backups risk data loss in disaster scenarios

**Alert 16: Database Storage >90% Full**
- Condition: `database_disk_used_gb / database_disk_total_gb > 0.9`
- Severity: HIGH
- Action: Auto-provision temporary storage, notify customer to scale or archive
- Rationale: Full disk causes write failures and application errors

---

## 6. Testing Requirements

### 6.1 Multi-Region Tests

**Test 1: Multi-Region Deployment**
- Deploy app to Toronto → Deploy to NYC → Deploy to London
- Verify: All regions running, isolated infrastructure, identical code versions
- Success criteria: 3 regions healthy, response time <100ms per region

**Test 2: Latency-Based Routing**
- Configure `latency_based` routing with 3 regions
- Simulate requests from 10 global locations (GeoIP spoofing)
- Verify: 90% of requests routed to nearest region

**Test 3: Automatic Failover**
- Configure failover policy with NYC primary, Toronto standby
- Simulate NYC region failure (kill health check endpoint)
- Verify: Traffic switches to Toronto within 60 seconds, zero dropped requests

**Test 4: Weighted Canary Deployment**
- Deploy new version to Toronto (10% traffic), NYC has old version (90% traffic)
- Send 10,000 requests, measure actual distribution
- Verify: Traffic distribution within ±5% of target (Toronto 10%, NYC 90%)

**Test 5: Cross-Region Data Transfer Billing**
- Deploy Toronto + London regions
- Trigger 5GB cross-region transfer (database replication simulation)
- Verify: Credit burn includes data transfer charge ($0.10 for 5GB)

### 6.2 Database Tests

**Test 6: PostgreSQL Provisioning**
- Provision development tier (4GB) PostgreSQL 17
- Verify: Database accessible, credentials work, included storage available
- Success criteria: Connection successful, query execution <10ms, 40GB storage

**Test 7: Database Scaling**
- Provision 8GB production PostgreSQL → Scale to 16GB
- Verify: Downtime <30 seconds, connections restored, new connection limit (195)
- Measure: Actual downtime, burn rate increase ($155 → $295)

**Test 8: Automated Backup**
- Provision database → Wait for automated backup (triggers at 4 AM daily)
- Verify: Backup created, size accurate, retention policy applied (30 days)
- Success criteria: Backup listed in backups array, restorable

**Test 9: Point-in-Time Recovery**
- Provision production database → Insert 1000 rows → Wait 5 minutes → Delete 500 rows
- Restore to timestamp before deletion
- Verify: Restored database has all 1000 rows, original database unchanged

**Test 10: Connection Limit Handling**
- Provision 4GB PostgreSQL (97 connection limit)
- Open 100 concurrent connections
- Verify: Connections 1-97 succeed, connections 98-100 fail with clear error message

**Test 11: Disk Full Auto-Scaling**
- Provision 4GB database (40GB included storage)
- Fill database to 39.5GB
- Verify: Auto-provisioning triggers at 90% (36GB), temporary storage added

**Test 12: High Availability Failover**
- Provision production tier PostgreSQL (primary + standby)
- Simulate primary node crash (API call to trigger failover)
- Verify: Standby promoted within 30 seconds, write operations resume, zero data loss

---

## 7. Implementation Phases

### 7.1 Phase 2A: Multi-Region (Months 3-4)

**Week 1-2: Infrastructure**
- DigitalOcean multi-region account setup
- GeoDNS routing configuration (Route53 or Cloudflare)
- Cross-region networking (VPC peering)

**Week 3-4: Core Implementation**
- Implement tools 20-24 (deploy_to_region, list_regions, configure_traffic_routing, get_region_status, remove_region_deployment)
- Deploy control plane in Toronto (centralized orchestration)
- Health check system with 30-second intervals

**Week 5-6: Routing & Failover**
- Implement DNS-based routing policies (round_robin, latency_based, weighted, failover)
- Automatic failover logic (health check → DNS update)
- Traffic distribution monitoring

**Week 7-8: Testing & Docs**
- Execute multi-region tests (Tests 1-5)
- Documentation: Migration guide, architecture diagrams
- Beta testing with 5 pilot customers

### 7.2 Phase 2B: Database Services (Months 5-6)

**Week 1-2: Database Infrastructure**
- DigitalOcean Managed Databases setup (PostgreSQL, MySQL, Redis)
- Private networking configuration (VPC-only access)
- Backup storage (S3-compatible object storage)

**Week 3-4: Core Implementation**
- Implement tools 25-30 (provision_database, scale_database, backup_database, restore_backup, get_database_status, deprovision_database)
- Credential management system (encryption at rest, secure delivery)
- Connection pooling recommendations

**Week 5-6: Backup & Recovery**
- Automated daily backup scheduling
- Point-in-time recovery implementation (transaction log archival)
- Cross-region backup replication (disaster recovery)

**Week 7-8: Testing & Docs**
- Execute database tests (Tests 6-12)
- Documentation: Database selection guide, connection examples
- Beta testing with 5 pilot customers

---

## 8. Migration Path from Phase 1

### 8.1 Backward Compatibility

**Guaranteed Compatibility:**
- All Phase 1 tools (1-19) work identically in Phase 2
- Single-region services default to Toronto (no behavior change)
- Existing services continue running without migration

**Opt-In Migration:**
- Customers choose when to enable multi-region or databases
- No forced migrations or breaking changes
- Phase 1 pricing remains stable

### 8.2 Customer Migration Workflows

**Workflow 1: Add Second Region to Existing Service**

**Starting state:** Single-region app in Toronto (Phase 1 service)

**Steps:**
1. `deploy_to_region` → `service_id: "svc_existing"`, `region: "nyc3"`
2. `configure_traffic_routing` → `policy: "latency_based"`
3. Monitor for 24 hours
4. Optionally remove Toronto if fully migrating to NYC

**Result:** Seamless upgrade from single-region to multi-region, zero downtime

---

**Workflow 2: Migrate from Container Database to Managed Database**

**Starting state:** PostgreSQL running in Docker container on Phase 1 service

**Steps:**
1. `provision_database` → Production tier PostgreSQL
2. Export data from container: `pg_dump > backup.sql`
3. Import to managed database: `psql < backup.sql`
4. Update application environment variables
5. Test application with new database
6. Deprovision old service

**Result:** Upgraded to managed database with HA, backups, zero-ops maintenance

---

## 9. Pricing Summary

### 9.1 Multi-Region Costs

**Application Hosting (per region):**
- Same as Phase 1 single-region pricing
- Example: 2 CPU / 4GB = $12/month per region
- 3 regions = $36/month total

**Data Transfer:**
- Intra-region: Free
- Cross-region (same continent): $0.01/GB
- Cross-region (different continents): $0.02/GB
- Internet egress: Included up to 1TB/month

**Deployment Operations:**
- Deploy to additional region: 50 credit hold → 25 credit burn (one-time)

### 9.2 Database Costs

**Development Tier (Single Node):**
- PostgreSQL/MySQL: $15-$45/month (1GB-4GB)
- Redis: $10-$30/month (1GB-4GB)

**Production Tier (High Availability):**
- PostgreSQL/MySQL: $85-$1,095/month (4GB-64GB)
- Redis: $60-$790/month (4GB-64GB)

**Cluster Tier (Redis Only):**
- 3-9 nodes: $210-$630/month

**Add-Ons:**
- Extra storage: $0.10/GB/month
- Backup storage: $0.05/GB/month
- Cross-region replication: +100% base cost

---

## 10. Spec Completeness Checklist

**Before moving to Plan phase:**

- [x] Clear user value proposition stated
- [x] Success criteria defined and measurable
- [x] All functional requirements enumerated (12 new tools)
- [x] All constraints documented (provider limits, SLAs, storage)
- [x] Error scenarios identified (9 scenarios across multi-region + databases)
- [x] Security requirements specified (SSL, private networking, credential encryption)
- [x] Performance requirements quantified (latency targets, failover times, replication lag)
- [ ] Token efficiency requirements stated (needs estimation)
- [x] Testing requirements defined (12 tests across both features)
- [x] Observability requirements defined (19 metrics, 6 alerts)
- [ ] Reviewed for Constitution compliance (needs governance review)
- [x] Logic checked (internally consistent)
- [ ] Peer reviewed (if team > 1)

---

## 11. Approval

**Status:** Ready for Plan Phase (Codex Ultrareview: 9/10 Quality Rating)

**Approvals:**
- [x] CTO (Simon Carr) - Approved for Plan Phase 2025-10-31
- [ ] CEO (if business impact - pricing model changes)
- [ ] Security Review (database credential handling, cross-region networking)

**Approved Date:** [Pending]
**Next Review:** [Pending]

---

## Changelog

**v2.1.0 (2025-10-31):**
- **CODEX REVIEW COMPLETE:** All 9 issues resolved (4 critical + 5 follow-ups), 9/10 quality rating
- Added comprehensive validation rules to configure_traffic_routing (weighted and failover policies)
- Added database_disk_total_gb metric (19 metrics total, was 13)
- Added Scenario 5: Backup Corruption detection and recovery
- Added SSE event payload schemas for deploy_to_region and provision_database
- Updated spec status: "Draft" → "Ready for Plan Phase"
- **Status:** Implementation-ready, matches Phase 1 v1.3.0 quality standards

**v2.0.1 (2025-10-31):**
- **CRITICAL FIXES:** Resolved 4 blocking issues from Codex ultrareview
- Fixed credit model contradictions (1 credit = $0.01 CAD throughout all examples)
- Added clustering/replication parameters to provision_database (node_count, read_replicas, replica_regions)
- Added timestamp parameter to restore_backup for point-in-time recovery (PITR)
- Added Tool 28: list_backups (enumerate backups with PITR window)
- Converted all error codes to lowercase (Phase 1 consistency)
- Renumbered tools: restore_backup (28→29), get_database_status (29→30), deprovision_database (30→31)

**v2.0.0 (2025-10-31):**
- Initial Phase 2 specification
- Added 12 new MCP tools (5 multi-region, 7 database)
- Defined 5 geographic regions with latency-based routing
- Specified 3 database tiers (development, production, cluster)
- Added initial metrics and alerts for observability
- Documented 12 integration tests
- Defined credit models for regions and databases
- Created migration paths from Phase 1
