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

## Avvio locale

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
docker compose up -d
python scripts/init_db.py
python main.py
```

Su Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
docker compose up -d
python scripts/init_db.py
python main.py
```

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