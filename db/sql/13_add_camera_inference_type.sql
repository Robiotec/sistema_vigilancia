ALTER TABLE cameras
  ADD COLUMN IF NOT EXISTS inference_type varchar(40) NOT NULL DEFAULT 'inactiva';

ALTER TABLE cameras
  DROP CONSTRAINT IF EXISTS ck_cameras_inference_type;

ALTER TABLE cameras
  DROP CONSTRAINT IF EXISTS cameras_inference_type_check;

UPDATE cameras
SET inference_type = CASE
  WHEN inference_type = 'rostros' THEN 'rostro'
  WHEN inference_type = 'placas' THEN 'placa'
  WHEN inference_type = 'zonas' THEN 'zona'
  WHEN inference_type = 'movimientos' THEN 'movimiento'
  WHEN inference_type IN ('rostro', 'placa', 'zona', 'movimiento', 'inactiva') THEN inference_type
  ELSE 'inactiva'
END
WHERE inference_type IS NULL
   OR inference_type NOT IN ('rostro', 'placa', 'zona', 'movimiento', 'inactiva');

ALTER TABLE cameras
  ADD CONSTRAINT ck_cameras_inference_type
  CHECK (inference_type IN ('rostro', 'placa', 'zona', 'movimiento', 'inactiva'));
