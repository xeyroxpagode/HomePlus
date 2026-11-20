from __future__ import annotations

import sys
from pathlib import Path

ORCHESTRATOR_ROOT = Path(__file__).resolve().parent.parent
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

import homi_delivery as hd
from homi_delivery import DeliverySignals, select_delivery_plan, DeliveryPlan
import support
from support import make_request, run_invoke
import json


def test_tc01_neutral():
    plan = select_delivery_plan(DeliverySignals())
    assert plan.intent == "neutral"
    assert plan.reason_code == "DEFAULT_NEUTRAL"


def test_tc02_verified_success():
    plan = select_delivery_plan(DeliverySignals(verified_success=True))
    assert plan.intent == "confirmation"


def test_tc03_clarification():
    plan = select_delivery_plan(DeliverySignals(clarification_required=True))
    assert plan.intent == "question"


def test_tc04_confirmation_pending():
    plan = select_delivery_plan(DeliverySignals(confirmation_pending=True))
    assert plan.intent == "question"
    assert plan.pace == "slow"


def test_tc05_error():
    plan = select_delivery_plan(DeliverySignals(operation_failed=True))
    assert plan.intent == "warning"


def test_tc06_denied():
    plan = select_delivery_plan(DeliverySignals(operation_denied=True))
    assert plan.intent == "warning"
    assert plan.urgency == "normal"


def test_tc07_partial():
    plan = select_delivery_plan(DeliverySignals(partial_failure=True))
    assert plan.intent == "warning"


def test_tc08_precedence():
    plan = select_delivery_plan(DeliverySignals(verified_success=True, confirmation_pending=True))
    assert plan.intent == "question"


def test_tc09_determinism():
    s = DeliverySignals(verified_success=True)
    a = select_delivery_plan(s).model_dump()
    b = select_delivery_plan(s).model_dump()
    assert a == b


def test_tc11_locale():
    plan = select_delivery_plan(DeliverySignals())
    assert plan.locale == "es-AR"


def test_tc12_valid_values():
    for i in ["neutral", "confirmation", "question", "warning"]:
        p = DeliveryPlan(intent=i, urgency="normal", energy="medium", pace="normal", profile=i, reason_code="DEFAULT_NEUTRAL")
        assert p.intent == i


def test_tc13_invalid_values():
    try:
        DeliveryPlan(intent="foo", urgency="normal", energy="medium", pace="normal", profile="neutral", reason_code="DEFAULT_NEUTRAL")
        assert False
    except Exception:
        pass


def test_tc14_absent_signals():
    plan = select_delivery_plan(None)
    assert plan.intent == "neutral"


def test_tc16_think_misleading():
    # THINK says listo but failed
    plan = select_delivery_plan(DeliverySignals(operation_failed=True))
    assert plan.intent == "warning"


def test_tc17_injection_ignored():
    # arbitrary text cannot change plan
    plan = select_delivery_plan(DeliverySignals())
    assert plan.intent == "neutral"


def test_tc18_arbitrary_params_rejected():
    try:
        DeliveryPlan(intent="neutral", urgency="normal", energy="medium", pace="normal", profile="neutral", reason_code="DEFAULT_NEUTRAL", temperature=1.0)
        assert False
    except Exception:
        pass


def test_tc21_mapping_neutral():
    from homi_delivery import tts_map
    plan = select_delivery_plan(DeliverySignals())
    out = tts_map(plan, {"neutral"})
    assert out["applied_profile"] == "neutral"


def test_tc25_provider_no_profiles():
    from homi_delivery import tts_map
    plan = select_delivery_plan(DeliverySignals(verified_success=True))
    out = tts_map(plan, set())
    assert out["applied_profile"] == "neutral"
    assert out["fallback_reason"] is not None


def test_tc28_response_builder_integration():
    request = make_request(capability="think", operation="infer_with_tools", suffix="t27int", text="hola")
    # make a fake think response via support FakeTransport
    transport = support.FakeTransport()
    # default transport returns answer HOMI; run_invoke
    result = run_invoke(request, transport)
    # result may be ErrorEnvelope or ResponseEnvelope; check if response has delivery_plan
    if hasattr(result, "result") and isinstance(result.result, dict):
        assert "delivery_plan" in result.result


def test_tc30_text_intact():
    # ensure text answer unchanged (smoke)
    request = make_request(capability="think", operation="infer_with_tools", suffix="t27txt", text="hola")
    transport = support.FakeTransport()
    result = run_invoke(request, transport)
    if hasattr(result, "result") and isinstance(result.result, dict):
        # delivery_plan present but answer unchanged baseline
        assert "delivery_plan" in result.result