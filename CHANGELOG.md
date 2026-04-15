# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project scaffold: Git Flow branching, CI, issue and PR templates,
  contributor docs, and Apache-2.0 license.
- Foundation layer: typed errors (`RoboflowMCPError` and friends), env-driven
  settings with secret masking, secret-scrubbing log formatter, async
  Roboflow HTTP client with auto-auth and exponential-backoff retry, and a
  FastMCP server skeleton that boots cleanly with zero tools registered.
- First real tools: `roboflow_get_workspace` and `roboflow_list_projects`.
  Both wrap `GET /{workspace}`, honour `ROBOFLOW_WORKSPACE` as a default, and
  return typed `Workspace`/`Project` pydantic models.

[Unreleased]: https://github.com/MayankD409/Roboflow-MCP-Server/compare/HEAD...HEAD
