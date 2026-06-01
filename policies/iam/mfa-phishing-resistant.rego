# Validates the evidence collected by evidence/okta/mfa_policy_export.sh
# against capability cap-mfa-phishing-resistant.
#
# Pass: every active MFA enrollment policy lists only phishing-resistant
# factors (webauthn, fido2). No fallback to SMS, voice, or push.

package iam.mfa_phishing_resistant

import rego.v1

# Phishing-resistant factor types per NIST SP 800-63B AAL3
phishing_resistant := {"webauthn", "fido2"}

# Factors that explicitly fail this capability
forbidden := {"sms", "call", "push", "question"}

default valid := false

valid if {
    count(violations) == 0
    count(active_policies) > 0
}

active_policies contains policy if {
    some policy in input
    policy.status == "ACTIVE"
}

violations contains msg if {
    some policy in active_policies
    some setting in policy.settings.factors
    setting.consent.type != "NONE"
    not setting.factor in phishing_resistant
    msg := sprintf("Policy '%s' permits non-phishing-resistant factor '%s'",
                   [policy.name, setting.factor])
}

violations contains msg if {
    some policy in active_policies
    some setting in policy.settings.factors
    setting.factor in forbidden
    setting.consent.enroll != "NOT_ALLOWED"
    msg := sprintf("Policy '%s' allows forbidden factor '%s'",
                   [policy.name, setting.factor])
}
