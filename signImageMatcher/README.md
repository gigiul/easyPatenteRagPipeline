# Sign Image Matcher

Sistema per identificare i segnali stradali nelle domande del quiz usando VL (Vision Language) con few-shot learning.

## Approccio attuale

```
Immagine + domanda + contesto + few-shot → LLM → risposta diretta (Vera/Falsa)
```

Un'unica chiamata LLM che riceve:
- L'immagine del segnale
- La domanda V/F
- Il contesto dal manuale (3 chunk)
- 3-4 esempi few-shot

## Flusso Edge Function

1. Cache check → se `question_translations.explanation` esiste, ritorna subito
2. Fetch immagine (se presente) da Supabase Storage
3. Embedding della domanda (cache o genera)
4. Chunk matching → embedding search (3 chunk più rilevanti)
5. Se c'è immagine → `callLLMWithImage` (single-call con few-shot)
6. Se non c'è immagine → `callLLM` (solo testo)
7. Salva in cache
8. Traduci seconda lingua (se richiesta)

## File

| File | Scopo |
|------|-------|
| `create_table.sql` | DDL per `sign_reference_images` (DEPRECATO, da rimuovere) |
| `create_sign_to_chunk.sql` | DDL per `sign_to_chunk` (DEPRECATO, da rimuovere) |
| `extract_signs.py` | Estrae segnali dalle pagine manuallo (DEPRECATO) |
| `embed_signs.py` | Calcola embeddings (DEPRECATO) |
| `fix_chunk_ids.py` | Corregge chunk_id (DEPRECATO) |
| `populate_sign_to_chunk.py` | Popola sign_to_chunk (DEPRECATO) |
| `add_missing_signs.py` | Aggiunge segnali mancanti (DEPRECATO) |

## Few-shot examples

Gli esempi few-shot sono hardcoded nella Edge Function (`FEW_SHOT_EXAMPLES`).
Formato:
```json
{
  "description": "Descrizione visiva del segnale",
  "sign": "Nome esatto dal Codice della Strada",
  "question": "Domanda V/F",
  "answer": "Vera o Falsa"
}
```

Servono 3-4 esempi di categorie diverse (PERICOLO, DIVIETO, OBBLIGO) per mostrare il pattern al modello.

## Note

- Le tabelle `sign_reference_images` e `sign_to_chunk` sono deprecate
- L'approccio attuale (single-call con few-shot) è più semplice e preciso
- Il VL vede l'immagine e risponde direttamente, senza passaggi intermedi
