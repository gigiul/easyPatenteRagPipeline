# Manual Chunker — Pipeline RAG per il manuale patente

Converte i 128 file `.md` (uno per pagina, OCR via GLM) in chunk gerarchici
(capitolo → sezione) pronti per embedding e inserimento in Supabase pgvector.

## Setup

```bash
pip install tiktoken
```

## Uso

```bash
python manual_chunker.py --pages-dir manual_pages/ --manual-version "2024-ed3"
```

Opzioni:
- `--output nome.json` — file di output (default: `manual_chunks.json`)
- `--max-tokens N` — token massimi per chunk prima dello split (default: 400)

## Come funziona (in breve)

1. **Capitolo** ("Lezione N") → rilevato in modo **deterministico** leggendo
   l'Indice (ultima pagina del manuale), che riporta i numeri di pagina
   stampati di inizio di ogni Lezione. Nessuna euristica o LLM necessaria
   per questo livello.
2. **Offset pagina** → viene calcolato automaticamente l'offset costante tra
   il numero del file (`manual-page-004.md`) e il numero stampato nel testo
   (es. pagina "1"). Sui campioni forniti: offset = **+3** su tutte le pagine
   testate. Questo converte "Lezione N inizia a pag. stampata X" nel file
   corretto.
3. **Sezione** → ogni riga interamente MAIUSCOLA (es. `STRADA`,
   `DIREZIONE OBBLIGATORIA DIRITTO`) apre una nuova sezione; il testo fino
   alla prossima riga maiuscola ne è il corpo.
4. **Continuità tra pagine** → gestiti esplicitamente due artefatti OCR
   osservati nei campioni:
   - **Sillabazione**: una riga finisce con `-` e la pagina successiva
     inizia con lettera minuscola → parola ricomposta (es. `"non in-"` +
     `"dica"` → `"non indica"`).
   - **Overlap duplicato**: la pagina successiva ripete la coda della frase
     precedente prima di proseguire con contenuto nuovo → la sovrapposizione
     viene rilevata (minimo 15 caratteri) e scartata.
5. **subsection** è sempre `null` in questa versione — nei campioni non
   emerge un terzo livello esplicito nel testo. Il campo resta nello schema
   per un affinamento futuro.

## Cosa verificare dopo l'esecuzione

Lo script stampa un **report QA** con:
- Pagine attese ma mancanti nella cartella (per capitolo)
- Capitoli senza nessuna sezione rilevata (possibile problema di parsing)
- Statistiche token per chunk (min/max/media)
- Quanti chunk hanno un `category_id` assegnato

**Da controllare manualmente prima dell'uso in produzione:**

1. **`CHAPTER_CATEGORY_ID`** (in cima allo script) — mappa solo le Lezioni
   2-11 (segnaletica) e la 14 (precedenza/incroci) alle categorie quiz
   esistenti, perché sono le uniche con corrispondenza 1:1 certa. Le altre
   19 Lezioni hanno `category_id = null`: se vuoi collegarle a categorie
   quiz esistenti, serve sapere come l'app consolida le 30 Lezioni in 14
   categorie (alcune Lezioni potrebbero non avere ancora una categoria
   quiz corrispondente).

2. **`CHAPTER_CHUNK_TYPE_DEFAULT`** — assegna `chunk_type` per capitolo
   (default ragionevole basato sui titoli), con override automatico verso
   `sanction_table` se il testo contiene parole come "sanzione", "€",
   "punti patente". Verifica su un campione reale se i capitoli 19-30
   (equipaggiamento, patenti, incidenti, ecc.) necessitano di default diversi.

3. **`ARTICLE_REF_RE`** — il regex per riferimenti "Art. X CdS" non ha
   trovato corrispondenze nei 4 campioni forniti (nessuno ne conteneva).
   Verifica il pattern su pagine reali che citano articoli del Codice
   (probabilmente nei capitoli su sanzioni/patenti) e aggiusta se necessario.

4. **Pagine con OCR anomalo** — se il report QA segnala capitoli senza
   sezioni o con pochissimo testo, apri quelle pagine `.md` manualmente:
   probabile che l'euristica sulle intestazioni MAIUSCOLE non abbia
   trovato corrispondenze (formattazione OCR diversa dal solito).

## Schema di output

Ogni chunk nel JSON generato include (embedding escluso, da generare in
uno step separato):

```json
{
  "chunk_id": "segnali-di-pericolo/dosso/001",
  "manual_version": "2024-ed3",
  "chapter": "Segnali di Pericolo",
  "chapter_id": "cap-02",
  "section": "DOSSO",
  "section_id": "cap-02-sez-03",
  "subsection": null,
  "chunk_type": "sign_description",
  "article_ref": [],
  "page_start": 4,
  "page_end": 4,
  "chunk_index": 1,
  "prev_chunk_id": "...",
  "next_chunk_id": "...",
  "text": "...",
  "embedding_text": "Segnali di Pericolo — DOSSO\n\n...",
  "token_count": 137,
  "keywords": ["dosso", "indica"],
  "category_id": "1c72e436-7a7f-4547-8f0e-b40f6fea7294"
}
```

## Schema database (Supabase)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE public.manual_chunks (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  chunk_id text NOT NULL,
  manual_version text NOT NULL,
  chapter text,
  chapter_id text,
  section text,
  section_id text,
  subsection text,
  chunk_type text NOT NULL DEFAULT 'rule',
  article_ref text[],
  page_start int4,
  page_end int4,
  chunk_index int4,
  prev_chunk_id text,
  next_chunk_id text,
  text text NOT NULL,
  embedding_text text NOT NULL,
  token_count int4,
  keywords text[],
  embedding vector(1536),
  category_id uuid,
  created_at timestamptz DEFAULT now(),
  CONSTRAINT manual_chunks_pkey PRIMARY KEY (id),
  CONSTRAINT manual_chunks_chunk_id_key UNIQUE (chunk_id),
  CONSTRAINT manual_chunks_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.categories(id)
);

-- Collegamento chunk <-> domande quiz (popolato in un passaggio successivo,
-- es. via similarità tra embedding, non generato da questo script)
CREATE TABLE public.manual_chunk_questions (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  chunk_id uuid NOT NULL,
  question_id uuid NOT NULL,
  relevance_score float4,
  created_at timestamptz DEFAULT now(),
  CONSTRAINT manual_chunk_questions_pkey PRIMARY KEY (id),
  CONSTRAINT manual_chunk_questions_chunk_id_fkey FOREIGN KEY (chunk_id) REFERENCES public.manual_chunks(id),
  CONSTRAINT manual_chunk_questions_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.questions(id)
);
```

`chunk_id` è `UNIQUE` (non PK) così l'upsert per nuove edizioni del manuale
usa `ON CONFLICT (chunk_id) DO UPDATE` senza duplicare, mentre l'`id` uuid
resta stabile per le foreign key. `prev_chunk_id`/`next_chunk_id` sono testo
puro (non FK) per evitare riferimenti forward durante l'inserimento bulk.

## Prossimi passi (fuori scope di questo script)

1. Generare gli embedding (`embedding_text` → vettore) e popolare la colonna
   `embedding` prima dell'insert.
2. Collegare i chunk alle domande quiz esistenti (`manual_chunk_questions`),
   probabilmente via similarità semantica tra l'embedding del chunk e
   l'embedding del testo della domanda, una volta che anche le domande
   hanno un proprio embedding.
