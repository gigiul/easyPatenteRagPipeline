-- Abilita pgvector
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.manual_chunks (
  id             uuid         NOT NULL DEFAULT gen_random_uuid(),
  chunk_id       text         NOT NULL,
  manual_version text         NOT NULL,
  language       text         NOT NULL DEFAULT 'it',

  -- Struttura gerarchica
  chapter        text,
  chapter_id     text,
  section        text,
  section_id     text,
  subsection     text,

  -- Classificazione
  chunk_type     text         NOT NULL DEFAULT 'rule',
  category_id    uuid,

  -- Posizione
  page_start     int4,
  page_end       int4,
  chunk_index    int4,
  prev_chunk_id  text,
  next_chunk_id  text,

  -- Contenuti
  text           text         NOT NULL,
  embedding_text text         NOT NULL,
  llm_context    text         NOT NULL,
  token_count    int4,
  char_count     int4,
  source_file    text[],

  -- Metadati
  article_ref    text[],
  keywords       text[],

  -- Embedding (Qwen3-0.6B = 1024 dims)
  embedding      vector(1024),

  -- Timestamps
  created_at     timestamptz  DEFAULT now(),
  updated_at     timestamptz  DEFAULT now(),

  CONSTRAINT manual_chunks_pkey PRIMARY KEY (id),
  CONSTRAINT manual_chunks_chunk_id_version_key UNIQUE (chunk_id, manual_version),
  CONSTRAINT manual_chunks_category_id_fkey FOREIGN KEY (category_id)
    REFERENCES public.categories(id) ON DELETE SET NULL
);

-- Indice per ricerca vettoriale (IVFFlat per dataset piccoli)
CREATE INDEX IF NOT EXISTS manual_chunks_embedding_idx
  ON public.manual_chunks
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 20);

-- Indici per query frequenti
CREATE INDEX IF NOT EXISTS manual_chunks_chapter_id_idx ON public.manual_chunks(chapter_id);
CREATE INDEX IF NOT EXISTS manual_chunks_category_id_idx ON public.manual_chunks(category_id);
CREATE INDEX IF NOT EXISTS manual_chunks_manual_version_idx ON public.manual_chunks(manual_version);
CREATE INDEX IF NOT EXISTS manual_chunks_language_idx ON public.manual_chunks(language);

-- RLS (Read-only per utenti autenticati)
ALTER TABLE public.manual_chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "manual_chunks_read_policy"
  ON public.manual_chunks FOR SELECT
  TO authenticated
  USING (true);

-- Funzione di ricerca semantica
CREATE OR REPLACE FUNCTION match_manual_chunks(
  query_embedding vector(1024),
  match_count int DEFAULT 5,
  filter_category_id uuid DEFAULT NULL,
  filter_language text DEFAULT 'it'
)
RETURNS TABLE (
  id uuid,
  chunk_id text,
  chapter text,
  section text,
  llm_context text,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    mc.id,
    mc.chunk_id,
    mc.chapter,
    mc.section,
    mc.llm_context,
    1 - (mc.embedding <=> query_embedding) AS similarity
  FROM public.manual_chunks mc
  WHERE mc.language = filter_language
    AND (filter_category_id IS NULL OR mc.category_id = filter_category_id)
    AND mc.embedding IS NOT NULL
  ORDER BY mc.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Tabella di collegamento chunk ↔ domande quiz
CREATE TABLE IF NOT EXISTS public.manual_chunk_questions (
  id              uuid      NOT NULL DEFAULT gen_random_uuid(),
  chunk_id        uuid      NOT NULL,
  question_id     uuid      NOT NULL,
  relevance_score float4,
  created_at      timestamptz DEFAULT now(),
  CONSTRAINT manual_chunk_questions_pkey PRIMARY KEY (id),
  CONSTRAINT manual_chunk_questions_chunk_fkey FOREIGN KEY (chunk_id)
    REFERENCES public.manual_chunks(id) ON DELETE CASCADE,
  CONSTRAINT manual_chunk_questions_question_fkey FOREIGN KEY (question_id)
    REFERENCES public.questions(id) ON DELETE CASCADE,
  CONSTRAINT manual_chunk_questions_unique UNIQUE (chunk_id, question_id)
);
