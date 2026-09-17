# Deployment

## Architecture

- Frontend: Vercel, rooted at `frontend/`.
- API: Render, running `backend/app/main.py`.
- Database: Supabase PostgreSQL.
- Scheduled jobs: GitHub Actions.

## Render

Build command:

```text
pip install -r backend/requirements.txt
```

Start command:

```text
cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Health checks:

- Liveness: `/api/health`
- Readiness: `/api/health/ready`

Required environment variables:

- `DATABASE_URL`
- `CORS_ALLOW_ORIGINS`
- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`
- `ANTHROPIC_API_KEY` (optional unless explanations are enabled)
- `ADMIN_SECRET` (required for admin endpoints)

Never commit values for these variables.

## Vercel

Set `NEXT_PUBLIC_API_BASE_URL` to:

```text
https://invest-feed-mvp.onrender.com/api
```

Use the same value for Production and Preview unless a separate preview API is intentionally deployed.

## Supabase

Use the pooler or direct PostgreSQL connection string as `DATABASE_URL`. Apply schema changes through a versioned migration process before changing the production service.

## Post-deploy smoke test

```text
GET /api/health
GET /api/health/ready
GET /api/opportunities
GET /api/portfolio
```

A successful deployment requires HTTP 200 for all four endpoints and no CORS errors from the Vercel origin.
