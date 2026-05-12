\if :{?master_password_hash}
\else
  \echo 'Debe ejecutar con -v master_password_hash=<bcrypt_hash>'
  \quit
\endif

WITH inserted_user AS (
    INSERT INTO users (username, password_hash, active)
    VALUES ('robiotec', :'master_password_hash', true)
    ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash
    RETURNING id
)
INSERT INTO user_roles (user_id, role_id)
SELECT inserted_user.id, roles.id
FROM inserted_user, roles
WHERE roles.name = 'master'
ON CONFLICT DO NOTHING;

