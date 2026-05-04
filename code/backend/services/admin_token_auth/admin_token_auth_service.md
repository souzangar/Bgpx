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
  - admin CLI (runtime client),
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

Current admin CLI process is separate from backend process memory.
To operate on **existing runtime state**, CLI must call protected runtime endpoints.

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

## 5) Token Strategy (v1)

### 5.1 Token source
- Environment variable: `BGPX_ADMIN_TOKEN`

### 5.2 Transport
- Request header: `X-Admin-Token`

### 5.3 Validation rules
1. If env token is missing/blank -> fail closed for protected routes.
2. If request token missing -> `401 Unauthorized`.
3. If token mismatch -> `401 Unauthorized`.
4. Compare using constant-time comparison (`hmac.compare_digest`).

### 5.4 Logging rules
- Never log raw token values.
- Log only decision-level metadata (missing/invalid/accepted).

---

## 6) Models Design (`models/admin_token_auth`)

Planned DTOs:

1. `AdminTokenValidationResultModel`
   - `is_authorized: bool`
   - `reason: Literal["ok", "missing_config", "missing_token", "invalid_token"]`

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

1. Load configured admin token from env.
2. Validate incoming token.
3. Return model-based validation result.
4. Provide FastAPI-friendly guard/dependency wrapper.

Planned method examples:
- `get_configured_admin_token()`
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

### 8.2 CLI behavior

CLI becomes runtime client:
- sends `X-Admin-Token` header,
- token taken from `--token` or `BGPX_ADMIN_TOKEN` env,
- base URL from `--base-url` (default localhost backend URL).

### 8.3 Reuse for future domains

Any future private API (ping/traceroute/maintenance/etc.) reuses the same guard.

---

## 9) Security Notes

1. Prefer binding backend admin exposure to trusted network interfaces.
2. Use TLS in non-local deployments.
3. Rotate `BGPX_ADMIN_TOKEN` via deployment/env management.
4. Consider adding scope-based tokens in later phase.

---

## 10) Implementation Action Plan

1. Create models under `models/admin_token_auth`.
2. Implement `services/admin_token_auth/admin_token_auth_service.py`.
3. Add protected admin IP-geo API routes.
4. Wire routes into API router.
5. Refactor CLI to call runtime endpoints with token header.
6. Add unit tests for service + route auth guard + CLI HTTP path.
7. Add integration checks for protected endpoint behavior.

---

## 11) Acceptance Criteria

1. Protected endpoints reject missing/invalid token with `401`.
2. Valid token allows runtime admin actions.
3. CLI controls existing runtime (not local isolated state) via endpoint calls.
4. Token validation logic exists in one reusable service (no duplicated checks).
5. Tests cover positive and negative auth paths.

---

## 12) Out of Scope (v1)

- Multi-token user registry
- Role-based access control (RBAC)
- External identity provider integration
- Persistent credential store

These can be added later without breaking v1 route contracts.
