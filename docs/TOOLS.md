# Tools

This page lists every MCP tool, resource, and prompt the server exposes. It
grows one row at a time as tools land.

## Tools

| Name | Status | Description |
|---|---|---|
| `roboflow_get_workspace` | alpha | Fetch a workspace's metadata and its projects. Falls back to `ROBOFLOW_WORKSPACE` when called without arguments. |
| `roboflow_list_projects` | alpha | Return just the project list for a workspace. Lighter than `roboflow_get_workspace` when you only need the project array. |
| `roboflow_search_images` | alpha | Search a project's images. Filter by `tag`, `class_name`, or semantic `prompt`. Paginated with `limit` (max 250) and `offset`. |
| `roboflow_add_image_tags` | alpha | Attach one or more tags to an image. |
| `roboflow_remove_image_tags` | alpha | Detach one or more tags from an image. |
| `roboflow_set_image_tags` | alpha | Replace an image's tags with exactly the given list. |

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
