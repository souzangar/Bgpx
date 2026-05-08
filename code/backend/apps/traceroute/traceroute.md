# Traceroute App Layer (`traceroute_app.py`)

## Purpose

The traceroute app layer orchestrates traceroute use-case flow for upper layers.

## Current behavior

- Calls `TracerouteAdapter.run_traceroute(host)` to collect normalized hop data.
- Enriches each successful hop with geolocation `country_code` by calling IP geolocation service lookup on hop IP.
- Skips geolocation lookup for non-IP hops (for example `*`) and keeps `country_code` as `null`.

## Contract notes

- API layer stays transport-only and returns app output via `asdict(...)`.
- Hop-level field `country_code` is additive and nullable for unresolved/private/unavailable records.
