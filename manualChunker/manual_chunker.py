"""
manual_chunker.py — Pipeline di chunking gerarchico per il manuale patente
============================================================================
Converte i 128 file .md (uno per pagina, OCR via GLM) in chunk strutturati
per RAG (Supabase pgvector), rispettando la struttura logica capitolo/sezione
del manuale invece di tagli a dimensione fissa.

STRATEGIA (validata sui file campione forniti):
  1. Il capitolo (chapter = "Lezione N") viene rilevato in modo AL 100%
     DETERMINISTICO leggendo l'Indice (ultima pagina del manuale), che
     riporta i numeri di pagina STAMPATI di inizio di ogni Lezione.
  2. Viene rilevato un offset costante tra il numero del file
     (manual-page-004.md) e il numero stampato nel testo (pagina "1"):
     nei campioni offset = +3 su tutte le pagine testate.
     Questo converte "Lezione N inizia a pag. stampata X" direttamente
     nel file corretto, SENZA bisogno di euristiche o LLM per capire
     dove inizia/finisce ogni capitolo.
  3. All'interno di un capitolo, la sezione viene rilevata via euristica:
     ogni riga interamente MAIUSCOLA (es. "STRADA", "DIREZIONE OBBLIGATORIA
     DIRITTO") apre una nuova sezione; il testo seguente (fino alla
     prossima riga maiuscola) è il corpo di quella sezione.
  4. Gestione esplicita di due artefatti OCR osservati a cavallo di pagina:
       - sillabazione: riga finisce con "-" e la pagina successiva
         inizia con lettera minuscola → si ricompone la parola spezzata.
       - overlap duplicato: la pagina successiva ripete la coda della
         frase precedente prima di continuare con contenuto nuovo →
         si rileva la sovrapposizione e si scarta il duplicato.
  5. subsection è sempre None in questa versione: nei campioni osservati
     non emerge un terzo livello esplicito nel testo. Il campo resta nello
     schema per un affinamento futuro (es. liste numerate molto lunghe
     dentro una sezione).

Uso:
    python manual_chunker.py --pages-dir manual_pages/ --manual-version 2024-ed3
    python manual_chunker.py --pages-dir manual_pages/ --manual-version 2024-ed3 --output chunks.json

Dipendenze:
    pip install tiktoken
"""

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
    def count_tokens(text: str) -> int:
        return len(_ENC.encode(text))
except Exception as e:
    print(f"⚠️  tiktoken non disponibile ({type(e).__name__}) — uso stima approssimata "
          f"(~1.3 token/parola). Per conteggi esatti: pip install tiktoken e verifica la connessione.")
    def count_tokens(text: str) -> int:
        return int(len(text.split()) * 1.3)

# ── Costanti di rumore (intestazioni/piè di pagina da rimuovere) ────────────
# NOTA: osservati due formati alternati (pagine dispari/pari del libro):
#   dispari: "Manuale di teoria per le patenti A1 A e B" + numero
#   pari:    numero + "Valerio Platia e Roberto Mastri"
TITLE_NOISE  = "manuale di teoria per le patenti a1 a e b"
AUTHOR_NOISE = "valerio platia e roberto mastri"

LEZIONE_RE = re.compile(r'^Lezione\s+(\d+)\.?\s*(.+)$')
TOC_ENTRY_RE = re.compile(r'^Lezione\s+(\d+)\s+(.+?)\s*[.…]{2,}\s*(\d+)\s*$', re.MULTILINE)
ARTICLE_REF_RE = re.compile(r'\bArt(?:icolo)?\.?\s*\d+[\w\-/]*\s*(?:del\s+)?(?:C\.?d\.?S\.?|Codice della Strada)', re.IGNORECASE)

# ── Mapping capitolo (numero Lezione) → chunk_type di default ──────────────
# Basato sui titoli reali dell'Indice. Sovrascritto da regole più specifiche
# (es. tabelle di sanzioni) quando rilevate nel testo.
CHAPTER_CHUNK_TYPE_DEFAULT = {
    1: "definition",
    2: "sign_description", 3: "sign_description", 4: "sign_description",
    5: "sign_description", 6: "sign_description", 7: "sign_description",
    8: "sign_description", 9: "sign_description", 10: "sign_description",
    11: "sign_description",
    12: "rule", 13: "rule", 14: "rule", 15: "rule", 16: "rule",
    17: "rule", 18: "rule",
    19: "device_description", 20: "device_description",
    21: "safety_rule", 22: "rule",
    23: "license_rule", 24: "license_rule",
    25: "safety_rule", 26: "procedure", 27: "health_rule",
    28: "environment_rule", 29: "vehicle_component", 30: "vehicle_component",
}

# ── Mapping capitolo → category_id ───────────────
# Mappa tutte le 30 Lezioni alle 24 categorie Supabase.
CHAPTER_CATEGORY_ID = {
    1:  "41d2be33-3ca3-41f5-809f-ce2329ae9628",  # Veicoli e Strade
    2:  "1c72e436-7a7f-4547-8f0e-b40f6fea7294",  # Segnali di Pericolo
    3:  "1a693ebd-3e77-49da-a5cb-aefd34af0d8e",  # Segnali di Precedenza
    4:  "1055628b-9e4a-4544-92fd-60167704c315",  # Segnali di Divieto
    5:  "cfecfe52-5925-443e-a798-5adff605c489",  # Segnali di Obbligo
    6:  "fd787783-6b5b-4e0a-a0b4-2173aad17c37",  # Segnali di Indicazione
    7:  "4caf0f96-d5a9-49e7-b345-bae6277295b7",  # Segnali temporanei/cantiere/complementari
    8:  "4caf0f96-d5a9-49e7-b345-bae6277295b7",  # Segnali complementari
    9:  "cf7cd590-6fdc-4c7c-8b64-6dbade75c49d",  # Pannelli Integrativi
    10: "9ae4ea7e-03e8-4f62-963a-ebea4fbb42e8",  # Segnaletica luminosa e manuale
    11: "add74848-59a1-4150-ba8b-1a01678ee745",  # Segnaletica orizzontale
    12: "a2b3c4d5-8e7f-4b6c-9d1e-2f3a4b5c6002",  # Regolazione velocità, distanza sicurezza
    13: "b3c4d5e6-7f8a-4c5d-9e1f-3a4b5c6d7003",  # Posizione veicoli, svolte, manovre
    14: "2ee255f6-5157-4af3-a6e1-2baa80df62dd",  # Precedenze
    15: "a1111111-1111-4a1a-8a1a-111111111115",  # Sorpasso
    16: "a2222222-2222-4b2b-8b2b-222222222216",  # Fermata e sosta
    17: "a3333333-3333-4c3c-8c3c-333333333317",  # Ingombro carreggiata
    18: "a3333333-3333-4c3c-8c3c-333333333317",  # Circolazione autostrade
    19: "f1a2b3c4-9d8e-4a7b-8c1d-1e2f3a4b5001",  # Luci, specchi, dispositivi
    20: "f1a2b3c4-9d8e-4a7b-8c1d-1e2f3a4b5001",  # Spie e simboli
    21: "a4444444-4444-4d4d-8d4d-444444444418",  # Comportamento conducente
    22: "a3333333-3333-4c3c-8c3c-333333333317",  # Trasporto persone/carico
    23: "c1111111-1111-4a1a-8a1a-111111111120",  # Patente e documenti
    24: "c1111111-1111-4a1a-8a1a-111111111120",  # Obbligo funzionari, documenti
    25: "a5555555-5555-4e5e-8e5e-555555555519",  # Cause incidenti
    26: "a5555555-5555-4e5e-8e5e-555555555519",  # Comportamento in caso di incidente, RCA
    27: "a5555555-5555-4e5e-8e5e-555555555519",  # Alcol, stupefacenti, primo soccorso
    28: "c3333333-3333-4c3c-8c3c-333333333122",  # Inquinamento
    29: "c2222222-2222-4b2b-8b2b-222222222121",  # Elementi costitutivi veicolo
    30: "c2222222-2222-4b2b-8b2b-222222222121",  # Stabilità e tenuta di strada
}

MIN_OVERLAP_CHARS = 15   # soglia minima per considerare un overlap "reale" tra pagine
MAX_OVERLAP_CHECK  = 80  # quanti caratteri controllare per l'overlap


# ── Utilità testo ────────────────────────────────────────────────────────────
def normalize(s: str) -> str:
    """Rimuove accenti e normalizza spazi/case per confronti robusti."""
    n = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', n).strip().lower()


def slugify(s: str) -> str:
    """Converte una stringa in slug URL-safe (accenti rimossi, minuscolo, trattini)."""
    n = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    n = re.sub(r"[^\w\s-]", "", n).strip().lower()
    return re.sub(r"[\s_]+", "-", n)


def is_noise_line(line: str) -> bool:
    """Riconosce le righe di intestazione/piè di pagina da rimuovere:
    titolo del libro, nome autori, numero di pagina isolato."""
    stripped = line.strip()
    if re.fullmatch(r'\d{1,4}', stripped):
        return True
    n = normalize(stripped)
    return n == TITLE_NOISE or n == AUTHOR_NOISE


def is_heading_line(line: str) -> bool:
    """Una riga è un'intestazione di sezione se è (quasi) interamente
    maiuscola, contiene almeno una lettera ed è ragionevolmente corta.
    Punteggiatura interna (virgole, punti, parentesi) è ammessa;
    l'euristica confronta solo il case, non la punteggiatura."""
    stripped = line.strip()
    if not stripped or len(stripped) > 100:
        return False
    if not any(c.isalpha() for c in stripped):
        return False
    core = stripped.rstrip(':').strip()
    return core == core.upper()


def join_continuation(prev_last_line: str, next_first_line: str) -> str:
    """Unisce l'ultima riga accumulata di una pagina con la prima riga
    di continuazione della pagina successiva, gestendo:
      - sillabazione (trattino di fine riga + minuscola dopo)
      - overlap duplicato (l'OCR ripete la coda della frase precedente)
    """
    prev = prev_last_line.rstrip()
    nxt = next_first_line.lstrip()

    if prev.endswith('-') and nxt and nxt[0].islower():
        return prev[:-1] + nxt

    max_check = min(len(prev), len(nxt), MAX_OVERLAP_CHECK)
    for size in range(max_check, MIN_OVERLAP_CHARS, -1):
        if prev[-size:].lower() == nxt[:size].lower():
            return prev + " " + nxt[size:].lstrip()

    return prev + " " + nxt


# ── Step 1: Parsing dell'Indice (TOC) ───────────────────────────────────────
@dataclass
class TocEntry:
    lezione_num: int
    title: str
    printed_start_page: int


def parse_toc(toc_text: str) -> list:
    entries = []
    for num, title, page in TOC_ENTRY_RE.findall(toc_text):
        entries.append(TocEntry(int(num), title.strip(), int(page)))
    entries.sort(key=lambda e: e.lezione_num)
    return entries


def find_toc_file(pages_dir: Path) -> Optional[Path]:
    """Trova il file che contiene l'Indice cercando la parola chiave 'Indice'
    come riga isolata, controllando i file dall'ultimo al primo (l'indice
    è tipicamente in fondo al manuale)."""
    files = sorted(pages_dir.glob('manual-page-*.md'),
                    key=lambda p: int(re.search(r'(\d+)', p.stem).group(1)),
                    reverse=True)
    for f in files:
        text = f.read_text(encoding='utf-8')
        if re.search(r'^\s*Indice\s*$', text, re.MULTILINE):
            return f
    return None


# ── Step 2: Rilevamento offset file↔pagina stampata ─────────────────────────
def extract_printed_page_num(text: str) -> Optional[int]:
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for line in lines[:3]:
        if re.fullmatch(r'\d{1,4}', line):
            return int(line)
    return None


def compute_offset(pages_dir: Path) -> int:
    offsets = []
    for f in pages_dir.glob('manual-page-*.md'):
        file_num = int(re.search(r'(\d+)', f.stem).group(1))
        printed = extract_printed_page_num(f.read_text(encoding='utf-8'))
        if printed is not None:
            offsets.append(file_num - printed)
    if not offsets:
        raise ValueError("Impossibile determinare l'offset pagina file↔stampata.")
    mode_offset = Counter(offsets).most_common(1)[0][0]
    consistency = offsets.count(mode_offset) / len(offsets)
    if consistency < 0.9:
        print(f"⚠️  Offset non uniforme su tutte le pagine (coerenza {consistency:.0%}). "
              f"Uso il valore più comune: {mode_offset}. Verifica manualmente eventuali outlier.")
    return mode_offset


# ── Step 3: Costruzione range di pagine per capitolo ────────────────────────
@dataclass
class ChapterRange:
    lezione_num: int
    title: str
    chapter_id: str
    file_start: int
    file_end: int


def build_chapter_ranges(toc_entries: list, offset: int, all_file_nums: list) -> list:
    ranges = []
    max_file_num = max(all_file_nums)
    for i, entry in enumerate(toc_entries):
        file_start = entry.printed_start_page + offset
        if i + 1 < len(toc_entries):
            file_end = toc_entries[i + 1].printed_start_page + offset - 1
        else:
            # Ultimo capitolo: termina dove inizia l'indice (ultima pagina nota) - 1
            file_end = max_file_num - 1
        ranges.append(ChapterRange(
            lezione_num=entry.lezione_num,
            title=entry.title,
            chapter_id=f"cap-{entry.lezione_num:02d}",
            file_start=file_start,
            file_end=file_end,
        ))
    return ranges


# ── Step 4: Estrazione sezioni da una pagina ────────────────────────────────
def strip_noise_and_get_lines(text: str):
    """Rimuove fino a 2 righe di rumore in testa e rileva 'Lezione N. Titolo'
    se presente come primo contenuto reale. Ritorna (lezione_match_o_None,
    lista_righe_di_contenuto)."""
    lines = text.split('\n')
    non_empty_idx = [i for i, l in enumerate(lines) if l.strip()]

    idx_pointer = 0
    stripped_count = 0
    while idx_pointer < len(non_empty_idx) and stripped_count < 2:
        if is_noise_line(lines[non_empty_idx[idx_pointer]]):
            stripped_count += 1
            idx_pointer += 1
        else:
            break

    lezione_match = None
    if idx_pointer < len(non_empty_idx):
        first_idx = non_empty_idx[idx_pointer]
        m = LEZIONE_RE.match(lines[first_idx].strip())
        if m:
            lezione_match = (int(m.group(1)), m.group(2).strip())
            idx_pointer += 1

    content_lines = [lines[i].strip() for i in non_empty_idx[idx_pointer:]]
    return lezione_match, content_lines


@dataclass
class Section:
    heading: str            # es. "STRADA", o "Introduzione" per il testo prima della 1a intestazione
    section_index: int      # posizione all'interno del capitolo (1-based)
    lines: list = field(default_factory=list)   # righe di testo accumulate
    page_start: int = None  # pagina STAMPATA di inizio
    page_end: int = None    # pagina STAMPATA di fine


def parse_chapter_sections(chapter: ChapterRange, pages_dir: Path, offset: int, qa_notes: list) -> list:
    """Itera le pagine-file del range del capitolo, costruendo le sezioni
    con merge cross-pagina (sillabazione/overlap) dove necessario."""
    sections = []
    current_section = None
    section_counter = 0

    for file_num in range(chapter.file_start, chapter.file_end + 1):
        page_path = pages_dir / f"manual-page-{file_num:03d}.md"
        if not page_path.exists():
            qa_notes.append(f"[cap-{chapter.lezione_num:02d}] pagina file {file_num} mancante, saltata")
            continue

        printed_page = file_num - offset
        text = page_path.read_text(encoding='utf-8')
        lezione_match, content_lines = strip_noise_and_get_lines(text)

        if not content_lines:
            continue

        line_ptr = 0
        # Se la pagina non inizia con un'intestazione, il primo blocco è
        # continuazione dell'ultima sezione aperta (o "Introduzione" se è
        # la prima pagina del capitolo e non c'è ancora nessuna sezione).
        if not is_heading_line(content_lines[0]):
            if current_section is None:
                section_counter += 1
                current_section = Section(heading="Introduzione", section_index=section_counter,
                                            page_start=printed_page)
                sections.append(current_section)
            else:
                # Merge con l'ultima riga della sezione precedente (sillabazione/overlap)
                if current_section.lines:
                    merged = join_continuation(current_section.lines[-1], content_lines[0])
                    current_section.lines[-1] = merged
                else:
                    current_section.lines.append(content_lines[0])
                line_ptr = 1
            current_section.page_end = printed_page

        # Processa il resto della pagina: ogni riga heading apre nuova sezione
        while line_ptr < len(content_lines):
            line = content_lines[line_ptr]
            if is_heading_line(line):
                section_counter += 1
                current_section = Section(heading=line, section_index=section_counter,
                                            page_start=printed_page, page_end=printed_page)
                sections.append(current_section)
            else:
                if current_section is None:
                    # Difensivo: non dovrebbe accadere dato il branch sopra
                    section_counter += 1
                    current_section = Section(heading="Introduzione", section_index=section_counter,
                                                page_start=printed_page, page_end=printed_page)
                    sections.append(current_section)
                current_section.lines.append(line)
                current_section.page_end = printed_page
            line_ptr += 1

    if not sections:
        qa_notes.append(f"[cap-{chapter.lezione_num:02d}] '{chapter.title}': NESSUNA sezione rilevata — verificare manualmente")

    return sections


# ── Step 5: Classificazione chunk_type ──────────────────────────────────────
SANCTION_HINTS = re.compile(r'(?:€|euro|sanzione|punt[oi]\s+(?:sulla\s+)?patente|sospension[ei]\s+della\s+patente)', re.IGNORECASE)


def classify_chunk_type(lezione_num: int, text: str) -> str:
    if SANCTION_HINTS.search(text):
        return "sanction_table"
    return CHAPTER_CHUNK_TYPE_DEFAULT.get(lezione_num, "rule")


# ── Step 6: Estrazione riferimenti normativi e keyword ──────────────────────
def extract_article_refs(text: str) -> list:
    return sorted(set(m.strip() for m in ARTICLE_REF_RE.findall(text)))


# Stopword italiane minime per l'estrazione keyword (euristica leggera, non NLP)
IT_STOPWORDS = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "di", "a", "da", "in",
    "con", "su", "per", "tra", "fra", "e", "o", "che", "non", "si", "è", "sono",
    "questo", "questa", "questi", "queste", "come", "quando", "dove", "anche",
    "più", "meno", "molto", "poco", "essere", "avere", "al", "del", "della",
    "dei", "delle", "nel", "nella", "sul", "sulla", "ad", "ed", "se", "cui",
}


def extract_keywords(heading: str, text: str, max_keywords: int = 8) -> list:
    keywords = []
    heading_kw = heading.lower().strip()
    if heading_kw and heading_kw != "introduzione":
        keywords.append(heading_kw)

    # Sequenze capitalizzate nel testo originale (candidati nome proprio/termine tecnico)
    candidates = re.findall(r'\b[A-Z][a-zà-ù]+(?:\s+[A-Z][a-zà-ù]+){0,2}\b', text)
    for c in candidates:
        c_norm = c.lower().strip()
        words = c_norm.split()
        if all(w in IT_STOPWORDS for w in words):
            continue
        if c_norm not in keywords:
            keywords.append(c_norm)
        if len(keywords) >= max_keywords:
            break

    return keywords[:max_keywords]


# ── Step 7: Suddivisione sezioni troppo lunghe ──────────────────────────────
SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-ZÀ-Ù])')


def split_long_text(text: str, max_tokens: int) -> list:
    """Divide un testo troppo lungo su confini di frase, senza overlap fisso
    forzato (l'overlap si applica solo se una singola frase supera già il limite,
    caso raro per definizioni/regole di questo manuale)."""
    if count_tokens(text) <= max_tokens:
        return [text]

    sentences = SENTENCE_SPLIT_RE.split(text)
    chunks, current = [], []
    current_tokens = 0

    for sent in sentences:
        sent_tokens = count_tokens(sent)
        if current and current_tokens + sent_tokens > max_tokens:
            chunks.append(" ".join(current))
            current, current_tokens = [], 0
        current.append(sent)
        current_tokens += sent_tokens

    if current:
        chunks.append(" ".join(current))
    return chunks if chunks else [text]


# ── Step 8: Assemblaggio chunk finali ───────────────────────────────────────
def assemble_chunks(chapter_ranges: list, pages_dir: Path, offset: int,
                     manual_version: str, max_tokens: int, qa_notes: list) -> list:
    all_chunks = []

    for chapter in chapter_ranges:
        chapter_slug = slugify(chapter.title)
        sections = parse_chapter_sections(chapter, pages_dir, offset, qa_notes)
        category_id = CHAPTER_CATEGORY_ID.get(chapter.lezione_num)

        for section in sections:
            full_text = "\n".join(section.lines).strip()
            if not full_text:
                continue

            section_slug = slugify(section.heading)
            section_id = f"{chapter.chapter_id}-sez-{section.section_index:02d}"
            chunk_type = classify_chunk_type(chapter.lezione_num, full_text)
            pieces = split_long_text(full_text, max_tokens)
            
            # Determina file sorgenti coinvolti usando offset
            source_files = [
                f"manual-page-{(p + offset):03d}.md"
                for p in range(section.page_start, section.page_end + 1)
            ]

            for piece_idx, piece_text in enumerate(pieces, start=1):
                chunk_id = f"v1/{chapter.chapter_id}/sez-{section.section_index:02d}/{piece_idx:03d}"
                embedding_text = f"{chapter.title} — {section.heading}\n\n{piece_text}"
                
                llm_context = (
                    f"# Lezione {chapter.lezione_num} — {chapter.title}\n"
                    f"## {section.heading}\n\n"
                    f"{piece_text}\n\n"
                    f"[Pagine: {section.page_start}-{section.page_end} | Manuale v{manual_version}]"
                )

                all_chunks.append({
                    "chunk_id": chunk_id,
                    "manual_version": manual_version,
                    "language": "it",
                    "chapter": chapter.title,
                    "chapter_id": chapter.chapter_id,
                    "section": section.heading,
                    "section_id": section_id,
                    "subsection": None,
                    "chunk_type": chunk_type,
                    "category_id": category_id,
                    "page_start": section.page_start,
                    "page_end": section.page_end,
                    "chunk_index": piece_idx,
                    "prev_chunk_id": None,   # collegato in un secondo passaggio globale
                    "next_chunk_id": None,
                    "text": piece_text,
                    "embedding_text": embedding_text,
                    "llm_context": llm_context,
                    "token_count": count_tokens(piece_text),
                    "char_count": len(piece_text),
                    "source_file": source_files,
                    "article_ref": extract_article_refs(piece_text),
                    "keywords": extract_keywords(section.heading, piece_text),
                })

    # Collegamento prev/next in ordine di lettura globale (già garantito
    # dall'ordine di iterazione capitolo→sezione→pezzo)
    for i, chunk in enumerate(all_chunks):
        chunk["prev_chunk_id"] = all_chunks[i - 1]["chunk_id"] if i > 0 else None
        chunk["next_chunk_id"] = all_chunks[i + 1]["chunk_id"] if i < len(all_chunks) - 1 else None

    return all_chunks


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Chunking gerarchico del manuale patente per RAG")
    parser.add_argument("--pages-dir", required=True, help="Cartella con i file manual-page-NNN.md")
    parser.add_argument("--manual-version", required=True, help='es. "2024-ed3"')
    parser.add_argument("--output", default="manual_chunks.json", help="File JSON di output")
    parser.add_argument("--max-tokens", type=int, default=400, help="Token massimi per chunk (default 400)")
    args = parser.parse_args()

    pages_dir = Path(args.pages_dir)
    if not pages_dir.exists():
        print(f"❌ Cartella non trovata: {pages_dir}")
        sys.exit(1)

    all_files = sorted(pages_dir.glob('manual-page-*.md'))
    if not all_files:
        print(f"❌ Nessun file manual-page-*.md trovato in {pages_dir}")
        sys.exit(1)
    all_file_nums = [int(re.search(r'(\d+)', f.stem).group(1)) for f in all_files]

    print(f"{'═'*60}\n  Manual Chunker — {len(all_files)} pagine trovate\n{'═'*60}")

    # 1. Trova e parsa l'Indice
    toc_file = find_toc_file(pages_dir)
    if not toc_file:
        print("❌ Nessuna pagina con 'Indice' trovata. Impossibile determinare i capitoli.")
        sys.exit(1)
    print(f"  Indice trovato in: {toc_file.name}")
    toc_entries = parse_toc(toc_file.read_text(encoding='utf-8'))
    print(f"  Voci Lezione estratte dall'indice: {len(toc_entries)}")

    # 2. Calcola offset file↔pagina stampata
    offset = compute_offset(pages_dir)
    print(f"  Offset pagina file↔stampata: {offset:+d}")

    # 3. Costruisci i range di pagine per capitolo
    chapter_ranges = build_chapter_ranges(toc_entries, offset, all_file_nums)
    print(f"\n  Range capitoli calcolati:")
    for c in chapter_ranges:
        n_pages_available = sum(1 for n in range(c.file_start, c.file_end + 1) if n in all_file_nums)
        n_pages_total = c.file_end - c.file_start + 1
        print(f"    cap-{c.lezione_num:02d}  file {c.file_start}-{c.file_end}  "
              f"({n_pages_available}/{n_pages_total} pagine disponibili)  {c.title}")

    # 4. Assembla i chunk
    qa_notes = []
    chunks = assemble_chunks(chapter_ranges, pages_dir, offset, args.manual_version, args.max_tokens, qa_notes)

    # 5. Scrivi output
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    print(f"\n{'─'*60}\n  RISULTATO\n{'─'*60}")
    print(f"  Chunk totali generati: {len(chunks)}")
    print(f"  Output: {args.output}")

    token_counts = [c["token_count"] for c in chunks]
    if token_counts:
        print(f"  Token per chunk — min: {min(token_counts)}  max: {max(token_counts)}  "
              f"media: {sum(token_counts)/len(token_counts):.0f}")

    with_category = sum(1 for c in chunks if c["category_id"])
    print(f"  Chunk con category_id assegnato: {with_category}/{len(chunks)}")

    if qa_notes:
        print(f"\n  ⚠️  NOTE QA ({len(qa_notes)}) — verificare manualmente:")
        for note in qa_notes:
            print(f"    - {note}")
    else:
        print(f"\n  ✅ Nessuna anomalia rilevata durante il parsing.")


if __name__ == "__main__":
    main()
