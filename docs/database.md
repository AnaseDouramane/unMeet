# Database

## Contesto

Il progetto usa SQLAlchemy e PostgreSQL come base di persistenza. Il modello presente oggi è `SourceItemModel`, definito in `app/database/models.py`.

## Modello Dati

`SourceItemModel` rappresenta un record normalizzato proveniente da una fonte esterna.

### Campi Principali

- `id`: chiave primaria interna.
- `external_id`: identificatore della fonte.
- `source`: nome della fonte, per esempio `hackernews`.
- `raw_payload`: payload originale della sorgente.
- `title`: titolo del record.
- `clean_title`: titolo pulito, se presente.
- `body`: corpo del record.
- `clean_body`: corpo pulito, se presente.
- `url`: link originale.
- `document_text`: testo composto da titolo e corpo.
- `dedup_hash`: hash normalizzato usato per il riconoscimento dei duplicati.
- `author`: autore, se disponibile.
- `published_at`: data di pubblicazione con timezone.
- `processed_at`: timestamp di elaborazione, nullable.
- `engagement_score`: metrica di engagement, se disponibile.

## Significato Di Raw E Processed

La distinzione nel progetto è semplice:

- `raw_payload` conserva la risposta originale della fonte senza perdere struttura o campi extra;
- i campi derivati, come `clean_title`, `clean_body`, `document_text` e `dedup_hash`, rappresentano la versione processata del contenuto;
- `title` e `body` nel modello possono ospitare la rappresentazione normalizzata destinata alla persistenza, mentre il payload originale resta intatto in `raw_payload`.

La pipeline di preprocessing oggi produce `PreparedDocument` con titolo e corpo puliti, ma non scrive ancora questi dati nel database.

## Perché PostgreSQL

PostgreSQL è già la base scelta nel repository e offre:

- vincoli e indici affidabili;
- supporto nativo a timezone per i timestamp;
- tipizzazione robusta per la persistenza dei dati normalizzati;
- compatibilità con `pgvector`, che è preparato nel container Docker.

## Perché JSONB

`raw_payload` usa `JSONB` perché ogni fonte può esporre una struttura diversa e il progetto deve conservare il dato originale senza imporre uno schema rigido su tutto il payload.

I test verificano esplicitamente che il campo sia mappato come `JSONB` in PostgreSQL.

## Vincoli E Indici

### `UNIQUE(source, external_id)`

Questo vincolo impedisce di salvare due volte lo stesso elemento proveniente dalla stessa fonte. È il meccanismo di base per mantenere l'idempotenza dell'ingestion.

### `INDEX(dedup_hash)`

L'indice su `dedup_hash` serve a rendere veloce il recupero dei documenti che risultano uguali dopo la normalizzazione del testo.

## Stato Attuale

Il modello è pronto per la persistenza, ma oggi il run principale del progetto si ferma alla preparazione dei documenti e non inserisce record nel database.
