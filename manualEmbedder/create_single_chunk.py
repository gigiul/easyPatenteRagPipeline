#!/usr/bin/env python3
"""
create_single_chunk.py — Script per creare ed embeddare un singolo chunk personalizzato.

Genera il JSON formattato ed embeddato pronto per l'inserimento o copia/incolla su Supabase.
Basato sulla configurazione di reembed_chunks.py / embed_chunks.py.
"""

import argparse
import csv
import io
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

LLM_ENDPOINT = os.environ.get("LLM_ENDPOINT", "http://localhost:1234")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-embeddinggemma-300m")
OUTPUT_DIR = Path(__file__).parent / "output"


def generate_embedding(text: str, endpoint: str = LLM_ENDPOINT, model: str = EMBEDDING_MODEL) -> list[float]:
    """Genera l'embedding vettoriale tramite l'API dell'endpoint LLM (es. LM Studio)."""
    payload = json.dumps({
        "model": model,
        "input": text,
    }).encode("utf-8")
    
    req = urllib.request.Request(
        f"{endpoint.rstrip('/')}/v1/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["data"][0]["embedding"]
    except Exception as e:
        print(f"❌ Errore durante la generazione dell'embedding: {e}")
        print(f"   Assicurati che LM Studio sia attivo su {endpoint}")
        sys.exit(1)


def slugify(text: str) -> str:
    """Crea uno slug per il nome del file a partire dall'ID del chunk."""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', text)


def estimate_tokens(text: str) -> int:
    """Stima approssimativa dei token basata sulle parole/caratteri."""
    words = len(text.split())
    chars = len(text)
    # Stima media per la lingua italiana (circa 1.3 token per parola o char/4)
    return max(int(words * 1.3), chars // 4, 1)


CSV_FIELDS = [
    "chunk_id",
    "manual_version",
    "language",
    "chapter",
    "chapter_id",
    "section",
    "section_id",
    "subsection",
    "chunk_type",
    "category_id",
    "page_start",
    "page_end",
    "chunk_index",
    "prev_chunk_id",
    "next_chunk_id",
    "text",
    "embedding_text",
    "llm_context",
    "token_count",
    "char_count",
    "source_file",
    "article_ref",
    "keywords",
    "embedding",
]


def format_pg_array(arr: list[str] | None) -> str:
    """Formatta una lista Python nel formato array di PostgreSQL, es. {"item1","item2"}."""
    if not arr:
        return "{}"
    items_formatted = []
    for item in arr:
        s = str(item).replace("\\", "\\\\").replace('"', '\\"')
        items_formatted.append(f'"{s}"')
    return "{" + ",".join(items_formatted) + "}"


def format_pg_vector(vec: list[float] | None) -> str:
    """Formatta una lista di float nel formato stringa vettoriale, es. "[0.1, -0.2, ...]"."""
    if not vec:
        return ""
    return json.dumps(vec)


def main():
    parser = argparse.ArgumentParser(description="Crea ed embedda un singolo chunk personalizzato per Supabase.")
    parser.add_argument("--text", help="Testo principale del chunk")
    parser.add_argument("--file", help="Percorso di un file di testo da usare come contenuto del chunk")
    parser.add_argument("--chunk-id", help="ID unico del chunk (es. v1/custom/001)")
    parser.add_argument("--manual-version", default="09072026", help="Versione del manuale (default: 09072026)")
    parser.add_argument("--chapter", help="Nome del capitolo (opzionale)")
    parser.add_argument("--chapter-id", help="ID del capitolo (es. cap-ext)")
    parser.add_argument("--section", help="Nome della sezione (opzionale)")
    parser.add_argument("--section-id", help="ID della sezione (es. cap-ext-sez-01)")
    parser.add_argument("--chunk-type", default="custom_rule", help="Tipo di chunk (default: custom_rule)")
    parser.add_argument("--keywords", help="Keyword separate da virgola (es: patente, revisione)")
    parser.add_argument("--endpoint", default=LLM_ENDPOINT, help=f"Endpoint API LLM (default: {LLM_ENDPOINT})")
    parser.add_argument("--model", default=EMBEDDING_MODEL, help=f"Modello di embedding (default: {EMBEDDING_MODEL})")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Cartella di output per il CSV/JSON generato")

    args = parser.parse_args()

    # Flag per determinare se attivare la modalità interattiva
    is_interactive = not (args.text or args.file)

    # Determinazione del testo (da file, da flag o interattivo multilinea)
    text = args.text
    if not text and args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"❌ File non trovato: {file_path}")
            sys.exit(1)
        text = file_path.read_text(encoding="utf-8").strip()

    if not text:
        print("=== Creazione Chunk Singolo ===")
        print("Incolla o inserisci il TESTO del chunk.")
        print("(Su Mac/Linux premi CTRL+D su una nuova riga quando hai finito di inserire il testo):\n")
        try:
            text = sys.stdin.read().strip()
        except KeyboardInterrupt:
            print("\nOperazione annullata.")
            sys.exit(0)
        if not text:
            print("❌ Il testo non può essere vuoto.")
            sys.exit(1)

    chunk_id = args.chunk_id
    if not chunk_id:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if is_interactive:
            prompt_id = input(f"\nInserisci CHUNK ID [default: v1/custom/{timestamp}]: ").strip()
            chunk_id = prompt_id if prompt_id else f"v1/custom/{timestamp}"
        else:
            chunk_id = f"v1/custom/{timestamp}"

    chapter = args.chapter
    if chapter is None and is_interactive:
        ch_in = input("Inserisci CAPITOLO [lascia vuoto se assente]: ").strip()
        chapter = ch_in if ch_in else None

    section = args.section
    if section is None and is_interactive:
        sec_in = input("Inserisci SEZIONE [lascia vuoto se assente]: ").strip()
        section = sec_in if sec_in else None

    keywords_list = []
    if args.keywords:
        keywords_list = [k.strip() for k in args.keywords.split(",") if k.strip()]
    elif is_interactive:
        kw_in = input("Inserisci KEYWORD separate da virgola [lascia vuoto se assente]: ").strip()
        if kw_in:
            keywords_list = [k.strip() for k in kw_in.split(",") if k.strip()]

    # Costruzione embedding_text e llm_context
    header_parts = []
    if chapter:
        header_parts.append(chapter)
    if section:
        header_parts.append(section)

    if header_parts:
        header_str = " — ".join(header_parts)
        embedding_text = f"{header_str}\n\n{text}"
    else:
        embedding_text = text

    llm_context_parts = []
    if chapter:
        llm_context_parts.append(f"# {chapter}")
    if section:
        llm_context_parts.append(f"## {section}")
    llm_context_parts.append(f"\n{text}")
    llm_context_parts.append(f"\n[Manuale v{args.manual_version}]")
    llm_context = "\n".join(llm_context_parts)

    print(f"\n🔄 Generazione embedding via {args.endpoint} (modello: {args.model})...")
    embedding = generate_embedding(embedding_text, endpoint=args.endpoint, model=args.model)
    print(f"✅ Embedding generato con successo ({len(embedding)} dimensioni)!")

    # Struttura completa del chunk
    chunk_data = {
        "chunk_id": chunk_id,
        "manual_version": args.manual_version,
        "language": "it",
        "chapter": chapter,
        "chapter_id": args.chapter_id,
        "section": section,
        "section_id": args.section_id,
        "subsection": None,
        "chunk_type": args.chunk_type,
        "category_id": None,
        "page_start": None,
        "page_end": None,
        "chunk_index": 1,
        "prev_chunk_id": None,
        "next_chunk_id": None,
        "text": text,
        "embedding_text": embedding_text,
        "llm_context": llm_context,
        "token_count": estimate_tokens(text),
        "char_count": len(text),
        "source_file": ["manual_custom_entry.md"],
        "article_ref": [],
        "keywords": keywords_list,
        "embedding": embedding,
    }

    # Preparazione riga CSV per PostgreSQL / Supabase
    csv_row = []
    for field in CSV_FIELDS:
        val = chunk_data.get(field)
        if val is None:
            csv_row.append("")
        elif field in ("source_file", "article_ref", "keywords"):
            csv_row.append(format_pg_array(val))
        elif field == "embedding":
            csv_row.append(format_pg_vector(val))
        else:
            csv_row.append(str(val))

    # Generazione stringa CSV
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer, lineterminator="\n")
    writer.writerow(CSV_FIELDS)
    writer.writerow(csv_row)
    csv_string = csv_buffer.getvalue()

    # Salvataggio su file CSV e JSON
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    file_slug = slugify(chunk_id)

    csv_output_filepath = out_dir / f"single_chunk_{file_slug}.csv"
    json_output_filepath = out_dir / f"single_chunk_{file_slug}.json"

    with open(csv_output_filepath, "w", encoding="utf-8") as f:
        f.write(csv_string)

    with open(json_output_filepath, "w", encoding="utf-8") as f:
        json.dump(chunk_data, f, ensure_ascii=False, indent=2)

    print(f"\n💾 File CSV salvato in: {csv_output_filepath}")
    print(f"💾 File JSON salvato in: {json_output_filepath}")

    # Visualizzazione output CSV a schermo
    print("\n" + "=" * 60)
    print("📋 CSV PRONTO PER L'IMPORTAZIONE / COPIA-INCOLLA SU SUPABASE:")
    print("=" * 60)
    print(csv_string.strip())
    print("=" * 60)


if __name__ == "__main__":
    main()

