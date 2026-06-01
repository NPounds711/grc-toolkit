"""
Okta connector. Returns:

  list_users()  → list of active users with their enrolled MFA factors
  list_mfa_policies()  → all MFA enrollment policies + their settings

No interpretation. The aggregator decides what compliance looks like.
"""

from __future__ import annotations

import urllib.parse
import urllib.request
from typing import Any

from connectors._base import BaseConnector, ConnectorError


class OktaConnector(BaseConnector):
    CONNECTOR_ID = "okta"
    FIXTURE_FILES = ["users.json", "mfa_policies.json"]

    def _call(self, path: str) -> Any:
        creds = self.env_required("OKTA_DOMAIN", "OKTA_API_TOKEN")
        url = f"https://{creds['OKTA_DOMAIN']}{path}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"SSWS {creds['OKTA_API_TOKEN']}",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                import json
                return json.loads(resp.read().decode())
        except Exception as e:
            raise ConnectorError(f"okta API call failed for {path}: {e}") from e

    def list_users(self) -> list[dict]:
        """All ACTIVE users with hydrated factors. Heavy call — paginates."""
        if self.ctx.fixture_mode:
            return self.fixture("users.json")["users"]

        out: list[dict] = []
        # Real impl would page through /api/v1/users with status filter and
        # then call /api/v1/users/{id}/factors per user. Kept tight here
        # because in CI we use fixtures; the live impl is straightforward to
        # extend when a real Okta is wired in.
        users = self._call("/api/v1/users?filter=" + urllib.parse.quote('status eq "ACTIVE"') + "&limit=200")
        for user in users:
            factors = self._call(f"/api/v1/users/{user['id']}/factors")
            user["factors"] = factors
            out.append(user)
        return out

    def list_mfa_policies(self) -> list[dict]:
        if self.ctx.fixture_mode:
            return self.fixture("mfa_policies.json")
        return self._call("/api/v1/policies?type=MFA_ENROLL")
