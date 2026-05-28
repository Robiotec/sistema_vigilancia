import time
import json
import random
import requests
from datetime import datetime

URL = "http://207.246.68.223:8010/api/telemetria"

carro_id = "CARRO_MINA_BONANZA"

lat = -1.273583
lon = -79.070000

while True:
    lat += 0.00005
    lon += 0.00003

    data = {
        "id": carro_id,
        "nombre": "CARRO MINA BONANZA",
        "timestamp": datetime.now().isoformat(),
        "latitud": lat,
        "longitud": lon,
        "velocidad": random.randint(10, 45),
        "bateria": random.randint(90, 100),
        "estado": "AVANZANDO",
        "satelites": random.randint(18, 24),
        "fix_gps": "RTK Float"
    }

    try:
        r = requests.post(URL, json=data, timeout=5)
        print("Enviado:", r.status_code, data)
    except Exception as e:
        print("Error enviando:", e)

    time.sleep(1)