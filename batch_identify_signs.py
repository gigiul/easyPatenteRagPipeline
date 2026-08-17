#!/usr/bin/env python3
"""
Script batch per identificare i segnali stradali nelle immagini delle domande.
Popola il campo image_sign_type nella tabella questions.

Usage:
  python3 batch_identify_signs.py

Prerequisiti:
  - LM Studio in esecuzione su localhost:8000
  - signs.json nella directory corrente
  - Variabili d'ambiente o config con SUPABASE_URL e SUPABASE_KEY
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error

# ── Config ──
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://mvkxafzywzuohnbqjqmo.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")  # service role key
LLM_ENDPOINT = os.environ.get("LLM_ENDPOINT", "http://localhost:1234")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwythos-9b-claude-mythos-5-1m")
SIGN_LIST_PATH = os.path.join(os.path.dirname(__file__), "..", "signs.json")

# ── Load sign list ──
with open(SIGN_LIST_PATH) as f:
    signs_data = json.load(f)

sign_names = [s["name"] for s in signs_data["signs"]]
sign_list_text = "\n".join([f"- {name}" for name in sign_names])

# ── Helpers ──
def supabase_get(path, headers=None):
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        headers=headers or {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def supabase_patch(path, data, headers=None):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        data=body,
        method="PATCH",
        headers=headers or {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status


def fetch_image_base64(image_filename):
    storage_url = f"{SUPABASE_URL}/storage/v1/object/public/easypatente/{image_filename}"
    try:
        req = urllib.request.Request(storage_url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            img_bytes = resp.read()
            import base64
            ext = image_filename.rsplit(".", 1)[-1].lower()
            mime = "jpeg" if ext == "jpg" else ext
            b64 = base64.b64encode(img_bytes).decode()
            return f"data:image/{mime};base64,{b64}"
    except Exception as e:
        print(f"  Failed to fetch image {image_filename}: {e}")
        return None


def identify_sign(image_base64):
    prompt = f"""Analizza l'immagine di un segnale stradale italiano.
Scegli il segnale CORRETTO da questa lista:

{sign_list_text}

Regole:
- Rispondi SOLO con il nome esatto del segnale dalla lista
- Se non riesci a identificarlo, rispondi "NON_IDENTIFICATO"
- Non aggiungere spiegazioni

Segnale nell'immagine:"""

    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Sei un esperto di segnaletica stradale italiana. Rispondi SOLO con il nome del segnale."
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_base64}},
                ],
            },
        ],
        "max_tokens": 150,
        "temperature": 0,
    }).encode()

    req = urllib.request.Request(
        f"{LLM_ENDPOINT}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            content = data["choices"][0]["message"]["content"].strip()
            # Clean up: remove quotes, extra text
            content = content.strip('"').strip("'")
            # Take only first line
            content = content.split("\n")[0].strip()
            return content
    except Exception as e:
        print(f"  LLM error: {e}")
        return None


def main():
    if not SUPABASE_KEY:
        print("ERROR: Set SUPABASE_KEY environment variable (service role key)")
        sys.exit(1)

    # Get questions with image but no sign_type
    print("Fetching questions with images...")
    questions = supabase_get(
        "questions?select=id,code,image_filename,image_sign_type"
        "&image_filename=not.is.null"
        "&image_sign_type=is.null"
        "&order=code.asc"
    )

    print(f"Found {len(questions)} questions to process\n")

    if not questions:
        print("No questions to process. All done!")
        return

    identified = 0
    failed = 0

    for i, q in enumerate(questions):
        code = q["code"]
        filename = q["image_filename"]
        print(f"[{i+1}/{len(questions)}] {code} ({filename})")

        # Fetch image
        image_b64 = fetch_image_base64(filename)
        if not image_b64:
            failed += 1
            continue

        # Identify sign
        sign_name = identify_sign(image_b64)

        if sign_name and sign_name != "NON_IDENTIFICATO":
            print(f"  -> {sign_name}")
            try:
                supabase_patch(
                    f"questions?id=eq.{q['id']}",
                    {"image_sign_type": sign_name},
                )
                identified += 1
            except Exception as e:
                print(f"  DB error: {e}")
                failed += 1
        else:
            print(f"  -> NON_IDENTIFICATO")
            failed += 1

        # Rate limit: 1 request per second
        time.sleep(1)

    print(f"\n{'='*40}")
    print(f"Done: {identified} identified, {failed} failed")


if __name__ == "__main__":
    main()
