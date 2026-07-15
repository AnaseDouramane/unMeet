# unMeet — Product Requirements Document

## 1. Documento

- **Prodotto:** unMeet
- **Versione:** 0.1
- **Stato:** Draft operativo
- **Ambito:** MVP portfolio
- **Owner:** Project team unMeet

---

## 2. Sintesi del prodotto

unMeet è una piattaforma di **Problem Intelligence** che raccoglie problemi, richieste e bisogni espressi spontaneamente in community tecniche pubbliche, li raggruppa semanticamente e verifica se esistono già soluzioni collegate sul mercato.

L'MVP deve dimostrare una pipeline completa e verificabile:

```text
Fonti pubbliche
    ↓
Ingestion multi-fonte
    ↓
Normalizzazione e pulizia
    ↓
Deduplicazione
    ↓
Embedding locali
    ↓
Clustering semantico
    ↓
Canonicalizzazione del problema
    ↓
Ricerca di soluzioni esistenti
    ↓
Classificazione della copertura
    ↓
Dashboard locale
```

---

## 3. Problema

Ogni giorno migliaia di utenti descrivono problemi reali su Hacker News, Stack Exchange, Reddit e forum pubblici.

Questi segnali sono difficili da utilizzare perché:

- sono dispersi tra piattaforme diverse;
- sono espressi con parole differenti;
- includono spam, rumore e duplicati;
- non distinguono una lamentela isolata da un bisogno ricorrente;
- richiedono analisi manuale per essere confrontati con il mercato;
- non sono presentati in una forma immediatamente utile per la discovery di prodotto.

---

## 4. Obiettivo dell'MVP

Dimostrare che un sistema cost-aware può:

1. raccogliere contenuti reali da almeno due fonti primarie e una secondaria;
2. normalizzare dati eterogenei in uno schema comune;
3. filtrare rumore e duplicati;
4. generare embedding con un modello locale open-source;
5. identificare gruppi di discussioni che esprimono lo stesso problema;
6. sintetizzare ogni gruppo in una descrizione comprensibile;
7. cercare soluzioni esistenti collegate;
8. classificare ogni cluster in base alla copertura di mercato;
9. mostrare risultati ed evidenze in una dashboard locale.

---

## 5. Non-obiettivi

L'MVP non deve:

- generare automaticamente idee di startup complete;
- garantire che un cluster sia un'opportunità commerciale;
- stimare TAM, SAM o SOM;
- fornire scoring numerici 0-100;
- offrire autenticazione, workspace o pagamenti;
- supportare X/Twitter;
- funzionare come SaaS pubblico;
- fornire analisi AI premium;
- supportare aggiornamenti schedulati;
- supportare tutte le lingue.

---

## 6. Utenti target

### Utenti primari

- aspiring founder;
- indie hacker;
- product manager;
- startup early-stage;
- innovation analyst.

### Bisogno principale

Ridurre il tempo necessario per individuare problemi ricorrenti e verificare rapidamente se il mercato li sta già affrontando.

---

## 7. User journey principale

### Step 1 — Avvio della pipeline

L'utente avvia manualmente la pipeline da CLI o script.

### Step 2 — Raccolta

Il sistema raccoglie contenuti da:

- Hacker News;
- Stack Exchange;
- Reddit.

### Step 3 — Elaborazione

Il sistema:

- normalizza;
- pulisce;
- deduplica;
- genera embedding;
- crea cluster.

### Step 4 — Analisi del cluster

Per ogni cluster il sistema produce:

- titolo;
- descrizione canonica;
- keyword;
- numero di citazioni;
- distribuzione per fonte;
- andamento temporale;
- discussioni rappresentative.

### Step 5 — Market coverage

Il sistema ricerca possibili soluzioni su GitHub e/o Product Hunt.

### Step 6 — Dashboard

L'utente consulta i cluster ordinati e apre:

- dettagli;
- discussioni originali;
- soluzioni individuate;
- stato di copertura.

---

## 8. Requisiti funzionali

## FR-01 — Ingestion Hacker News

Il sistema deve poter acquisire dati reali tramite Hacker News API.

### Dati minimi

- id esterno;
- titolo;
- testo;
- URL;
- autore;
- timestamp;
- score;
- numero commenti, se disponibile;
- payload originale.

### Criteri di accettazione

- la pipeline salva record reali;
- la riesecuzione non crea duplicati;
- gli errori HTTP vengono gestiti;
- ogni record conserva il link originale.

---

## FR-02 — Ingestion Stack Exchange

Il sistema deve acquisire domande tramite Stack Exchange API.

### Dati minimi

- question id;
- titolo;
- body;
- link;
- owner;
- creation date;
- score;
- answer count;
- tags;
- payload originale.

### Criteri di accettazione

- la paginazione funziona;
- i rate limit vengono rispettati;
- i record sono normalizzati nello stesso schema di Hacker News.

---

## FR-03 — Ingestion Reddit

Il sistema deve integrare Reddit come fonte secondaria.

### Criteri di accettazione

- il connettore usa API pubbliche autorizzate;
- eventuali limiti di accesso sono documentati;
- la mancata disponibilità di Reddit non blocca l'intera pipeline.

---

## FR-04 — Schema normalizzato

Tutte le fonti devono produrre lo stesso oggetto logico.

### Campi richiesti

- `external_id`;
- `source`;
- `title`;
- `body`;
- `url`;
- `author`;
- `published_at`;
- `engagement_score`;
- `raw_payload`;
- `ingested_at`.

---

## FR-05 — Pulizia testo

Il sistema deve:

- rimuovere HTML;
- normalizzare Unicode e spazi;
- eliminare testi vuoti;
- eliminare contenuti sotto una soglia minima;
- combinare titolo e corpo;
- rimuovere boilerplate noto;
- produrre un campo `clean_text`.

---

## FR-06 — Deduplicazione

Il sistema deve identificare:

- duplicati per fonte e id;
- duplicati per URL;
- duplicati esatti per hash;
- quasi duplicati tramite similarità.

Ogni contenuto escluso deve mantenere una motivazione tracciabile.

---

## FR-07 — Embedding locali

Il sistema deve generare embedding con `sentence-transformers`.

### Requisiti

- modello open-source;
- esecuzione locale;
- batch processing;
- normalizzazione opzionale dei vettori;
- versione del modello salvata;
- embedding memorizzati in pgvector.

---

## FR-08 — Clustering HDBSCAN

Il sistema deve utilizzare HDBSCAN.

### Output richiesti

- cluster label;
- membership probability;
- identificazione del rumore;
- parametri del run;
- timestamp del run;
- versione degli embedding usati.

---

## FR-09 — Canonicalizzazione dei cluster

Per ogni cluster valido il sistema deve produrre:

- titolo sintetico;
- descrizione canonica;
- keyword;
- documenti rappresentativi;
- numero totale di citazioni;
- distribuzione per fonte;
- prima e ultima citazione.

La prima versione può usare metodi estrattivi senza LLM a pagamento.

---

## FR-10 — Ricerca market coverage

Il sistema deve interrogare almeno una fonte tra:

- GitHub;
- Product Hunt.

Per ogni cluster deve salvare:

- query utilizzata;
- risultati trovati;
- URL;
- titolo;
- descrizione;
- metriche disponibili;
- similarity score, se calcolato;
- data della ricerca.

---

## FR-11 — Classificazione della copertura

Ogni cluster deve ricevere uno stato:

- `non_presidiato`;
- `parzialmente_coperto`;
- `saturo`.

La classificazione deve basarsi su criteri documentati e su evidenze memorizzate.

La prima versione può usare una regola euristica, purché non sia presentata come verità assoluta.

---

## FR-12 — Dashboard locale

La dashboard deve mostrare:

- elenco cluster;
- titolo;
- descrizione;
- numero di citazioni;
- andamento temporale;
- fonti;
- stato di copertura;
- discussioni originali;
- soluzioni esistenti individuate.

### Filtri minimi

- fonte;
- intervallo temporale;
- stato di copertura;
- dimensione minima del cluster.

---

## 9. Requisiti non funzionali

## NFR-01 — Cost awareness

Gli embedding devono essere eseguiti localmente senza dipendere da API commerciali.

## NFR-02 — Reproducibility

Ogni run deve salvare configurazione, timestamp e versione del modello.

## NFR-03 — Idempotenza

La riesecuzione dell'ingestion non deve creare duplicati.

## NFR-04 — Tracciabilità

Ogni cluster deve poter essere ricondotto ai documenti e alle fonti originali.

## NFR-05 — Resilienza

Il fallimento di una singola fonte non deve invalidare i dati già raccolti dalle altre.

## NFR-06 — Sicurezza

Token e credenziali devono essere gestiti tramite variabili d'ambiente.

## NFR-07 — Manutenibilità

Connettori, preprocessing, embedding, clustering, market coverage e dashboard devono essere moduli separati.

## NFR-08 — Osservabilità

La pipeline deve produrre log per:

- inizio e fine fase;
- numero record processati;
- record scartati;
- errori API;
- durata;
- risultato del run.

---

## 10. Metriche di successo

L'MVP è considerato dimostrativo se raggiunge:

- almeno 2 fonti primarie funzionanti;
- almeno 1.000 documenti reali acquisiti complessivamente;
- deduplicazione verificabile;
- embedding generati per almeno il 90% dei documenti validi;
- almeno 10 cluster ispezionabili;
- presenza di link originali per almeno il 95% dei documenti;
- market coverage completata per almeno il 90% dei cluster validi;
- dashboard navigabile localmente;
- almeno 3 cluster qualitativamente convincenti da usare nel case study.

Queste soglie sono iniziali e possono essere aggiornate dopo i primi esperimenti.

---

## 11. Rischi principali

### Accesso alle fonti

Reddit e Product Hunt possono imporre limiti o modifiche alle API.

**Mitigazione:** rendere ogni connector sostituibile e non bloccare la pipeline in caso di errore.

### Qualità dei cluster

Gli embedding potrebbero raggruppare discussioni semanticamente vicine ma riferite a problemi differenti.

**Mitigazione:** test qualitativi, tuning HDBSCAN, documenti rappresentativi e analisi del rumore.

### Market coverage debole

Il numero di risultati non è sufficiente per stabilire la saturazione reale.

**Mitigazione:** presentare la classificazione come stima euristica supportata da evidenze.

### Bias delle fonti

Le community tecniche non rappresentano l'intero mercato.

**Mitigazione:** dichiarare esplicitamente il limite nel case study.

### Costi computazionali

Embedding e clustering potrebbero essere lenti su hardware limitato.

**Mitigazione:** batch, caching, modello compatto e dataset iniziale controllato.

---

## 12. Assunzioni

- l'MVP verrà eseguito localmente;
- la lingua iniziale sarà l'inglese;
- il dataset iniziale sarà limitato nel tempo o nel numero di record;
- l'utente è tecnico;
- la pipeline verrà avviata on-demand;
- la dashboard non richiede autenticazione.

---

## 13. Dipendenze esterne

- Hacker News API;
- Stack Exchange API;
- Reddit API;
- GitHub API e/o Product Hunt API;
- PostgreSQL;
- pgvector;
- sentence-transformers;
- HDBSCAN;
- Streamlit.

---

## 14. Decisioni aperte

Prima dell'implementazione completa devono essere fissate:

1. modello sentence-transformers iniziale;
2. finestra temporale dei dati;
3. query o categorie da raccogliere;
4. metodo per quasi-duplicati;
5. utilizzo o meno di UMAP;
6. parametri iniziali HDBSCAN;
7. strategia di canonicalizzazione;
8. fonte primaria per market coverage;
9. regole iniziali per classificare la copertura;
10. dataset di valutazione manuale.

---

## 15. Exit criteria del PRD

Il PRD è approvato quando:

- l'obiettivo dell'MVP è non ambiguo;
- ogni requisito fondamentale è rappresentato;
- le funzionalità future sono escluse;
- esistono criteri di accettazione verificabili;
- rischi e limiti sono espliciti;
- le decisioni ancora aperte sono tracciate.
