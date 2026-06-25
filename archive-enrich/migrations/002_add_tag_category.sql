-- Catégorie sémantique d'un tag (10 valeurs fermées + NULL si pas encore classé)
ALTER TABLE tags ADD COLUMN category TEXT;
CREATE INDEX IF NOT EXISTS idx_tags_category ON tags(category);
