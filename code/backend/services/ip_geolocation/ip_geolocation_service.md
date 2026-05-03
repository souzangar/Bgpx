# IP Geolocation Service Plan (`ip_geolocation_service.py`)

This document defines the design and implementation plan for the backend IP geolocation service layer.

Location target:
- Service doc: `code/backend/services/ip_geolocation_service.md`
- Current service module: `code/backend/services/ip_geolocation_service.py`
- Planned modular service packages:
  - `code/backend/services/ip_geolocation/ip_geolocation_service.py`
  - `code/backend/services/ip_geolocation/ip_geolocation_data_refresher.py`
  - `code/backend/services/background_task_runner/background_task_runner.py`

Related service docs:
- `code/backend/services/background_task_runner_service.md` (generic runner lifecycle/scheduling contract)

---

## 1) Purpose

The `ip_geolocation_service.py` module is responsible for:
- Loading IP geolocation dataset from infra adapters
- Maintaining in-memory lookup state
- Exposing lookup and status use-cases for upper layers
- Handling progressive loading and readiness behavior

It must **not** directly perform low-level I/O. All source access goes through infra adapters.

---

## 2) Layer Position

Expected flow:

`api -> apps -> services -> infra/models`

- API layer exposes routes
- App layer orchestrates calls
- Service layer owns business/runtime behavior
- Infra reads/parses source payloads
- Models define shared contracts

### 2.1 Planned service package boundaries (for reusable background updates)

To support future features that need the same auto-refresh behavior, split responsibilities into:

```text
code/backend/services/
  ip_geolocation/
    ip_geolocation_service.py
    ip_geolocation_data_refresher.py

  background_task_runner/
    background_task_runner.py

code/backend/models/
  background_task_runner/
    background_task_runner_models.py
    __init__.py
```

Boundary rule:
- Keep `background_task_runner` generic (looping, cancellation, scheduling interval, error boundaries).
- Keep `ip_geolocation_data_refresher` domain-specific (fingerprint check, reload decision, snapshot swap, geo-specific status).
- Do **not** place domain refreshers under `background_task_runner/tasks/...`.

### 2.2 Runtime orchestration contract (`main.py` lifecycle)

To make component ownership and startup flow explicit, use this runtime wiring contract:

1. Construct `ip_geolocation_service` (query/read facade + active snapshot holder).
2. Construct `ip_geolocation_data_refresher` (source-change detection + snapshot builder/publisher).
3. Register refresher job in `background_task_runner`.
4. Start `background_task_runner` during app startup (`main.py` lifespan startup).
5. Stop/unregister runner tasks during app shutdown (`main.py` lifespan shutdown).

Resulting behavior:
- Refresh/build work stays in background and does not block API routing.
- API lookup path depends only on `ip_geolocation_service`.

### 2.3 Service ↔ refresher integration contract

The geolocation service and refresher should communicate via an explicit publish contract.

`ip_geolocation_data_refresher` responsibilities:
- Poll file metadata trigger (`inode + mtime_ns`) and decide when to reload.
- Build and validate a **new immutable snapshot** off the read path.
- On success, publish snapshot to service through a single swap/publish entrypoint.
- On failure, report status/metrics and keep existing active snapshot untouched.

`ip_geolocation_service` responsibilities:
- Expose lookup/status APIs to app/API layers.
- Own active snapshot reference used by all lookups.
- Perform atomic snapshot swap on publish.
- Never parse source file directly and never run polling logic.

Hard boundary rule:
- API/app layer must call only `ip_geolocation_service` for lookup and status.
- API/app layer must not call `ip_geolocation_data_refresher` directly.

### 2.4 Publish-state contract (how service knows `loading` vs `ready`)

`ip_geolocation_service` is the **single owner** of read-facing runtime state used by lookup/status APIs.
`ip_geolocation_data_refresher` is the **producer** that publishes updates through service-owned methods.

Recommended state ownership inside `ip_geolocation_service`:
- `service_state`: `loading | ready | failed`
- `active_snapshot` (current immutable lookup snapshot)
- `last_loaded_at` (timestamp of last successful publish)
- optional refresh status metadata (`last_refresh_error`, counters)

Recommended publication flow:
1. Service starts in `loading` with empty/initial snapshot.
2. Refresher builds+validates a new snapshot off-path.
3. Refresher calls one service publish entrypoint (example: `publish_snapshot(new_snapshot, metadata)`).
4. Service atomically swaps snapshot and updates runtime state.

Behavioral rules:
- On first successful publish: set `service_state = ready`.
- On later refresh failure: keep old `active_snapshot` and record refresh error metadata.
- `failed` should represent unrecoverable service-level failure (not ordinary transient refresh errors).

This keeps lookup semantics deterministic while preserving service/refresher boundary separation.

---

## 3) Data Source and Storage

Provider file location (fixed hardcoded path):
- `code/backend/data/ip_geolocation/ipinfo-geo.json`

For this provider-specific adapter (`ip_geolocation_ipinfo_json_file_reader_adapter.py`),
the dataset filename and path are fixed and always read from the hardcoded location above.

### 3.1 Reviewed provider file characteristics (`ipinfo-geo.json`)

Based on the current file review, the dataset has these characteristics:

- File format is **NDJSON / JSON Lines** (one JSON object per line), **not** a single JSON array/object.
- Current snapshot size is 626 records (line-delimited entries).
- Schema is consistent across all reviewed lines with 8 keys:
  - `network`
  - `country`
  - `country_code`
  - `continent`
  - `continent_code`
  - `asn`
  - `as_name`
  - `as_domain`
- ASN-related fields can be null:
  - `asn` ~22.2%
  - `as_name` ~22.2%
  - `as_domain` ~24.0%
- `network` is mostly CIDR (e.g. `1.0.0.0/24`) but also includes host-only IP values without prefix (e.g. `1.7.168.172`).

### 3.2 Parser and normalization contract

Infra parser/service ingestion should explicitly handle the reviewed format:

1. Read source file line-by-line (streaming-friendly for larger future datasets).
2. Parse each non-empty line as a standalone JSON object.
3. Validate `network` value:
   - if CIDR, parse as network range,
   - if host IP without CIDR, normalize to `/32` for indexing consistency.
4. Keep nullable ASN metadata as optional fields (do not fail record when `asn`/`as_name`/`as_domain` are null).
5. Track and expose malformed-line counts for observability.

---

## 4) Naming Rules (Domain + Usage)

Follow explicit naming convention:

Infra modules:
- `ip_geolocation_ipinfo_json_file_reader_adapter.py`
- `ip_geolocation_ipinfo_json_file_reader_parser.py`

Service modules:
- `ip_geolocation/ip_geolocation_service.py`
- `ip_geolocation/ip_geolocation_data_refresher.py`
- `background_task_runner/background_task_runner.py`

Method naming examples:
- `initialize_ip_geolocation_dataset()`
- `lookup_ip_geolocation(ip: str)`
- `get_ip_geolocation_load_status()`
- `reload_ip_geolocation_dataset()`
- `start_ip_geolocation_source_watch()`
- `stop_ip_geolocation_source_watch()`

### 4.1 DTO ownership and placement rule

All DTOs/models related to IP geolocation service contracts must be placed under:

- `code/backend/models/ip_geolocation/`

Expected package layout:

```text
code/backend/models/ip_geolocation/
  __init__.py
  ip_geolocation_models.py
```

Boundary and import rule:
- Service/app/api layers must import IP geolocation DTOs from `models/ip_geolocation`.
- Do not define IP geolocation DTOs inside `services/`, `apps/`, or `api/` modules.
- Keep request/response contract types centralized in `models` package to follow general project design guidelines.

---

## 5) Service Responsibilities

`ip_geolocation_service.py` should implement:

1. Dataset lifecycle management
   - loading -> ready (or failed)

2. In-memory lookup store
   - keep normalized records/index in RAM
   - keep canonical network representation (CIDR/network object)

3. Progressive loading support
   - allow API availability during load
   - return explicit state when lookup cannot be resolved yet

4. Lookup contract stability
   - avoid ambiguous null responses
   - include resolution state metadata

5. Observability of loading state
   - progress percent
   - record counts
   - malformed/ignored line counts
   - last loaded timestamp

6. Data-quality guardrails
   - validate required geo keys per record
   - normalize host-IP networks to `/32`
   - gracefully skip or fail-fast based on configured strictness

7. Source-change-driven cache refresh
   - detect source file updates and refresh in-memory dataset without process restart
   - use lightweight file fingerprint trigger (`inode` + `mtime_ns`)
   - rebuild fresh cache snapshot and atomically swap only on successful parse
   - keep old cache active if reload fails

---

## 6) Runtime State Model

Recommended service states:
- `loading`
- `ready`
- `failed`

Recommended successful lookup resolution states:
- `found`
- `initializing_db`
- `not_found`

Failure behavior:
- Use the platform-standard `status = failure` service envelope.
- Do not overload lookup `resolution` with failure semantics.

### 6.1 Two-axis response model (important)

To keep responses unambiguous, treat runtime and lookup outcomes as **separate dimensions**:

1. **API/service envelope status** (`status`)
   - Purpose: indicates whether request execution succeeded at platform/service level.
   - Typical values: `success` | `failure`.

2. **Lookup resolution state** (`resolution_state`)
   - Purpose: indicates business/domain outcome of geolocation lookup.
   - Allowed values (only on successful envelope):
     - `found`
     - `initializing_db`
     - `not_found`

3. **Runtime service state** (`service_state`)
   - Internal/current lifecycle state of geolocation service:
     - `loading`
     - `ready`
     - `failed`

Rule of thumb:
- `status` answers: **"Could the service process this request?"**
- `resolution_state` answers: **"What was the lookup result (if request processing succeeded)?"**

### 6.2 Runtime → API status mapping

| Runtime `service_state` | Envelope `status` | Allowed `resolution_state` | Meaning |
|---|---|---|---|
| `loading` | `success` | `found` | IP matched a range that has already been loaded. |
| `loading` | `success` | `initializing_db` | Load is still in progress; cannot conclude not-found yet. |
| `ready` | `success` | `found` | Full dataset available; lookup matched. |
| `ready` | `success` | `not_found` | Full dataset available; lookup did not match. |
| `failed` | `failure` | _N/A_ | Service-level failure; return standard failure envelope. |

Important constraint:
- Never return lookup-failure-style values inside `resolution_state` (e.g. `failed`, `error`, `timeout`).
- Those belong to envelope-level failure handling (`status = failure`).

### 6.3 Relation to HTTP response status

`status` in payload and HTTP status code should be aligned but still represent different layers:

- **HTTP status** = protocol-level outcome (e.g. 200, 400, 500, 503).
- **Payload `status`** = platform contract outcome (`success` / `failure`).
- **Payload `resolution_state`** = lookup domain result (only when payload `status = success`).

Recommended behavior:
- `found` / `initializing_db` / `not_found` are successful lookup outcomes, so they can be returned with HTTP `200` and payload `status = success`.
- Runtime exceptions, adapter crashes, corrupted source failures, etc. should return payload `status = failure` and an appropriate HTTP error code (commonly `500` or `503`, based on your API policy).

### 6.4 Example payloads

Success + found:

```json
{
  "status": "success",
  "service_state": "ready",
  "resolution_state": "found",
  "data": {
    "ip": "1.0.0.8",
    "network": "1.0.0.0/24",
    "country": "AU",
    "asn": "AS13335"
  }
}
```

Success + initializing_db:

```json
{
  "status": "success",
  "service_state": "loading",
  "resolution_state": "initializing_db",
  "data": {
    "ip": "8.8.8.8",
    "network": null,
    "country": null,
    "asn": null
  }
}
```

Service failure envelope (no lookup semantics):

```json
{
  "status": "failure",
  "service_state": "failed",
  "error": {
    "code": "IP_GEO_INIT_FAILED",
    "message": "Failed to load geolocation dataset"
  }
}
```

---

## 7) Progressive Loading Behavior

Desired behavior (as discussed):

- Service starts loading at app startup.
- Geo endpoints remain available during loading.
- Loading should proceed in batches/chunks of parsed NDJSON lines.
- If requested IP data is already loaded -> return geo details.
- If requested IP is not currently found while load is still in progress -> return null geo fields with:
  - `resolution_state = "initializing_db"`
- If requested IP is not found after full load completes -> return:
  - `resolution_state = "not_found"`

This prevents downtime while avoiding ambiguous response semantics.

---

## 8) Concurrency and Safety

Concurrency ownership follows a **two-layer contract**:

1. **Runner lifecycle layer** (`background_task_runner`) owns generic task runtime lifecycle.
2. **Domain refresher layer** (`ip_geolocation_data_refresher`) owns geolocation snapshot build/publish safety.

This document keeps only IP geolocation requirements and integration wiring.
Generic runner behavior details are intentionally centralized in the runner service document.

### 8.1 Background task runner ownership and contract reference

All generic runner lifecycle/overlap/cancellation/error-boundary contract details are documented in:
- `code/backend/services/background_task_runner/background_task_runner_service.md`

`ip_geolocation_service.md` must reference those contracts and avoid re-defining runner internals.

### 8.2 Task-level state publication standard (IP geolocation refresher)

`ip_geolocation_data_refresher` should enforce domain-level data safety:

1. Parse and build a **new immutable snapshot** off the active read path.
2. Validate fully before publication.
3. Publish via **atomic snapshot swap** (`active_cache <- new_snapshot`).
4. On reload failure, keep old snapshot active.

Performance guidance:
- Prefer lock-free read path against immutable snapshots.
- If a lock is needed, keep it around only the tiny publication/status update boundary, not parsing.

### 8.3 In-memory cache refresh on source file replacement/edit

Because `ipinfo-geo.json` may be replaced multiple times per day, the service should support automatic refresh.

Recommended runtime behavior:

1. Start a background watcher/poller at service initialization.
2. Poll source file metadata on a short interval (e.g. `1-2s`).
3. Track this lightweight fingerprint from `os.stat(...)`:
   - `st_ino` (inode)
   - `st_mtime_ns` (nanosecond mtime)
4. If fingerprint changed, debounce briefly (e.g. `300-1000ms`) and trigger reload.
5. Reload by parsing file into a **new** in-memory snapshot (do not mutate active cache in place).
6. On successful parse/validation, atomically swap `active_cache <- new_snapshot`.
7. On parse failure, keep old cache, mark reload failure metrics/status, and continue serving requests.

Ownership note:
- Poll loop lifecycle should be hosted by `background_task_runner`.
- IP geolocation refresh logic should be hosted by `ip_geolocation_data_refresher`.
- For exact runner guarantees and APIs, follow `background_task_runner/background_task_runner_service.md`.

Notes:
- This design avoids expensive full-file hashing checks on every poll for GB-sized files.
- `inode + mtime_ns` is the chosen practical trigger for this project's controlled update workflow.
- Atomic swap guarantees readers never see partial/half-built cache state.

### 8.4 Writer-side contract (important)

The process that updates `ipinfo-geo.json` should use atomic replace semantics:

1. Write new dataset to a temporary file in the same directory.
2. Rename temp file to `ipinfo-geo.json`.

This minimizes partial-write exposure and makes inode/mtime-based detection reliable in practice.

---

## 9) Public Service Interface (Planned)

Planned methods:

- `initialize_ip_geolocation_dataset() -> None`
  - start initial load (startup trigger)

- `lookup_ip_geolocation(ip: str) -> GeoLookupResultModel`
  - on `status = success`, return `resolution_state` as `found`, `initializing_db`, or `not_found`
  - on service failures, return standard `status = failure` envelope

- `get_ip_geolocation_load_status() -> GeoLoadStatusModel`
  - expose loading state/progress

- `reload_ip_geolocation_dataset() -> None` (optional)
  - manual refresh entrypoint

- `start_ip_geolocation_source_watch() -> None` (optional)
  - register/start IP geolocation refresher task in background task runner

- `stop_ip_geolocation_source_watch() -> None` (optional)
  - unregister/stop IP geolocation refresher task from background task runner

---

## 10) Integration with App/API

App layer module:
- `apps/ip_geolocation/ip_geolocation_app.py`

API layer module:
- `api/ip_geolocation_api.py`

Suggested endpoints:
- `GET /api/geo/lookup?ip=...`
- `GET /api/geo/status`
- `POST /api/geo/reload` (optional)

---

## 11) Configuration

Suggested env vars:
- `IP_GEO_PROVIDER` (default: `ipinfo`)
- `IP_GEO_LOADING_MODE` (`progressive` | `strict`)
- `IP_GEO_BATCH_SIZE`
- `IP_GEO_MAX_BAD_LINES` (maximum tolerated malformed lines before fail)
- `IP_GEO_NORMALIZE_HOST_IP` (`true` by default; converts bare host IPs to `/32`)
- `IP_GEO_WATCH_ENABLED` (`true` by default)
- `IP_GEO_WATCH_INTERVAL_SECONDS` (default: `1.0`)
- `IP_GEO_WATCH_DEBOUNCE_MS` (default: `500`)

---

## 12) Testing Plan

Unit tests:
- state transitions
- lookup behavior in `initializing_db` vs `ready` (`initializing_db` transitions to `not_found` after full load)
- failure handling and reload flow
- response contract behavior:
  - success envelope with `found` / `initializing_db` / `not_found`
  - standard failure envelope on runtime errors
- NDJSON line parser behavior (valid/invalid line handling)
- network normalization behavior:
  - CIDR stays CIDR
  - bare host IP normalized to `/32`
- nullable ASN field handling (`asn`, `as_name`, `as_domain`)
- malformed-line counters and strictness threshold behavior
- source-change refresh trigger behavior (`inode`/`mtime_ns` changes)
- unchanged source metadata should not trigger reload
- failed hot-reload keeps previous active cache
- successful hot-reload atomically swaps to new cache

Integration tests:
- route wiring for `/api/geo/lookup` and `/api/geo/status`
- payload contract consistency
- startup progressive load with `resolution_state = "initializing_db"` during in-flight load
- status payload includes total/loaded/failed-line metrics
- replacing `ipinfo-geo.json` during runtime refreshes lookup results without process restart

Use small fixture **NDJSON** files for deterministic tests.

---

## 13) Future Enhancements

- Replace raw JSON structure with optimized index format for memory efficiency
- Add Redis L2 cache for multi-instance deployments
- Add provider-switch strategy via adapter composition without service API changes

---

## 14) Summary

This service design keeps:
- architecture boundaries clean,
- naming explicit and domain-oriented,
- startup behavior resilient,
- responses unambiguous during progressive load,
- future provider migration low-impact.

---

## 15) Implementation Action Plan (Execution Sequence Locked)

This section is the implementation-grade action plan for this module and is explicitly aligned to the required sequence:

1. models
2. infra adapter/parsers
3. refresher service component
4. extend models for ip geo part (if required)
5. ip geo service component
6. expose ip geo to app layer
7. expose ip geo to api layer

The rule for implementation is strict ordering: do not move to the next stage until the previous stage acceptance checks pass.

### 15.1 Goal, Deliverables, Success Criteria, Constraints

Goal:
- Implement IP geolocation with background-driven source refresh first, then expose query/status capabilities through app and API layers.

Primary deliverables:
- `code/backend/models/ip_geolocation/ip_geolocation_models.py`
- `code/backend/infra/ip_geolocation/ip_geolocation_ipinfo_json_file_reader_adapter.py`
- `code/backend/infra/ip_geolocation/ip_geolocation_ipinfo_json_file_reader_parser.py`
- `code/backend/services/ip_geolocation/ip_geolocation_data_refresher.py`
- `code/backend/services/ip_geolocation/ip_geolocation_service.py`
- `code/backend/apps/ip_geolocation/ip_geolocation_app.py`
- `code/backend/api/ip_geolocation_api.py`
- Router/lifespan wiring updates (`code/backend/api/router.py`, `code/backend/main.py`)
- Unit + integration tests for parser/refresher/service/routes

Success criteria:
- Startup state transitions: `loading -> ready` after first successful publish.
- Lookup contract correctness:
  - `found` when matched,
  - `initializing_db` while load is in progress and no conclusive miss,
  - `not_found` only after full readiness.
- Source file change (`inode + mtime_ns`) triggers rebuild and atomic snapshot swap.
- Refresh failures never replace active snapshot; old snapshot remains served.
- App/API routes return model-consistent payloads.

Constraints:
- Enforce architecture flow: `api -> apps -> services -> infra/models`.
- Keep background runner generic (no domain logic inside runner).
- Keep all IP geo DTOs in `models/ip_geolocation`.
- Service must not perform low-level file parsing directly.

---

### 15.2 Stage 1 — Models

Scope:
- Create/complete DTOs and state contracts in `code/backend/models/ip_geolocation/ip_geolocation_models.py`.

Required model groups:
1. Service lifecycle state:
   - `loading`, `ready`, `failed`
2. Lookup resolution state:
   - `found`, `initializing_db`, `not_found`
3. Normalized geo record model:
   - network, country fields, continent fields, optional ASN metadata
4. Snapshot/status models:
   - counters (`total`, `loaded`, `malformed`), timestamps, optional refresh metadata
5. API-facing lookup response model:
   - two-axis contract: envelope `status` and `resolution_state`

Acceptance checks:
- Models are imported from `models/ip_geolocation` only (no duplicate DTOs in services/apps/api).
- Field names align with sections 6 and 9 of this document.

---

### 15.3 Stage 2 — Infra adapter/parsers

Scope:
- Implement source read + parse stack under `code/backend/infra/ip_geolocation/`.

Modules:
- `ip_geolocation_ipinfo_json_file_reader_adapter.py`
- `ip_geolocation_ipinfo_json_file_reader_parser.py`

Design decision:
- Use a single concrete adapter (`ip_geolocation_ipinfo_json_file_reader_adapter.py`) for refresher-facing source reads.
- Keep parsing/normalization logic in `ip_geolocation_ipinfo_json_file_reader_parser.py`.
- Do not add a separate generic source adapter contract file until multi-provider support is needed.

Behavior contract:
1. Read `code/backend/data/ip_geolocation/ipinfo-geo.json` line-by-line.
2. Parse each non-empty line as standalone JSON object (NDJSON semantics).
3. Normalize network values:
   - CIDR stays CIDR,
   - host-only IP normalized to `/32`.
4. Keep ASN fields nullable (`asn`, `as_name`, `as_domain`).
5. Count malformed lines and surface this count for observability.

Acceptance checks:
- Parser handles valid, invalid, and mixed NDJSON fixture lines deterministically.
- Normalization rules match section 3.2.

---

### 15.4 Stage 3 — Refresher service component (first runtime priority)

Scope:
- Implement `code/backend/services/ip_geolocation/ip_geolocation_data_refresher.py` as domain refresh producer.

Responsibilities:
1. Poll source metadata fingerprint (`st_ino`, `st_mtime_ns`).
2. Detect changes and debounce reload trigger.
3. Build/validate new immutable snapshot off read path.
4. Publish snapshot through service entrypoint only.
5. On failure: keep old snapshot, report refresh error metadata.

Runner integration:
- Register refresher as background task in `background_task_runner`.
- Suggested task id: `ip_geolocation_source_watch`.

Acceptance checks:
- Unchanged fingerprint does not trigger reload.
- Changed fingerprint triggers rebuild.
- Failed rebuild never mutates active serving snapshot.

---

### 15.5 Stage 4 — Extend models for IP geo part (if required)

Scope:
- After refresher/service handshake is implemented, extend model contracts only where integration reveals missing runtime fields.

Possible additions:
- `last_refresh_error`
- `last_refresh_attempt_at`
- `last_refresh_succeeded_at`
- `active_source_fingerprint`
- counters for refresh attempts/success/failure

Acceptance checks:
- Any added fields are backward-compatible and documented.
- Status payload remains clear and non-ambiguous.

---

### 15.6 Stage 5 — IP geo service component (read-facing facade)

Scope:
- Implement `code/backend/services/ip_geolocation/ip_geolocation_service.py`.

Responsibilities:
1. Own active snapshot + runtime read-facing state.
2. Expose lookup/status use-cases.
3. Provide single publish/swap entrypoint for refresher.
4. Enforce atomic snapshot swap.

Planned methods:
- `initialize_ip_geolocation_dataset()`
- `lookup_ip_geolocation(ip: str)`
- `get_ip_geolocation_load_status()`
- `publish_snapshot(new_snapshot, metadata)`
- optional: `reload_ip_geolocation_dataset()`

Acceptance checks:
- During `loading`, unresolved lookups return `initializing_db`.
- During `ready`, unresolved lookups return `not_found`.
- Service-level failure uses standard failure envelope (`status = failure`).

---

### 15.7 Stage 6 — Expose IP geo to app layer

Scope:
- Add app orchestrator module: `code/backend/apps/ip_geolocation/ip_geolocation_app.py`.

Responsibilities:
- Call service methods only (no infra/parser/file logic).
- Provide app-level functions for lookup/status (+ optional manual reload).

Acceptance checks:
- App layer remains thin orchestration boundary, consistent with `apps/ping` and `apps/traceroute` conventions.

---

### 15.8 Stage 7 — Expose IP geo to API layer

Scope:
- Add API router module: `code/backend/api/ip_geolocation_api.py`.
- Register router in `code/backend/api/router.py`.

Suggested endpoints:
- `GET /api/geo/lookup?ip=...`
- `GET /api/geo/status`
- optional `POST /api/geo/reload`

Lifespan/runtime wiring:
- In `code/backend/main.py` lifespan startup:
  - build/resolve service,
  - build refresher,
  - register/start refresher task in background runner.
- In shutdown:
  - stop refresher task,
  - stop runner idempotently.

Acceptance checks:
- Routes are reachable and return model-consistent payloads.
- Startup/shutdown does not leave duplicate or zombie task loops.

---

### 15.9 Test Execution Plan (gated by sequence)

Unit tests:
1. Models serialization and state-value constraints.
2. Parser behavior (NDJSON, malformed-line handling, `/32` normalization).
3. Refresher behavior (fingerprint detection, publish/no-publish paths).
4. Service lookup semantics (`found` / `initializing_db` / `not_found`).

Integration tests:
1. API route wiring and payload shape consistency.
2. Startup progressive-loading behavior.
3. Runtime file replacement triggers refreshed results without process restart.

Gate condition:
- Do not mark implementation complete until all targeted tests pass and route/lifecycle checks are green.

---

### 15.10 Execution Order Checklist (Implementation Tracker)

- [ ] Stage 1 complete: models
- [ ] Stage 2 complete: infra adapters/parsers
- [ ] Stage 3 complete: refresher service component
- [ ] Stage 4 complete: model extension (if required)
- [ ] Stage 5 complete: ip geo service component
- [ ] Stage 6 complete: app layer exposure
- [ ] Stage 7 complete: api layer exposure
- [ ] Tests and lifecycle validations complete