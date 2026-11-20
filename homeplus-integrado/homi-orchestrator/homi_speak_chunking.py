"""T29 — Chunking lingüístico para SPEAK (HOMI-D side).

Fragmenta texto normalizado (T28) en unidades prosódicas completas
(oraciones/cláusulas), preservando números, montos, fechas, abreviaturas,
nombres propios y signos de puntuación.

No corta arbitrariamente por caracteres o tokens.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Chunk:
    chunk_id: str
    index: int
    text: str
    profile: str = "neutral"
    is_final: bool = False


# Abreviaturas comunes es-AR que no deben romper oración
_ABBREVS = {
    "sr", "sra", "dr", "dra", "prof", "ing", "lic", "av", "av.", "etc",
    " aprox", "vs", "nro", "tel", "cel", "pje",
}


def _split_sentences(text: str) -> List[str]:
    """Divide en oraciones respetando abreviaturas y puntuación."""
    text = (text or "").strip()
    if not text:
        return []
    # Normalizar espacios
    text = re.sub(r"\s+", " ", text)
    # Marcadores de fin de oración: . ! ? seguidos de espacio+mayúscula o fin
    # Proteger abreviaturas simples reemplazando punto temporal
    protected = text
    for ab in _ABBREVS:
        # reemplazar "ab." por "ab§"
        protected = re.sub(r"(?i)\b" + re.escape(ab.rstrip(".")) + r"\.", lambda m: m.group(0).replace(".", "§"), protected)

    # Dividir por . ! ? seguidos de espacio o fin
    parts = re.split(r"(?<=[.!?])\s+", protected)
    # Restaurar
    parts = [p.replace("§", ".") for p in parts]
    # Reagrupar fragmentos muy cortos (< 3 palabras) con el siguiente
    merged: List[str] = []
    buf = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if buf:
            buf = buf + " " + p
        else:
            buf = p
        # si buf tiene al menos una oración completa y termina en puntuación, flush
        if re.search(r"[.!?]$", buf.strip()) and len(buf.split()) >= 4:
            merged.append(buf.strip())
            buf = ""
    if buf.strip():
        merged.append(buf.strip())
    return merged


def chunk_text(text: str, *, profile: str = "neutral", base_id: str = "chunk") -> List[Chunk]:
    sentences = _split_sentences(text)
    if not sentences:
        return []
    chunks: List[Chunk] = []
    for i, s in enumerate(sentences):
        chunks.append(Chunk(
            chunk_id=f"{base_id}_{i+1:03d}",
            index=i,
            text=s,
            profile=profile,
            is_final=(i == len(sentences) - 1),
        ))
    return chunks


def chunks_to_payload(chunks: List[Chunk]) -> list[dict]:
    return [
        {"chunk_id": c.chunk_id, "index": c.index, "text": c.text,
         "profile": c.profile, "is_final": c.is_final}
        for c in chunks
    ]


def verify_no_loss(original: str, chunks: List[Chunk]) -> bool:
    """Verifica que la concatenación de chunks contiene todo el texto original (normalizado)."""
    joined = " ".join(c.text for c in chunks)
    norm_orig = re.sub(r"\s+", " ", (original or "").strip())
    norm_joined = re.sub(r"\s+", " ", joined.strip())
    return norm_orig == norm_joined