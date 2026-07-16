# ADR 002: SourceItem vs PreparedDocument

## Contesto

Il codice distingue tra dato grezzo in ingresso e dato preparato per gli stadi successivi. `SourceItem` rappresenta l'input dei connettori, mentre `PreparedDocument` rappresenta il risultato del preprocessing.

## Decisione

Mantenere due strutture separate:

- `SourceItem` per il dato originale;
- `PreparedDocument` per il documento pulito e normalizzato.

## Motivazione

- il dato grezzo deve restare intatto;
- il preprocessing non deve mutare l'input;
- il testo pulito e il `dedup_hash` sono derivati e vanno tenuti separati dal payload iniziale;
- la separazione rende più chiari i test e le responsabilità dei layer.

## Conseguenze

- l'ingestion può concentrarsi sul mapping della fonte;
- il preprocessing può essere testato in isolamento;
- le trasformazioni restano esplicite;
- la persistenza dovrà decidere in modo chiaro quando salvare il record grezzo e quando salvare il record processato.
