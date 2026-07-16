# unMeet

## Obiettivo Del Progetto

unMeet raccoglie problemi e bisogni espressi in community pubbliche, li normalizza e prepara la base per analisi semantiche e verifica della copertura di mercato.

## Stack Tecnologico

- Python 3.11
- SQLAlchemy
- PostgreSQL
- pgvector tramite immagine `pgvector/pgvector:pg16`
- Streamlit per la dashboard locale
- `requests` per l'ingestion di Hacker News
- `pytest` per i test

## Architettura Della Pipeline

Il flusso eseguito oggi è lineare:

1. `main.py` crea `Pipeline(settings)`.
2. `Pipeline` istanzia `HackerNewsConnector(limit=10)` e `PreprocessingService`.
3. Il connettore recupera gli id degli story da Hacker News e scarica ogni item.
4. Solo gli item di tipo `story` vengono convertiti in `SourceItem`.
5. `PreprocessingService` pulisce `title` e `body`, costruisce `document_text` e calcola `dedup_hash`.
6. La pipeline restituisce una lista di `PreparedDocument`.

Persistenza, embeddings, clustering e market coverage sono presenti come aree del repository, ma non sono ancora collegate al flusso eseguito da `main.py`.

## Ruoli

### Developer

- implementa una feature per volta;
- modifica solo i file necessari;
- esegue `pytest` prima di proporre il commit;
- usa Conventional Commits.

### Reviewer

- non implementa nuove funzionalità e non modifica il codice applicativo, salvo esplicita richiesta;
- può aggiungere o migliorare i test quando il task lo richiede;
- si concentra su architettura, qualità del codice e qualità della suite di test;
- evita refactoring prematuri;
- distingue sempre tra problemi reali e miglioramenti futuri;
- aiuta il Tech Lead a prendere decisioni, non a introdurre complessità non necessaria.

### Formato Delle Review

Ogni osservazione del Reviewer deve essere classificata in uno di questi modi:

- `NOW`: problema reale da affrontare nella prossima feature;
- `LATER`: miglioramento valido da inserire nella roadmap, ma non prioritario;
- `IGNORE`: osservazione corretta ma non utile da implementare nell'attuale fase del progetto.

Per ogni osservazione il Reviewer deve indicare sempre:

- severità: bassa, media o alta;
- motivazione;
- impatto concreto sul progetto;
- azione consigliata;
- classificazione: `NOW`, `LATER` o `IGNORE`.

## Regole Di Lavoro

- una feature per commit;
- `pytest` prima del commit;
- Conventional Commits;
- nessuna modifica architetturale senza approvazione;
- modificare solo i file necessari.

## Workflow Di Sviluppo

1. Analizzare il contesto del progetto e i file coinvolti.
2. Implementare la modifica minima necessaria.
3. Eseguire i test rilevanti, partendo da `pytest`.
4. Aprire la review del Reviewer.
5. Correggere solo i punti emersi in review, se necessario.
6. Creare il commit con messaggio Conventional Commits.
7. Eseguire `git push` quando la modifica è pronta.
