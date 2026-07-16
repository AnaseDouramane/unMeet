# ADR 001: PostgreSQL

## Contesto

Il progetto conserva dati provenienti da fonti diverse e deve supportare vincoli di unicità, timestamp con timezone e un payload flessibile per i dati grezzi.

## Decisione

Usare PostgreSQL come database principale del progetto.

## Motivazione

- è già la base configurata nel repository;
- supporta bene il modello relazionale presente;
- permette vincoli e indici utili per l'idempotenza;
- si integra con SQLAlchemy;
- è compatibile con `pgvector`, già preparato nel container Docker.

## Conseguenze

- il progetto resta su uno stack unico per la persistenza;
- il modello dati può crescere senza cambiare motore;
- il payload originale può essere mantenuto vicino ai dati strutturati;
- eventuali funzionalità vettoriali potranno essere introdotte nello stesso database.
