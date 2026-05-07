# BGPX Backend App Layer — Rules & Guidelines

This document defines standards for building and maintaining the **app layer** in `code/backend/apps`.

Audience:
- Human developers
- AI coding agents

Goal:
- Keep application code structured, testable, and aligned with clean layer boundaries.

---

## 1) Scope of the App Layer

The app layer is responsible for:
- Orchestrating feature use-cases
- Coordinating calls to service layer components
- Preparing stable outputs for API layer consumption

The app layer is **not** responsible for:
- API router aggregation concerns
- Infrastructure bootstrapping
- Heavy business rule implementation (belongs to services)
- Shared model/DTO ownership

---

## 2) Core Rule: Business Logic Lives in `services`

If there is business logic, it must be implemented in:
- `code/backend/services`

In such cases, the app layer must act as a:
- **Services orchestrator**

This means app modules should:
- Compose workflow across one or more services
- Handle use-case sequencing
- Transform service outputs into app-level response objects

This means app modules should **not**:
- Embed complex domain/business rules directly inside `*_app.py`
- Duplicate business logic that should be reusable in services
- Redefine shared DTOs/models locally (use `code/backend/models`)

---

## 3) Layer Boundaries & Dependency Direction

Expected dependency flow:

`api -> apps -> services -> models/infra`

Guidelines:
- API layer calls app layer
- App layer calls services/models as needed
- Keep dependency direction one-way (avoid upward coupling)

---

## 4) Folder & File Conventions

For each feature `X`:

- `apps/x/__init__.py`
- `apps/x/x_app.py`

Conventions:
- App module file suffix: `_app.py`
- Export main router/functions through `__init__.py` and `__all__`
- Keep naming lowercase and explicit

---

## 5) App Handler / Use-Case Design Rules

- Keep handlers focused and single-purpose
- Orchestrate behavior; do not overload endpoint handlers with business rules
- Use clear function names (`health_check`, `create_session`, `reconcile_prefixes`)
- Prefer small composable functions over large monolithic methods

---

## 6) Contracts and Return Shapes

- Return predictable, stable structures for the API layer
- Keep output keys intentional and consistent
- If output contracts evolve, update API and tests together
- If a model/DTO is shared or reusable, define it in `code/backend/models`
- Follow strict model typing from models layer and avoid multi-type fields unless explicitly justified

---

## 7) Validation & Error Handling

- Validate inputs as early as practical
- Raise explicit, meaningful errors
- Avoid leaking sensitive internals in error details
- Keep error behavior consistent across feature handlers

---

## 8) Async & Performance Guidance

- Use `async` when the call chain is async-aware
- Avoid blocking I/O in async flows
- Keep orchestration lightweight and delegate costly work to services

---

## 9) Testing Requirements (App Layer Focus)

For app behavior, prefer unit-focused coverage in:
- `code/backend/tests/unit/`

Minimum expectations for non-trivial app changes:
- Happy path behavior
- Core failure path behavior
- Service interaction assumptions (if mocked/stubbed)

Integration tests in `tests/integration` should validate API wiring, while unit tests should validate app orchestration behavior.

---

## 10) Docstrings, Type Hints, and Readability

Required:
- Type hints on public function signatures
- Concise docstrings for public handlers/use-case functions

Recommended:
- Keep modules short and navigable
- Prefer explicit imports
- Add short comments only where logic intent is not obvious

---

## 11) Contributor Checklist (Human + AI)

Before merging app-layer changes, verify:

- [ ] Feature module follows `apps/<feature>/<feature>_app.py` pattern
- [ ] Complex business logic is placed in `code/backend/services`
- [ ] App layer is orchestrating services, not replacing them
- [ ] Shared DTOs/models are defined in `code/backend/models` (not duplicated in apps)
- [ ] Type hints and docstrings are present
- [ ] Unit tests are added/updated for use-case behavior
- [ ] API integration tests are updated when contracts change

---

## 12) Anti-Patterns to Avoid

- Putting business/domain rules directly in API bridge files
- Implementing heavy business logic inside `*_app.py`
- Duplicating the same rule in multiple app modules
- Duplicating DTO/model contracts in app files instead of `code/backend/models`
- Returning inconsistent output shapes for similar operations
- Skipping tests for new orchestration logic

---

## 13) Quick Example (Health Feature Today)

Current simple feature:
- `apps/health/health_app.py` defines `GET /health`

As complexity grows:
1. Move business decisions to `services/health/*`
2. Keep `health_app.py` focused on orchestrating service calls
3. Keep API layer focused on route composition and transport concerns

This approach keeps features maintainable as the backend evolves.