# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-04-15

First public release. The server is usable end to end for dataset curation
against a real Roboflow workspace.

### Added
- Project scaffold with Git Flow branching, CI across Python 3.10-3.13,
  issue and PR templates, contributor docs, and the Apache-2.0 license.
- Foundation layer: typed errors (`RoboflowMCPError` and friends), env-driven
  settings with `SecretStr` masking, a secret-scrubbing log formatter, an
  async Roboflow HTTP client with auto-auth and exponential-backoff retry,
  and a FastMCP server skeleton.
- Workspace tools `roboflow_get_workspace` and `roboflow_list_projects`.
  Both wrap `GET /{workspace}`, honour `ROBOFLOW_WORKSPACE` as a default,
  and return typed pydantic models.
- Image search and tagging: `roboflow_search_images` with `tag`,
  `class_name`, and semantic `prompt` filters, plus
  `roboflow_add_image_tags`, `roboflow_remove_image_tags`, and
  `roboflow_set_image_tags`. Enough for the full "find, tag, find again"
  workflow that drives tag-based dataset curation.

### Fixed
- `ImageSummary.created` now accepts an int or a string. Roboflow's docs
  claim the field is a string, but the live search endpoint returns a
  Unix-millisecond int (e.g. `1715286185986`). Caught against a real
  workspace during v0.1 verification.

[Unreleased]: https://github.com/MayankD409/Roboflow-MCP-Server/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/MayankD409/Roboflow-MCP-Server/releases/tag/v0.1.0
