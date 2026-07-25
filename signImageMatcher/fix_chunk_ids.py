#!/usr/bin/env python3
"""
Trova e assegna i chunk_id mancanti nella tabella sign_reference_images.
Confronta sign_name con le sezioni dei manual_chunks.
"""
import json, os, sys, urllib.request
from pathlib import Path

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://mvkxafzywzuohnbqjqmo.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
CHUNKS_PATH = Path(__file__).parent.parent / "manualChunker" / "output" / "manual_chunks.json"


def supabase_get(table, select="*", filters=""):
    url = f"{SUPABASE_URL}/rest/v1/{table}?select={select}"
    if filters: url += f"&{filters}"
    req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def supabase_patch(table, data, filters):
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1/{table}?{filters}", data=body, method="PATCH",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                 "Content-Type": "application/json", "Prefer": "return=minimal"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status


def find_best_chunk(sign_name, chunks):
    """Trova il chunk migliore per un segnale usando matching flessibile."""
    name_upper = sign_name.upper().strip()

    # 1. Match esatto
    for chunk in chunks:
        section = chunk.get("section", "").upper().strip()
        if section == name_upper:
            return chunk.get("chunk_id")

    # 2. Match parziale (il nome è contenuto nella sezione)
    for chunk in chunks:
        section = chunk.get("section", "").upper().strip()
        if name_upper in section or section in name_upper:
            return chunk.get("chunk_id")

    # 3. Match su keywords
    name_words = set(name_upper.split())
    best_chunk = None
    best_score = 0
    for chunk in chunks:
        section = chunk.get("section", "").upper()
        keywords = set(chunk.get("keywords", []))
        section_words = set(section.split())
        score = len(name_words & section_words) + len(name_words & keywords)
        if score > best_score:
            best_score = score
            best_chunk = chunk.get("chunk_id")

    if best_score >= 2:
        return best_chunk

    return None


def main():
    if not SUPABASE_KEY:
        print("ERROR: Set SUPABASE_KEY"); sys.exit(1)

    # Load chunks
    with open(CHUNKS_PATH) as f:
        chunks = json.load(f)
    print(f"Loaded {len(chunks)} chunks")

    # Get signs without chunk_id
    signs = supabase_get("sign_reference_images", "id,sign_name,chunk_id", "chunk_id.is.null")
    print(f"Found {len(signs)} signs without chunk_id\n")

    fixed = 0
    for sign in signs:
        chunk_id = find_best_chunk(sign["sign_name"], chunks)
        if chunk_id:
            try:
                supabase_patch("sign_reference_images", {"chunk_id": chunk_id}, f"id=eq.{sign['id']}")
                print(f"  FIXED: {sign['sign_name']} -> {chunk_id}")
                fixed += 1
            except Exception as e:
                print(f"  ERROR: {sign['sign_name']}: {e}")
        else:
            print(f"  NOT FOUND: {sign['sign_name']}")

    print(f"\nDone: {fixed}/{len(signs)} fixed")


if __name__ == "__main__":
    main()
