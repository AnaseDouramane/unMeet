# unMeet — Roadmap

## Milestone 0 — Product Definition

### Deliverable

- `PRD.md`;
- `Vision.md`;
- `Scope.md`;
- `Architecture.md`;
- `Roadmap.md`.

### Exit criteria

- obiettivo chiaro;
- scope definito;
- funzionalità future escluse;
- architettura logica documentata;
- metriche e rischi espliciti.

---

## Milestone 1 — Repository e ambiente locale

### Attività

- struttura cartelle;
- virtual environment;
- requirements;
- Docker Compose;
- PostgreSQL;
- pgvector;
- `.env`;
- logging;
- test runner;
- linting.

### Exit criteria

Il progetto può essere installato e avviato localmente seguendo il README.

---

## Milestone 2 — Hacker News ingestion

### Attività

- implementazione connector;
- recupero dati reali;
- mapping schema comune;
- gestione errori;
- paginazione;
- test;
- persistenza.

### Exit criteria

I record di Hacker News vengono acquisiti e salvati senza duplicati.

---

## Milestone 3 — Stack Exchange ingestion

### Attività

- connector;
- paginazione;
- rate limit;
- normalizzazione;
- test;
- persistenza.

### Exit criteria

I dati Stack Exchange vengono salvati nello stesso schema di Hacker News.

---

## Milestone 4 — Reddit ingestion

### Attività

- autenticazione;
- connector;
- gestione limiti;
- fallback;
- test.

### Exit criteria

Reddit funziona come fonte secondaria senza bloccare le altre fonti.

---

## Milestone 5 — Cleaning e deduplication

### Attività

- pulizia HTML;
- normalizzazione;
- soglie minime;
- filtri;
- hash;
- duplicati esatti;
- quasi duplicati;
- report diagnostico.

### Exit criteria

Il corpus pulito è sensibilmente meno rumoroso del dataset grezzo.

---

## Milestone 6 — Embedding pipeline

### Attività

- scelta modello;
- benchmark locale;
- elaborazione batch;
- versionamento;
- salvataggio pgvector;
- query di similarità.

### Exit criteria

Ogni documento valido possiede un embedding persistito.

---

## Milestone 7 — HDBSCAN clustering

### Attività

- preparazione matrice;
- eventuale UMAP;
- tuning;
- gestione rumore;
- salvataggio run;
- ispezione manuale.

### Exit criteria

Il sistema produce cluster semanticamente coerenti e identificabili.

---

## Milestone 8 — Cluster canonicalization

### Attività

- documenti rappresentativi;
- keyword;
- titolo;
- descrizione;
- trend;
- distribuzione per fonte.

### Exit criteria

Ogni cluster è comprensibile senza leggere tutte le discussioni.

---

## Milestone 9 — Market coverage

### Attività

- connector GitHub o Product Hunt;
- generazione query;
- raccolta risultati;
- similarity matching;
- classificazione;
- evidenze.

### Exit criteria

Ogni cluster valido ha uno stato supportato da risultati consultabili.

---

## Milestone 10 — Dashboard locale

### Attività

- elenco cluster;
- filtri;
- dettaglio;
- trend;
- link originali;
- soluzioni;
- stato copertura.

### Exit criteria

Un osservatore esterno comprende il progetto usando la dashboard.

---

## Milestone 11 — Evaluation e case study

### Attività

- selezione cluster;
- benchmark;
- analisi qualitativa;
- screenshot;
- diagrammi;
- limiti;
- README;
- case study.

### Exit criteria

Il repository racconta chiaramente problema, scelte tecniche, risultati e limiti.
