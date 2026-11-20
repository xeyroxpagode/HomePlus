import datetime
from datetime import timezone, timedelta
import homi_t14_temporal as T

def ref():
    return datetime.datetime(2026, 10, 29, 15, 0, tzinfo=timezone.utc)  # Thursday

def test_relative():
    r = T.resolve_temporal("manana", reference_utc=ref(), timezone="UTC")
    assert r["status"]=="RESOLVED"
    assert r["value"]=="2026-10-30"

def test_weekday_policy():
    r = T.resolve_temporal("este viernes", reference_utc=ref(), timezone="UTC", future_required=True)
    # Oct 29 Thu -> this friday Oct 30
    assert r["value"]=="2026-10-30"

def test_explicit_impossible():
    r = T.resolve_temporal("31/02/2026", reference_utc=ref(), timezone="UTC")
    assert r["status"]=="INVALID"

def test_hour_ambiguous():
    r = T.resolve_temporal("8", reference_utc=ref(), timezone="UTC")
    assert r["status"]=="AMBIGUOUS"

def test_named_time():
    r = T.resolve_temporal("ocho de la manana", reference_utc=ref(), timezone="UTC")
    assert r["value"]=="08:00"

def test_moment_no_hour():
    r = T.resolve_temporal("a la tarde", reference_utc=ref(), timezone="UTC")
    assert r["kind"]=="time_of_day"
    assert r["value"] is None

def test_range_week():
    r = T.resolve_temporal("esta semana", reference_utc=ref(), timezone="UTC")
    assert r["status"]=="RESOLVED"
    assert r["value"]["start"]=="2026-10-26"

def test_tz_conversion():
    r = T.combine_to_instant("2026-10-29","12:00","America/Argentina/Buenos_Aires")
    assert r["status"]=="RESOLVED"
    assert "2026-10-29T15:00" in r["value"]  # ART UTC-3

def test_dst_nonexistent():
    # spring forward example: America/New_York 2026-03-08 02:30 doesn't exist
    r = T.combine_to_instant("2026-03-08","02:30","America/New_York")
    assert r["status"] in ("INVALID","AMBIGUOUS")
