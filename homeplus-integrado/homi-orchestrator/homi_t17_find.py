"""HOMI T17 — BASE FIND: document ingestion foundation.

Modulo FIND de HOMI-D. Convierte documentos autorizados (via SEE Worker o
snapshots capturados) en HomiDocument y chunks deterministas con metadata
segura. No calcula embeddings ni retrieval: eso corresponde a T18.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import shutil
import socket
import time
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

FIND_CONTRACT_VERSION = "find-ingestion-1.0"
HOMI_DOCUMENT_VERSION = "homi-document-1.0"
PIPELINE_VERSION = "find-pipeline-1.0"
CHUNK_CONFIG_VERSION = "chunk-config-1.0"

DEFAULT_CHUNK_SIZE_TOKENS = 500
DEFAULT_CHUNK_OVERLAP_TOKENS = 80
CHARS_PER_TOKEN = 4

SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
}

VISIBILITIES = {"household", "personal", "restricted"}
SENSITIVITIES = {"normal", "sensitive", "restricted"}
SOURCE_TYPES = {"homecloud_document", "asset_document", "fixture_document"}

JOB_STATES = {"PENDING", "RUNNING", "SUCCEEDED", "FAILED", "SKIPPED"}


class FindError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "retryable": self.retryable}


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------


@dataclass
class IngestionRequest:
    contract_version: str = FIND_CONTRACT_VERSION
    event_type: str = "document.created"
    document_id: str = ""
    document_version: int = 1
    household_id: str = ""
    source_type: str = "homecloud_document"
    asset_id: Optional[str] = None
    correlation_id: str = ""
    actor_id: Optional[str] = None
    authorization: Optional[str] = None
    # Optional explicit metadata supplied by trusted source (HomePlus). These are
    # not authoritative by themselves; the provider must validate them.
    title: Optional[str] = None
    owner_id: Optional[str] = None
    visibility: Optional[str] = None
    sensitivity: Optional[str] = None
    category: Optional[str] = None
    mime_type: Optional[str] = None
    updated_at: Optional[str] = None
    permissions: Optional[Dict[str, Any]] = None

    def validate(self) -> None:
        if self.contract_version != FIND_CONTRACT_VERSION:
            raise FindError("CONTRACT_VERSION_UNSUPPORTED", f"unsupported contract_version: {self.contract_version}")
        if not self.document_id:
            raise FindError("INVALID_DOCUMENT_ID", "document_id is required")
        if not isinstance(self.document_version, int) or self.document_version < 1:
            raise FindError("INVALID_VERSION", "document_version must be a positive integer")
        if not self.household_id:
            raise FindError("MISSING_HOUSEHOLD", "household_id is required")
        if self.source_type not in SOURCE_TYPES:
            raise FindError("INVALID_SOURCE_TYPE", f"unsupported source_type: {self.source_type}")
        if not self.correlation_id:
            self.correlation_id = f"corr-{uuid.uuid4().hex[:12]}"


@dataclass
class DocumentSecurityMetadata:
    household_id: str
    owner_id: str
    visibility: str = "household"
    sensitivity: str = "normal"
    permissions: Dict[str, Any] = field(default_factory=dict)
    restrictions: List[str] = field(default_factory=list)
    category: Optional[str] = None
    asset_id: Optional[str] = None
    source_type: str = "homecloud_document"
    mime_type: str = "application/pdf"
    updated_at: Optional[str] = None

    def validate(self) -> None:
        if not self.household_id:
            raise FindError("MISSING_HOUSEHOLD", "chunk cannot be created without household_id")
        if not self.owner_id:
            raise FindError("MISSING_OWNER", "owner_id is required")
        if self.visibility not in VISIBILITIES:
            raise FindError("INVALID_VISIBILITY", f"invalid visibility: {self.visibility}")
        if self.sensitivity not in SENSITIVITIES:
            raise FindError("INVALID_SENSITIVITY", f"invalid sensitivity: {self.sensitivity}")
        if self.mime_type not in SUPPORTED_MIME_TYPES:
            raise FindError("UNSUPPORTED_MIME", f"unsupported mime_type: {self.mime_type}")


@dataclass
class HomiDocument:
    contract_version: str = HOMI_DOCUMENT_VERSION
    document_id: str = ""
    document_version: int = 1
    title: Optional[str] = None
    text: str = ""
    sections: List[Dict[str, Any]] = field(default_factory=list)
    tables: List[Dict[str, Any]] = field(default_factory=list)
    pages: Optional[int] = None
    language: Optional[str] = None
    metadata: DocumentSecurityMetadata = field(default_factory=lambda: DocumentSecurityMetadata("", ""))
    provenance: Dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""
    parser_version: str = ""
    pipeline_version: str = PIPELINE_VERSION

    def validate(self) -> None:
        if self.contract_version != HOMI_DOCUMENT_VERSION:
            raise FindError("INVALID_CONTRACT", "invalid HomiDocument contract_version")
        if not self.document_id:
            raise FindError("INVALID_DOCUMENT_ID", "HomiDocument.document_id is required")
        if not self.text or not self.text.strip():
            raise FindError("EMPTY_EXTRACTION", "HomiDocument has no extractable text")
        self.metadata.validate()
        if not self.content_hash:
            self.content_hash = sha256_text(self.text)


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    document_version: int
    chunk_index: int
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    token_estimate: int = 0
    pipeline_version: str = PIPELINE_VERSION
    chunk_config_version: str = CHUNK_CONFIG_VERSION

    def validate(self) -> None:
        if not self.chunk_id:
            raise FindError("INVALID_CHUNK_ID", "chunk_id is required")
        if not self.text or not self.text.strip():
            raise FindError("EMPTY_CHUNK", "chunk text cannot be empty")
        md = self.metadata
        for key in ("household_id", "document_id", "document_version", "owner_id",
                    "visibility", "source_type", "mime_type", "pipeline_version"):
            if md.get(key) in (None, ""):
                raise FindError("MISSING_CHUNK_METADATA", f"chunk metadata missing {key}")
        if md.get("household_id") != self.metadata.get("household_id"):
            pass


@dataclass
class JobResultRef:
    homi_document_path: Optional[str] = None
    chunks_path: Optional[str] = None
    manifest_entry_path: Optional[str] = None


@dataclass
class IngestionJob:
    job_id: str = ""
    idempotency_key: str = ""
    document_id: str = ""
    document_version: int = 1
    household_id: str = ""
    correlation_id: str = ""
    state: str = "PENDING"
    attempts: int = 0
    error: Optional[Dict[str, Any]] = None
    created_at: str = ""
    updated_at: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    result_ref: Optional[Dict[str, Any]] = None
    pipeline_version: str = PIPELINE_VERSION
    chunk_config_version: str = CHUNK_CONFIG_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Job store (local JSON persistence)
# ---------------------------------------------------------------------------


class JobStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.jobs_dir = self.root / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def save(self, job: IngestionJob) -> None:
        job.updated_at = now_iso()
        path = self._path(job.job_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(job.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def get(self, job_id: str) -> Optional[IngestionJob]:
        path = self._path(job_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return IngestionJob(**data)

    def find_by_key(self, key: str) -> Optional[IngestionJob]:
        for path in self.jobs_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("idempotency_key") == key:
                return IngestionJob(**data)
        return None

    def list_jobs(self) -> List[IngestionJob]:
        out = []
        for path in sorted(self.jobs_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                out.append(IngestionJob(**data))
            except Exception:
                continue
        return out


# ---------------------------------------------------------------------------
# SEE document adapter
# ---------------------------------------------------------------------------


def adapt_see_response_to_homi_document(
    request: IngestionRequest,
    see_response: Dict[str, Any],
    security: DocumentSecurityMetadata,
    source_kind: str = "see_worker",
) -> HomiDocument:
    if not isinstance(see_response, dict):
        raise FindError("INVALID_PARSER_RESPONSE", "SEE response must be an object")
    if see_response.get("status") != "success":
        err = see_response.get("error") or {}
        raise FindError("PARSER_FAILED", f"SEE read_document failed: {err.get('code') or err}")
    if see_response.get("task") and see_response.get("task") != "read_document":
        raise FindError("INVALID_TASK", f"unexpected task: {see_response.get('task')}")
    text = see_response.get("text")
    if not isinstance(text, str):
        raise FindError("INVALID_PARSER_RESPONSE", "SEE response text must be a string")
    text = clean_text(text)
    if not text:
        raise FindError("EMPTY_EXTRACTION", "parser produced no text")

    fields = see_response.get("fields") or {}
    sections = fields.get("sections") if isinstance(fields, dict) else None
    tables = fields.get("tables") if isinstance(fields, dict) else None
    doc_meta = fields.get("document_metadata") if isinstance(fields, dict) else None

    pages = None
    if isinstance(doc_meta, dict):
        pages = doc_meta.get("pages")
        if pages == 0:
            pages = None
    # fallback to top-level metadata
    top_meta = see_response.get("metadata") or {}
    if pages is None:
        pages = top_meta.get("page_count")

    engine = see_response.get("engine") or "unknown"
    parser_version = f"{engine}:{see_response.get('contract_version', 'see-1.0.0')}"

    title = request.title
    if title is None and isinstance(doc_meta, dict):
        title = doc_meta.get("name")

    security.mime_type = security.mime_type or (top_meta.get("artifact", {}) or {}).get("mime_type") or security.mime_type
    # mime from request if provided
    if request.mime_type:
        security.mime_type = request.mime_type

    doc = HomiDocument(
        document_id=request.document_id,
        document_version=request.document_version,
        title=title,
        text=text,
        sections=list(sections or []),
        tables=list(tables or []),
        pages=pages,
        language=None,
        metadata=security,
        provenance={
            "source_kind": source_kind,
            "parser": "see_worker",
            "engine": engine,
            "provider_id": see_response.get("provider_id"),
            "contract_version": see_response.get("contract_version"),
            "request_id": see_response.get("request_id"),
            "warnings": list(see_response.get("warnings") or []),
            "metadata": top_meta,
        },
        parser_version=parser_version,
    )
    doc.content_hash = sha256_text(doc.text)
    doc.validate()
    return doc


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _split_paragraphs(text: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _current_section_from_line(line: str) -> Optional[str]:
    m = re.match(r"^#{1,6}\s+(.+)$", line.strip())
    if m:
        return m.group(1).strip()
    return None


def chunk_homi_document(
    doc: HomiDocument,
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    overlap_tokens: int = DEFAULT_CHUNK_OVERLAP_TOKENS,
) -> List[Chunk]:
    max_chars = chunk_size_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN

    sec_meta = doc.metadata
    base_md = {
        "household_id": sec_meta.household_id,
        "document_id": doc.document_id,
        "document_version": doc.document_version,
        "owner_id": sec_meta.owner_id,
        "visibility": sec_meta.visibility,
        "sensitivity": sec_meta.sensitivity,
        "source_type": sec_meta.source_type,
        "asset_id": sec_meta.asset_id,
        "mime_type": sec_meta.mime_type,
        "category": sec_meta.category,
        "updated_at": sec_meta.updated_at,
        "permissions": sec_meta.permissions,
        "restrictions": sec_meta.restrictions,
        "pipeline_version": doc.pipeline_version,
        "chunk_config_version": CHUNK_CONFIG_VERSION,
        "parser_version": doc.parser_version,
        "content_hash": doc.content_hash,
    }

    chunks: List[Chunk] = []
    # Process tables first as their own chunks (preserve headers/rows).
    for ti, table in enumerate(doc.tables or []):
        ttext = ""
        for key in ("markdown", "html", "dataframe", "text"):
            if table.get(key):
                ttext = str(table.get(key))
                break
        if not ttext.strip():
            continue
        # table context
        section = None
        # try to find nearest section by scanning text? leave None
        md = dict(base_md)
        md["section"] = section
        md["content_type"] = "table"
        md["table_index"] = ti
        # split if too long by rows
        lines = ttext.splitlines()
        header = lines[0] if lines else ""
        body = lines[1:]
        current = header + ("\n" if header else "")
        for row in body:
            if len(current) + len(row) + 1 > max_chars and current.strip() != header.strip():
                # finalize
                _append_chunk(chunks, doc, current.strip(), md, base_md)
                current = (header + "\n" if header else "") + row + "\n"
            else:
                current += row + "\n"
        if current.strip():
            _append_chunk(chunks, doc, current.strip(), md, base_md)

    # Process main text
    paragraphs = _split_paragraphs(doc.text)
    current_section: Optional[str] = None
    # track section per paragraph
    # We'll iterate lines to update section, but paragraphs may span. Use heuristic:
    # if a paragraph is a heading, update current_section and include as context.

    buffer = ""
    buffer_section = None
    for para in paragraphs:
        # detect heading-only paragraph
        sec = _current_section_from_line(para.splitlines()[0] if para else "")
        if sec and len(para.splitlines()) == 1:
            current_section = sec
            # include heading as context in next chunks; don't create empty chunk
            continue
        # decide if adding para exceeds max
        candidate = (buffer + "\n\n" + para).strip() if buffer else para
        if len(candidate) <= max_chars:
            buffer = candidate
            if buffer_section is None:
                buffer_section = current_section
        else:
            if buffer.strip():
                md = dict(base_md)
                md["section"] = buffer_section
                md["content_type"] = "text"
                _append_chunk(chunks, doc, buffer.strip(), md, base_md)
                # overlap: seed buffer with tail of previous chunk
                tail = buffer.strip()[-overlap_chars:] if overlap_chars > 0 else ""
                buffer = (tail + "\n\n" + para).strip() if tail else para
                buffer_section = current_section
            else:
                # para itself too long: split by sentences/chars
                _split_long_paragraph(chunks, doc, para, current_section, base_md, max_chars, overlap_chars)
                buffer = ""
                buffer_section = None

    if buffer.strip():
        md = dict(base_md)
        md["section"] = buffer_section
        md["content_type"] = "text"
        _append_chunk(chunks, doc, buffer.strip(), md, base_md)

    # Renumber chunk_index sequentially and recompute ids
    for idx, ch in enumerate(chunks):
        ch.chunk_index = idx
        ch.chunk_id = make_chunk_id(doc, idx, ch.text)
        ch.metadata["chunk_index"] = idx
        ch.metadata["section"] = ch.metadata.get("section")
    # validate
    for ch in chunks:
        ch.validate()
    if not chunks:
        raise FindError("CHUNKING_FAILED", "no chunks produced")
    return chunks


def _append_chunk(chunks: List[Chunk], doc: HomiDocument, text: str, md: Dict[str, Any], base_md: Dict[str, Any]) -> None:
    text = clean_text(text)
    if not text:
        return
    idx = len(chunks)
    cid = make_chunk_id(doc, idx, text)
    ch = Chunk(
        chunk_id=cid,
        document_id=doc.document_id,
        document_version=doc.document_version,
        chunk_index=idx,
        text=text,
        metadata=dict(md),
        token_estimate=estimate_tokens(text),
    )
    # ensure metadata has chunk_index
    ch.metadata["chunk_index"] = idx
    chunks.append(ch)


def _split_long_paragraph(chunks, doc, para, section, base_md, max_chars, overlap_chars):
    # split into sentences
    sentences = re.split(r"(?<=[.!?])\s+", para)
    buffer = ""
    for sent in sentences:
        candidate = (buffer + " " + sent).strip() if buffer else sent
        if len(candidate) <= max_chars:
            buffer = candidate
        else:
            if buffer.strip():
                md = dict(base_md)
                md["section"] = section
                md["content_type"] = "text"
                _append_chunk(chunks, doc, buffer.strip(), md, base_md)
                tail = buffer.strip()[-overlap_chars:] if overlap_chars > 0 else ""
                buffer = (tail + " " + sent).strip() if tail else sent
            else:
                # hard split
                for i in range(0, len(sent), max_chars):
                    part = sent[i:i + max_chars]
                    md = dict(base_md)
                    md["section"] = section
                    md["content_type"] = "text"
                    _append_chunk(chunks, doc, part, md, base_md)
                buffer = ""
    if buffer.strip():
        md = dict(base_md)
        md["section"] = section
        md["content_type"] = "text"
        _append_chunk(chunks, doc, buffer.strip(), md, base_md)


def make_chunk_id(doc: HomiDocument, index: int, text: str) -> str:
    payload = "|".join([
        doc.metadata.household_id,
        doc.document_id,
        str(doc.document_version),
        PIPELINE_VERSION,
        CHUNK_CONFIG_VERSION,
        str(index),
        sha256_text(text)[:16],
    ])
    return "chunk-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


class DocumentProvider:
    """Interface for authorized document content providers."""

    def fetch(self, request: IngestionRequest) -> Tuple[Dict[str, Any], DocumentSecurityMetadata, str]:
        """Return (see_response, security_metadata, source_kind)."""
        raise NotImplementedError


class LiveSeeDocumentProvider(DocumentProvider):
    """Fetch a fresh ``read_document`` result from an authorized SEE Worker.

    ``access_ref`` values remain opaque.  The provider never accepts a local
    filesystem path or URL as a document reference; callers supply an explicit
    document-id-to-access-ref mapping (or opt into using the document id as the
    opaque reference).  The bearer token is kept in memory and is never added
    to persisted provenance or error messages.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        access_refs: Optional[Dict[str, str]] = None,
        timeout_s: float = 330.0,
    ):
        if not base_url.startswith(("http://", "https://")):
            raise FindError("INVALID_SEE_URL", "SEE base_url must be HTTP(S)")
        if not token:
            raise FindError("MISSING_SEE_TOKEN", "SEE internal token is required")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.access_refs = dict(access_refs or {})
        self.timeout_s = timeout_s

    @staticmethod
    def _opaque_ref(value: str) -> str:
        if not value or value != value.strip():
            raise FindError("INVALID_ACCESS_REF", "SEE access_ref must be a non-empty opaque reference")
        if "://" in value or any(part in value for part in ("/", "\\", ":", "..")):
            raise FindError("INVALID_ACCESS_REF", "SEE access_ref must be opaque, not a path or URL")
        return value

    def fetch(self, request: IngestionRequest) -> Tuple[Dict[str, Any], DocumentSecurityMetadata, str]:
        access_ref = self._opaque_ref(self.access_refs.get(request.document_id, request.document_id))
        request_id = f"see-{request.correlation_id or uuid.uuid4().hex[:12]}-{uuid.uuid4().hex[:8]}"
        artifact: Dict[str, Any] = {"id": request.document_id, "access_ref": access_ref}
        if request.mime_type:
            artifact["mime_type"] = request.mime_type
        payload = {
            "contract_version": "see-1.0.0",
            "request_id": request_id[:128],
            "artifact": artifact,
            "task": "read_document",
            "hints": {},
        }
        http_request = urllib.request.Request(
            f"{self.base_url}/v1/see",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout_s) as response:
                raw = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            try:
                error_payload = json.loads(exc.read().decode("utf-8", "replace"))
                code = (error_payload.get("error") or {}).get("code") or f"HTTP_{exc.code}"
            except Exception:
                code = f"HTTP_{exc.code}"
            raise FindError("PARSER_FAILED", f"SEE read_document failed: {code}", retryable=exc.code >= 500) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", None)
            timed_out = isinstance(exc, (TimeoutError, socket.timeout)) or isinstance(reason, (TimeoutError, socket.timeout))
            code = "PARSER_TIMEOUT" if timed_out else "PARSER_UNAVAILABLE"
            detail = type(reason or exc).__name__
            raise FindError(code, f"SEE read_document unavailable: {detail}", retryable=True) from exc

        try:
            see = json.loads(raw)
        except ValueError as exc:
            raise FindError("INVALID_PARSER_RESPONSE", "SEE response was not valid JSON") from exc
        if not isinstance(see, dict):
            raise FindError("INVALID_PARSER_RESPONSE", "SEE response must be an object")
        if see.get("request_id") != payload["request_id"]:
            raise FindError("INVALID_PARSER_RESPONSE", "SEE response request_id mismatch")

        top_meta = see.get("metadata") or {}
        artifact_meta = top_meta.get("artifact") or {}
        security = DocumentSecurityMetadata(
            household_id=request.household_id,
            owner_id=request.owner_id or request.actor_id or "owner-unknown",
            visibility=request.visibility or "household",
            sensitivity=request.sensitivity or "normal",
            permissions=request.permissions or {},
            restrictions=[],
            category=request.category,
            asset_id=request.asset_id,
            source_type=request.source_type,
            mime_type=request.mime_type or artifact_meta.get("mime_type") or "application/pdf",
            updated_at=request.updated_at,
        )
        security.validate()
        return see, security, "see_worker_live"


class SnapshotDocumentProvider(DocumentProvider):
    """Uses captured SEE responses from t15_2 as verifiable snapshots."""

    def __init__(self, snapshot_map: Dict[str, str]):
        # fixture_key -> path to captured JSON (with http_status/response)
        self.snapshot_map = snapshot_map

    def fetch(self, request: IngestionRequest) -> Tuple[Dict[str, Any], DocumentSecurityMetadata, str]:
        key = request.document_id  # document_id doubles as fixture key in controlled mode
        # allow explicit fixture key via correlation? We'll support map lookup by document_id first
        path = self.snapshot_map.get(key)
        if path is None:
            # try by source asset
            raise FindError("DOCUMENT_NOT_FOUND", f"no snapshot for document_id={key}")
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "response" in raw:
            see = raw["response"]
        else:
            see = raw
        # security metadata from request/trusted fields (controlled fixture)
        security = DocumentSecurityMetadata(
            household_id=request.household_id,
            owner_id=request.owner_id or request.actor_id or "owner-unknown",
            visibility=request.visibility or "household",
            sensitivity=request.sensitivity or "normal",
            permissions=request.permissions or {},
            restrictions=[],
            category=request.category,
            asset_id=request.asset_id,
            source_type=request.source_type,
            mime_type=request.mime_type or (see.get("metadata", {}).get("artifact", {}) or {}).get("mime_type") or "application/pdf",
            updated_at=request.updated_at,
        )
        try:
            security.validate()
        except FindError:
            # mime may be inferred from see response metadata
            pass
        # infer mime if missing
        if not security.mime_type:
            security.mime_type = "application/pdf"
        security.validate()
        return see, security, "fixture_snapshot"


class ControlledFixtureProvider(DocumentProvider):
    """Provider for controlled fixtures where text is supplied directly.

    Used for adversarial/edge tests. The payload is treated as a SEE response.
    """

    def __init__(self, fixtures: Dict[str, Dict[str, Any]]):
        self.fixtures = fixtures

    def fetch(self, request: IngestionRequest) -> Tuple[Dict[str, Any], DocumentSecurityMetadata, str]:
        fix = self.fixtures.get(request.document_id)
        if not fix:
            raise FindError("DOCUMENT_NOT_FOUND", f"fixture not found: {request.document_id}")
        see = fix["see_response"]
        meta = fix.get("security", {})
        security = DocumentSecurityMetadata(
            household_id=request.household_id,
            owner_id=meta.get("owner_id", request.owner_id or request.actor_id or "owner-unknown"),
            visibility=meta.get("visibility", request.visibility or "household"),
            sensitivity=meta.get("sensitivity", request.sensitivity or "normal"),
            permissions=meta.get("permissions", request.permissions or {}),
            restrictions=meta.get("restrictions", []),
            category=meta.get("category", request.category),
            asset_id=request.asset_id or meta.get("asset_id"),
            source_type=request.source_type,
            mime_type=meta.get("mime_type", request.mime_type or "text/plain"),
            updated_at=meta.get("updated_at", request.updated_at),
        )
        security.validate()
        return see, security, "controlled_fixture"


# ---------------------------------------------------------------------------
# Ingestion orchestrator
# ---------------------------------------------------------------------------


def run_ingestion(
    request: IngestionRequest,
    provider: DocumentProvider,
    store: JobStore,
    artifacts_dir: str | Path,
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    overlap_tokens: int = DEFAULT_CHUNK_OVERLAP_TOKENS,
) -> IngestionJob:
    request.validate()
    artifacts_dir = Path(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # idempotency key (content hash unknown yet -> based on identity+pipeline)
    idem_key = sha256_text("|".join([
        request.household_id,
        request.document_id,
        str(request.document_version),
        PIPELINE_VERSION,
        CHUNK_CONFIG_VERSION,
        request.source_type,
    ]))

    existing = store.find_by_key(idem_key)
    if existing and existing.state == "SUCCEEDED":
        # verify result files exist; if so reuse
        if existing.result_ref and existing.result_ref.get("chunks_path"):
            cp = Path(existing.result_ref["chunks_path"])
            if cp.exists():
                return existing

    job_id = existing.job_id if existing else f"job-{uuid.uuid4().hex[:12]}"
    job = existing if existing else IngestionJob(
        job_id=job_id,
        idempotency_key=idem_key,
        document_id=request.document_id,
        document_version=request.document_version,
        household_id=request.household_id,
        correlation_id=request.correlation_id,
        state="PENDING",
        created_at=now_iso(),
    )
    job.state = "RUNNING"
    job.started_at = now_iso()
    job.attempts = (job.attempts or 0) + 1
    store.save(job)

    try:
        see, security, source_kind = provider.fetch(request)
        # mime validation
        if security.mime_type not in SUPPORTED_MIME_TYPES:
            raise FindError("UNSUPPORTED_MIME", f"unsupported mime_type: {security.mime_type}")
        doc = adapt_see_response_to_homi_document(request, see, security, source_kind=source_kind)
        chunks = chunk_homi_document(doc, chunk_size_tokens, overlap_tokens)

        # persist artifacts
        job_dir = artifacts_dir / request.household_id / request.document_id / f"v{request.document_version}"
        job_dir.mkdir(parents=True, exist_ok=True)
        doc_path = job_dir / "homi_document.json"
        chunks_path = job_dir / "chunks.json"
        doc_path.write_text(json.dumps(dataclasses.asdict(doc), ensure_ascii=False, indent=2), encoding="utf-8")
        # asdict on dataclass with nested dataclass works
        chunks_payload = [dataclasses.asdict(c) for c in chunks]
        chunks_path.write_text(json.dumps(chunks_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        job.state = "SUCCEEDED"
        job.finished_at = now_iso()
        job.result_ref = {
            "homi_document_path": str(doc_path),
            "chunks_path": str(chunks_path),
            "chunk_count": len(chunks),
            "content_hash": doc.content_hash,
        }
        store.save(job)
        return job
    except Exception as e:
        if isinstance(e, FindError):
            err = e.to_dict()
        else:
            err = {"code": "UNEXPECTED_ERROR", "message": str(e), "retryable": False}
        job.state = "FAILED"
        job.finished_at = now_iso()
        job.error = err
        store.save(job)
        raise FindError(err["code"], err["message"], err.get("retryable", False))


# need fix asdict for nested DocumentSecurityMetadata etc (dataclasses.asdict works)
# and Chunk validate missing content? ok
