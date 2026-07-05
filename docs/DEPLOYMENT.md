# FitnessOS Deployment Guide

## Architecture

```
Internet
    │
    ├──► Vercel (Next.js frontend)
    │        │
    └──► Railway/Render (FastAPI + Celery)
                 │
                 ├──► Supabase (PostgreSQL + pgvector + Storage)
                 └──► Redis Cloud (Celery broker)
```

---

## Frontend: Vercel

1. Push to GitHub
2. Connect repository to Vercel
3. Set environment variables in Vercel dashboard:

```
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=
CLERK_SECRET_KEY=
NEXT_PUBLIC_API_URL=https://your-api.railway.app
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
```

4. Deploy. Vercel handles CI/CD automatically.

---

## Backend: Railway

1. Create a new Railway project
2. Add a service from GitHub repo (select `backend/` as root)
3. Set environment variables from `backend/.env.example`
4. Railway auto-deploys on push to `main`

**Start command**:
```
uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2
```

**Celery worker** (separate Railway service):
```
celery -A app.workers.celery_app worker --loglevel=info
```

**Celery beat** (separate Railway service):
```
celery -A app.workers.celery_app beat --loglevel=info
```

---

## Database: Supabase

1. Create a Supabase project
2. Enable pgvector: `CREATE EXTENSION IF NOT EXISTS vector;`
3. Run migrations: `alembic upgrade head`
4. Copy the connection string to `DATABASE_URL`

---

## Redis: Redis Cloud (or Upstash)

1. Create a Redis instance
2. Copy the connection URL to `REDIS_URL`, `CELERY_BROKER_URL`

---

## Production Checklist

- [ ] `APP_ENV=production` in environment
- [ ] `DEBUG=false`
- [ ] Strong `SECRET_KEY` (32+ random characters)
- [ ] All API keys configured
- [ ] Database migrations applied
- [ ] pgvector extension enabled
- [ ] Celery worker running
- [ ] Celery beat running
- [ ] Health check endpoints responding
- [ ] CORS origins restricted to production domain
- [ ] Rate limiting active
