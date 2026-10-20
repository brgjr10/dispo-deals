# Repo QA Campaign Instructions

Campaign ID: bug-qa-20261018
Date: 2026-10-18

## Repo Table

| GitHub name | Local path | Remote | Branch | HEAD | Dirty | Notes |
|-------------|------------|--------|--------|------|-------|-------|
| dispo-deals  | \\zimaserver\ZimaOS-HD\AppData\Projects\dispo-deals | https://github.com/brgjr10/dispo-deals.git | master | c72203b | yes (7 untracked: scrapers/bigcartel.py, scrapers/fourthwall.py, scripts/category_aliases/, scripts/fix_existing_data.py, scripts/fix_live_db.py, tests/test_prune_products.py) | Python app (FastAPI API + scrapers + dashboard HTML). 673 pytest passed. |

## Phase rules
- Phase 0: setup done. Toolchain check: pytest runs fine over UNC (673 passed). node --check not applicable; tsc/pytest OK on UNC here.
- Phase 1: per-repo test agents write QA/reports/<github-name>.md
- Phase 2: consolidation only after all reports in
- Phase 3: fixes only on approval, local edits only, never push/commit

## Structural traps noted
- No obvious orphaned build output (no dist/ with index.html loading bundle; dashboard.html present as static). 
- Tests exist and pass.
- No committed secrets obvious from quick scan.

## Toolchain
- Python: pytest works on UNC (verified). compileall/node checks if needed.
- No Docker daemon; runtime probes limited to local python/http server.
- Ports: 18100-18120

