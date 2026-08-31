"""Tests for the private administrative audit attribution boundary."""

import pytest

from app.admin_audit import (
    MAX_AUDIT_REASON_LENGTH,
    MAX_OPERATOR_IDENTIFIER_LENGTH,
    resolve_admin_audit_context,
)


def test_development_can_omit_audit_context_for_disposable_fixtures() -> None:
    assert (
        resolve_admin_audit_context(
            operator_identifier=None,
            reason=None,
            production_required=False,
        )
        is None
    )


def test_production_admin_mutation_requires_operator_and_reason() -> None:
    with pytest.raises(ValueError, match="Production administrative mutations require"):
        resolve_admin_audit_context(
            operator_identifier=None,
            reason=None,
            production_required=True,
        )


@pytest.mark.parametrize(
    ("operator_identifier", "reason"),
    [
        ("operator-01", None),
        (None, "approved recovery"),
        ("   ", "approved recovery"),
        ("operator-01", "   "),
    ],
)
def test_partial_audit_context_is_always_rejected(
    operator_identifier: str | None,
    reason: str | None,
) -> None:
    with pytest.raises(ValueError, match="must be supplied together"):
        resolve_admin_audit_context(
            operator_identifier=operator_identifier,
            reason=reason,
            production_required=False,
        )


def test_audit_context_is_trimmed_without_normalizing_meaning() -> None:
    context = resolve_admin_audit_context(
        operator_identifier="  ladamian-admin  ",
        reason="  Approved account recovery after identity verification.  ",
        production_required=True,
    )

    assert context is not None
    assert context.operator_identifier == "ladamian-admin"
    assert context.reason == "Approved account recovery after identity verification."


def test_audit_context_lengths_are_bounded() -> None:
    with pytest.raises(ValueError, match="Operator identifier"):
        resolve_admin_audit_context(
            operator_identifier="x" * (MAX_OPERATOR_IDENTIFIER_LENGTH + 1),
            reason="approved",
            production_required=True,
        )

    with pytest.raises(ValueError, match="Audit reason"):
        resolve_admin_audit_context(
            operator_identifier="operator-01",
            reason="x" * (MAX_AUDIT_REASON_LENGTH + 1),
            production_required=True,
        )
