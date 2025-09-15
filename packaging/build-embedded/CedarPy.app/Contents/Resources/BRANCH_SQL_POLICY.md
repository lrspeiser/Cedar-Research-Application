# Branch-Aware SQL Policy (STRICT EXPLICIT-ONLY)

Summary
- No automatic injection or rewriting of SQL statements.
- If a table includes project_id and branch_id columns, every mutating SQL must explicitly scope to the correct project and branch.
- This ensures deterministic behavior and avoids accidental cross-branch writes.

Rules
1) INSERT into a branch-aware table MUST include project_id and branch_id columns explicitly in the column list.
   Example (OK):
   INSERT INTO threads (id, project_id, branch_id, title) VALUES (123, 7, 42, 'hello');
   Example (Rejected):
   INSERT INTO threads (id, title) VALUES (123, 'hello');

2) UPDATE and DELETE on a branch-aware table MUST include a WHERE clause that references BOTH project_id and branch_id.
   Example (OK):
   UPDATE threads SET title = 't' WHERE id = 123 AND project_id = 7 AND branch_id = 42;
   DELETE FROM threads WHERE id = 123 AND project_id = 7 AND branch_id = 42;
   Example (Rejected):
   UPDATE threads SET title = 't' WHERE id = 123;   -- missing project_id/branch_id
   DELETE FROM threads WHERE id = 123;              -- missing project_id/branch_id

3) SELECT and CREATE are executed as-is (no auto-filter). You must write the appropriate filters yourself as needed.

Error messages you may see
- Strict branch policy: INSERT into '<table>' must explicitly include columns: project_id, branch_id.
- Strict branch policy: UPDATE/DELETE on '<table>' must include WHERE with both project_id and branch_id.
- Strict branch policy check failed: <details>

FAQ
- Why not auto-inject? We want fully deterministic SQL without magic.
- How do I find my current branch_id? The UI shows it in the project URL query (branch_id=...), and SELECT queries on branches can retrieve IDs.
- What if a table has no branch columns? Then the policy does not apply to that table (but we recommend adding them). See the 'Make Table Branch-aware' action in the UI.
