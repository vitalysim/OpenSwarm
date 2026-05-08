# Changelog

All notable OpenSwarm changes should be recorded here. Use this file for
human-readable release notes and implementation context that is useful after the
commit history gets noisy.

This project follows the spirit of [Keep a Changelog](https://keepachangelog.com/)
and uses semantic versioning where packaged releases allow it.

## Unreleased

### Added

- Added a registry-driven multi-swarm runtime with `open-swarm` and
  `security-research`.
- Added the Security Research Swarm with nine agents for
  orchestration, deep research, threat intelligence, vulnerability research,
  OSINT enrichment, lab analysis, technical writing, slides, and visual design.
- Added public no-key security research tools for NVD/CVE, CISA KEV, FIRST
  EPSS, and MITRE ATT&CK/CWE/CAPEC lookup.
- Added local research workspace tools for notes, resources, progress tracking,
  and design language loading.
- Added tracked Security Research Workspace templates and design assets under
  `research_workspace/security/`.
- Added TUI support for in-app swarm selection, active swarm/agent/model
  display, and swarm-scoped model management.
- Added TUI working-directory control (`/cwd`) with prompt-footer visibility so
  users can see and change the active project directory for the current
  OpenSwarm session.
- Added provider-neutral OpenSwarm skills under `openswarm_skills/`, with
  backend discovery/loading tools for all primary agents.
- Added TUI `/skills` support for OpenSwarm launches so skill selections insert
  an OpenSwarm instruction directive instead of a provider-native slash command.
- Added `OPENSWARM_MODEL_TIMEOUT_SECONDS` for optional model-call timeouts; by
  default OpenSwarm no longer hard-stops subscription or slide model calls at
  180 seconds.
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
- Added request-scoped workspace context and tests for project-relative file
  reads/writes and TUI working-directory transport.

### Changed

- `server.py` and the local TUI bridge now expose every available registered
  swarm.
- Model control is now swarm-aware and keeps distinct env vars per swarm while
  preserving existing OpenSwarm env vars.
- The onboarding model-routing exports now include Security Research Swarm env
  vars for subscription-first, API-first, and custom setup paths.
- Centralized agent `ModelSettings` creation in `config.py` so initial startup
  and live model switching use the same OpenAI/subscription/LiteLLM rules.
- Updated every agent factory to use the centralized model-settings helper.
- Updated onboarding to share model option definitions with the runtime model
  registry.
- Updated document, slide, image, video, file, and security research tools to
  resolve relative paths and generated artifacts under the active OpenSwarm
  working directory.
- Updated the OpenSwarm launcher to constrain skill discovery to the
  project-local skills directory and avoid loading global `.claude` or
  `.agents` skills by default.
- Expanded `npm run test:tui` to cover the Agent Swarm adapter, agent picker,
  prompt framework-mode footer, and session-error tests.

### Fixed

- OpenSwarm-specific TUI model controls now degrade gracefully when connected to
  a generic Agency Swarm server that does not expose OpenSwarm model-control
  routes.
- Dialog-rendered model management now has access to the model context.
- Local launchers (`run.py` and `bin/openswarm`) now discover the locally-built
  TUI binary under `packages/openswarm-tui/.../dist/`, so a fresh `npm run
  build:tui` is used immediately instead of falling back to the upstream
  `agentswarm-cli` from npm.
- Initial TUI agency target now uses the registered swarm id (e.g. `open-swarm`)
  instead of the agency display name (`OpenSwarm`), preventing
  `Streaming request failed (404): {"detail":"Not Found"}` on the first prompt
  in a multi-swarm setup.
- TUI swarm selection now updates both the visible footer and the next Agency
  Swarm request route when the launcher is backed by `OPENCODE_CONFIG_CONTENT`
  instead of only showing a success toast.

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
