"""
Tests for tenant impersonation ("View as tenant", read-only operator support
feature): `_resolve_impersonation_start` (the pure decision logic behind
`POST /api/v1/operator/impersonation/start`) plus static source checks that
prove the required safeguards are actually wired into the route source —
admin-only, no write-through-as-tenant path, and audit logging on both
start and end.

Contract under test for `_resolve_impersonation_start`: given the looked-up
tenant row (or `None`) and whether the target account is a system admin,
decide whether impersonation may begin. No DB access here, mirroring
`compute_fleet_health` / `_resolve_scheduler_run` in this same test suite.
"""
import sys
import unittest
from pathlib import Path

# Make app importable without a running server
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.routes.operator import _resolve_impersonation_start

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class ResolveImpersonationStartTests(unittest.TestCase):
    def test_unknown_tenant_raises_404(self):
        with self.assertRaises(HTTPException) as ctx:
            _resolve_impersonation_start(None, target_is_admin=False)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_system_admin_target_raises_403_no_privilege_escalation(self):
        tenant = {"id": "tenant-1", "name": "Acme Corp", "status": "active"}
        with self.assertRaises(HTTPException) as ctx:
            _resolve_impersonation_start(tenant, target_is_admin=True)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_suspended_tenant_raises_409(self):
        tenant = {"id": "tenant-1", "name": "Acme Corp", "status": "suspended"}
        with self.assertRaises(HTTPException) as ctx:
            _resolve_impersonation_start(tenant, target_is_admin=False)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_valid_active_non_admin_tenant_resolves(self):
        tenant = {"id": "tenant-1", "name": "Acme Corp", "status": "active"}
        result = _resolve_impersonation_start(tenant, target_is_admin=False)
        self.assertEqual(result, {"tenant_id": "tenant-1", "tenant_name": "Acme Corp"})

    def test_missing_status_field_does_not_raise_409(self):
        # A tenant row without a status key (defensive) should not be treated
        # as suspended.
        tenant = {"id": "tenant-1", "name": "Acme Corp"}
        result = _resolve_impersonation_start(tenant, target_is_admin=False)
        self.assertEqual(result["tenant_id"], "tenant-1")


class ImpersonationRouteStaticTests(unittest.TestCase):
    """Source-level proofs that the required safeguards are actually wired
    into `app/routes/operator.py`, not just asserted in docstrings."""

    def setUp(self):
        self.source = read("app/routes/operator.py")

    def test_start_and_end_routes_are_admin_guarded(self):
        # Both endpoints must depend on get_system_admin, the same dependency
        # every other /operator/* route uses -- only a system admin may call them.
        start_block = self.source[
            self.source.index('@router.post("/impersonation/start")'):
            self.source.index('class EndImpersonationPayload')
        ]
        end_block = self.source[self.source.index('class EndImpersonationPayload'):]
        self.assertIn("Depends(get_system_admin)", start_block)
        self.assertIn("Depends(get_system_admin)", end_block)

    def test_start_writes_impersonation_started_audit_event(self):
        start_block = self.source[
            self.source.index('def start_impersonation('):
            self.source.index('class EndImpersonationPayload')
        ]
        self.assertIn("record_audit_event(", start_block)
        self.assertIn('action="operator.impersonation_started"', start_block)
        self.assertIn('actor_user_id=_admin.get("user_id")', start_block)

    def test_end_writes_impersonation_ended_audit_event(self):
        end_block = self.source[self.source.index('def end_impersonation('):]
        self.assertIn("record_audit_event(", end_block)
        self.assertIn('action="operator.impersonation_ended"', end_block)
        self.assertIn('actor_user_id=_admin.get("user_id")', end_block)

    def test_start_response_carries_no_token_or_credential(self):
        # The response payload must not include anything resembling a bearer
        # token, session cookie, or the tenant owner's real credentials --
        # impersonation must not be usable to authenticate as the tenant.
        start_block = self.source[
            self.source.index('def start_impersonation('):
            self.source.index('class EndImpersonationPayload')
        ]
        return_block = start_block[start_block.index("return {"):]
        forbidden_markers = ("access_token", "refresh_token", "session_token", "password", "jwt", "credential")
        lowered = return_block.lower()
        for marker in forbidden_markers:
            self.assertNotIn(marker, lowered, f"impersonation start response must not expose '{marker}'")
        self.assertIn('"read_only": True', return_block)

    def test_no_write_through_as_tenant_endpoint_exists(self):
        # Impersonation must be read-only: there must be no POST/PATCH/DELETE
        # route under /impersonation/ other than start and end themselves
        # (both of which only validate + audit, never mutate tenant data).
        impersonation_routes = [
            line.strip() for line in self.source.splitlines()
            if "/impersonation" in line and "@router." in line
        ]
        allowed = {
            '@router.post("/impersonation/start")',
            '@router.post("/impersonation/end")',
        }
        self.assertEqual(set(impersonation_routes), allowed)

    def test_start_validates_target_is_not_a_system_admin(self):
        start_block = self.source[
            self.source.index('def start_impersonation('):
            self.source.index('class EndImpersonationPayload')
        ]
        self.assertIn("system_admins", start_block)
        self.assertIn("target_is_admin", start_block)

    def test_impersonation_session_is_time_boxed(self):
        self.assertIn("IMPERSONATION_SESSION_TTL_SECONDS", self.source)
        start_block = self.source[
            self.source.index('def start_impersonation('):
            self.source.index('class EndImpersonationPayload')
        ]
        self.assertIn("expires_at", start_block)

    def test_core_tenant_dependency_is_untouched(self):
        # Impersonation must not touch get_tenant_id / get_tenant_and_role --
        # those guard every tenant-side route and widening them for operator
        # use would weaken tenant isolation for the whole app.
        tenant_deps_source = read("app/dependencies/tenant.py")
        self.assertNotIn("impersonat", tenant_deps_source.lower())


if __name__ == "__main__":
    unittest.main()
