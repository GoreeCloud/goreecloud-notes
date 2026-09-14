import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "platform" / "mobile-client-readiness.json"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_mobile_readiness_contract_is_fail_closed() -> None:
    contract = load_contract()

    assert contract["schema"] == "goreecloud.notes.mobile-client-readiness/v1"
    assert contract["product"] == "GoreeCloud Notes"
    assert contract["lifecycle"] == "development"
    assert contract["authority"]["milestone"] == "Milestone 5 — Mobility and Offline Work"

    android = contract["android"]
    assert android["status"] == "blocked-prerequisites"
    assert android["production_capable"] is False
    assert android["stable_eligible"] is False
    assert android["implementation_started"] is False

    prerequisites = contract["prerequisites"]
    required = {
        "mobile_api_contract",
        "native_identity_binding",
        "incremental_sync_and_conflicts",
        "attachment_transfer",
        "local_data_protection",
        "privacy_shield",
        "wardveil_security",
        "everkeep",
        "goreecloud_sync",
        "glaze_ui_current_stable",
        "representative_android_acceptance",
    }
    assert set(prerequisites) == required
    assert all(item["required"] is True for item in prerequisites.values())
    assert all(item["accepted"] is False for item in prerequisites.values())
    assert all(item["evidence"] == [] for item in prerequisites.values())


def test_mobile_readiness_contract_preserves_authority_invariants() -> None:
    invariants = load_contract()["invariants"]

    assert invariants["backend_authorization_remains_authoritative"] is True
    assert invariants["browser_cookie_reuse_for_native_authentication_allowed"] is False
    assert invariants["embedded_reusable_service_credentials_allowed"] is False
    assert invariants["client_selected_owner_authority_allowed"] is False
    assert invariants["offline_cache_is_authoritative_store"] is False
    assert invariants["sync_equals_backup"] is False
    assert invariants["missing_evidence_may_be_presented_as_acceptance"] is False


def test_android_cannot_be_marked_ready_while_required_prerequisites_are_open() -> None:
    contract = load_contract()
    prerequisites = contract["prerequisites"]
    open_required = [
        name
        for name, item in prerequisites.items()
        if item["required"] and not item["accepted"]
    ]

    assert open_required
    assert contract["android"]["status"] != "ready"
    assert contract["android"]["production_capable"] is False
    assert contract["android"]["stable_eligible"] is False
