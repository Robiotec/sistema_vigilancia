# MediaMTX

MediaMTX debe correr en la misma VM y mantener su API interna en `127.0.0.1`.

Version instalada: `v1.17.1`.

Puertos por defecto:

- RTSP: `8554`
- RTMP: `1935`
- WebRTC/WHEP: `8889`
- HLS: `8888`
- API interna: `9997`

La autenticacion HTTP apunta a:

```yaml
authHTTPAddress: http://127.0.0.1:8003/mediamtx/auth
```

Ejemplo:

```bash
cp .env.example .env
/root/robiotec/servicios/mediamtx/scripts/start.sh
```

Verificar binario:

```bash
./mediamtx --version
```

Instalacion systemd opcional:

```bash
cd /root/robiotec/servicios
sudo ./install-systemd.sh
sudo systemctl enable --now robiotec-mediamtx
```
