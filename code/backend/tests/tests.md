# BGPX Backend Tests Layer — Rules & Guidelines

This document defines standards for building and maintaining the **tests layer** in `code/backend/tests`.

Audience:
- Human developers
- AI coding agents

Goal:
- Keep backend testing consistent, reliable, and aligned with architecture boundaries.

---

## 1) Hard Rule: Pytest Only

All backend tests must use **pytest**.

This is a strict, non-negotiable rule:
- Use `pytest` for unit tests
- Use `pytest` for integration tests
- Do not introduce alternative test frameworks/runners for backend tests

---

## 2) Test Layer Structure

- `code/backend/tests/unit/`
  - Fast, isolated tests for logic and contracts
- `code/backend/tests/integration/`
  - Multi-component tests validating real wiring/collaboration paths

---

## 3) Unit Testing Guidelines

Unit tests should:
- Focus on isolated behavior (services, models, parsers, pure app logic)
- Mock/stub external boundaries when needed
- Cover happy path + key failure/edge conditions
- Be deterministic and fast

Unit tests should avoid:
- Real external I/O dependencies unless explicitly required
- Coupling to unrelated components

---

## 4) Integration Testing Guidelines

Integration tests are **not limited to API tests**.

Integration tests **can** (not must) be added for any component with I/O or multi-part collaboration, including:
- API endpoint wiring and response contracts
- Service + infra adapter collaboration paths
- Infra adapter behavior with parser interaction
- Any other practical I/O integration path

Use integration tests when they add confidence for real component interaction boundaries.

---

## 5) Naming & Style Conventions

- File naming: `test_*.py`
- Test function naming: `test_<expected_behavior>()`
- Prefer Arrange/Act/Assert structure
- Keep assertions explicit and meaningful
- Keep tests independent (no ordering assumptions)

---

## 6) API Integration Test Pattern (Current Example)

Current repository example:
- `code/backend/tests/integration/test_health_api.py`

Pattern shown there:
- Build app instance
- Use `TestClient`
- Call endpoint
- Assert status code and response payload

---

## 7) Contract & Model Consistency in Tests

- Reuse shared models/DTO contracts from `code/backend/models` when relevant
- Validate strict typing expectations in tests
- Avoid creating duplicate ad-hoc contract shapes in multiple tests when shared contracts exist

---

## 8) Running Tests

Run all backend tests:

```bash
pytest code/backend/tests
```

Run only unit tests:

```bash
pytest code/backend/tests/unit
```

Run only integration tests:

```bash
pytest code/backend/tests/integration
```

---

## 9) Contributor Checklist (Human + AI)

Before merging, verify:

- [ ] All new/updated tests use **pytest**
- [ ] Unit tests were added/updated for logic changes
- [ ] Integration tests were considered for I/O or multi-component behavior
- [ ] Integration tests are scoped to meaningful collaboration boundaries
- [ ] Assertions are clear, deterministic, and contract-focused

---

## 10) Anti-Patterns to Avoid

- Using non-pytest frameworks for backend tests
- Over-relying on integration tests for logic that should be unit tested
- Writing flaky tests that depend on timing/order/shared state
- Embedding complex setup in every test instead of reusable fixtures
- Skipping failure/edge-case coverage for non-trivial behavior

This layer protects system quality — keep tests intentional, readable, and architecture-aware.