# Top Navigation (`TopNav.tsx`)

## Purpose

The top navigation provides a minimal, persistent header for the frontend shell.

## Current Behavior

- Renders the `BrandMark` on the left (`BGPX` / `Looking Glass`).
- Keeps a right-aligned GitHub repository action on `sm` and larger breakpoints.
- Uses sticky positioning with border and blur styling to match the dashboard theme.

## Removed Elements

Per latest UI simplification:

- The top search/command bar (`Search hosts, prefixes, ASNs`) is removed.
- The API health indicator pill is removed.

The top nav is now intentionally minimal and no longer accepts props for search focus or API health tone/label.