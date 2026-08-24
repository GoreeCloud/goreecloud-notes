from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "platform" / "integrations.json"
REQUIRED = {"glazeUI", "wardveilSecurity", "privacyShield", "everkeep"}
ALLOWED_STATUS = {"planned", "foundation", "implemented", "validated", "accepted"}


def main() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("schema") != "goreecloud.platform-integrations/v1":
        raise SystemExit("unsupported platform integration schema")
    if data.get("application") != "GoreeCloud Notes":
        raise SystemExit("platform contract must identify GoreeCloud Notes")
    if data.get("implementation") != "native":
        raise SystemExit("Notes must remain an original native implementation")

    systems = data.get("systems")
    if not isinstance(systems, dict):
        raise SystemExit("systems must be an object")

    missing = REQUIRED - systems.keys()
    if missing:
        raise SystemExit(f"missing mandatory systems: {sorted(missing)}")

    for name in sorted(REQUIRED):
        entry = systems[name]
        if not isinstance(entry, dict):
            raise SystemExit(f"{name} must be an object")
        if entry.get("required") is not True:
            raise SystemExit(f"{name} must remain required")
        if entry.get("status") not in ALLOWED_STATUS:
            raise SystemExit(f"{name} has invalid status")
        evidence = entry.get("evidence")
        if not isinstance(evidence, list) or not evidence or not all(isinstance(item, str) and item.strip() for item in evidence):
            raise SystemExit(f"{name} must record non-empty evidence")

    gates = data.get("openAcceptanceGates")
    if not isinstance(gates, list):
        raise SystemExit("openAcceptanceGates must be a list")

    if not data.get("stableQualificationBlocked"):
        nonaccepted = [name for name in sorted(REQUIRED) if systems[name]["status"] != "accepted"]
        if nonaccepted:
            raise SystemExit("Stable qualification may be unblocked only after acceptance: " + ", ".join(nonaccepted))
        if gates:
            raise SystemExit("Stable qualification cannot be unblocked with open acceptance gates")


if __name__ == "__main__":
    main()
