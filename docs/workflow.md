# Workflow

## Processo Di Sviluppo

Il workflow adottato dal progetto è lineare e conservativo: una modifica piccola, verificata e reviewata alla volta.

## Developer

Il Developer:

- legge il contesto del modulo interessato;
- implementa la feature minima necessaria;
- modifica solo i file coinvolti;
- esegue i test prima di proporre il commit;
- prepara il commit con messaggio Conventional Commits.

## Reviewer

Il Reviewer:

- controlla correttezza e regressioni;
- verifica che non ci siano cambi architetturali non concordati;
- conferma che la modifica resti limitata allo scope richiesto;
- approva solo quando il comportamento è coperto dai test o comunque verificato.

## Test

Prima del commit si esegue `pytest`.

Quando serve, si possono aggiungere test mirati al comportamento modificato, ma senza allargare la modifica oltre il necessario.

## Git Commit

Ogni commit deve rappresentare una sola feature o correzione coerente.

Il messaggio deve seguire Conventional Commits, per esempio:

- `docs: add initial project documentation`
- `feat: add source ingestion`
- `fix: handle empty body`

## Git Push

Dopo review e test positivi, il branch viene pushato nel remote.

## Regole Operative

- una feature per commit;
- `pytest` prima del commit;
- Conventional Commits;
- nessuna modifica architetturale senza approvazione;
- modificare solo i file necessari.
