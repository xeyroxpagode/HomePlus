import homi_t14_contextual as C

def test_clarification_validation():
    rec = C.create_clarification(actor_id="a", household_id="h", session_id="s", intent="complete", ambiguous_expr="tarea", candidates=[{"id":"1","name":"T1"},{"id":"2","name":"T2"}])
    ok, _ = C.validate_clarification(rec["id"], actor_id="a", household_id="h", session_id="s")
    assert ok
    # cross household rejected
    ok2, _ = C.validate_clarification(rec["id"], actor_id="a", household_id="h2", session_id="s")
    assert not ok2

def test_selection_not_confirmation():
    rec = C.create_clarification(actor_id="a", household_id="h", session_id="s", intent="complete", ambiguous_expr="tarea", candidates=[{"id":"1","name":"T1"},{"id":"2","name":"T2"}])
    r = C.select_candidate(rec["id"], 2, actor_id="a", household_id="h", session_id="s")
    assert r["status"]=="RESOLVED"
    assert r["selection"]["id"]=="2"
    assert r["confirmation_required"] is True

def test_context_ref_numbered():
    r = C.resolve_contextual_reference("la segunda", context_candidates=[{"id":"1"},{"id":"2"}])
    assert r["status"]=="RESOLVED"

def test_expired():
    rec = C.create_clarification(actor_id="a", household_id="h", session_id="s", intent="x", ambiguous_expr="y", candidates=[{"id":"1","name":"T1"}], ttl_seconds=0)
    import time; time.sleep(0.01)
    ok,_ = C.validate_clarification(rec["id"], actor_id="a", household_id="h", session_id="s")
    assert not ok

def test_relation_verify():
    task = {"id":"t1","assignee_id":"m1"}
    member = {"id":"m1","name":"Juli"}
    assert C.verify_relation(task, member) is True
    assert C.verify_relation({"id":"t1","assignee_id":"m2"}, member) is False

def test_gate():
    r = C.resolution_gate({"entity":{"status":"RESOLVED"},"time":{"status":"RESOLVED"}})
    assert r["allowed"] is True
    r2 = C.resolution_gate({"entity":{"status":"AMBIGUOUS"}})
    assert r2["allowed"] is False

def test_partial_merge():
    out = C.partial_resolution_merge({}, {"juli":{"status":"RESOLVED","id":"1"}, "task":{"status":"AMBIGUOUS"}})
    assert "juli" in out and "task" not in out

def test_invented_uuid_gate():
    # contextual doesn't accept uuid without context
    r = C.resolve_contextual_reference("123e4567-e89b-12d3-a456-426614174000")
    assert r["status"] in ("AMBIGUOUS",)  # no auto resolve
