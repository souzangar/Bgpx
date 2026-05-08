# Hero Section (`Hero.tsx`)

## Purpose

The Hero layer introduces BGPX and presents the **Client IP info** frame.

It provides:

- Product headline and short description
- Primary CTA (`Run a check`)
- Secondary CTA (`View API examples`)
- Client IP metadata panel with loading/error/success rendering

## Current Layout Behavior

- Container uses a two-column grid on large screens:
  - `lg:grid-cols-2`
- This creates a **50/50 split** between:
  - Left: text and action buttons
  - Right: client IP information frame

## Typography Decisions

To improve balance between content and the client info panel, font sizes were reduced:

- Hero title:
  - from `text-4xl sm:text-5xl lg:text-6xl`
  - to `text-3xl sm:text-4xl lg:text-5xl`
- Hero paragraph:
  - from `text-sm sm:text-base leading-7`
  - to `text-xs sm:text-sm leading-6`
- Client IP heading (`Client IP info`):
  - reduced to `text-[11px]` with slightly tighter tracking
- Client IP key/value rows:
  - reduced to `text-[11px]`
  - row spacing tightened (`space-y-1.5`)

## Data Rendering Contract

The right panel uses `clientIpInfoState` (`RequestState<ClientIpInfoResponse>`) and keeps three states:

1. **Loading**: shows resolving message
2. **Error**: shows failure message
3. **Success**: renders structured key/value rows from `fieldRows`

No API logic was changed in this update; this layer change is visual/layout only.