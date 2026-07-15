# unMeet — Architecture

## Obiettivo

L'architettura deve supportare una pipeline modulare, ripetibile, ispezionabile e facilmente estendibile.

## Vista generale

```text
Hacker News API ─┐
Stack Exchange ──┼──> Ingestion Layer
Reddit API ──────┘
                         |
                         v
                 Normalization Layer
                         |
                         v
                    Cleaning Layer
                         |
                         v
                 Deduplication Layer
                         |
                         v
              Local Embedding Service
                         |
                         v
               PostgreSQL + pgvector
                         |
                         v
                   HDBSCAN Engine
                         |
                         v
             Cluster Canonicalization
                         |
                         v
             Market Coverage Connectors
                GitHub / Product Hunt
                         |
                         v
              Coverage Classification
                         |
                         v
                 Streamlit Dashboard
```

## Moduli

### `app/ingestion`

Responsabilità:

- connessione alle API;
- paginazione;
- rate limiting;
- retry;
- gestione errori;
- mapping verso lo schema comune.

Connettori:

- `hackernews.py`;
- `stackexchange.py`;
- `reddit.py`.

### `app/preprocessing`

Responsabilità:

- pulizia HTML;
- normalizzazione;
- costruzione del testo finale;
- filtraggio;
- deduplicazione.

### `app/embeddings`

Responsabilità:

- caricamento del modello locale;
- generazione batch;
- normalizzazione vettori;
- versionamento del modello;
- salvataggio in pgvector.

### `app/clustering`

Responsabilità:

- caricamento embedding;
- eventuale riduzione dimensionale;
- esecuzione HDBSCAN;
- gestione rumore;
- salvataggio label e confidence;
- statistiche dei cluster.

### `app/market`

Responsabilità:

- trasformazione dei cluster in query;
- ricerca su GitHub e/o Product Hunt;
- salvataggio risultati;
- matching semantico;
- classificazione copertura.

### `app/database`

Responsabilità:

- modelli SQLAlchemy;
- sessioni;
- migrazioni;
- relazioni;
- integrazione pgvector.

### `app/dashboard`

Responsabilità:

- visualizzazione cluster;
- filtri;
- trend;
- fonti originali;
- risultati di mercato;
- stato di copertura.

### `app/services`

Responsabilità:

- orchestrazione delle fasi;
- avvio dei run;
- gestione dipendenze;
- logging;
- configurazione.

## Stack

### Linguaggio

Python 3.11 o superiore.

### Database

- PostgreSQL;
- pgvector;
- SQLAlchemy;
- Alembic.

### Elaborazione dati

- pandas;
- BeautifulSoup;
- scikit-learn;
- sentence-transformers;
- HDBSCAN;
- UMAP opzionale.

### Dashboard

Streamlit.

### Ambiente

Docker Compose per PostgreSQL e pgvector.

## Schema dati comune

```json
{
  "external_id": "string",
  "source": "string",
  "title": "string",
  "body": "string",
  "url": "string",
  "author": "string|null",
  "published_at": "datetime",
  "engagement_score": 0,
  "raw_payload": {},
  "ingested_at": "datetime"
}
```

## Principi architetturali

- separazione delle responsabilità;
- idempotenza;
- configurazione esterna;
- persistenza dei risultati intermedi;
- versionamento dei modelli;
- tracciabilità;
- connector sostituibili;
- fallimento isolato delle fonti;
- pipeline rieseguibile per singola fase.

## Decisioni tecniche

### PostgreSQL + pgvector

Consente di mantenere dati relazionali e vettoriali nello stesso sistema, riducendo la complessità infrastrutturale dell'MVP.

### sentence-transformers

Permette embedding locali, controllabili e senza dipendenza da API commerciali.

### HDBSCAN

È adatto quando il numero di problemi distinti non è noto e una parte dei documenti può essere rumore.

### Streamlit

È sufficiente per una dashboard locale e riduce il tempo dedicato al frontend.

## Decisioni ancora aperte

- modello embedding iniziale;
- uso di UMAP;
- parametri HDBSCAN;
- soglia minima dei cluster;
- strategia di canonicalizzazione;
- fonte primaria di market coverage;
- regole di classificazione;
- finestra temporale dei dati.
