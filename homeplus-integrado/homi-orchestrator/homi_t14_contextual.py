"""HOMI T14.4 - Contextual Resolution & Integration."""
from __future__ import annotations
import uuid, time
from typing import Any, Dict, Optional

# In-memory clarification store keyed by (session, household, actor)
_CLARIFICATIONS: dict = {}

def create_clarification(*, actor_id, household_id, session_id, intent, ambiguous_expr, candidates, partial_results=None, ttl_seconds=300):
    cid = str(uuid.uuid4())
    rec = {
        "id": cid,
        "actor_id": str(actor_id) if actor_id is not None else None,
        "household_id": str(household_id) if household_id is not None else None,
        "session_id": str(session_id) if session_id is not None else None,
        "intent": intent,
        "ambiguous_expr": ambiguous_expr,
        "candidates": candidates,
        "partial_results": partial_results or {},
        "created_at": time.time(),
        "expires_at": time.time() + ttl_seconds,
        "status": "PENDING",
    }
    _CLARIFICATIONS[cid] = rec
    return rec

def find_pending_clarification(*, actor_id, household_id, session_id):
    now = time.time()
    for rec in _CLARIFICATIONS.values():
        if (str(rec.get("actor_id")) == str(actor_id)
                and str(rec.get("household_id")) == str(household_id)
                and str(rec.get("session_id")) == str(session_id)
                and rec.get("status") == "PENDING"
                and now <= rec.get("expires_at", 0)):
            return rec
    return None


def get_clarification(cid):
    rec = _CLARIFICATIONS.get(cid)
    if not rec: return None
    if time.time() > rec["expires_at"]:
        rec["status"] = "EXPIRED"
    return rec

def validate_clarification(cid, *, actor_id, household_id, session_id):
    rec = get_clarification(cid)
    if not rec: return False, "not_found"
    if rec["status"] != "PENDING": return False, rec["status"]
    if str(rec["actor_id"]) != str(actor_id): return False, "actor_mismatch"
    if str(rec["household_id"]) != str(household_id): return False, "household_mismatch"
    if str(rec["session_id"]) != str(session_id): return False, "session_mismatch"
    return True, "ok"

def select_candidate(cid, index_or_id, *, actor_id, household_id, session_id):
    ok, reason = validate_clarification(cid, actor_id=actor_id, household_id=household_id, session_id=session_id)
    if not ok:
        return {"status":"INVALID","reason":reason}
    rec = get_clarification(cid)
    cands = rec["candidates"] or []
    selected = None
    # index (1-based)
    if isinstance(index_or_id, int):
        if 1 <= index_or_id <= len(cands):
            selected = cands[index_or_id-1]
    else:
        # id or name
        for c in cands:
            if str(c.get("id")) == str(index_or_id) or str(c.get("name")).casefold() == str(index_or_id).casefold():
                selected = c; break
    if selected is None:
        return {"status":"INVALID","reason":"candidate_not_found"}
    rec["status"] = "RESOLVED_SELECTION"
    return {"status":"RESOLVED","selection":selected,"clarification_id":cid,"intent":rec["intent"],
            "partial_results":rec["partial_results"],"confirmation_required":True}

def cancel_clarification(cid, *, actor_id=None, household_id=None, session_id=None):
    rec = _CLARIFICATIONS.get(cid)
    if not rec:
        return False
    if actor_id is not None and str(rec.get("actor_id")) != str(actor_id):
        return False
    if household_id is not None and str(rec.get("household_id")) != str(household_id):
        return False
    if session_id is not None and str(rec.get("session_id")) != str(session_id):
        return False
    rec["status"] = "CANCELLED"
    return True


def resolve_contextual_reference(ref, *, context_candidates=None, pending_proposal=None, prior_results=None):
    """Resolve pronouns/contextual refs using authorized context only."""
    refn = str(ref).strip().casefold() if ref is not None else ""
    # pending proposal target
    if pending_proposal and refn in ("esa tarea","ese activo","eso","el de recien","el de recién","la de recien","la de recién"):
        tid = pending_proposal.get("target_id") or pending_proposal.get("task_id") or pending_proposal.get("id")
        if tid:
            return {"status":"RESOLVED","source":"pending_proposal","id":tid}
    # numbered options from clarification
    if context_candidates:
        if refn in ("la primera","primera","1","la 1","primero"):
            return {"status":"RESOLVED","source":"clarification_option","index":0}
        if refn in ("la segunda","segunda","2","la 2","segundo"):
            return {"status":"RESOLVED","source":"clarification_option","index":1}
        if refn in ("la tercera","tercera","3","la 3","tercero"):
            return {"status":"RESOLVED","source":"clarification_option","index":2}
        if refn in ("la otra","la otra tarea","el otro","la segunda") and len(context_candidates) == 2:
            # "la otra" -> the candidate not last selected; default to index 1 if only two
            return {"status":"RESOLVED","source":"clarification_option","index":1}
    # prior results (by key)
    if isinstance(prior_results, dict):
        if ref in prior_results:
            return {"status":"RESOLVED","source":"prior_result","value":prior_results[ref]}
        for k, v in prior_results.items():
            if str(k).casefold() == refn:
                return {"status":"RESOLVED","source":"prior_result","value":v}
    return {"status":"AMBIGUOUS","reason":"no_context_reference","original":ref}

def verify_relation(task, member, *, relation_field="assignee_id"):
    """Verify that a task is actually associated to member."""
    if not task or not member:
        return False
    val = task.get(relation_field) or task.get("assignee") or task.get("owner")
    # member may be id or name
    mid = member.get("id") if isinstance(member, dict) else member
    mname = member.get("name") if isinstance(member, dict) else None
    if val is None:
        return False
    if str(val) == str(mid):
        return True
    if mname and str(val).casefold() == str(mname).casefold():
        return True
    return False

def resolution_gate(resolutions, *, operation_supported=True):
    """Check all mandatory refs resolved before proposal."""
    missing = []
    for k, v in (resolutions or {}).items():
        if isinstance(v, dict):
            if v.get("status") != "RESOLVED":
                missing.append(k)
        elif v is None:
            missing.append(k)
    if not operation_supported:
        return {"allowed":False,"reason":"unsupported_operation"}
    if missing:
        return {"allowed":False,"reason":"missing_resolution","missing":missing}
    return {"allowed":True,"reason":"ok"}

def partial_resolution_merge(existing, new_results):
    out = dict(existing or {})
    for k, v in (new_results or {}).items():
        if isinstance(v, dict) and v.get("status") == "RESOLVED":
            out[k] = v
    return out
