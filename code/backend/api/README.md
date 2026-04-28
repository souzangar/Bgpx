# BGPX Backend API Layer — Rules & Guidelines

This document defines standards for building and maintaining the **API layer** in `code/backend/api`.

Audience:
- Human developers
- AI coding agents

Goal:
- Keep API code consistent, testable, and easy to extend as new features are added.

---

## 1) Scope of the API Layer

The API layer is responsible for:
- Defining API routers and route composition
- Organizing feature router boundaries
- Exposing application capabilities under stable HTTP paths

The API layer is **not** responsible for:
- Business logic implementation
- Data access logic
- Infrastructure concerns
- Shared model/DTO ownership

Business behavior should live in `apps/*`/`services/*`, while shared models and DTOs must live in `models/*`. API modules focus on routing and HTTP contracts.

---

## 2) Current Routing Architecture

Current request path composition:

1. `main.py` includes top-level API router with prefix `/api`
2. `api/router.py` aggregates feature API routers
3. `api/<feature>/<feature>_api.py` bridges API layer to `apps/<feature>` router
4. `apps/<feature>/*` defines actual endpoint handlers

Example in repository:
- `main.py` -> `api/router.py` -> `api/health/health_api.py` -> `apps/health/health_app.py`

---

## 3) Folder & File Conventions

For each new feature `X`:

- API package:
  - `api/x/__init__.py`
  - `api/x/x_api.py`
- App package:
  - `apps/x/__init__.py`
  - `apps/x/x_app.py`

Conventions:
- API module file suffix: `_api.py`
- App module file suffix: `_app.py`
- Export routers via `__init__.py` and `__all__`
- Keep package/module names lowercase and explicit

---

## 4) Router Composition Rules

When adding a new endpoint feature:

1. Create app router in `apps/<feature>/<feature>_app.py`
2. Create API bridge router in `api/<feature>/<feature>_api.py`
3. Include app router inside feature API router
4. Include feature API router in `api/router.py`

Do:
- Keep API routers small and compositional
- Use `APIRouter()` per module
- Keep imports explicit and local to layer boundaries

Avoid:
- Registering all endpoints directly in `main.py`
- Mixing business logic directly inside API bridge modules

---

## 5) Endpoint Design Guidelines

- Use clear and stable route paths
- Use plural resources where appropriate (for future extensibility)
- Keep tag names consistent per feature (e.g., `tags=["health"]`)
- Return predictable JSON payloads
- Reuse DTOs/models from `code/backend/models` instead of redefining contracts in API files

Response conventions:
- Success responses should have clear key names
- Error responses should be structured and consistent across endpoints
- Choose status codes intentionally (`200`, `201`, `204`, `400`, `404`, `409`, `422`, `500`, etc.)

---

## 6) Type Hints, Docstrings, and Readability

Required:
- Add type hints for function signatures
- Add concise docstrings to public endpoint handlers
- Keep function names descriptive (`health_check`, `list_routes`, etc.)
- Prefer request/response models with strict field types from `code/backend/models`

Recommended:
- Keep handlers focused and short
- Move complex logic to app/service layers
- Prefer explicit imports over wildcard imports
- Avoid ambiguous multi-type model fields unless explicitly justified by the domain contract

---

## 7) Validation & Error Handling

- Validate request data using FastAPI/Pydantic models when applicable
- Avoid silent failures
- Raise explicit HTTP errors when needed (`HTTPException` with meaningful details)
- Do not leak sensitive internal details in error responses

---

## 8) Testing Requirements

For each newly exposed API route, add/update tests under:
- `code/backend/tests/integration/`

Minimum expectations:
- Route is reachable via expected API prefix
- Success status code and payload are verified
- Core failure/validation path is tested when relevant

Pattern example:
- Existing `test_health_api.py` validates `GET /api/health` wiring and payload

---

## 9) Contributor Checklist (Human + AI)

Before merging API changes, verify:

- [ ] Feature router exists in `apps/<feature>`
- [ ] API bridge exists in `api/<feature>`
- [ ] Router is included in `api/router.py`
- [ ] Route paths include the global `/api` prefix through `main.py`
- [ ] Shared request/response models are defined in `code/backend/models`
- [ ] Shared models avoid ambiguous multi-type fields unless explicitly justified
- [ ] Type hints and docstrings are present
- [ ] Integration tests are added/updated
- [ ] Endpoint responses and status codes are intentional and documented in code

---

## 10) Anti-Patterns to Avoid

- Putting business logic directly into API aggregation files
- Skipping tests for new routes
- Returning inconsistent payload shapes for similar operations
- Adding feature routes without registering them in `api/router.py`
- Creating unclear module names or mixing unrelated features in one file

---

## 11) Quick Example (Feature Wiring)

1. Define endpoint handler in `apps/example/example_app.py`
2. Include it from `api/example/example_api.py`
3. Register `example_api.router` in `api/router.py`
4. Test through `/api/...` path using integration tests

This keeps routing clean and feature growth predictable.