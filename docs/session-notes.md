# Session Notes

---

## Session 2 — 2026-04-27

**Branch:** `feature/phase1-app-and-docker`
**Goal:** Complete all Phase 1 deliverables — worker, frontend, Dockerfiles, Compose, tests.

### What Was Built

| File | Description |
|------|-------------|
| `app/worker/worker.py` | RabbitMQ consumer. Reads from `click_events` queue, writes to `analytics` table. Includes retry loop with backoff so it survives RabbitMQ slow starts. |
| `app/worker/requirements.txt` | `pika==1.3.2`, `psycopg2-binary==2.9.10` |
| `app/frontend/static/index.html` | Single-page HTML/JS frontend. Uses `fetch()` to POST to `/shorten`, displays result. No framework. |
| `app/frontend/nginx.conf` | Nginx config. Serves static files; proxies `/shorten` and `/<code>` to `api:5000` by service name. |
| `app/api/Dockerfile` | Multi-stage build: builder stage installs deps with `--prefix`, runtime stage copies only the installed packages. Non-root `appuser`. Runs via gunicorn. |
| `app/worker/Dockerfile` | Same multi-stage pattern as API. Runs `worker.py` directly. |
| `app/frontend/Dockerfile` | Single-stage `nginx:1.27-alpine`. Copies `nginx.conf` and `static/`. |
| `infra/postgres/Dockerfile` | Thin wrapper over `postgres:16-alpine`. Version pinned; ready for init scripts. |
| `infra/redis/Dockerfile` | Thin wrapper over `redis:7-alpine`. Ready for custom `redis.conf`. |
| `infra/rabbitmq/Dockerfile` | Thin wrapper over `rabbitmq:3.13-management-alpine`. Ready for plugin enablement. |
| `app/api/.dockerignore` | Excludes `__pycache__/`, `*.pyc`, `.git`, `tests/`, `*.md` from build context. |
| `app/worker/.dockerignore` | Same as API. |
| `app/frontend/.dockerignore` | Same pattern. |
| `infra/postgres/.dockerignore` | Excludes `*.md`, `.git`. |
| `infra/redis/.dockerignore` | Same. |
| `infra/rabbitmq/.dockerignore` | Same. |
| `.env.example` | Documents all required environment variables. Real `.env` is git-ignored. |
| `docker-compose.yml` | All 6 services. Healthchecks on postgres/redis/rabbitmq. API and worker use `depends_on: condition: service_healthy`. Named volumes for postgres and redis. Only port 80 (frontend) and 15672 (RabbitMQ management UI) exposed to host. |
| `app/api/tests/conftest.py` | Adds `app/api/` to `sys.path` so pytest can find `app.py`. |
| `app/api/tests/test_api.py` | 7 unit tests. All pass. No real DB/Redis/RabbitMQ needed — dependencies are mocked with `unittest.mock`. |

### Bugs Fixed During This Session

**`init_db()` not called under gunicorn**
- Root cause: `init_db()` was inside `if __name__ == "__main__":`, which gunicorn never executes (it imports the module instead of running it as a script).
- Fix: moved `init_db()` to module level so it runs on import regardless of how the app is started.
- File: `app/api/app.py`

**`gunicorn` missing from requirements**
- Root cause: `app/api/Dockerfile` runs `gunicorn` as `CMD` but it wasn't listed in `requirements.txt`, so the image would fail to start.
- Fix: added `gunicorn==22.0.0` to `app/api/requirements.txt`.

### Architecture Decisions Made

**All 6 services have Dockerfiles (including postgres, redis, rabbitmq)**
- Even infrastructure services have a thin `FROM <image>:<tag>` Dockerfile in `infra/`.
- Rationale: version pinning is explicit and visible in a file you own, not buried in docker-compose.yml. Each Dockerfile is also a ready extension point (postgres init scripts, custom redis.conf, RabbitMQ plugins) that won't require restructuring later.

**Multi-stage builds for API and worker**
- Builder stage installs Python dependencies with `--prefix=/install`. Runtime stage copies only those installed packages into a fresh base image.
- Rationale: keeps the production image free of pip's download cache and build-time tools, reducing image size and attack surface.

**Port exposure policy**
- Only port 80 (Nginx frontend) is exposed to the host. Port 5000 (API) is internal only — reachable by the Nginx proxy via Docker's internal network but not from outside the host.
- Port 15672 (RabbitMQ management UI) is exposed for local debugging.

### Ad-hoc Commands Run (Now Captured in bootstrap.sh)

The following commands were run interactively during this session. They have since been added to `scripts/bootstrap.sh` so the environment is reproducible:

```bash
pipx install pytest
pipx inject pytest flask gunicorn psycopg2-binary redis pika prometheus-client
```

**Why `pipx inject`:** pytest runs in its own isolated virtualenv managed by pipx. The app's runtime libraries (flask, psycopg2, etc.) must be present in that same venv for `import app` to succeed in tests. `pipx inject` adds packages to an existing pipx venv without creating a new one.

### What's Next

1. `scripts/local-dev.sh` — build, start stack, poll until healthy, smoke test, teardown flag
2. Final lint pass: `hadolint` all Dockerfiles, `flake8` all Python files
3. Commit all changes with conventional commit message
4. Open PR: `feature/phase1-app-and-docker` → `develop`

---

## Session 1 — 2026-04-21

**Branch:** `feature/phase1-app-and-docker`
**Phase:** 1 — Git, Docker, and the Application

### What Was Built

- All prerequisites installed via `scripts/bootstrap.sh` (Docker, hadolint, flake8)
- GitHub repo created; `main` and `develop` branches pushed
- Feature branch `feature/phase1-app-and-docker` created from `develop`
- Directory skeleton created
- `app/api/requirements.txt` written
- `app/api/app.py` written — Flask API with `/shorten`, `/<code>`, `/health`, `/metrics`

### Reference: API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/shorten` | Accept `{"url": "..."}`, return `{"short_url": "...", "code": "..."}` |
| GET | `/<short_code>` | Redirect to original URL (Redis cache → Postgres fallback) |
| GET | `/health` | Returns `{"status": "ok"}` — used by Docker/K8s healthchecks |
| GET | `/metrics` | Prometheus metrics endpoint (scraped in Phase 5) |
