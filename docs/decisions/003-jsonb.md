# ADR 003: JSONB

## Contesto

Le fonti di ingestion possono esporre payload con struttura diversa. Il progetto deve conservare i dati originali senza perdere informazioni non previste dallo schema comune.

## Decisione

Usare `JSONB` per il campo `raw_payload` di `SourceItemModel`.

## Motivazione

- il formato è adatto a payload eterogenei;
- conserva la struttura originale della risposta della fonte;
- è supportato nativamente da PostgreSQL;
- evita di modellare subito ogni campo specifico delle fonti;
- facilita l'ispezione e il debug dei dati grezzi.

## Conseguenze

- il progetto può accettare payload diversi senza migrazioni continue;
- la validazione del contenuto rilevante resta nel codice applicativo;
- la struttura del payload originale rimane recuperabile anche quando lo schema comune è più stretto.
