"""
Live Row-Level Security (RLS) and Tenant Isolation Verification Suite.
Executes against the active Supabase PostgreSQL database to prove Gate 1 security requirements:
1. Cross-tenant Read Denial (User B cannot see User A's data).
2. Cross-tenant Insert Denial (User B cannot reference User A's projects/contacts).
3. Cross-tenant Update Denial (User B cannot modify User A's meetings).
4. Cross-tenant Delete Denial (User B cannot delete User A's documents).
5. State Isolation & Leakage Prevention (SET LOCAL claim resets cleanly).
"""
import uuid
import json
import urllib.request
import os
import sys

TOKEN = os.environ.get("SUPABASE_ACCESS_TOKEN", "")
PROJECT_REF = os.environ.get("SUPABASE_PROJECT_REF", "ulqysmxopkkizydttqqp")

def run_sql(query: str):
    url = f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query"
    data = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        raise RuntimeError(f"Database Query Error: {err_msg}")

def test_rls_suite():
    print("=================================================================")
    print("RUNNING GATE 1 LIVE RLS & TENANT ISOLATION VERIFICATION SUITE")
    print("=================================================================")

    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    project_a = str(uuid.uuid4())
    meeting_a = str(uuid.uuid4())
    doc_a = str(uuid.uuid4())

    print(f"[*] Generated User A: {user_a}")
    print(f"[*] Generated User B: {user_b}")

    # 1. Setup: Seed User A and User B in auth.users and user_profiles
    setup_sql = f"""
    -- Insert into auth.users (mocking Supabase auth identities)
    INSERT INTO auth.users (id, email)
    VALUES 
        ('{user_a}', 'user_a@example.com'),
        ('{user_b}', 'user_b@example.com')
    ON CONFLICT (id) DO NOTHING;

    -- Insert into user_profiles
    INSERT INTO public.user_profiles (id, email, full_name)
    VALUES 
        ('{user_a}', 'user_a@example.com', 'User Alpha'),
        ('{user_b}', 'user_b@example.com', 'User Beta')
    ON CONFLICT (id) DO NOTHING;

    -- Seed Project and Meeting for User A
    INSERT INTO public.projects (id, user_id, name, description)
    VALUES ('{project_a}', '{user_a}', 'Confidential Alpha Project', 'Top secret strategy');

    INSERT INTO public.meetings (id, user_id, project_id, title, start_time, end_time)
    VALUES ('{meeting_a}', '{user_a}', '{project_a}', 'Alpha Strategy Review', NOW() + INTERVAL '2 hours', NOW() + INTERVAL '3 hours');

    INSERT INTO public.documents (id, user_id, filename, storage_path, file_type, file_size_bytes, sha256_checksum, processing_status)
    VALUES ('{doc_a}', '{user_a}', 'secret_doc.pdf', 'storage/docs/{doc_a}.pdf', 'pdf', 1024, 'dummy_sha256_hash_value', 'extracted');
    """
    run_sql(setup_sql)
    print("[+] Setup complete: User A seeded with project, meeting, and document.")

    # 2. Test 1: User A can see their own meeting
    test_user_a_read = f"""
    DO $$
    DECLARE
        cnt INTEGER;
    BEGIN
        SET LOCAL ROLE authenticated;
        PERFORM set_config('request.jwt.claim.sub', '{user_a}', true);
        
        SELECT COUNT(*) INTO cnt FROM public.meetings WHERE id = '{meeting_a}';
        IF cnt != 1 THEN
            RAISE EXCEPTION 'TEST FAILED: User A should see exactly 1 meeting, saw %', cnt;
        END IF;
    END $$;
    """
    run_sql(test_user_a_read)
    print("[PASS] Test 1: User A can read their own meeting.")

    # 3. Test 2: User B Cross-tenant Read Denial
    test_user_b_read = f"""
    DO $$
    DECLARE
        cnt INTEGER;
    BEGIN
        SET LOCAL ROLE authenticated;
        PERFORM set_config('request.jwt.claim.sub', '{user_b}', true);
        
        SELECT COUNT(*) INTO cnt FROM public.meetings;
        IF cnt != 0 THEN
            RAISE EXCEPTION 'SECURITY BREACH: User B read User A meetings! Saw % rows', cnt;
        END IF;

        SELECT COUNT(*) INTO cnt FROM public.projects;
        IF cnt != 0 THEN
            RAISE EXCEPTION 'SECURITY BREACH: User B read User A projects! Saw % rows', cnt;
        END IF;

        SELECT COUNT(*) INTO cnt FROM public.documents;
        IF cnt != 0 THEN
            RAISE EXCEPTION 'SECURITY BREACH: User B read User A documents! Saw % rows', cnt;
        END IF;
    END $$;
    """
    run_sql(test_user_b_read)
    print("[PASS] Test 2: User B cannot read User A's meetings, projects, or documents.")

    # 4. Test 3: User B Cross-tenant Update Denial
    test_user_b_update = f"""
    DO $$
    DECLARE
        rows_affected INTEGER;
    BEGIN
        SET LOCAL ROLE authenticated;
        PERFORM set_config('request.jwt.claim.sub', '{user_b}', true);
        
        UPDATE public.meetings SET title = 'HACKED TITLE' WHERE id = '{meeting_a}';
        GET DIAGNOSTICS rows_affected = ROW_COUNT;
        
        IF rows_affected != 0 THEN
            RAISE EXCEPTION 'SECURITY BREACH: User B modified User A meeting! Updated % rows', rows_affected;
        END IF;
    END $$;
    """
    run_sql(test_user_b_update)
    print("[PASS] Test 3: User B cannot update User A's meeting (0 rows affected).")

    # 5. Test 4: User B Cross-tenant Delete Denial
    test_user_b_delete = f"""
    DO $$
    DECLARE
        rows_affected INTEGER;
    BEGIN
        SET LOCAL ROLE authenticated;
        PERFORM set_config('request.jwt.claim.sub', '{user_b}', true);
        
        DELETE FROM public.documents WHERE id = '{doc_a}';
        GET DIAGNOSTICS rows_affected = ROW_COUNT;
        
        IF rows_affected != 0 THEN
            RAISE EXCEPTION 'SECURITY BREACH: User B deleted User A document! Deleted % rows', rows_affected;
        END IF;
    END $$;
    """
    run_sql(test_user_b_delete)
    print("[PASS] Test 4: User B cannot delete User A's document (0 rows affected).")

    # 6. Test 5: Cross-tenant Insert Denial via Composite FK
    # User B attempts to create a meeting linked to User A's project
    test_user_b_fk_tampering = f"""
    DO $$
    BEGIN
        SET LOCAL ROLE authenticated;
        PERFORM set_config('request.jwt.claim.sub', '{user_b}', true);
        
        BEGIN
            INSERT INTO public.meetings (user_id, project_id, title, start_time, end_time)
            VALUES ('{user_b}', '{project_a}', 'Malicious Link Meeting', NOW() + INTERVAL '1 hour', NOW() + INTERVAL '2 hours');
            
            RAISE EXCEPTION 'SECURITY BREACH: User B linked meeting to User A project without FK error!';
        EXCEPTION 
            WHEN foreign_key_violation THEN
                -- Expected behavior: composite FK (project_id, user_id) blocked the cross-tenant link!
                RAISE NOTICE 'Foreign key violation caught as expected.';
        END;
    END $$;
    """
    run_sql(test_user_b_fk_tampering)
    print("[PASS] Test 5: Composite Foreign Key correctly blocked User B from referencing User A's project.")

    # 7. Test 6: Verify Clean State Reset
    test_reset_isolation = f"""
    DO $$
    DECLARE
        curr_role TEXT;
    BEGIN
        RESET ALL;
        SELECT current_user INTO curr_role;
        IF curr_role != 'postgres' THEN
            RAISE EXCEPTION 'RESET ALL failed to restore postgres role, current: %', curr_role;
        END IF;
    END $$;
    """
    run_sql(test_reset_isolation)
    print("[PASS] Test 6: RESET ALL restores connection to clean administrative state.")

    # Cleanup test data
    cleanup_sql = f"""
    DELETE FROM public.user_profiles WHERE id IN ('{user_a}', '{user_b}');
    DELETE FROM auth.users WHERE id IN ('{user_a}', '{user_b}');
    """
    run_sql(cleanup_sql)
    print("[+] Test teardown: Test users and relational cascades cleaned up cleanly.")
    print("=================================================================")
    print("ALL GATE 1 TENANT ISOLATION TESTS PASSED WITH 100% SUCCESS!")
    print("=================================================================")

if __name__ == "__main__":
    test_rls_suite()
