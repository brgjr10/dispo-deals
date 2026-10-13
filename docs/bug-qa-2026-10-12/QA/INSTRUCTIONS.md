# QA Campaign Instructions — dispo-deals

Generated: 2026-10-12

## Repo Table

| GitHub Name | Local Path | Commit | Branch | Baseline Dirty Files |
|-------------|------------|--------|--------|---------------------|
| dispo-deals | F:\Documents\dispo-deals | 9aa64bb | master | 0 (clean) |

GitHub: https://github.com/brgjr10/dispo-deals

## Architecture Summary

A Python-based dispensary deals notifier that:
- Scrapes Dutchie (GraphQL) and Klutch (HTML) storefronts on a schedule (default: every 6 hours)
- Persists seen deals and weekly menu snapshots to SQLite (`data/dispo_deals.db`)
- Sends rich Discord/Slack webhook notifications with store logos and product images
- Imports strain profiles from Leafly (search + detail pages) and attaches to products
- Serves a dashboard via `api_server.py` (ThreadingHTTPServer on port 4040) with deal insight charts (Chart.js vendored locally)
- Deployable via Docker Compose with FlareSolverr for Cloudflare bypass

**Entrypoints:**
- `main.py` — CLI with `--once`, `--dry-run`, `--import-strains`, `--enrich-strains`, `--test-webhook`
- `api_server.py` — Dashboard API server

**External services:** Dutchie GraphQL API, Klutch website, Leafly consumer API, Discord/Slack webhook
**Storage:** SQLite (seen_deals, weekly_snapshots, strains, strain_misses, store_logos, product_images)
**Build pipeline:** None (pure Python). Dockerfile installs deps from requirements.txt.
**Test coverage:** 163 pytest tests covering models, categories, strains, charts, sidebar, full menu, API, Dutchie HTML parsing, cloudscraper, embeds.

## Phase Rules (from repo-qa skill)

1. **Never push.** No git push/commit/stash. Leave all changes in working tree.
2. **Never fabricate runtime results.** If not executed, mark finding `Strong` or `Suspected`.
3. **Never print real secrets.** Reference finding ID instead.
4. **Never revert pre-existing uncommitted work.** Capture `git status --porcelain` at start/end.
5. **House standards** (codebase-memory.md): Extend don't rewrite; match style; reliability > readability > performance; never silently fail.

## Toolchain Verification (ENVIRONMENT.md)

- pytest on UNC path: **verified functional** (ran test_models.py → 7 passed)
- Python 3.14.6 available
- No Docker daemon available (static review only for Dockerfile/compose)
- No Electron runtime (N/A)

## Structural Traps to Check First

1. **Clean clone build:** Check for tracked files importing untracked files, `requirements.txt` scripts with untracked sources, tests importing untracked `conftest`.
2. **Committed build output orphaning source:** Check if `dashboard.html` loads only a prebuilt bundle while source files are unreferenced.
3. **Secrets reachable from build:** Check `.dockerignore`, `.env` committed, `*.db`, baked-in API keys, `.npmrc` tokens.

## Test Taxonomy (must hunt in ALL categories A–I)

A. Build & dependency health  
B. Correctness & logic  
C. Input validation & injection  
D. Security & secrets  
E. Frontend / UI  
F. Persistence & data integrity  
G. Performance & resources  
H. Operational  
I. Cross-cutting / subprojects

## Dynamic Testing Required

- Run existing test suites (`pytest tests -q`)
- `python -m compileall .` on source tree
- Import the app and probe routes with Flask test client (api_server.py uses stdlib HTTPServer)
- Node: `node --check` on any JS files
- Probe SSRF defenses with alternate encodings

## Report Output

Write exactly one file: `QA/reports/dispo-deals.md` following the skeleton in TEST_AGENT.md §Step 5.

Final message: ≤15 lines with counts by severity, top 3 findings, what you could not test, and the report file path.