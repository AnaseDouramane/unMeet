# Database

## Tecnologie

La persistenza usa SQLAlchemy, PostgreSQL e `pgvector`. Lo script `scripts/init_db.py` abilita l'estensione vettoriale nel database locale.

## SourceItem

`SourceItemModel` rappresenta un documento normalizzato e le informazioni necessarie alla ricerca semantica.

Oltre ai campi sorgente, testo pulito, `document_text`, `dedup_hash` e timestamp, contiene:

- `embedding`: vettore `VECTOR(384)`, nullable;
- `embedding_model`: stringa nullable che identifica il modello che ha prodotto il vettore.

I vincoli di database mantengono coerente la coppia:

- `ck_source_items_embedding_requires_model`: un embedding richiede `embedding_model`;
- `ck_source_items_embedding_model_requires_embedding`: un `embedding_model` richiede embedding;
- `ck_source_items_embedding_model_not_blank`: il modello non può essere una stringa vuota.

Restano inoltre il vincolo `UNIQUE(source, external_id)` e l'indice su `dedup_hash`.

## Repository e DTO pubblici

`SourceItemRepository` incapsula SQLAlchemy. Le API pubbliche restituiscono `PersistedSourceItem` oppure `ClusterableDocument`, entrambi immutabili, invece dei modelli ORM.

`PersistedSourceItem` include `embedding`, `embedding_model` e una copia immutabile del payload JSON. Il repository crea il DTO prima di chiudere la sessione, evitando risultati ORM detached.

Le query vettoriali richiedono `embedding_model` e filtrano sempre su quel valore. Questo impedisce confronti tra embedding generati da modelli differenti.

## Cluster run e cluster

`ClusterRunModel` registra un'esecuzione di clustering e conserva:

- `embedding_model` non nullable;
- `min_cluster_size` non nullable;
- `min_samples` nullable, perché HDBSCAN può usare il default;
- `metric` non nullable;
- timestamp di creazione.

`ClusterModel` appartiene a una run tramite `run_id` e registra label, keyword TF-IDF, centroide pgvector e numero di documenti. La tabella associativa `cluster_source_items` collega ogni cluster ai `SourceItem` che ne fanno parte.

`ClusterRunMetadata`, `PersistedCluster` e `PersistedClusterRun` sono DTO immutabili usati dalle API pubbliche del repository.

## Limiti attuali

Il database è sacrificabile durante questa fase: non sono presenti migrazioni Alembic. Non vengono ancora salvate probability di membership o altre metriche avanzate HDBSCAN.