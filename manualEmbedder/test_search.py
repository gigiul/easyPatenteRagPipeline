#!/usr/bin/env python3
"""
Test manuale: genera embedding per una domanda e trova i chunk più simili.
"""
import json
import sys
import urllib.request

LLM_ENDPOINT = "http://localhost:1234"
EMBEDDING_MODEL = "text-embedding-embeddinggemma-300m"

question = input("Domanda: ").strip()
if not question:
    sys.exit(1)

# Genera embedding
payload = json.dumps({"model": EMBEDDING_MODEL, "input": question}).encode()
req = urllib.request.Request(
    f"{LLM_ENDPOINT}/v1/embeddings",
    data=payload,
    headers={"Content-Type": "application/json"},
)

with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read())
    embedding = data["data"][0]["embedding"]

print(f"\nEmbedding: {len(embedding)} dimensioni")
print(f"Incolla questa query SQL in Supabase:\n")

# Genera la query SQL
embedding_str = str(embedding)
sql = f"""SELECT
  chunk_id,
  section,
  chapter,
  1 - (embedding <=> '{embedding_str}'::vector) AS similarity
FROM manual_chunks
WHERE language = 'it'
  AND embedding IS NOT NULL
ORDER BY embedding <=> '{embedding_str}'::vector
LIMIT 5;"""

print(sql)
