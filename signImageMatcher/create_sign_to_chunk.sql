-- Tabella ponte che mappa ogni segnale al suo chunk di testo
-- Soluzione al problema della mappatura imprecisa tra segnali e chunk

CREATE TABLE IF NOT EXISTS sign_to_chunk (
  sign_name text PRIMARY KEY,
  sign_category text NOT NULL,
  chunk_id text NOT NULL,
  keywords text[],
  created_at timestamptz DEFAULT now()
);

-- Indice per ricerca veloce
CREATE INDEX IF NOT EXISTS idx_sign_to_chunk_category ON sign_to_chunk(sign_category);

-- RLS: service role full access, authenticated read
ALTER TABLE sign_to_chunk ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access" ON sign_to_chunk
  FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Authenticated read" ON sign_to_chunk
  FOR SELECT USING (auth.role() = 'authenticated');
