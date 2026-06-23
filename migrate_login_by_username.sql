-- ============================================================
-- Permite login por nome de usuário (além de email)
-- ============================================================
-- Executar no SQL Editor do Supabase Dashboard
-- ============================================================

-- Função para resolver nome → email (acessível anonimamente)
CREATE OR REPLACE FUNCTION get_email_by_nome(p_nome TEXT)
RETURNS TEXT
LANGUAGE plpgsql SECURITY DEFINER STABLE
AS $$
DECLARE
  v_email TEXT;
BEGIN
  SELECT email INTO v_email FROM profiles WHERE LOWER(nome) = LOWER(p_nome) LIMIT 1;
  RETURN v_email;
END;
$$;

-- Garante que anônimos podem chamar esta função
GRANT EXECUTE ON FUNCTION get_email_by_nome(TEXT) TO anon;
