CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  CREATE TYPE estado_dispositivo AS ENUM ('activo', 'inactivo', 'mantenimiento', 'error');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
  CREATE TYPE estado_stream AS ENUM ('online', 'offline', 'error', 'pendiente');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

ALTER TABLE companies ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE users ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE roles ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE areas ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE rboxes ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE vehicles ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE drones ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE cameras ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE stream_paths ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE stream_configs ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE stream_configs ALTER COLUMN requires_token SET DEFAULT true;
ALTER TABLE stream_configs ALTER COLUMN updated_at SET DEFAULT now();
ALTER TABLE stream_templates ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE drone_robiotec_configs ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE drone_dji_configs ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE stream_access_tokens ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE device_publish_tokens ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE drone_telemetry ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE vehicle_telemetry ALTER COLUMN id SET DEFAULT gen_random_uuid();

ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS ruc varchar(30),
  ADD COLUMN IF NOT EXISTS address text,
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

CREATE UNIQUE INDEX IF NOT EXISTS uq_companies_ruc_active
  ON companies (ruc)
  WHERE ruc IS NOT NULL AND deleted_at IS NULL;

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS name varchar(160),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

UPDATE users
SET name = username
WHERE name IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_active
  ON users (lower(email))
  WHERE email IS NOT NULL AND deleted_at IS NULL;

ALTER TABLE roles
  ADD COLUMN IF NOT EXISTS description text,
  ADD COLUMN IF NOT EXISTS active boolean NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

ALTER TABLE user_roles
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS active boolean NOT NULL DEFAULT true;

ALTER TABLE rboxes
  ADD COLUMN IF NOT EXISTS location text,
  ADD COLUMN IF NOT EXISTS status varchar(40) NOT NULL DEFAULT 'activo',
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

CREATE INDEX IF NOT EXISTS ix_rboxes_company_active
  ON rboxes (company_id, active)
  WHERE deleted_at IS NULL;

ALTER TABLE vehicles
  ADD COLUMN IF NOT EXISTS description text,
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

ALTER TABLE vehicles DROP CONSTRAINT IF EXISTS vehicles_unique_code_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_vehicles_company_plate_active
  ON vehicles (company_id, upper(plate))
  WHERE plate IS NOT NULL AND deleted_at IS NULL;

ALTER TABLE drones
  ADD COLUMN IF NOT EXISTS serial_number varchar(160),
  ADD COLUMN IF NOT EXISTS status varchar(40) NOT NULL DEFAULT 'activo',
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

ALTER TABLE drones DROP CONSTRAINT IF EXISTS drones_unique_code_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_drones_company_unique_code_active
  ON drones (company_id, unique_code)
  WHERE unique_code IS NOT NULL AND deleted_at IS NULL;

ALTER TABLE cameras
  ADD COLUMN IF NOT EXISTS vehicle_position varchar(120),
  ADD COLUMN IF NOT EXISTS status varchar(40) NOT NULL DEFAULT 'activo',
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

ALTER TABLE cameras DROP CONSTRAINT IF EXISTS cameras_unique_code_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_cameras_company_unique_code_active
  ON cameras (company_id, unique_code)
  WHERE unique_code IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_cameras_company_active
  ON cameras (company_id, active)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_cameras_rbox ON cameras (rbox_id);
CREATE INDEX IF NOT EXISTS ix_cameras_vehicle ON cameras (vehicle_id);
CREATE INDEX IF NOT EXISTS ix_cameras_drone ON cameras (drone_id);

ALTER TABLE stream_configs
  ADD COLUMN IF NOT EXISTS publish_path varchar(120),
  ADD COLUMN IF NOT EXISTS publish_url text,
  ADD COLUMN IF NOT EXISTS output_protocol varchar(40) NOT NULL DEFAULT 'webrtc',
  ADD COLUMN IF NOT EXISTS mediamtx_server varchar(160),
  ADD COLUMN IF NOT EXISTS mediamtx_port integer,
  ADD COLUMN IF NOT EXISTS token_encrypted text,
  ADD COLUMN IF NOT EXISTS stream_status varchar(40) NOT NULL DEFAULT 'pendiente',
  ADD COLUMN IF NOT EXISTS webrtc_enabled boolean NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS rtsp_enabled boolean NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS rtmp_enabled boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS active boolean NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

UPDATE stream_configs
SET
  publish_path = COALESCE(publish_path, mediamtx_path),
  publish_url = COALESCE(publish_url, output_rtsp_url),
  mediamtx_server = COALESCE(mediamtx_server, '127.0.0.1'),
  mediamtx_port = COALESCE(mediamtx_port, 8554)
WHERE publish_path IS NULL
   OR publish_url IS NULL
   OR mediamtx_server IS NULL
   OR mediamtx_port IS NULL;

CREATE INDEX IF NOT EXISTS ix_stream_configs_publish_path_active
  ON stream_configs (publish_path)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_stream_configs_status_active
  ON stream_configs (stream_status, active);

ALTER TABLE drone_dji_configs
  ADD COLUMN IF NOT EXISTS app_id varchar(160),
  ADD COLUMN IF NOT EXISTS app_key_encrypted text,
  ADD COLUMN IF NOT EXISTS device_sn varchar(160),
  ADD COLUMN IF NOT EXISTS active boolean NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

ALTER TABLE drone_robiotec_configs
  ADD COLUMN IF NOT EXISTS endpoint text,
  ADD COLUMN IF NOT EXISTS token_encrypted text,
  ADD COLUMN IF NOT EXISTS operation_mode varchar(40) NOT NULL DEFAULT 'api',
  ADD COLUMN IF NOT EXISTS active boolean NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS ix_drone_telemetry_drone_received_desc
  ON drone_telemetry (drone_id, received_at DESC);

CREATE INDEX IF NOT EXISTS ix_vehicle_telemetry_vehicle_received_desc
  ON vehicle_telemetry (vehicle_id, received_at DESC);

CREATE OR REPLACE FUNCTION validate_active_drone_has_camera()
RETURNS trigger AS $$
BEGIN
  IF NEW.active IS TRUE AND COALESCE(NEW.deleted_at, 'infinity'::timestamptz) = 'infinity'::timestamptz THEN
    IF NOT EXISTS (
      SELECT 1
      FROM cameras c
      WHERE c.drone_id = NEW.id
        AND c.active IS TRUE
        AND c.deleted_at IS NULL
    ) THEN
      RAISE EXCEPTION 'El dron % debe tener al menos una camara activa asociada', NEW.id;
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_active_drone_has_camera ON drones;
CREATE CONSTRAINT TRIGGER trg_active_drone_has_camera
AFTER INSERT OR UPDATE ON drones
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION validate_active_drone_has_camera();

DROP TRIGGER IF EXISTS trg_companies_updated_at ON companies;
CREATE TRIGGER trg_companies_updated_at BEFORE UPDATE ON companies
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_roles_updated_at ON roles;
CREATE TRIGGER trg_roles_updated_at BEFORE UPDATE ON roles
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_rboxes_updated_at ON rboxes;
CREATE TRIGGER trg_rboxes_updated_at BEFORE UPDATE ON rboxes
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_vehicles_updated_at ON vehicles;
CREATE TRIGGER trg_vehicles_updated_at BEFORE UPDATE ON vehicles
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_drones_updated_at ON drones;
CREATE TRIGGER trg_drones_updated_at BEFORE UPDATE ON drones
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_cameras_updated_at ON cameras;
CREATE TRIGGER trg_cameras_updated_at BEFORE UPDATE ON cameras
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_stream_configs_updated_at ON stream_configs;
CREATE TRIGGER trg_stream_configs_updated_at BEFORE UPDATE ON stream_configs
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

BEGIN;
SET CONSTRAINTS ALL DEFERRED;

INSERT INTO companies (id, name, ruc, address, active)
VALUES (
  '00000000-0000-0000-0000-000000000001',
  'Robiotec Demo',
  '0999999999001',
  'Guayaquil, Ecuador',
  true
)
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
    ruc = COALESCE(companies.ruc, EXCLUDED.ruc),
    address = COALESCE(companies.address, EXCLUDED.address);

INSERT INTO roles (id, name, description, active)
VALUES (
  '00000000-0000-0000-0000-000000000010',
  'admin',
  'Administrador general de la plataforma',
  true
)
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
    description = EXCLUDED.description,
    active = true;

INSERT INTO users (company_id, username, name, email, password_hash, active)
VALUES (
  '00000000-0000-0000-0000-000000000001',
  'robiotec',
  'Robiotec Admin',
  'admin@robiotec.local',
  crypt('Robiotec@2026', gen_salt('bf')),
  true
)
ON CONFLICT (username) DO UPDATE
SET company_id = EXCLUDED.company_id,
    name = EXCLUDED.name,
    email = COALESCE(users.email, EXCLUDED.email),
    password_hash = EXCLUDED.password_hash,
    active = true,
    deleted_at = NULL;

INSERT INTO user_roles (user_id, role_id, active)
SELECT users.id, roles.id, true
FROM users, roles
WHERE users.username = 'robiotec'
  AND roles.name = 'admin'
ON CONFLICT (user_id, role_id) DO UPDATE
SET active = true;

INSERT INTO rboxes (id, company_id, name, serial, local_ip, location, status, active)
VALUES (
  '00000000-0000-0000-0000-000000000030',
  '00000000-0000-0000-0000-000000000001',
  'RBox Principal',
  'RBOX-DEMO-001',
  '192.168.1.10',
  'Garita principal',
  'activo',
  true
)
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
    serial = EXCLUDED.serial,
    local_ip = EXCLUDED.local_ip,
    location = EXCLUDED.location,
    status = EXCLUDED.status,
    active = true;

INSERT INTO vehicles (id, company_id, name, plate, vehicle_type, unique_code, description, active, can_publish)
VALUES (
  '00000000-0000-0000-0000-000000000040',
  '00000000-0000-0000-0000-000000000001',
  'Vehiculo Patrulla 1',
  'GTR-001',
  'auto',
  'VEH-DEMO-001',
  'Vehiculo de supervision',
  true,
  true
)
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
    plate = EXCLUDED.plate,
    unique_code = EXCLUDED.unique_code,
    description = EXCLUDED.description,
    active = true;

INSERT INTO drones (id, company_id, name, provider, unique_code, drone_type, model, manufacturer, serial_number, status, active, can_publish)
VALUES (
  '00000000-0000-0000-0000-000000000050',
  '00000000-0000-0000-0000-000000000001',
  'Dron Robiotec Demo',
  'robiotec',
  'DRON-DEMO-001',
  'robiotec',
  'RB-AIR-1',
  'Robiotec',
  'SN-RB-0001',
  'activo',
  true,
  true
)
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
    unique_code = EXCLUDED.unique_code,
    model = EXCLUDED.model,
    manufacturer = EXCLUDED.manufacturer,
    serial_number = EXCLUDED.serial_number,
    status = EXCLUDED.status,
    active = true;

INSERT INTO cameras (
  id, company_id, rbox_id, drone_id, name, brand, unique_code, camera_type,
  protocol, ip, port, username, password_encrypted, channel, stream, quality,
  status, active, can_publish
)
VALUES
(
  '00000000-0000-0000-0000-000000000060',
  '00000000-0000-0000-0000-000000000001',
  '00000000-0000-0000-0000-000000000030',
  NULL,
  'Camara Hikvision Entrada',
  'hikvision',
  'CAM-HIK-001',
  'fixed',
  'rtsp',
  '192.168.1.64',
  554,
  'visor',
  crypt('R0B10T3C2025', gen_salt('bf')),
  101,
  0,
  'mainstream',
  'activo',
  true,
  true
),
(
  '00000000-0000-0000-0000-000000000061',
  '00000000-0000-0000-0000-000000000001',
  NULL,
  '00000000-0000-0000-0000-000000000050',
  'Camara principal Dron Demo',
  'robiotec',
  'DRON-DEMO-001',
  'drone',
  'rtmp',
  NULL,
  NULL,
  NULL,
  NULL,
  1,
  0,
  'mainstream',
  'activo',
  true,
  true
)
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
    brand = EXCLUDED.brand,
    unique_code = EXCLUDED.unique_code,
    camera_type = EXCLUDED.camera_type,
    protocol = EXCLUDED.protocol,
    status = EXCLUDED.status,
    active = true;

INSERT INTO stream_configs (
  camera_id, input_protocol, origin_url, mediamtx_path, output_webrtc_url,
  output_rtsp_url, output_hls_url, publish_path, publish_url, output_protocol,
  mediamtx_server, mediamtx_port, stream_status, webrtc_enabled, rtsp_enabled, rtmp_enabled
  , requires_token
)
VALUES
(
  '00000000-0000-0000-0000-000000000060',
  'rtsp',
  'rtsp://visor:R0B10T3C2025@192.168.1.64:554/Streaming/Channels/101',
  'CAM-HIK-001',
  '/stream/token/CAM-HIK-001',
  'rtsp://127.0.0.1:8554/CAM-HIK-001',
  '/CAM-HIK-001/index.m3u8',
  'CAM-HIK-001',
  'rtsp://127.0.0.1:8554/CAM-HIK-001',
  'webrtc',
  '127.0.0.1',
  8554,
  'pendiente',
  true,
  true,
  false,
  true
),
(
  '00000000-0000-0000-0000-000000000061',
  'rtmp',
  'rtmp://127.0.0.1:1935/DRON-DEMO-001',
  'DRON-DEMO-001',
  '/stream/token/DRON-DEMO-001',
  'rtsp://127.0.0.1:8554/DRON-DEMO-001',
  '/DRON-DEMO-001/index.m3u8',
  'DRON-DEMO-001',
  'rtsp://127.0.0.1:8554/DRON-DEMO-001',
  'webrtc',
  '127.0.0.1',
  8554,
  'pendiente',
  true,
  true,
  true,
  true
)
ON CONFLICT (mediamtx_path) DO UPDATE
SET origin_url = EXCLUDED.origin_url,
    publish_path = EXCLUDED.publish_path,
    publish_url = EXCLUDED.publish_url,
    output_webrtc_url = EXCLUDED.output_webrtc_url,
    output_rtsp_url = EXCLUDED.output_rtsp_url,
    output_hls_url = EXCLUDED.output_hls_url,
    output_protocol = EXCLUDED.output_protocol,
    mediamtx_server = EXCLUDED.mediamtx_server,
    mediamtx_port = EXCLUDED.mediamtx_port,
    stream_status = EXCLUDED.stream_status;

COMMIT;
