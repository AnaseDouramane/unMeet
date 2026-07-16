# Roadmap

## Feature Completate

- Struttura del progetto Python con moduli separati per ingestion, preprocessing, database, market e dashboard.
- Connettore `HackerNewsConnector` per recuperare gli story da Hacker News.
- Schema comune `SourceItem` per i dati in ingresso.
- Pulizia HTML e normalizzazione degli spazi.
- Costruzione del `document_text` da titolo e corpo.
- Calcolo di `dedup_hash` basato sul testo normalizzato.
- `PreparedDocument` e `PreprocessingService`.
- Pipeline corrente che coordina Hacker News e preprocessing.
- Modello `SourceItemModel` con vincolo di unicità e indice su `dedup_hash`.
- Bootstrap del database PostgreSQL con `pgvector`.
- Test automatici per ingestion, preprocessing, pipeline e schema database.

## Feature Future

- Persistenza effettiva dei `SourceItemModel` generati dalla pipeline.
- Ingestion reale da Stack Exchange.
- Ingestion reale da Reddit.
- Embedding locali nel flusso principale.
- Clustering dei documenti.
- Connessione al layer di market coverage.
- Dashboard collegata ai dati elaborati.
- Migrazioni e gestione evolutiva dello schema dati.
- Eventuale estensione della pipeline oltre Hacker News come fonte primaria attiva.
