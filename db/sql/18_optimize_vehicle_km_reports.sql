CREATE INDEX IF NOT EXISTS ix_vehicle_telemetry_received_vehicle
    ON vehicle_telemetry (received_at, vehicle_id);
