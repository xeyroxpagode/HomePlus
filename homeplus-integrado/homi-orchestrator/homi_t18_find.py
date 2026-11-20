"""HOMI T18 — FIND REAL: hybrid retrieval (BGE-M3 + pgvector + PostgreSQL FTS + RRF)."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from homi_t17_find import FindError, Chunk, HomiDocument

FIND_RETRIEVAL_CONTRACT = "find-retrieval-1.0"
EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIM = 1024
EMBEDDING_VERSION = "bge-m3-dense-1.0"
RRF_K = 60

DB_HOST = os.getenv("FIND_DB_HOST", "localhost")
DB_PORT = int(os.getenv("FIND_DB_PORT", "55322") if False else os.getenv("FIND_DB_PORT", "54322"))
DB_NAME = os.getenv("FIND_DB_NAME", "postgres")
DB_USER = os.getenv("FIND_DB_USER", "postgres")
DB_PASSWORD = os.getenv("FIND_DB_PASSWORD", "postgres")


class RetrievalError(FindError):
    pass


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# Access context
# ---------------------------------------------------------------------------


@dataclass
class AccessContext:
    household_id: str
    actor_id: str
    owner_id: Optional[str] = None

    def validate(self) -> None:
        if not self.household_id:
            raise RetrievalError("MISSING_HOUSEHOLD", "household_id is required")
        if not self.actor_id:
            raise RetrievalError("MISSING_ACTOR", "actor_id is required")


# ---------------------------------------------------------------------------
# Result contracts
# ---------------------------------------------------------------------------


@dataclass
class RetrievalItem:
    request_id: str
    status: str = "ok"
    document_id: str = ""
    document_version: int = 0
    chunk_id: str = ""
    asset_id: Optional[str] = None
    title: Optional[str] = None
    snippet: str = ""
    source_type: str = ""
    section: Optional[str] = None
    chunk_index: int = 0
    score: float = 0.0
    rank: int = 0
    engine_metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


@dataclass
class RetrievalResult:
    request_id: str
    status: str
    query: str
    household_id: str
    items: List[RetrievalItem] = field(default_factory=list)
    dense_count: int = 0
    fts_count: int = 0
    fused_count: int = 0
    latency_ms: float = 0.0
    warnings: List[str] = field(default_factory=list)
    error: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "status": self.status,
            "query": self.query,
            "household_id": self.household_id,
            "items": [asdict(i) for i in self.items],
            "dense_count": self.dense_count,
            "fts_count": self.fts_count,
            "fused_count": self.fused_count,
            "latency_ms": self.latency_ms,
            "warnings": self.warnings,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Embedding provider
# ---------------------------------------------------------------------------


class BGEEmbeddingProvider:
    def __init__(self, model_name: str = EMBEDDING_MODEL, device: Optional[str] = None, normalize: bool = True):
        self.model_name = model_name
        self.device = device
        self.normalize = normalize
        self._model = None
        self.load_time_ms: Optional[float] = None

    def _load(self):
        if self._model is not None:
            return
        t0 = time.time()
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as e:
            raise RetrievalError("EMBEDDING_PROVIDER_UNAVAILABLE", f"sentence_transformers not available: {e}", retryable=False)
        try:
            self._model = SentenceTransformer(self.model_name, device=self.device)
        except Exception as e:
            raise RetrievalError("EMBEDDING_MODEL_LOAD_FAILED", f"failed to load {self.model_name}: {e}", retryable=False)
        self.load_time_ms = (time.time() - t0) * 1000.0

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        self._load()
        if not texts:
            return []
        try:
            arr = self._model.encode(list(texts), normalize_embeddings=self.normalize, convert_to_numpy=True)
        except Exception as e:
            raise RetrievalError("EMBEDDING_FAILED", f"embedding failed: {e}", retryable=True)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        out = []
        for row in arr:
            v = [float(x) for x in row]
            if len(v) != EMBEDDING_DIM:
                raise RetrievalError("EMBEDDING_DIM_MISMATCH", f"expected {EMBEDDING_DIM}, got {len(v)}")
            out.append(v)
        return out

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]

    def metadata(self) -> Dict[str, Any]:
        self._load()
        import sentence_transformers
        return {
            "model": self.model_name,
            "version": EMBEDDING_VERSION,
            "dim": EMBEDDING_DIM,
            "normalize": self.normalize,
            "device": str(self._model.device) if hasattr(self._model, "device") else (self.device or "cpu"),
            "load_time_ms": self.load_time_ms,
            "sentence_transformers": sentence_transformers.__version__,
        }


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def get_conn():
    import psycopg
    try:
        return psycopg.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            connect_timeout=10,
        )
    except Exception as e:
        raise RetrievalError("DB_UNAVAILABLE", f"postgres connection failed: {e}", retryable=True)


def _row_to_item(row, request_id, engine_meta) -> RetrievalItem:
    return RetrievalItem(
        request_id=request_id,
        status="ok",
        document_id=row["document_id"],
        document_version=row["document_version"],
        chunk_id=row["chunk_id"],
        asset_id=row["asset_id"],
        title=row["title"],
        snippet=(row["text"] or "")[:400],
        source_type=row["source_type"],
        section=row["section"],
        chunk_index=row["chunk_index"],
        score=float(row.get("score", 0.0)),
        rank=int(row.get("rank", 0)),
        engine_metadata=dict(engine_meta),
    )


# ---------------------------------------------------------------------------
# Access predicate
# ---------------------------------------------------------------------------


def can_access(row: Dict[str, Any], ctx: AccessContext) -> bool:
    if row.get("household_id") != ctx.household_id:
        return False
    if not row.get("active", True):
        return False
    vis = row.get("visibility")
    if vis == "household":
        return True
    if vis == "personal":
        return row.get("owner_id") == (ctx.owner_id or ctx.actor_id)
    if vis == "restricted":
        perms = row.get("permissions") or {}
        if not isinstance(perms, dict):
            return False
        # allow if actor explicitly in allow list or permissions has actor true
        if perms.get(ctx.actor_id) is True:
            return True
        allowed = perms.get("allowed_actors") or perms.get("granted") or []
        if isinstance(allowed, list) and ctx.actor_id in allowed:
            return True
        if perms.get("household") is True and ctx.household_id == row.get("household_id"):
            return True
        return False
    return False


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------


CRITICAL_META = ["household_id", "document_id", "document_version", "owner_id", "visibility", "source_type", "mime_type", "pipeline_version"]


def _validate_chunk_meta(chunk: dict) -> List[str]:
    md = chunk.get("metadata") or {}
    missing = []
    for k in CRITICAL_META:
        if md.get(k) in (None, ""):
            missing.append(k)
    if md.get("visibility") not in ("household", "personal", "restricted"):
        missing.append("visibility(invalid)")
    if md.get("household_id") is None:
        missing.append("household_id")
    return missing


def index_chunks(chunks: List[dict], provider: BGEEmbeddingProvider, title: Optional[str] = None) -> Dict[str, Any]:
    # compute embeddings
    texts = [c.get("text", "") for c in chunks]
    embeddings = provider.embed(texts)
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                for c, emb in zip(chunks, embeddings):
                    md = c.get("metadata") or {}
                    missing = _validate_chunk_meta(c)
                    if missing:
                        # do not publish
                        continue
                    sql = """
                    INSERT INTO find.find_chunks (
                        chunk_id, household_id, document_id, document_version, owner_id, visibility,
                        sensitivity, source_type, asset_id, mime_type, section, chunk_index, text,
                        token_estimate, content_hash, pipeline_version, chunk_config_version, parser_version,
                        title, permissions, restrictions, category, updated_at, embedding,
                        active, embedding_model, embedding_version
                    ) VALUES (
                        %(chunk_id)s, %(household_id)s, %(document_id)s, %(document_version)s, %(owner_id)s, %(visibility)s,
                        %(sensitivity)s, %(source_type)s, %(asset_id)s, %(mime_type)s, %(section)s, %(chunk_index)s, %(text)s,
                        %(token_estimate)s, %(content_hash)s, %(pipeline_version)s, %(chunk_config_version)s, %(parser_version)s,
                        %(title)s, %(permissions)s, %(restrictions)s, %(category)s, %(updated_at)s, %(embedding)s::vector,
                        TRUE, %(embedding_model)s, %(embedding_version)s
                    )
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        household_id=EXCLUDED.household_id,
                        document_id=EXCLUDED.document_id,
                        document_version=EXCLUDED.document_version,
                        owner_id=EXCLUDED.owner_id,
                        visibility=EXCLUDED.visibility,
                        sensitivity=EXCLUDED.sensitivity,
                        source_type=EXCLUDED.source_type,
                        asset_id=EXCLUDED.asset_id,
                        mime_type=EXCLUDED.mime_type,
                        section=EXCLUDED.section,
                        chunk_index=EXCLUDED.chunk_index,
                        text=EXCLUDED.text,
                        token_estimate=EXCLUDED.token_estimate,
                        content_hash=EXCLUDED.content_hash,
                        pipeline_version=EXCLUDED.pipeline_version,
                        chunk_config_version=EXCLUDED.chunk_config_version,
                        parser_version=EXCLUDED.parser_version,
                        title=EXCLUDED.title,
                        permissions=EXCLUDED.permissions,
                        restrictions=EXCLUDED.restrictions,
                        category=EXCLUDED.category,
                        updated_at=EXCLUDED.updated_at,
                        embedding=EXCLUDED.embedding,
                        active=TRUE,
                        embedding_model=EXCLUDED.embedding_model,
                        embedding_version=EXCLUDED.embedding_version,
                        updated_indexed_at=now()
                    """
                    import json as _json
                    params = {
                        "chunk_id": c["chunk_id"],
                        "household_id": md["household_id"],
                        "document_id": md["document_id"],
                        "document_version": md["document_version"],
                        "owner_id": md["owner_id"],
                        "visibility": md["visibility"],
                        "sensitivity": md.get("sensitivity", "normal"),
                        "source_type": md["source_type"],
                        "asset_id": md.get("asset_id"),
                        "mime_type": md["mime_type"],
                        "section": md.get("section"),
                        "chunk_index": md.get("chunk_index", c.get("chunk_index", 0)),
                        "text": c["text"],
                        "token_estimate": c.get("token_estimate", 0),
                        "content_hash": md.get("content_hash", ""),
                        "pipeline_version": md.get("pipeline_version", "find-pipeline-1.0"),
                        "chunk_config_version": md.get("chunk_config_version", "chunk-config-1.0"),
                        "parser_version": md.get("parser_version"),
                        "title": title if title is not None else md.get("title"),
                        "permissions": _json.dumps(md.get("permissions") or {}),
                        "restrictions": _json.dumps(md.get("restrictions") or []),
                        "category": md.get("category"),
                        "updated_at": md.get("updated_at"),
                        "embedding": emb,
                        "embedding_model": EMBEDDING_MODEL,
                        "embedding_version": EMBEDDING_VERSION,
                    }
                    cur.execute(sql, params)
        return {"indexed": len(chunks)}
    finally:
        conn.close()


def index_from_chunks_file(path: str | Path, provider: BGEEmbeddingProvider, title: Optional[str] = None) -> Dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RetrievalError("INVALID_CHUNKS_FILE", "chunks file must be a list")
    return index_chunks(data, provider, title=title)


def deactivate_old_versions(household_id: str, document_id: str, keep_version: int) -> int:
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE find.find_chunks SET active=FALSE, updated_indexed_at=now() WHERE household_id=%s AND document_id=%s AND document_version < %s AND active=TRUE",
                    (household_id, document_id, keep_version),
                )
                return cur.rowcount
    finally:
        conn.close()


def delete_document(household_id: str, document_id: str, document_version: Optional[int] = None) -> int:
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                if document_version is None:
                    cur.execute(
                        "UPDATE find.find_chunks SET active=FALSE, updated_indexed_at=now() WHERE household_id=%s AND document_id=%s",
                        (household_id, document_id),
                    )
                else:
                    cur.execute(
                        "UPDATE find.find_chunks SET active=FALSE, updated_indexed_at=now() WHERE household_id=%s AND document_id=%s AND document_version=%s",
                        (household_id, document_id, document_version),
                    )
                return cur.rowcount
    finally:
        conn.close()


def update_document_metadata(household_id: str, document_id: str, document_version: int, fields: Dict[str, Any]) -> int:
    # update metadata columns without touching embedding
    allowed = {
        "title": "title",
        "owner_id": "owner_id",
        "visibility": "visibility",
        "sensitivity": "sensitivity",
        "permissions": "permissions",
        "restrictions": "restrictions",
        "asset_id": "asset_id",
        "category": "category",
    }
    sets = []
    params: Dict[str, Any] = {"household_id": household_id, "document_id": document_id, "document_version": document_version}
    import json as _json
    for k, col in allowed.items():
        if k in fields:
            sets.append(f"{col} = %({k})s")
            val = fields[k]
            if k in ("permissions", "restrictions"):
                params[k] = _json.dumps(val)
            else:
                params[k] = val
    if not sets:
        return 0
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE find.find_chunks SET {', '.join(sets)}, updated_indexed_at=now() WHERE household_id=%(household_id)s AND document_id=%(document_id)s AND document_version=%(document_version)s",
                    params,
                )
                return cur.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def _dense_search(ctx: AccessContext, query_emb: List[float], top_k: int, request_id: str) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        with conn:
            with conn.cursor(row_factory=_dict_row) as cur:
                cur.execute(
                    """
                    SELECT chunk_id, document_id, document_version, owner_id, visibility, source_type,
                           asset_id, title, text, section, chunk_index, permissions, household_id, active
                    FROM find.find_chunks
                    WHERE household_id = %s AND active = TRUE
                      AND (
                        visibility = 'household'
                        OR (visibility = 'personal' AND owner_id = %s)
                        OR (visibility = 'restricted' AND (permissions ? %s OR permissions->'allowed_actors' ? %s))
                      )
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (ctx.household_id, ctx.owner_id or ctx.actor_id, ctx.actor_id, ctx.actor_id, query_emb, top_k),
                )
                rows = cur.fetchall()
        out = []
        for r in rows:
            if not can_access(r, ctx):
                continue
            r = dict(r)
            r["score"] = 0.0
            out.append(r)
        # assign dense ranks
        for i, r in enumerate(out, start=1):
            r["_dense_rank"] = i
        return out
    finally:
        conn.close()


def _fts_search(ctx: AccessContext, query: str, top_k: int) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        with conn:
            with conn.cursor(row_factory=_dict_row) as cur:
                cur.execute(
                    """
                    SELECT chunk_id, document_id, document_version, owner_id, visibility, source_type,
                           asset_id, title, text, section, chunk_index, permissions, household_id, active,
                           ts_rank_cd(tsv, plainto_tsquery('simple', %s)) AS fts_rank
                    FROM find.find_chunks
                    WHERE household_id = %s AND active = TRUE
                      AND tsv @@ plainto_tsquery('simple', %s)
                      AND (
                        visibility = 'household'
                        OR (visibility = 'personal' AND owner_id = %s)
                        OR (visibility = 'restricted' AND (permissions ? %s OR permissions->'allowed_actors' ? %s))
                      )
                    ORDER BY fts_rank DESC, chunk_id ASC
                    LIMIT %s
                    """,
                    (query, ctx.household_id, query, ctx.owner_id or ctx.actor_id, ctx.actor_id, ctx.actor_id, top_k),
                )
                rows = cur.fetchall()
        out = []
        for r in rows:
            if not can_access(r, ctx):
                continue
            r = dict(r)
            r["_fts_rank"] = None
            out.append(r)
        for i, r in enumerate(out, start=1):
            r["_fts_rank"] = i
        return out
    finally:
        conn.close()


def _dict_row(cursor):
    # psycopg row factory
    from psycopg.rows import dict_row
    return dict_row(cursor)


# monkey: set row_factory properly by importing
from psycopg.rows import dict_row as _psycopg_dict_row


def _ensure_row_factory(func):
    return func


# fix _dense/_fts to use dict_row: redefine wrappers below by patching? Instead modify functions? We'll just call with row_factory=dict_row via cursor factory.
# The above functions reference _dict_row which we define as returning dict_row. But we called _dict_row(cursor) incorrectly. Let's instead patch by replacing calls.


def retrieve(
    query: str,
    ctx: AccessContext,
    provider: BGEEmbeddingProvider,
    top_k: int = 10,
    dense_k: int = 20,
    fts_k: int = 20,
    request_id: Optional[str] = None,
) -> RetrievalResult:
    rid = request_id or f"req-{uuid.uuid4().hex[:12]}"
    t0 = time.time()
    ctx.validate()
    warnings: List[str] = []
    if not query or not query.strip():
        return RetrievalResult(
            request_id=rid, status="invalid_query", query=query, household_id=ctx.household_id,
            latency_ms=(time.time() - t0) * 1000.0, warnings=["empty query"],
        )
    if top_k < 1 or top_k > 100:
        return RetrievalResult(
            request_id=rid, status="invalid_top_k", query=query, household_id=ctx.household_id,
            latency_ms=(time.time() - t0) * 1000.0, warnings=["top_k must be 1..100"],
        )

    # dense
    dense_results: List[Dict[str, Any]] = []
    fts_results: List[Dict[str, Any]] = []
    dense_error = None
    fts_error = None
    try:
        qemb = provider.embed_one(query.strip())
        dense_results = _dense_search_fixed(ctx, qemb, dense_k, rid)
    except Exception as e:
        dense_error = str(e)
        warnings.append(f"dense unavailable: {dense_error}")
    try:
        fts_results = _fts_search_fixed(ctx, query.strip(), fts_k)
    except Exception as e:
        fts_error = str(e)
        warnings.append(f"fts unavailable: {fts_error}")

    # RRF fusion
    fused = _rrf_fuse(dense_results, fts_results, top_k)

    items: List[RetrievalItem] = []
    for rank, r in enumerate(fused, start=1):
        item = RetrievalItem(
            request_id=rid,
            status="ok",
            document_id=r["document_id"],
            document_version=r["document_version"],
            chunk_id=r["chunk_id"],
            asset_id=r.get("asset_id"),
            title=r.get("title"),
            snippet=(r.get("text") or "")[:400],
            source_type=r.get("source_type", ""),
            section=r.get("section"),
            chunk_index=r.get("chunk_index", 0),
            score=float(r.get("rrf_score", 0.0)),
            rank=rank,
            engine_metadata={
                "dense_rank": r.get("_dense_rank"),
                "fts_rank": r.get("_fts_rank"),
                "fusion": "rrf",
                "k": RRF_K,
            },
            warnings=[],
        )
        items.append(item)

    status = "ok"
    if dense_error and fts_error:
        status = "error"
    elif dense_error or fts_error:
        status = "partial"

    return RetrievalResult(
        request_id=rid,
        status=status,
        query=query,
        household_id=ctx.household_id,
        items=items,
        dense_count=len(dense_results),
        fts_count=len(fts_results),
        fused_count=len(items),
        latency_ms=(time.time() - t0) * 1000.0,
        warnings=warnings,
    )


def _dense_search_fixed(ctx, query_emb, top_k, rid):
    conn = get_conn()
    try:
        with conn:
            with conn.cursor(row_factory=_psycopg_dict_row) as cur:
                cur.execute(
                    """
                    SELECT chunk_id, document_id, document_version, owner_id, visibility, source_type,
                           asset_id, title, text, section, chunk_index, permissions, household_id, active
                    FROM find.find_chunks
                    WHERE household_id = %s AND active = TRUE
                      AND (
                        visibility = 'household'
                        OR (visibility = 'personal' AND owner_id = %s)
                        OR (visibility = 'restricted' AND (permissions ? %s OR permissions->'allowed_actors' ? %s))
                      )
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (ctx.household_id, ctx.owner_id or ctx.actor_id, ctx.actor_id, ctx.actor_id, query_emb, top_k),
                )
                rows = cur.fetchall()
        out = []
        for r in rows:
            rd = dict(r)
            if not can_access(rd, ctx):
                continue
            rd["_dense_rank"] = None
            out.append(rd)
        for i, r in enumerate(out, start=1):
            r["_dense_rank"] = i
        return out
    finally:
        conn.close()


def _fts_search_fixed(ctx, query, top_k):
    conn = get_conn()
    try:
        with conn:
            with conn.cursor(row_factory=_psycopg_dict_row) as cur:
                cur.execute(
                    """
                    SELECT chunk_id, document_id, document_version, owner_id, visibility, source_type,
                           asset_id, title, text, section, chunk_index, permissions, household_id, active
                    FROM find.find_chunks
                    WHERE household_id = %s AND active = TRUE
                      AND tsv @@ plainto_tsquery('simple', %s)
                      AND (
                        visibility = 'household'
                        OR (visibility = 'personal' AND owner_id = %s)
                        OR (visibility = 'restricted' AND (permissions ? %s OR permissions->'allowed_actors' ? %s))
                      )
                    ORDER BY ts_rank_cd(tsv, plainto_tsquery('simple', %s)) DESC, chunk_id ASC
                    LIMIT %s
                    """,
                    (ctx.household_id, query, ctx.owner_id or ctx.actor_id, ctx.actor_id, ctx.actor_id, query, top_k),
                )
                rows = cur.fetchall()
        out = []
        for r in rows:
            rd = dict(r)
            if not can_access(rd, ctx):
                continue
            rd["_fts_rank"] = None
            out.append(rd)
        for i, r in enumerate(out, start=1):
            r["_fts_rank"] = i
        return out
    finally:
        conn.close()


def _rrf_fuse(dense_results, fts_results, top_k):
    scores: Dict[str, float] = {}
    rows: Dict[str, Dict[str, Any]] = {}
    for r in dense_results:
        cid = r["chunk_id"]
        rank = r.get("_dense_rank") or 9999
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
        rows[cid] = r
        rows[cid]["_dense_rank"] = rank
    for r in fts_results:
        cid = r["chunk_id"]
        rank = r.get("_fts_rank") or 9999
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
        if cid not in rows:
            rows[cid] = r
        rows[cid]["_fts_rank"] = rank
    # attach scores
    for cid, r in rows.items():
        r["rrf_score"] = scores[cid]
    # sort deterministic: score desc, then chunk_id asc
    ordered = sorted(rows.values(), key=lambda x: (-x["rrf_score"], x["chunk_id"]))
    return ordered[:top_k]


# Backwards compat aliases
_dense_search = _dense_search_fixed
_fts_search = _fts_search_fixed
