import json
from pathlib import Path

import homi_t17_find as F

ROOT = Path(__file__).resolve().parents[1]
T15 = ROOT / "t15_2" / "evidence" / "T15_2"
TMP = ROOT / "t17" / "_test_tmp"


def _see_from(name):
    raw = json.loads((T15 / name).read_text(encoding="utf-8"))
    return raw["response"]


def test_pdf_snapshot_ingestion(tmp_path):
    see = _see_from("from_d_pdf.json")
    store_root = tmp_path / "jobs"
    art = tmp_path / "art"
    provider = F.ControlledFixtureProvider({
        "doc-pdf-001": {
            "see_response": see,
            "security": {
                "owner_id": "member-a",
                "visibility": "household",
                "sensitivity": "normal",
                "mime_type": "application/pdf",
            },
        }
    })
    req = F.IngestionRequest(
        document_id="doc-pdf-001",
        document_version=1,
        household_id="household-a",
        source_type="homecloud_document",
        correlation_id="corr-pdf-1",
        owner_id="member-a",
        visibility="household",
        sensitivity="normal",
        mime_type="application/pdf",
    )
    job = F.run_ingestion(req, provider, F.JobStore(store_root), art)
    assert job.state == "SUCCEEDED"
    doc = json.loads(Path(job.result_ref["homi_document_path"]).read_text(encoding="utf-8"))
    chunks = json.loads(Path(job.result_ref["chunks_path"]).read_text(encoding="utf-8"))
    assert doc["text"].startswith("HOMI SEE WORKER")
    assert len(chunks) >= 1
    for c in chunks:
        assert c["metadata"]["household_id"] == "household-a"
        assert c["metadata"]["owner_id"] == "member-a"
        assert c["metadata"]["visibility"] == "household"


def test_docx_table(tmp_path):
    see = _see_from("from_d_docx.json")
    store_root = tmp_path / "jobs"
    art = tmp_path / "art"
    provider = F.ControlledFixtureProvider({
        "doc-docx-001": {"see_response": see, "security": {
            "owner_id": "member-b", "visibility": "personal", "sensitivity": "normal",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }}
    })
    req = F.IngestionRequest(
        document_id="doc-docx-001", document_version=1, household_id="household-b",
        source_type="homecloud_document", correlation_id="corr-docx-1",
        owner_id="member-b", visibility="personal", sensitivity="normal",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    job = F.run_ingestion(req, provider, F.JobStore(store_root), art)
    assert job.state == "SUCCEEDED"
    chunks = json.loads(Path(job.result_ref["chunks_path"]).read_text(encoding="utf-8"))
    # table chunk exists
    assert any(c["metadata"].get("content_type") == "table" for c in chunks)
    assert all(c["metadata"]["visibility"] == "personal" for c in chunks)


def test_idempotency(tmp_path):
    see = _see_from("from_d_pdf.json")
    store_root = tmp_path / "jobs"
    art = tmp_path / "art"
    provider = F.ControlledFixtureProvider({
        "doc-pdf-002": {"see_response": see, "security": {
            "owner_id": "member-a", "visibility": "household", "sensitivity": "normal",
            "mime_type": "application/pdf",
        }}
    })
    req = F.IngestionRequest(
        document_id="doc-pdf-002", document_version=1, household_id="household-a",
        source_type="homecloud_document", correlation_id="corr-1",
        owner_id="member-a", visibility="household", sensitivity="normal",
        mime_type="application/pdf",
    )
    j1 = F.run_ingestion(req, provider, F.JobStore(store_root), art)
    j2 = F.run_ingestion(req, provider, F.JobStore(store_root), art)
    assert j1.job_id == j2.job_id
    c1 = json.loads(Path(j1.result_ref["chunks_path"]).read_text())
    c2 = json.loads(Path(j2.result_ref["chunks_path"]).read_text())
    assert [c["chunk_id"] for c in c1] == [c["chunk_id"] for c in c2]


def test_new_version_different_ids(tmp_path):
    see = _see_from("from_d_pdf.json")
    store_root = tmp_path / "jobs"
    art = tmp_path / "art"
    prov = F.ControlledFixtureProvider({
        "doc-v": {"see_response": see, "security": {
            "owner_id": "member-a", "visibility": "household", "sensitivity": "normal",
            "mime_type": "application/pdf",
        }}
    })
    for v in (1, 2):
        req = F.IngestionRequest(
            document_id="doc-v", document_version=v, household_id="household-a",
            source_type="homecloud_document", correlation_id=f"corr-v{v}",
            owner_id="member-a", visibility="household", sensitivity="normal",
            mime_type="application/pdf",
        )
        job = F.run_ingestion(req, prov, F.JobStore(store_root), art)
        assert job.state == "SUCCEEDED"
    # ids should differ by version in metadata
    c1 = json.loads((art / "household-a" / "doc-v" / "v1" / "chunks.json").read_text())
    c2 = json.loads((art / "household-a" / "doc-v" / "v2" / "chunks.json").read_text())
    assert c1[0]["metadata"]["document_version"] == 1
    assert c2[0]["metadata"]["document_version"] == 2
    assert c1[0]["chunk_id"] != c2[0]["chunk_id"]


def test_household_isolation(tmp_path):
    see = _see_from("from_d_pdf.json")
    store_root = tmp_path / "jobs"
    art = tmp_path / "art"
    prov = F.ControlledFixtureProvider({
        "doc-iso": {"see_response": see, "security": {
            "owner_id": "member-a", "visibility": "household", "sensitivity": "normal",
            "mime_type": "application/pdf",
        }}
    })
    for hh, owner in (("household-a", "member-a"), ("household-b", "member-b")):
        req = F.IngestionRequest(
            document_id="doc-iso", document_version=1, household_id=hh,
            source_type="homecloud_document", correlation_id=f"corr-{hh}",
            owner_id=owner, visibility="household", sensitivity="normal",
            mime_type="application/pdf",
        )
        # override document_id per household to avoid idempotency collision? document same but household differs -> key includes household
        job = F.run_ingestion(req, prov, F.JobStore(store_root), art)
        assert job.state == "SUCCEEDED"
    ca = json.loads((art / "household-a" / "doc-iso" / "v1" / "chunks.json").read_text())
    cb = json.loads((art / "household-b" / "doc-iso" / "v1" / "chunks.json").read_text())
    assert all(c["metadata"]["household_id"] == "household-a" for c in ca)
    assert all(c["metadata"]["household_id"] == "household-b" for c in cb)


def test_missing_household_blocks():
    try:
        r = F.IngestionRequest(document_id="x", document_version=1, household_id="", source_type="homecloud_document", correlation_id="c")
        r.validate()
    except F.FindError as e:
        assert e.code == "MISSING_HOUSEHOLD"
    else:
        raise AssertionError("expected FindError")


def test_empty_extraction_fails(tmp_path):
    see = {"status": "success", "task": "read_document", "engine": "docling", "text": "   ", "fields": {}, "metadata": {}}
    store_root = tmp_path / "jobs"
    art = tmp_path / "art"
    prov = F.ControlledFixtureProvider({
        "doc-empty": {"see_response": see, "security": {
            "owner_id": "member-a", "visibility": "household", "sensitivity": "normal",
            "mime_type": "application/pdf",
        }}
    })
    req = F.IngestionRequest(
        document_id="doc-empty", document_version=1, household_id="household-a",
        source_type="homecloud_document", correlation_id="corr-empty",
        owner_id="member-a", visibility="household", sensitivity="normal",
        mime_type="application/pdf",
    )
    try:
        F.run_ingestion(req, prov, F.JobStore(store_root), art)
    except F.FindError as e:
        assert e.code == "EMPTY_EXTRACTION"
    else:
        raise AssertionError("expected failure")


def test_unsupported_mime_fails(tmp_path):
    see = _see_from("from_d_pdf.json")
    store_root = tmp_path / "jobs"
    art = tmp_path / "art"
    prov = F.ControlledFixtureProvider({
        "doc-mime": {"see_response": see, "security": {
            "owner_id": "member-a", "visibility": "household", "sensitivity": "normal",
            "mime_type": "application/x-evil",
        }}
    })
    req = F.IngestionRequest(
        document_id="doc-mime", document_version=1, household_id="household-a",
        source_type="homecloud_document", correlation_id="corr-mime",
        owner_id="member-a", visibility="household", sensitivity="normal",
        mime_type="application/x-evil",
    )
    try:
        F.run_ingestion(req, prov, F.JobStore(store_root), art)
    except F.FindError as e:
        assert e.code in ("UNSUPPORTED_MIME", "INVALID_SENSITIVITY") or "MIME" in e.code
    else:
        raise AssertionError("expected failure")


def test_missing_metadata_blocks_chunk():
    md = F.DocumentSecurityMetadata(household_id="h1", owner_id="", visibility="household", sensitivity="normal", mime_type="application/pdf")
    try:
        md.validate()
    except F.FindError as e:
        assert e.code == "MISSING_OWNER"
    else:
        raise AssertionError("expected failure")


def test_live_see_provider_uses_fresh_contract(monkeypatch):
    captured = {}

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(http_request, timeout):
        body = json.loads(http_request.data.decode("utf-8"))
        captured["body"] = body
        captured["authorization"] = http_request.get_header("Authorization")
        captured["timeout"] = timeout
        return FakeResponse({
            "contract_version": "see-1.0.0",
            "request_id": body["request_id"],
            "status": "success",
            "task": "read_document",
            "engine": "docling",
            "provider_id": "document-docling",
            "text": "fresh live parser text",
            "fields": {},
            "metadata": {"artifact": {"mime_type": "application/pdf"}},
        })

    monkeypatch.setattr(F.urllib.request, "urlopen", fake_urlopen)
    provider = F.LiveSeeDocumentProvider(
        "http://homi-b:8021", "secret-in-memory", {"doc-live": "doc-known-text-pdf"}, timeout_s=12
    )
    request = F.IngestionRequest(
        document_id="doc-live", document_version=1, household_id="household-live",
        source_type="fixture_document", correlation_id="corr-live", actor_id="member-live",
        owner_id="member-live", visibility="household", mime_type="application/pdf",
    )
    see, security, source_kind = provider.fetch(request)
    assert see["text"] == "fresh live parser text"
    assert captured["body"]["artifact"]["access_ref"] == "doc-known-text-pdf"
    assert captured["body"]["task"] == "read_document"
    assert captured["authorization"] == "Bearer secret-in-memory"
    assert captured["timeout"] == 12
    assert security.household_id == "household-live"
    assert source_kind == "see_worker_live"


def test_live_see_provider_rejects_path_reference():
    try:
        F.LiveSeeDocumentProvider(
            "http://homi-b:8021", "token", {"doc-live": "fixtures/document.pdf"}
        ).fetch(F.IngestionRequest(
            document_id="doc-live", document_version=1, household_id="household-live",
            source_type="fixture_document", correlation_id="corr-live", owner_id="member-live",
            mime_type="application/pdf",
        ))
    except F.FindError as error:
        assert error.code == "INVALID_ACCESS_REF"
    else:
        raise AssertionError("expected opaque access_ref validation failure")


def test_live_see_provider_classifies_timeout(monkeypatch):
    def timed_out(*_args, **_kwargs):
        raise F.urllib.error.URLError(TimeoutError("controlled timeout"))

    monkeypatch.setattr(F.urllib.request, "urlopen", timed_out)
    provider = F.LiveSeeDocumentProvider(
        "http://homi-b:8021", "token", {"doc-live": "doc-known-text-pdf"}, timeout_s=0.01
    )
    try:
        provider.fetch(F.IngestionRequest(
            document_id="doc-live", document_version=1, household_id="household-live",
            source_type="fixture_document", correlation_id="corr-timeout", owner_id="member-live",
            mime_type="application/pdf",
        ))
    except F.FindError as error:
        assert error.code == "PARSER_TIMEOUT"
        assert error.retryable is True
    else:
        raise AssertionError("expected timeout")
