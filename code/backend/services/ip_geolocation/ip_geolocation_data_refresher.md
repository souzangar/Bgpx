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

## Notes

- Event IDs must remain aligned with `logging_config.json`.
- If new event IDs are added in code, update logging config in the same change.