# Local MCP Server Setup: Windows + WSL

A tool-agnostic guide for connecting a Python-based MCP server running in WSL to Claude Desktop (Windows) and/or Claude Code. Distilled from hard-won lessons setting up a local MCP server.

## Prerequisites

- Windows 10/11 with **WSL2** (Ubuntu or similar)
- **Python 3.11+** installed inside WSL (not Windows)
- Your MCP server code and its dependencies installed in a WSL venv
- Claude Desktop (Windows app) and/or Claude Code

## Writing your MCP server: rules that bite you later

These aren't optional — violating any of them causes silent failures when launched by Claude Desktop.

### 1. stdout is the MCP protocol — never `print()` to it

The MCP server communicates with Claude over stdin/stdout. Any `print()` call corrupts the protocol. All logs, warnings, and debug output must go to **stderr**.

```python
import sys
def _log(msg: str) -> None:
    print(msg, file=sys.stderr)
```

If you import third-party code that prints to stdout, wrap it with `contextlib.redirect_stdout`.

### 2. Use absolute paths for everything — never relative

Claude Desktop launches your server with the **working directory set to somewhere unpredictable** (often `C:\` on Windows, or `/` in WSL). Relative paths like `Path("data/cache")` or `"config.yaml"` will fail with `PermissionError` or `FileNotFoundError`.

Two ways to fix:

```python
# Option A: anchor paths to the script's location
from pathlib import Path
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "cache"
```

```python
# Option B: chdir to project root at startup (do this BEFORE imports
# that read relative paths at module load)
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
# ... now imports with relative paths work
```

### 3. Load `.env` before any imports that read env vars

```python
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
# ... now import modules that read os.getenv() at module load time
```

## Claude Desktop (Windows) config

Edit `%APPDATA%\Claude\claude_desktop_config.json` (create the file if missing):

```json
{
  "mcpServers": {
    "my-server-name": {
      "command": "wsl.exe",
      "args": [
        "/home/<wsl-username>/path/to/project/.venv/bin/python",
        "-u",
        "/home/<wsl-username>/path/to/project/server.py"
      ]
    }
  }
}
```

**Critical details:**

| Detail | Why |
|--------|-----|
| `wsl.exe` not `wsl` | Windows PATH lookup needs the `.exe` extension |
| No `--cd` flag | Redundant if your server uses absolute paths (see rule #2) |
| `-u` flag on python | Forces unbuffered stdout; without it the MCP protocol hangs waiting for flushed data |
| Full WSL paths | Use `/home/user/...`, not Windows paths or `~` shortcuts |
| Absolute venv python | `/home/user/project/.venv/bin/python`, not just `python` |

### After editing: fully quit Claude Desktop

Closing the window isn't enough. The process keeps running in the tray. Right-click the tray icon → **Quit**, then reopen. The config is only read on fresh startup.

## Claude Code config

Edit `~/.claude/settings.json` inside WSL (or the project-level `.claude/settings.json`):

```json
{
  "mcpServers": {
    "my-server-name": {
      "command": "/home/<user>/path/to/project/.venv/bin/python",
      "args": [
        "-u",
        "/home/<user>/path/to/project/server.py"
      ]
    }
  }
}
```

No `wsl.exe` wrapper — Claude Code already runs in WSL. Start a new Claude Code session to pick up the change.

## Debugging

### Logs live here

- **Claude Desktop:** `%APPDATA%\Claude\logs\mcp-server-<name>.log`
- **Claude Code:** visible in session startup output

The log shows the exact command invoked, the Python traceback (if any), and whether the connection handshake succeeded.

### Test the server standalone first

```bash
source .venv/bin/activate
python -u server.py
```

It should print startup logs to stderr, then hang waiting for MCP protocol input. Press Ctrl+C. If this fails, the problem is in your server, not the Claude config.

### MCP Inspector (interactive test harness)

```bash
npx @modelcontextprotocol/inspector python -u server.py
```

Opens a browser UI to test tools, resources, and prompts without wiring up to Claude.

## Common failure modes

| Error in log | Cause | Fix |
|--------------|-------|-----|
| `Server disconnected` immediately | Server crashed at startup | Check traceback in log file |
| `PermissionError: 'data'` | Relative path in working-dir-less environment | Use absolute paths (rule #2) |
| `FileNotFoundError: .env` | `.env` not found | Load via absolute path: `load_dotenv(ROOT / ".env")` |
| `ModuleNotFoundError` | Wrong Python binary | Point `command` at the venv Python, not system Python |
| Server starts but no tools appear | stdout pollution | All logs must go to stderr (rule #1) |
| Config changes ignored | Claude Desktop cached | Fully quit from tray, don't just close window |
| Protocol hangs | Python stdout buffering | Add `-u` flag to python args |

## Quick checklist

Before asking "why doesn't it work":

- [ ] Server runs standalone with `python -u server.py`
- [ ] All `print()` goes to stderr, not stdout
- [ ] All file paths in the server are absolute (or `os.chdir(ROOT)` at startup)
- [ ] `.env` loaded from `ROOT / ".env"`, not just `.env`
- [ ] Config uses `wsl.exe` (for Desktop) or direct venv python (for Code)
- [ ] Config uses `-u` flag on python
- [ ] Claude Desktop fully quit (not just closed) after config change
- [ ] Checked the log file at `%APPDATA%\Claude\logs\`
