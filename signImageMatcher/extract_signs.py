#!/usr/bin/env python3
"""
Estrae i segnali stradali dalle pagine del manuale (001-060)
e li salva nella tabella sign_reference_images di Supabase.
"""
import json, os, sys, base64, urllib.request, time
from pathlib import Path

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://mvkxafzywzuohnbqjqmo.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
LLM_ENDPOINT = os.environ.get("LLM_ENDPOINT", "http://localhost:8000")
LLM_MODEL = os.environ.get("LLM_MODEL", "lm-studio")
PAGES_DIR = Path(__file__).parent.parent / "manualePatente"
SIGNS_JSON = Path(__file__).parent.parent.parent / "signs.json"

with open(SIGNS_JSON) as f:
    signs_data = json.load(f)
sign_names = [s["name"] for s in signs_data["signs"]]
sign_categories = {s["name"]: s["category"] for s in signs_data["signs"]}

def supabase_insert(table, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1/{table}", data=body, method="POST",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                 "Content-Type": "application/json", "Prefer": "return=minimal"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status

def image_to_base64(filepath):
    with open(filepath, "rb") as f:
        img_bytes = f.read()
    ext = filepath.suffix.lower().lstrip(".")
    mime = "jpeg" if ext == "jpg" else ext
    b64 = base64.b64encode(img_bytes).decode()
    return f"data:image/{mime};base64,{b64}"

def identify_signs_in_page(image_base64, page_num):
    prompt = f"""Analizza questa pagina del manuale della patente.
Identifica TUTTI i segnali stradali visibili.
Per ogni segnale, restituisci JSON: {{"name": "NOME", "category": "CATEGORIA"}}
Categorie: PERICOLO, DIVIETO, OBBLIGO, PRECEDENZA, INDICAZIONE
Lista segnali: {json.dumps(sign_names, ensure_ascii=False)}
Se non ci sono segnali, restituisci [].
Rispondi SOLO con il JSON."""

    payload = json.dumps({"model": LLM_MODEL, "messages": [
        {"role": "system", "content": "Esperto di segnaletica stradale italiana."},
        {"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_base64}},
        ]}],
        "max_tokens": 1024, "temperature": 0}).encode()

    req = urllib.request.Request(f"{LLM_ENDPOINT}/v1/chat/completions", data=payload,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            content = data["choices"][0]["message"]["content"].strip()
            content = content.strip("```json").strip("```").strip()
            return json.loads(content)
    except Exception as e:
        print(f"  LLM error: {e}")
        return []

def find_chunk_id(sign_name):
    try:
        chunks_path = Path(__file__).parent.parent / "manualChunker" / "output" / "manual_chunks.json"
        with open(chunks_path) as f:
            chunks = json.load(f)
        name_upper = sign_name.upper()
        for chunk in chunks:
            if chunk.get("section", "").upper() == name_upper:
                return chunk.get("chunk_id")
        for chunk in chunks:
            if name_upper in chunk.get("section", "").upper():
                return chunk.get("chunk_id")
        return None
    except Exception:
        return None

def main():
    if not SUPABASE_KEY:
        print("ERROR: Set SUPABASE_KEY"); sys.exit(1)

    pages = sorted(PAGES_DIR.glob("manual-page-*.png"))
    pages = [p for p in pages if int(p.stem.split("-")[-1]) <= 60]
    print(f"Found {len(pages)} pages to process (001-060)\n")

    total = 0
    for i, page_path in enumerate(pages):
        page_num = int(page_path.stem.split("-")[-1])
        print(f"[{i+1}/{len(pages)}] {page_path.name}")

        img_b64 = image_to_base64(page_path)
        signs = identify_signs_in_page(img_b64, page_num)

        if not signs:
            print(f"  No signs found"); continue

        for sign in signs:
            name = sign.get("name", "")
            category = sign.get("category", sign_categories.get(name, "SCONOSCIUTO"))
            if not name: continue

            chunk_id = find_chunk_id(name)
            try:
                supabase_insert("sign_reference_images", {
                    "sign_name": name, "sign_category": category,
                    "image_filename": page_path.name, "chunk_id": chunk_id,
                })
                print(f"  + {name} ({category}) -> {chunk_id or 'N/A'}")
                total += 1
            except Exception as e:
                print(f"  DB error: {e}")
        time.sleep(1)

    print(f"\nDone: {total} signs extracted")

if __name__ == "__main__":
    main()