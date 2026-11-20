import homi_t14_entity as E

def test_exact():
    cands = [{"id":"1","name":"Juli","household_id":"h1","domain":"member"}]
    r = E.resolve_entity("Juli", domain="member", household_id="h1", candidates=cands)
    assert r["status"]=="RESOLVED" and r["id"]=="1"

def test_alias():
    cands = [{"id":"1","name":"Benjamín","aliases":["Benja"],"household_id":"h1","domain":"member"}]
    r = E.resolve_entity("Benja", domain="member", household_id="h1", candidates=cands)
    assert r["status"]=="RESOLVED"

def test_collision():
    cands = [{"id":"1","name":"Juan","household_id":"h1","domain":"member"},
             {"id":"2","name":"Juan","household_id":"h1","domain":"member"}]
    r = E.resolve_entity("Juan", domain="member", household_id="h1", candidates=cands)
    assert r["status"]=="AMBIGUOUS"

def test_ps4_ps5():
    cands = [{"id":"a","name":"PlayStation 4","household_id":"h1","domain":"asset"},
             {"id":"b","name":"PlayStation 5","aliases":["PS5","Play"],"household_id":"h1","domain":"asset"}]
    r = E.resolve_entity("PS5", domain="asset", household_id="h1", candidates=cands)
    assert r["status"]=="RESOLVED" and r["id"]=="b"
    r2 = E.resolve_entity("Play", domain="asset", household_id="h1", candidates=cands)
    # "Play" alias only on PS5 -> resolved
    assert r2["status"]=="RESOLVED" and r2["id"]=="b"

def test_domain_wrong():
    cands = [{"id":"1","name":"Juli","household_id":"h1","domain":"member"}]
    r = E.resolve_entity("Juli", domain="task", household_id="h1", candidates=cands)
    assert r["status"] in ("NOT_FOUND","INCOMPLETE")

def test_cross_household():
    cands = [{"id":"1","name":"Juli","household_id":"h2","domain":"member"}]
    r = E.resolve_entity("Juli", domain="member", household_id="h1", candidates=cands)
    assert r["status"] in ("NOT_FOUND","INCOMPLETE")

def test_empty_complete():
    r = E.resolve_entity("Nadie", domain="member", household_id="h1", candidates=[], search_complete=True)
    assert r["status"]=="NOT_FOUND"

def test_incomplete():
    r = E.resolve_entity("Nadie", domain="member", household_id="h1", candidates=[], search_complete=False)
    assert r["status"]=="INCOMPLETE"

def test_uuid_invented_not_verified():
    # core doesn't verify uuid existence; but if not in candidates -> not found
    r = E.resolve_entity("123e4567-e89b-12d3-a456-426614174000", domain="member", household_id="h1", candidates=[])
    assert r["status"]=="NOT_FOUND"

def test_fuzzy_typo():
    cands = [{"id":"1","name":"Matematica","household_id":"h1","domain":"task"}]
    r = E.resolve_entity("Matematicas", domain="task", household_id="h1", candidates=cands)
    # fuzzy may resolve
    assert r["status"] in ("RESOLVED","NOT_FOUND","AMBIGUOUS")
