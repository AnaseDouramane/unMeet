# Architecture

## Contesto

Il repository contiene una pipeline ancora piccola ma già separata per responsabilità. Il run eseguibile oggi parte da `main.py` e attraversa solo ingestion da Hacker News e preprocessing.

## Pipeline Attuale

```text
main.py
  -> app.config.settings
  -> app.services.pipeline.Pipeline
  -> app.ingestion.hackernews.HackerNewsConnector
  -> app.ingestion.schemas.SourceItem
  -> app.services.preprocessing.PreprocessingService
  -> app.preprocessing.cleaner.clean_text
  -> app.preprocessing.normalizer.build_document_text
  -> app.preprocessing.deduplicator.text_hash
  -> app.preprocessing.schemas.PreparedDocument
```

## Layer E Responsabilità

### Entry point

`main.py` crea la pipeline e avvia un run sincrono.

### Configurazione

`app/config.py` legge le variabili d'ambiente e fornisce i parametri di runtime, inclusi URL del database e credenziali opzionali per connettori futuri.

### Ingestion

`app/ingestion` contiene il contratto comune `SourceConnector`, lo schema `SourceItem` e il connettore attivo `HackerNewsConnector`.

Il connettore:

- legge la lista degli story id;
- scarica i singoli item;
- filtra gli elementi che non sono di tipo `story`;
- costruisce un `SourceItem` con payload originale.

### Preprocessing

`app/preprocessing` contiene tre passi separati:

- `cleaner.py` rimuove HTML, unescapa entità e compatta gli spazi;
- `normalizer.py` compone il testo finale del documento;
- `deduplicator.py` calcola un hash SHA-256 normalizzato su minuscole e spazi.

### Servizio Di Orchestrazione

`app/services/preprocessing.py` unisce i passi precedenti e produce `PreparedDocument` senza mutare il `SourceItem` di input.

`app/services/pipeline.py` coordina l'esecuzione corrente e restituisce la lista dei documenti preparati.

### Database

`app/database` definisce base declarative, sessione SQLAlchemy e il modello `SourceItemModel`.

Nel repository il database è già previsto come PostgreSQL, con supporto `pgvector` abilitato dallo script di bootstrap, ma la pipeline eseguita oggi non salva ancora i documenti.

### Altri Layer Presenti

`app/embeddings`, `app/clustering`, `app/market` e `app/dashboard` esistono come aree del progetto, ma non sono ancora collegate al flusso eseguito da `main.py`.

## Flusso Dei Dati

1. Hacker News restituisce dati grezzi.
2. `HackerNewsConnector` li converte nello schema comune `SourceItem`.
3. `PreprocessingService` pulisce titolo e corpo.
4. `build_document_text` costruisce il testo da usare downstream.
5. `text_hash` genera `dedup_hash`.
6. La pipeline restituisce `PreparedDocument` pronti per eventuali stadi successivi.

## Stato Del Sistema

Il progetto è strutturato per crescere verso persistenza, embeddings, clustering e market coverage, ma questi passi non fanno ancora parte del run principale.
