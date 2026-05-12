ALTER TABLE cameras ADD COLUMN IF NOT EXISTS rbox_id uuid;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS vehicle_id uuid;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS drone_id uuid;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS unique_code varchar(120) UNIQUE;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS camera_type varchar(40) NOT NULL DEFAULT 'fixed';
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS protocol varchar(40) NOT NULL DEFAULT 'rtsp';
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS ip varchar(120);
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS port integer;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS username varchar(120);
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS password_encrypted text;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS channel integer;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS stream integer;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS quality varchar(40);
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS public_ip_enabled boolean NOT NULL DEFAULT false;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS uses_rbox boolean NOT NULL DEFAULT false;

ALTER TABLE rboxes ADD COLUMN IF NOT EXISTS local_ip varchar(120);
ALTER TABLE rboxes ADD COLUMN IF NOT EXISTS public_ip varchar(120);
ALTER TABLE rboxes ADD COLUMN IF NOT EXISTS last_connection_at timestamptz;

ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS vehicle_type varchar(60) NOT NULL DEFAULT 'auto';
ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS unique_code varchar(120) UNIQUE;
ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS model varchar(100);

ALTER TABLE drones ADD COLUMN IF NOT EXISTS drone_type varchar(60) NOT NULL DEFAULT 'robiotec';
ALTER TABLE drones ADD COLUMN IF NOT EXISTS model varchar(100);
ALTER TABLE drones ADD COLUMN IF NOT EXISTS manufacturer varchar(100);

CREATE TABLE IF NOT EXISTS stream_templates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    brand varchar(80) NOT NULL,
    model varchar(100),
    protocol varchar(40) NOT NULL DEFAULT 'rtsp',
    url_template text NOT NULL,
    description text
);

CREATE TABLE IF NOT EXISTS stream_configs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id uuid REFERENCES cameras(id),
    drone_id uuid REFERENCES drones(id),
    input_protocol varchar(40) NOT NULL DEFAULT 'rtsp',
    origin_url text,
    mediamtx_path varchar(180) UNIQUE NOT NULL,
    output_webrtc_url text,
    output_rtsp_url text,
    output_hls_url text,
    requires_token boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS drone_robiotec_configs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    drone_id uuid UNIQUE NOT NULL REFERENCES drones(id),
    unique_ip varchar(120),
    mediamtx_path varchar(180) UNIQUE NOT NULL,
    generated_url text
);

CREATE TABLE IF NOT EXISTS drone_dji_configs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    drone_id uuid UNIQUE NOT NULL REFERENCES drones(id),
    public_ip varchar(120),
    rtmp_port integer NOT NULL DEFAULT 1935,
    rtmp_path varchar(180) NOT NULL,
    generated_rtmp_url text
);

ALTER TABLE drone_telemetry ADD COLUMN IF NOT EXISTS latitude double precision;
ALTER TABLE drone_telemetry ADD COLUMN IF NOT EXISTS longitude double precision;
ALTER TABLE drone_telemetry ADD COLUMN IF NOT EXISTS altitude double precision;
ALTER TABLE drone_telemetry ADD COLUMN IF NOT EXISTS speed double precision;
ALTER TABLE drone_telemetry ADD COLUMN IF NOT EXISTS battery double precision;
ALTER TABLE drone_telemetry ADD COLUMN IF NOT EXISTS heading double precision;
ALTER TABLE drone_telemetry ADD COLUMN IF NOT EXISTS armed_state varchar(80);

ALTER TABLE vehicle_telemetry ADD COLUMN IF NOT EXISTS latitude double precision;
ALTER TABLE vehicle_telemetry ADD COLUMN IF NOT EXISTS longitude double precision;
ALTER TABLE vehicle_telemetry ADD COLUMN IF NOT EXISTS speed double precision;
ALTER TABLE vehicle_telemetry ADD COLUMN IF NOT EXISTS heading double precision;

CREATE INDEX IF NOT EXISTS idx_stream_configs_path ON stream_configs(mediamtx_path);
CREATE INDEX IF NOT EXISTS idx_stream_configs_camera ON stream_configs(camera_id);
CREATE INDEX IF NOT EXISTS idx_stream_configs_drone ON stream_configs(drone_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO robiotec_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO robiotec_app;
