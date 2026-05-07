# BGPX Backend Infra Layer — Rules & Guidelines

This document defines standards for building and maintaining the **infrastructure layer** in `code/backend/infra`.

Audience:
- Human developers
- AI coding agents

Goal:
- Isolate low-level and external-system concerns behind clean adapters, while preserving separation of concerns across the backend architecture.

---

## 1) Why the Infra Layer Exists

The infra layer exists to:
- Encapsulate low-level system operations (filesystem, OS/runtime details, network primitives, certificates, etc.)
- Encapsulate communication with external systems (APIs, SDKs, databases, queues, cloud services)
- Keep app/service layers focused on orchestration and business logic
- Enable easier replacement, mocking, and testing of external dependencies

---

## 2) Infra Layer Responsibilities

Infra components are responsible for:
- Implementing adapters/gateways for low-level or external dependencies
- Managing integration details (connection behavior, retries, timeouts, SDK specifics)
- Returning clean, normalized outputs to upper layers

---

## 3) What Infra Must Not Do

Infra components must **not**:
- Implement business/domain decision logic
- Perform app-level orchestration
- Handle API transport/routing concerns
- Define shared model/DTO ownership outside `code/backend/models`

---

## 4) Mandatory Rule: Parsing Must Be Delegated to Dedicated Parser Components

If an infra adapter receives raw payloads/data from low-level systems or external applications, parsing must be done in a **dedicated parser component**.

Parsing inside infra adapter methods is **not allowed**.

### Why this rule exists
- Preserves separation of concerns
- Keeps adapters focused on integration I/O responsibilities
- Makes parsing logic independently unit-testable
- Makes adapter+parser collaboration easier to integration-test

### Expected pattern
1. Infra adapter fetches raw data
2. Adapter calls a dedicated parser component/module
3. Parser returns normalized structures/models
4. Adapter returns parsed result to upper layers

---

## 5) Contracts and Models

- Shared models/DTOs must be defined in `code/backend/models`
- Infra should import and reuse these contracts
- Do not duplicate equivalent DTO/model definitions in infra modules
- Prefer strict single-type fields and avoid ambiguous multi-type fields unless explicitly justified

---

## 6) Dependency Direction

Expected architectural flow:

`api -> apps -> services -> infra`

Infra is an implementation boundary consumed by upper layers. It should not depend on API/app orchestration code.

---

## 7) Folder & Naming Conventions

Suggested feature-oriented organization:

- `infra/<feature>/`
- `infra/<feature>/<feature>_adapter.py`
- `infra/<feature>/<feature>_parser.py` (or dedicated parser module/package)
- `infra/<feature>/__init__.py`

Conventions:
- Use explicit names (`*_adapter.py`, `*_parser.py`)
- Keep adapter interfaces clear and stable
- Keep parser modules focused on data transformation only

---

## 8) Testing Expectations

Infra quality should be validated through:

1. **Unit tests (adapters)**
   - External dependencies mocked/stubbed
   - Adapter behavior and error mapping verified

2. **Unit tests (parsers)**
   - Raw input variants parsed into expected normalized output
   - Edge-case and malformed input handling verified

3. **Integration tests (adapter + parser)**
   - End-to-end collaboration path verified where practical

Use:
- `code/backend/tests/unit/`
- `code/backend/tests/integration/`

---

## 9) Contributor Checklist (Human + AI)

Before merging infra changes, verify:

- [ ] Infra code only handles integration/low-level concerns
- [ ] Business logic is not implemented in infra adapters
- [ ] Raw/external data parsing is delegated to dedicated parser components
- [ ] Shared DTOs/models come from `code/backend/models`
- [ ] Contracts remain strictly typed and clear
- [ ] Adapter tests and parser tests are added/updated

---

## 10) Anti-Patterns to Avoid

- Embedding domain/business rules in infra adapters
- Parsing raw external payloads directly in adapter methods
- Duplicating shared DTO/model contracts in infra files
- Returning inconsistent structures across adapters for similar contracts
- Coupling infra modules to API/app transport details

This layer should remain a clean boundary that isolates technical integration complexity from domain and application logic.