# Bruno Requests for BGPX

This folder contains Bruno API request collections for the BGPX project.

## Purpose

- Provide ready-to-run requests for local API testing.
- Keep examples consistent for developers, QA, and AI coding agents.
- Offer reusable templates for creating new endpoint requests.

## Current Structure

```text
bruno-requests/
├── README.md
└── BGPX/
    ├── opencollection.yml
    ├── Get Health.yml
    └── Samples/
        ├── Sample GET Resource.yml
        ├── Sample POST Resource.yml
        ├── Sample PUT Resource.yml
        ├── Sample PATCH Resource.yml
        └── Sample DELETE Resource.yml
```

## Base URL and Environment Notes

- Default API base URL in current requests: `https://localhost`
- Health endpoint currently implemented in backend: `GET /api/health`
- Backend runs with HTTPS (self-signed/local cert setup may require trust configuration in your client/runtime)

## What is Real vs Template

- **Real endpoint (currently implemented):**
  - `Get Health.yml` → `GET /api/health`
- **Template/sample endpoints (may not exist yet in backend):**
  - All files under `BGPX/Samples/` using `/api/resources` paths

Use sample requests as scaffolding when new CRUD endpoints are added.

## Request Authoring Conventions

When adding requests, follow these rules:

1. Keep file names descriptive: `Verb Resource.yml`.
2. Use HTTPS URLs and explicit API paths.
3. Keep `auth: inherit` unless endpoint requires explicit auth config.
4. For JSON payloads:
   - Add `Content-Type: application/json`
   - Use realistic payload examples.
5. Keep request settings aligned:
   - `encodeUrl: true`
   - `followRedirects: true`
   - `maxRedirects: 5`

## AI-Friendly Instructions (Machine Readable)

AI agents should follow this policy when updating this folder:

1. Do not modify `opencollection.yml` unless collection metadata changes.
2. Preserve existing working requests.
3. Add new files under the same collection (`BGPX`) and keep sequence numbers unique/incremental.
4. If endpoint is not implemented, mark request as `Sample` in file name and documentation.
5. For CRUD examples, use canonical paths:
   - Collection path: `/api/resources`
   - Item path: `/api/resources/{id}`
6. Prefer JSON examples with clear, minimal fields.
7. Keep each request self-contained and readable by humans.

## Quick Start

1. Open Bruno.
2. Open collection folder: `bruno-requests/BGPX`.
3. Run `Get Health` first to verify local backend connectivity.
4. Use sample CRUD requests as templates for new backend APIs.
