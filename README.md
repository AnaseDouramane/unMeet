# unMeet

unMeet raccoglie problemi reali da community pubbliche, li raggruppa semanticamente e verifica la copertura del mercato.

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

- `app/ingestion`: connettori alle fonti dati
- `app/preprocessing`: pulizia, normalizzazione e deduplicazione
- `app/embeddings`: embedding locali
- `app/clustering`: clustering HDBSCAN
- `app/market`: ricerca di soluzioni esistenti
- `app/database`: modelli e sessione PostgreSQL
- `app/dashboard`: dashboard locale
- `app/services`: orchestrazione della pipeline
- `docs`: documentazione
- `scripts`: script operativi
- `tests`: test automatici
