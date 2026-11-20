"""HOMI T09-D — the frozen T08 legacy path must stay untouched."""

from __future__ import annotations

import unittest
from unittest import mock

import httpx
import support
import t09_support
from support import (
    FakeTransport,
    json_response,
    make_request,
    resolution_document,
    run_invoke,
)


class LegacyPathTests(unittest.TestCase):

    def test_infer_operation_is_unchanged(self) -> None:
        request = make_request(suffix="t09dlegacy")

        transport = FakeTransport()

        transport.get_handler = (
            lambda method, url, **kwargs: json_response(
                resolution_document(
                    extra_provider={"timeout_s": 180}
                )
            )
        )

        transport.post_handler = (
            lambda method, url, **kwargs: json_response(
                support.success_envelope(request)
            )
        )

        result = run_invoke(request, transport)

        self.assertEqual(
            getattr(result, "status", None),
            "SUCCESS",
        )

        self.assertEqual(
            result.result.get("answer"),
            "HOMI",
        )

        self.assertEqual(
            result.correlation.request_id,
            request.context.request_id,
        )

    def test_legacy_request_to_a_is_byte_equivalent(self) -> None:
        request = make_request(
            suffix="t09dbytes",
            text="Responde unicamente con la palabra: HOMI",
        )

        posts: list[dict] = []

        transport = FakeTransport()

        transport.get_handler = (
            lambda method, url, **kwargs: json_response(
                resolution_document(
                    extra_provider={"timeout_s": 180}
                )
            )
        )

        def post_handler(method, url, **kwargs):
            posts.append(kwargs.get("json"))

            return json_response(
                support.success_envelope(request)
            )

        transport.post_handler = post_handler

        run_invoke(request, transport)

        self.assertEqual(
            len(posts),
            1,
        )

        self.assertEqual(
            posts[0],
            request.model_dump(mode="json"),
        )

        sent = httpx.Request(
            "POST",
            "http://homi-a:8011/invoke",
            json=posts[0],
        ).read()

        expected = httpx.Request(
            "POST",
            "http://homi-a:8011/invoke",
            json=request.model_dump(mode="json"),
        ).read()

        self.assertEqual(
            sent,
            expected,
        )

        self.assertEqual(
            posts[0]["operation"],
            "infer",
        )

        self.assertEqual(
            posts[0]["payload"],
            {"text": "Responde unicamente con la palabra: HOMI"},
        )

    def test_legacy_path_never_invokes_the_tool_seam(self) -> None:
        request = make_request(suffix="t09dnotool")

        transport = FakeTransport()

        transport.get_handler = (
            lambda method, url, **kwargs: json_response(
                resolution_document(
                    extra_provider={"timeout_s": 180}
                )
            )
        )

        transport.post_handler = (
            lambda method, url, **kwargs: json_response(
                support.success_envelope(request)
            )
        )

        with mock.patch.object(
            support.orch,
            "invoke_with_tools",
            side_effect=AssertionError(
                "the legacy path must not reach the tool seam"
            ),
        ):
            result = run_invoke(request, transport)

        self.assertEqual(
            getattr(result, "status", None),
            "SUCCESS",
        )

    def test_legacy_path_ignores_the_authorization_header(
        self,
    ) -> None:
        request = make_request(suffix="t09dlegacyauth")

        posts: list[dict] = []

        transport = FakeTransport()

        transport.get_handler = (
            lambda method, url, **kwargs: json_response(
                resolution_document(
                    extra_provider={"timeout_s": 180}
                )
            )
        )

        def post_handler(method, url, **kwargs):
            posts.append(kwargs.get("json"))

            return json_response(
                support.success_envelope(request)
            )

        transport.post_handler = post_handler

        result = t09_support.run_invoke_with_tools(
            request,
            transport,
            authorization=f"Bearer {t09_support.SENTINEL_TOKEN}",
        )

        self.assertEqual(
            getattr(result, "status", None),
            "SUCCESS",
        )

        self.assertEqual(
            len(posts),
            1,
        )

        self.assertNotIn(
            t09_support.SENTINEL_TOKEN,
            str(posts[0]),
        )

        self.assertNotIn(
            "Authorization",
            str(posts[0]),
        )

    def test_no_new_endpoint_was_added(self) -> None:
        paths = sorted(
            route.path for route in support.orch.app.routes
        )

        self.assertEqual(
            paths,
            [
                "/docs",
                "/docs/oauth2-redirect",
                "/health",
                "/invoke",
                "/openapi.json",
                "/redoc",
            ],
        )

    def test_capability_enum_is_unchanged(self) -> None:
        from homi_contracts import Capability

        self.assertEqual(
            [item.value for item in Capability],
            [
                "think",
                "see",
                "hear",
                "speak",
                "find",
            ],
        )

    def test_control_plane_constant_matches_the_app(self) -> None:
        self.assertEqual(
            t09_support.loop.CONTROL_PLANE,
            support.orch.CONTROL_PLANE,
        )

    def test_tool_discriminator_is_operation_scoped(self) -> None:
        request = make_request(
            capability="think",
            operation="infer_with_tools",
            suffix="t09ddisc",
        )

        transport = FakeTransport()

        transport.get_handler = (
            lambda method, url, **kwargs: json_response(
                resolution_document(
                    extra_provider={"timeout_s": 180}
                )
            )
        )

        transport.post_handler = (
            lambda method, url, **kwargs: json_response(
                support.success_envelope(request)
            )
        )

        with mock.patch.object(
            support.orch,
            "invoke_with_tools",
            side_effect=AssertionError(
                "the tool seam must be reached"
            ),
        ) as seam:
            try:
                run_invoke(request, transport)

            except AssertionError:
                pass

            else:
                self.fail(
                    "the tool seam was not reached"
                )

        seam.assert_called_once()


if __name__ == "__main__":
    unittest.main()
