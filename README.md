# ragPipeline — Pipeline RAG per il Manuale della Patente

Pipeline che converte il manuale della patente (PDF) in chunk strutturati per RAG.

## Architettura

```
PDF Manuale → PNG → OCR → MD → Chunk → Embedding → Supabase
```

## Directory

```
ragPipeline/
├── imageTranscribe/          # FASE 1: OCR
│   ├── transcribe_images.py
│   └── manualImages/         # Output: file MD
│
├── manualChunker/            # FASE 2: Chunking
│   ├── manual_chunker.py
│   └── output/
│       └── manual_chunks.json
│
├── manualEmbedder/           # FASE 3: Embedding
│   ├── embed_chunks.py
│   ├── reembed_chunks.py     # Re-embedding con nuovo modello
│   ├── test_search.py        # Test ricerca chunk
│   └── output/
│       └── manual_chunks_embedded.json
│
├── manualUploader/           # FASE 4: Upload
│   ├── upload_chunks.py
│   └── migrations/
│       └── 001_create_manual_chunks.sql
│
└── manualePatente/           # Sorgente
    ├── manual-page-*.png     # 128 pagine
    └── scuolaguida-manuale-teoria-A1-A-B.pdf
```

## Esecuzione

### Prerequisiti
- LM Studio in esecuzione su localhost:1234
- Modelli caricati: embedding (text-embedding-embeddinggemma-300m)
- Python 3.10+ con dipendenze installate

### Pipeline completa

```bash
# FASE 1: OCR (trasforma PNG in MD)
cd imageTranscribe
python3 transcribe_images.py

# FASE 2: Chunking (MD → JSON strutturato)
cd ../manualChunker
python3 manual_chunker.py --pages-dir ../imageTranscribe/manualImages/

# FASE 3: Embedding (JSON → JSON con vettori)
cd ../manualEmbedder
python3 embed_chunks.py

# FASE 4: Upload (JSON → Supabase)
cd ../manualUploader
SUPABASE_URL=... SUPABASE_KEY=... python3 upload_chunks.py

# RE-EMBEDDING (cambio modello)
cd ../manualEmbedder
SUPABASE_KEY=... EMBEDDING_MODEL=text-embedding-embeddinggemma-300m python3 reembed_chunks.py
```

## Tabella manual_chunks

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `chunk_id` | text | ID deterministico (es. `v1/cap-02/sez-03/001`) |
| `chapter` | text | Nome capitolo (es. "Segnali di Pericolo") |
| `section` | text | Nome sezione (es. "DOSSO") |
| `chunk_type` | text | definition, sign_description, rule, sanction_table |
| `text` | text | Testo del chunk |
| `embedding_text` | text | Testo usato per l'embedding |
| `llm_context` | text | Contesto formattato per il LLM |
| `embedding` | vector(768) | Vettore embeddinggemma-300m |
| `article_ref` | _text | Riferimenti al Codice della Strada |
| `keywords` | _text | Parole chiave estratte |

## Note

- Le pagine 001-060 contengono le definizioni dei segnali con le immagini
- Gli embedding devono usare lo stesso modello di quelli nel resto del sistema
- L'identificazione segnali avviene nell'Edge Function con VL + few-shot
