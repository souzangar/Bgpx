# Tools Section (`Tools.tsx`)

## Purpose

The Tools layer provides operational diagnostics and lookup utilities inside the frontend:

- **Network tools**
  - **Ping** (single probe latency/status)
  - **Traceroute** (path hops with RTT/loss)
- **IP Tools**
  - **IP Lookup**
  - **ASN Lookup**
  - **Country Lookup**

## Layout Behavior

This section renders as **two stacked cards in vertical page order**.

- `ToolCard` #1: `id="network-tools"`
  - Internal tabs:
    - `Ping`
    - `Traceroute`
- `ToolCard` #2: `id="ip-tools"`
  - Internal tabs:
    - `IP Lookup`
    - `ASN Lookup`
    - `Country Lookup`

Both cards keep the same visual language (tab chips, border treatments, and typography) used across the rest of the tools UI.

Order on page:
1. `Network tools`
2. `IP Tools`

## Interaction Model

- Local state `activeTab` controls the active **Network tools** tab.
- Local state `activeIpTab` controls the active **IP Tools** tab.
- Tab buttons update their respective state and are visually highlighted when active.
- Network tools card header icon/description changes based on active network tab metadata.
- IP Tools card description changes based on the active IP tab metadata.

## Data and Behavior Contract

Existing request/validation behavior is preserved:

- Ping uses existing props/state:
  - `pingHost`, `pingValidationError`, `pingState`
  - `onPingHostChange`, `onRunPing`
- Traceroute uses existing props/state:
  - `tracerouteHost`, `tracerouteValidationError`, `tracerouteState`
  - `onTracerouteHostChange`, `onRunTraceroute`

IP Tools are wired to lookup behavior:

- **IP Lookup** renders resolved IP/network/country/ASN/domain details.
  - Country presentation is a single field combining country name with formatted country code (`flag + ISO-2`) in parentheses.
    - Example: `Australia (🇦🇺 AU)`
  - The previous standalone country-code card is removed.
  - The freed card slot is now used for **ASN Name** (`as_name`) with `N/A` fallback when absent.
- **ASN Lookup** renders a network list table for the ASN.
- **Country Lookup** renders a network list table for the country code.

ASN and Country lookup displays include provider naming when available:

- ASN result summary renders `ASN - as_name` above the table (for example `AS13335 - Cloudflare, Inc.`).
- Country table ASN cells render `ASN - as_name` when both are present, otherwise fallback to plain ASN or `N/A`.

ASN lookup table also includes a right-aligned filter input on the same header row:

- Filter matches across all row fields (case-insensitive):
  - `network` (IP/CIDR)
  - `country` and `country_code`
  - `continent` and `continent_code`
- Pagination is applied on filtered results.

Country lookup table also includes a right-aligned filter input on the same header row:

- Filter matches across all row fields (case-insensitive):
  - `network` (IP/CIDR)
  - `continent` and `continent_code`
  - `asn` and `as_name`
- Pagination is applied on filtered results.

ASN and Country list tables support pagination:

- **15 items per page**
- Bottom navigation controls:
  - `Previous`
  - current page indicator (`Page X / Y`)
  - `Next`
- **Go to page** input + `Go` button
- Navigation buttons are disabled at range boundaries (first/last page).

Traceroute table contract now includes geolocation enrichment:

- An **ASN** column is rendered as the **rightmost** traceroute table column.
- A **Country** column is rendered immediately before ASN.
- ASN cell format is `asn - as_name` when both values are available.
- If `as_name` is missing, ASN cell falls back to `asn`.
- If ASN data is unavailable, ASN cell shows `N/A`.
- The displayed value is composed from hop-level `country` and `country_code` returned by backend.
- When both values are present and code is valid, UI renders **`Country (flag + code)`** (for example `Australia (🇦🇺 AU)`).
- If only country name is available, UI renders the country name.
- If only a valid country code is available, UI renders **flag + code** (for example `🇩🇪 DE`).
- If both fields are missing/invalid (for example private IPs or unresolved interconnect hops), UI shows **`N/A`**.

This keeps the column title user-friendly while preserving a compact country-code display format.