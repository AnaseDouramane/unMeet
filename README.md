# unMeet

unMeet raccoglie contenuti da community pubbliche, identifica i problemi espressi, li raggruppa semanticamente e rende disponibili cluster, trend e opportunità tramite API e interfacce locali.

## Stato attuale

Il workflow completo si avvia con `python -m scripts.run_unmeet` e svolge:

1. ingestion multi-fonte da Hacker News, GitHub Issues e, se configurato, Reddit;
2. preprocessing e deduplicazione testuale;
3. classificazione locale dei contenuti con Qwen3;
4. archiviazione dei contenuti non-problema;
5. generazione degli embedding per i problemi identificati;
6. persistenza/upsert in PostgreSQL con `pgvector`;
7. clustering HDBSCAN e topic labeling TF-IDF;
8. confronto con la run compatibile precedente e persistenza dei trend.

Il comando stampa un riepilogo con record acquisiti, problemi identificati, errori di classificazione, cluster e distribuzione dei trend. `main.py` è mantenuto come alias compatibile dello stesso workflow completo.

Le fonti sono selezionate, nell'ordine di esecuzione, con `INGESTION_SOURCES`. Sono supportati `hackernews`, `github` e `reddit`; almeno una fonte deve essere abilitata. `INGESTION_FAIL_FAST=false` consente alle fonti successive di proseguire dopo il fallimento di un connettore.

Hacker News usa per default `topstories`, `newstories` e `beststories`, con un limite globale di 500 post unici e validi. È supportato anche `askstories`.

Esempio:

```bash
cp .env.example .env
docker compose up -d
python -m scripts.init_db
python -m scripts.run_unmeet
```

Per ripetere soltanto clustering, labeling e trend sui problemi già persistiti:

```bash
python -m scripts.run_analysis
```

La prima esecuzione scarica i modelli locali Qwen3 e sentence-transformers. Qwen3 seleziona CUDA quando disponibile e usa altrimenti la CPU.

## Applicazione locale

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

La dashboard Streamlit è al momento un placeholder e non è ancora collegata ai dati persistiti.

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
- `app/problem_detection`: classificazione locale problema/non-problema
- `app/embeddings`: generazione degli embedding locali
- `app/database`: modelli SQLAlchemy, repository e DTO pubblici
- `app/clustering`: HDBSCAN, labeling, matching tra run e trend detection
- `app/analysis`: orchestrazione dell'analisi successiva all'ingestion
- `app/api`: REST API FastAPI
- `app/opportunities`: ranking delle opportunità
- `app/market`: connettori sperimentali per market coverage
- `app/dashboard`: dashboard locale
- `app/services`: orchestrazione della pipeline
- `scripts`: entry point operativi, import/export e valutazione
- `docs`: documentazione architetturale e operativa
- `tests`: test automatici
