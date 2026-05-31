ALTER TABLE cameras
  ADD COLUMN IF NOT EXISTS inference_type varchar(40) NOT NULL DEFAULT 'inactiva';

ALTER TABLE cameras
  DROP CONSTRAINT IF EXISTS ck_cameras_inference_type;

ALTER TABLE cameras
  DROP CONSTRAINT IF EXISTS cameras_inference_type_check;

UPDATE cameras
SET inference_type = CASE
  WHEN inference_type = 'rostro' THEN 'rostros'
  WHEN inference_type = 'placa' THEN 'placas'
  WHEN inference_type = 'zona' THEN 'zonas'
  WHEN inference_type = 'movimiento' THEN 'movimientos'
  WHEN inference_type IN ('rostros', 'placas', 'zonas', 'movimientos', 'inactiva') THEN inference_type
  ELSE 'inactiva'
END
WHERE inference_type IS NULL
   OR inference_type NOT IN ('rostros', 'placas', 'zonas', 'movimientos', 'inactiva');

ALTER TABLE cameras
  ADD CONSTRAINT ck_cameras_inference_type
  CHECK (inference_type IN ('rostros', 'placas', 'zonas', 'movimientos', 'inactiva'));
