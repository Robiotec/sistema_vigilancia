# Base de datos

PostgreSQL usa UUID como llave primaria y `pgcrypto` para `gen_random_uuid()`.

Orden recomendado:

```bash
psql -U postgres -v app_password='<password_seguro>' -f sql/00_create_database.sql
psql -U postgres -d robiotec_vms -f sql/01_create_extensions.sql
psql -U postgres -d robiotec_vms -f sql/02_create_tables.sql
psql -U postgres -d robiotec_vms -f sql/03_create_default_roles.sql
psql -U postgres -d robiotec_vms -v master_password_hash='<bcrypt_hash>' -f sql/04_create_master_user.sql
psql -U postgres -d robiotec_vms -f sql/05_seed_default_data.sql
psql -U postgres -d robiotec_vms -f sql/08_apply_approved_saas_model.sql
```

No guardar contrasenas reales en SQL. El script del usuario master recibe el hash bcrypt como variable `master_password_hash`.

## Modelo SaaS aprobado

`sql/08_apply_approved_saas_model.sql` aplica el modelo aprobado para producción sin borrar los datos existentes:

- agrega campos de auditoría `updated_at` y `deleted_at` a entidades maestras;
- agrega `ruc`, dirección, estado operativo, ubicación, número de serie y configuración extendida de streams;
- cambia la unicidad de `unique_code`/`id_unico` hacia el alcance por empresa mediante índices parciales;
- agrega índices para cámaras, streams y telemetría;
- agrega validación diferida para que un dron activo tenga al menos una cámara activa asociada;
- crea seeds de empresa, rol admin, usuario root, RBox, vehículo, cámara Hikvision, dron con cámara y `stream_configs`.

Para entornos nuevos se puede ejecutar después de `02_create_tables.sql`. Para entornos existentes, ejecutar con respaldo previo de PostgreSQL.
