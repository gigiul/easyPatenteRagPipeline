# Pipeline RAG per il Manuale Patente — Piano di Implementazione

## Contesto

Il sistema converte un manuale di teoria per la patente di guida (30 Lezioni, ~128 pagine Markdown da OCR) in chunk semantici, genera embedding vettoriali e li inserisce in Supabase per la ricerca semantica in un'app di quiz.

La pipeline ha 4 fasi indipendenti: **OCR → Chunking → Embedding → Supabase**.

---

## Analisi: Categorie Supabase vs Indice del Manuale

Ho incrociato le **24 categorie** (12 normali + 12 hard) su Supabase con le **30 Lezioni** dell'indice. Ecco il mapping completo corretto:

| sort | Categoria Supabase (IT, `is_hard=false`)                                        | UUID (non-hard)                            | Lezioni mappate  |
|------|---------------------------------------------------------------------------------|--------------------------------------------|------------------|
| 1    | Veicoli e Strade                                                                | `41d2be33-3ca3-41f5-809f-ce2329ae9628`     | **1**             |
| 2    | Segnali di Pericolo                                                             | `1c72e436-7a7f-4547-8f0e-b40f6fea7294`     | **2**             |
| 3    | Segnali di Precedenza                                                           | `1a693ebd-3e77-49da-a5cb-aefd34af0d8e`     | **3**             |
| 4    | Segnali di Divieto                                                              | `1055628b-9e4a-4544-92fd-60167704c315`     | **4**             |
| 5    | Segnali di Obbligo                                                              | `cfecfe52-5925-443e-a798-5adff605c489`     | **5**             |
| 6    | Segnali di Indicazione                                                          | `fd787783-6b5b-4e0a-a0b4-2173aad17c37`     | **6**             |
| 7    | Segnali temporanei e di cantiere. Segnali complementari                         | `4caf0f96-d5a9-49e7-b345-bae6277295b7`     | **7, 8**          |
| 8    | Pannelli Integrativi                                                            | `cf7cd590-6fdc-4c7c-8b64-6dbade75c49d`     | **9**             |
| 9    | Segnaletica luminosa e manuale                                                  | `9ae4ea7e-03e8-4f62-963a-ebea4fbb42e8`     | **10**            |
| 10   | Segnaletica orizzontale                                                         | `add74848-59a1-4150-ba8b-1a01678ee745`     | **11**            |
| 11   | Luci, specchi, dispositivi del veicolo. Posizione di guida                      | `f1a2b3c4-9d8e-4a7b-8c1d-1e2f3a4b5001`     | **19, 20**        |
| 12   | Regolazione e limiti di velocità. Distanza di sicurezza                         | `a2b3c4d5-8e7f-4b6c-9d1e-2f3a4b5c6002`     | **12**            |
| 13   | Posizione dei veicoli sulla carreggiata, svolte e manovre varie                 | `b3c4d5e6-7f8a-4c5d-9e1f-3a4b5c6d7003`     | **13**            |
| 14   | Precedenze                                                                      | `2ee255f6-5157-4af3-a6e1-2baa80df62dd`     | **14**            |
| 15   | Sorpasso                                                                        | `a1111111-1111-4a1a-8a1a-111111111115`     | **15**            |
| 16   | Fermata e sosta dei veicoli                                                     | `a2222222-2222-4b2b-8b2b-222222222216`     | **16**            |
| 17   | Trasporto di persone, carico, ingombro della carreggiata ecc. Autostrade        | `a3333333-3333-4c3c-8c3c-333333333317`     | **17, 18, 22**    |
| 18   | Comportamento corretto del conducente                                           | `a4444444-4444-4d4d-8d4d-444444444418`     | **21, 24, 25**    |
| 19   | Cause più frequenti di incidenti. Incidenti. Primo soccorso. RCA                | `a5555555-5555-4e5e-8e5e-555555555519`     | **25, 26, 27**    |
| 20   | Patente e documenti                                                             | `c1111111-1111-4a1a-8a1a-111111111120`     | **23, 24**        |
| 21   | Tenuta di strada e manutenzione del veicolo                                     | `c2222222-2222-4b2b-8b2b-222222222121`     | **29, 30**        |
| 22   | Inquinamento, spie e quiz di riepilogo                                          | `c3333333-3333-4c3c-8c3c-333333333122`     | **28**            |
| 23   | Veicoli a due ruote                                                             | `c4444444-4444-4d4d-8d4d-444444444123`     | *(cross-lezione)* |
| 24   | Veicoli con rimorchi                                                            | `c5555555-5555-4e5e-8e5e-555555555124`     | *(cross-lezione)* |

> [!IMPORTANT]
> **Problemi identificati nel chunker attuale:**
> 1. `CHAPTER_CATEGORY_ID` mappa solo 10 Lezioni su 30 — le altre 20 hanno `null`. Ora con le 24 categorie Supabase **tutte le 30 Lezioni** possono essere mappate.
> 2. Le categorie 23 e 24 ("Veicoli a due ruote", "Veicoli con rimorchi") sono **cross-lezione**: i contenuti rilevanti sono sparsi in più Lezioni. Queste sono categorie dell'app quiz, non del manuale. Per il chunker vanno lasciate a `null` e gestite a livello quiz.
> 3. Alcune Lezioni vengono mappate a **più di una categoria** (es. Lezione 25 → cat 18 + cat 19). Mantengo un mapping 1:1 Lezione→categoria primaria.
> 4. Campi mancanti nello schema attuale vs lo schema richiesto: `language`, `llm_context`, `char_count`, `source_file`.

---

## User Review Required

> [!IMPORTANT]
> **Mapping Lezione→Categoria**: alcune Lezioni afferiscono a più categorie (es. Lezione 24 "Obbligo verso funzionari, Documenti di Guida, Uso di Occhiali" potrebbe essere sia cat 18 "Comportamento" sia cat 20 "Patente e documenti"). Ho assegnato ciascuna Lezione alla categoria primaria più affine. Vedi la tabella sopra — confermi o vuoi aggiustare qualche mapping?

> [!IMPORTANT]
> **Modello di embedding**: usi **Qwen3-Embedding-0.6B-GGUF** via `llama-cpp-python` localmente? Qual è il servizio/server locale che lo espone? 
> - NO uso LM Studio via api, questo è un esempio di chiamata:
curl http://127.0.0.1:1234/v1/embeddings \-H "Content-Type: application/json" \-d '{
  "model": "text-embedding-qwen3-embedding-0.6b",
  "input": "Some text to embed"
}'

La risposta della chiamata è: {
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "embedding": [
        -0.027323966845870018,
        0.01018007192760706,
       ...
      ],
      "index": 0
    }
  ],
  "model": "text-embedding-qwen3-embedding-0.6b",
  "usage": {
    "prompt_tokens": 0,
    "total_tokens": 0
  }
}% 

> [!WARNING]
> **Dimensione embedding nel DB**: il README attuale specifica `vector(1536)` (dimensione OpenAI), ma Qwen3-Embedding-0.6B produce vettori da **1024** dimensioni. La migrazione va aggiornata.

---

## Open Questions

1. **Vuoi che le categorie cross-lezione (23, 24) vengano assegnate anche ai chunk pertinenti del manuale?** Questo richiederebbe un mapping a livello di sezione (non di Lezione), basato su parole chiave. R: No
2. **Versionamento**: quale stringa usare come `manual_version`? (es. `"2024-ed3"` come nel README, o la data di elaborazione `"09072026"` come nei chunk di test?) R: 09072026

---

## Proposed Changes

### Struttura delle cartelle finale

```
patente/
├── imageTranscribe/          # OCR (già fatto)
│   ├── transcribe_images.py
│   └── manualImages/
│       ├── manual-page-004.md
│       └── ...
├── manualChunker/            # Fase 2: Chunking
│   ├── manual_chunker.py     # [MODIFY] — migliorato
│   ├── README.md             # [MODIFY] — aggiornato
│   └── output/               # [NEW] directory di output
│       └── manual_chunks.json
├── manualEmbedder/           # [NEW] Fase 3: Embedding
│   ├── embed_chunks.py       # Genera embedding da chunks.json
│   ├── requirements.txt
│   └── output/
│       └── manual_chunks_embedded.json
├── manualUploader/           # [NEW] Fase 4: Upload Supabase
│   ├── upload_chunks.py      # Inserisce/aggiorna su Supabase
│   ├── requirements.txt
│   └── migrations/
│       └── 001_create_manual_chunks.sql
└── supabase_backup/          # Backup esistente
```

---

### Componente 1: Chunker (miglioramento)

#### [MODIFY] [manual_chunker.py](file:///Users/luigidalleaste/Documents/luigi/sw/patente/manualChunker/manual_chunker.py)

Modifiche principali:

1. **`CHAPTER_CATEGORY_ID` completo**: mapping di tutte le 30 Lezioni alle 24 categorie Supabase, con i UUID reali dalla query.

```python
CHAPTER_CATEGORY_ID = {
    1:  "41d2be33-3ca3-41f5-809f-ce2329ae9628",  # Veicoli e Strade
    2:  "1c72e436-7a7f-4547-8f0e-b40f6fea7294",  # Segnali di Pericolo
    3:  "1a693ebd-3e77-49da-a5cb-aefd34af0d8e",  # Segnali di Precedenza
    4:  "1055628b-9e4a-4544-92fd-60167704c315",  # Segnali di Divieto
    5:  "cfecfe52-5925-443e-a798-5adff605c489",  # Segnali di Obbligo
    6:  "fd787783-6b5b-4e0a-a0b4-2173aad17c37",  # Segnali di Indicazione
    7:  "4caf0f96-d5a9-49e7-b345-bae6277295b7",  # Segnali temporanei/cantiere/complementari
    8:  "4caf0f96-d5a9-49e7-b345-bae6277295b7",  # Segnali complementari (stessa cat di 7)
    9:  "cf7cd590-6fdc-4c7c-8b64-6dbade75c49d",  # Pannelli Integrativi
    10: "9ae4ea7e-03e8-4f62-963a-ebea4fbb42e8",  # Segnaletica luminosa e manuale
    11: "add74848-59a1-4150-ba8b-1a01678ee745",  # Segnaletica orizzontale
    12: "a2b3c4d5-8e7f-4b6c-9d1e-2f3a4b5c6002",  # Regolazione velocità, distanza sicurezza
    13: "b3c4d5e6-7f8a-4c5d-9e1f-3a4b5c6d7003",  # Posizione veicoli, svolte, manovre
    14: "2ee255f6-5157-4af3-a6e1-2baa80df62dd",  # Precedenze
    15: "a1111111-1111-4a1a-8a1a-111111111115",  # Sorpasso
    16: "a2222222-2222-4b2b-8b2b-222222222216",  # Fermata e sosta
    17: "a3333333-3333-4c3c-8c3c-333333333317",  # Ingombro carreggiata
    18: "a3333333-3333-4c3c-8c3c-333333333317",  # Circolazione autostrade (stessa cat di 17)
    19: "f1a2b3c4-9d8e-4a7b-8c1d-1e2f3a4b5001",  # Luci, specchi, dispositivi
    20: "f1a2b3c4-9d8e-4a7b-8c1d-1e2f3a4b5001",  # Spie e simboli (stessa cat di 19)
    21: "a4444444-4444-4d4d-8d4d-444444444418",  # Comportamento conducente (cinture, casco)
    22: "a3333333-3333-4c3c-8c3c-333333333317",  # Trasporto persone/carico (stessa cat di 17)
    23: "c1111111-1111-4a1a-8a1a-111111111120",  # Patente e documenti
    24: "c1111111-1111-4a1a-8a1a-111111111120",  # Obbligo funzionari, documenti (stessa cat)
    25: "a5555555-5555-4e5e-8e5e-555555555519",  # Cause incidenti
    26: "a5555555-5555-4e5e-8e5e-555555555519",  # Comportamento in caso di incidente, RCA
    27: "a5555555-5555-4e5e-8e5e-555555555519",  # Alcol, stupefacenti, primo soccorso
    28: "c3333333-3333-4c3c-8c3c-333333333122",  # Inquinamento
    29: "c2222222-2222-4b2b-8b2b-222222222121",  # Elementi costitutivi veicolo
    30: "c2222222-2222-4b2b-8b2b-222222222121",  # Stabilità e tenuta di strada
}
```

2. **Campi mancanti aggiunti allo schema del chunk**:
   - `language`: `"it"` (costante per ora)
   - `llm_context`: testo formattato con contesto gerarchico completo (capitolo + sezione + testo) ottimizzato per essere passato a un LLM come contesto
   - `char_count`: `len(text)`
   - `source_file`: nome del file sorgente (es. `"manual-page-004.md"`)

3. **`llm_context` format**:
```
# Lezione 2 — Segnali di Pericolo
## STRADA DEFORMATA

Indica a 150 metri una strada in cattivo stato, dissestata o con pavimentazione
irregolare (asfalto rovinato, buche, fossi) ...

[Pagine: 4-4 | Manuale v2024-ed3]
```

4. **`source_file`**: tracciato per ogni chunk come lista dei file coinvolti (quando una sezione copre più pagine).

5. **`CHAPTER_CHUNK_TYPE_DEFAULT` aggiornato** per i capitoli 12-30 con tipi più specifici:

```python
CHAPTER_CHUNK_TYPE_DEFAULT = {
    1: "definition",
    2: "sign_description", 3: "sign_description", 4: "sign_description",
    5: "sign_description", 6: "sign_description", 7: "sign_description",
    8: "sign_description", 9: "sign_description", 10: "sign_description",
    11: "sign_description",
    12: "rule", 13: "rule", 14: "rule", 15: "rule", 16: "rule",
    17: "rule", 18: "rule",
    19: "device_description", 20: "device_description",
    21: "safety_rule", 22: "rule",
    23: "license_rule", 24: "license_rule",
    25: "safety_rule", 26: "procedure", 27: "health_rule",
    28: "environment_rule", 29: "vehicle_component", 30: "vehicle_component",
}
```

6. **`chunk_id` deterministico e versioned**: formato `v1/cap-02/sez-03/001` per evitare collisioni e permettere upsert.

---

### Componente 2: Embedder (nuovo)

#### [NEW] `manualEmbedder/embed_chunks.py`

Responsabilità:
- Legge `manual_chunks.json` (output del chunker)
- Per ogni chunk, genera l'embedding del campo `embedding_text` usando **Qwen3-Embedding-0.6B-GGUF** via `llama-cpp-python`
- Salva `manual_chunks_embedded.json` con il campo `embedding` aggiunto (lista di float)
- Supporta batch processing e resume (se interrotto, riprende dall'ultimo chunk)
- Mostra progress bar con stima tempo

```bash
python embed_chunks.py \
  --input ../manualChunker/output/manual_chunks.json \
  --output output/manual_chunks_embedded.json \
  --model-path /path/to/qwen3-embedding-0.6b.gguf \
  --batch-size 32
```

---

### Componente 3: Uploader Supabase (nuovo)

#### [NEW] `manualUploader/upload_chunks.py`

Responsabilità:
- Legge `manual_chunks_embedded.json`
- Esegue upsert su `manual_chunks` (usando `chunk_id` come chiave di conflitto)
- Supporta `--dry-run` per validare prima dell'inserimento
- Verifica integrità post-inserimento (count, campioni)

```bash
python upload_chunks.py \
  --input ../manualEmbedder/output/manual_chunks_embedded.json \
  --supabase-url $SUPABASE_URL \
  --supabase-key $SUPABASE_SERVICE_KEY \
  --dry-run
```

#### [NEW] `manualUploader/migrations/001_create_manual_chunks.sql`

```sql
-- Abilita pgvector
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.manual_chunks (
  id             uuid         NOT NULL DEFAULT gen_random_uuid(),
  chunk_id       text         NOT NULL,
  manual_version text         NOT NULL,
  language       text         NOT NULL DEFAULT 'it',

  -- Struttura gerarchica
  chapter        text,
  chapter_id     text,
  section        text,
  section_id     text,
  subsection     text,

  -- Classificazione
  chunk_type     text         NOT NULL DEFAULT 'rule',
  category_id    uuid,

  -- Posizione
  page_start     int4,
  page_end       int4,
  chunk_index    int4,
  prev_chunk_id  text,
  next_chunk_id  text,

  -- Contenuti
  text           text         NOT NULL,
  embedding_text text         NOT NULL,
  llm_context    text         NOT NULL,
  token_count    int4,
  char_count     int4,
  source_file    text[],

  -- Metadati
  article_ref    text[],
  keywords       text[],

  -- Embedding (Qwen3-0.6B = 1024 dims)
  embedding      vector(1024),

  -- Timestamps
  created_at     timestamptz  DEFAULT now(),
  updated_at     timestamptz  DEFAULT now(),

  CONSTRAINT manual_chunks_pkey PRIMARY KEY (id),
  CONSTRAINT manual_chunks_chunk_id_version_key UNIQUE (chunk_id, manual_version),
  CONSTRAINT manual_chunks_category_id_fkey FOREIGN KEY (category_id)
    REFERENCES public.categories(id) ON DELETE SET NULL
);

-- Indice per ricerca vettoriale (IVFFlat per dataset piccoli)
CREATE INDEX IF NOT EXISTS manual_chunks_embedding_idx
  ON public.manual_chunks
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 20);

-- Indici per query frequenti
CREATE INDEX IF NOT EXISTS manual_chunks_chapter_id_idx ON public.manual_chunks(chapter_id);
CREATE INDEX IF NOT EXISTS manual_chunks_category_id_idx ON public.manual_chunks(category_id);
CREATE INDEX IF NOT EXISTS manual_chunks_manual_version_idx ON public.manual_chunks(manual_version);
CREATE INDEX IF NOT EXISTS manual_chunks_language_idx ON public.manual_chunks(language);

-- RLS (Read-only per utenti autenticati)
ALTER TABLE public.manual_chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "manual_chunks_read_policy"
  ON public.manual_chunks FOR SELECT
  TO authenticated
  USING (true);

-- Funzione di ricerca semantica
CREATE OR REPLACE FUNCTION match_manual_chunks(
  query_embedding vector(1024),
  match_count int DEFAULT 5,
  filter_category_id uuid DEFAULT NULL,
  filter_language text DEFAULT 'it'
)
RETURNS TABLE (
  id uuid,
  chunk_id text,
  chapter text,
  section text,
  llm_context text,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    mc.id,
    mc.chunk_id,
    mc.chapter,
    mc.section,
    mc.llm_context,
    1 - (mc.embedding <=> query_embedding) AS similarity
  FROM public.manual_chunks mc
  WHERE mc.language = filter_language
    AND (filter_category_id IS NULL OR mc.category_id = filter_category_id)
    AND mc.embedding IS NOT NULL
  ORDER BY mc.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Tabella di collegamento chunk ↔ domande quiz
CREATE TABLE IF NOT EXISTS public.manual_chunk_questions (
  id              uuid      NOT NULL DEFAULT gen_random_uuid(),
  chunk_id        uuid      NOT NULL,
  question_id     uuid      NOT NULL,
  relevance_score float4,
  created_at      timestamptz DEFAULT now(),
  CONSTRAINT manual_chunk_questions_pkey PRIMARY KEY (id),
  CONSTRAINT manual_chunk_questions_chunk_fkey FOREIGN KEY (chunk_id)
    REFERENCES public.manual_chunks(id) ON DELETE CASCADE,
  CONSTRAINT manual_chunk_questions_question_fkey FOREIGN KEY (question_id)
    REFERENCES public.questions(id) ON DELETE CASCADE,
  CONSTRAINT manual_chunk_questions_unique UNIQUE (chunk_id, question_id)
);
```

---

## Verification Plan

### Automated Tests

```bash
# 1. Esegui il chunker aggiornato su tutte le 122 pagine
python manual_chunker.py \
  --pages-dir ../imageTranscribe/manualImages/ \
  --manual-version "09072026" \
  --output output/manual_chunks.json

# 2. Verifica JSON valido e schema completo
python -c "
import json
with open('output/manual_chunks.json') as f:
    chunks = json.load(f)
required = ['chunk_id','manual_version','language','chapter','chapter_id',
            'section','section_id','subsection','chunk_type','category_id',
            'page_start','page_end','chunk_index','prev_chunk_id','next_chunk_id',
            'text','embedding_text','llm_context','token_count','char_count','source_file']
for c in chunks:
    missing = [k for k in required if k not in c]
    assert not missing, f'Chunk {c[\"chunk_id\"]} missing: {missing}'
# Verifica che tutti i chunk abbiano category_id
with_cat = sum(1 for c in chunks if c['category_id'])
print(f'{with_cat}/{len(chunks)} chunk con category_id')
assert with_cat == len(chunks), 'Ci sono chunk senza category_id'
print('✅ Schema OK')
"

# 3. Embedding (dopo aver configurato il modello)
python embed_chunks.py \
  --input ../manualChunker/output/manual_chunks.json \
  --output output/manual_chunks_embedded.json

# 4. Upload dry-run
python upload_chunks.py \
  --input ../manualEmbedder/output/manual_chunks_embedded.json \
  --dry-run
```

### Manual Verification

- Controllare 3-5 chunk a campione per verificare che `llm_context` sia ben formattato
- Verificare che i chunk alle transizioni di pagina non abbiano testo troncato o duplicato
- Dopo l'upload, eseguire una query vettoriale di test da Supabase SQL editor
