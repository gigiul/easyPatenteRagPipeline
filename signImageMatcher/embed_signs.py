#!/usr/bin/env python3
"""
Calcola gli embeddings per le immagini dei segnali in sign_reference_images.
"""
import json, os, sys, base64, urllib.request, time
from pathlib import Path

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://mvkxafzywzuohnbqjqmo.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
LLM_ENDPOINT = os.environ.get("LLM_ENDPOINT", "http://localhost:8000")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "qwen-embedding-3-0.6B")
VL_MODEL = os.environ.get("VL_MODEL", "lm-studio")
PAGES_DIR = Path(__file__).parent.parent / "manualePatente"

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

def generate_text_embedding(text):
    payload = json.dumps({"model": EMBEDDING_MODEL, "input": text}).encode()
    req = urllib.request.Request(f"{LLM_ENDPOINT}/v1/embeddings", data=payload,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
        return data["data"][0]["embedding"]

def generate_image_embedding(image_base64):
    payload = json.dumps({"model": VL_MODEL, "messages": [
        {"role": "user", "content": [
            {"type": "text", "text": "Descrivi questo segnale stradale in una frase."},
            {"type": "image_url", "image_url": {"url": image_base64}},
        ]}], "max_tokens": 100}).encode()
    req = urllib.request.Request(f"{LLM_ENDPOINT}/v1/chat/completions", data=payload,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
        description = data["choices"][0]["message"]["content"].strip()
        return generate_text_embedding(description)

def main():
    if not SUPABASE_KEY:
        print("ERROR: Set SUPABASE_KEY"); sys.exit(1)

    signs = supabase_get("sign_reference_images", "id,sign_name,image_filename", "embedding.is.null")
    print(f"Found {len(signs)} signs without embeddings\n")

    for i, sign in enumerate(signs):
        print(f"[{i+1}/{len(signs)}] {sign['sign_name']}")

        img_path = PAGES_DIR / sign["image_filename"]
        if not img_path.exists():
            print(f"  Image not found"); continue

        with open(img_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        ext = img_path.suffix.lower().lstrip(".")
        mime = "jpeg" if ext == "jpg" else ext
        img_data_url = f"data:image/{mime};base64,{b64}"

        try:
            embedding = generate_image_embedding(img_data_url)
            supabase_patch("sign_reference_images", {"embedding": str(embedding)}, f"id=eq.{sign['id']}")
            print(f"  OK")
        except Exception as e:
            print(f"  Error: {e}")

        time.sleep(0.5)

    print("\nDone!")

if __name__ == "__main__":
    main()