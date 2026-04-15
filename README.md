# mcp-server-roboflow

An MCP server that exposes the [Roboflow](https://roboflow.com) API to
MCP-compatible clients like Claude Code, Claude Desktop, and Cursor.

Use it to manage datasets, upload and tag images, push annotations, and inspect
projects without leaving your editor.

> Not affiliated with Roboflow Inc. This is a community project.

## Status

Early development. The public API and tool names will change until `v1.0.0`.
See [CHANGELOG.md](CHANGELOG.md) for what shipped in each release.

## Install

Requires Python 3.10 or newer and a Roboflow private API key.

### Claude Code

```bash
claude mcp add roboflow \
  --scope user \
  --env ROBOFLOW_API_KEY=your_key_here \
  -- uvx mcp-server-roboflow
```

Restart Claude Code. Tools appear as `mcp__roboflow__*`.

### From source

```bash
git clone https://github.com/MayankD409/Roboflow-MCP-Server.git
cd Roboflow-MCP-Server
uv sync
uv run mcp-server-roboflow
```

## Configuration

Environment variables (copy `.env.example` to `.env` for local dev):

| Variable | Required | Description |
|---|---|---|
| `ROBOFLOW_API_KEY` | yes | Your Roboflow private API key |
| `ROBOFLOW_WORKSPACE` | no | Default workspace slug, so tools can omit it |
| `ROBOFLOW_API_URL` | no | Override the API base (default `https://api.roboflow.com`) |
| `ROBOFLOW_MCP_LOG_LEVEL` | no | `DEBUG`, `INFO`, `WARNING`, `ERROR` (default `INFO`) |

## Tools

See [docs/TOOLS.md](docs/TOOLS.md) for the full list. v0.1 focuses on dataset
management: list workspaces and projects, upload images, add and filter by
tags, upload annotations.

## Contributing

We follow Git Flow and test-driven development. New tools land through PRs to
`develop`; releases cut from `develop` into `main` with a semver tag.

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a PR. Bugs and feature
ideas go in [issues](https://github.com/MayankD409/Roboflow-MCP-Server/issues).

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
