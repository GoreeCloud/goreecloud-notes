from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "platform" / "browser_capture.json"
DRAFT_BUILDER = ROOT / "backend" / "app" / "browser_capture.py"
DRAFT_TESTS = ROOT / "backend" / "tests" / "test_browser_capture.py"
ALLOWED_KINDS = {"page", "link", "selection"}


def main() -> None:
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if data.get("schema") != "goreecloud.browser-capture/v1":
        raise SystemExit("unsupported Browser capture contract schema")
    if data.get("service") != "GoreeCloud Notes":
        raise SystemExit("contract must identify GoreeCloud Notes")
    if data.get("destination") != "https://notes.goreecloud.com":
        raise SystemExit("unexpected Notes capture destination")

    kinds = data.get("acceptedKinds")
    if not isinstance(kinds, list) or not kinds or set(kinds) - ALLOWED_KINDS:
        raise SystemExit("acceptedKinds must be a non-empty subset of reviewed capture kinds")

    requirements = data.get("requirements")
    if not isinstance(requirements, dict):
        raise SystemExit("requirements must be an object")
    for key in ("authenticated", "reviewedAdapter", "oneTimeIntent", "leastPrivilege", "ownerScopedWrite"):
        if requirements.get(key) is not True:
            raise SystemExit(f"{key} must remain required")
    for key in ("privateBrowsingExportAllowed", "capturedContentInURLAllowed"):
        if requirements.get(key) is not False:
            raise SystemExit(f"{key} must remain false")

    implementation = data.get("implementation")
    if not isinstance(implementation, dict):
        raise SystemExit("implementation must be an object")
    draft_ready = implementation.get("captureDraftBuilderReady") is True
    endpoint_ready = implementation.get("serviceWriteEndpointReady") is True
    adapter_ready = implementation.get("browserAdapterReady") is True
    production = implementation.get("productionApproved") is True
    if draft_ready and (not DRAFT_BUILDER.is_file() or not DRAFT_TESTS.is_file()):
        raise SystemExit("capture draft readiness requires source and test evidence")
    if endpoint_ready and not draft_ready:
        raise SystemExit("service endpoint cannot be ready before the capture draft builder")

    gates = data.get("openGates")
    if not isinstance(gates, list):
        raise SystemExit("openGates must be a list")
    if adapter_ready and not endpoint_ready:
        raise SystemExit("Browser adapter cannot be ready before the service endpoint")
    if production and (not endpoint_ready or not adapter_ready or gates):
        raise SystemExit("production approval requires endpoint, adapter, and zero open gates")


if __name__ == "__main__":
    main()
