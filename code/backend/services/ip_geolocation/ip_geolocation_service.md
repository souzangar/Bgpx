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
- `ip_geolocation_source_adapter.py`
- `ip_geolocation_ipinfo_json_file_reader_adapter.py`
- `ip_geolocation_ipinfo_payload_parser.py`

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

Race-condition prevention should be implemented as a **two-layer model**:

1. **Runner-level lifecycle safety** (`background_task_runner`) for all current/future background tasks.
2. **Task-level state publication safety** (`ip_geolocation_data_refresher`) for domain-specific shared data.

This split gives both:
- reusable platform standards across tasks,
- high-performance domain correctness for geolocation cache reads/writes.

### 8.1 Background task runner ownership and contract reference

All generic runner lifecycle, overlap, cancellation, and error-boundary behavior is documented in:
- `code/backend/services/background_task_runner_service.md`

This IP geolocation document intentionally keeps only integration expectations.

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
- Poll loop lifecycle and overlap prevention should be hosted by `background_task_runner`.
- IP geolocation refresh logic should be hosted by `ip_geolocation_data_refresher`.
- For exact runner guarantees and APIs, follow `background_task_runner_service.md`.

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