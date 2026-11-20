"""T23 — Pruebas unitarias para adjuntos conversacionales y orquestación SEE.

Cubre: AttachmentStore, selección de tarea SEE, proyección de contexto
para THINK y aislamiento multi-household.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from homi_attachment_store import (  # noqa: E402
    AttachmentStore,
    AttachmentRecord,
    STATE_UPLOADED,
    STATE_ANALYSIS_COMPLETED,
    STATE_ANALYSIS_FAILED,
    get_store,
)
from homi_see_orchestrator import (  # noqa: E402
    seleccionar_tarea_see,
    SeeOrchestratorError,
)
from homi_context_builder import (  # noqa: E402
    build_context_projection,
    ContextEnvelope,
)
from homi_contracts import (  # noqa: E402
    RequestEnvelope, RequestContext, Capability,
)
from homi_contracts.ids import (  # noqa: E402
    new_request_id, new_trace_id, new_turn_id, new_conversation_id,
)
from homi_tool_loop import (  # noqa: E402
    ATTACHMENT_ONLY_PROVIDER_TEXT,
    provider_text_for_model,
)


# ---------------------------------------------------------------------------
# Fixture de archivo PNG válido (1x1 píxel rojo)
# ---------------------------------------------------------------------------

VALID_PNG_1X1 = bytes([
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
    0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR
    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1
    0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53, 0xDE,
    0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41, 0x54,  # IDAT
    0x78, 0x9C, 0x63, 0xF8, 0x0F, 0x00, 0x00, 0x01,
    0x01, 0x00, 0x05, 0xD2, 0xDC, 0x02, 0x1E,
    0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44,
    0xAE, 0x42, 0x60, 0x82,
])


# ---------------------------------------------------------------------------
# AttachmentStore
# ---------------------------------------------------------------------------

def test_create_upload_and_get(tmp_path):
    """Subir archivo y recuperarlo con metadatos."""
    db = tmp_path / "test.db"
    root = tmp_path / "storage"
    store = AttachmentStore(root=root, db_path=db)

    record = store.create_upload(
        household_id="hogar_1",
        owner_id="usuario_a",
        conversation_id="conv_1",
        original_filename="factura.png",
        file_bytes=VALID_PNG_1X1,
        declared_mime="image/png",
    )

    assert record.attachment_id.startswith("att_")
    assert record.status == STATE_UPLOADED
    assert record.mime_type == "image/png"
    assert record.size_bytes == len(VALID_PNG_1X1)
    assert record.sha256
    assert record.expires_at
    assert Path(record.storage_path).exists()

    recovered = store.get_for_owner(
        record.attachment_id,
        household_id="hogar_1",
        owner_id="usuario_a",
    )
    assert recovered is not None
    assert recovered.attachment_id == record.attachment_id
    assert recovered.original_filename == "factura.png"

    store.close()


def test_upload_preserves_unicode_and_spaces_in_display_filename(tmp_path):
    """El nombre visible conserva Unicode; el archivo físico sigue siendo seguro."""

    store = AttachmentStore(
        root=tmp_path / "storage",
        db_path=tmp_path / "test.db",
    )

    record = store.create_upload(
        household_id="hogar_1",
        owner_id="usuario_a",
        conversation_id="conv_unicode",
        original_filename="reporte anual ñ.pdf",
        file_bytes=b"%PDF-1.4\n%%EOF\n",
    )

    assert record.original_filename == "reporte anual ñ.pdf"
    assert Path(record.storage_path).name.isascii()
    assert Path(record.storage_path).suffix == ".pdf"
    assert record.storage_path.endswith(".pdf")

    store.close()


def test_attachment_only_turn_uses_provider_fallback_without_changing_text():
    """El texto público vacío conserva el fallback provider-only."""

    assert provider_text_for_model(
        "",
        has_attachments=True,
    ) == ATTACHMENT_ONLY_PROVIDER_TEXT
    assert provider_text_for_model(
        "texto real",
        has_attachments=True,
    ) == "texto real"
    assert provider_text_for_model(
        "",
        has_attachments=False,
    ) == ""


def test_upload_rejects_empty_file(tmp_path):
    """Rechazar archivo vacío."""
    store = AttachmentStore(root=tmp_path / "storage", db_path=tmp_path / "test.db")
    with pytest.raises(ValueError, match="archivo_vacio"):
        store.create_upload(
            household_id="hogar_1",
            owner_id="usuario_a",
            conversation_id=None,
            original_filename="empty.png",
            file_bytes=b"",
        )
    store.close()


def test_upload_rejects_invalid_type(tmp_path):
    """Rechazar tipo de archivo no soportado (extensión no permitida)."""
    store = AttachmentStore(root=tmp_path / "storage", db_path=tmp_path / "test.db")
    with pytest.raises(ValueError, match="extension_no_soportada"):
        store.create_upload(
            household_id="hogar_1",
            owner_id="usuario_a",
            conversation_id=None,
            original_filename="malware.exe",
            file_bytes=b"MZ\x90\x00\x03",
        )
    store.close()


def test_upload_rejects_too_large(tmp_path):
    """Rechazar archivo excede el límite."""
    store = AttachmentStore(root=tmp_path / "storage", db_path=tmp_path / "test.db")
    with pytest.raises(ValueError, match="archivo_demasiado_grande"):
        store.create_upload(
            household_id="hogar_1",
            owner_id="usuario_a",
            conversation_id=None,
            original_filename="big.png",
            file_bytes=b"\x00" * (21 * 1024 * 1024),
        )
    store.close()


def test_household_isolation(tmp_path):
    """Un household no puede ver attachments de otro."""
    store = AttachmentStore(root=tmp_path / "storage", db_path=tmp_path / "test.db")

    record = store.create_upload(
        household_id="hogar_1",
        owner_id="usuario_a",
        conversation_id=None,
        original_filename="privada.png",
        file_bytes=VALID_PNG_1X1,
    )

    # Otro household: no debe encontrarlo
    assert store.get_for_owner(
        record.attachment_id,
        household_id="hogar_2",
        owner_id="usuario_b",
    ) is None

    # Otro owner, mismo household: no debe encontrarlo
    assert store.get_for_owner(
        record.attachment_id,
        household_id="hogar_1",
        owner_id="usuario_b",
    ) is None

    # Correcto: sí lo encuentra
    assert store.get_for_owner(
        record.attachment_id,
        household_id="hogar_1",
        owner_id="usuario_a",
    ) is not None

    store.close()


def test_delete_attachment(tmp_path):
    """Eliminar attachment borra registro y archivo físico."""
    store = AttachmentStore(root=tmp_path / "storage", db_path=tmp_path / "test.db")
    record = store.create_upload(
        household_id="hogar_1",
        owner_id="usuario_a",
        conversation_id=None,
        original_filename="borrar.png",
        file_bytes=VALID_PNG_1X1,
    )
    path = Path(record.storage_path)
    assert path.exists()

    ok = store.delete(record.attachment_id, household_id="hogar_1", owner_id="usuario_a")
    assert ok is True
    assert not path.exists()
    assert store.get(record.attachment_id) is None

    # Eliminar de nuevo: no existe
    ok2 = store.delete(record.attachment_id, household_id="hogar_1", owner_id="usuario_a")
    assert ok2 is False

    store.close()


def test_delete_isolation(tmp_path):
    """No se puede eliminar attachment de otro household."""
    store = AttachmentStore(root=tmp_path / "storage", db_path=tmp_path / "test.db")
    record = store.create_upload(
        household_id="hogar_1",
        owner_id="usuario_a",
        conversation_id=None,
        original_filename="a.png",
        file_bytes=VALID_PNG_1X1,
    )
    ok = store.delete(record.attachment_id, household_id="hogar_2", owner_id="usuario_b")
    assert ok is False
    store.close()


def test_see_result_persistence_and_continuity(tmp_path):
    """Guardar y recuperar SeeResult; continuidad por conversación."""
    store = AttachmentStore(root=tmp_path / "storage", db_path=tmp_path / "test.db")

    att = store.create_upload(
        household_id="hogar_1",
        owner_id="usuario_a",
        conversation_id="conv_alpha",
        original_filename="factura.pdf",
        file_bytes=b"%PDF-1.4 fake",
        declared_mime="application/pdf",
    )

    sr = store.save_see_result(
        attachment_id=att.attachment_id,
        conversation_id="conv_alpha",
        turn_id="turn_1",
        request_id="req_1",
        task="extract_invoice",
        status="success",
        artifact_type="document",
        result={"fields": {"merchant": "Edenor", "amount": 48320}},
    )

    # Recuperar por attachment
    sr2 = store.get_see_result_for_attachment(
        att.attachment_id, household_id="hogar_1", owner_id="usuario_a"
    )
    assert sr2 is not None
    assert sr2.see_result_id == sr.see_result_id
    assert sr2.task == "extract_invoice"

    # Continuidad: último SeeResult de la conversación
    sr3 = store.get_latest_see_result_for_conversation(
        "conv_alpha", household_id="hogar_1", owner_id="usuario_a"
    )
    assert sr3 is not None
    assert sr3.see_result_id == sr.see_result_id

    # Aislamiento: otro household no lo ve
    sr4 = store.get_latest_see_result_for_conversation(
        "conv_alpha", household_id="hogar_2", owner_id="usuario_b"
    )
    assert sr4 is None

    store.close()


# ---------------------------------------------------------------------------
# Selección de tarea SEE
# ---------------------------------------------------------------------------

class _FakeAttachment:
    def __init__(self, mime_type):
        self.mime_type = mime_type


def test_seleccionar_tarea_factura_documento():
    """Mensaje de factura + documento -> extract_invoice."""
    tarea = seleccionar_tarea_see(
        texto_usuario="¿Cuánto tengo que pagar de esta factura?",
        mime_type="application/pdf",
        attachment_record=_FakeAttachment("application/pdf"),
    )
    assert tarea == "extract_invoice"


def test_seleccionar_tarea_leer_documento():
    """Mensaje de leer + documento -> read_document."""
    tarea = seleccionar_tarea_see(
        texto_usuario="Leé este documento por favor",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        attachment_record=_FakeAttachment("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    )
    assert tarea == "read_document"


def test_seleccionar_tarea_describir_imagen():
    """Mensaje genérico + imagen -> describe_image."""
    tarea = seleccionar_tarea_see(
        texto_usuario="Mirá esta imagen",
        mime_type="image/png",
        attachment_record=_FakeAttachment("image/png"),
    )
    assert tarea == "describe_image"


def test_seleccionar_tarea_formato_incompatible():
    """Formato sin tarea aplicable -> error con código FORMATO_NO_SOPORTADO."""
    with pytest.raises(SeeOrchestratorError) as exc_info:
        seleccionar_tarea_see(
            texto_usuario="¿qué hay?",
            mime_type="application/octet-stream",
            attachment_record=_FakeAttachment("application/octet-stream"),
        )
    assert exc_info.value.code == "FORMATO_NO_SOPORTADO"


# ---------------------------------------------------------------------------
# Context builder: see_results en proyección para THINK
# ---------------------------------------------------------------------------

def test_context_projection_incluye_see_results():
    """Los see_results del payload llegan a la proyección de THINK."""
    ctx = RequestContext(
        request_id=new_request_id(),
        trace_id=new_trace_id(),
        turn_id=new_turn_id(),
        conversation_id=new_conversation_id(),
        actor_id="usuario_a",
        household_id="hogar_1",
        timestamp=datetime.now(timezone.utc),
    )
    request = RequestEnvelope(
        context=ctx,
        capability=Capability.THINK,
        operation="infer_with_tools",
        payload={
            "text": "¿Cuánto vence?",
            "_see_results": [
                {
                    "attachment_id": "att_1",
                    "task": "extract_invoice",
                    "status": "success",
                    "artifact_type": "document",
                    "text": "Factura de prueba",
                    "fields": {"amount": 48320, "currency": "ARS"},
                    "warnings": [],
                    "engine": "docling",
                    "provider_id": "document-docling",
                }
            ],
        },
    )

    proj = build_context_projection(request)
    assert "see_results" in proj
    assert len(proj["see_results"]) == 1
    sr = proj["see_results"][0]
    assert sr["task"] == "extract_invoice"
    assert sr["fields"]["amount"] == 48320
    assert sr["fields"]["currency"] == "ARS"
    assert proj["actor_status"] == "VALID"
    assert proj["household_status"] == "VALID"


def test_context_projection_sin_see_results():
    """Sin _see_results, la proyección no trae la clave."""
    ctx = RequestContext(
        request_id=new_request_id(),
        trace_id=new_trace_id(),
        turn_id=new_turn_id(),
        conversation_id=new_conversation_id(),
        actor_id="usuario_a",
        household_id="hogar_1",
        timestamp=datetime.now(timezone.utc),
    )
    request = RequestEnvelope(
        context=ctx,
        capability=Capability.THINK,
        operation="infer_with_tools",
        payload={"text": "Hola, ¿cómo estás?"},
    )

    proj = build_context_projection(request)
    assert "see_results" not in proj
