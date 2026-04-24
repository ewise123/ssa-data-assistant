# MCP Server Setup Guide

Connect the SSA Data Assistant MCP server to Claude Desktop or Claude Code so you can query the Project_Master_Database from any Claude chat.

## Prerequisites

- **Windows 10/11** with **WSL2** (Ubuntu)
- **Python 3.11+** installed in WSL
- **Claude Desktop** (Windows) and/or **Claude Code**
- Access to the `PG_DSN_READONLY` connection string (ask Emory)

## 1. Clone and install (in WSL)

```bash
git clone https://github.com/ewise123/ssa-data-assistant.git
cd ssa-data-assistant
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Create `.env` file

In the project root, create `.env`:

```bash
PG_DSN_READONLY=postgresql://user:password@host:5432/dbname?sslmode=require
PG_SEARCH_PATH=Project_Master_Database
```

## 3. Verify the server runs

```bash
source .venv/bin/activate
python mcp_server.py
```

You should see log lines ending in `[mcp] Ready — fully local, no external API dependencies`, then it will hang (waiting for MCP protocol input — that's normal). Press `Ctrl+C` to exit.

First run downloads the ~80MB local embedding model (one-time).

## 4. Configure Claude Desktop (Windows)

Edit `%APPDATA%\Claude\claude_desktop_config.json` (create if missing). Add the `mcpServers` block — **replace `<USERNAME>` with your WSL username** (run `whoami` in WSL to find it):

```json
{
  "mcpServers": {
    "ssa-data-assistant": {
      "command": "wsl.exe",
      "args": [
        "/home/<USERNAME>/ssa-data-assistant/.venv/bin/python",
        "-u",
        "/home/<USERNAME>/ssa-data-assistant/mcp_server.py"
      ]
    }
  }
}
```

**Fully quit Claude Desktop** (right-click tray icon → Quit, not just close window), then reopen. The tools appear under the 🔌 icon.

## 5. Configure Claude Code

Edit `~/.claude/settings.json` in WSL. Add:

```json
{
  "mcpServers": {
    "ssa-data-assistant": {
      "command": "/home/<USERNAME>/ssa-data-assistant/.venv/bin/python",
      "args": [
        "-u",
        "/home/<USERNAME>/ssa-data-assistant/mcp_server.py"
      ]
    }
  }
}
```

Start a new Claude Code session to pick up the change.

## 6. Test it

In any Claude chat, ask:

> "List all the tables in the database"

Claude will call `list_tables` and show the 26 tables. Then try:

> "How many consultants do we have by title?"

Claude will call `get_schema` → `get_golden_examples` → `execute_query` automatically.

## Troubleshooting

**Error: "Server disconnected"** — Check the log at `%APPDATA%\Claude\logs\mcp-server-ssa-data-assistant.log`. Common causes:

- **`PermissionError: 'data'`** — WSL path or username wrong in the config
- **`FileNotFoundError: .env`** — `.env` file missing in project root
- **`ModuleNotFoundError`** — venv not activated or dependencies not installed (re-run `pip install -r requirements.txt`)
- **Connection string errors** — verify `PG_DSN_READONLY` works: `python -c "from app.db import run_select; print(run_select('SELECT 1'))"`

**Changes not picked up** — Claude Desktop caches the config. Fully quit the process (not just close the window) and reopen.

## What the tools do

| Tool | Purpose |
|------|---------|
| `get_schema(question)` | Returns relevant tables/columns with descriptions and sample values |
| `get_golden_examples(question, k=3)` | Returns similar verified (question, SQL) examples |
| `execute_query(sql)` | Validates and runs read-only SQL (SELECT only, LIMIT ≤ 100) |
| `list_tables()` | Lists all 26 tables with descriptions |

No OpenAI key needed — uses local embeddings (all-MiniLM-L6-v2 via onnxruntime).
