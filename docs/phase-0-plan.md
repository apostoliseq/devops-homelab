# Phase 1 Plan: Git, Docker, and the Application

## Context

The project is at ground zero — the repository exists with only a CLAUDE.md and project plan. Nothing has been built yet: no application code, no Dockerfiles, no scripts, no directory structure. Phase 1 is the foundation everything else rests on. Without working, containerized application components, Phases 2–7 cannot begin. The goal of this phase is to produce a running full-stack application locally via Docker Compose, prove each component talks to the others, and establish the Git workflow habits that carry through the entire project.

---

## Prerequisites

- [x] Git installed
- [x] Docker Engine installed — `docker ps` confirmed working
- [x] Docker Compose plugin installed — v5.1.3
- [x] `hadolint` installed — v2.12.0
- [x] `flake8` installed — v7.3.0
- [x] `scripts/bootstrap.sh` written and committed (captures all of the above)
- [x] GitHub repository created with `main` and `develop` branches
- [x] Local repo renamed from `master` → `main`, remote connected, branches pushed
- [x] Feature branch `feature/phase1-app-and-docker` created

None of these require Kubernetes — K8s is Phase 2.

---

## Resource Impact

Phase 1 runs entirely in Docker Compose on the local machine. No Kubernetes, no Jenkins.

| Component | Estimated RAM |
|---|---|
| PostgreSQL | ~200 MB |
| Redis | ~50 MB |
| RabbitMQ | ~200 MB |
| API (Flask) | ~100 MB |
| Worker | ~80 MB |
| Frontend (Nginx) | ~30 MB |
| **Total** | **~660 MB** |

Well within the 16 GB budget. Docker itself uses ~200–300 MB overhead.

---

## Risks and Things That Could Go Wrong

1. **RabbitMQ / Postgres startup order** — the API and worker start before the database/queue is ready. Mitigated with `healthcheck` + `depends_on: condition: service_healthy` in Compose.
2. **Port conflicts** — if the VM already has Postgres or Nginx running, ports 5432/80 will be taken. Check with `ss -tlnp` before starting.
3. **pip dependency hell** — avoid installing Python packages system-wide. Use a virtual environment inside each Docker image; never install with pip on the host.
4. **Non-idempotent scripts** — the local-dev.sh script must handle the case where containers are already running (call `docker compose down` before `up`).
5. **Secrets in git** — DB passwords and RabbitMQ credentials must go in a `.env` file that is listed in `.gitignore`. Never hardcoded in Dockerfiles or Compose files.
6. **`latest` image tags** — forbidden per conventions. Every base image must have an explicit version tag (e.g., `python:3.12-slim`, `postgres:16-alpine`).

---

## Directory Structure to Create

```
devops-homelab/
├── app/
│   ├── frontend/
│   │   ├── Dockerfile
│   │   ├── .dockerignore
│   │   └── static/
│   │       └── index.html
│   ├── api/
│   │   ├── Dockerfile
│   │   ├── .dockerignore
│   │   ├── requirements.txt
│   │   ├── app.py
│   │   └── tests/
│   │       └── test_api.py
│   └── worker/
│       ├── Dockerfile
│       ├── .dockerignore
│       ├── requirements.txt
│       └── worker.py
├── scripts/
│   └── local-dev.sh
├── docker-compose.yml
├── .env.example          ← committed; .env is gitignored
└── README.md
```

---

## Step-by-Step Implementation Order

### Step 1: Git and GitHub Setup ← NEXT
1. Rename local branch: `git branch -m master main`
2. On GitHub: create repo `devops-homelab` (no auto-init — local repo already has commits).
3. Connect and push: `git remote add origin https://github.com/apostoliseq/devops-homelab.git && git push -u origin main`
4. Create and push develop: `git checkout -b develop && git push -u origin develop`
5. Create Phase 1 feature branch: `git checkout -b feature/phase1-app-and-docker develop`

### Step 2: Create the Directory Skeleton
Create the directory tree above. Start with empty placeholder files so the structure is visible in git.

### Step 3: Write the Application Code

**API (Flask)** — `app/api/app.py`:
- `POST /shorten` — accepts a long URL, generates a short code, stores in Postgres, publishes an analytics event to RabbitMQ, returns the short URL.
- `GET /<short_code>` — looks up in Redis first (cache hit), then Postgres (cache miss, writes to Redis), returns a redirect.
- `/health` — returns HTTP 200, used by Compose healthchecks.
- Expose Prometheus metrics via `prometheus_client` (needed in Phase 5, cheap to add now).

**Worker** — `app/worker/worker.py`:
- Connects to RabbitMQ, consumes analytics events from a queue.
- Writes click events (short_code, timestamp, IP) to a Postgres `analytics` table.
- Reconnects on failure (RabbitMQ may not be immediately ready).

**Frontend** — `app/frontend/static/index.html`:
- A single HTML page with a form: input a long URL, click "Shorten", display the result.
- Uses plain fetch() to call the API — no frameworks.

### Step 4: Write Dockerfiles

Rules for every Dockerfile:
- Pin the base image version (no `latest`).
- Multi-stage build for the API and worker (build stage installs deps, final stage is a clean slim image).
- Run as a non-root user (`RUN adduser --disabled-password appuser && USER appuser`).
- Add a `.dockerignore` excluding `__pycache__`, `.git`, `*.pyc`, `tests/`.

### Step 5: Write docker-compose.yml

Services: `frontend`, `api`, `worker`, `postgres`, `redis`, `rabbitmq`.

Key points:
- All credentials come from `.env` (never hardcoded).
- `postgres`, `redis`, and `rabbitmq` have `healthcheck` blocks.
- `api` and `worker` have `depends_on: condition: service_healthy` on their dependencies.
- Postgres and Redis have named volumes so data survives `docker compose down`.
- API and frontend communicate via the Docker Compose internal network (not localhost).

### Step 6: Write scripts/local-dev.sh

Stages:
1. Build all images (`docker compose build`).
2. Start the stack (`docker compose up -d`).
3. Wait for the API healthcheck to pass (loop + curl `/health`).
4. Run a smoke test: POST a URL to `/shorten`, GET the short code, verify redirect.
5. Print success/failure summary.
6. Optionally accept a `--down` flag to tear everything down.

### Step 7: Write Unit Tests

`app/api/tests/test_api.py`:
- Test `POST /shorten` with a valid URL — expect 201 + JSON with `short_url`.
- Test `POST /shorten` with an invalid URL — expect 400.
- Test `GET /<code>` for an existing code — expect 302 redirect.
- Test `GET /<code>` for a missing code — expect 404.
- Use pytest + `unittest.mock` to stub out Postgres and Redis (pure unit tests, no real DB).

### Step 8: Verify Linting

Run before committing:
```bash
hadolint app/api/Dockerfile
hadolint app/worker/Dockerfile
hadolint app/frontend/Dockerfile
flake8 app/api/app.py app/worker/worker.py
```

### Step 9: Open a Pull Request

- Push `feature/phase1-app-and-docker` to GitHub.
- Open a PR from `feature/phase1-app-and-docker` → `develop`.
- Write a PR description summarising what was built and what each component does.
- Merge (no-ff) after review.
- Tag the state on `main` once `develop` is stable: `git tag v0.1.0`.

---

## Verification: How to Confirm Phase 1 is Complete

1. `docker compose up -d` starts all 6 containers with no errors.
2. `docker compose ps` shows all services as healthy.
3. `./scripts/local-dev.sh` prints "All smoke tests passed."
4. Browsing to `http://<vm-ip>:80` shows the URL shortener UI.
5. Submitting a URL in the UI returns a working short link.
6. Clicking the short link redirects to the original URL.
7. `flake8` and `hadolint` produce zero warnings.
8. `pytest app/api/tests/` — all tests pass.
9. GitHub shows at least one merged PR into `develop`.

---

## What the User Learns in This Phase

- How Docker images are built and why multi-stage builds save space.
- Why containers run as non-root (principle of least privilege).
- What Docker Compose does — it's just a way to define and wire multiple containers together.
- Why secrets go in `.env` and never in code.
- How service dependencies and healthchecks prevent startup race conditions.
- GitFlow: the habit of working in feature branches and merging via PRs.
- Why linting tools (flake8, hadolint) exist and what they catch.
