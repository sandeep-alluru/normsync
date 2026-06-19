# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `NormVersionStore` — track full history of norm changes with versioning and time-travel queries
- `NormVersion` dataclass with version, changed_by, change_reason, previous_version fields
- `agent_compliance_report()` — compute compliance rate, risk level, and trend for a single agent
- `fleet_compliance_report()` — rank a fleet of agents by compliance (worst first)
- `AgentCompliance` dataclass with violation_breakdown and risk_level
- `detect_norm_conflicts()` — find logical contradictions, priority ambiguities, and scope overlaps between norms
- `NormConflict` dataclass with conflict_type and example_action
- CLI: `normsync compliance <agent_id>` and `normsync conflicts` commands

## [0.1.0] - 2026-06-18

### Added
- WorldNorm, AgentAction, NormViolation, NormRevision data model with SHA-256 content-addressing
- NormMonitor with token-based condition matching
- NormStore SQLite backend (in-memory and file-based)
- CLI: add, check, violations, revisions, status commands
- FastAPI REST API: /health, /norm, /norms, /check, /violations
- MCP server: add_norm, check_action, list_violations tools
- Report formatters: to_json, to_markdown, print_violations
- 46 tests with ≥85% coverage
- GitHub Actions CI (ubuntu + macos), release workflow with ci-gate

[Unreleased]: https://github.com/sandeep-alluru/normsync/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sandeep-alluru/normsync/releases/tag/v0.1.0
