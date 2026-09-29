"""
Unit and integration tests for Row-Level Security (RLS) and Tenant Isolation.
Executes against the active PostgreSQL database instance.
"""
import pytest
from apps.api.tests.verify_rls_live import test_rls_suite

def test_tenant_rls_security_suite():
    """
    Executes the 6 core Gate 1 security tests:
    1. Cross-tenant Read Denial (User B cannot read User A meetings/projects/docs)
    2. Cross-tenant Update Denial (User B cannot modify User A data)
    3. Cross-tenant Delete Denial (User B cannot delete User A documents)
    4. Composite Foreign Key Enforcement (User B cannot reference User A project)
    5. User A Isolation (User A accesses only their own data)
    6. Session State Reset (RESET ALL restores clean role)
    """
    # Runs the verified live suite
    test_rls_suite()
