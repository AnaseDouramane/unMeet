# Architecture

## Stato del sistema

unMeet è una pipeline locale per trasformare contenuti di community pubbliche in problemi classificati, embedding tracciabili, cluster semantici e trend confrontabili tra run.

L'entry point operativo è `scripts/run_unmeet.py`. Costruisce i connettori configurati, esegue l'ingestion in sequenza e avvia l'analisi se almeno una fonte termina con successo. `INGESTION_FAIL_FAST` determina se fermarsi al primo errore di fonte.

## Pipeline eseguita

```text
scripts.run_unmeet
  -> MultiSourceIngestionService
  -> connector configurati (Hacker News, GitHub Issues, Reddit)
  -> Pipeline
  -> SourceItem
  -> PreprocessingService
  -> PreparedDocument
  -> ProblemDetectionService + Qwen3ProblemClassifier
  -> [solo problemi] EmbeddingService.encode
  -> SourceItemRepository.save
  -> PostgreSQL + pgvector
  -> AnalysisOrchestrator
  -> clustering + labeling
  -> matching con la run precedente compatibile
  -> trend detection
  -> ClusterRepository
```

I contenuti classificati come non-problema sono comunque persistiti, ma senza embedding. Un output malformato del classificatore viene registrato nelle statistiche e trattato in modo conservativo come non-problema. Per ogni problema la pipeline salva vettore, modello, risultato e provenance della classificazione.

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

## API e interfacce

La REST API FastAPI espone health check e risorse sotto `/api/v1` per analytics, opportunità, cluster, trend e ricerca semantica. Il frontend usa `NEXT_PUBLIC_API_BASE_URL`. La dashboard Streamlit è ancora un placeholder locale e non è collegata ai dati persistiti.

## Componenti non ancora integrati nel workflow completo

- connettore Stack Exchange;
- market coverage GitHub/Product Hunt nell'orchestrazione;
- schedulazione automatica delle run;
- migrazioni evolutive dello schema.
