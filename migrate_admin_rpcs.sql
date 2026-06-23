-- ============================================================
-- Cria as RPCs de administração de usuários
-- ============================================================
-- Executar no SQL Editor do Supabase Dashboard
-- ============================================================

-- 1. Listar todos os usuários
DROP FUNCTION IF EXISTS admin_list_users();
DROP FUNCTION IF EXISTS admin_list_users(UUID);
CREATE OR REPLACE FUNCTION admin_list_users()
RETURNS JSON
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
  result JSON;
BEGIN
  SELECT json_agg(json_build_object(
    'user_id', p.id,
    'nome', p.nome,
    'email', p.email,
    'role', p.role
  ) ORDER BY p.nome) INTO result
  FROM profiles p;
  RETURN COALESCE(result, '[]'::JSON);
END;
$$;

GRANT EXECUTE ON FUNCTION admin_list_users() TO authenticated;

-- 2. Atualizar role de um usuário
DROP FUNCTION IF EXISTS admin_update_role(BIGINT, TEXT);
DROP FUNCTION IF EXISTS admin_update_role(UUID, TEXT);
CREATE OR REPLACE FUNCTION admin_update_role(target_user_id BIGINT, new_role TEXT)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
AS $$
BEGIN
  UPDATE profiles SET role = new_role WHERE id = target_user_id;
END;
$$;

GRANT EXECUTE ON FUNCTION admin_update_role(BIGINT, TEXT) TO authenticated;

-- 3. Excluir um usuário (auth + profile)
DROP FUNCTION IF EXISTS admin_delete_user(BIGINT);
DROP FUNCTION IF EXISTS admin_delete_user(UUID);
CREATE OR REPLACE FUNCTION admin_delete_user(target_user_id BIGINT)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
  auth_uid UUID;
  user_email TEXT;
BEGIN
  SELECT email INTO user_email FROM profiles WHERE id = target_user_id;
  IF user_email IS NOT NULL THEN
    SELECT id INTO auth_uid FROM auth.users WHERE email = user_email;
  END IF;
  DELETE FROM profiles WHERE id = target_user_id;
  IF auth_uid IS NOT NULL THEN
    DELETE FROM auth.users WHERE id = auth_uid;
  END IF;
END;
$$;

GRANT EXECUTE ON FUNCTION admin_delete_user(BIGINT) TO authenticated;

-- 4. Resetar senha de um usuário
DROP FUNCTION IF EXISTS admin_reset_password(BIGINT, TEXT);
DROP FUNCTION IF EXISTS admin_reset_password(UUID, TEXT);
CREATE OR REPLACE FUNCTION admin_reset_password(target_user_id BIGINT, new_password TEXT)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
  auth_uid UUID;
  user_email TEXT;
BEGIN
  SELECT email INTO user_email FROM profiles WHERE id = target_user_id;
  IF user_email IS NOT NULL THEN
    SELECT id INTO auth_uid FROM auth.users WHERE email = user_email;
    IF auth_uid IS NOT NULL THEN
      UPDATE auth.users SET encrypted_password = crypt(new_password, gen_salt('bf')) WHERE id = auth_uid;
    END IF;
  END IF;
END;
$$;

GRANT EXECUTE ON FUNCTION admin_reset_password(BIGINT, TEXT) TO authenticated;

-- 5. Inserir perfil após criar auth user
DROP FUNCTION IF EXISTS admin_insert_profile(TEXT, TEXT);
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
