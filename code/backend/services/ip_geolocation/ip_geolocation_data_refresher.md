# IP Geolocation Data Refresher (`ip_geolocation_data_refresher.py`)

## Purpose

`IpGeolocationDataRefresher` polls source file fingerprint changes and publishes refreshed IP geolocation snapshots.

Core responsibilities:
- detect source changes (`inode` + `mtime_ns`)
- debounce rapid file updates
- rebuild snapshots via adapter
- publish chunked or single snapshot updates
- keep previous active snapshot on refresh errors

## Logging Contract

Component/event logger:
- component key: `ip_geo_refresher`
- base logger: `bgpx.tasks.ip_geo.refresher`
- runtime config: `code/backend/data/configs/logging_config.json`

Important event:
- `chunk_published`

### Compact chunk log format (current)

Chunk publish logs are intentionally compact to avoid noisy, long terminal lines per chunk.

Current message template:

```text
IP geo chunk published (chunk=%s, records=%s, published=%s, final=%s, elapsed=%.2fs)
```

This keeps progress signal while removing verbose per-chunk fields that previously made logs too long.

## Performance Model (memory + startup latency)

This refresher was redesigned to avoid loading the full dataset into memory
twice per refresh cycle and to start publishing chunks as soon as possible.

### Streaming path (preferred)

When the adapter exposes `iter_read_results(chunk_size=...)`:

1. **First load** (no active snapshot or service not yet `ready`):
   - Single streaming pass reads and publishes chunks incrementally via
     `publish_snapshot(...)`.
   - No pre-scan; time-to-first-chunk is minimal.
   - Final chunk triggers the service's atomic snapshot swap.

2. **Subsequent refreshes** (active snapshot exists and
   `get_active_key_index` is available):
   - **Pass 1 — streaming pre-scan:** build a compact
     `dict[str, int]` (`network` → content hash) of the incoming dataset.
     Full records from each chunk are dropped as soon as their hash
     contribution is recorded. Peak memory is proportional to *one chunk*
     plus the resulting key index, never the full record set.
   - Diff the incoming index against the service's cached key index:
     - **Equivalent:** emit `refresh_skipped_equivalent` and stop.
     - **Small change ratio** (`changed / current_size ≤ delta_threshold_ratio`,
       default `0.1`) AND `apply_snapshot_delta_records` available:
       run **Pass 2 — streaming delta apply**. Pass 2 re-iterates the file
       and materializes only records whose network is in the
       `added ∪ updated` set; `removed` networks are dropped by the service.
     - **Otherwise:** run **Pass 2 — streaming full republish** (chunked
       publish path).
   - Old snapshot keeps serving reads throughout both passes; atomic swap
     only happens on the final chunk / delta apply.

### Non-streaming path (legacy fallback)

For adapters that don't expose `iter_read_results` (e.g. some test fakes),
the refresher falls back to the previous behavior: single `read_records()`
call, then `is_snapshot_equivalent` check, then `apply_snapshot_delta`, then
full single-result publish if needed.

### Constructor callables

`IpGeolocationDataRefresher.__init__` accepts these snapshot-side callables:

- `publish_snapshot` *(required)* — chunked publish into service.
- `is_snapshot_equivalent` *(optional)* — legacy non-streaming equivalence.
- `apply_snapshot_delta` *(optional)* — legacy non-streaming delta apply.
- `get_active_key_index` *(optional)* — streaming pre-scan diff source.
  Returns `None` when the service has no active snapshot; that signals the
  refresher to take the streaming full-republish path (first load).
- `apply_snapshot_delta_records` *(optional)* — streaming delta apply
  entrypoint. Receives only the changed records plus a `removed_networks`
  set — never the full incoming dataset.

Also tunable:

- `publish_chunk_size` (default `50_000`) — chunk size for streaming passes.
- `delta_threshold_ratio` (default `0.1`) — streaming delta vs full
  republish decision threshold.

### Localhost override validation

Validation is **log-only** (refresher never mutates the source file). On the
streaming path, the first record captured during the pre-scan pass is used
so we don't read the file a third time just to validate. On first load
(no pre-scan), validation happens on the first non-empty chunk.

## Notes

- Event IDs must remain aligned with `logging_config.json`.
- If new event IDs are added in code, update logging config in the same change.
- `_record_value_hash(record)` in this module must stay in sync with
  `IpGeolocationService._record_value_hash` so streaming diffs match the
  service's cached key index.
