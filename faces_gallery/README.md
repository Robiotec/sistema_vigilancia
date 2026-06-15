# Faces Gallery

Galeria central de embeddings faciales para sincronizacion con Jetson y servicios de reconocimiento.

Los archivos generados viven en `faces_gallery/data/` y no se versionan:

- `embeddings.npz`
- `gallery.faiss`
- `metadata.json`
- `idx_to_cedula.json`
- `state.json`
- `version`

La API Central publica estos artefactos por:

- `GET /api/faces-gallery/manifest`
- `GET /api/faces-gallery/files/{filename}`
- `GET /api/faces-gallery/metadata`

Configurar en `apicentral/.env`:

- `FACES_GALLERY_DIR=/root/robiotec/faces_gallery/data`
- `FACES_GALLERY_TOKEN=<token_largo_para_jetsons>`

Las Jetson deben enviar el token en `X-Robiotec-Faces-Token` o como `Authorization: Bearer ...`.
