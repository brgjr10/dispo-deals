# QA Consolidated Report — bug-qa-20261018

## 1. Campaign Summary

### 1.1 Totals by Severity (reconciled)

| Severity | Count |
|---|---|
| Critical | 3 |
| High | 4 |
| Medium | 9 |
| Low | 5 |
| Info | 9 |
| Total | 30 |

Per-repo reconciliation: counts taken directly from finding headings in `QA/reports/dispo-deals.md`. No discrepancy between agent self-report and report headings (single repo, single agent).

### 1.2 Per-Repo Health Table

| Repo | Commit | Branch | Build | Tests | Crit | High | Med | Low | Info | Health |
|---|---|---|---|---|---|---|---|---|---|---|
| dispo-deals | c72203b | master | Dockerfile/static (no build step) | 673 passed (env OK on UNC) | 3 | 4 | 9 | 5 | 9 | Fair — 2 Critical fixed in Phase 3, 1 Critical false-positive |

### 1.3 Cross-Repo Systemic Pattern Count

Single-repo campaign; no cross-repo patterns.

## 2. Executive Summary (for the owner)

Dispo-deals is a Python scraper + API dashboard (FastAPI-style handler over SQLite) with a strong existing test suite (673 passing). The Phase 1 QA pass found 30 findings across categories A–I. The two genuine Critical findings were fixed in Phase 3: (1) SSRF in the image downloader — it accepted arbitrary URLs with no private-IP blocking, now validates scheme, blocks private/reserved IPs, pins the connection to defeat DNS rebind, requires image Content-Type, and caps size at 10 MB; (2) a clean-clone breakage where tracked `scrapers/__init__.py` imported untracked `bigcartel`/`fourthwall` modules, now made opportunistic so `import scrapers` succeeds standalone. `.gitignore` was also extended to cover keys/certs/build outputs (`git add -A` threat model). One Critical (path traversal) and one Critical (add-store SSRF) were verified false-positives. All 684 tests (existing 673 + 11 new security tests) pass and `verify-scope.ps1` reports 0 dangling imports. Recommended to proceed to adversarial re-review before any push.

## 3. Consolidated Findings

Renumbered QA-001…QA-030, mapped from the per-repo report IDs.

### 3.1 CRITICAL

- **QA-001 (C-001) SSRF in image downloader/proxy** — `utils/images.py:download_image` accepted arbitrary URLs, no scheme/private-IP guard. FIXED in Phase 3 (scheme validation, private-IP blocking, connection pinning, content-type + 10 MB cap). Tests added.
- **QA-002 (C-002) Path traversal in static serving** — `api_server.py` static fallback uses `SimpleHTTPRequestHandler.translate_path`, which strips `..`/`.` components. Verified false-positive for traversal; repo-root-as-webroot exposure noted as INFO.
- **QA-003 (C-003) Unvalidated add-store URLs** — `api_server.py` `/api/add-store` never fetches the user URL; it extracts a slug and queries hardcoded dutchie.com GraphQL. Verified false-positive for SSRF.

### 3.2 HIGH

- **QA-004 (H-001) CSP includes `unsafe-inline`** — `api_server.py:SECURITY_HEADERS`. Not fixed (dashboard.html uses inline scripts; removing without nonces breaks it — product decision).
- **QA-005 (H-002) Image download no size limit** — addressed as part of QA-001 (10 MB cap + content-type check).
- **QA-006 (H-003) Prune guard solid** — verified correct by `tests/test_prune_products.py` (10 pass). Positive finding.
- **QA-007 (H-004) weekly_summaries PK prevents double-send** — `storage/sqlite.py`. Positive finding.

### 3.3 MEDIUM

- QA-008 (M-001) Uncaught exceptions could leak details — suspected, not fixed.
- QA-009 (M-002) Healthcheck hits heavy `/api/data` — design note, not fixed.
- QA-010 (M-003) No POST body size limit — deferred (Wave 3+).
- QA-011 (M-004) Image cache not integrity-validated on load — low risk, not fixed.
- QA-012 (M-005) Leafly client no circuit breaker — disabled by default, not fixed.
- QA-013 (M-006) Store interval throttle logic — positive, well-documented.
- QA-014 (M-007) Category alias performance — OK (dict lookups).
- QA-015 (M-008) SQLite datetime deprecation warnings — tech debt, not fixed.
- QA-016 (M-009) CSP in static HTML — suspected, not fixed.

### 3.4 LOW

- QA-017 (L-001) `.dockerignore` coverage — covers `.env`, `data/`, `cache/`, `*.db`; OK.
- QA-018 (L-002) Non-root Docker user — positive.
- QA-019 (L-003) Requirements loose pinning (`>=`) — tech debt, not fixed.
- QA-020 (L-004) Logo cache file permissions — low, not fixed.
- QA-021 (L-005) `output.txt` tracked (hygiene) — tracked AND gitignored; left as-is (removing from index is a history decision).

### 3.5 INFO (verified-clean categories & coverage notes)

- QA-022..QA-030: untracked files don't break tracked code (verify-scope 0 dangling imports), prune guard tested, dashboard a11y good (`aria-label`/`aria-expanded`, no `role="application"` regression), no committed secrets (`.env` gitignored+dockerignored), mojibake repair present, image content-hash caching, weekly-summaries atomic PK, full test suite passes.

### 3.6 Agent Corrections & False Premises

- C-002 and C-003 were reported as Critical in Phase 1 based on static reading; dynamic/code review confirmed they are false-positives (traversal neutralized by stdlib; add-store never fetches user URL). Reported as false-positives with evidence rather than silently dropped.

## 4. Cross-Repo Systemic Patterns

None (single-repo campaign).

## 5. Fix Wave Plan

All Wave 0–2 fixes for dispo-deals are complete in the working tree (see `QA/review/dispo-deals.md`). No remaining Wave 0–2 items. Wave 3–4 items (M-003 body size limit, H-001 CSP nonce migration, L-003 requirements pinning) are deferred pending owner prioritization.

## 6. Verification Strategy

- Build/type gates: Python only; `py_compile` on edited modules OK; no TS/vite.
- Environment blockers: None for Python — pytest runs reliably on UNC (684 passed). No Docker daemon (container runtime static-review only). No network-dependent live scraping run.
- Runtime probes: api_server starts on port 18100–18120 range (start one service at a time, stop after). Not re-run after fixes since changes are import/security guards exercised by unit tests.
- Frontend console-error bar: N/A (static HTML, no build step).
- Regression tests: `tests/test_image_security.py` (11 mocked, no network) + existing suite.
- Constraints: No push/commit; changes remain in working tree as diff for owner review.

## 7. Risks, Unknowns, and Questions for the owner

- Coverage gaps: CORS `Access-Control-Allow-Origin: '*'` on JSON API responses (present in `_send_json_error`/`send_api_data`); same-origin by default but worth confirming intent.
- Findings marked Strong/Suspected: C-002/C-003 resolved to false-positive; H-001/H-002/M-001/M-003 remain unexploited static observations.
- Open questions: (1) Approve H-001 CSP change knowing it may require dashboard nonce work? (2) Approve pinning CI action tags + `permissions:` in ci.yml/schema-docs.yml? (3) `output.txt` tracked — leave or remove from index (history decision)?
- No credential rotation needed (no committed secrets found).

## 8. Pre-Existing Uncommitted Work Warning

Do not touch these pre-existing uncommitted files (left as found):
- `scrapers/bigcartel.py`, `scrapers/fourthwall.py` (untracked new scraper modules)
- `scripts/category_aliases/`, `scripts/fix_existing_data.py`, `scripts/fix_live_db.py`
- `tests/test_prune_products.py`

## 9. Appendices

- Per-repo report index: `QA/reports/dispo-deals.md`
- Repo path map: GitHub `brgjr10/dispo-deals` <-> local `\\zimaserver\ZimaOS-HD\AppData\Projects\dispo-deals`
- Severity legend: Critical = active exploit path / data loss / clean-clone breakage; High = exploitable with conditions or weak defense; Medium = exploit unlikely or limited impact; Low = hygiene; Info = verified-clean / positive / hygiene note.
