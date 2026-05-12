\if :{?app_password}
\else
  \echo 'Debe ejecutar con -v app_password=<password_seguro>'
  \quit
\endif

CREATE DATABASE robiotec_vms;

CREATE USER robiotec_app WITH PASSWORD :'app_password';
GRANT ALL PRIVILEGES ON DATABASE robiotec_vms TO robiotec_app;
