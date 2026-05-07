# BGPX Backend Services Layer — Rules & Guidelines

This document defines standards for building and maintaining the **services layer** in `code/backend/services`.

Audience:
- Human developers
- AI coding agents

Goal:
- Centralize business logic in one clean layer that is reusable, testable, and independent of transport/framework details.

---

## 1) Why the Services Layer Exists

The services layer exists to:
- Keep business/domain logic out of API and app orchestration modules
- Prevent logic duplication across features
- Improve maintainability and long-term scalability
- Make business behavior easy to test in isolation

Without a services layer, business logic tends to spread across handlers and routers, making the system harder to reason about.

---

## 2) Services Layer Responsibilities

Services are responsible for:
- Implementing business rules and domain decisions
- Performing policy checks and validations related to domain behavior
- Executing reusable use-case logic
- Returning clear domain/app-level outputs to the app layer

Services are **not** responsible for:
- FastAPI routing or HTTP transport concerns
- API response formatting details
- App-level orchestration across multiple endpoints
- Defining shared model/DTO ownership outside `code/backend/models`

---

## 3) Architectural Position

Expected dependency flow:

`api -> apps -> services -> models/infra`

Layer roles:
- `api`: transport and route composition
- `apps`: use-case orchestration
- `services`: business logic execution
- `infra`: low-level adapters and external integrations

---

## 4) Mandatory Boundary Rule: External/Low-Level Access Goes Through `infra`

If any service needs to interact with:
- Low-level systems (filesystem, OS primitives, sockets, certificates, process/runtime details)
- External components outside our software (third-party APIs, DB clients/drivers, queues, cloud SDKs)

it **must go through `code/backend/infra`**.

### Why this rule is mandatory
- Preserves separation of concerns in the domain design model
- Keeps service logic vendor-agnostic and testable
- Avoids tight coupling to implementation details
- Simplifies replacement/mocking of external dependencies

### Practical expectation
- Services depend on abstractions/contracts
- `infra` provides concrete adapter implementations

---

## 5) Allowed vs Forbidden Dependencies in Services

Allowed:
- Domain models/value objects
- Other service modules (when logically justified)
- Interfaces/abstractions representing infrastructure capabilities
- Models/DTOs imported from `code/backend/models`

Forbidden:
- Direct FastAPI request/response handling in business logic
- Direct low-level I/O or external SDK usage from services
- Importing transport-layer modules from `api/*`
- Duplicating shared DTO/model contracts in service-local modules

---

## 6) Service Design Guidelines

- Keep services focused and cohesive
- Prefer small, composable units over monolith classes/functions
- Use explicit function names that describe business intent
- Keep side effects controlled and visible
- Favor deterministic behavior where possible

---

## 7) Inputs, Outputs, and Errors

- Define clear service inputs and outputs (typed where possible)
- Keep returned structures stable and intentional
- Raise explicit, meaningful errors for business rule violations
- Do not leak infrastructure internals through service errors
- Reuse models/DTOs from `code/backend/models` for shared contracts
- Prefer strict single-type fields and avoid multi-type fields unless explicitly justified

---

## 8) Async, I/O, and Performance

- Use async patterns consistently when upstream/downstream flow is async
- Do not hide blocking operations inside async service paths
- Delegate I/O implementation details to infra adapters

---

## 9) Folder & Naming Conventions

Suggested feature-oriented organization:

- `services/<feature>/`
- `services/<feature>/<feature>_service.py`
- `services/<feature>/__init__.py`

Conventions:
- Use clear module names based on domain intent
- Keep public service entry points explicit
- Avoid ambiguous utility dumping grounds

---

## 10) Testing Requirements (Unit-First)

Service logic should primarily be covered with unit tests under:
- `code/backend/tests/unit/`

Minimum expectations for non-trivial service changes:
- Happy path behavior
- Key business rule branches
- Failure and edge-case paths
- Adapter interaction assumptions (mocked/stubbed)

---

## 11) Contributor Checklist (Human + AI)

Before merging service-layer changes, verify:

- [ ] Business logic is implemented in `code/backend/services`
- [ ] App layer remains an orchestrator, not a business-rules container
- [ ] Any external/low-level interaction is routed through `code/backend/infra`
- [ ] Shared DTOs/models are defined in `code/backend/models` (not duplicated in services)
- [ ] Service contracts are typed and documented
- [ ] Multi-type model fields are avoided unless explicitly justified
- [ ] Unit tests cover core business paths and failure behavior
- [ ] New dependencies do not violate layer boundaries

---

## 12) Anti-Patterns to Avoid

- Embedding business rules directly in `api/*` or `apps/*`
- Calling third-party APIs directly from service logic without infra adapters
- Mixing transport concerns with domain logic
- Duplicating the same rule across multiple services
- Duplicating DTO/model contracts in services instead of `code/backend/models`
- Defaulting to ambiguous multi-type fields in shared contracts
- Returning inconsistent output structures for equivalent operations

---

## 13) Example Collaboration Pattern

1. API receives request and routes it
2. App layer orchestrates use-case flow
3. Service executes business logic
4. If needed, service uses an infra adapter for low-level/external access
5. Result flows back to app, then to API response

This pattern keeps responsibilities explicit and the architecture clean as the codebase grows.