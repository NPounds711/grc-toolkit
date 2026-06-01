"""
AWS IAM connector. Returns raw IAM state — users, roles, account summary.

Real implementation uses boto3 (added to requirements). Fixture mode reads
JSON files for tests/demos.

Aggregators decide what counts as compliant; this connector just reports.
"""

from __future__ import annotations

from typing import Any

from connectors._base import BaseConnector, ConnectorError


class AwsIamConnector(BaseConnector):
    CONNECTOR_ID = "aws_iam"
    FIXTURE_FILES = [
        "users.json",
        "roles.json",
        "account_summary.json",
        "account_password_policy.json",
    ]

    def _client(self):
        try:
            import boto3
        except ImportError as e:
            raise ConnectorError(
                "boto3 not installed. Either pip install boto3 or run with "
                "fixture_mode=True for testing/demo."
            ) from e
        return boto3.client("iam")

    def list_users(self) -> list[dict]:
        if self.ctx.fixture_mode:
            return self.fixture("users.json")["users"]
        iam = self._client()
        users: list[dict] = []
        paginator = iam.get_paginator("list_users")
        for page in paginator.paginate():
            for user in page["Users"]:
                user["MFADevices"] = iam.list_mfa_devices(UserName=user["UserName"])["MFADevices"]
                user["AttachedPolicies"] = iam.list_attached_user_policies(
                    UserName=user["UserName"]
                )["AttachedPolicies"]
                users.append(user)
        return users

    def list_roles(self) -> list[dict]:
        if self.ctx.fixture_mode:
            return self.fixture("roles.json")["roles"]
        iam = self._client()
        roles: list[dict] = []
        paginator = iam.get_paginator("list_roles")
        for page in paginator.paginate():
            roles.extend(page["Roles"])
        return roles

    def account_summary(self) -> dict:
        if self.ctx.fixture_mode:
            return self.fixture("account_summary.json")
        return self._client().get_account_summary()["SummaryMap"]

    def password_policy(self) -> dict:
        if self.ctx.fixture_mode:
            return self.fixture("account_password_policy.json")
        try:
            return self._client().get_account_password_policy()["PasswordPolicy"]
        except Exception:
            return {}
