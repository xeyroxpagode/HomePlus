"""HOMI T14.2/3 - Entity Resolver Core."""
from __future__ import annotations
import re, unicodedata
from typing import Any, Dict, List, Optional
try:
    from rapidfuzz import fuzz, process
    _HAS_RF = True
except Exception:
    _HAS_RF = False

STATUSES = {"RESOLVED","AMBIGUOUS","NOT_FOUND","INVALID","UNSUPPORTED","UNAVAILABLE","UNAUTHORIZED","INCOMPLETE"}

def normalize_name(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    # unicode normalize
    s = unicodedata.normalize("NFKC", s)
    s = s.casefold()
    # remove accents? Keep but normalize; also strip accents for matching key
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    # punctuation -> space
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _aliases(entity):
    als = []
    name = entity.get("name")
    if name: als.append(name)
    for a in entity.get("aliases", []) or []:
        als.append(a)
    # contextual alias
    if entity.get("context_alias"):
        als.append(entity["context_alias"])
    return als

def _candidate_ok(candidate, household_id, domain):
    if candidate.get("household_id") is not None and household_id is not None:
        if str(candidate["household_id"]) != str(household_id):
            return False
    if candidate.get("domain") is not None and domain is not None:
        if str(candidate["domain"]) != str(domain):
            return False
    return True

def resolve_entity(expression, *, domain, household_id=None, actor_id=None, candidates=None, candidates_source="provided", search_complete=True, read_error=None):
    """Core resolution over provided candidates. Returns result dict."""
    expr_raw = expression
    expr = (expression or "").strip() if isinstance(expression, str) else expression
    if not isinstance(expr, str) or not expr.strip():
        return {"status":"INVALID","domain":domain,"original":expr_raw,"reason":"empty_expression"}
    if domain is None:
        return {"status":"INVALID","domain":domain,"original":expr_raw,"reason":"missing_domain"}
    # read errors
    if read_error:
        # map
        code = str(read_error).upper()
        if "UNAUTH" in code:
            return {"status":"UNAUTHORIZED","domain":domain,"original":expr_raw,"reason":str(read_error)}
        if "UNAVAIL" in code or "UNAVAILABLE" in code:
            return {"status":"UNAVAILABLE","domain":domain,"original":expr_raw,"reason":str(read_error)}
        return {"status":"UNAVAILABLE","domain":domain,"original":expr_raw,"reason":str(read_error)}
    if candidates is None:
        candidates = []
    # filter authorized
    auth = [c for c in candidates if _candidate_ok(c, household_id, domain)]
    # exact name
    norm_expr = normalize_name(expr)
    exact = []
    alias_exact = []
    norm_matches = []
    for c in auth:
        names = [normalize_name(x) for x in _aliases(c)]
        raw_names = [str(x).strip().casefold() for x in _aliases(c) if x is not None]
        if expr.strip().casefold() in [n.casefold() for n in _aliases(c) if isinstance(n,str)]:
            exact.append(c)
        # alias exact (case-insensitive)
        if any(str(x).strip().casefold() == expr.strip().casefold() for x in _aliases(c) if isinstance(x,str)):
            alias_exact.append(c)
        if norm_expr in names:
            norm_matches.append(c)
    # precedence: exact -> alias -> normalized
    if exact:
        uniq = _dedup_by_id(exact)
        if len(uniq) == 1:
            return _make_resolved(uniq[0], expr_raw, "exact_name", domain)
        return _make_ambiguous(uniq, expr_raw, "exact_name_collision", domain)
    if alias_exact:
        uniq = _dedup_by_id(alias_exact)
        if len(uniq) == 1:
            return _make_resolved(uniq[0], expr_raw, "exact_alias", domain)
        return _make_ambiguous(uniq, expr_raw, "alias_collision", domain)
    if norm_matches:
        uniq = _dedup_by_id(norm_matches)
        if len(uniq) == 1:
            return _make_resolved(uniq[0], expr_raw, "normalized", domain)
        return _make_ambiguous(uniq, expr_raw, "normalized_collision", domain)

    # fuzzy matching on authorized candidates
    if auth and _HAS_RF:
        # build choices
        choices = []
        for c in auth:
            for a in _aliases(c):
                choices.append((str(a), c))
        if choices:
            # compute best scores
            scored = []
            for text, c in choices:
                sc = fuzz.WRatio(norm_expr, normalize_name(text))
                scored.append((sc, c))
            # group by candidate max
            best_by_cand = {}
            for sc, c in scored:
                cid = c.get("id")
                if cid not in best_by_cand or sc > best_by_cand[cid][0]:
                    best_by_cand[cid] = (sc, c)
            ranked = sorted(best_by_cand.values(), key=lambda x: x[0], reverse=True)
            if ranked:
                top_score, top_cand = ranked[0]
                # threshold
                THRESHOLD = 85
                if top_score >= THRESHOLD:
                    # check margin / collision
                    if len(ranked) > 1 and ranked[1][0] >= THRESHOLD and (top_score - ranked[1][0]) < 5:
                        cands = [r[1] for r in ranked if r[0] >= THRESHOLD]
                        return _make_ambiguous(_dedup_by_id(cands), expr_raw, "fuzzy_collision", domain, score=top_score)
                    # ensure not weak for writes? caller decides; mark score
                    return _make_resolved(top_cand, expr_raw, "fuzzy", domain, score=top_score)
    # not found vs incomplete
    if not search_complete:
        return {"status":"INCOMPLETE","domain":domain,"original":expr_raw,"reason":"search_incomplete"}
    return {"status":"NOT_FOUND","domain":domain,"original":expr_raw,"reason":"no_match"}

def _dedup_by_id(cands):
    seen = set(); out = []
    for c in cands:
        cid = c.get("id")
        if cid in seen: continue
        seen.add(cid); out.append(c)
    return out

def _make_resolved(cand, expr, method, domain, **extra):
    return {
        "status":"RESOLVED",
        "domain":domain,
        "original":expr,
        "id":cand.get("id"),
        "name":cand.get("name"),
        "entity":cand,
        "method":method,
        "source":"homeplus_read",
        **extra,
    }

def _make_ambiguous(cands, expr, reason, domain, **extra):
    return {
        "status":"AMBIGUOUS",
        "domain":domain,
        "original":expr,
        "candidates":[
            {"id":c.get("id"),"name":c.get("name"),"extra":{k:v for k,v in c.items() if k not in ("id","name")}}
            for c in cands
        ],
        "reason":reason,
        **extra,
    }
