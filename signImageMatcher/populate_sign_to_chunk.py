#!/usr/bin/env python3
"""
Popola la tabella sign_to_chunk collegando i nomi dei segnali ai chunk di testo.

Legge i chunk dal manuale e li mappa ai segnali usando il nome della sezione.

Usage:
  python3 populate_sign_to_chunk.py

Prerequisiti:
  - manual_chunks.json esistente
  - signs.json esistente
  - Tabella sign_to_chunk creata in Supabase
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://mvkxafzywzuohnbqjqmo.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
CHUNKS_PATH = Path(__file__).parent.parent / "manualChunker" / "output" / "manual_chunks.json"
SIGNS_PATH = Path(__file__).parent.parent.parent / "signs.json"


def supabase_insert(table, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{table}",
        data=body,
        method="POST",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status


def find_chunk_for_sign(sign_name, chunks):
    """Trova il chunk migliore per un segnale usando matching preciso."""
    name_upper = sign_name.upper().strip()

    # 1. Match esatto su section
    for chunk in chunks:
        section = chunk.get("section", "").upper().strip()
        if section == name_upper:
            return chunk

    # 2. Match parziale: il nome è contenuto nella sezione
    for chunk in chunks:
        section = chunk.get("section", "").upper().strip()
        if name_upper in section or section in name_upper:
            return chunk

    # 3. Match su keywords
    for chunk in chunks:
        keywords = [k.upper() for k in chunk.get("keywords", [])]
        if name_upper in keywords:
            return chunk

    return None


def main():
    if not SUPABASE_KEY:
        print("ERROR: Set SUPABASE_KEY")
        sys.exit(1)

    # Load chunks
    with open(CHUNKS_PATH) as f:
        chunks = json.load(f)
    print(f"Loaded {len(chunks)} chunks")

    # Load signs
    with open(SIGNS_PATH) as f:
        signs_data = json.load(f)
    signs = signs_data["signs"]
    print(f"Loaded {len(signs)} signs\n")

    inserted = 0
    not_found = 0

    for sign in signs:
        name = sign["name"]
        category = sign["category"]

        chunk = find_chunk_for_sign(name, chunks)

        if chunk:
            chunk_id = chunk["chunk_id"]
            section = chunk.get("section", "")
            keywords = sign.get("keywords", [])

            try:
                supabase_insert("sign_to_chunk", {
                    "sign_name": name,
                    "sign_category": category,
                    "chunk_id": chunk_id,
                    "keywords": keywords,
                })
                print(f"  OK: {name} -> {chunk_id} (section: {section})")
                inserted += 1
            except Exception as e:
                print(f"  ERROR: {name}: {e}")
        else:
            print(f"  NOT FOUND: {name}")
            not_found += 1

    print(f"\nDone: {inserted} inserted, {not_found} not found")


if __name__ == "__main__":
    main()
