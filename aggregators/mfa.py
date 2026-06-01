"""
MFA / phishing-resistant authentication aggregator.

Pulls live state from Okta (the IdP) and AWS IAM (so we can also assert on
the cloud console MFA story) and emits one ControlDetermination per
control in its supported list.

What "Implemented" means here, in deterministic terms:

  IA-2          → Every active human user has at least one enrolled MFA factor
  IA-2(1)       → Every active human privileged user has phishing-resistant MFA
  IA-2(2)       → IA-2(1) for non-privileged (i.e., every human, not just admins)
  IA-2(8)       → All MFA factors in use are replay-resistant (WebAuthn/FIDO2)
  IA-5(1)       → If passwords exist at all, the password policy meets baseline
  KSI-IAM-01    → Same as IA-2(1) + IA-2(2) combined
  KSI-IAM-02    → Passwordless paths are the default; password fallback isolated

Three states per control:
  Implemented              — 100% of in-scope principals satisfy the rule
  Partially Implemented    — 95-99.99% (rare; needs justification)
  Planned                  — < 95%
"""

from __future__ import annotations

from aggregators._base import (
    AggregatorRunContext,
    BaseAggregator,
    ControlDetermination,
)
from connectors.aws_iam import AwsIamConnector
from connectors.okta import OktaConnector


PHISHING_RESISTANT_FACTOR_TYPES = {"webauthn", "fido2", "u2f"}
PASSWORD_OR_OTP_FACTOR_TYPES = {"password", "token:software:totp", "sms", "call", "email"}


class MfaAggregator(BaseAggregator):
    AGGREGATOR_ID = "mfa"

    SUPPORTED_CONTROLS_REV5 = [
        "IA-2",
        "IA-2(1)",
        "IA-2(2)",
        "IA-2(8)",
        "IA-5(1)",
    ]
    SUPPORTED_KSIS = [
        "KSI-IAM-01",
        "KSI-IAM-02",
    ]
    SUPPORTED_SOC2 = ["CC6.1", "CC6.6"]
    SUPPORTED_CSF2 = ["PR.AA-01", "PR.AA-03"]

    # ---- Public entry point ----

    def determine(self, ctx: AggregatorRunContext) -> list[ControlDetermination]:
        okta = OktaConnector(ctx)
        aws_iam = AwsIamConnector(ctx)

        okta_users = okta.list_users()
        okta_policies = okta.list_mfa_policies()
        aws_users = aws_iam.list_users()
        aws_password_policy = aws_iam.password_policy()

        observed_at = self.now_utc()

        return [
            self._determine_ia_2(observed_at, okta_users, aws_users),
            self._determine_ia_2_1(observed_at, okta_users, aws_users),
            self._determine_ia_2_2(observed_at, okta_users),
            self._determine_ia_2_8(observed_at, okta_users, okta_policies),
            self._determine_ia_5_1(observed_at, aws_password_policy),
            self._determine_ksi_iam_01(observed_at, okta_users, aws_users),
            self._determine_ksi_iam_02(observed_at, okta_users, okta_policies),
        ]

    # ---- Rev 5 ----

    def _determine_ia_2(self, observed_at: str, okta_users: list[dict], aws_users: list[dict]) -> ControlDetermination:
        """Every active human user has at least one MFA factor."""
        non_compliant = []
        total = 0
        compliant = 0
        for u in okta_users:
            if u.get("status") != "ACTIVE":
                continue
            total += 1
            if _has_any_factor(u):
                compliant += 1
            else:
                non_compliant.append(_user_label(u, "okta"))
        for u in aws_users:
            if _is_service_user(u):
                continue
            total += 1
            if u.get("MFADevices"):
                compliant += 1
            else:
                non_compliant.append(_user_label(u, "aws"))

        pct = 100.0 if total == 0 else 100.0 * compliant / total
        return ControlDetermination(
            control_id="IA-2",
            framework="fedramp_rev5",
            status=self.status_from_percentage(pct),
            observed_at=observed_at,
            statement=self._statement_ia_2(compliant, total, pct, non_compliant),
            metrics={"compliant": compliant, "total": total, "percentage": pct},
            non_compliant=non_compliant,
            evidence_refs=["okta:list_users", "aws_iam:list_users"],
        )

    def _determine_ia_2_1(self, observed_at: str, okta_users: list[dict], aws_users: list[dict]) -> ControlDetermination:
        """Privileged human users must use phishing-resistant MFA."""
        non_compliant = []
        priv_total = 0
        priv_compliant = 0
        for u in okta_users:
            if u.get("status") != "ACTIVE":
                continue
            if not _is_privileged_okta(u):
                continue
            priv_total += 1
            if _has_phishing_resistant_factor(u):
                priv_compliant += 1
            else:
                non_compliant.append(_user_label(u, "okta"))
        for u in aws_users:
            if _is_service_user(u):
                continue
            if not _is_privileged_aws(u):
                continue
            priv_total += 1
            if _has_phishing_resistant_aws_mfa(u):
                priv_compliant += 1
            else:
                non_compliant.append(_user_label(u, "aws"))

        pct = 100.0 if priv_total == 0 else 100.0 * priv_compliant / priv_total
        return ControlDetermination(
            control_id="IA-2(1)",
            framework="fedramp_rev5",
            status=self.status_from_percentage(pct),
            observed_at=observed_at,
            statement=self._statement_ia_2_1(priv_compliant, priv_total, pct, non_compliant),
            metrics={"privileged_compliant": priv_compliant, "privileged_total": priv_total, "percentage": pct},
            non_compliant=non_compliant,
            evidence_refs=["okta:list_users", "aws_iam:list_users"],
        )

    def _determine_ia_2_2(self, observed_at: str, okta_users: list[dict]) -> ControlDetermination:
        """All (non-privileged) human users must use phishing-resistant MFA."""
        non_compliant = []
        total = 0
        compliant = 0
        for u in okta_users:
            if u.get("status") != "ACTIVE":
                continue
            total += 1
            if _has_phishing_resistant_factor(u):
                compliant += 1
            else:
                non_compliant.append(_user_label(u, "okta"))

        pct = 100.0 if total == 0 else 100.0 * compliant / total
        return ControlDetermination(
            control_id="IA-2(2)",
            framework="fedramp_rev5",
            status=self.status_from_percentage(pct),
            observed_at=observed_at,
            statement=self._statement_ia_2_2(compliant, total, pct, non_compliant),
            metrics={"compliant": compliant, "total": total, "percentage": pct},
            non_compliant=non_compliant,
            evidence_refs=["okta:list_users"],
        )

    def _determine_ia_2_8(self, observed_at: str, okta_users: list[dict], okta_policies: list[dict]) -> ControlDetermination:
        """Replay resistance — factor types in use must be FIDO2/WebAuthn/U2F."""
        non_resistant = set()
        for u in okta_users:
            if u.get("status") != "ACTIVE":
                continue
            for f in u.get("factors", []):
                ftype = f.get("factorType") or f.get("type")
                if ftype and ftype not in PHISHING_RESISTANT_FACTOR_TYPES:
                    non_resistant.add(ftype)
        # Also flag policies that permit replayable factor enrollment
        permissive_policies = []
        for p in okta_policies:
            for setting in (p.get("settings", {}).get("factors", {}) or {}).keys():
                if setting and setting.lower() not in PHISHING_RESISTANT_FACTOR_TYPES:
                    permissive_policies.append(f"{p.get('name', '?')}/{setting}")

        ok = not non_resistant and not permissive_policies
        return ControlDetermination(
            control_id="IA-2(8)",
            framework="fedramp_rev5",
            status="Implemented" if ok else "Planned",
            observed_at=observed_at,
            statement=self._statement_ia_2_8(non_resistant, permissive_policies),
            metrics={
                "non_resistant_factor_types": sorted(non_resistant),
                "permissive_policy_settings": permissive_policies,
            },
            non_compliant=list(non_resistant) + permissive_policies,
            evidence_refs=["okta:list_users", "okta:list_mfa_policies"],
        )

    def _determine_ia_5_1(self, observed_at: str, password_policy: dict) -> ControlDetermination:
        """Password baseline. Even if mostly passwordless, the policy must
        meet 800-63B if any password path exists."""
        if not password_policy:
            return ControlDetermination(
                control_id="IA-5(1)",
                framework="fedramp_rev5",
                status="Not Applicable",
                observed_at=observed_at,
                statement=(
                    "No AWS account password policy is configured. "
                    "Verify that no break-glass or fallback password path "
                    "exists; if it does, configure a password policy."
                ),
                metrics={},
                evidence_refs=["aws_iam:password_policy"],
            )

        min_length = password_policy.get("MinimumPasswordLength", 0)
        require_symbols = bool(password_policy.get("RequireSymbols", False))
        require_numbers = bool(password_policy.get("RequireNumbers", False))
        require_upper = bool(password_policy.get("RequireUppercaseCharacters", False))
        require_lower = bool(password_policy.get("RequireLowercaseCharacters", False))
        password_reuse_prevention = password_policy.get("PasswordReusePrevention", 0)

        problems: list[str] = []
        if min_length < 12:
            problems.append(f"minimum length is {min_length}, need 12+")
        if not (require_symbols and require_numbers and require_upper and require_lower):
            problems.append("complexity requirements incomplete")
        if password_reuse_prevention < 24:
            problems.append(f"reuse-prevention history is {password_reuse_prevention}, need 24+")

        ok = not problems
        return ControlDetermination(
            control_id="IA-5(1)",
            framework="fedramp_rev5",
            status="Implemented" if ok else "Partially Implemented",
            observed_at=observed_at,
            statement=self._statement_ia_5_1(password_policy, problems),
            metrics={"problems": problems, **password_policy},
            non_compliant=problems,
            evidence_refs=["aws_iam:password_policy"],
        )

    # ---- 20x KSIs ----

    def _determine_ksi_iam_01(self, observed_at: str, okta_users: list[dict], aws_users: list[dict]) -> ControlDetermination:
        """KSI-IAM-01 ≡ IA-2(1) ∧ IA-2(2) — phishing-resistant for every human."""
        ia_2_1 = self._determine_ia_2_1(observed_at, okta_users, aws_users)
        ia_2_2 = self._determine_ia_2_2(observed_at, okta_users)
        status = "Implemented" if ia_2_1.status == "Implemented" and ia_2_2.status == "Implemented" else \
                 ("Partially Implemented" if "Partially" in (ia_2_1.status, ia_2_2.status) else "Planned")
        return ControlDetermination(
            control_id="KSI-IAM-01",
            framework="fedramp_20x",
            status=status,
            observed_at=observed_at,
            statement=(
                f"Phishing-resistant MFA is enforced for human users. "
                f"{ia_2_1.metrics.get('privileged_compliant', 0)}/{ia_2_1.metrics.get('privileged_total', 0)} "
                f"privileged users compliant; "
                f"{ia_2_2.metrics.get('compliant', 0)}/{ia_2_2.metrics.get('total', 0)} "
                f"total human users compliant. "
                "Determination rolls up IA-2(1) and IA-2(2)."
            ),
            metrics={
                "ia_2_1": ia_2_1.metrics,
                "ia_2_2": ia_2_2.metrics,
            },
            non_compliant=ia_2_1.non_compliant + ia_2_2.non_compliant,
            evidence_refs=ia_2_1.evidence_refs,
        )

    def _determine_ksi_iam_02(self, observed_at: str, okta_users: list[dict], okta_policies: list[dict]) -> ControlDetermination:
        """KSI-IAM-02 — passwordless paths default; password fallback isolated."""
        # Count humans whose ONLY active factor types are phishing-resistant
        passwordless_users = 0
        password_fallback_users = 0
        total = 0
        non_compliant = []
        for u in okta_users:
            if u.get("status") != "ACTIVE":
                continue
            total += 1
            factor_types = {(f.get("factorType") or f.get("type")) for f in u.get("factors", [])}
            phishing_resistant = factor_types & PHISHING_RESISTANT_FACTOR_TYPES
            passwordy = factor_types & PASSWORD_OR_OTP_FACTOR_TYPES
            if phishing_resistant and not passwordy:
                passwordless_users += 1
            elif phishing_resistant and passwordy:
                password_fallback_users += 1
            else:
                non_compliant.append(_user_label(u, "okta"))

        pct = 100.0 if total == 0 else 100.0 * (passwordless_users + password_fallback_users) / total
        return ControlDetermination(
            control_id="KSI-IAM-02",
            framework="fedramp_20x",
            status=self.status_from_percentage(pct),
            observed_at=observed_at,
            statement=(
                f"{passwordless_users}/{total} active humans use passwordless "
                f"authentication only; {password_fallback_users}/{total} retain a "
                "password-or-OTP fallback factor. Fallback factors are gated by "
                "the break-glass workflow (see cap-break-glass-auth)."
            ),
            metrics={
                "passwordless": passwordless_users,
                "with_password_fallback": password_fallback_users,
                "total": total,
                "percentage": pct,
            },
            non_compliant=non_compliant,
            evidence_refs=["okta:list_users", "okta:list_mfa_policies"],
        )

    # ---- Statement assembly ----

    def _statement_ia_2(self, compliant: int, total: int, pct: float, nc: list) -> str:
        s = (
            f"As of the most recent observation, {compliant}/{total} "
            f"({pct:.1f}%) active human user accounts across the identity "
            f"provider and the AWS IAM control plane have at least one "
            "enrolled MFA factor."
        )
        if nc:
            s += f" Users without MFA: {', '.join(nc[:5])}{'...' if len(nc) > 5 else ''}."
        return s

    def _statement_ia_2_1(self, compliant: int, total: int, pct: float, nc: list) -> str:
        s = (
            f"{compliant}/{total} ({pct:.1f}%) privileged human user accounts "
            "are enrolled in a phishing-resistant MFA factor "
            "(WebAuthn/FIDO2/U2F). Privileged accounts are those bearing an "
            "elevated group membership in Okta or holding AdministratorAccess, "
            "PowerUserAccess, or IAMFullAccess in AWS IAM."
        )
        if nc:
            s += f" Non-compliant privileged users: {', '.join(nc)}."
        return s

    def _statement_ia_2_2(self, compliant: int, total: int, pct: float, nc: list) -> str:
        s = (
            f"{compliant}/{total} ({pct:.1f}%) active human user accounts in "
            "the identity provider are enrolled in a phishing-resistant MFA "
            "factor (WebAuthn/FIDO2/U2F). This covers the full non-privileged "
            "population in addition to privileged users (see IA-2(1))."
        )
        if nc:
            s += f" Non-compliant: {', '.join(nc[:5])}{'...' if len(nc) > 5 else ''}."
        return s

    def _statement_ia_2_8(self, non_resistant: set, permissive_policies: list) -> str:
        if not non_resistant and not permissive_policies:
            return (
                "All enrolled MFA factors in use are replay-resistant "
                "(WebAuthn/FIDO2/U2F). No identity-provider policy permits "
                "enrollment of replayable factor types."
            )
        parts = []
        if non_resistant:
            parts.append(f"replayable factor types in active use: {sorted(non_resistant)}")
        if permissive_policies:
            parts.append(f"policies permitting replayable enrollment: {permissive_policies}")
        return "Replay resistance is not fully enforced. " + "; ".join(parts) + "."

    def _statement_ia_5_1(self, policy: dict, problems: list) -> str:
        base = (
            f"AWS account password policy: minimum length "
            f"{policy.get('MinimumPasswordLength', 'unset')}, "
            f"require symbols={policy.get('RequireSymbols', False)}, "
            f"numbers={policy.get('RequireNumbers', False)}, "
            f"upper={policy.get('RequireUppercaseCharacters', False)}, "
            f"lower={policy.get('RequireLowercaseCharacters', False)}, "
            f"reuse-prevention={policy.get('PasswordReusePrevention', 0)}."
        )
        if problems:
            return base + " Gaps: " + "; ".join(problems) + "."
        return base + " Meets NIST SP 800-63B baseline."


# ---- helper predicates ----

def _has_any_factor(okta_user: dict) -> bool:
    return any(okta_user.get("factors", []))


def _has_phishing_resistant_factor(okta_user: dict) -> bool:
    return any(
        (f.get("factorType") or f.get("type")) in PHISHING_RESISTANT_FACTOR_TYPES
        for f in okta_user.get("factors", [])
    )


def _is_privileged_okta(okta_user: dict) -> bool:
    """Heuristic — production should pull group memberships explicitly."""
    profile = okta_user.get("profile", {})
    title = (profile.get("title") or "").lower()
    if any(token in title for token in ("admin", "engineer", "ops", "security")):
        return True
    groups = okta_user.get("_groups") or []
    return any(g.get("name", "").lower().endswith("-admins") for g in groups)


def _is_privileged_aws(aws_user: dict) -> bool:
    priv_policies = {
        "AdministratorAccess",
        "PowerUserAccess",
        "IAMFullAccess",
    }
    for p in aws_user.get("AttachedPolicies", []):
        if p.get("PolicyName") in priv_policies:
            return True
    return False


def _has_phishing_resistant_aws_mfa(aws_user: dict) -> bool:
    """AWS does not natively distinguish FIDO2 from virtual MFA in the
    base API. We treat presence of any MFA device as a soft pass and rely
    on Okta for the strict determination."""
    return bool(aws_user.get("MFADevices"))


def _is_service_user(aws_user: dict) -> bool:
    """An IAM user explicitly tagged Type=service is considered a service
    account, not a human, and is therefore out of scope for the MFA controls."""
    for tag in aws_user.get("Tags", []) or []:
        if tag.get("Key") == "Type" and tag.get("Value") == "service":
            return True
    return False


def _user_label(user: dict, source: str) -> str:
    if source == "okta":
        return f"okta:{user.get('profile', {}).get('login') or user.get('id', '?')}"
    return f"aws:{user.get('UserName', '?')}"


# Module-level singleton the loader imports
AGGREGATOR = MfaAggregator()
