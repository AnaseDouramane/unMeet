# unMeet

unMeet raccoglie problemi espressi in community pubbliche, li normalizza, genera embedding locali e li persiste per analisi semantiche e clustering.

## Stato attuale

Il flusso eseguito da `main.py` usa Hacker News come fonte attiva e svolge:

1. ingestion degli story;
2. preprocessing e deduplicazione testuale;
3. generazione di embedding locali con `sentence-transformers`;
4. persistenza/upsert in PostgreSQL con `pgvector`;
5. salvataggio della provenance del modello di embedding.

La ricerca semantica, il clustering HDBSCAN, il topic labeling TF-IDF e la persistenza degli snapshot di clustering sono disponibili nei rispettivi servizi e repository. Non sono ancora orchestrati automaticamente dal run della pipeline.

Hacker News usa per default i feed `topstories`, `newstories` e `beststories` e restituisce fino a
500 post unici e validi per run. Configurare `HACKERNEWS_FEEDS` e `HACKERNEWS_LIMIT` nell'ambiente
(vedi `.env.example`); il limite è globale tra tutti i feed. È supportato anche `askstories` tramite
l'endpoint Firebase ufficiale `askstories.json`, senza scraping.

Per una run da 500 post candidati:

```bash
HACKERNEWS_FEEDS=topstories,newstories,beststories HACKERNEWS_LIMIT=500 python -m scripts.run_unmeet
```

## Run locally

Installare prima le dipendenze Python e configurare il database come necessario per il proprio ambiente.

### Backend

```bash
uvicorn app.api.app:create_app --factory --reload
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

`frontend/.env.example` contiene l'unico URL della REST API usato dal frontend:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Riavviare `npm run dev` dopo aver creato o modificato `.env.local`. Il backend permette per
default le origini locali `localhost:3000` e `127.0.0.1:3000`; in altri ambienti impostare
`API_CORS_ORIGINS` con una lista separata da virgole.

## Dashboard

```bash
streamlit run app/dashboard/app.py
```

## Test

```bash
pytest
```

## Struttura

- `app/ingestion`: connettori e schema delle fonti
- `app/preprocessing`: pulizia, normalizzazione e deduplicazione
- `app/embeddings`: generazione degli embedding locali
- `app/database`: modelli SQLAlchemy, repository e DTO pubblici
- `app/clustering`: HDBSCAN, documenti clusterizzabili e topic labeling TF-IDF
- `app/market`: connettori per market coverage, non ancora integrati nel run
- `app/dashboard`: dashboard locale
- `app/services`: orchestrazione della pipeline
- `docs`: documentazione architetturale e operativa
- `tests`: test automatici
