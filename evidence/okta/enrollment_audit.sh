#!/usr/bin/env bash
# Evidence collector: monthly Okta MFA enrollment audit.
# Referenced by capabilities/iam/mfa-phishing-resistant.yaml (ev-okta-enrollment-audit).
#
# Output: JSON file in $OUTPUT_DIR/okta_mfa_enrollment.json listing every
# active user with their enrolled MFA factors. Downstream validation_rule
# (from the capability YAML) confirms 100% WebAuthn enrollment.

set -euo pipefail

OUTPUT_DIR="${1:?usage: $0 <output_dir>}"
OKTA_DOMAIN="${OKTA_DOMAIN:?OKTA_DOMAIN env var required}"
OKTA_TOKEN="${OKTA_API_TOKEN:?OKTA_API_TOKEN env var required}"

mkdir -p "$OUTPUT_DIR"

# Paginate through active users. Okta returns 200 per page by default.
NEXT_URL="https://${OKTA_DOMAIN}/api/v1/users?filter=status%20eq%20%22ACTIVE%22&limit=200"
USERS_FILE="$OUTPUT_DIR/.okta_users.tmp.json"
echo "[]" > "$USERS_FILE"

while [ -n "$NEXT_URL" ]; do
  RESP_HEADERS="$(mktemp)"
  curl -sS -D "$RESP_HEADERS" \
       -H "Authorization: SSWS $OKTA_TOKEN" \
       -H "Accept: application/json" \
       "$NEXT_URL" \
    | jq --slurpfile prev "$USERS_FILE" '$prev[0] + .' \
    > "$USERS_FILE.next"
  mv "$USERS_FILE.next" "$USERS_FILE"

  # Parse the Link header for the rel="next" page, if any
  NEXT_URL="$(grep -i '^link:' "$RESP_HEADERS" \
              | grep -oE '<[^>]+>; rel="next"' \
              | head -1 \
              | sed -E 's/^<([^>]+)>.*/\1/' \
              || true)"
  rm -f "$RESP_HEADERS"
done

# For each user, hydrate their enrolled factors. Sequential to stay
# well below Okta's API rate limit.
jq -c '.[]' "$USERS_FILE" | while read -r user; do
  user_id="$(echo "$user" | jq -r '.id')"
  factors="$(curl -sS \
    -H "Authorization: SSWS $OKTA_TOKEN" \
    -H "Accept: application/json" \
    "https://${OKTA_DOMAIN}/api/v1/users/${user_id}/factors")"
  echo "$user" | jq --argjson f "$factors" '. + {factors: $f}'
done | jq -s '{users: .}' > "$OUTPUT_DIR/okta_mfa_enrollment.json"

rm -f "$USERS_FILE"

# Metadata sidecar
cat > "$OUTPUT_DIR/okta_mfa_enrollment.metadata.json" <<EOF
{
  "evidenceId": "ev-okta-enrollment-audit",
  "collectedAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "source": "okta",
  "domain": "$OKTA_DOMAIN",
  "collector": "$(basename "$0")",
  "schemaVersion": "1.0",
  "userCount": $(jq '.users | length' "$OUTPUT_DIR/okta_mfa_enrollment.json")
}
EOF

echo "Wrote $OUTPUT_DIR/okta_mfa_enrollment.json"
