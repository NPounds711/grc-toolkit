# Validates evidence collected by evidence/aws/iam_jit_grants.sh
# against capability cap-jit-least-privilege.
#
# Pass: no human IAM principal carries standing privileged policies.
# Privileged role assumption must be time-bounded (≤4h session) and
# the grant log must show a peer approver.

package iam.no_standing_admin

import rego.v1

# Policies considered "standing privileged" if attached directly to a human user
standing_privileged_policies := {
    "AdministratorAccess",
    "PowerUserAccess",
    "IAMFullAccess",
    "AmazonEKSClusterAdminPolicy",
}

# Max permitted session duration for elevated roles, in seconds
max_session_seconds := 14400  # 4 hours

default valid := false

valid if {
    count(violations) == 0
}

# Violation: human user has a standing privileged policy attached
violations contains msg if {
    some user in input.users
    user.type == "human"
    some attached in user.attached_policies
    attached.policy_name in standing_privileged_policies
    msg := sprintf(
        "User '%s' has standing privileged policy '%s' attached. " +
        "All privileged access must be just-in-time.",
        [user.user_name, attached.policy_name],
    )
}

# Violation: privileged role permits sessions longer than 4 hours
violations contains msg if {
    some role in input.roles
    role.privileged == true
    role.max_session_duration > max_session_seconds
    msg := sprintf(
        "Role '%s' permits %d-second sessions, exceeds 4h JIT cap.",
        [role.role_name, role.max_session_duration],
    )
}

# Violation: a grant in the JIT log lacks a peer approver
violations contains msg if {
    some grant in input.jit_grants
    not grant.approver
    msg := sprintf(
        "JIT grant '%s' to user '%s' has no approver recorded.",
        [grant.grant_id, grant.user],
    )
}

# Violation: a grant lacks a documented business justification
violations contains msg if {
    some grant in input.jit_grants
    not grant.justification
    msg := sprintf(
        "JIT grant '%s' has no business justification.",
        [grant.grant_id],
    )
}
