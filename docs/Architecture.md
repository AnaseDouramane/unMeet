# Architecture

## Stato del sistema

unMeet è una pipeline locale per trasformare contenuti di community pubbliche in documenti normalizzati, embedding tracciabili e input compatibili per clustering semantico.

Il run automatico parte da `main.py` e persiste i documenti con il modello di embedding effettivamente usato. Clustering, labeling e persistenza degli snapshot di clustering sono componenti disponibili, ma non sono ancora concatenati automaticamente alla pipeline.

## Pipeline eseguita

```text
main.py
  -> Pipeline
  -> HackerNewsConnector
  -> SourceItem
  -> PreprocessingService
  -> PreparedDocument
  -> EmbeddingService.encode
  -> SourceItemRepository.save
  -> PostgreSQL + pgvector
```

Per ogni documento la pipeline passa a `SourceItemRepository.save()` sia il vettore sia `EmbeddingService.model_name`. Questo collega ogni embedding alla sua provenance e impedisce inserimenti incompleti.

## Embedding e semantic search

`EmbeddingService` usa `sentence-transformers` e produce vettori di 384 dimensioni. Il contratto runtime rifiuta output con dimensionalità diversa, valori non numerici o non finiti.

`SourceItemRepository` persiste i vettori nella colonna `pgvector` e conserva `embedding_model`. Le letture vettoriali richiedono sempre il modello:

- `find_similar(embedding, embedding_model, limit)` esegue una ricerca per distanza coseno filtrata sul modello;
- `find_all_with_embeddings(embedding_model)` restituisce solo documenti compatibili, ordinati stabilmente per `id`.

Il repository espone DTO immutabili e non restituisce modelli SQLAlchemy dalle proprie API pubbliche. Il mapping ORM → DTO avviene prima della chiusura della sessione.

## Clustering e topic labeling

`ClusteringService.cluster_documents(embedding_model)` richiede esplicitamente il modello e legge quindi un solo spazio vettoriale alla volta. Usa `HDBSCANClusterer`, configurabile con:

- `min_cluster_size`;
- `min_samples` opzionale;
- `metric` (predefinita `euclidean`).

I documenti con etichetta HDBSCAN `-1` sono trattati come rumore. I cluster validi sono rappresentati da `DocumentCluster` e `ClusterableDocument`, che include anche `embedding_model`.

`TopicLabelingService` etichetta un cluster usando TF-IDF sui `document_text`: estrae keyword ordinate in modo deterministico e costruisce una label leggibile.

## Persistenza dei cluster

`ClusterRepository` salva run e cluster separatamente dai documenti sorgente:

```text
ClusterRun
  -> Cluster
       -> cluster_source_items
       -> SourceItem
```

Ogni `ClusterRun` conserva uno snapshot dei metadata necessari per interpretare e riprodurre il risultato:

- `embedding_model`;
- `min_cluster_size`;
- `min_samples`;
- `metric`.

`ClusterRunMetadata` e `PersistedClusterRun` sono DTO immutabili. Il repository rifiuta di associare a una run documenti ottenuti con un modello di embedding diverso.

## Componenti non ancora orchestrati

- ingestion Stack Exchange e Reddit;
- esecuzione automatica del clustering dopo la pipeline;
- topic labeling e salvataggio cluster nel run principale;
- market coverage e dashboard collegate ai dati persistiti;
- trend detection.