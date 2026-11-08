# unMeet

**Pain-signal engine for go-to-market teams.** unMeet reads public communities (Hacker News,
Reddit, GitHub Issues), finds people describing a problem, asking for a tool or complaining about
a product, and turns each post into an actionable signal: intent, the author's exact words,
products mentioned and severity. Signals are clustered into recurring problems, tracked over
time, filtered by saved topics and pushed to tools like Clay through webhooks or CSV.

```text
"Every Monday I spend three hours cleaning duplicate contacts in HubSpot. Anything that fixes this?"
  → intent: solution_search · products: HubSpot · severity: 2
  → quote: "I spend three hours cleaning duplicate contacts" (verified verbatim in the source)
  → cluster: "Sales teams clean duplicate CRM contacts by hand" (rising)
```

## How it works

```mermaid
flowchart LR
  A[Hacker News · Reddit OAuth · GitHub] --> B[Clean + dedupe]
  B --> C{Already classified?}
  C -- yes --> X[skip]
  C -- no --> D[LLM signal extraction<br/>concurrent, schema-validated]
  D -- problem --> E[MiniLM embeddings]
  D -- not a problem --> F[(archive)]
  E --> G[(Postgres + pgvector)]
  G --> H[L2 + UMAP + HDBSCAN]
  H --> I[LLM problem statements<br/>+ trend vs previous run]
  G --> J[Signals API · CSV]
  G --> K[Tracked topics → webhooks]
```

Engineering choices worth knowing:

- **Grounded quotes.** The LLM must return a verbatim excerpt; quotes that do not appear in the
  source text are discarded, so no fabricated words are ever attributed to a real person.
- **Provider-agnostic LLM layer.** One OpenAI-compatible client (Groq by default, or OpenAI,
  OpenRouter, vLLM, Ollama) with schema-constrained JSON, strict validation, and retries that
  honour `Retry-After`. A local Qwen3 backend remains available with no API key.
- **Incremental and idempotent.** Unchanged items are never re-classified; edited ones are.
  Classification runs in ordered concurrent batches and keeps partial progress on failure.
- **Clustering that works on sentence embeddings.** Vectors are normalised and projected with
  UMAP before HDBSCAN; the preprocessing is part of each run's signature so trends only compare
  compatible runs.
- **Safe outbound webhooks.** https only, no redirects, and the destination is re-resolved at
  send time to block private and metadata addresses (SSRF / DNS rebinding).
- **Honest evaluation.** F1 is reported with a bootstrap 95% interval on a labeled sample of real
  data, not on synthetic sentences; see [docs/EVALUATION.md](docs/EVALUATION.md).

## Quick start

To try the product by hand (one command to set up, a digest and a feedback sheet for a manual test with
founders), follow [docs/PROTOTYPE.md](docs/PROTOTYPE.md).

```bash
cp .env.example .env            # set LLM_API_KEY (e.g. a Groq key) and UNMEET_API_KEY
docker compose up -d            # Postgres 16 + pgvector
python -m pip install -r requirements-dev.txt
python -m scripts.init_db       # applies Alembic migrations
python -m scripts.run_unmeet    # ingest → classify → embed → cluster → trends
python -m scripts.deliver_alerts  # push new signals of tracked topics to their webhooks
python -m scripts.run_worker      # or: keep polling every source every 10 minutes (cursors, backoff)
```

Multi-tenant accounts, roles, plans and login are described in [docs/SAAS.md](docs/SAAS.md); the launch plan is in [docs/LAUNCH.md](docs/LAUNCH.md).

API and UI:

```bash
uvicorn app.api.app:create_app --factory --reload
cd frontend && npm install && cp .env.example .env.local && npm run dev
```

Re-run only clustering, labeling and trends on stored data with `python -m scripts.run_analysis`.

## Configuration

| Variable | Purpose |
|----------|---------|
| `INGESTION_SOURCES` | `hackernews,hackernews_search,stackexchange,reddit,github` in execution order |
| `STACKEXCHANGE_SITE`, `STACKEXCHANGE_QUERIES`, `STACKEXCHANGE_KEY` | for `stackexchange`: site slug, `;`-separated keyword queries (empty = all new questions), optional API key for a higher quota |
| `HACKERNEWS_SEARCHES` | for `hackernews_search`: `tag` or `tag:query` specs separated by `;` (tags: comment, story, ask_hn, show_hn) |
| `HACKERNEWS_FEEDS`, `HACKERNEWS_INCLUDE_COMMENTS` | feeds to read; comments carry most pain points |
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_SUBREDDITS` | Reddit OAuth app (required for anything beyond local tests) |
| `CLASSIFIER_BACKEND` | `llm` (signals) or `qwen3` (local, binary) |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | any OpenAI-compatible endpoint |
| `CLASSIFICATION_WORKERS` | concurrent classification requests |
| `CLASSIFICATION_BATCH_SIZE` | texts per LLM request (default 1); invalid batch entries are retried one by one |
| `POLL_INTERVAL_SECONDS`, `POLL_MAX_BACKOFF_SECONDS`, `POLL_STALL_AFTER_SECONDS` | `scripts.run_worker` polling interval, failure backoff cap, and the silence after which a source is logged as stalled |
| `TOPIC_GATE_ENABLED` | embed first; call the LLM only for items near an active topic (default on; no topics = no filtering) |
| `LABELING_BACKEND` | `llm` problem statements or `keywords` (TF-IDF) |
| `UNMEET_API_KEY` | required for write endpoints outside development |

## API

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/signals` | filters: `topic` (semantic), `intent`, `product`, `source`, `min_severity`, `since` |
| `GET /api/v1/signals.csv` | same filters, CSV for Clay / Sheets / CRM import |
| `GET/POST /api/v1/topics`, `DELETE /api/v1/topics/{id}` | saved topics (writes need the API key) |
| `GET /api/v1/topics/{id}/signals` | best-matching signals for a topic |
| `GET /api/v1/opportunities`, `/clusters`, `/trends`, `/analytics/summary` | clustered problems and trends |
| `GET /api/v1/inbox`, `/inbox/counts`, `POST /inbox/state`, `POST /inbox/{id}/reply-draft` | the workspace inbox: triage states, reply drafts |
| `POST /api/v1/onboarding/analyze`, `/onboarding/confirm` | propose topics from a URL, then create them |
| `GET /api/v1/workspace`, `/workspace/members`, `/workspace/api-keys`, `/workspace/channels`, `/workspace/usage` | team, keys, digests and AI usage (managers) |
| `GET /api/v1/reports`, `/reports/{id}`, `/reports/{id}.md` | public pain reports built from clusters (no author names) |
| `POST /api/v1/demo` | public landing-page demo, off unless `DEMO_ENABLED=true`, rate limited and cached |
| `GET /api/v1/search` | semantic search over problems |
| `GET /health`, `GET /health/ingestion` | liveness; 503 when a source with data went quiet |
| `GET /api/v1/audit`, `GET /api/v1/usage/llm` | audit trail of writes; LLM tokens and cost (API key) |
| `POST /api/v1/privacy/erasure` | delete everything stored about an author (API key) |

Interactive docs at `/docs` when the API is running. Reads and writes are rate limited per client
(`RATE_LIMIT_READ_PER_MINUTE`, `RATE_LIMIT_WRITE_PER_MINUTE`). See [docs/DEPLOY.md](docs/DEPLOY.md) for
operations and [docs/GDPR.md](docs/GDPR.md) for data protection.

## Development

```bash
ruff check . && mypy app && pytest
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/unmeet_test pytest  # + integration
cd frontend && npm run lint && npm test && npm run build
```

Integration tests run on a real Postgres with pgvector (migrations vs ORM drift, upserts, vector
search, JSONB filters); CI runs everything on every pull request. Schema changes go through
Alembic: edit `app/database/models.py`, then `alembic revision --autogenerate -m "..."`.

## Layout

- `app/ingestion` – source connectors · `app/preprocessing` – cleaning and dedup
- `app/problem_detection` – LLM and Qwen3 classifiers · `app/llm` – OpenAI-compatible client
- `app/embeddings`, `app/clustering`, `app/analysis` – vectors, clusters, labels, trends
- `app/signals`, `app/topics` – signal queries, tracked topics, webhook delivery
- `app/api` – FastAPI · `frontend` – Next.js · `migrations` – Alembic
- `scripts` – run, analysis, alerts, evaluation · `docs` – architecture, audit, evaluation
