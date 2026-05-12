-- Protege el id_unico/codigo_unico de Camara.
-- Este valor es el path estable de publicacion en MediaMTX y no debe cambiar
-- cuando se edita el nombre u otros campos de la camara.

CREATE OR REPLACE FUNCTION prevent_camera_unique_code_change()
RETURNS trigger AS $$
BEGIN
    IF OLD.unique_code IS NOT NULL
       AND NEW.unique_code IS DISTINCT FROM OLD.unique_code THEN
        NEW.unique_code := OLD.unique_code;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_camera_unique_code_change ON cameras;

CREATE TRIGGER trg_prevent_camera_unique_code_change
BEFORE UPDATE ON cameras
FOR EACH ROW
EXECUTE FUNCTION prevent_camera_unique_code_change();