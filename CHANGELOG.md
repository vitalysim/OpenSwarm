# Changelog

All notable OpenSwarm changes should be recorded here. Use this file for
human-readable release notes and implementation context that is useful after the
commit history gets noisy.

This project follows the spirit of [Keep a Changelog](https://keepachangelog.com/)
and uses semantic versioning where packaged releases allow it.

## Unreleased

### Added

- Added runtime per-agent model controls for OpenSwarm agents.
- Added OpenSwarm TUI model status display so the prompt footer shows the active
  backend model instead of only `agency-swarm/default`.
- Added an Agent picker action for managing OpenSwarm agent models.
- Added backend model-control routes:
  - `GET /{agency}/openswarm/models`
  - `POST /{agency}/openswarm/agent-model`
- Added a central model registry in `model_control.py` for agent model env vars,
  curated model choices, auth-status mapping, and `.env` persistence.
- Added tests for backend model switching and TUI model-state APIs.

### Changed

- Centralized agent `ModelSettings` creation in `config.py` so initial startup
  and live model switching use the same OpenAI/subscription/LiteLLM rules.
- Updated every agent factory to use the centralized model-settings helper.
- Updated onboarding to share model option definitions with the runtime model
  registry.
- Expanded `npm run test:tui` to cover the Agent Swarm adapter, agent picker,
  prompt framework-mode footer, and session-error tests.

### Fixed

- OpenSwarm-specific TUI model controls now degrade gracefully when connected to
  a generic Agency Swarm server that does not expose OpenSwarm model-control
  routes.
- Dialog-rendered model management now has access to the model context.

## 2026-05-07

### Added

- Vendored the AgentSwarm/OpenCode TUI source under `packages/openswarm-tui`.
- Added a custom TUI build workflow and local build command.
- Added backend authentication status flow for Codex CLI, Claude Code, OpenAI,
  Anthropic, Google, Composio, SearchAPI, media services, and stock image
  providers.
- Added subscription-backed model adapters for Codex CLI and Claude Code.
- Added subscription web search routing through Codex/Claude Code with fallback
  support.
- Added `uv`-based Python development and test instructions.

### Changed

- The Python launcher now passes backend auth mode to the TUI so users do not
  have to use the upstream OpenAI browser login flow for OpenSwarm.
- Local development and verification commands now run through `uv run ...`.

### Verified

- `uv run pytest tests/test_model_control.py`
- `npm run test:tui`
- `npm run build:tui`
- `npm run test:tui:e2e`
