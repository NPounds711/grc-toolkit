"""Tests for the MFA aggregator. Uses fixture data — no AWS / Okta required."""

from __future__ import annotations

from pathlib import Path

from aggregators._base import AggregatorRunContext
from aggregators.mfa import AGGREGATOR as MFA_AGGREGATOR


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _ctx():
    return AggregatorRunContext(
        fixture_mode=True,
        fixture_dir=str(FIXTURES),
        run_id="test-run",
    )


def test_aggregator_emits_all_supported_controls():
    determinations = MFA_AGGREGATOR.determine(_ctx())
    seen = {(d.framework, d.control_id) for d in determinations}
    expected = (
        {("fedramp_rev5", c) for c in MFA_AGGREGATOR.SUPPORTED_CONTROLS_REV5}
        | {("fedramp_20x", k) for k in MFA_AGGREGATOR.SUPPORTED_KSIS}
    )
    assert expected.issubset(seen), f"Missing: {expected - seen}"


def test_ia_2_implemented_when_all_have_mfa():
    """Fixture: 4 active humans all have factors, plus 2 AWS humans with MFA."""
    determinations = MFA_AGGREGATOR.determine(_ctx())
    ia_2 = next(d for d in determinations if d.control_id == "IA-2" and d.framework == "fedramp_rev5")
    assert ia_2.status == "Implemented", ia_2.statement
    assert ia_2.metrics["compliant"] == ia_2.metrics["total"]


def test_ia_2_1_implemented_when_all_privileged_have_webauthn():
    determinations = MFA_AGGREGATOR.determine(_ctx())
    ia_2_1 = next(d for d in determinations if d.control_id == "IA-2(1)")
    assert ia_2_1.status == "Implemented", ia_2_1.statement


def test_ia_2_8_passes_when_only_phishing_resistant_in_use():
    determinations = MFA_AGGREGATOR.determine(_ctx())
    ia_2_8 = next(d for d in determinations if d.control_id == "IA-2(8)")
    # Dan has a TOTP factor in the fixture, so IA-2(8) should fail
    assert ia_2_8.status == "Planned", (
        f"IA-2(8) should flag TOTP as non-replay-resistant. Got: {ia_2_8.statement}"
    )


def test_ksi_iam_01_rolls_up_ia_2_1_and_2_2():
    determinations = MFA_AGGREGATOR.determine(_ctx())
    ksi = next(d for d in determinations if d.control_id == "KSI-IAM-01")
    assert ksi.framework == "fedramp_20x"
    assert ksi.status == "Implemented", ksi.statement
    assert "IA-2(1)" in ksi.statement and "IA-2(2)" in ksi.statement


def test_service_users_excluded_from_mfa_scope():
    """github-actions-deploy is tagged Type=service and should not count."""
    determinations = MFA_AGGREGATOR.determine(_ctx())
    ia_2 = next(d for d in determinations if d.control_id == "IA-2")
    # 4 okta humans + 2 aws humans = 6; service account doesn't count
    assert ia_2.metrics["total"] == 6, ia_2.metrics


def test_password_policy_meets_baseline():
    determinations = MFA_AGGREGATOR.determine(_ctx())
    ia_5_1 = next(d for d in determinations if d.control_id == "IA-5(1)")
    assert ia_5_1.status == "Implemented", ia_5_1.statement


def test_observed_at_timestamp_present():
    determinations = MFA_AGGREGATOR.determine(_ctx())
    for d in determinations:
        assert d.observed_at, f"{d.control_id} missing observed_at"
        assert "T" in d.observed_at and (d.observed_at.endswith("Z") or "+" in d.observed_at)


def test_evidence_refs_populated():
    determinations = MFA_AGGREGATOR.determine(_ctx())
    for d in determinations:
        if d.status == "Not Applicable":
            continue
        assert d.evidence_refs, f"{d.control_id} has no evidence_refs"


def test_aggregator_invariants_validated_at_capability_load():
    """The MFA capability's satisfies block must be a subset of the
    aggregator's SUPPORTED_*. Loader raises CapabilityValidationError
    if a capability references controls the aggregator doesn't cover."""
    from renderers.shared.capability_loader import load_all
    caps = load_all()
    mfa_cap = next(c for c in caps if c.id == "cap-mfa-phishing-resistant")
    assert mfa_cap.is_aggregator_backed
    aggregator = mfa_cap.load_aggregator()
    declared_controls = {e["control"] for e in mfa_cap.rev5_controls()}
    assert declared_controls.issubset(set(aggregator.SUPPORTED_CONTROLS_REV5))
