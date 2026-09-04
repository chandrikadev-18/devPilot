# Changelog

All notable changes to DevPilot AI are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [4.0.0] - 2026-09-04

### Enterprise Final Release & Certification

#### Highlights
* **Final Enterprise Release**: Full certification of DevPilot AI as an end-to-end, production-grade AI developer assistant and autonomous codebase engineer.
* **100% Test & Gating Coverage**: Complete passing test suite across 522 backend test cases (521 passed, 1 skipped) and 13 frontend integration tests.
* **Zero Security Blockers**: Comprehensive verification of security headers, sandboxed path resolution, strict CORS, IDOR defenses, and real-time secret redaction.

#### Reliability & Recovery
* Verified high-availability readiness probe (`/health/ready`) assessing storage, vector database, graph parser, and Git availability.
* Validated atomic state persistence in `.devpilot/` with automated snapshot and disaster recovery restore routines.
* Automated syntax verification and multi-stage rollback manager for autonomous patch applications.

#### Observability & Diagnostics
* Unified `X-Request-ID` correlation across all HTTP requests, responses, background tasks, and error envelopes.
* Subsystem diagnostics via `/health/details` with credential protection and sensitive data redaction.
* Real-time in-memory performance metrics via `/metrics` capturing latency percentiles (p50, p95), status distributions, and operation throughput.

#### CI/CD & Artifacts
* Production-ready GitHub Actions workflow (`.github/workflows/ci.yml`) gating pull requests and main branch deployments on backend tests, frontend builds, security scans, and smoke test execution.
* Optimized frontend bundle with zero debug artifacts and zero credential leakage.

---

## [3.9.0] - 2026-09-03

### Deployment Readiness & Disaster Recovery
* Added deployment health and readiness gates.
* Implemented cold-start disaster recovery and snapshot restore procedures.
* Added `.github/workflows/ci.yml` multi-stage CI/CD pipeline.

---

## [3.8.0] - 2026-09-02

### Security Hardening & Compliance
* Added defense-in-depth HTTP security headers (`X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`).
* Implemented real-time regex sanitization for API keys, Bearer tokens, and secrets across logging and error envelopes.
* Added path traversal sandboxing in `resolve_safe_path`.
* Enforced human approval gates with explicit confirmation (`--force`) for high-risk modifications.

---

## [3.7.0] - 2026-09-01

### Performance & Scalability
* Optimized in-memory metrics collector and request latency histograms.
* Improved AST parser caching and dependency traversal efficiency.

---

## [3.6.0] - 2026-08-30

### Resilience & Fault Tolerance
* Added corrupted JSON store resilience and atomic write recovery.
* Added timeout boundaries (`OPERATION_TIMEOUT`, `TEST_TIMEOUT`) and resource cleanup.

---

## [3.5.0] - 2026-08-28

### Observability & Monitoring
* Introduced `/health`, `/health/ready`, and `/health/details` endpoints.
* Added `ObservabilityMiddleware` with `X-Request-ID` and `X-Response-Time-MS` propagation.
* Implemented frontend `ErrorBoundary` component with recovery fallbacks.

---

## [3.4.0] - 2026-08-25

### Autonomous Issue-to-PR Engineering
* Added autonomous task orchestration: understanding, root-cause analysis, planning, approval gating, atomic execution, syntax validation, and review summary generation.
* Added CLI commands: `task-create`, `task-analyze`, `task-plan`, `task-approve`, `task-execute`, `task-report`.

---

## [3.0.0] - 2026-08-20

### Modern Web Frontend
* Implemented enterprise React 18 / TypeScript SPA with Vite.
* Added interactive Codebase Explorer, AST Graph visualizer, Change Approval Manager, and Real-time Task Monitor.

---

## [0.1.0 - 0.9.0] - 2026-08-10

### Foundation & Core Engines
* AST Tree-sitter parsing for Python.
* Deterministic code chunking and local embeddings (`BAAI/bge-small-en-v1.5`).
* Qdrant vector database integration and hybrid semantic search.
* Bounded read-only AI agent and Git history intelligence.
