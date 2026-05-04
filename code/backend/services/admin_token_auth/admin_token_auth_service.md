# Admin Token Auth Service Plan (`admin_token_auth_service.py`)

This document defines the design and implementation plan for a reusable admin-token authentication/authorization service.

Target location:
- Service doc: `code/backend/services/admin_token_auth/admin_token_auth_service.md`
- Planned service module: `code/backend/services/admin_token_auth/admin_token_auth_service.py`
- Planned models package: `code/backend/models/admin_token_auth/`

---

## 1) Purpose

`admin_token_auth` provides a **shared token-guard mechanism** for privileged backend operations.

Primary goals:
- protect private/admin endpoints with a reusable policy,
- avoid ad-hoc token checks duplicated across route files,
- provide one stable contract for both:
  - remote/internal admin users (network access with token).

---

## 2) Domain Design Guideline Alignment

Follow project architecture flow:

`api -> apps -> services -> infra/models`

### 2.1 Boundary rules

1. **API layer**
   - receives requests and invokes dependency guard from `services/admin_token_auth`.
   - must not implement token comparison logic inline.

2. **App layer**
   - orchestrates domain actions (e.g., IP geo status/reinitialize/refresh-once).
   - must not own auth validation rules.

3. **Service layer (`admin_token_auth`)**
   - owns token retrieval, normalization, validation, and guard result mapping.
   - reusable across all future private APIs.

4. **Models layer**
   - owns shared DTOs/contracts for admin auth result/error metadata.

---

## 3) Why This Service Is Needed

Admin operations may run from separate processes/services than backend process memory.
To operate on **existing runtime state**, callers must use protected runtime endpoints.

Therefore we need:
- protected admin API endpoints, and
- a shared auth service so protection is consistent and maintainable.

---

## 4) Naming and Package Structure

Approved naming:
- `admin_token_auth`

Planned structure:

```text
code/backend/services/
  admin_token_auth/
    __init__.py
    admin_token_auth_service.py
    admin_token_auth_service.md

code/backend/models/
  admin_token_auth/
    __init__.py
    admin_token_auth_models.py
```

---

## 5) Token Strategy (v1.1 - simple multi-token)

### 5.1 Token source
- Primary environment variable: `BGPX_ADMIN_TOKENS`

`BGPX_ADMIN_TOKENS` supports multiple entries with optional note (e.g., person name):

```text
<token>|<note>
```

Example values:

```text
token_1|person 1;token_2|person 2
```

or newline-separated:

```text
token_1|person 1
token_2|person 2
```

Parsing rules (keep simple):
1. token is required; note is optional,
2. separators accepted: `;` and newline,
3. blank/invalid entries are ignored,
4. duplicate tokens are de-duplicated.

### 5.5 `.env` sample

Recommended `.env` setting:

```env
# Admin tokens (single privilege level, no RBAC)
# Format: <token>|<note> ; <token>|<note>
BGPX_ADMIN_TOKENS=token_1|person 1;token_2|person 2
```

Docs readability equivalent (newline style):

```text
token_1|person 1
token_2|person 2
```

### 5.2 Transport
- Request header: `X-Admin-Token`

### 5.3 Validation rules
1. If configured token set is missing/empty -> fail closed for protected routes.
2. If request token missing -> `401 Unauthorized`.
3. If token does not match any configured token -> `401 Unauthorized`.
4. If token matches one configured token -> authorized (single access level).
5. Compare using constant-time comparison (`hmac.compare_digest`) in membership check loop.

### 5.4 Logging rules
- Never log raw token values.
- Log only decision-level metadata (missing/invalid/accepted).

---

## 6) Models Design (`models/admin_token_auth`)

Planned DTOs:

1. `AdminTokenValidationResultModel`
   - `is_authorized: bool`
   - `reason: Literal["ok", "missing_config", "missing_token", "invalid_token"]`
   - optional `matched_note: str | None` (for audit/debug only; never expose token)

2. `AdminAuthErrorModel`
   - `code: str`
   - `message: str`

3. Optional helper model for observability:
   - `AdminTokenAuthConfigStateModel` (e.g., configured/not-configured)

Rule:
- Keep these contracts in `models` only.
- Service/app/api should import from models package.

---

## 7) Service Design (`admin_token_auth_service.py`)

Planned responsibilities:

1. Load configured admin token entries from env (`BGPX_ADMIN_TOKENS`).
2. Validate incoming token.
3. Return model-based validation result (optional matched note metadata).
4. Provide FastAPI-friendly guard/dependency wrapper.

Planned method examples:
- `get_configured_admin_tokens()`
- `validate_admin_token(provided_token: str | None)`
- `require_admin_token(provided_token: str | None)`

Behavior:
- deterministic failure reasons,
- fail-closed when config is absent,
- no domain-specific logic (IP geo logic remains outside this service).

---

## 8) Integration Contract

### 8.1 Admin API endpoints (runtime-side)

Suggested endpoints:
- `GET /api/admin/ip-geolocation/status`
- `POST /api/admin/ip-geolocation/reinitialize`
- `POST /api/admin/ip-geolocation/refresh-once`

All protected by `admin_token_auth` guard.

### 8.3 Reuse for future domains

Any future private API (ping/traceroute/maintenance/etc.) reuses the same guard.

---

## 9) Security Notes

1. Prefer binding backend admin exposure to trusted network interfaces.
2. Use TLS in non-local deployments.
3. Rotate tokens in `BGPX_ADMIN_TOKENS` via deployment/env management.
4. Keep all tokens at one privilege level in v1.1 (no RBAC/scope checks).

---

## 10) Acceptance Criteria

1. Protected endpoints reject missing/invalid token with `401`.
2. Any valid configured token allows runtime admin actions.
3. Admin clients control existing runtime (not local isolated state) via endpoint calls.
4. Token validation logic exists in one reusable service (no duplicated checks).
5. Notes (e.g., person labels) are supported in configuration without adding RBAC complexity.
6. Tests cover positive and negative auth paths.

---

## 11) Out of Scope (v1.1)

- Role-based access control (RBAC)
- External identity provider integration
- Persistent credential store

These can be added later without breaking v1 route contracts.

---

## 12) Implementation Action Plan (Dedicated Final Section)

This is the dedicated final section of the file and contains the implementation-grade action plan for admin token authentication.

Implementation sequence:

1. models
2. service core
3. FastAPI guard contract
4. protected endpoint integration
5. router wiring
6. unit tests
7. integration tests

Rule:
- Do not move to the next stage until the current stage acceptance checks pass.

### 12.1 Goal, Deliverables, Success Criteria, Constraints

Goal:
- Deliver a reusable, centralized admin token authentication mechanism that can be applied consistently across privileged API endpoints.

Primary deliverables:
- `code/backend/models/admin_token_auth/__init__.py`
- `code/backend/models/admin_token_auth/admin_token_auth_models.py`
- `code/backend/services/admin_token_auth/__init__.py`
- `code/backend/services/admin_token_auth/admin_token_auth_service.py`
- Admin-protected route module(s) for IP geolocation runtime operations
- Router wiring updates in `code/backend/api/router.py`
- Unit and integration tests for parsing, validation, guard behavior, and endpoint protection

Success criteria:
- Missing or invalid token always returns `401 Unauthorized` on protected endpoints.
- Any configured valid token grants access to protected admin operations.
- Token validation behavior is deterministic and reasoned (`ok`, `missing_config`, `missing_token`, `invalid_token`).
- All token-check logic exists in one reusable service, with no ad-hoc inline checks in route handlers.
- Token notes are supported for metadata/audit context without introducing RBAC complexity.

Constraints:
- Enforce architecture flow: `api -> apps -> services -> infra/models`.
- Keep DTOs in `models/admin_token_auth` only.
- Do not log or expose raw token values.
- Fail closed when `BGPX_ADMIN_TOKENS` is missing/empty for protected routes.
- Keep v1.1 scope to single privilege level (no role/scope matrix).

---

### 12.2 Stage 1 — Models

Scope:
- Create and finalize auth contract DTOs under `code/backend/models/admin_token_auth/`.

Required model groups:
1. Validation result model:
   - authorization boolean
   - reason enum/literal values (`ok`, `missing_config`, `missing_token`, `invalid_token`)
   - optional matched note metadata
2. Error model:
   - stable error code
   - user-safe message
3. Optional config-state model:
   - configured/not-configured observability signal

Acceptance checks:
- Models are imported from `models/admin_token_auth` in service/app/api layers.
- Reason taxonomy is fixed and consistently referenced.
- No auth DTO duplication in service or API modules.

---

### 12.3 Stage 2 — Service Core (`admin_token_auth_service.py`)

Scope:
- Implement the core token parsing and validation engine in `code/backend/services/admin_token_auth/admin_token_auth_service.py`.

Responsibilities:
1. Read raw configuration from `BGPX_ADMIN_TOKENS`.
2. Parse entries using supported separators (`;` and newline).
3. Parse `token|note` pairs where token is required and note is optional.
4. Ignore blank or malformed entries safely.
5. De-duplicate tokens while preserving deterministic behavior.
6. Validate provided request token against configured token set.
7. Perform constant-time token comparison in match loop.
8. Return model-based validation result with deterministic reason.

Failure/decision contract:
- Missing config -> `missing_config`
- Missing provided token -> `missing_token`
- Non-matching token -> `invalid_token`
- Match found -> `ok`

Acceptance checks:
- Parsing behavior is deterministic for mixed separators and mixed valid/invalid entries.
- Validation does not depend on endpoint-specific logic.
- No raw-token output in logs or exceptions.

---

### 12.4 Stage 3 — FastAPI Guard Contract

Scope:
- Expose a dependency-friendly guard entrypoint that API endpoints can reuse.

Responsibilities:
1. Receive token from `X-Admin-Token` header flow.
2. Invoke service validation contract.
3. Map non-authorized outcomes to standardized `401 Unauthorized` responses.
4. Keep decision mapping consistent across all protected routes.

Boundary rules:
- API handlers must consume this guard and must not implement custom token checks inline.
- Guard should remain auth-focused and not include domain action logic.

Acceptance checks:
- A single guard contract can be attached to any future admin endpoint.
- Protected route behavior is consistent regardless of domain (IP geo now, others later).

---

### 12.5 Stage 4 — Protected Admin Endpoint Integration

Scope:
- Apply guard to runtime admin IP-geolocation operations.

Target endpoints:
- `GET /api/admin/ip-geolocation/status`
- `POST /api/admin/ip-geolocation/reinitialize`
- `POST /api/admin/ip-geolocation/refresh-once`

Responsibilities:
1. Ensure each endpoint requires admin token guard.
2. Keep endpoint business logic in app/service layers.
3. Keep auth as cross-cutting concern through shared guard only.

Acceptance checks:
- All listed endpoints enforce admin token validation.
- Endpoint domain responses are unchanged except for access control behavior.

---

### 12.6 Stage 5 — Router and Wiring

Scope:
- Ensure protected admin route module is wired into global API router composition.

Responsibilities:
1. Register admin route module in `code/backend/api/router.py`.
2. Verify import paths and dependency composition remain clean.
3. Confirm no circular import introduced by auth service usage.

Acceptance checks:
- Admin routes are reachable through main router.
- App starts without wiring/import regressions.

---

### 12.7 Stage 6 — Unit Test Plan

Scope:
- Add focused unit tests for parsing and validation behavior.

Required unit coverage:
1. Empty/missing `BGPX_ADMIN_TOKENS` -> `missing_config`.
2. Missing request token -> `missing_token`.
3. Invalid request token -> `invalid_token`.
4. Valid token match -> `ok`.
5. Entry parsing with:
   - semicolon separators,
   - newline separators,
   - optional notes,
   - duplicate tokens,
   - blank/malformed entries.
6. Deterministic note association on successful match (metadata only).

Acceptance checks:
- Positive/negative paths are covered with deterministic assertions.
- Tests verify that no raw token values are surfaced in error payload contracts.

---

### 12.8 Stage 7 — Integration Test Plan

Scope:
- Validate end-to-end protected endpoint behavior via test client.

Required integration coverage:
1. Protected endpoint call without header -> `401`.
2. Protected endpoint with invalid token -> `401`.
3. Protected endpoint with any configured valid token -> success path.
4. Multi-token config behavior allows all configured valid tokens.
5. Missing/empty token config enforces fail-closed behavior for protected routes.

Acceptance checks:
- HTTP behavior exactly matches auth contract.
- Runtime admin actions are reachable only through valid token-authenticated requests.

---

### 12.9 Execution Order Checklist (Implementation Tracker)

- [ ] Stage 1 complete: models
- [ ] Stage 2 complete: service core
- [ ] Stage 3 complete: FastAPI guard contract
- [ ] Stage 4 complete: protected admin endpoint integration
- [ ] Stage 5 complete: router and wiring
- [ ] Stage 6 complete: unit tests
- [ ] Stage 7 complete: integration tests
