"""HOMI T14 Corrective 02 - Authorized HomePlus READ adapter."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import httpx


def _base_url(base_url: Optional[str] = None) -> str:
    if base_url:
        return str(base_url).rstrip("/")
    return (os.getenv("HOMI_TOOL_BASE_URL") or "http://127.0.0.1:3001").rstrip("/")


def _headers(authorization: Optional[str]) -> dict:
    headers = {"Accept": "application/json"}
    if authorization:
        headers["Authorization"] = authorization if authorization.lower().startswith("bearer ") else f"Bearer {authorization}"
    return headers


def _extract_list(payload: Any, *keys: str) -> List[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in keys:
            val = payload.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
        # common wrappers
        for key in ("data", "result", "items"):
            val = payload.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
            if isinstance(val, dict):
                nested = _extract_list(val, *keys)
                if nested:
                    return nested
    return []


def read_members(*, actor_id, household_id, authorization, base_url=None, timeout=10.0) -> Tuple[List[dict], Optional[str], bool]:
    if not household_id:
        return [], "UNAUTHORIZED", False
    url = f"{_base_url(base_url)}/api/households/{household_id}/members"
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers=_headers(authorization))
    except httpx.TimeoutException:
        return [], "UNAVAILABLE", False
    except httpx.TransportError:
        return [], "UNAVAILABLE", False
    except Exception:
        return [], "UNAVAILABLE", False
    if resp.status_code == 401:
        return [], "UNAUTHORIZED", False
    if resp.status_code == 403:
        return [], "UNAUTHORIZED", False
    if resp.status_code >= 500:
        return [], "UNAVAILABLE", False
    if resp.status_code != 200:
        return [], "UNAVAILABLE", False
    try:
        payload = resp.json()
    except Exception:
        return [], "UNAVAILABLE", False
    rows = _extract_list(payload, "members", "data")
    candidates = []
    for row in rows:
        mid = row.get("membership_id") or row.get("id") or row.get("person_id")
        name = row.get("display_name") or row.get("name") or row.get("full_name")
        aliases = []
        if row.get("aliases"):
            aliases = list(row.get("aliases") or [])
        # possible alias fields
        for key in ("alias", "nickname"):
            if row.get(key):
                aliases.append(row.get(key))
        candidates.append({
            "id": mid,
            "name": name,
            "aliases": aliases,
            "domain": "member",
            "household_id": row.get("household_id") or household_id,
            "role": row.get("role"),
            "status": row.get("status"),
            "source": "homeplus_read",
        })
    # Assume complete if no pagination indicator
    search_complete = True
    if isinstance(payload, dict):
        if payload.get("has_more") is True or payload.get("next") or payload.get("next_page"):
            search_complete = False
        if payload.get("total") is not None and len(rows) < int(payload.get("total") or 0):
            search_complete = False
    return candidates, None, search_complete


def read_assets(*, actor_id, household_id, authorization, base_url=None, timeout=10.0) -> Tuple[List[dict], Optional[str], bool]:
    if not household_id:
        return [], "UNAUTHORIZED", False
    url = f"{_base_url(base_url)}/api/inventory/items"
    params = {"household_id": household_id}
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, params=params, headers=_headers(authorization))
    except httpx.TimeoutException:
        return [], "UNAVAILABLE", False
    except httpx.TransportError:
        return [], "UNAVAILABLE", False
    except Exception:
        return [], "UNAVAILABLE", False
    if resp.status_code in (401, 403):
        return [], "UNAUTHORIZED", False
    if resp.status_code >= 500:
        return [], "UNAVAILABLE", False
    if resp.status_code != 200:
        return [], "UNAVAILABLE", False
    try:
        payload = resp.json()
    except Exception:
        return [], "UNAVAILABLE", False
    rows = _extract_list(payload, "items", "data")
    candidates = []
    for row in rows:
        aid = row.get("id") or row.get("item_id")
        name = row.get("name") or row.get("title") or row.get("label")
        aliases = list(row.get("aliases") or [])
        for key in ("alias", "nickname", "sku"):
            if row.get(key):
                aliases.append(row.get(key))
        candidates.append({
            "id": aid,
            "name": name,
            "aliases": aliases,
            "domain": "asset",
            "household_id": row.get("household_id") or household_id,
            "source": "homeplus_read",
        })
    search_complete = True
    if isinstance(payload, dict):
        if payload.get("has_more") is True or payload.get("next") or payload.get("next_page"):
            search_complete = False
    return candidates, None, search_complete
