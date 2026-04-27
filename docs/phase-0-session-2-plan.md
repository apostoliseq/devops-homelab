# Phase 1 Completion Plan — App, Docker & Local Dev

## Context

The project is a URL shortener used as a learning vehicle for a full DevOps pipeline.
Phase 1 goal: get all six services running locally with `docker compose`, fully tested,
and merged into `develop` via a pull request.

**Current branch:** `feature/phase1-app-and-docker`
**What already exists:** Git scaffold, docs, bootstrap.sh, and `app/api/app.py` (Flask API, 240 lines).
**What is missing:** worker, frontend, Dockerfiles, docker-compose, env template, tests, local-dev script.

---

## Prerequisites

- `scripts/bootstrap.sh` has been run (Docker + hadolint + flake8 installed).
- User is on the `feature/phase1-app-and-docker` branch.
- `app/api/app.py` and `app/api/requirements.txt` are already written.

---

## Implementation Order

Steps are ordered by dependency. Later steps depend on earlier ones being present.

### Step 1 — Worker service (`app/worker/`)

**Why first:** the worker has no dependencies on the frontend or Dockerfiles; writing it now
keeps code and infra concerns separate.

1. Create `app/worker/requirements.txt`:
   ```
   pika==1.3.2
   psycopg2-binary==2.9.10
   ```
2. Create `app/worker/worker.py` — consumes `click_events` queue, writes rows to the
   `analytics` table in Postgres. Must handle reconnection on RabbitMQ restart.

---

### Step 2 — Frontend (`app/frontend/static/index.html`)

Single HTML page (no build step needed):
- `<form>` that POSTs to `/shorten` via `fetch()`
- Displays the returned short URL
- Pure HTML/JS, no framework

---

### Step 3 — Dockerfiles (3 files)

All three follow these rules (enforced by hadolint):
- Pin exact base image version (no `latest`)
- Non-root user
- `COPY` only what's needed

| File | Base image | Notes |
|---|---|---|
| `app/api/Dockerfile` | `python:3.12-slim` | Multi-stage: build deps in builder, copy to slim runtime |
| `app/worker/Dockerfile` | `python:3.12-slim` | Same pattern as API |
| `app/frontend/Dockerfile` | `nginx:1.27-alpine` | Single stage; copy `static/` to Nginx html dir |

---

### Step 4 — `.dockerignore` files (3 files)

One per service directory. Each excludes: `__pycache__/`, `*.pyc`, `.git`, `tests/`, `*.md`.

---

### Step 5 — `.env.example`

Documents every environment variable the stack needs. Real `.env` is git-ignored.

```
DB_HOST=postgres
DB_NAME=urlshortener
DB_USER=appuser
DB_PASS=changeme
REDIS_HOST=redis
RABBITMQ_HOST=rabbitmq
RABBITMQ_USER=guest
RABBITMQ_PASS=guest
BASE_URL=http://localhost
```

---

### Step 6 — `docker-compose.yml`

Wire all 6 services. Key requirements:
- Named volumes for `postgres` and `redis` data
- `healthcheck` on postgres, redis, rabbitmq
- `depends_on: condition: service_healthy` so API and worker only start when dependencies are ready
- All credentials from `${VAR}` references (loaded from `.env`)
- Expose only what's needed externally: port 80 (frontend)

Service map:

| Service | Image | Ports exposed to host |
|---|---|---|
| `frontend` | custom build | 80→80 |
| `api` | custom build | 5000 (internal only, fronted by nginx proxy) |
| `worker` | custom build | none |
| `postgres` | `postgres:16-alpine` | none |
| `redis` | `redis:7-alpine` | none |
| `rabbitmq` | `rabbitmq:3.13-management-alpine` | 15672 (management UI) |

The frontend Nginx config will proxy `/shorten` and `/<code>` to the API container.

---

### Step 7 — Unit tests (`app/api/tests/test_api.py`)

Tests use `pytest` and `unittest.mock` — no real DB or Redis needed.

Cover:
- `POST /shorten` with valid URL → 201 + JSON body
- `POST /shorten` missing `url` field → 400
- `GET /<existing_code>` → 302 redirect
- `GET /<missing_code>` → 404
- `GET /health` → 200

---

### Step 8 — `scripts/local-dev.sh`

Idempotent automation script. Accepts `--down` flag.

Default (up) flow:
1. Copy `.env.example` to `.env` if `.env` missing
2. `docker compose build`
3. `docker compose up -d`
4. Poll `docker compose ps` until all services healthy (max 60s)
5. Smoke test: POST to `/shorten`, GET the returned short URL, assert 302

Teardown (`--down`): `docker compose down -v`

---

### Step 9 — Lint, test, commit, PR

```bash
hadolint app/api/Dockerfile app/worker/Dockerfile app/frontend/Dockerfile
flake8 app/api/app.py app/worker/worker.py
pytest app/api/tests/
./scripts/local-dev.sh        # full smoke test
git add -p                    # stage changes deliberately
git commit -m "feat: complete phase 1 — worker, frontend, dockerfiles, compose, tests"
gh pr create --base develop
```

---

## Risks & Things That Could Go Wrong

| Risk | Mitigation |
|---|---|
| RabbitMQ slow to start → worker crash-loops | Worker uses retry loop with backoff on connection failure |
| Postgres not ready → API 500 on first request | `depends_on: service_healthy` + healthcheck in compose |
| Port 80 already in use on VM | `local-dev.sh` checks with `ss -tlnp` before starting |
| hadolint warnings block commit | Fix warnings as Dockerfiles are written, not after |
| `flake8` line-length issues in app.py | Add `# noqa` only where line can't be shortened; fix everything else |

---

## Resource Impact

| Component | Estimated RAM |
|---|---|
| PostgreSQL 16 | ~200 MB |
| Redis 7 | ~50 MB |
| RabbitMQ 3.13 | ~200 MB |
| Flask API | ~100 MB |
| Worker | ~80 MB |
| Nginx frontend | ~30 MB |
| **Total** | **~660 MB** |

Well within the 16 GB available.

---

## Verification (Definition of Done)

Phase 1 is complete when all of the following pass:

- [ ] `hadolint` — zero warnings on all 3 Dockerfiles
- [ ] `flake8` — zero warnings on all Python files
- [ ] `pytest app/api/tests/` — all tests green
- [ ] `docker compose up -d` — all 6 containers start
- [ ] `docker compose ps` — all services show `healthy`
- [ ] `./scripts/local-dev.sh` — prints "All smoke tests passed"
- [ ] Browser at `http://<vm-ip>` shows the URL shortener UI
- [ ] Submitting a URL returns a working short link that redirects
- [ ] PR merged into `develop` on GitHub
