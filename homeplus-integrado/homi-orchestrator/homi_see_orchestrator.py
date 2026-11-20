"""T23 — Orquestador SEE desde HOMI-D hacia HOMI-B.

Responsabilidades de HOMI-D:
- Resolver identidad y household del turno autenticado.
- Validar pertenencia y estado del attachment.
- Emitir acceso temporal de alcance mínimo hacia HOMI-B.
- Solicitar procesamiento SEE al worker (contrato see-1.0.0).
- Recibir, validar y normalizar el SeeResult.
- Incorporar el resultado al contexto del turno.

No se propaga base64 entre servicios. El archivo viaja del almacenamiento
privado de D a un acceso temporal autorizado en B (staging endpoint).
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request

from homi_attachment_store import (
    AttachmentStore,
    get_store,
    STATE_ANALYSIS_COMPLETED,
    STATE_ANALYSIS_FAILED,
    STATE_ANALYSIS_IN_PROGRESS,
    STATE_ANALYSIS_PARTIAL,
    STATE_ANALYSIS_PENDING,
    sniff_mime,
)
from homi_context_builder import build_context_projection

# ---------------------------------------------------------------------------
# Configuración del endpoint SEE (HOMI-B)
# ---------------------------------------------------------------------------

SEE_BASE_URL = os.getenv("HOMI_SEE_BASE_URL", "http://100.77.57.38:8021")
SEE_INTERNAL_TOKEN = os.getenv(
    "SEE_INTERNAL_TOKEN",
    "y5RJdeXlESMzcsDLEeDOWHsHI1UkHmmGWiIz/e9sFZE=",
)

# Tareas SEE disponibles en el worker (contrato see-1.0.0, T19)
SEE_TASK_DESCRIBE_IMAGE = "describe_image"
SEE_TASK_READ_DOCUMENT = "read_document"
SEE_TASK_EXTRACT_TABLE = "extract_table"
SEE_TASK_EXTRACT_INVOICE = "extract_invoice"
SEE_TASK_CLASSIFY_DOCUMENT = "classify_document"
SEE_TASK_INSPECT_UI = "inspect_ui"

# Tiempo de vida de una referencia de staging en B (segundos)
STAGING_TTL_SECONDS = 3600

# Tiempos de espera
SEE_REQUEST_TIMEOUT_S = 120.0
STAGE_REQUEST_TIMEOUT_S = 60.0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


class SeeOrchestratorError(Exception):
    """Error tipado del orquestador SEE."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        http_status: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.http_status = http_status
        self.details = details or {}


def _http_post_json(
    url: str,
    *,
    token: str,
    body: dict[str, Any],
    timeout_s: float,
) -> tuple[int, dict[str, Any] | str]:
    """POST JSON con autenticación Bearer. Devuelve (status, cuerpo)."""
    data = json.dumps(body).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            raw = response.read().decode("utf-8", "replace")
            try:
                return response.status, json.loads(raw)
            except ValueError:
                return response.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, raw
    except urllib.error.URLError as exc:
        raise SeeOrchestratorError(
            "SEE_TRANSPORT_FAILURE",
            f"no se pudo conectar con HOMI-B: {exc.reason}",
            retryable=True,
        ) from exc
    except Exception as exc:  # pragma: no cover - defensivo
        raise SeeOrchestratorError(
            "SEE_TRANSPORT_FAILURE",
            f"error inesperado contactando HOMI-B: {exc}",
            retryable=False,
        ) from exc


def _http_post_raw_file(
    url: str,
    *,
    token: str,
    filename: str,
    content: bytes,
    content_type: str,
    timeout_s: float,
) -> tuple[int, dict[str, Any] | str]:
    """POST de un archivo binario (cuerpo raw, sin base64) con autenticación Bearer.

    Los metadatos viajan en encabezados (X-Filename, X-Content-Type), nunca
    el archivo codificado en base64 por el sistema.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Filename": filename,
        "X-Content-Type": content_type,
        "Content-Type": "application/octet-stream",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, data=content, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            raw = response.read().decode("utf-8", "replace")
            try:
                return response.status, json.loads(raw)
            except ValueError:
                return response.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, raw
    except urllib.error.URLError as exc:
        raise SeeOrchestratorError(
            "SEE_STAGE_TRANSPORT_FAILURE",
            f"no se pudo conectar con el staging de HOMI-B: {exc.reason}",
            retryable=True,
        ) from exc
    except Exception as exc:  # pragma: no cover - defensivo
        raise SeeOrchestratorError(
            "SEE_STAGE_TRANSPORT_FAILURE",
            f"error inesperado en staging de HOMI-B: {exc}",
            retryable=False,
        ) from exc


def _authorize_b(token: str) -> None:
    """Verifica que HOMI-B esté disponible y autenticado."""
    status, payload = _http_post_json(
        f"{SEE_BASE_URL.rstrip('/')}/health",
        token=token,
        body={},
        timeout_s=10.0,
    )
    # /health no requiere auth; si responde, el nodo está vivo.
    if status < 200 or status >= 300:
        raise SeeOrchestratorError(
            "SEE_NODE_UNAVAILABLE",
            "HOMI-B no responde",
            retryable=True,
            http_status=status,
        )


def seleccionar_tarea_see(
    *,
    texto_usuario: str,
    mime_type: str | None,
    attachment_record: Any | None = None,
) -> str:
    """Elige la tarea SEE a partir del mensaje, el MIME y las capacidades.

    No se introduce un clasificador de IA: es una estrategia heurística
    acotada sobre palabras clave del mensaje y el tipo de contenido.
    """
    texto = (texto_usuario or "").strip().lower()
    mime = (mime_type or "").lower()
    es_imagen = mime in ("image/png", "image/jpeg", "image/bmp")
    es_documento = mime in (
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/plain", "text/markdown",
    )

    # Palabras clave de factura
    palabras_factura = {
        "factura", "recibo", "comprobante", "pagar", "pago", "importe",
        "total", "monto", "vencimiento", "fecha de vencimiento", "edenor",
        "edemsa", "empresa", "proveedor",
    }
    # Palabras clave de tabla
    palabras_tabla = {"tabla", "cuadro", "filas", "columnas", "celda"}
    # Palabras clave de lectura documental
    palabras_leer = {"leer", "contenido", "texto", "documento", "qué dice", "que dice"}
    # Palabras clave de descripción genérica
    palabras_describir = {"mirá", "mira", "qué hay", "que hay", "qué aparece", "que aparece", "imagen", "foto"}

    es_factura = any(p in texto for p in palabras_factura)
    es_tabla = any(p in texto for p in palabras_tabla)
    es_leer_doc = any(p in texto for p in palabras_leer)
    es_describir = any(p in texto for p in palabras_describir)

    # Estrategia: preferir tarea específica si el mensaje lo pide y el formato lo permite
    if es_factura and es_documento:
        return SEE_TASK_EXTRACT_INVOICE
    if es_tabla and es_documento:
        return SEE_TASK_EXTRACT_TABLE
    if es_leer_doc and es_documento:
        return SEE_TASK_READ_DOCUMENT
    if es_factura and es_imagen:
        # Una imagen de factura (escaneo) se lee como documento
        return SEE_TASK_EXTRACT_INVOICE
    if es_tabla and es_imagen:
        return SEE_TASK_EXTRACT_TABLE
    if es_leer_doc and es_imagen:
        return SEE_TASK_READ_DOCUMENT
    if es_describir and es_imagen:
        return SEE_TASK_DESCRIBE_IMAGE

    # Petición genérica «mirá esto»: comprensión apropiada al formato
    if es_imagen:
        return SEE_TASK_DESCRIBE_IMAGE
    if es_documento:
        return SEE_TASK_READ_DOCUMENT

    # Formato incompatible con cualquier tarea: error coherente
    raise SeeOrchestratorError(
        "FORMATO_NO_SOPORTADO",
        "el formato del archivo no admite ninguna operación SEE disponible",
        retryable=False,
        details={"mime_type": mime_type},
    )


class SeeOrchestrator:
    """Orquesta el acceso de HOMI-D a HOMI-B para un attachment autorizado."""

    def __init__(
        self,
        *,
        store: AttachmentStore | None = None,
        base_url: str | None = None,
        token: str | None = None,
    ) -> None:
        self.store = store or get_store()
        self.base_url = (base_url or SEE_BASE_URL).rstrip("/")
        self.token = token or SEE_INTERNAL_TOKEN

    # ------------------------------------------------------------------
    # Autorización del attachment
    # ------------------------------------------------------------------

    def validar_attachment_para_turno(
        self,
        *,
        attachment_id: str,
        household_id: str,
        owner_id: str,
    ) -> Any:
        """Verifica identidad, household, pertenencia y estado del attachment."""
        from homi_attachment_store import (
            STATE_UPLOADED,
            STATE_ANALYSIS_PENDING,
            STATE_ANALYSIS_IN_PROGRESS,
            STATE_ANALYSIS_COMPLETED,
            STATE_ANALYSIS_PARTIAL,
        )

        record = self.store.get_for_owner(
            attachment_id,
            household_id=household_id,
            owner_id=owner_id,
        )
        if record is None:
            raise SeeOrchestratorError(
                "ATTACHMENT_NOT_FOUND",
                "el adjunto no existe o no pertenece al usuario/household",
                retryable=False,
                http_status=404,
            )

        # Verificar expiración física del archivo
        expira = _parse_iso(record.expires_at)
        if expira is not None and _utc_now() >= expira:
            raise SeeOrchestratorError(
                "ATTACHMENT_EXPIRED",
                "el adjunto ha expirado y su archivo ya no está disponible",
                retryable=False,
                http_status=410,
            )

        # Verificar que el archivo físico exista
        storage_path = Path(record.storage_path)
        if not storage_path.exists():
            raise SeeOrchestratorError(
                "ATTACHMENT_FILE_MISSING",
                "el archivo del adjunto no está disponible en storage",
                retryable=False,
                http_status=404,
            )

        # Estados válidos para enviar a SEE
        estados_validos = frozenset({
            STATE_UPLOADED,
            STATE_ANALYSIS_PENDING,
            STATE_ANALYSIS_IN_PROGRESS,
            STATE_ANALYSIS_COMPLETED,
            STATE_ANALYSIS_PARTIAL,
        })
        if record.status not in estados_validos:
            raise SeeOrchestratorError(
                "ATTACHMENT_INVALID_STATE",
                f"el adjunto está en estado '{record.status}' y no puede analizarse",
                retryable=False,
                http_status=400,
            )

        return record

    # ------------------------------------------------------------------
    # Staging hacia HOMI-B
    # ------------------------------------------------------------------

    def stage_archivo_a_b(
        self,
        *,
        attachment_record: Any,
    ) -> str:
        """Copia el archivo al staging de HOMI-B y devuelve la access_ref opaca.

        HOMI-D transfiere el binario (no base64) al endpoint temporal de B.
        B lo almacena en su directorio de staging y registra una access_ref
        de vida corta en su artefact registry.
        """
        storage_path = Path(attachment_record.storage_path)
        if not storage_path.exists():
            raise SeeOrchestratorError(
                "ATTACHMENT_FILE_MISSING",
                "el archivo del adjunto no está disponible para staging",
                retryable=False,
                http_status=404,
            )

        content = storage_path.read_bytes()
        mime = attachment_record.mime_type or sniff_mime(storage_path)
        nombre_original = attachment_record.original_filename or storage_path.name

        url = f"{self.base_url}/v1/see/stage"
        status, payload = _http_post_raw_file(
            url,
            token=self.token,
            filename=nombre_original,
            content=content,
            content_type=mime,
            timeout_s=STAGE_REQUEST_TIMEOUT_S,
        )

        if status >= 400:
            code = "SEE_STAGE_REJECTED"
            if isinstance(payload, dict):
                err = payload.get("error") or {}
                code = err.get("code", code)
            raise SeeOrchestratorError(
                code,
                "HOMI-B rechazó el staging del archivo",
                retryable=False,
                http_status=status,
                details={"mime_type": mime},
            )

        if not isinstance(payload, dict) or "access_ref" not in payload:
            raise SeeOrchestratorError(
                "SEE_STAGE_INVALID_RESPONSE",
                "HOMI-B no devolvió una access_ref válida",
                retryable=False,
                http_status=status,
            )

        return str(payload["access_ref"])

    # ------------------------------------------------------------------
    # Llamada a SEE en HOMI-B
    # ------------------------------------------------------------------

    def ejecutar_see(
        self,
        *,
        access_ref: str,
        task: str,
        mime_type: str | None,
        request_id: str,
        hints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Pide a HOMI-B que procese el artefacto y devuelve el SeeResult."""
        url = f"{self.base_url}/v1/see"
        body: dict[str, Any] = {
            "contract_version": "see-1.0.0",
            "request_id": request_id,
            "artifact": {
                "id": access_ref,
                "access_ref": access_ref,
                "mime_type": mime_type,
            },
            "task": task,
            "hints": hints or {"language": "es"},
        }

        started = time.perf_counter()
        status, payload = _http_post_json(
            url,
            token=self.token,
            body=body,
            timeout_s=SEE_REQUEST_TIMEOUT_S,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if status >= 400:
            code = "SEE_ERROR"
            retryable = False
            details: dict[str, Any] = {"http_status": status, "elapsed_ms": elapsed_ms}
            if isinstance(payload, dict):
                err = payload.get("error") or {}
                code = err.get("code", code)
                retryable = bool(err.get("retryable", False))
                details["code"] = err.get("code")
                details["message"] = err.get("message")
            raise SeeOrchestratorError(
                code,
                "HOMI-B devolvió un error al procesar SEE",
                retryable=retryable,
                http_status=status,
                details=details,
            )

        if not isinstance(payload, dict):
            raise SeeOrchestratorError(
                "SEE_INVALID_RESPONSE",
                "HOMI-B devolvió una respuesta no válida",
                retryable=False,
                http_status=status,
            )

        if payload.get("status") != "success":
            err = payload.get("error") or {}
            raise SeeOrchestratorError(
                "SEE_BUSINESS_ERROR",
                "HOMI-B reportó un error en el resultado SEE",
                retryable=bool(err.get("retryable", False)),
                http_status=status,
                details={
                    "code": err.get("code"),
                    "message": err.get("message"),
                    "elapsed_ms": elapsed_ms,
                },
            )

        # Validar que el request_id corresponda (no mezclar respuestas)
        if payload.get("request_id") != request_id:
            raise SeeOrchestratorError(
                "SEE_REQUEST_ID_MISMATCH",
                "el request_id del SeeResult no coincide con la solicitud",
                retryable=False,
                http_status=status,
            )

        return payload

    # ------------------------------------------------------------------
    # Orquestación completa para un turno
    # ------------------------------------------------------------------

    def procesar_attachment_para_turno(
        self,
        *,
        attachment_id: str,
        household_id: str,
        owner_id: str,
        texto_usuario: str,
        conversation_id: str,
        turn_id: str,
    ) -> dict[str, Any]:
        """Flujo completo: validar, staging, SEE, devolver SeeResult normalizado.

        Marca el estado del attachment en cada etapa.
        """
        record = self.validar_attachment_para_turno(
            attachment_id=attachment_id,
            household_id=household_id,
            owner_id=owner_id,
        )

        # Marcar análisis en curso
        self.store.update_status(
            record.attachment_id,
            STATE_ANALYSIS_IN_PROGRESS,
            turn_id=turn_id,
            conversation_id=conversation_id,
        )

        request_id = f"req_{uuid.uuid4().hex[:16]}"

        try:
            task = seleccionar_tarea_see(
                texto_usuario=texto_usuario,
                mime_type=record.mime_type,
                attachment_record=record,
            )
        except SeeOrchestratorError:
            self.store.update_status(
                record.attachment_id, STATE_ANALYSIS_FAILED, turn_id=turn_id
            )
            raise

        # Staging del archivo a B
        try:
            access_ref = self.stage_archivo_a_b(attachment_record=record)
        except SeeOrchestratorError:
            self.store.update_status(
                record.attachment_id, STATE_ANALYSIS_FAILED, turn_id=turn_id
            )
            raise

        # Ejecutar SEE
        try:
            see_result = self.ejecutar_see(
                access_ref=access_ref,
                task=task,
                mime_type=record.mime_type,
                request_id=request_id,
                hints={"language": "es"},
            )
        except SeeOrchestratorError:
            self.store.update_status(
                record.attachment_id, STATE_ANALYSIS_FAILED, turn_id=turn_id
            )
            raise

        # Persistir SeeResult y asociar al attachment/turno
        see_result_id = None
        try:
            sr = self.store.save_see_result(
                attachment_id=record.attachment_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
                request_id=request_id,
                task=task,
                status=see_result.get("status", "success"),
                artifact_type=see_result.get("artifact_type"),
                result=see_result,
            )
            see_result_id = sr.see_result_id
        except Exception:
            # No fallar el turno por un error de persistencia del resultado;
            # el SeeResult ya se obtuvo. Se registra y se continúa.
            pass

        # Determinar estado final de análisis
        warnings = see_result.get("warnings") or []
        fields = see_result.get("fields") or {}
        tiene_campos = bool(fields)
        if warnings and not tiene_campos:
            estado_final = STATE_ANALYSIS_PARTIAL
        elif tiene_campos or see_result.get("text"):
            estado_final = STATE_ANALYSIS_COMPLETED
        else:
            estado_final = STATE_ANALYSIS_COMPLETED

        self.store.update_status(
            record.attachment_id,
            estado_final,
            turn_id=turn_id,
            conversation_id=conversation_id,
            see_result_id=see_result_id,
            see_task=task,
        )

        return {
            "attachment_id": record.attachment_id,
            "see_result_id": see_result_id,
            "task": task,
            "status": see_result.get("status", "success"),
            "artifact_type": see_result.get("artifact_type"),
            "text": see_result.get("text"),
            "fields": see_result.get("fields", {}),
            "regions": see_result.get("regions", []),
            "tables": see_result.get("tables", []),
            "sections": see_result.get("sections", []),
            "provenance": see_result.get("provenance", []),
            "confidence_level": see_result.get("confidence_level"),
            "confidence": see_result.get("confidence"),
            "warnings": see_result.get("warnings", []),
            "engine": see_result.get("engine"),
            "provider_id": see_result.get("provider_id"),
            "timing_ms": see_result.get("timing_ms"),
            "request_id": request_id,
            "conversation_id": conversation_id,
            "turn_id": turn_id,
        }


# Instancia compartida
_orchestrator: SeeOrchestrator | None = None


def get_orchestrator() -> SeeOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = SeeOrchestrator()
    return _orchestrator
