#!/usr/bin/env python3
"""
Ricalcola gli embedding di tutti i chunk con un nuovo modello.
Cancella gli embeddings esistenti e li rigenera.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://mvkxafzywzuohnbqjqmo.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im12a3hhZnp5d3p1b2huYnFqcW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MzU4ODgzMiwiZXhwIjoyMDg5MTY0ODMyfQ.Cz8AncuuZnSKdec5COxhNHGaNm5KR_Hh8aGRU261RiA")
LLM_ENDPOINT = os.environ.get("LLM_ENDPOINT", "http://localhost:1234")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-embeddinggemma-300m")
CHUNKS_PATH = Path(__file__).parent.parent / "manualChunker" / "output" / "manual_chunks.json"


def generate_embedding(text):
    payload = json.dumps({
        "model": EMBEDDING_MODEL,
        "input": text,
    }).encode()
    req = urllib.request.Request(
        f"{LLM_ENDPOINT}/v1/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
        return data["data"][0]["embedding"]


def supabase_patch(table, data, filters):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{table}?{filters}",
        data=body,
        method="PATCH",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status


def main():
    if not SUPABASE_KEY:
        print("ERROR: Set SUPABASE_KEY")
        sys.exit(1)

    print(f"Model: {EMBEDDING_MODEL}")
    print(f"Endpoint: {LLM_ENDPOINT}\n")

    # 1. Test embedding generation
    print("Test embedding generation...")
    try:
        test_emb = generate_embedding("test")
        print(f"OK - dimensions: {len(test_emb)}")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # 2. Load chunks from local file
    with open(CHUNKS_PATH) as f:
        chunks = json.load(f)
    print(f"Loaded {len(chunks)} chunks from local file\n")

    # 3. Re-embed and update each chunk in DB
    updated = 0
    failed = 0

    for i, chunk in enumerate(chunks):
        chunk_id = chunk["chunk_id"]
        embedding_text = chunk.get("embedding_text", "")

        if not embedding_text:
            print(f"[{i+1}/{len(chunks)}] SKIP: {chunk_id} (no embedding_text)")
            failed += 1
            continue

        try:
            embedding = generate_embedding(embedding_text)
            supabase_patch(
                "manual_chunks",
                {"embedding": str(embedding)},
                f"chunk_id=eq.{chunk_id}"
            )
            print(f"[{i+1}/{len(chunks)}] OK: {chunk_id} ({len(embedding)} dim)")
            updated += 1
        except Exception as e:
            print(f"[{i+1}/{len(chunks)}] ERROR: {chunk_id}: {e}")
            failed += 1

    print(f"\nDone: {updated} updated, {failed} failed")


if __name__ == "__main__":
    main()
