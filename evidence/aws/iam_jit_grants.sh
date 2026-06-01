#!/usr/bin/env bash
# Evidence collector: AWS IAM standing/JIT grant audit.
# Referenced by capabilities/iam/jit-least-privilege.yaml (ev-pam-grant-log).
#
# Captures:
#   1. All human IAM users + their directly-attached managed policies
#   2. All IAM roles with their max-session-duration (to flag >4h on
#      privileged roles)
#   3. CloudTrail AssumeRole events for the past 24h that targeted any
#      role tagged Privileged=true — these become the JIT grant log
#
# Output: JSON consumed by policies/iam/no-standing-admin.rego.

set -euo pipefail

OUTPUT_DIR="${1:?usage: $0 <output_dir>}"
LOOKBACK_HOURS="${LOOKBACK_HOURS:-24}"

mkdir -p "$OUTPUT_DIR"

# Validate AWS auth before doing real work
aws sts get-caller-identity > /dev/null

# --- Users + directly-attached policies ---
echo "Collecting IAM users..."
USERS_RAW="$(aws iam list-users --output json)"
USERS_ENRICHED="[]"
for user in $(echo "$USERS_RAW" | jq -r '.Users[].UserName'); do
  policies="$(aws iam list-attached-user-policies --user-name "$user" --output json \
                | jq '.AttachedPolicies | map({policy_name: .PolicyName, policy_arn: .PolicyArn})')"
  tags="$(aws iam list-user-tags --user-name "$user" --output json \
            | jq '.Tags // []')"
  # Treat a user as "human" unless explicitly tagged Type=service
  is_human="true"
  if echo "$tags" | jq -e '.[] | select(.Key == "Type" and .Value == "service")' > /dev/null; then
    is_human="false"
  fi
  USERS_ENRICHED="$(echo "$USERS_ENRICHED" | jq \
    --arg name "$user" \
    --argjson policies "$policies" \
    --argjson human "$is_human" \
    '. + [{user_name: $name, type: ($human | if . then "human" else "service" end), attached_policies: $policies}]')"
done

# --- Roles + max-session-duration ---
echo "Collecting IAM roles..."
ROLES_RAW="$(aws iam list-roles --output json)"
ROLES_ENRICHED="$(echo "$ROLES_RAW" | jq '
  .Roles | map({
    role_name: .RoleName,
    role_arn: .Arn,
    max_session_duration: .MaxSessionDuration,
    privileged: (.Tags // []) | any(.Key == "Privileged" and .Value == "true")
  })
')"

# --- JIT grant log: CloudTrail AssumeRole events ---
echo "Collecting CloudTrail AssumeRole events for last ${LOOKBACK_HOURS}h..."
START_TIME="$(date -u -v-"${LOOKBACK_HOURS}"H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
             || date -u --date="${LOOKBACK_HOURS} hours ago" +%Y-%m-%dT%H:%M:%SZ)"

GRANTS="$(aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRole \
  --start-time "$START_TIME" \
  --output json \
  | jq '[.Events[] | {
      grant_id: .EventId,
      user: (.Username // "unknown"),
      role: (.Resources // [] | map(select(.ResourceType == "AWS::IAM::Role") | .ResourceName) | first),
      time: .EventTime,
      approver: ((.CloudTrailEvent | fromjson).requestParameters.tags // [] | map(select(.key == "approver") | .value) | first),
      justification: ((.CloudTrailEvent | fromjson).requestParameters.tags // [] | map(select(.key == "justification") | .value) | first)
    }]')"

# --- Assemble final document ---
jq -n \
  --argjson users "$USERS_ENRICHED" \
  --argjson roles "$ROLES_ENRICHED" \
  --argjson grants "$GRANTS" \
  '{users: $users, roles: $roles, jit_grants: $grants}' \
  > "$OUTPUT_DIR/aws_iam_jit_grants.json"

# Metadata sidecar
cat > "$OUTPUT_DIR/aws_iam_jit_grants.metadata.json" <<EOF
{
  "evidenceId": "ev-pam-grant-log",
  "collectedAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "source": "aws",
  "account": "$(aws sts get-caller-identity --query Account --output text)",
  "region": "${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}",
  "lookbackHours": ${LOOKBACK_HOURS},
  "collector": "$(basename "$0")",
  "schemaVersion": "1.0"
}
EOF

echo "Wrote $OUTPUT_DIR/aws_iam_jit_grants.json"
