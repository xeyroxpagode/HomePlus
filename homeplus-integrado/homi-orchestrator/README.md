# HOMI-D — núcleo de orquestación (portado)

Origen: `C:\Homi\orchestrator` (baseline con hashes en `MANIFEST.csv`).
Adaptaciones: catálogo v2 regenerado con 92 tools del 18/11, ancla SHA recalculada,
allow-list ampliada y T24_READ_ENABLED por defecto. NO se portaron voz/T31/LiveKit/TTS.

Arranque: `python -m uvicorn app:app --host 127.0.0.1 --port 8001`
Requiere THINK (HOMI-A), STT (HOMI-C) y PostgreSQL con esquema `homi`.
Si HOMI-A está DOWN, `/invoke` responde error de proveedor: no se simula inferencia.
