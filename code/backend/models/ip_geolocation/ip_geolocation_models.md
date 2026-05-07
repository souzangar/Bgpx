# IP Geolocation Models Layer

## Purpose
- Defines immutable shared contract models for IP geolocation requests, records, lookup payloads, status snapshots, and response envelopes.
- Enforces model-level validation inside dataclass `__post_init__` methods.

## Validation Conventions
- String identity fields are validated as non-empty trimmed strings (for example: `ip`, `asn`, `country`, `continent`, and error fields).
- Numeric counters that represent quantities must be non-negative.

## Shared Validation Constants
- `TOTAL_CANNOT_BE_NEGATIVE_ERROR = "total cannot be negative"`
  - Centralizes the repeated non-negative `total` validation message across:
    - `IpGeolocationAsnLookupDataModel`
    - `IpGeolocationCountryLookupDataModel`
    - `IpGeolocationContinentLookupDataModel`
    - `IpGeolocationLoadCountersModel`
  - Keeps error text behavior unchanged while preventing duplicated literals and aligning with static analysis expectations.

## Notes
- This layer exposes model symbols via `__all__` in `ip_geolocation_models.py`.
- Changes in this file should remain synchronized with implementation updates in `ip_geolocation_models.py`.