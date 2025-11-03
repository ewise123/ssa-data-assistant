# Updating SSA Data Assistant When the Database Changes

This runbook describes every step required after you add tables, columns, or data relationships to the **Project_Master_Database** schema. Follow the checklist in order so the app, documentation, and GPT assistant all stay in sync.

---

## Prerequisites

- Access to the PostgreSQL instance in pgAdmin 4 (or psql) with privileges to RUN DDL and grant read permissions.
- The read-only connection string used by the app (`PG_DSN_READONLY`). The username in this DSN (e.g., `chat_reader`) is the role that must keep `SELECT` on new objects.
- Latest copies of:
  - Lucidchart/ERD for Project_Master_Database
  - `README.md`, this runbook, and `docs/USING_SSA_DATA_ASSISTANT.md`
- A terminal with `curl` (on Windows use `curl.exe`) or the ability to run PowerShell `Invoke-WebRequest`.
- Optional: value of `CATALOG_RELOAD_TOKEN` (if set in your deployment) for authenticating the catalog reload endpoint.

---

## Checklist Overview

1. [Plan & capture the schema change](#1-plan--capture-the-schema-change)
2. [Apply DDL in PostgreSQL](#2-apply-ddl-in-postgresql)
3. [Grant read access to the app role](#3-grant-read-access-to-the-app-role)
4. [Update SSA Assistant config files](#4-update-ssa-assistant-config-files)
5. [Reload the catalog/config in the running app](#5-reload-the-catalogconfig-in-the-running-app)
6. [Validate end-to-end](#6-validate-end-to-end)
7. [Update docs, Lucidchart, and GPT knowledge base](#7-update-docs-lucidchart-and-gpt-knowledge-base)

Each step below explains what to do and how to find required values.

---

## 1. Plan & capture the schema change

1. Export the existing schema for reference (pgAdmin 4 → right-click schema → **Scripts > CREATE Script…**).
2. Update the Lucidchart / ERD with the planned additions (new tables, relationships, primary/foreign keys).
3. Document any new terminology, expected joins, or business rules. You will use this when editing config files and documentation later.

---

## 2. Apply DDL in PostgreSQL

1. In pgAdmin 4, connect to the database that hosts the `Project_Master_Database` schema.
2. Run your DDL (CREATE TABLE, ALTER TABLE, etc.) in the **Query Tool**.
3. If you need to backfill data, perform it now (e.g., `INSERT INTO`, `UPDATE` statements).
4. Verify the objects were created:
   ```sql
   SELECT table_schema, table_name
   FROM information_schema.tables
   WHERE table_schema = 'Project_Master_Database'
     AND table_name IN ('NewTableName', 'AnotherNewTable');
   ```
5. If you renamed or dropped columns, double-check dependent views, foreign keys, and application SQL.

---

## 3. Grant read access to the app role

The SSA app connects with the user embedded in `PG_DSN_READONLY`. You can find it by looking at your `.env`, Key Vault secret, or app settings (example: `postgresql://chat_reader:...@host:5432/postgres?sslmode=require`).

1. Identify the app role. Example using psql/pgAdmin:
   ```sql
   SELECT current_user;
   ```
   when connected with the app’s DSN.
2. Grant `SELECT` on each new table or view:
   ```sql
   GRANT SELECT ON "Project_Master_Database"."NewTableName" TO chat_reader;
   ```
3. If you added sequences, grant usage:
   ```sql
   GRANT USAGE ON SEQUENCE "Project_Master_Database"."newtable_id_seq" TO chat_reader;
   ```

---

## 4. Update SSA Assistant config files

All config lives under `app/config/`. Update only what is affected by your schema change.

| File | When to update | Notes |
|------|----------------|-------|
| `column_semantics.csv` | New columns, renamed columns | Provide semantic type and preferred filter. Follow existing rows for format. |
| `join_map.json` | New tables or relationships that the assistant should traverse | Add a new `paths` entry describing tables, joins, canonical filters, and default columns. |
| `*_aliases.csv` | New synonyms or user-facing names | For clients, titles, tools, etc. |
| `disambiguation.json` | Routing hints based on keywords | Map new terms to datasets/tables. |

Tips:
- Use ASCII quotes/commas to avoid encoding issues.
- Keep IDs snake_case and reflect true foreign key relationships.
- Commit changes to version control so they can be reviewed.

---

## 5. Reload the catalog/config in the running app

After editing config, trigger the reload endpoint (no need to restart the service).

1. Start the FastAPI app if it is not already running.
2. Issue a POST to `/debug/catalog/reload`.
   - **Local development (no token):**
     ```powershell
     curl.exe -X POST http://localhost:8000/debug/catalog/reload
     ```
   - **Secured environment (token required):**
     1. Retrieve the token from the environment variable `CATALOG_RELOAD_TOKEN` (e.g., check Azure App Settings, Key Vault, or your deployment pipeline secrets).
     2. Invoke the endpoint with the bearer token:
        ```powershell
        curl.exe -X POST https://<app-host>/debug/catalog/reload ^
          -H "Authorization: Bearer <CATALOG_RELOAD_TOKEN>"
        ```
3. A successful response looks like:
   ```json
   {
     "ok": true,
     "catalog": {"schema": "Project_Master_Database", "tables": 42, "foreign_keys": 88, "error": null},
     "config": {"aliases": 18, "join_paths": 12, "semantics_tables": 20, ...}
   }
   ```
   If `ok` is false, inspect the `error` fields and fix typos in config files.

---

## 6. Validate end-to-end

1. **Environment sanity check:**  
   ```powershell
   curl.exe http://localhost:8000/debug/env
   ```
   Ensure `catalog_loaded` is true and `catalog_error` is null.

2. **Functional tests:**  
   - Ask the SSA app a question that should touch the new objects.
   - Confirm the generated SQL references the new table/column.
   - Verify the row count banner and results look correct.

3. **Analytics logging:**  
   - If you expect the question to show up as a common query, submit it twice and confirm `/analytics/common-queries` includes it.
   - Trigger an error case intentionally (optional) to verify `/admin/problem-queries`.

4. **Database grants:**  
   - Reconnect with the read-only DSN and run a simple `SELECT` against the new table to confirm permissions.

---

## 7. Update docs, Lucidchart, and GPT knowledge base

1. Update:
   - Lucidchart or ERD with the final schema.
   - This runbook and `README.md` if procedures changed.
   - `docs/USING_SSA_DATA_ASSISTANT.md` when new datasets or user-facing features appear.
2. Commit the changes to version control and open a pull request.
3. Share the updated schema SQL, docs, and diagrams with the GPT maintenance assistant so it has the new context.
4. Notify stakeholders and, if needed, add a note to release/change logs.

---

## Appendix: Sample SQL snippets

```sql
-- Verify all tables in the schema
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'Project_Master_Database'
ORDER BY table_name;

-- Check column metadata for a specific table
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'Project_Master_Database'
  AND table_name = 'ResourceTool';

-- Confirm the read-only role has access
SET ROLE chat_reader;
SELECT * FROM "Project_Master_Database"."ResourceTool" LIMIT 5;
RESET ROLE;
```

Follow this checklist every time the underlying SQL changes so the SSA Data Assistant stays accurate and the GPT helper has the latest picture of the warehouse.
