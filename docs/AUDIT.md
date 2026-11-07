# Technical audit — November 2026

Baseline: commit `ddc4180`. Scope: whole repository (backend, frontend, scripts, tests, docs).

## What works

- 298 backend tests and 8 frontend tests pass; the code is defensive (strict validation, immutable DTOs, explicit embedding-model provenance).
- Clear module boundaries: ingestion → preprocessing → classification → embeddings → pgvector → clustering → trends → ranking → API → Next.js UI.
- Cluster runs are reproducible (run metadata snapshot) and trends are matched across compatible runs.

## Defects

| # | Area | Problem | Impact |
|---|------|---------|--------|
| D1 | Config | `.env` is never loaded (`python-dotenv` is a dependency but `load_dotenv` is never called); `Settings` defaults are evaluated at import time. | Following the README silently runs with defaults. |
| D2 | Pipeline | Every run re-classifies items already stored. | LLM cost and runtime grow with every run. |
| D3 | Clustering | HDBSCAN runs on raw 384-d vectors with euclidean distance, no normalisation or dimensionality reduction, `min_cluster_size=2`. | Density estimates degrade in high dimensions; many tiny clusters or everything as noise. |
| D4 | Labeling | Cluster label is a comma-joined list of TF-IDF terms. | Not readable as a problem statement; not sellable. |
| D5 | Hacker News | Only top/new/best *stories* are fetched, sequentially; comments are ignored. | Pain points live in comments and Ask HN; ingestion of 500 items is slow. |
| D6 | Reddit | Unauthenticated `www.reddit.com/*.json`; OAuth credentials are accepted but unused. | Rate-limited/blocked; not acceptable for commercial use. |
| D7 | Classifier | One document at a time on local Qwen3-0.6B; binary output only. | Slow on CPU; no intent, no quote, no product mentions — nothing a GTM user can act on. |
| D8 | Evaluation | `problem_detection_eval.jsonl` has 35 synthetic, hand-written sentences. | Reported F1 is not evidence of real-world quality. |
| D9 | Schema | `create_all` only, no migrations. | Every schema change is a manual reset. |
| D10 | Quality gates | 131 ruff findings, 29 mypy errors, no CI. | Regressions go unnoticed. |
| D11 | Product | No accounts, saved topics, alerts or export; Streamlit dashboard is a placeholder. | Not a product a customer can pay for. |

## Product direction

Turn unMeet into a **pain-signal engine for GTM teams**: users save topics (a competitor, a category, a workflow), the system finds people publicly expressing that pain, classifies intent, extracts the exact quote, clusters the signals and delivers them as alerts and exports (CSV, webhook for Clay).

## Plan

1. Foundations: fix D1–D3, D5, D10; add CI.
2. Intelligence: pluggable LLM classifier with structured output and batching (D7), LLM cluster labels (D4), honest evaluation harness (D8).
3. Product: tracked topics, signal feed, alerts, CSV/webhook export, Alembic migrations (D9, D11).
4. SaaS: auth, billing, deployment.

## Status after the revamp

| # | Status | Where |
|---|--------|-------|
| D1 | Fixed | `.env` loaded from the working directory (`app/config.py`) |
| D2 | Fixed | unchanged items skipped (`Pipeline._is_already_classified`) |
| D3 | Fixed | L2 + UMAP + HDBSCAN (`HDBSCANClusterer.for_text_embeddings`) |
| D4 | Fixed | LLM problem statements with TF-IDF fallback (`app/clustering/llm_labeling.py`) |
| D5 | Fixed | concurrent HN fetching, top-level comments |
| D6 | Fixed | Reddit OAuth `client_credentials` |
| D7 | Fixed | OpenAI-compatible signal classifier, concurrent batches |
| D8 | Tooling in place | bootstrap CI + real-data sampling; numbers still need a labeled sample |
| D9 | Fixed | Alembic migrations, integration tests on Postgres |
| D10 | Fixed | ruff + mypy clean, CI workflow |
| D11 | Partly | signals feed, topics, webhooks, CSV, API key; multi-tenant accounts and billing remain |
