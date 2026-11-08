# Provare il prototipo a mano

Serve a rispondere a una domanda sola: **le conversazioni che trova sono utili a un fondatore, e lo pagherebbe?**
Non è ancora un prodotto da lanciare: oggi cerca solo su Hacker News (Reddit richiede credenziali, vedi "Limiti").

## Cosa ti serve (tutto gratuito)

- Python 3.11+ e Node 20+.
- Docker Desktop (per Postgres con pgvector) oppure un Postgres 16 con l'estensione `vector`.
- Una chiave **Groq** gratuita (console.groq.com → API Keys). Con un altro servizio compatibile OpenAI cambiano
  solo `LLM_BASE_URL`, `LLM_API_KEY` e `LLM_MODEL`.

## 1. Installazione (una volta)

```bash
git clone https://github.com/AnaseDouramane/unMeet.git && cd unMeet
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
cp .env.example .env                                      # Windows: copy .env.example .env
docker compose up -d                                      # Postgres + pgvector
```

Apri `.env` e imposta queste righe (le altre lasciale):

```text
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/unmeet
LLM_API_KEY=<la tua chiave Groq>
LLM_MODEL=openai/gpt-oss-120b        # controlla su Groq quali modelli sono disponibili
CLASSIFICATION_WORKERS=1             # il piano gratuito ha limiti di richieste al minuto
CLASSIFICATION_BATCH_SIZE=4
```

La prima esecuzione scarica il piccolo modello di embedding (circa 90 MB): è normale.

## 2. Un comando per preparare tutto

```bash
python -m scripts.prototype --owner tuaemail@esempio.com --site https://iltuo-prodotto.com
```

Fa questo, in ordine: aggiorna il database, crea il workspace "Prototype" con una **chiave API** (te la mostra una
sola volta, copiala), legge il tuo sito e propone 3–5 topic con le frasi da cercare, cerca su Hacker News gli
ultimi 90 giorni e valuta cosa trova. Senza `--site` usa 4 topic di esempio. Puoi rilanciarlo: riusa quello che c'è.
Ci vogliono alcuni minuti (la prima volta anche il download del modello).

## 3. Guardare il risultato

```bash
uvicorn app.api.app:create_app --factory --reload        # terminale 1
cd frontend && npm install && cp .env.example .env.local && npm run dev   # terminale 2
```

Apri http://localhost:3000/inbox, incolla la chiave quando te la chiede.

- **Inbox**: per ogni conversazione vedi la citazione esatta, perché corrisponde e il link all'originale.
  Tasti: `j`/`k` muoviti, `r` rilevante, `x` non rilevante, `e` risposto, `u` torna a nuovo, `d` bozza di risposta.
- **Topics**: modifica le frasi da cercare (le "Phrases to search for"). È la leva principale sui risultati.
- **Set up**: rifai l'onboarding da un altro sito.
- **Settings**: piano, chiavi API, digest email/Slack (richiedono SMTP o un webhook Slack).

## 4. Il test con i fondatori

1. Per ogni persona che vuoi provare: `python -m scripts.prototype --owner lei@esempio.com --site https://suo-sito.com`
   (o crea un workspace per ciascuno).
2. `python -m scripts.concierge digest --workspace <id> --count 5 --drafts` scrive `concierge/digest-DATA.md`
   (da incollare in una email) e `concierge/feedback-DATA.csv`.
3. Mandale il digest. Per ogni conversazione chiedi: **è utile? risponderesti?** Scrivi sì/no nelle colonne
   `useful` e `would_reply` del CSV.
4. `python -m scripts.concierge results concierge/feedback-DATA.csv --workspace <id>` aggiorna l'inbox e stampa la
   quota di utili con l'**intervallo al 95%**. Con meno di 30 risposte l'intervallo è largo: non decidere su 10 risposte.
5. Chiedi anche, a voce: *"a che prezzo mensile sarebbe troppo poco per fidarti, un affare, caro, troppo caro?"*
   Le risposte sull'uso valgono più di quelle sul prezzo, ma segnale di pagamento è ciò che conta.

Soglie suggerite per decidere (cambiale se vuoi): continuare se almeno 3 persone su 10 chiedono di proseguire e
2 accettano di pagare; fermarsi se la quota di utili resta sotto il 50% anche dopo aver migliorato le frasi.

## Limiti da conoscere (misurati, non ipotesi)

- **Solo Hacker News.** Nei test, frasi di categoria ("model hosting platform") hanno prodotto 49 post letti dal
  modello e nessuna conversazione utile; con frasi precise e prodotti concorrenti su temi da fondatori sono usciti
  3 match su 75, uno giusto, uno plausibile, uno sbagliato (con il prompt precedente). Reddit è dove vive questa
  domanda, ma serve un'app OAuth Reddit (gratis) e il controllo dei termini d'uso commerciali.
- **La precisione non è misurata.** Il test con i fondatori è il primo modo di misurarla.
- **Il filtro prima del modello è severo** (distanza 0,6): può scartare post buoni. Si regola solo con esempi
  etichettati.
- **Piano gratuito Groq:** limiti di richieste e token; se vedi errori 429 abbassa `CLASSIFICATION_WORKERS` a 1 e
  riduci `--limit`.
- **Le bozze di risposta** sono un aiuto, non un testo da pubblicare: rileggile. Dichiarano sempre l'affiliazione
  e nulla viene pubblicato da unMeet.
- Niente registrazione utenti, pagamenti o deploy: è un prototipo locale.

## Se l'inbox è vuota

1. Allarga la finestra: `--days 365`.
2. Nella pagina Topics scrivi frasi come le scriverebbe una persona ("alternative to hubspot", "looking for a tool
   to…"), non nomi di categoria.
3. Aggiungi nomi di prodotti concorrenti: sono le ricerche più precise.
4. Se dopo questo è ancora vuota, è un dato: su Hacker News quel tema non ha conversazioni. Va provato su Reddit.

## Costi

Con Groq gratuito: nessuno. Un run di 60 post usa circa 35.000 token. Con un modello a pagamento calcola il costo
dal listino del fornitore.
