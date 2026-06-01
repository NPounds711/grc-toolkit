#!/usr/bin/env bash
# Evidence collector: Okta MFA policy export.
# Referenced by capabilities/iam/mfa-phishing-resistant.yaml (ev-okta-mfa-policy-export).
#
# Output: JSON file in $OUTPUT_DIR/okta_mfa_policy.json containing all
# active MFA enrollment policies. Downstream validation_rule (from the
# capability YAML) determines pass/fail.

set -euo pipefail

OUTPUT_DIR="${1:?usage: $0 <output_dir>}"
OKTA_DOMAIN="${OKTA_DOMAIN:?OKTA_DOMAIN env var required}"
OKTA_TOKEN="${OKTA_API_TOKEN:?OKTA_API_TOKEN env var required}"

mkdir -p "$OUTPUT_DIR"

# Pull MFA enrollment policies
curl -sS -H "Authorization: SSWS $OKTA_TOKEN" \
     -H "Accept: application/json" \
     "https://${OKTA_DOMAIN}/api/v1/policies?type=MFA_ENROLL" \
     | jq '.' \
     > "$OUTPUT_DIR/okta_mfa_policy.json"

# Emit a small metadata file so the renderer can cite collection time
cat > "$OUTPUT_DIR/okta_mfa_policy.metadata.json" <<EOF
{
  "evidenceId": "ev-okta-mfa-policy-export",
  "collectedAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "source": "okta",
  "domain": "$OKTA_DOMAIN",
  "collector": "$(basename "$0")",
  "schemaVersion": "1.0"
}
EOF

echo "Wrote $OUTPUT_DIR/okta_mfa_policy.json"
