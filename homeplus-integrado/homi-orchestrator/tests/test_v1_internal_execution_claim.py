"""The gateway can read only the current D-owned execution claim."""

import hashlib
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app
import homi_tool_execution_ledger as ledger


def test_execution_claim_requires_secret_and_matching_scope(monkeypatch):
    secret = "test-only-internal-secret"
    monkeypatch.setenv("HOMI_INTERNAL_WRITE_SECRET", secret)
    args = {"title": "QA"}
    digest = hashlib.sha256(b'{"title":"QA"}').hexdigest()
    proposal = SimpleNamespace(
        status="EXECUTING",
        expires_at=None,
        tool_id="planner.tasks.create",
        public_projection={"proposal": {"arguments": args}},
    )
    run = SimpleNamespace(
        status="EXECUTING",
        actor_ref=ledger.actor_reference("actor-qa"),
        scope_ref=ledger.scope_reference("household-qa"),
        payload_hash=digest,
    )
    monkeypatch.setattr(app, "get_terminal_proposal_by_id", lambda _: proposal)
    monkeypatch.setattr(ledger, "get_ledger", lambda: SimpleNamespace(get=lambda _: run))
    client = TestClient(app.app)
    url = "/api/homi/v1/internal/proposals/prop_qa"
    assert client.get(url).status_code == 403
    headers = {
        "X-Homi-Internal-Write": secret,
        "X-Actor-Id": "actor-qa",
        "X-Household-Id": "other-household",
    }
    assert client.get(url, headers=headers).status_code == 403
    headers["X-Household-Id"] = "household-qa"
    response = client.get(url, headers=headers)
    assert response.status_code == 200
    assert response.json()["proposal"]["args_hash"] == digest
