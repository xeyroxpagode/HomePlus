"""T23 — Almacén de adjuntos conversacionales (HOMI-D).

Registro de metadatos y almacenamiento privado de archivos adjuntos
aportados por usuarios durante una conversación de Homi en HomePlus.

Reconciliación G1.2: los metadatos viven ahora en el esquema ``homi`` de
la base de datos PostgreSQL existente de HomePlus. Los archivos binarios
siguen alojados en el directorio privado de staging de HOMI-D
(almacenamiento de archivos, no base de datos). Este módulo es el único
propietario del SQL de las tablas ``homi.attachments`` y
``homi.see_results``.

El almacenamiento de archivo es temporal/privado de HOMI-D como punto de
estaging para el envío autorizado a HOMI-B. En producción este archivo
debería delegar en el storage de HomePlus (Supabase Storage) y este módulo
soportaría esa referencia opaca sin cambiar el contrato de attachment_id.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Mapping

from homi_db import Database, DatabaseError, get_database


# ---------------------------------------------------------------------------
# Configuración de límites V1
# ---------------------------------------------------------------------------

MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024          # 20 MB (mismo tope que SEE worker)
MIN_ATTACHMENT_BYTES = 1                         # rechazar archivo vacío
ATTACHMENT_RETENTION_HOURS = 24                  # ciclo de vida del archivo físico

EXTENSIONES_PERMITIDAS = {
    ".png", ".jpg", ".jpeg", ".bmp",
    ".pdf", ".docx", ".xlsx", ".pptx",
    ".txt", ".md",
}

# MIMEs canónicos soportados (alinea con el SEE worker)
MIMES_SOPORTADOS = {
    "image/png", "image/jpeg", "image/bmp",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain", "text/markdown",
}

# Estados del ciclo de vida del adjunto conversacional
STATE_SELECTED = "selected"
STATE_UPLOADING = "uploading"
STATE_UPLOADED = "uploaded"
STATE_UPLOAD_FAILED = "upload_failed"
STATE_ANALYSIS_PENDING = "analysis_pending"
STATE_ANALYSIS_IN_PROGRESS = "analysis_in_progress"
STATE_ANALYSIS_COMPLETED = "analysis_completed"
STATE_ANALYSIS_PARTIAL = "analysis_partial"
STATE_ANALYSIS_FAILED = "analysis_failed"

ALL_STATES = frozenset({
    STATE_SELECTED, STATE_UPLOADING, STATE_UPLOADED, STATE_UPLOAD_FAILED,
    STATE_ANALYSIS_PENDING, STATE_ANALYSIS_IN_PROGRESS,
    STATE_ANALYSIS_COMPLETED, STATE_ANALYSIS_PARTIAL, STATE_ANALYSIS_FAILED,
})


def utc_now() -> datetime:
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


def new_attachment_id() -> str:
    return f"att_{uuid.uuid4().hex[:24]}"


def new_see_result_id() -> str:
    return f"see_{uuid.uuid4().hex[:24]}"


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sniff_mime(path: Path) -> str:
    """Detección de tipo real por contenido (magic bytes / ZIP)."""
    with path.open("rb") as handle:
        head = handle.read(4096)
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"BM"):
        return "image/bmp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        return _sniff_ooxml(path)
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "application/x-ole-storage"
    if _looks_textual(head):
        return "text/plain"
    return "application/octet-stream"


def _sniff_ooxml(path: Path) -> str:
    import zipfile
    markers = {
        "word/": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xl/": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "ppt/": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    except Exception:
        return "application/zip"
    for marker, mime in markers.items():
        if any(name.startswith(marker) for name in names):
            return mime
    return "application/zip"


def _looks_textual(head: bytes) -> bool:
    if not head:
        return False
    sample = head[:512]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    printable = sum(1 for b in sample if 32 <= b < 127 or b in (9, 10, 13))
    return printable / max(len(sample), 1) > 0.9


def extension_permitida(nombre_archivo: str) -> bool:
    ext = Path(nombre_archivo).suffix.lower()
    return ext in EXTENSIONES_PERMITIDAS


def nombre_seguro(nombre_archivo: str) -> str:
    """Return a safe display basename without discarding Unicode or spaces.

    Path components and control characters are removed. The remaining name is
    the user-visible original filename and therefore keeps valid spaces,
    accents and non-ASCII characters.
    """

    raw = str(nombre_archivo or "")
    base = raw.replace("\\", "/").rsplit("/", 1)[-1]
    safe = "".join(
        character
        for character in base
        if ord(character) >= 32 and character != "\x7f"
    ).strip()

    if not safe or safe in (".", ".."):
        return "archivo"

    return safe


def nombre_storage_seguro(nombre_archivo: str) -> str:
    """Return an ASCII-safe physical filename while preserving its suffix."""

    visible = nombre_seguro(nombre_archivo)
    suffix = Path(visible).suffix.lower()
    stem = visible[:-len(suffix)] if suffix else visible
    ascii_stem = "".join(
        character
        for character in stem
        if character.isascii()
        and (character.isalnum() or character in "._-")
    ).strip("._-")

    return (ascii_stem[:48] or "archivo") + suffix


# ---------------------------------------------------------------------------
# Modelo de datos
# ---------------------------------------------------------------------------


@dataclass
class AttachmentRecord:
    attachment_id: str
    household_id: str
    owner_id: str
    conversation_id: str | None
    turn_id: str | None
    storage_path: str
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    status: str
    created_at: str
    expires_at: str
    see_result_id: str | None = None
    see_task: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attachment_id": self.attachment_id,
            "household_id": self.household_id,
            "owner_id": self.owner_id,
            "conversation_id": self.conversation_id,
            "turn_id": self.turn_id,
            "storage_path": self.storage_path,
            "original_filename": self.original_filename,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "status": self.status,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "see_result_id": self.see_result_id,
            "see_task": self.see_task,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "AttachmentRecord":
        return cls(
            attachment_id=str(row["attachment_id"]),
            household_id=str(row["household_id"]),
            owner_id=str(row["owner_id"]),
            conversation_id=(
                str(row["conversation_id"])
                if row["conversation_id"] is not None
                else None
            ),
            turn_id=(
                str(row["turn_id"])
                if row["turn_id"] is not None
                else None
            ),
            storage_path=str(row["storage_path"]),
            original_filename=str(row["original_filename"]),
            mime_type=str(row["mime_type"]),
            size_bytes=int(row["size_bytes"]),
            sha256=str(row["sha256"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            expires_at=str(row["expires_at"]),
            see_result_id=(
                str(row["see_result_id"])
                if row["see_result_id"] is not None
                else None
            ),
            see_task=(
                str(row["see_task"])
                if row["see_task"] is not None
                else None
            ),
        )


@dataclass
class SeeResultRecord:
    see_result_id: str
    attachment_id: str
    conversation_id: str
    turn_id: str
    request_id: str
    task: str
    status: str
    artifact_type: str | None
    result_json: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "see_result_id": self.see_result_id,
            "attachment_id": self.attachment_id,
            "conversation_id": self.conversation_id,
            "turn_id": self.turn_id,
            "request_id": self.request_id,
            "task": self.task,
            "status": self.status,
            "artifact_type": self.artifact_type,
            "result": json.loads(self.result_json),
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Almacén
# ---------------------------------------------------------------------------

class AttachmentStore:
    """Almacén de metadatos y archivos de adjuntos conversacionales.

    Los archivos viven en un directorio privado bajo HOMI-D. Los metadatos
    viven en PostgreSQL (esquema ``homi``). El acceso está acotado por
    household y owner.
    """

    def __init__(
        self,
        root: str | Path | None = None,
        db_path: str | Path | None = None,
        *,
        schema: str | None = None,
        database: Database | None = None,
    ) -> None:
        # ``db_path`` se acepta por compatibilidad con llamadas existentes
        # pero se ignora: los metadatos ahora viven en PostgreSQL.
        self._db_path_ignored = db_path

        if root is None:
            root = Path(__file__).resolve().parent / "storage" / "attachments"
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

        self._database = database or get_database()
        self.schema = schema or self._database.config.schema
        self._lock = threading.RLock()

    # -- tabla helpers -----------------------------------------------------

    def _table(self, name: str) -> str:
        return f'"{self.schema}"."{name}"'

    def _required_tables(self) -> None:
        for name in ("attachments", "see_results"):
            if not self._database.table_exists(name):
                raise DatabaseError(
                    f"the homi schema table {name} is not available in PostgreSQL"
                )

    # -- attachment operations --------------------------------------------

    def create_upload(
        self,
        *,
        household_id: str,
        owner_id: str,
        conversation_id: str | None,
        original_filename: str,
        file_bytes: bytes,
        declared_mime: str | None = None,
    ) -> AttachmentRecord:
        """Valida y almacena un archivo adjunto. Devuelve el registro."""
        self._required_tables()

        if not file_bytes:
            raise ValueError("archivo_vacio")

        if len(file_bytes) > MAX_ATTACHMENT_BYTES:
            raise ValueError("archivo_demasiado_grande")

        if not extension_permitida(original_filename):
            raise ValueError("extension_no_soportada")

        # Escribir a archivo temporal para sniffing
        tmp_name = nombre_storage_seguro(original_filename)
        tmp_path = self.root / f".tmp_{uuid.uuid4().hex[:12]}_{tmp_name}"
        try:
            tmp_path.write_bytes(file_bytes)
            real_mime = sniff_mime(tmp_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

        if real_mime not in MIMES_SOPORTADOS:
            raise ValueError("tipo_no_soportado")

        # Validar coherencia MIME declarado vs real
        if declared_mime is not None:
            declared = declared_mime.strip().lower().split(";")[0].strip()
            if declared not in MIMES_SOPORTADOS:
                raise ValueError("mime_declarado_no_soportado")
            if declared != real_mime:
                raise ValueError("mime_no_coincide")

        attachment_id = new_attachment_id()
        stored_name = (
            f"{attachment_id}_{nombre_storage_seguro(original_filename)}"
        )
        storage_path = str(self.root / stored_name)

        now = utc_now()
        expires = now + timedelta(hours=ATTACHMENT_RETENTION_HOURS)

        # Escribir archivo definitivo
        self.root.joinpath(stored_name).write_bytes(file_bytes)

        digest = sha256_of_file(self.root.joinpath(stored_name))

        record = AttachmentRecord(
            attachment_id=attachment_id,
            household_id=household_id,
            owner_id=owner_id,
            conversation_id=conversation_id,
            turn_id=None,
            storage_path=storage_path,
            original_filename=nombre_seguro(original_filename),
            mime_type=real_mime,
            size_bytes=len(file_bytes),
            sha256=digest,
            status=STATE_UPLOADED,
            created_at=_iso(now),
            expires_at=_iso(expires),
        )

        try:
            self._database.execute(
                f"""
                insert into {self._table('attachments')} (
                    attachment_id, household_id, owner_id, conversation_id,
                    turn_id, storage_path, original_filename, mime_type,
                    size_bytes, sha256, status, created_at, expires_at,
                    see_result_id, see_task
                ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          %s, %s, %s)
                """,
                (
                    record.attachment_id, record.household_id,
                    record.owner_id, record.conversation_id,
                    record.turn_id, record.storage_path,
                    record.original_filename, record.mime_type,
                    record.size_bytes, record.sha256, record.status,
                    record.created_at, record.expires_at,
                    record.see_result_id, record.see_task,
                ),
            )

        except DatabaseError as error:
            # Si falla la persistencia de metadatos, borrar el archivo
            # físico para no dejar huérfanos.
            try:
                self.root.joinpath(stored_name).unlink()
            except OSError:
                pass
            raise ValueError("almacenamiento_no_disponible") from error

        return record

    def get(self, attachment_id: str) -> AttachmentRecord | None:
        self._required_tables()
        row = self._database.query_one(
            f"select * from {self._table('attachments')} "
            "where attachment_id = %s",
            (attachment_id,),
        )
        return AttachmentRecord.from_row(row) if row else None

    def get_for_owner(
        self,
        attachment_id: str,
        *,
        household_id: str,
        owner_id: str,
    ) -> AttachmentRecord | None:
        """Obtiene un attachment solo si pertenece al household y owner."""
        self._required_tables()
        row = self._database.query_one(
            """
            select * from """ + self._table('attachments') + """
            where attachment_id = %s and household_id = %s and owner_id = %s
            """,
            (attachment_id, household_id, owner_id),
        )
        return AttachmentRecord.from_row(row) if row else None

    def list_by_conversation(
        self,
        conversation_id: str,
        *,
        household_id: str,
        owner_id: str,
    ) -> list[AttachmentRecord]:
        self._required_tables()
        rows = self._database.query(
            """
            select * from """ + self._table('attachments') + """
            where conversation_id = %s and household_id = %s and owner_id = %s
            order by created_at desc
            """,
            (conversation_id, household_id, owner_id),
        )
        return [AttachmentRecord.from_row(row) for row in rows]

    def update_status(
        self,
        attachment_id: str,
        status: str,
        *,
        turn_id: str | None = None,
        see_result_id: str | None = None,
        see_task: str | None = None,
        conversation_id: str | None = None,
    ) -> None:
        self._required_tables()

        fields = ["status = %s"]
        params: list[Any] = [status]
        if turn_id is not None:
            fields.append("turn_id = %s")
            params.append(turn_id)
        if see_result_id is not None:
            fields.append("see_result_id = %s")
            params.append(see_result_id)
        if see_task is not None:
            fields.append("see_task = %s")
            params.append(see_task)
        if conversation_id is not None:
            fields.append("conversation_id = %s")
            params.append(conversation_id)
        params.append(attachment_id)

        self._database.execute(
            f"update {self._table('attachments')} set "
            + ", ".join(fields) + " where attachment_id = %s",
            tuple(params),
        )

    def delete(self, attachment_id: str, *, household_id: str, owner_id: str) -> bool:
        """Elimina un attachment solo si pertenece al household/owner."""
        record = self.get_for_owner(
            attachment_id, household_id=household_id, owner_id=owner_id
        )
        if record is None:
            return False

        # Borrar archivo físico si existe
        try:
            p = Path(record.storage_path)
            if p.exists():
                p.unlink()
        except OSError:
            pass

        self._database.execute(
            f"delete from {self._table('attachments')} "
            "where attachment_id = %s",
            (attachment_id,),
        )
        return True

    def purge_expired(self) -> int:
        """Elimina archivos físicos y registros expirados. Devuelve count."""
        self._required_tables()
        now = utc_now()
        rows = self._database.query(
            f"select attachment_id, storage_path from {self._table('attachments')} "
            "where expires_at is not null and expires_at < %s",
            (_iso(now),),
        )
        removed = 0
        for row in rows:
            try:
                p = Path(row["storage_path"])
                if p.exists():
                    p.unlink()
            except OSError:
                pass
            self._database.execute(
                f"delete from {self._table('attachments')} "
                "where attachment_id = %s",
                (str(row["attachment_id"]),),
            )
            removed += 1
        return removed

    def close(self) -> None:
        """Close the store (no-op: the database connection is shared)."""

    # -- SeeResult operations --------------------------------------------

    def save_see_result(
        self,
        *,
        attachment_id: str,
        conversation_id: str,
        turn_id: str,
        request_id: str,
        task: str,
        status: str,
        artifact_type: str | None,
        result: dict[str, Any],
    ) -> SeeResultRecord:
        self._required_tables()

        see_result_id = new_see_result_id()
        now = utc_now()
        result_json = json.dumps(result, ensure_ascii=False)

        record = SeeResultRecord(
            see_result_id=see_result_id,
            attachment_id=attachment_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            request_id=request_id,
            task=task,
            status=status,
            artifact_type=artifact_type,
            result_json=result_json,
            created_at=_iso(now),
        )

        self._database.execute(
            f"""
            insert into {self._table('see_results')} (
                see_result_id, attachment_id, conversation_id, turn_id,
                request_id, task, status, artifact_type, result_json,
                created_at
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                record.see_result_id, record.attachment_id,
                record.conversation_id, record.turn_id,
                record.request_id, record.task, record.status,
                record.artifact_type, record.result_json,
                record.created_at,
            ),
        )
        return record

    def _see_result_from_row(self, row: Mapping[str, Any]) -> SeeResultRecord:
        result_json = row.get("result_json")
        if isinstance(result_json, str):
            try:
                result_json = json.dumps(json.loads(result_json), ensure_ascii=False)
            except (TypeError, ValueError):
                pass
        return SeeResultRecord(
            see_result_id=str(row["see_result_id"]),
            attachment_id=str(row["attachment_id"]),
            conversation_id=str(row["conversation_id"]),
            turn_id=str(row["turn_id"]),
            request_id=str(row["request_id"]),
            task=str(row["task"]),
            status=str(row["status"]),
            artifact_type=(
                str(row["artifact_type"])
                if row["artifact_type"] is not None
                else None
            ),
            result_json=str(result_json),
            created_at=str(row["created_at"]),
        )

    def get_see_result(
        self,
        see_result_id: str,
        *,
        household_id: str,
        owner_id: str,
    ) -> SeeResultRecord | None:
        """Obtiene un SeeResult validando pertenencia a través del attachment."""
        self._required_tables()
        row = self._database.query_one(
            """
            select sr.* from """ + self._table('see_results') + """ sr
            join """ + self._table('attachments') + """ a
              on sr.attachment_id = a.attachment_id
            where sr.see_result_id = %s
              and a.household_id = %s
              and a.owner_id = %s
            """,
            (see_result_id, household_id, owner_id),
        )
        return self._see_result_from_row(row) if row else None

    def get_latest_see_result_for_conversation(
        self,
        conversation_id: str,
        *,
        household_id: str,
        owner_id: str,
    ) -> SeeResultRecord | None:
        """Devuelve el último SeeResult válido de una conversación."""
        self._required_tables()
        row = self._database.query_one(
            """
            select sr.* from """ + self._table('see_results') + """ sr
            join """ + self._table('attachments') + """ a
              on sr.attachment_id = a.attachment_id
            where sr.conversation_id = %s
              and a.household_id = %s
              and a.owner_id = %s
              and sr.status = 'success'
            order by sr.created_at desc
            limit 1
            """,
            (conversation_id, household_id, owner_id),
        )
        return self._see_result_from_row(row) if row else None

    def get_see_result_for_attachment(
        self,
        attachment_id: str,
        *,
        household_id: str,
        owner_id: str,
    ) -> SeeResultRecord | None:
        self._required_tables()
        row = self._database.query_one(
            """
            select sr.* from """ + self._table('see_results') + """ sr
            join """ + self._table('attachments') + """ a
              on sr.attachment_id = a.attachment_id
            where sr.attachment_id = %s
              and a.household_id = %s
              and a.owner_id = %s
              and sr.status = 'success'
            order by sr.created_at desc
            limit 1
            """,
            (attachment_id, household_id, owner_id),
        )
        return self._see_result_from_row(row) if row else None

    def list_see_results_by_conversation(
        self,
        conversation_id: str,
        *,
        household_id: str,
        owner_id: str,
    ) -> list[dict[str, Any]]:
        """Devuelve todos los SeeResults válidos de una conversación."""
        self._required_tables()
        rows = self._database.query(
            """
            select sr.see_result_id, sr.attachment_id, sr.task, sr.status,
                   sr.artifact_type, sr.result_json, sr.created_at
            from """ + self._table('see_results') + """ sr
            join """ + self._table('attachments') + """ a
              on sr.attachment_id = a.attachment_id
            where sr.conversation_id = %s
              and a.household_id = %s
              and a.owner_id = %s
              and sr.status = 'success'
            order by sr.created_at desc
            """,
            (conversation_id, household_id, owner_id),
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            result_json = row.get("result_json")
            if isinstance(result_json, str):
                try:
                    result_json = json.loads(result_json)
                except (TypeError, ValueError):
                    result_json = {}
            result.append(
                {
                    "see_result_id": row["see_result_id"],
                    "attachment_id": row["attachment_id"],
                    "task": row["task"],
                    "status": row["status"],
                    "artifact_type": row["artifact_type"],
                    "result": result_json,
                    "created_at": row["created_at"],
                }
            )
        return result


# Instancia compartida (singleton por proceso)
_store: AttachmentStore | None = None
_store_lock = threading.RLock()


def get_store() -> AttachmentStore:
    global _store

    with _store_lock:
        if _store is None:
            _store = AttachmentStore()

        return _store


def configure_store(
    root: str | Path | None = None,
    *,
    schema: str | None = None,
    database: Database | None = None,
) -> AttachmentStore:
    """Configure an explicit store, primarily for tests."""

    global _store

    with _store_lock:
        if _store is not None:
            # No close needed: Database manages its own connection.
            pass

        _store = AttachmentStore(root, schema=schema, database=database)
        return _store


def reset_store() -> None:
    """Forget the process store (tests only)."""

    global _store

    with _store_lock:
        _store = None


def close_store() -> None:
    """Close the process store connection (tests only).

    The underlying ``Database`` connection is shared and process-wide, so
    this is a no-op kept for compatibility with callers that expect a
    ``close`` method.
    """

    global _store

    with _store_lock:
        _store = None
