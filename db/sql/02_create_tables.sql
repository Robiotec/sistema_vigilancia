CREATE TYPE resource_type AS ENUM ('camera', 'vehicle', 'drone');
CREATE TYPE token_action AS ENUM ('read', 'publish');

CREATE TABLE IF NOT EXISTS companies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name varchar(160) UNIQUE NOT NULL,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name varchar(40) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid REFERENCES companies(id),
    username varchar(80) UNIQUE NOT NULL,
    email varchar(180) UNIQUE,
    password_hash varchar(255) NOT NULL,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS areas (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name varchar(160) NOT NULL,
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS user_areas (
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    area_id uuid NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, area_id)
);

CREATE TABLE IF NOT EXISTS cameras (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES companies(id),
    area_id uuid REFERENCES areas(id),
    rbox_id uuid,
    vehicle_id uuid,
    vehicle_position varchar(120),
    drone_id uuid,
    name varchar(160) NOT NULL,
    brand varchar(60) NOT NULL,
    model varchar(80),
    rtsp_url text,
    unique_code varchar(120) UNIQUE,
    camera_type varchar(40) NOT NULL DEFAULT 'fixed',
    protocol varchar(40) NOT NULL DEFAULT 'rtsp',
    ip varchar(120),
    port integer,
    username varchar(120),
    password_encrypted text,
    channel integer,
    stream integer,
    quality varchar(40),
    public_ip_enabled boolean NOT NULL DEFAULT false,
    uses_rbox boolean NOT NULL DEFAULT false,
    active boolean NOT NULL DEFAULT true,
    can_publish boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS rboxes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES companies(id),
    area_id uuid REFERENCES areas(id),
    name varchar(160) NOT NULL,
    serial varchar(120) UNIQUE NOT NULL,
    local_ip varchar(120),
    public_ip varchar(120),
    last_connection_at timestamptz,
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS vehicles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES companies(id),
    area_id uuid REFERENCES areas(id),
    owner_user_id uuid REFERENCES users(id),
    name varchar(160) NOT NULL,
    vehicle_type varchar(60) NOT NULL DEFAULT 'auto',
    unique_code varchar(120) UNIQUE,
    plate varchar(40),
    model varchar(100),
    active boolean NOT NULL DEFAULT true,
    can_publish boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS drones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES companies(id),
    area_id uuid REFERENCES areas(id),
    owner_user_id uuid REFERENCES users(id),
    name varchar(160) NOT NULL,
    provider varchar(60) NOT NULL DEFAULT 'robiotec',
    unique_code varchar(120) UNIQUE,
    drone_type varchar(60) NOT NULL DEFAULT 'robiotec',
    model varchar(100),
    manufacturer varchar(100),
    active boolean NOT NULL DEFAULT true,
    can_publish boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS stream_paths (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES companies(id),
    area_id uuid REFERENCES areas(id),
    path varchar(180) UNIQUE NOT NULL,
    resource_type resource_type NOT NULL,
    resource_id uuid NOT NULL,
    active boolean NOT NULL DEFAULT true,
    can_publish boolean NOT NULL DEFAULT true
);

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

CREATE TABLE IF NOT EXISTS stream_access_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    stream_path_id uuid NOT NULL REFERENCES stream_paths(id) ON DELETE CASCADE,
    token_hash varchar(255) NOT NULL,
    action token_action NOT NULL,
    protocol varchar(40) NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS device_publish_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    stream_path_id uuid NOT NULL REFERENCES stream_paths(id) ON DELETE CASCADE,
    token_hash varchar(255) NOT NULL,
    active boolean NOT NULL DEFAULT true,
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS drone_telemetry (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    drone_id uuid REFERENCES drones(id),
    latitude double precision,
    longitude double precision,
    altitude double precision,
    speed double precision,
    battery double precision,
    heading double precision,
    armed_state varchar(80),
    payload jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vehicle_telemetry (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_id uuid REFERENCES vehicles(id),
    latitude double precision,
    longitude double precision,
    speed double precision,
    heading double precision,
    payload jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_stream_paths_path ON stream_paths(path);
CREATE INDEX IF NOT EXISTS idx_stream_configs_path ON stream_configs(mediamtx_path);
CREATE INDEX IF NOT EXISTS idx_stream_access_tokens_stream ON stream_access_tokens(stream_path_id, expires_at);
CREATE INDEX IF NOT EXISTS idx_device_publish_tokens_stream ON device_publish_tokens(stream_path_id);
