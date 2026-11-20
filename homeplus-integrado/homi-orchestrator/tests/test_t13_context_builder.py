import os
import sys
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from homi_context_builder import (
    build_context,
    build_context_projection,
    project_for_think,
    resolve_timezone,
    validate_surface,
)
from homi_contracts import RequestContext, RequestEnvelope, Capability


def _make_request(actor="a1", household="h1", conv="conv_abcdefgh", tz_payload=None, surface=None, metadata=None):
    ctx = RequestContext(
        conversation_id=conv,
        actor_id=actor,
        household_id=household,
        timestamp=datetime(2026, 10, 29, 23, 30, tzinfo=timezone.utc),
    )
    payload = {}
    if tz_payload:
        payload.update(tz_payload)
    if surface is not None:
        payload["surface"] = surface
    if metadata:
        payload["client_metadata"] = metadata
    return RequestEnvelope(context=ctx, capability=Capability.THINK, operation="infer_with_tools", payload=payload)


class TestT13ContextBuilder(unittest.TestCase):
    def test_resolve_timezone_user_pref(self):
        tz, src, status = resolve_timezone(user_tz="Europe/Madrid")
        self.assertEqual(tz, "Europe/Madrid")
        self.assertEqual(src, "user_preference")
        self.assertEqual(status, "resolved")

    def test_resolve_timezone_invalid_fallback(self):
        tz, src, status = resolve_timezone(user_tz="Mars/Phobos")
        self.assertEqual(status, "resolved")
        self.assertEqual(tz, "UTC")

    def test_validate_surface_known(self):
        s, st = validate_surface("Planner")
        self.assertEqual(s, "planner")
        self.assertEqual(st, "valid")

    def test_validate_surface_unknown(self):
        s, st = validate_surface("admin")
        self.assertIsNone(s)
        self.assertEqual(st, "unknown")

    def test_validate_surface_none(self):
        s, st = validate_surface(None)
        self.assertIsNone(s)

    def test_build_context_basic(self):
        req = _make_request()
        env = build_context(req)
        d = env.to_dict()
        self.assertEqual(d["actor"]["status"], "VALID")
        self.assertEqual(d["household"]["status"], "VALID")
        self.assertEqual(d["session"]["status"], "VALID")
        self.assertIsNotNone(d["temporal"]["reference_time_utc"])
        self.assertIsNotNone(d["temporal"]["local_date"])
        self.assertEqual(d["surface"]["status"], "UNKNOWN")

    def test_build_context_surface(self):
        req = _make_request(surface="planner")
        env = build_context(req)
        d = env.to_dict()
        self.assertEqual(d["surface"]["kind"], "planner")
        self.assertEqual(d["surface"]["status"], "VALID")

    def test_build_context_timezone_payload(self):
        req = _make_request(tz_payload={"timezone": "America/Argentina/Buenos_Aires"})
        env = build_context(req)
        d = env.to_dict()
        self.assertEqual(d["temporal"]["timezone"], "America/Argentina/Buenos_Aires")
        self.assertEqual(d["temporal"]["status"], "resolved")

    def test_project_for_think_no_secrets(self):
        req = _make_request(surface="planner")
        env = build_context(req)
        proj = project_for_think(env)
        self.assertIn("temporal", proj)
        self.assertIn("surface", proj)
        flat = str(proj).lower()
        self.assertNotIn("jwt", flat)
        self.assertNotIn("token", flat)

    def test_build_context_projection(self):
        req = _make_request()
        proj = build_context_projection(req)
        self.assertIsInstance(proj, dict)
        self.assertIn("temporal", proj)

    def test_midnight_conversion(self):
        ctx = RequestContext(
            conversation_id="conv_abcdefgh",
            actor_id="a1",
            household_id="h1",
            timestamp=datetime(2026, 10, 29, 23, 59, tzinfo=timezone.utc),
        )
        req = RequestEnvelope(context=ctx, capability=Capability.THINK, operation="x", payload={"timezone": "America/Argentina/Buenos_Aires"})
        env = build_context(req)
        d = env.to_dict()
        self.assertEqual(d["temporal"]["local_date"], "2026-10-29")

    def test_surface_manipulation_no_perms(self):
        req = _make_request(surface="finances", metadata={"role": "admin"})
        env = build_context(req)
        d = env.to_dict()
        self.assertEqual(d["surface"]["kind"], "finances")
        self.assertNotIn("role", d["surface"])


if __name__ == "__main__":
    unittest.main()
