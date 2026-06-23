-- ============================================================
-- MIGRAÇÃO: Substitui content (HTML) por data_json (estruturado)
-- ============================================================
-- Executar no SQL Editor do Supabase Dashboard
-- ============================================================

-- 1. Adiciona colunas template_type e data_json
ALTER TABLE page
  ADD COLUMN IF NOT EXISTS template_type VARCHAR(50) DEFAULT 'blank';
ALTER TABLE page
  ADD COLUMN IF NOT EXISTS data_json JSONB DEFAULT '{"version":1,"sections":[]}';

-- 2. Remove coluna content (agora substituída por data_json)
ALTER TABLE page DROP COLUMN IF EXISTS content;
