-- ============================================================
-- Cria as RPCs de administração de usuários
-- ============================================================
-- Executar no SQL Editor do Supabase Dashboard
-- ============================================================

-- Elimina todas as versões antigas
DROP FUNCTION IF EXISTS admin_list_users();
DROP FUNCTION IF EXISTS admin_list_users(UUID);
DROP FUNCTION IF EXISTS admin_update_role(BIGINT, TEXT);
DROP FUNCTION IF EXISTS admin_update_role(UUID, TEXT);
DROP FUNCTION IF EXISTS admin_delete_user(BIGINT);
DROP FUNCTION IF EXISTS admin_delete_user(UUID);
DROP FUNCTION IF EXISTS admin_reset_password(BIGINT, TEXT);
DROP FUNCTION IF EXISTS admin_reset_password(UUID, TEXT);
DROP FUNCTION IF EXISTS admin_insert_profile(TEXT, TEXT);

-- 1. Listar todos os usuários (retorna auth.users.id como user_id — UUID)
CREATE OR REPLACE FUNCTION admin_list_users()
RETURNS JSON
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
  result JSON;
BEGIN
  SELECT json_agg(json_build_object(
    'user_id', au.id::TEXT,
    'nome', COALESCE(p.nome, au.raw_user_meta_data->>'nome', split_part(au.email, '@', 1)),
    'email', au.email,
    'role', COALESCE(p.role, 'user')
  ) ORDER BY COALESCE(p.nome, au.raw_user_meta_data->>'nome')) INTO result
  FROM auth.users au
  LEFT JOIN profiles p ON p.email = au.email;
  RETURN COALESCE(result, '[]'::JSON);
END;
$$;

GRANT EXECUTE ON FUNCTION admin_list_users() TO authenticated;

-- 2. Atualizar role de um usuário (target_user_id = auth.users.id UUID)
CREATE OR REPLACE FUNCTION admin_update_role(target_user_id UUID, new_role TEXT)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
AS $$
BEGIN
  UPDATE profiles SET role = new_role
  WHERE email = (SELECT email FROM auth.users WHERE id = target_user_id);
  IF NOT FOUND THEN
    INSERT INTO profiles (nome, email, role)
    SELECT raw_user_meta_data->>'nome', email, new_role
    FROM auth.users WHERE id = target_user_id;
  END IF;
END;
$$;

GRANT EXECUTE ON FUNCTION admin_update_role(UUID, TEXT) TO authenticated;

-- 3. Excluir um usuário (auth + profile)
CREATE OR REPLACE FUNCTION admin_delete_user(target_user_id UUID)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
AS $$
BEGIN
  DELETE FROM profiles WHERE email = (SELECT email FROM auth.users WHERE id = target_user_id);
  DELETE FROM auth.users WHERE id = target_user_id;
END;
$$;

GRANT EXECUTE ON FUNCTION admin_delete_user(UUID) TO authenticated;

-- 4. Resetar senha de um usuário
CREATE OR REPLACE FUNCTION admin_reset_password(target_user_id UUID, new_password TEXT)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
AS $$
BEGIN
  UPDATE auth.users SET encrypted_password = crypt(new_password, gen_salt('bf')) WHERE id = target_user_id;
END;
$$;

GRANT EXECUTE ON FUNCTION admin_reset_password(UUID, TEXT) TO authenticated;

-- 5. Inserir perfil após criar auth user
CREATE OR REPLACE FUNCTION admin_insert_profile(p_nome TEXT, p_email TEXT)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
AS $$
BEGIN
  INSERT INTO profiles (nome, email, role) VALUES (p_nome, p_email, 'user');
EXCEPTION WHEN unique_violation THEN
  UPDATE profiles SET nome = p_nome WHERE email = p_email;
END;
$$;

GRANT EXECUTE ON FUNCTION admin_insert_profile(TEXT, TEXT) TO authenticated;
