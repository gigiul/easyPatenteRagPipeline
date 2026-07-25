#!/usr/bin/env python3
"""
Aggiunge i segnali mancanti a sign_to_chunk.
"""
import json
import os
import urllib.request

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://mvkxafzywzuohnbqjqmo.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# Segnali da aggiungere/aggiornare
MISSING_SIGNS = [
    # Segnali combinati direzione (quelli che mancavano)
    {"sign_name": "Direzione obbligatoria diritto e destra", "sign_category": "OBBLIGO", "chunk_id": "v1/cap-05/sez-09/001", "keywords": ["diritto", "destra", "frecce", "doppia freccia"]},
    {"sign_name": "Direzione obbligatoria diritto e sinistra", "sign_category": "OBBLIGO", "chunk_id": "v1/cap-05/sez-10/001", "keywords": ["diritto", "sinistra", "frecce", "doppia freccia"]},
    {"sign_name": "Direzione obbligatoria destra e sinistra", "sign_category": "OBBLIGO", "chunk_id": "v1/cap-05/sez-08/001", "keywords": ["destra", "sinistra", "frecce", "doppia freccia"]},

    # Altri segnali obbligo mancanti
    {"sign_name": "Alt - Stazione", "sign_category": "OBBLIGO", "chunk_id": "v1/cap-05/sez-32/001", "keywords": ["stazione", "alt", "obbligo"]},
    {"sign_name": "Alt - Dogana", "sign_category": "OBBLIGO", "chunk_id": "v1/cap-05/sez-28/001", "keywords": ["dogana", "alt", "obbligo"]},
    {"sign_name": "Catene da neve obbligatorie", "sign_category": "OBBLIGO", "chunk_id": "v1/cap-05/sez-17/001", "keywords": ["catene", "neve", "obbligo"]},
    {"sign_name": "Passaggi consentiti", "sign_category": "OBBLIGO", "chunk_id": "v1/cap-05/sez-13/001", "keywords": ["passaggi", "consentiti", "obbligo"]},
    {"sign_name": "Confine di stato", "sign_category": "OBBLIGO", "chunk_id": "v1/cap-05/sez-29/001", "keywords": ["confine", "stato", "europa"]},

    # Correzione: Direzione obbligatoria a diritto punta al chunk sbagliato
    {"sign_name": "Direzione obbligatoria a diritto", "sign_category": "OBBLIGO", "chunk_id": "v1/cap-05/sez-02/001", "keywords": ["diritto", "obbligo", "frecce"]},
]


def supabase_upsert(table, data):
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


def main():
    if not SUPABASE_KEY:
        print("ERROR: Set SUPABASE_KEY")
        return

    print(f"Adding {len(MISSING_SIGNS)} signs...\n")

    for sign in MISSING_SIGNS:
        try:
            status = supabase_upsert("sign_to_chunk", sign)
            print(f"  OK: {sign['sign_name']} -> {sign['chunk_id']}")
        except Exception as e:
            print(f"  ERROR: {sign['sign_name']}: {e}")

    print("\nDone!")


if __name__ == "__main__":
    main()
