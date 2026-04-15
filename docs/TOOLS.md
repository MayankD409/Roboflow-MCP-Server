# Tools

This page lists every MCP tool, resource, and prompt the server exposes. It
grows one row at a time as tools land.

## Tools

| Name | Status | Description |
|---|---|---|
| `roboflow_get_workspace` | alpha | Fetch a workspace's metadata and its projects. Falls back to `ROBOFLOW_WORKSPACE` when called without arguments. |
| `roboflow_list_projects` | alpha | Return just the project list for a workspace. Lighter than `roboflow_get_workspace` when you only need the project array. |

## Resources

| URI | Status | Description |
|---|---|---|
| _none yet_ | | |

## Prompts

| Name | Status | Description |
|---|---|---|
| _none yet_ | | |

## Status legend

- **alpha**: behaviour may change; no compatibility promise.
- **beta**: stable signature, minor fields may still change.
- **stable**: covered by semver; breaking changes need a major bump.
