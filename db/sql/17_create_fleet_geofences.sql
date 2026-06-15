CREATE TABLE IF NOT EXISTS geofences (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES companies(id),
    name varchar(160) NOT NULL,
    geofence_type varchar(20) NOT NULL CHECK (geofence_type IN ('circle', 'polygon')),
    geometry jsonb NOT NULL,
    active boolean NOT NULL DEFAULT true,
    description text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE INDEX IF NOT EXISTS ix_geofences_company_active
    ON geofences (company_id, active)
    WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS vehicle_geofence_states (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_id uuid NOT NULL REFERENCES vehicles(id),
    geofence_id uuid NOT NULL REFERENCES geofences(id),
    inside boolean NOT NULL DEFAULT false,
    last_gps_at timestamptz,
    last_changed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_vehicle_geofence_state UNIQUE (vehicle_id, geofence_id)
);

CREATE INDEX IF NOT EXISTS ix_vehicle_geofence_states_vehicle
    ON vehicle_geofence_states (vehicle_id);

CREATE TABLE IF NOT EXISTS geofence_alerts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_id uuid NOT NULL REFERENCES vehicles(id),
    plate varchar(40),
    geofence_id uuid NOT NULL REFERENCES geofences(id),
    geofence_name varchar(160) NOT NULL,
    event_type varchar(20) NOT NULL CHECK (event_type IN ('entry', 'exit')),
    gps_at timestamptz,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    latitude double precision,
    longitude double precision,
    processed boolean NOT NULL DEFAULT false,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_geofence_alerts_recorded_at
    ON geofence_alerts (recorded_at DESC);

CREATE INDEX IF NOT EXISTS ix_geofence_alerts_vehicle_time
    ON geofence_alerts (vehicle_id, gps_at DESC);

CREATE INDEX IF NOT EXISTS ix_geofence_alerts_geofence_id
    ON geofence_alerts (geofence_id);

CREATE INDEX IF NOT EXISTS ix_geofence_alerts_processed
    ON geofence_alerts (processed);

CREATE INDEX IF NOT EXISTS ix_geofence_alerts_processed_recorded_at
    ON geofence_alerts (processed, recorded_at DESC);

GRANT SELECT, INSERT, UPDATE, DELETE ON geofences TO robiotec_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON vehicle_geofence_states TO robiotec_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON geofence_alerts TO robiotec_app;
