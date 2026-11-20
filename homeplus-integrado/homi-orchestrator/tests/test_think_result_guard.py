from __future__ import annotations

import unittest

import support
from support import (
    FakeTransport,
    json_response,
    make_request,
    resolution_document,
    run_invoke,
)


class ThinkResultGuardTests(unittest.TestCase):

    def _invoke_with_result(
        self,
        result: dict,
        suffix: str,
    ):
        request = make_request(suffix=suffix)

        transport = FakeTransport()

        transport.get_handler = (
            lambda method, url, **kwargs: json_response(
                resolution_document()
            )
        )

        transport.post_handler = (
            lambda method, url, **kwargs: json_response(
                support.success_envelope(
                    request,
                    result=result,
                )
            )
        )

        return run_invoke(request, transport)

    def test_non_empty_answer_is_accepted(self) -> None:
        result = self._invoke_with_result(
            {"answer": "HOMI"},
            "thinkok",
        )

        self.assertEqual(
            getattr(result, "status", None),
            "SUCCESS",
        )

        self.assertEqual(
            result.result.get("answer"),
            "HOMI",
        )

    def test_missing_answer_is_rejected(self) -> None:
        result = self._invoke_with_result(
            {"provider": "think-primary"},
            "thinkmissing",
        )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

        self.assertFalse(result.error.retryable)

        self.assertEqual(
            result.error.details.get("reason"),
            "invalid_think_result",
        )

    def test_blank_answer_is_rejected(self) -> None:
        result = self._invoke_with_result(
            {"answer": "   \n\t "},
            "thinkblank",
        )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

        self.assertFalse(result.error.retryable)

    def test_non_string_answer_is_rejected(self) -> None:
        result = self._invoke_with_result(
            {"answer": 42},
            "thinknonstring",
        )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

        self.assertFalse(result.error.retryable)

    def test_null_answer_is_rejected(self) -> None:
        result = self._invoke_with_result(
            {"answer": None},
            "thinknull",
        )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

    def test_guard_is_not_applied_to_see(self) -> None:
        request = make_request(
            capability="see",
            operation="observe",
            suffix="seeguard",
        )

        transport = FakeTransport()

        transport.get_handler = (
            lambda method, url, **kwargs: json_response(
                resolution_document(
                    capability="see",
                    provider_id="see-primary",
                    node_id="homi-b",
                    endpoint="http://homi-b:8011/invoke",
                )
            )
        )

        transport.post_handler = (
            lambda method, url, **kwargs: json_response(
                support.success_envelope(
                    request,
                    node_id="homi-b",
                    provider_id="see-primary",
                    capability="see",
                    result={},
                )
            )
        )

        result = run_invoke(request, transport)

        self.assertEqual(
            getattr(result, "status", None),
            "SUCCESS",
        )

    def test_guard_is_not_applied_to_speak(self) -> None:
        request = make_request(
            capability="speak",
            operation="say",
            suffix="speakguard",
        )

        transport = FakeTransport()

        transport.get_handler = (
            lambda method, url, **kwargs: json_response(
                resolution_document(
                    capability="speak",
                    provider_id="speak-primary",
                    node_id="homi-c",
                    endpoint="http://homi-c:8011/invoke",
                )
            )
        )

        transport.post_handler = (
            lambda method, url, **kwargs: json_response(
                support.success_envelope(
                    request,
                    node_id="homi-c",
                    provider_id="speak-primary",
                    capability="speak",
                    result={},
                )
            )
        )

        result = run_invoke(request, transport)

        self.assertEqual(
            getattr(result, "status", None),
            "SUCCESS",
        )


if __name__ == "__main__":
    unittest.main()
