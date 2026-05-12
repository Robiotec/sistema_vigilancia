INSERT INTO roles (name)
VALUES ('master'), ('company_admin'), ('area_admin'), ('operator'), ('viewer')
ON CONFLICT (name) DO NOTHING;

