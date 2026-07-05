# FitnessOS

Personal fitness platform with a multi-agent backend (LangGraph), long-term memory, and modules for workouts, nutrition, swimming, analytics, and weekly reviews.

## Stack

- **Frontend:** Next.js 15, React, TypeScript, Tailwind, shadcn/ui
- **Backend:** FastAPI, SQLAlchemy, Alembic, Celery
- **Data:** PostgreSQL + pgvector, Redis
- **Auth:** Clerk (optional in dev via bearer token bypass)

## Local setup

```bash
git clone https://github.com/akBhatnagar/FitnessOS.git
cd FitnessOS

cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local
# fill in API keys and database URL

docker compose up -d

docker exec fitnessos-backend alembic upgrade head
docker exec fitnessos-backend python scripts/seed_dev_user.py
```

Frontend: http://localhost:3000  
API: http://localhost:8000

## Project layout

```
backend/          FastAPI app, agents, workers
frontend/         Next.js app
deploy/           nginx, systemd, deploy scripts
docker/           Dockerfiles
docs/             architecture and API notes
scripts/          db init helpers
```

## Agents

Coach orchestrates Memory, Knowledge, Workout, Nutrition, Swimming, Analytics, Scheduler, Event, and Reflection agents. Provider and model are configured via environment variables (`DEFAULT_LLM_PROVIDER`, etc.).

## Docs

| File | Topic |
|------|--------|
| [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) | System overview |
| [docs/DATABASE.md](./docs/DATABASE.md) | Schema |
| [docs/AGENTS.md](./docs/AGENTS.md) | Agent roles |
| [docs/API.md](./docs/API.md) | REST endpoints |
| [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) | Production deploy |
| [docs/MEMORY.md](./docs/MEMORY.md) | Memory layers |
| [docs/ROADMAP.md](./docs/ROADMAP.md) | Planned work |

## Deploy (VPS)

Set host and domain, then run from your machine:

```bash
export DEPLOY_HOST=your.server.ip
export DEPLOY_DOMAIN=fit.example.com
export DEPLOY_EMAIL=you@example.com
bash deploy/scripts/setup_server.sh   # once, on the server
bash deploy/scripts/first_deploy.sh   # first deploy
bash deploy/scripts/deploy.sh         # subsequent deploys
```

Copy `backend/.env.example` to `backend/.env.production` on the server and configure secrets there. Do not commit production env files.

## License

Private use — check repository settings before redistribution.
