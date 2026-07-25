"""
embed_chunks.py — Script per generare embedding via LM Studio API

Legge i chunk generati (manual_chunks.json) e chiama l'API locale di LM Studio
per ottenere gli embedding di testo (Qwen3-Embedding-0.6B).
Salva il risultato aggiungendo il campo "embedding" a ogni chunk.
"""

import argparse
import json
import sys
from pathlib import Path

import requests
from tqdm import tqdm

def get_embedding(text: str, api_url: str, model_name: str) -> list[float]:
    payload = {
        "model": model_name,
        "input": text
    }
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(api_url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]
    except Exception as e:
        print(f"\n❌ Errore API: {e}")
        if 'response' in locals() and hasattr(response, 'text'):
            print(f"Dettagli: {response.text}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Genera embedding per i chunk del manuale")
    parser.add_argument("--input", required=True, help="File JSON di input (es. manual_chunks.json)")
    parser.add_argument("--output", required=True, help="File JSON di output (es. manual_chunks_embedded.json)")
    parser.add_argument("--api-url", default="http://127.0.0.1:1234/v1/embeddings", help="URL API LM Studio")
    parser.add_argument("--model-name", default="text-embedding-qwen3-embedding-0.6b", help="Nome del modello da passare all'API")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ File di input non trovato: {input_path}")
        sys.exit(1)

    print(f"Caricamento chunk da {input_path}...")
    with open(input_path, 'r', encoding='utf-8') as f:
        chunks = json.load(f)

    print(f"Trovati {len(chunks)} chunk.")
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Carica chunk già processati per supportare il resume
    embedded_chunks = []
    processed_ids = set()
    if output_path.exists():
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                embedded_chunks = json.load(f)
            processed_ids = {c["chunk_id"] for c in embedded_chunks}
            print(f"Ripresa da file esistente: {len(processed_ids)} chunk già elaborati.")
        except json.JSONDecodeError:
            print("File di output esistente corrotto. Verrà sovrascritto.")

    to_process = [c for c in chunks if c["chunk_id"] not in processed_ids]
    
    if not to_process:
        print("✅ Tutti i chunk hanno già un embedding.")
        sys.exit(0)

    print(f"Generazione embedding per {len(to_process)} chunk via {args.api_url}...")
    
    try:
        for chunk in tqdm(to_process, desc="Embedding"):
            embedding = get_embedding(chunk["embedding_text"], args.api_url, args.model_name)
            if embedding is None:
                print(f"Interruzione dovuta a un errore API al chunk {chunk['chunk_id']}.")
                break
                
            chunk["embedding"] = embedding
            embedded_chunks.append(chunk)
            
            # Salvataggio incrementale ogni 50 chunk per sicurezza
            if len(embedded_chunks) % 50 == 0:
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(embedded_chunks, f, ensure_ascii=False, indent=2)

    except KeyboardInterrupt:
        print("\nInterrotto dall'utente. Salvataggio parziale...")
    
    # Salvataggio finale
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(embedded_chunks, f, ensure_ascii=False, indent=2)
        
    print(f"\n✅ Salvati {len(embedded_chunks)} chunk in {output_path}")

if __name__ == "__main__":
    main()
