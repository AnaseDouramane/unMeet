# Deployment and operations

Nothing in this repository deploys itself, and nothing here has been deployed. Every step that
creates paid resources or touches DNS needs an explicit decision by the owner.

## Target layout (from the plan)

| Part | Where | Notes |
|------|-------|-------|
| Frontend (`frontend/`) | Vercel | set `NEXT_PUBLIC_API_BASE_URL` and the privacy variables per environment |
| API | container host (Fly.io / Railway / Render) | `python -m scripts.run_api`, `/health` as health check |
| Worker | same image, second process | `python -m scripts.run_worker` (one instance only: cursors are shared) |
| Postgres + pgvector | Supabase | run `python -m scripts.init_db` as the release step |
| Scheduled jobs | the host's cron | `scripts.deliver_alerts` (every 10 min), `scripts.run_analysis` (daily), `scripts.enforce_retention` (daily) |

Use two environments (staging and production) with separate databases and secrets. Never point
staging at the production database.

## Image

`Dockerfile` builds one image for every role. It has not been built in CI yet and it still
ships the CPU torch wheel (large): switching embeddings to a hosted API (M1.3) removes
torch/transformers. Local check with the compose profile:

```bash
docker compose --profile app up --build   # postgres, migrations, API on :8000, worker
```

## Configuration

Secrets live in the platform, never in the image or the repo. Minimum for production:

| Variable | Why |
|----------|-----|
| `UNMEET_ENV=production` | writes fail closed without an API key |
| `UNMEET_API_KEY` | protects writes, audit, usage and privacy endpoints |
| `DATABASE_URL` | Postgres with pgvector |
| `API_CORS_ORIGINS` | the frontend origin(s) |
| `TRUST_PROXY_HEADERS=true` | only behind a proxy you control, so rate limits see client IPs |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `CLASSIFIER_BACKEND=llm` | classification |
| `LLM_INPUT_USD_PER_MTOK`, `LLM_OUTPUT_USD_PER_MTOK` | cost reporting |
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | Reddit OAuth |
| `LOG_FORMAT=json` | structured logs (the image sets it) |

## Monitoring

- **Liveness**: `GET /health`.
- **Ingestion stalls**: point an uptime monitor at `GET /health/ingestion`; it returns 503 and
  names the source when one has not produced data for `INGESTION_STALE_AFTER_SECONDS`.
  The worker also logs `ingestion stalled` and per-source failures with backoff.
- **LLM cost**: `GET /api/v1/usage/llm` or `python -m scripts.llm_cost_report [YYYY-MM-DD]`.
- **Audit**: `GET /api/v1/audit` lists who changed what.
- **Errors**: logs are one JSON object per line with a `request_id`; forward them to the
  platform's log drain. To add an error tracker, initialise it at the top of `scripts/run_api.py`
  and `scripts/run_worker.py` (not added yet to avoid choosing a vendor).

## Rate limiting caveat

Limits are enforced in process memory per instance. With several API instances the effective
limit is multiplied; move the limiter to Redis before scaling horizontally.
