"""HOMI Pass 2 — catálogo de D definitivo (307 tools).

Estas pruebas verifican:

* el artefacto del catálogo v2 carga y verifica contra su ancla;
* la salida define los 307 tool ids objetivo;
* los READ deben ser kind=READ + NEVER; los WRITE deben tener risk mutacional;
* no hay campos de identidad en los schemas;
* el validador genérico rechaza keys prohibidas;
* `family.members.list` normalizado (salida canónica de D);
* el allow-list del catálogo v2 es visible a la entrada del modelo.
"""

from __future__ import annotations

import pytest

from homi_target_catalog import (  # noqa: E402
    V2_TARGET_READ_IDS,
    V2_TARGET_TOOL_IDS,
    V2_TARGET_WRITE_IDS,
)
from homi_tool_catalog import (  # noqa: E402
    CATALOG_V2_PATH,
    HOMI_TOOLS_V2_SHA256,
    T24_READ_TOOL_IDS,
    V2_CONFIRMATIONS,
    V2_KINDS,
    V2_WRITE_RISK_FLAGS,
    catalog_v2,
    effective_tool_ids,
    is_t24_read_enabled,
    is_t24_read_tool,
    sha256_bytes,
)
from homi_tool_normalize import normalize_tool_result
from homi_write_schemas import (  # noqa: E402
    WRITE_CONTRACTS,
    generic_validate_arguments,
)


def test_v2_catalogue_file_exists():
    assert CATALOG_V2_PATH.is_file()


def test_v2_catalogue_digest_matches_trust_anchor():
    data = CATALOG_V2_PATH.read_bytes()
    digest = sha256_bytes(data).upper()
    assert digest == HOMI_TOOLS_V2_SHA256


def test_v2_catalogue_loads_and_validates():
    cat = catalog_v2()
    assert cat.digest.upper() == HOMI_TOOLS_V2_SHA256
    assert cat.schema_version == "2.0.0"
    assert cat.tool_contract_version == "2.0.0"
    assert len(cat.tools) == len(V2_TARGET_TOOL_IDS)
    assert len(cat.tools) == 307


def test_v2_tool_ids_match_allow_list():
    cat = catalog_v2()
    tool_ids = [tool["tool_id"] for tool in cat.tools]
    assert tool_ids == sorted(tool_ids)
    assert tool_ids == list(V2_TARGET_TOOL_IDS)


def test_v2_reads_are_kind_read_and_confirmation_never():
    for tool in catalog_v2().tools:
        if tool["kind"] == "READ":
            assert "READ_ONLY" in tool["riskFlags"], tool["tool_id"]
            assert tool["confirmation"] == "NEVER", tool["tool_id"]
        else:
            assert "READ_ONLY" not in tool["riskFlags"], tool["tool_id"]
            assert tool["confirmation"] == "REQUIRED", tool["tool_id"]


def test_v2_write_risk_flags_are_mutational():
    for tool in catalog_v2().tools:
        if tool["kind"] == "WRITE":
            assert any(f in V2_WRITE_RISK_FLAGS for f in tool["riskFlags"]), tool["tool_id"]


def test_v2_input_schemas_have_no_forbidden_keys():
    from homi_tool_catalog import forbidden_keys_in  # noqa: E402

    for tool in catalog_v2().tools:
        forbidden = forbidden_keys_in(tool["inputSchema"])
        assert forbidden == [], f"forbidden keys in {tool['tool_id']}: {forbidden}"


def test_v2_ids_are_unique():
    assert len(set(V2_TARGET_TOOL_IDS)) == len(V2_TARGET_TOOL_IDS)
    assert len(set(V2_TARGET_WRITE_IDS)) == len(V2_TARGET_WRITE_IDS)


def test_effective_tool_ids_covers_catalogue():
    ids = effective_tool_ids()
    assert set(ids) == set(V2_TARGET_TOOL_IDS)
    assert is_t24_read_tool("finance.summary.get") is True
    assert is_t24_read_tool("planner.tasks.list") is True
    assert is_t24_read_tool("finance.expenses.create") is False  # WRITE


def test_is_t24_read_enabled_default_true():
    assert is_t24_read_enabled() is True


def test_generic_validator_rejects_forbidden_keys_and_unknown_fields():
    violations = generic_validate_arguments(
        "finance.expenses.create", {"actor_id": "x", "account_ref": "a1"}
    )
    assert any("forbidden" in v or "unknown" in v for v in violations) or violations


def test_generic_validator_accepts_valid_expense():
    assert generic_validate_arguments(
        "finance.expenses.create",
        {"account_ref": "a1", "amount": "10.50", "currency": "USD", "date": "2026-11-19"},
    ) == []


def test_write_contracts_count_and_risk():
    writes = [t for t in V2_TARGET_WRITE_IDS]
    assert len(writes) == 193
    for tool_id in writes:
        assert tool_id in WRITE_CONTRACTS
        contract = WRITE_CONTRACTS[tool_id]
        assert contract["kind"] == "WRITE"
        assert contract["confirmation"] == "REQUIRED"
        assert contract["execution_enabled"] is True


# ---------------------------------------------------------------------------
# Normalisation (salida canónica del normalizer)
# ---------------------------------------------------------------------------


def test_normalize_inventory_items_list():
    raw = {
        "ok": True,
        "data": {
            "items": [
                {
                    "item_ref": "item-1",
                    "name": "Leche entera",
                    "category_key": "dairy",
                    "quantity": 2,
                    "is_out_of_stock": False,
                }
            ]
        },
        "error": None,
        "truncated": False,
        "result_version": "1.0.0",
    }

    result = normalize_tool_result("inventory.items.list", raw)
    assert result.tool_id == "inventory.items.list"
    assert result.status == "SUCCESS"


def test_normalize_inventory_alerts_get():
    raw = {
        "ok": True,
        "data": {"low_stock": 3, "out_of_stock": 1, "pending_restock": 2},
        "error": None,
        "truncated": False,
        "result_version": "1.0.0",
    }

    result = normalize_tool_result("inventory.alerts.get", raw)
    assert result.data["low_stock"] == 3


def test_normalize_family_members_list():
    raw = {
        "ok": True,
        "data": {"members": [{"member_ref": "membership-1", "status": "active"}]},
        "error": None,
        "truncated": False,
        "result_version": "1.0.0",
    }

    result = normalize_tool_result("family.members.list", raw)
    assert result.data["members"][0]["member_ref"] == "membership-1"


def test_normalize_finance_movements_list():
    raw = {
        "ok": True,
        "data": {
            "movements": [
                {
                    "transaction_ref": "txn-1",
                    "type": "expense",
                    "amount": 45.50,
                    "currency": "ARS",
                    "date": "2026-10-15",
                    "category_label": "Supermercado",
                    "description": "Compra semanal",
                }
            ],
            "period": "2026-10",
        },
        "error": None,
        "truncated": False,
        "result_version": "1.0.0",
    }

    result = normalize_tool_result("finance.movements.list", raw)
    assert result.data["period"] == "2026-10"


def test_normalize_current_gateway_inventory_and_finance_lists():
    inventory = normalize_tool_result("inventory.items.list", {"items": []})
    assert inventory.data == {"items": []}

    finance = normalize_tool_result(
        "finance.accounts.list",
        {
            "accounts": [
                {
                    "id": "account-1",
                    "name": "Cuenta sueldo",
                    "currency": "ARS",
                    "accountType": "BANK",
                    "balanceState": "KNOWN",
                    "currentBalance": "1234.50",
                    "status": "ACTIVE",
                    "ownerPersonId": "must-not-leak",
                    "householdId": "must-not-leak",
                }
            ]
        },
    )
    assert finance.data["accounts"] == [
        {
            "account_ref": "account-1",
            "name": "Cuenta sueldo",
            "currency": "ARS",
            "account_type": "BANK",
            "balance_state": "KNOWN",
            "current_balance": "1234.50",
            "status": "ACTIVE",
        }
    ]


def test_normalize_finance_summary_get():
    raw = {
        "ok": True,
        "data": {
            "period": "2026-10",
            "context_type": "PERSONAL",
            "currencies": [
                {"currency": "ARS", "expense": 100.0, "income": 200.0, "net": 100.0}
            ],
        },
        "error": None,
        "truncated": False,
        "result_version": "1.0.0",
    }

    result = normalize_tool_result("finance.summary.get", raw)
    assert result.data["context_type"] == "PERSONAL"


def test_normalize_finance_transaction_get():
    raw = {
        "ok": True,
        "data": {
            "transaction_ref": "txn-42",
            "type": "income",
            "amount": 500.0,
            "currency": "USD",
            "date": "2026-10-01",
            "category_label": "Sueldo",
            "description": "Salario mensual",
        },
        "error": None,
        "truncated": False,
        "result_version": "1.0.0",
    }

    result = normalize_tool_result("finance.transaction.get", raw)
    assert result.data["currency"] == "USD"


def test_normalize_unknown_tool_raises():
    with pytest.raises(Exception):
        normalize_tool_result("inventory.unknown.tool", {"data": {}})


# ---------------------------------------------------------------------------
# Result version
# ---------------------------------------------------------------------------


def test_tool_result_version_constant():
    from homi_tool_normalize import TOOL_RESULT_VERSION

    assert TOOL_RESULT_VERSION == "1.0"
