"""
upload_chunks.py — Script per caricare i chunk su Supabase

Legge il file manual_chunks_embedded.json ed esegue l'upsert
nella tabella manual_chunks di Supabase.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from supabase import create_client, Client
from tqdm import tqdm

def main():
    parser = argparse.ArgumentParser(description="Carica i chunk embedded su Supabase")
    parser.add_argument("--input", required=True, help="File JSON di input (es. manual_chunks_embedded.json)")
    parser.add_argument("--supabase-url", help="URL di Supabase (se non impostato usa SUPABASE_URL env var)")
    parser.add_argument("--supabase-key", help="Service Key di Supabase (se non impostato usa SUPABASE_SERVICE_KEY env var)")
    parser.add_argument("--dry-run", action="store_true", help="Simula l'inserimento senza scrivere nel DB")
    parser.add_argument("--batch-size", type=int, default=100, help="Dimensione dei batch per l'inserimento")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ File di input non trovato: {input_path}")
        sys.exit(1)

    url = args.supabase_url or os.environ.get("SUPABASE_URL")
    key = args.supabase_key or os.environ.get("SUPABASE_SERVICE_KEY")

    if not url or not key:
        print("❌ Supabase URL o Key mancanti. Passali via argomenti o variabili d'ambiente.")
        sys.exit(1)

    print(f"Caricamento dati da {input_path}...")
    with open(input_path, 'r', encoding='utf-8') as f:
        chunks = json.load(f)

    if not chunks:
        print("Nessun chunk da caricare.")
        sys.exit(0)

    # Validazione base: controlliamo che ci sia l'embedding
    if "embedding" not in chunks[0]:
        print("⚠️ Attenzione: il primo chunk non ha un 'embedding'. Assicurati di usare il file generato da embed_chunks.py")

    print(f"Pronto a inserire {len(chunks)} chunk.")
    
    if args.dry_run:
        print("✅ Dry-run completato (nessuna operazione sul DB). Dati pronti per l'inserimento.")
        sys.exit(0)

    supabase: Client = create_client(url, key)
    
    # Per supabase-py è consigliato inviare batch per evitare timeout o payload troppo grandi
    batch_size = args.batch_size
    batches = [chunks[i:i + batch_size] for i in range(0, len(chunks), batch_size)]

    print(f"Inizio inserimento su Supabase (in {len(batches)} batch)...")
    
    success_count = 0
    try:
        for i, batch in enumerate(tqdm(batches, desc="Upserting")):
            # Rimuoviamo campi non nel DB se ce ne fossero, ma i nostri json combaciano col DB
            response = supabase.table("manual_chunks").upsert(
                batch, 
                on_conflict="chunk_id,manual_version"
            ).execute()
            
            # Con returning=minimal (default o no) supabase-py restituisce data. 
            # Per contare il successo:
            success_count += len(batch)
            
    except Exception as e:
        print(f"\n❌ Errore durante l'inserimento al batch {i+1}: {e}")
        sys.exit(1)

    print(f"\n✅ Upsert completato con successo: {success_count}/{len(chunks)} chunk elaborati.")

if __name__ == "__main__":
    main()
