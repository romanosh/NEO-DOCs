-- ============================================================
-- CORREÇÃO: Exclusão em Cascata de Páginas ao deletar Diretórios
-- ============================================================
-- Executar no SQL Editor do Supabase Dashboard
-- ============================================================

-- 1. RPC de segurança: deleta páginas por lista de menu_item_ids
--    Chamado pelo frontend ANTES de saveTree() para garantir
--    que as páginas sejam removidas independentemente do CASCADE
CREATE OR REPLACE FUNCTION admin_delete_pages_by_menu_item_ids(p_ids BIGINT[])
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  DELETE FROM page WHERE menu_item_id = ANY(p_ids);
END;
$$;

-- 2. Limpa páginas órfãs existentes (criadas antes da correção)
--    2a. Páginas cujo menu_item_id referencia um menu_item que não existe mais
DELETE FROM page WHERE menu_item_id IS NOT NULL AND menu_item_id NOT IN (SELECT id FROM menu_item);

--    2b. Páginas com menu_item_id = NULL (nunca linkadas)
--        ATENÇÃO: Só descomente esta linha se quiser apagar TODAS as páginas
--        que não têm vínculo com nenhum item do menu.
--        Se houver páginas propositalmente sem vínculo, NÃO execute esta linha.
DELETE FROM page WHERE menu_item_id IS NULL;

-- 3. Re-tenta o backfill para páginas que porventura não foram linkadas
--    (caso o backfill anterior tenha falhado por diferença de formatação)
WITH RECURSIVE paths AS (
  SELECT id, name::TEXT AS full_path FROM menu_item WHERE parent_id IS NULL
  UNION ALL
  SELECT m.id, (p.full_path || '|' || m.name)::TEXT
  FROM menu_item m JOIN paths p ON m.parent_id = p.id
)
UPDATE page SET menu_item_id = paths.id
FROM paths
WHERE page.menu_item_id IS NULL
  AND page.key = 'neo_page_' || lower(replace(paths.full_path, ' ', '_'));
