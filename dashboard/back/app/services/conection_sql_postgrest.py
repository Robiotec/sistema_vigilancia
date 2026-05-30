import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    "host": "207.246.68.223",
    "port": 5432,
    "database": "robiotec_vms",
    "user": "robiotec_app",
    "password": "Robiotec@2026",
    "sslmode": "require"
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def fetch_all(query, params=None):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchall()
    finally:
        conn.close()


def execute(query, params=None):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            conn.commit()
    finally:
        conn.close()
        
if __name__ == "__main__":
    # Conexión de prueba
    try:
        conn = get_connection()
        print("Conexión exitosa a PostgreSQL")
        
        # consulta de Cameras
        cameras = fetch_all("SELECT * FROM notification_email_recipients")
        for cam in cameras:
            print(cam)
        
    except Exception as e:
        print(f"Error al conectar a PostgreSQL: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
            