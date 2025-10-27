# Updating SSA Data Assistant for New Tables/Columns

This guide walks internal data owners through refreshing the assistant after adding tables or columns to the `Project_Master_Database` schema.

## Overview
1. **Apply schema changes** in PostgreSQL (via migrations or admin tooling).
2. **Refresh configuration** so the app understands the new objects.
3. **Verify the assistant** returns the expected hints and answers.

---

## 1. Apply Changes in Postgres
- Keep naming **consistent and descriptive** (snake_case tables/columns).
- Document relationships (`*_id` foreign keys) so they’re discoverable by the catalog.

## 2. Refresh Application Metadata

### Option A: On-demand catalog reload
Use the built-in `/debug/catalog/reload` endpoint (available to authenticated admins):

```bash
curl -X POST https://<app-host>/debug/catalog/reload \
     -H "Authorization: Bearer <admin-token>"
```

This re-runs:
- `load_catalog(...)`
- `load_aliases`, `load_join_map`, `load_column_semantics`, `load_allowed_values`
- `load_disambiguation_rules`

### Option B: CLI helper (local access)
If you have shell access to the app runners:

```bash
python scripts/refresh_catalog.py --dsn "$PG_DSN_READONLY" --schema Project_Master_Database
```

This script should:
1. Warm the catalog.
2. Emit counts of tables/columns/joins.
3. Optionally update checked-in static config (column semantics, join map) for review.

## 3. Update Supporting Config Files (if needed)
- **`app/config/column_semantics.csv`** – add entries for new columns (semantic type, filters).
- **`app/config/join_map.json`** – describe multi-hop join paths the assistant should prefer.
- **`app/config/*_aliases.csv`** – add synonyms users may use.
- **`app/config/disambiguation.json`** – map keywords to datasets/tables.

After editing, rerun the reload step so the app picks up the changes.

## 4. Validate
1. Hit `GET /debug/env` – ensure `catalog_loaded` and `config_loaded` return `true`.
2. Run sample QA:
   - `/ask` for a question referencing the new data.
   - Confirm the SQL and results make sense.
3. Update the “How-To” documentation (see user onboarding doc) if new datasets were added.

---

## Best Practices
- **Consistent naming**: singular table names (e.g., `ClientEngagement`), snake_case columns (`client_id`).
- **Foreign keys**: use `<table>_id` suffix to hint join directions.
- **Documentation**: accompany schema change with a short Markdown update (ERD, purpose, sample questions).
- **Version control**: treat config files like code; submit PRs with context.
