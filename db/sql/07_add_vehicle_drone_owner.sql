ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS owner_user_id uuid REFERENCES users(id);
ALTER TABLE drones ADD COLUMN IF NOT EXISTS owner_user_id uuid REFERENCES users(id);

CREATE INDEX IF NOT EXISTS ix_vehicles_owner_user_id ON vehicles(owner_user_id);
CREATE INDEX IF NOT EXISTS ix_drones_owner_user_id ON drones(owner_user_id);

UPDATE vehicles
SET owner_user_id = (SELECT id FROM users WHERE username = 'robiotec' LIMIT 1)
WHERE owner_user_id IS NULL;

UPDATE drones
SET owner_user_id = (SELECT id FROM users WHERE username = 'robiotec' LIMIT 1)
WHERE owner_user_id IS NULL;
