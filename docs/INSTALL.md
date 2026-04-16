# Installing `mcp-server-roboflow` in MCP clients

Every recipe below assumes:

- Python 3.10 or newer is available.
- You have a Roboflow private API key (Roboflow web UI → Settings → API Keys).
- `uv` is installed (`pipx install uv` or see https://docs.astral.sh/uv/).

The package is published to PyPI as `mcp-server-roboflow` with the console
script `mcp-server-roboflow`.

> Security note: prefer `uvx` to pinned installs. `uvx mcp-server-roboflow`
> fetches the latest release on each launch so security fixes land without
> an explicit upgrade step. If you need a fixed version, use
> `uvx mcp-server-roboflow@0.2.0`.

## Claude Code

```bash
claude mcp add roboflow \
  --scope user \
  --env ROBOFLOW_API_KEY=your_key_here \
  -- uvx mcp-server-roboflow
```

Restart Claude Code. Tools appear as `mcp__roboflow__*`.

Optional hardening flags:

```bash
claude mcp add roboflow \
  --scope user \
  --env ROBOFLOW_API_KEY=your_key_here \
  --env ROBOFLOW_WORKSPACE=contoro \
  --env ROBOFLOW_MCP_WORKSPACE_ALLOWLIST=contoro \
  --env ROBOFLOW_MCP_MODE=curate \
  --env ROBOFLOW_MCP_AUDIT_LOG=$HOME/.roboflow-mcp-audit.jsonl \
  -- uvx mcp-server-roboflow
```

## Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "roboflow": {
      "command": "uvx",
      "args": ["mcp-server-roboflow"],
      "env": {
        "ROBOFLOW_API_KEY": "your_key_here",
        "ROBOFLOW_WORKSPACE": "contoro",
        "ROBOFLOW_MCP_MODE": "readonly"
      }
    }
  }
}
```

Quit and relaunch Claude Desktop. Tools appear in the tool picker as
`roboflow_*`.

## Cursor

Edit `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` in your project:

```json
{
  "mcpServers": {
    "roboflow": {
      "command": "uvx",
      "args": ["mcp-server-roboflow"],
      "env": {
        "ROBOFLOW_API_KEY": "your_key_here"
      }
    }
  }
}
```

Restart Cursor. The tools appear under the MCP panel.

## Continue

Edit `~/.continue/config.json`:

```json
{
  "experimental": {
    "modelContextProtocolServers": [
      {
        "transport": {
          "type": "stdio",
          "command": "uvx",
          "args": ["mcp-server-roboflow"],
          "env": {
            "ROBOFLOW_API_KEY": "your_key_here"
          }
        }
      }
    ]
  }
}
```

## Windsurf

Edit `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "roboflow": {
      "command": "uvx",
      "args": ["mcp-server-roboflow"],
      "env": {
        "ROBOFLOW_API_KEY": "your_key_here"
      }
    }
  }
}
```

## Zed

Add to `~/.config/zed/settings.json`:

```json
{
  "context_servers": {
    "roboflow": {
      "command": {
        "path": "uvx",
        "args": ["mcp-server-roboflow"],
        "env": {
          "ROBOFLOW_API_KEY": "your_key_here"
        }
      }
    }
  }
}
```

## VS Code (MCP extension)

If you're using an MCP-aware extension such as the official Anthropic MCP
VS Code extension, add to your workspace settings:

```jsonc
{
  "mcp.servers": {
    "roboflow": {
      "command": "uvx",
      "args": ["mcp-server-roboflow"],
      "env": {
        "ROBOFLOW_API_KEY": "your_key_here"
      }
    }
  }
}
```

## From source (development)

```bash
git clone https://github.com/MayankD409/Roboflow-MCP-Server.git
cd Roboflow-MCP-Server
uv sync --all-extras
ROBOFLOW_API_KEY=your_key uv run mcp-server-roboflow
```

## Verifying the install

After install, the MCP client should show at least these six tools:

- `roboflow_get_workspace`
- `roboflow_list_projects`
- `roboflow_search_images`
- `roboflow_add_image_tags`
- `roboflow_remove_image_tags`
- `roboflow_set_image_tags`

Call `roboflow_get_workspace` with no arguments — it should return your
workspace metadata. If it doesn't, check:

1. `ROBOFLOW_API_KEY` is set in the MCP server's environment (not just
   your shell).
2. `ROBOFLOW_WORKSPACE` is set, or pass a workspace argument.
3. The logs: set `ROBOFLOW_MCP_LOG_LEVEL=DEBUG` for a one-shot diagnostic.

## Troubleshooting

- **Tool not showing up in client**: reload the client. Most MCP clients
  cache tool schemas at connection time.
- **"ROBOFLOW_API_URL must use https://"**: the default is correct; this
  fires when you've set a custom `ROBOFLOW_API_URL` to an `http://`
  address. Set `ROBOFLOW_MCP_ALLOW_INSECURE=1` for local dev only.
- **"destructive operations are blocked"**: the server is in readonly mode
  (the default). Set `ROBOFLOW_MCP_MODE=curate` to enable tag removals.
- **"Client-side rate limit reached"**: you've hit the built-in token
  bucket. Raise `ROBOFLOW_MCP_RATE_LIMIT_PER_MINUTE` and
  `ROBOFLOW_MCP_RATE_LIMIT_PER_HOUR`, or wait out the window.
- **Windows stdio buffering**: `uvx` handles this correctly. If you're
  running from source with a custom Python, set `PYTHONUNBUFFERED=1`.
