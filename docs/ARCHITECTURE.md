# Architecture

A short map of how the server is put together. Keep this document updated when
you change a layer.

## Layers

```
+----------------------------------+
| MCP client (Claude Code, ...)    |
+----------------+-----------------+
                 | stdio (JSON-RPC)
+----------------v-----------------+
| server.py  (FastMCP application) |   tool registration, lifecycle
+----------------+-----------------+
                 |
+----------------v-----------------+
| tools/  (one file per domain)    |   thin wrappers, pydantic I/O
+----------------+-----------------+
                 |
+----------------v-----------------+
| client.py (httpx) + sdk.py       |   auth, retries, error mapping
+----------------+-----------------+
                 |
+----------------v-----------------+
| Roboflow public API              |
+----------------------------------+
```

## Principles

- **Tools are thin.** A tool function validates input, calls a single client
  method, shapes the response. No business logic, no fan-out.
- **One domain per file.** `workspace.py`, `projects.py`, `images.py`, etc.
  Easier to review, easier for contributors to find their way.
- **Pydantic at the edges.** Inputs and outputs are pydantic models so JSON
  Schema falls out for free and MCP clients get proper type hints.
- **No globals.** The httpx client and settings are created once in `server.py`
  and passed into tool registration. Tests can swap them cleanly.
- **Secrets never log.** `config.py` masks the API key on repr and in log
  formatters. Anything that might echo a header goes through the scrubber.

## Where things live

| Path | What |
|---|---|
| `src/roboflow_mcp/server.py` | FastMCP app, `main()` entry point |
| `src/roboflow_mcp/config.py` | Pydantic settings from env |
| `src/roboflow_mcp/client.py` | Async httpx client, retries |
| `src/roboflow_mcp/sdk.py` | Roboflow Python SDK adapter |
| `src/roboflow_mcp/errors.py` | Typed exceptions, MCP mapping |
| `src/roboflow_mcp/logging.py` | Structured logging, scrubber |
| `src/roboflow_mcp/models/` | Pydantic request and response models |
| `src/roboflow_mcp/tools/` | One module per domain |
| `src/roboflow_mcp/resources/` | Read-only MCP resources |
| `src/roboflow_mcp/prompts/` | Reusable MCP prompts |
| `tests/unit/` | Pure unit tests, HTTP mocked |
| `tests/integration/` | Boot the server, call tools end-to-end |
| `tests/contract/` | Opt-in tests against the real API |

## Testing layers

| Layer | What it covers | Runs in CI? |
|---|---|---|
| Unit | One tool at a time, HTTP mocked with `respx` | Yes |
| Integration | Stdio server boots, `list_tools`, `call_tool` | Yes |
| Contract | Real Roboflow API calls via VCR cassettes or live | Only if `ROBOFLOW_TEST_API_KEY` is set |
