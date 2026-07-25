# Roadmap

## Feature completate

- Ingestion Hacker News con schema comune `SourceItem`.
- Ingestion multi-fonte configurabile per Hacker News, GitHub Issues e Reddit.
- Esecuzione resiliente per fonte con modalità fail-fast configurabile.
- Preprocessing: pulizia HTML, normalizzazione, `document_text` e `dedup_hash`.
- Classificazione locale problema/non-problema con Qwen3 e tracciamento del risultato.
- Pipeline che genera embedding solo per i problemi e archivia anche i non-problemi.
- PostgreSQL con `pgvector` e vettori a 384 dimensioni.
- Provenance del modello: ogni embedding salvato ha `embedding_model`; query semantiche e clustering sono isolati per modello.
- Semantic search con distanza coseno, filtrata per `embedding_model`.
- DTO pubblici immutabili del repository, senza esposizione dei modelli SQLAlchemy.
- Clustering HDBSCAN configurabile per `min_cluster_size`, `min_samples` e `metric`.
- Topic labeling TF-IDF con keyword deterministiche.
- Persistenza di `ClusterRun`, cluster, centroidi, keyword e membership documento-cluster.
- Snapshot immutabile dei metadata della run: modello embedding e parametri HDBSCAN.
- Matching dei cluster tra run compatibili e trend `new`, `rising`, `stable`, `falling`.
- Orchestrazione completa ingestion → analisi tramite `scripts.run_unmeet`.
- Ranking delle opportunità, analytics e ricerca semantica.
- REST API FastAPI e frontend locale.
- Test automatici per pipeline, analisi, API e componenti applicativi.

## Da integrare nel flusso principale

- Ingestion Stack Exchange.
- Market coverage e dashboard sui dati persistiti.

## Evoluzioni future

- Migrazioni e gestione evolutiva dello schema.
- Membership probability e metriche HDBSCAN avanzate.
- Più fonti, supporto multilingua, alert e reportistica.
