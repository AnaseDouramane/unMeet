# unMeet — MVP Scope

## Obiettivo

Definire con precisione ciò che deve essere costruito nell'MVP e ciò che resta fuori dal perimetro.

## In scope

### Fonti dati

Fonti primarie:

- Hacker News API;
- Stack Exchange API.

Fonte secondaria:

- Reddit API pubblica.

### Pipeline obbligatoria

1. raccolta dati reali;
2. normalizzazione in uno schema comune;
3. pulizia del testo;
4. rimozione di rumore e spam;
5. deduplicazione;
6. generazione di embedding locali;
7. salvataggio su PostgreSQL con pgvector;
8. clustering non supervisionato con HDBSCAN;
9. canonicalizzazione del cluster;
10. ricerca di soluzioni esistenti;
11. classificazione della copertura;
12. dashboard locale.

## Funzionalità fondamentali

### Ingestion multi-fonte

Il sistema deve acquisire dati reali e mantenere almeno:

- identificativo esterno;
- fonte;
- titolo;
- corpo;
- URL;
- autore, se disponibile;
- data di pubblicazione;
- metriche di engagement;
- payload originale;
- data di acquisizione.

### Pulizia

La pipeline deve gestire:

- HTML e markup;
- spazi e caratteri anomali;
- contenuti vuoti;
- testi troppo brevi;
- boilerplate;
- spam iniziale;
- duplicati esatti;
- quasi duplicati.

### Embedding

Gli embedding devono essere:

- generati localmente;
- prodotti con sentence-transformers;
- salvati in pgvector;
- associati alla versione del modello.

### Clustering

Il clustering deve usare HDBSCAN perché:

- il numero dei cluster non è noto;
- il rumore deve essere identificato;
- i cluster possono avere densità differenti;
- k-means imporrebbe un numero di cluster a priori.

### Market coverage

Per ogni cluster il sistema deve interrogare almeno una fonte esterna tra:

- GitHub;
- Product Hunt.

Gli stati possibili sono:

- `non_presidiato`;
- `parzialmente_coperto`;
- `saturo`.

### Dashboard

La dashboard locale deve mostrare:

- titolo del cluster;
- descrizione;
- numero di citazioni;
- andamento nel tempo;
- fonti;
- stato di copertura;
- discussioni originali;
- soluzioni individuate.

## Out of scope

Non fanno parte dell'MVP:

- X/Twitter;
- autenticazione;
- pagamenti;
- deploy pubblico;
- alert;
- aggiornamenti schedulati;
- scoring 0-100;
- analisi AI premium;
- ICP automatico;
- roadmap di validazione;
- supporto multilingua completo;
- applicazione mobile;
- multi-tenancy;
- workspace condivisi.

## Nice-to-have futuri

- integrazione X/Twitter;
- scoring di opportunità;
- supporto multilingua;
- alert su nuovi problemi;
- aggiornamento automatico;
- analisi AI on-demand;
- competitor analysis avanzata;
- esportazione report;
- confronto tra periodi.

## Criteri di completamento

L'MVP è completato quando:

1. Hacker News e Stack Exchange funzionano con dati reali;
2. Reddit è integrato o eventuali limiti sono documentati;
3. i dati normalizzati sono salvati in PostgreSQL;
4. gli embedding sono salvati in pgvector;
5. HDBSCAN produce cluster ispezionabili;
6. il sistema separa il rumore;
7. ogni cluster valido ha una rappresentazione leggibile;
8. il market coverage produce evidenze;
9. ogni cluster riceve uno stato;
10. la dashboard mostra link originali e risultati di mercato.
