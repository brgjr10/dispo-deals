# QA Report: dispo-deals

## Summary
- Total findings: 12
- By severity: 
  - CRITICAL: 0
  - HIGH: 0
  - MEDIUM: 6
  - LOW: 5
  - INFO: 1

## Findings

### A. Security
- A1: MEDIUM - Missing security headers in API responses (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Content-Security-Policy, Strict-Transport-Security, Permissions-Policy)
  - Location: api_server.py, DashboardHandler
  - Description: The API server does not set common security headers, potentially exposing the application to various web vulnerabilities.
  - Reproduction: Send a request to any API endpoint and check the response headers.
  - Impact: Medium - could lead to XSS, clickjacking, MIME sniffing, etc.
  - Fix: Add a middleware or modify the handler to set these headers.

- A2: MEDIUM - Dockerfile runs as root (no USER directive)
  - Location: Dockerfile
  - Description: The container runs as the root user, which is a security risk if the container is compromised.
  - Reproduction: Check the Dockerfile for the absence of a USER directive.
  - Impact: Medium - violates principle of least privilege.
  - Fix: Add a USER directive to run as a non-root user.

- A3: LOW - CORS header set to wildcard (*)
  - Location: api_server.py, DashboardHandler
  - Description: The API server sets Access-Control-Allow-Origin: *, which may be too permissive for a production environment.
  - Reproduction: Check the response headers of any API endpoint.
  - Impact: Low - acceptable for internal tools, but not for public APIs.
  - Fix: Consider restricting to specific origins if the API is exposed externally.

### B. Performance
- B1: MEDIUM - Image URL/index caches have no eviction policy
  - Location: api_server.py, image_cache and index_cache dictionaries
  - Description: The caches grow indefinitely without eviction, potentially leading to high memory usage over time.
  - Reproduction: Monitor memory usage of the API server over time while serving requests.
  - Impact: Medium - could cause OOM in long-running instances.
  - Fix: Implement a cache with a maximum size (e.g., using functools.lru_cache or a custom LRU cache).

- B2: LOW - SQLite uses autocommit mode without explicit WAL/journal_mode configuration
  - Location: storage/sqlite.py
  - Description: The SQLite connection uses the default autocommit mode and does not set WAL mode, which could affect write performance and concurrency.
  - Reproduction: Check the storage/sqlite.py file for the connection setup.
  - Impact: Low - minimal for this application's scale.
  - Fix: Consider setting journal_mode to WAL for better concurrency.

### C. Reliability
- C1: MEDIUM - API server only handles KeyboardInterrupt, not SIGTERM
  - Location: main.py or api_server.py (where the server is started)
  - Description: The server does not handle SIGTERM, which is the standard signal for graceful shutdown in Docker/Kubernetes.
  - Reproduction: Send a SIGTERM to the process and observe that it does not shut down gracefully.
  - Impact: Medium - could lead to unclean shutdowns in containerized environments.
  - Fix: Add a signal handler for SIGTERM (and SIGINT) to shut down the server gracefully.

- C2: LOW - Null bytes in scripts/__init__.py and scripts/debug/__init__.py
  - Location: scripts/__init__.py (position 3 and 5), scripts/debug/__init__.py
  - Description: The files contain null bytes, which cause compile errors and may indicate file corruption.
  - Reproduction: Run `python -m compileall . -q` and observe errors on these two files.
  - Impact: Low - prevents bytecode compilation but does not affect runtime (if the files are empty and not imported).
  - Fix: Remove the null bytes or recreate the files.

- C3: MEDIUM - Duplicate resolve method in utils/strain_match.py
  - Location: utils/strain_match.py (lines ~397-428 and ~431-461)
  - Description: Two identical methods named `resolve` exist, which is redundant and confusing.
  - Reproduction: Open the file and see the two methods.
  - Impact: Medium - code maintainability issue.
  - Fix: Remove one of the duplicate methods.

### D. Functionality
- D1: INFO - All tests pass (163 passed, 0 failed)
  - Location: test suite
  - Description: The existing test suite passes, indicating good test coverage and functionality.
  - Reproduction: Run `python -m pytest tests -q`.
  - Impact: Informational - positive finding.
  - Fix: None needed.

- D2: INFO - API server starts and responds to endpoints
  - Location: api_server.py
  - Description: The API server starts on port 18101 (or 4040 as per config) and responds to /api/data, /api/menu, /dashboard.html.
  - Reproduction: Start the server and curl the endpoints.
  - Impact: Informational - positive finding.
  - Fix: None needed.

- D3: LOW - Path traversal on /api/image/<key> and /api/logo/<store_id> returns placeholder SVG (by design)
  - Location: api_server.py, image and logo endpoints
  - Description: Requests for non-existent keys return a placeholder SVG instead of a 404, which may be intentional but could be confused with a valid image.
  - Reproduction: Request a non-existent key and observe the placeholder SVG.
  - Impact: Low - by design, but could be made more explicit.
  - Fix: Consider returning a 404 for non-existent keys if the placeholder is not desired.

### E. Usability
- E1: LOW - Non-semantic use of role="button" on <div>
  - Location: dashboard.html
  - Description: A <div> is used with role="button", tabindex="0", and aria-label. While functional, it is not as accessible as a native button element.
  - Reproduction: Inspect the dashboard.html for the element.
  - Impact: Low - minor accessibility improvement possible.
  - Fix: Consider using a <button> element instead.

### F. Code Quality
- F1: MEDIUM - Many outdated dependencies
  - Location: requirements.txt
  - Description: Several dependencies have newer versions available (e.g., cryptography 48.0.0 → 50.0.2).
  - Reproduction: Run `pip list --outdated`.
  - Impact: Medium - missing out on security patches and performance improvements.
  - Fix: Update the dependencies in requirements.txt and test.

- F3: LOW - Deprecated datetime.utcnow() usage
  - Location: models.py, storage/sqlite.py, utils/strain_match.py
  - Description: The code uses datetime.utcnow(), which is deprecated in Python 3.12.
  - Reproduction: Search for datetime.utcnow() in the codebase.
  - Impact: Low - will cause warnings in future Python versions.
  - Fix: Replace with datetime.now(timezone.utc).

### G. Documentation
- G1: INFO - No documentation issues found (to be confirmed)
  - Location: N/A
  - Description: No issues found in documentation (README, comments, etc.) during the review.
  - Impact: Informational.
  - Fix: None needed.

### H. Configuration
- H1: LOW - No .dockerignore file
  - Location: Project root
  - Description: The absence of a .dockerignore file may lead to unnecessary files being copied into the Docker image.
  - Reproduction: Check for the presence of .dockerignore.
  - Impact: Low - slightly larger image size and potential security risk if sensitive files are included.
  - Fix: Add a .dockerignore file to exclude unnecessary files (e.g., .git, __pycache__, *.pyc, .env, etc.).

- H2: INFO - webhook_url configured via env var in docker-compose.yml and empty in config.yaml/.env
  - Location: docker-compose.yml, config.yaml, .env
  - Description: The webhook URL is configurable via environment variable, which is good practice. The default is empty, which may be intentional.
  - Reproduction: Check the files.
  - Impact: Informational - configuration is flexible.
  - Fix: None needed.

### I. Build and Deployment
- I1: MEDIUM - No CI/CD pipeline (no .github/ directory)
  - Location: Project root
  - Description: The project lacks automated testing and deployment pipelines.
  - Reproduction: Check for the presence of .github/ or other CI/CD configuration.
  - Impact: Medium - increases manual effort and risk of human error.
  - Fix: Set up a basic CI/CD pipeline (e.g., GitHub Actions) to run tests on push and pull request.

- I2: LOW - Dockerfile: no HEALTHCHECK
  - Location: Dockerfile
  - Description: The Dockerfile does not include a HEALTHCHECK directive, making it harder to monitor container health.
  - Reproduction: Check the Dockerfile.
  - Impact: Low - minimal for simple monitoring.
  - Fix: Add a HEALTHCHECK that checks the API endpoint.