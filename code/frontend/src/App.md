# App Shell (`App.tsx`)

## Purpose

`App.tsx` composes the frontend page shell and wires top-level state/requests for the interactive tools.

## Current Layout Composition

The main page now renders these sections in order:

1. `TopNav`
2. `Hero`
3. `Tools`

## Removed Section

Per latest UI simplification, the bottom `ApiExamples` section has been removed from the page layout.

- `App.tsx` no longer imports `./sections/ApiExamples`.
- `App.tsx` no longer renders `<ApiExamples />` at the bottom of `<main>`.

## Notes

- Ping and traceroute flows remain unchanged.
- Client IP info bootstrap remains unchanged and is still passed to `Hero`.