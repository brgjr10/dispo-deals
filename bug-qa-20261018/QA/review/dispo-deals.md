# Fix Log — dispo-deals

| Field | Value |
|---|---|
| Local path | \\zimaserver\ZimaOS-HD\AppData\Projects\dispo-deals |
| Baseline commit | c72203b (master) |
| Baseline dirty files | M scrapers/__init__.py, M utils/images.py, M .gitignore ; ?? scrapers/bigcartel.py, ?? scrapers/fourthwall.py, ?? scripts/category_aliases/, ?? scripts/fix_existing_data.py, ?? scripts/fix_live_db.py, ?? tests/test_prune_products.py (pre-existing untracked, left untouched) |
| Files changed | 3 tracked (.gitignore, scrapers/__init__.py, utils/images.py) + 1 new test (tests/test_image_security.py) |
| Findings fixed | 2 (C-001, Theme-11 clean-clone import) + .gitignore coverage |
| Findings partial | 0 |
| Findings not fixed | 6 (see Findings not fixed) |
| `git diff --stat` at end | see below |

## Wave 0 — Secrets & CRITICAL

### C-001 — Critical — SSRF in image downloader/proxy (`download_image`)
- **Status:** FIXED
- **Files changed:** `utils/images.py`
- **What changed:** Rewrote `download_image` so it (1) only allows http/https schemes, (2) resolves the host once and rejects it if any resolved address is private/reserved/link-local/multicast (127/8, 10/8, 172.16/12, 192.168/16, 169.254/16, ::1/128, fc00::/7, etc.), (3) pins the connection to the first validated public IP by rewriting the URL netloc to that IP while keeping the original host as the `Host` header — defeating DNS rebind, (4) requires an `image/` Content-Type, and (5) caps the download at 10 MB streamed (also resolves H-002 unbounded image download). All rejection paths log why.
- **Test added:** `tests/test_image_security.py` (11 mocked tests — no network): blocks localhost/link-local/RFC1918/IPv6-localhost, blocks file:///ftp:// schemes, allows public image, blocks non-image Content-Type, blocks oversized image, verifies connection is pinned to the validated IP with original Host header, verifies unresolvable host returns None, verifies mixed public+private resolution is blocked.
- **Verify with:** `python -m pytest -q tests/test_image_security.py` (11 passed) and full suite `python -m pytest -q` (684 passed).
- **Notes:** `download_image` is called by `api_server._resolve_logo` (configured logo URLs) and `api_server._resolve_image` (deal image URLs from the deal set). Both keep the bytes-or-None contract, so callers are unchanged.

## Wave 1 — Security

(nothing beyond C-001; see Findings not fixed for H-001/H-002/M-003 dispositions)

## Wave 2 — Build & data integrity

### Theme-11 — Critical — Clean-clone build does not build (`scrapers/__init__.py` imports untracked modules)
- **Status:** FIXED
- **Files changed:** `scrapers/__init__.py`
- **What changed:** Tracked `scrapers/__init__.py` hard-imported `scrapers.bigcartel` and `scrapers.fourthwall`, which are untracked modules present only in the dirty working tree. On a clean clone `import scrapers` crashed with ModuleNotFoundError. Made both imports opportunistic (try/except ImportError, logging why), set them to `None` when absent, and made `__all__` and the `create_scraper` registry conditional so `import scrapers` always succeeds and `create_scraper` raises a clear "Unknown scraper" for missing scrapers instead of crashing at import time.
- **Test added:** none new (behavior covered by existing scraper tests; verified clean-clone simulation: `import scrapers` succeeds without bigcartel/fourthwall, BigCartelScraper/FourthwallScraper are None, create_scraper callable).
- **Verify with:** `python -c "import scrapers"` (OK), `python -m pytest -q tests/test_full_menu.py tests/test_magento.py tests/test_new_stores.py tests/test_scrape_throttle.py` (53 passed).
- **Notes:** Verified with `scripts/verify-scope.ps1`: dangling imports from untracked modules = 0. The untracked bigcartel/fourthwall files are pre-existing uncommitted work and were left untouched (never revert pre-existing work).

### .gitignore coverage — Wave 2/4 — `git add -A` threat model
- **Status:** FIXED
- **Files changed:** `.gitignore`
- **What changed:** Added a "Secrets and certificates" block (`*.key`, `*.crt`, `*.pem`, `*.p12`) and a "Build outputs" block (`dist/`, `build/`, `node_modules/`, `*.sqlite3`, `project.json`) so a careless `git add -A` cannot sweep in keys/certs/build artifacts. `.env`, `data/`, `cache/`, `*.db`, `*.sqlite` were already covered.
- **Test added:** none (config file).
- **Verify with:** `scripts/verify-scope.ps1` section 4 now reports 39 patterns with no key/cert/node_modules/dist/build/*.sqlite3/project.json findings.

## Wave 3 — Correctness / UX / perf

(none assigned)

## Wave 4 — Code health

(covered by .gitignore above)

## Findings not fixed

| Source ID | Severity | Why not |
|---|---|---|
| C-002 | Critical | Path-traversal claim is mitigated: the static fallback uses `SimpleHTTPRequestHandler.do_GET`, whose `translate_path` normalizes and strips `..`/`.` components, so `../` cannot escape the project root. Documented as FALSE-POSITIVE for traversal; the repo-root-as-webroot exposure is noted as INFO (hardening: restrict static serving to an explicit dir) left as a product decision. |
| C-003 | Critical | add-store SSRF claim is a FALSE-POSITIVE: `receive_add_store`/`add_store` never fetches the user-supplied URL. `_extract_dutchie_slug` pulls a `stores/<slug>` segment, then `resolve_dutchie_store` queries only hardcoded `https://api.dutchie.com/graphql` / `https://dutchie.com/graphql`. No server-side fetch of the attacker URL exists. |
| H-001 | High | CSP `unsafe-inline` retained because `dashboard.html` uses inline scripts/event handlers; removing it without nonces would break the dashboard. Changing to nonce/hash-based CSP is a product/UX decision (NEEDS-BRODIE if it affects published behavior). |
| H-002 | High | Addressed as part of C-001: `download_image` now caps downloads at 10 MB and requires `image/` Content-Type. |
| M-003 | Medium | No request body size limit on POST endpoints. Deferred: requires sizing middleware on `do_POST`; not in Wave 0–2 scope. |
| CI floating action tags | (verify-scope note) | `.github/workflows/ci.yml` and `schema-docs.yml` use `actions/checkout@v4` (floating tag) with no `permissions:` block. Pin by SHA and add `permissions:` — a CI-infra change, deferred. |

## NEW defects introduced by these changes

None. `download_image` preserves the bytes-or-None contract for both callers (`_resolve_logo`, `_resolve_image`); `scrapers/__init__.py` is backward-compatible when bigcartel/fourthwall are present (existing 53 scraper tests pass); `.gitignore` only affects untracked files.

## Verification run

- `python -m py_compile utils\images.py scrapers\__init__.py` — OK
- `python -m pytest -q tests/test_image_security.py` — 11 passed
- `python -m pytest -q tests/test_full_menu.py tests/test_magento.py tests/test_new_stores.py tests/test_scrape_throttle.py` — 53 passed
- `python -m pytest -q` (full suite) — 684 passed, 0 failed
- `scripts/verify-scope.ps1` — 0 dangling imports, no committed secrets, .gitignore gaps closed
- Clean-clone simulation (worktree lacking bigcartel/fourthwall): `import scrapers` OK, BigCartelScraper/FourthwallScraper = None, create_scraper callable

`git diff --stat` (tracked changes only; `tests/test_image_security.py` is new/untracked):
```
 .gitignore           |  13 +++++
 scrapers/__init__.py |  28 ++++++-- 
 utils/images.py      | 143 ++++++++++++...
 3 files changed, 175 insertions(+), 9 deletions(-)
```

All changes remain in the working tree as a diff. Nothing committed, pushed, or history-rewritten.
