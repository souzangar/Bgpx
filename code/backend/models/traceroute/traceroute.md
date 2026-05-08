# Traceroute Models (`traceroute_models.py`)

## Purpose

Defines shared traceroute DTOs used across infra/app/api layers.

## Current hop contract

`TracerouteHopModel` includes:

- distance/address
- RTT and packet-loss metrics
- `country: str | None`
- `country_code: str | None`
- `asn: str | None`
- `as_name: str | None`

`country`, `country_code`, `asn`, and `as_name` are nullable to support hops that cannot be geolocated (timeouts, private/unlisted ranges, or unresolved addresses).

## Result contract

`TracerouteResultModel` keeps stable envelope fields:

- `result`
- `hops`
- `message`

The hop-level geolocation field is additive and backward-compatible for API consumers.
