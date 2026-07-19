# Roadmap

## Feature completate

- Ingestion Hacker News con schema comune `SourceItem`.
- Preprocessing: pulizia HTML, normalizzazione, `document_text` e `dedup_hash`.
- Pipeline che genera embedding locali con `sentence-transformers` e persiste i documenti.
- PostgreSQL con `pgvector` e vettori a 384 dimensioni.
- Provenance del modello: ogni embedding salvato ha `embedding_model`; query semantiche e clustering sono isolati per modello.
- Semantic search con distanza coseno, filtrata per `embedding_model`.
- DTO pubblici immutabili del repository, senza esposizione dei modelli SQLAlchemy.
- Clustering HDBSCAN configurabile per `min_cluster_size`, `min_samples` e `metric`.
- Topic labeling TF-IDF con keyword deterministiche.
- Persistenza di `ClusterRun`, cluster, centroidi, keyword e membership documento-cluster.
- Snapshot immutabile dei metadata della run: modello embedding e parametri HDBSCAN.
- Test automatici per ingestion, preprocessing, embedding, repository, schema database, clustering, labeling e pipeline.

## Da integrare nel flusso principale

- Esecuzione automatica di clustering, labeling e persistenza cluster dopo l'ingestion.
- Ingestion reale da Stack Exchange e Reddit.
- Market coverage e dashboard sui dati persistiti.

## Evoluzioni future

- Migrazioni e gestione evolutiva dello schema.
- Trend detection.
- Membership probability e metriche HDBSCAN avanzate.
- Più fonti, supporto multilingua, alert e reportistica.