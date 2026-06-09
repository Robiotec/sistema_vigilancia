-- Elimina los constraints UNIQUE globales de email y username en users.
-- Ambos bloquean soft-delete: un usuario eliminado (deleted_at IS NOT NULL)
-- impide reutilizar su email o username en una cuenta nueva o restaurada.
--
-- Los índices parciales correctos (solo filas activas) ya existen desde la
-- migración 08 y permanecen intactos:
--   uq_users_email_active    → UNIQUE lower(email) WHERE email IS NOT NULL AND deleted_at IS NULL
--   uq_users_username_active → se crea aquí si aún no existe

-- 1. Eliminar constraint global de email
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_key;

-- 2. Eliminar constraint global de username
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_username_key;

-- 3. Crear índice parcial para username si no existe (equivalente al de email)
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username_active
    ON users (lower(username))
    WHERE deleted_at IS NULL;

-- 4. Mismo patrón para roles: el constraint global bloquea reutilizar
--    nombres de roles eliminados con soft-delete.
ALTER TABLE roles DROP CONSTRAINT IF EXISTS roles_name_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_roles_name_active
    ON roles (lower(name))
    WHERE deleted_at IS NULL;
