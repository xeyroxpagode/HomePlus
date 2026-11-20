"""HOMI T14.1 - Temporal Resolver."""
from __future__ import annotations
import re
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any, Dict, Optional, List

MONTHS_ES = {
    "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
    "julio":7,"agosto":8,"septiembre":9,"setiembre":9,"octubre":10,"noviembre":11,"diciembre":12,
}
WEEKDAYS_ES = {
    "lunes":0,"martes":1,"miercoles":2,"jueves":3,"viernes":4,"sabado":5,"domingo":6,
}
MOMENTS = {"manana","tarde","noche","mediodia","mediodia","temprano","mas tarde","mas tarde"}

def _norm(s):
    import unicodedata
    s=" ".join(str(s).strip().lower().split())
    s="".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c)!="Mn")
    return s

def _zone(tz_name):
    if not tz_name:
        return None
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return None

def _local_ref(reference_utc, tz_name):
    zi = _zone(tz_name)
    if zi is None:
        # fallback UTC but mark uncertain
        return reference_utc.astimezone(timezone.utc), zi, False
    return reference_utc.astimezone(zi), zi, True

def _result(status, kind, **kw):
    base = {"status":status,"kind":kind}
    base.update(kw)
    return base

def resolve_temporal(expression, *, reference_utc=None, timezone=None, tz_status="resolved", expected_type=None, future_required=False):
    if reference_utc is None:
        reference_utc = datetime.now(timezone.utc)
    if reference_utc.tzinfo is None:
        reference_utc = reference_utc.replace(tzinfo=timezone.utc)
    expr = _norm(expression)
    if not expr:
        return _result("INVALID","none",original=expression,reason="empty_expression")
    local_dt, zi, tz_ok = _local_ref(reference_utc, timezone)
    # if tz invalid/absent
    tz_unresolved = (zi is None) or (tz_status != "resolved")
    # We'll still compute using UTC if needed but mark source.

    # ---- relative dates ----
    rel = {
        "hoy":0,"manana":1,"manana":1,"pasado manana":2,"pasado manana":2,
        "ayer":-1,"anteayer":-2,
    }
    if expr in rel:
        d = local_dt.date() + timedelta(days=rel[expr])
        return _result("RESOLVED","date",value=d.isoformat(),normalized=expr,
                       local_date=d.isoformat(),timezone=timezone,source="relative_day",
                       reference_utc=reference_utc.isoformat())

    # ---- week ranges ----
    if expr in ("esta semana",):
        # monday..sunday
        monday = local_dt.date() - timedelta(days=local_dt.weekday())
        sunday = monday + timedelta(days=6)
        return _result("RESOLVED","date_range",value={"start":monday.isoformat(),"end_exclusive":(sunday+timedelta(days=1)).isoformat()},
                       normalized=expr,timezone=timezone,source="calendar_week")
    if expr in ("la semana que viene","semana que viene","la proxima semana","la proxima semana"):
        monday = local_dt.date() - timedelta(days=local_dt.weekday()) + timedelta(days=7)
        sunday = monday + timedelta(days=6)
        return _result("RESOLVED","date_range",value={"start":monday.isoformat(),"end_exclusive":(sunday+timedelta(days=1)).isoformat()},
                       normalized=expr,timezone=timezone,source="calendar_week")
    if expr in ("este mes",):
        first = local_dt.date().replace(day=1)
        # last day
        if first.month==12:
            nxt = first.replace(year=first.year+1,month=1)
        else:
            nxt = first.replace(month=first.month+1)
        return _result("RESOLVED","date_range",value={"start":first.isoformat(),"end_exclusive":nxt.isoformat()},
                       normalized=expr,timezone=timezone,source="calendar_month")
    if expr in ("el mes que viene","mes que viene","el proximo mes","el proximo mes"):
        first = local_dt.date().replace(day=1)
        if first.month==12:
            first = first.replace(year=first.year+1,month=1)
        else:
            first = first.replace(month=first.month+1)
        if first.month==12:
            nxt = first.replace(year=first.year+1,month=1)
        else:
            nxt = first.replace(month=first.month+1)
        return _result("RESOLVED","date_range",value={"start":first.isoformat(),"end_exclusive":nxt.isoformat()},
                       normalized=expr,timezone=timezone,source="calendar_month")
    if expr in ("fin de semana","el fin de semana"):
        # saturday-sunday of current week
        sat = local_dt.date() - timedelta(days=local_dt.weekday()) + timedelta(days=5)
        sun = sat + timedelta(days=1)
        return _result("RESOLVED","date_range",value={"start":sat.isoformat(),"end_exclusive":(sun+timedelta(days=1)).isoformat()},
                       normalized=expr,timezone=timezone,source="weekend")
    if expr in ("los proximos siete dias","los proximos siete dias","proximos siete dias"):
        start = local_dt.date()
        end = start + timedelta(days=7)
        return _result("RESOLVED","date_range",value={"start":start.isoformat(),"end_exclusive":end.isoformat()},
                       normalized=expr,timezone=timezone,source="rolling_7_days")

    # ---- durations ----
    m = re.match(r"^(?:en|dentro de)\s+(\d+)\s+(minutos?|min|horas?|hora|dias?|dia|dias|semanas?)$", expr)
    if m:
        n = int(m.group(1)); unit = m.group(2)
        if unit.startswith("min"):
            delta = timedelta(minutes=n)
        elif unit.startswith("hora"):
            delta = timedelta(hours=n)
        elif unit.startswith("dia") or unit.startswith("dia"):
            delta = timedelta(days=n)
        elif unit.startswith("semana"):
            delta = timedelta(weeks=n)
        else:
            delta = timedelta()
        inst = reference_utc + delta
        return _result("RESOLVED","duration",value={"seconds":int(delta.total_seconds()),"instant_utc":inst.isoformat()},
                       normalized=expr,timezone=timezone,source="relative_duration")

    # ---- weekdays ----
    # patterns
    weekday_match = None
    for w in WEEKDAYS_ES:
        if w in expr:
            weekday_match = w
            break
    if weekday_match is not None:
        target_wd = WEEKDAYS_ES[weekday_match]
        today_wd = local_dt.weekday()
        # determine policy
        if "pasado" in expr:
            # previous occurrence
            days_back = (today_wd - target_wd) % 7
            if days_back == 0:
                days_back = 7
            d = local_dt.date() - timedelta(days=days_back)
            return _result("RESOLVED","date",value=d.isoformat(),normalized=expr,timezone=timezone,source="weekday_past")
        if "que viene" in expr or "proxim" in expr or "próxim" in expr:
            # next week's same weekday
            days_ahead = (target_wd - today_wd) % 7
            # ensure next week
            if days_ahead == 0:
                days_ahead = 7
            # if "proximo" chronological future: next occurrence strictly future
            if "proxim" in expr or "próxim" in expr:
                if days_ahead == 0:
                    days_ahead = 7
                d = local_dt.date() + timedelta(days=days_ahead)
                return _result("RESOLVED","date",value=d.isoformat(),normalized=expr,timezone=timezone,source="weekday_next_future")
            # "que viene" -> next week calendar
            base_monday = local_dt.date() - timedelta(days=local_dt.weekday())
            d = base_monday + timedelta(days=7 + target_wd)
            return _result("RESOLVED","date",value=d.isoformat(),normalized=expr,timezone=timezone,source="weekday_next_week")
        if expr.startswith("este ") or "este " in expr:
            # friday of current week
            monday = local_dt.date() - timedelta(days=local_dt.weekday())
            d = monday + timedelta(days=target_wd)
            # if already passed and future required -> ambiguous
            if future_required and d < local_dt.date():
                return _result("AMBIGUOUS","date",original=expression,candidates=[d.isoformat(), (d+timedelta(days=7)).isoformat()],
                               reason="weekday_already_passed",timezone=timezone)
            return _result("RESOLVED","date",value=d.isoformat(),normalized=expr,timezone=timezone,source="weekday_this_week")
        # "el viernes" alone
        if expr in (f"el {weekday_match}", weekday_match, f"el {weekday_match} que viene"):
            pass
        # default: next applicable
        days_ahead = (target_wd - today_wd) % 7
        if days_ahead == 0:
            # today is that weekday -> ambiguous if precision needed
            if future_required:
                return _result("AMBIGUOUS","date",original=expression,
                               candidates=[local_dt.date().isoformat(), (local_dt.date()+timedelta(days=7)).isoformat()],
                               reason="today_same_weekday",timezone=timezone)
            return _result("RESOLVED","date",value=local_dt.date().isoformat(),normalized=expr,timezone=timezone,source="weekday_today")
        d = local_dt.date() + timedelta(days=days_ahead)
        return _result("RESOLVED","date",value=d.isoformat(),normalized=expr,timezone=timezone,source="weekday_next")

    # ---- explicit dates ----
    # numeric dd/mm or dd/mm/yyyy
    m = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$", expr)
    if m:
        dd = int(m.group(1)); mm = int(m.group(2)); yy = m.group(3)
        if yy is None:
            year = local_dt.year
        else:
            y = int(yy)
            if y < 100:
                y += 2000
            year = y
        try:
            d = date(year, mm, dd)
        except ValueError:
            return _result("INVALID","date",original=expression,reason="impossible_date",timezone=timezone)
        # if already passed and future required, don't auto next year
        if yy is None and future_required and d < local_dt.date():
            # leave as is but mark? spec says don't jump automatically; ask clarification
            return _result("AMBIGUOUS","date",original=expression,candidates=[d.isoformat(), d.replace(year=d.year+1).isoformat()],
                           reason="past_date_without_year",timezone=timezone)
        return _result("RESOLVED","date",value=d.isoformat(),normalized=expr,timezone=timezone,source="explicit_numeric")
    # "29 de febrero" or "dia de mes" / "dia de mes de año"
    m = re.match(r"^(\d{1,2})\s+de\s+([a-záéíóúñ]+)(?:\s+de\s+(\d{2,4}))?$", expr)
    if m:
        dd = int(m.group(1)); mon_name = m.group(2); yy = m.group(3)
        if mon_name not in MONTHS_ES:
            return _result("INVALID","date",original=expression,reason="unknown_month",timezone=timezone)
        mm = MONTHS_ES[mon_name]
        if yy is None:
            year = local_dt.year
        else:
            y = int(yy)
            if y < 100: y += 2000
            year = y
        try:
            d = date(year, mm, dd)
        except ValueError:
            return _result("INVALID","date",original=expression,reason="impossible_date",timezone=timezone)
        if yy is None and future_required and d < local_dt.date():
            return _result("AMBIGUOUS","date",original=expression,candidates=[d.isoformat(), d.replace(year=d.year+1).isoformat()],
                           reason="past_date_without_year",timezone=timezone)
        return _result("RESOLVED","date",value=d.isoformat(),normalized=expr,timezone=timezone,source="explicit_named")
    # "primero de enero"
    m = re.match(r"^(primero|1ro|1º|primero de)\s+de\s+([a-záéíóúñ]+)(?:\s+de\s+(\d{2,4}))?$", expr)
    if m:
        mon_name = m.group(2); yy = m.group(3)
        if mon_name not in MONTHS_ES:
            return _result("INVALID","date",original=expression,reason="unknown_month",timezone=timezone)
        mm = MONTHS_ES[mon_name]
        dd = 1
        year = local_dt.year if yy is None else (int(yy)+2000 if int(yy)<100 else int(yy))
        try:
            d = date(year, mm, dd)
        except ValueError:
            return _result("INVALID","date",original=expression,reason="impossible_date",timezone=timezone)
        return _result("RESOLVED","date",value=d.isoformat(),normalized=expr,timezone=timezone,source="explicit_named")

    # ---- hours ----
    # explicit HH:MM
    m = re.match(r"^(\d{1,2}):(\d{2})$", expr)
    if m:
        h = int(m.group(1)); mi = int(m.group(2))
        if h>23 or mi>59:
            return _result("INVALID","time",original=expression,reason="invalid_time",timezone=timezone)
        # DST check if tz available
        tstr = f"{h:02d}:{mi:02d}"
        return _result("RESOLVED","time",value=tstr,normalized=expr,timezone=timezone,source="explicit_time")
    # "ocho de la manana"
    NUMWORDS = {"uno":1,"dos":2,"tres":3,"cuatro":4,"cinco":5,"seis":6,"siete":7,"ocho":8,"nueve":9,"diez":10,"once":11,"doce":12}
    m = re.match(r"^(?:a las\s+)?([a-z]+|\d{1,2})\s+de la (manana|tarde|noche)$", expr)
    if m and m.group(1) in NUMWORDS:
        expr = expr.replace(m.group(1), str(NUMWORDS[m.group(1)]), 1)
        m = re.match(r"^(?:a las\s+)?(\d{1,2})\s+de la (manana|tarde|noche)$", expr)
    if m:
        h = int(m.group(1)); part = m.group(2)
        if part == "manana":
            hh = h % 12
        elif part == "tarde":
            hh = (h % 12) + 12 if h < 12 else h
            if hh < 12: hh += 12
        elif part == "noche":
            hh = (h % 12) + 12 if h < 12 else h
            if h == 12: hh = 0 if False else 24%24
        # normalize rough
        if part in ("tarde","noche") and h < 12:
            hh = h + 12
        if part == "manana" and h == 12:
            hh = 0
        if hh > 23:
            return _result("INVALID","time",original=expression,reason="invalid_time",timezone=timezone)
        return _result("RESOLVED","time",value=f"{hh:02d}:00",normalized=expr,timezone=timezone,source="named_time")
    if expr in ("mediodia","mediodia"):
        return _result("RESOLVED","time",value="12:00",normalized=expr,timezone=timezone,source="named_time")
    if expr in ("medianoche",):
        return _result("RESOLVED","time",value="00:00",normalized=expr,timezone=timezone,source="named_time")
    # "a las ocho" ambiguous
    m = re.match(r"^(?:a las\s+)?(\d{1,2})$", expr)
    if m:
        h = int(m.group(1))
        if h > 23:
            return _result("INVALID","time",original=expression,reason="invalid_time",timezone=timezone)
        # if no am/pm and exact instant required -> ambiguous candidates
        cands = [f"{h:02d}:00"]
        if h <= 12:
            cands = [f"{h:02d}:00", f"{(h+12)%24:02d}:00"]
            # dedup
            cands = sorted(set(cands))
        if len(cands) > 1:
            return _result("AMBIGUOUS","time",original=expression,candidates=cands,reason="missing_am_pm",timezone=timezone)
        return _result("RESOLVED","time",value=cands[0],normalized=expr,timezone=timezone,source="explicit_time")

    # moments of day
    if expr in MOMENTS or expr in ("a la manana","al mediodia","a la tarde","a la noche","temprano","mas tarde","mas tarde"):
        return _result("RESOLVED","time_of_day",value=None,normalized=expr,timezone=timezone,
                       source="time_of_day",needs_precision=True,reason="no_exact_hour")

    # ---- DST / timezone conversion for datetime? handled by caller ----

    # ---- unsupported/ambiguous fallback ----
    return _result("UNSUPPORTED","none",original=expression,reason="unrecognized_temporal",timezone=timezone)

def combine_to_instant(date_str, time_str, tz_name, *, reference_utc=None):
    """Combine local date+time into UTC instant, handling DST nonexistent/duplicate."""
    zi = _zone(tz_name) if tz_name else None
    if zi is None:
        # cannot convert reliably
        return {"status":"UNAVAILABLE","reason":"timezone_unavailable","timezone":tz_name}
    try:
        y, m, d = [int(x) for x in date_str.split("-")]
        hh, mm = [int(x) for x in time_str.split(":")]
    except Exception:
        return {"status":"INVALID","reason":"bad_components"}
    # build naive local datetime
    naive = datetime(y, m, d, hh, mm, tzinfo=zi, fold=0)
    # check existence: convert to UTC and back
    utc0 = naive.astimezone(timezone.utc)
    back0 = utc0.astimezone(zi)
    # nonexistent if wall time changed
    if (back0.year,back0.month,back0.day,back0.hour,back0.minute) != (y,m,d,hh,mm):
        # try fold=1
        naive1 = datetime(y,m,d,hh,mm,tzinfo=zi,fold=1)
        utc1 = naive1.astimezone(timezone.utc)
        back1 = utc1.astimezone(zi)
        if (back1.year,back1.month,back1.day,back1.hour,back1.minute) != (y,m,d,hh,mm):
            return {"status":"INVALID","reason":"nonexistent_local_time_dst","timezone":tz_name}
        # duplicate hour
        return {"status":"AMBIGUOUS","reason":"ambiguous_dst_duplicate","candidates":[utc0.isoformat(),utc1.isoformat()],"timezone":tz_name}
    # duplicate check: fold 0 and fold 1 differ
    naive1 = datetime(y,m,d,hh,mm,tzinfo=zi,fold=1)
    if naive1.utcoffset() != naive.utcoffset():
        utc1 = naive1.astimezone(timezone.utc)
        return {"status":"AMBIGUOUS","reason":"ambiguous_dst_duplicate","candidates":[utc0.isoformat(),utc1.isoformat()],"timezone":tz_name}
    return {"status":"RESOLVED","kind":"instant","value":utc0.isoformat(),"timezone":tz_name}
