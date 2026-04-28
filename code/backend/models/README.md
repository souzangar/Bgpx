# BGPX Backend Models Layer — Rules & Guidelines

This document defines standards for building and maintaining the **models layer** in `code/backend/models`.

Audience:
- Human developers
- AI coding agents

Goal:
- Keep all shared models/DTOs consistent across API, app, service, and infra layers.

---

## 1) Why the Models Layer Exists

The models layer is the **single source of truth** for system data contracts.

It exists to:
- Prevent duplicated model definitions across layers
- Keep validation and field typing consistent everywhere
- Make contracts easier to evolve and test safely

---

## 2) What Belongs in `code/backend/models`

- Domain models and value-like structures used across features
- DTOs for inter-layer communication
- Shared request/response contract schemas used by multiple layers

If API/App/Service/Infra needs a model or DTO, define it here first.

---

## 3) What Must Not Be in Models Layer

- Business logic and orchestration behavior
- FastAPI route wiring/transport concerns
- Infra adapter implementation details

Models should describe **data shape and validation**, not feature workflow.

---

## 4) System-Wide Rule: No Layer-Local Duplicate Models

Do not redefine the same conceptual model in:
- `api/*`
- `apps/*`
- `services/*`
- `infra/*`

Instead:
- Define shared models/DTOs in `code/backend/models`
- Import and use them from other layers

---

## 5) Strict Typing Rule (Important)

Avoid multi-type fields/unions as much as possible.

Example to avoid (unless truly unavoidable):
- `name: str | bool`
- `value: int | str | None`

Preferred:
- One clear, strict type per field
- Explicit optionality only when needed (e.g., `str | None` for nullable values)

Why:
- Stronger validation
- Safer contracts
- Less ambiguous behavior across layers

If polymorphism is required, use explicit/discriminated model patterns rather than ambiguous mixed primitive types.

---

## 6) Naming & Organization Conventions

Suggested feature-oriented structure:

- `models/<feature>/`
- `models/<feature>/<feature>_models.py`
- `models/<feature>/__init__.py`

Conventions:
- Use explicit model names (`HealthStatusDto`, `SessionCreateInput`, etc.)
- Keep naming stable and intention-revealing
- Avoid vague names like `Data`, `Info`, `TempModel`

---

## 7) Validation & Contract Evolution

- Define validation close to model fields
- Keep default values intentional and explicit
- When contracts change, update all affected layers and tests together
- Prefer additive, backward-compatible changes when possible

---

## 8) Testing Expectations

For non-trivial model changes, add/update tests in:
- `code/backend/tests/unit/`

Minimum expectations:
- Field validation behavior
- Serialization/deserialization behavior (if applicable)
- Edge-case inputs for critical contracts

---

## 9) Contributor Checklist (Human + AI)

Before merging model changes, verify:

- [ ] Shared model/DTO is defined in `code/backend/models`
- [ ] No duplicate equivalent model was introduced in other layers
- [ ] Field types are strict and clear
- [ ] Multi-type fields are avoided unless explicitly justified
- [ ] Validation rules match domain expectations
- [ ] Unit tests cover key validation and contract behavior

---

## 10) Anti-Patterns to Avoid

- Duplicating the same DTO in multiple layers
- Using ambiguous mixed primitive union types by default
- Embedding business behavior in model classes
- Evolving contracts silently without updating dependent layers/tests

This layer is the contract backbone of the backend — keep it clean and authoritative.