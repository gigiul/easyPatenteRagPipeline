#!/usr/bin/env python3
"""
Trascrive immagini in testo plain/markdown usando un modello VLM servito
localmente da LM Studio (endpoint OpenAI-compatible /v1/chat/completions).

Uso:
    python transcribe_images.py /percorso/cartella/immagini

Per ogni immagine (es. page-1.png) crea un file con lo stesso nome
e estensione .md (es. page-1.md) nella stessa cartella (o in --output-dir
se specificato).

Le immagini vengono processate UNA ALLA VOLTA (una singola immagine per
richiesta) per evitare il comportamento di loop osservato con batch
di immagini multiple in un solo prompt.
"""

import argparse
import base64
import json
import mimetypes
import sys
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configurazione di default (modificabile via argomenti CLI)
# ---------------------------------------------------------------------------
DEFAULT_ENDPOINT = "http://localhost:1234/api/v1/chat"
DEFAULT_MODEL = "qwen/qwen3-vl-30b"
DEFAULT_PROMPT = "Transcribe image to plain text preserving structure and all information."
DEFAULT_SYSTEM_PROMPT = (
    "You are a precise OCR/transcription engine. Transcribe the text content "
    "of the image faithfully, preserving structure (paragraphs, lists, tables, "
    "headings) using plain text or simple Markdown. Do not add commentary, "
    "explanations, or repeat content. Output only the transcription."
)

SUPPORTED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


def natural_sort_key(path: Path):
    """Ordina 'page-2' prima di 'page-10' invece che alfabeticamente."""
    import re
    parts = re.split(r"(\d+)", path.stem)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def encode_image_to_data_uri(image_path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(str(image_path))
    if mime_type is None:
        mime_type = "image/png"
    data = image_path.read_bytes()
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


def transcribe_image(
    image_path: Path,
    endpoint: str,
    model: str,
    prompt: str,
    system_prompt: str,
    timeout: int,
    max_tokens: int,
    temperature: float,
    context_length,
    api_key,
    store: bool,
) -> str:
    data_uri = encode_image_to_data_uri(image_path)

    payload = {
        "model": model,
        "input": [
            {"type": "text", "content": prompt},
            {"type": "image", "data_url": data_uri},
        ],
        "system_prompt": system_prompt,
        "temperature": temperature,
        "max_output_tokens": max_tokens,
        "store": store,
    }
    if context_length is not None:
        payload["context_length"] = context_length

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    response = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    result = response.json()

    try:
        output_items = result["output"]
    except KeyError as exc:
        raise RuntimeError(f"Risposta inattesa dal server: {json.dumps(result)[:500]}") from exc

    # Concatena tutti gli item di tipo "message" (di solito ce n'è uno solo,
    # ma se il modello genera più messaggi/tool call li uniamo in ordine).
    messages = [item["content"] for item in output_items if item.get("type") == "message"]

    if not messages:
        raise RuntimeError(f"Nessun messaggio di tipo 'message' nella risposta: {json.dumps(result)[:500]}")

    return "\n".join(messages)


def main():
    parser = argparse.ArgumentParser(description="Trascrive immagini con un VLM locale (LM Studio).")
    parser.add_argument("input_dir", type=Path, help="Cartella contenente le immagini da trascrivere")
    parser.add_argument("--output-dir", type=Path, default=None,
                         help="Cartella di destinazione per i file .md (default: stessa cartella input)")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="URL endpoint chat completions")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Nome del modello caricato in LM Studio")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Prompt utente inviato con ogni immagine")
    parser.add_argument("--system-prompt", default=DEFAULT_SYSTEM_PROMPT, help="System prompt")
    parser.add_argument("--max-tokens", type=int, default=4096, help="Max token generati per immagine")
    parser.add_argument("--temperature", type=float, default=0.0, help="Temperature (0 = deterministico)")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout richiesta in secondi")
    parser.add_argument("--delay", type=float, default=1.0,
                         help="Pausa in secondi tra una richiesta e l'altra (per non stressare il modello)")
    parser.add_argument("--overwrite", action="store_true",
                         help="Sovrascrive i file .md già esistenti (default: li salta)")
    parser.add_argument("--retries", type=int, default=2, help="Numero di retry in caso di errore per immagine")
    parser.add_argument("--api-key", default=None, help="Token Authorization: Bearer (solo se richiesto)")
    parser.add_argument("--context-length", type=int, default=None, help="Numero di token di contesto (opzionale)")
    parser.add_argument("--store", action="store_true", help="Fa salvare la chat a LM Studio (default: no)")

    args = parser.parse_args()

    input_dir: Path = args.input_dir
    output_dir: Path = args.output_dir or input_dir

    if not input_dir.is_dir():
        print(f"Errore: '{input_dir}' non è una cartella valida.", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    images = sorted(
        (p for p in input_dir.iterdir() if p.suffix.lower() in SUPPORTED_EXT),
        key=natural_sort_key,
    )

    if not images:
        print(f"Nessuna immagine trovata in '{input_dir}' (estensioni supportate: {sorted(SUPPORTED_EXT)}).")
        sys.exit(0)

    print(f"Trovate {len(images)} immagini. Endpoint: {args.endpoint} | Modello: {args.model}\n")

    ok_count = 0
    fail_count = 0

    for idx, image_path in enumerate(images, start=1):
        out_path = output_dir / f"{image_path.stem}.md"

        if out_path.exists() and not args.overwrite:
            print(f"[{idx}/{len(images)}] {image_path.name} -> SKIP (esiste già {out_path.name})")
            continue

        print(f"[{idx}/{len(images)}] {image_path.name} -> in corso...", end=" ", flush=True)

        last_error = None
        for attempt in range(1, args.retries + 2):  # tentativo iniziale + retry
            try:
                text = transcribe_image(
                    image_path=image_path,
                    endpoint=args.endpoint,
                    model=args.model,
                    prompt=args.prompt,
                    system_prompt=args.system_prompt,
                    timeout=args.timeout,
                    max_tokens=args.max_tokens,
                    temperature=args.temperature,
                    context_length=args.context_length,
                    api_key=args.api_key,
                    store=args.store,
                )
                out_path.write_text(text.strip() + "\n", encoding="utf-8")
                print(f"OK ({len(text)} caratteri) -> {out_path.name}")
                ok_count += 1
                last_error = None
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt <= args.retries:
                    print(f"\n  tentativo {attempt} fallito ({exc}), riprovo...", end=" ", flush=True)
                    time.sleep(2)

        if last_error is not None:
            print(f"FALLITO dopo {args.retries + 1} tentativi: {last_error}")
            fail_count += 1

        # Pausa tra un'immagine e l'altra: aiuta a evitare che il modello
        # "trascini" contesto/stato tra richieste successive, oltre a dare
        # respiro alla GPU/CPU locale.
        if idx < len(images):
            time.sleep(args.delay)

    print(f"\nCompletato: {ok_count} trascritte, {fail_count} fallite, "
          f"{len(images) - ok_count - fail_count} saltate.")


if __name__ == "__main__":
    main()
