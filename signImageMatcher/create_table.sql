CREATE TABLE IF NOT EXISTS sign_reference_images (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sign_name text NOT NULL,
  sign_category text NOT NULL,
  image_filename text NOT NULL,
  embedding vector(1024),
  chunk_id text,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sign_ref_embedding ON sign_reference_images
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 20);

CREATE INDEX IF NOT EXISTS idx_sign_ref_name ON sign_reference_images(sign_name);

ALTER TABLE sign_reference_images ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access" ON sign_reference_images
  FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Authenticated read" ON sign_reference_images
  FOR SELECT USING (auth.role() = 'authenticated');

CREATE OR REPLACE FUNCTION match_sign_images(
  query_embedding vector(1024),
  match_count int DEFAULT 3,
  similarity_threshold float DEFAULT 0.7
)
RETURNS TABLE (
  id uuid, sign_name text, sign_category text, chunk_id text, similarity float
)
LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  SELECT sri.id, sri.sign_name, sri.sign_category, sri.chunk_id,
    1 - (sri.embedding <=> query_embedding) AS similarity
  FROM sign_reference_images sri
  WHERE sri.embedding IS NOT NULL
    AND 1 - (sri.embedding <=> query_embedding) > similarity_threshold
  ORDER BY sri.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;