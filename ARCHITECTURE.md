# OpenSwarm Architecture

This document is the map for changing OpenSwarm without having to rediscover
the system from scratch. It explains the major runtime paths, where each piece
lives, and which files to edit for common changes.

## Runtime Shape

OpenSwarm is a Python Agency Swarm project with a vendored TypeScript TUI.
The Python side owns agents, tools, model routing, authentication status, and
FastAPI endpoints. The TUI side owns terminal UX, agent selection, local bridge
communication, and packaged binaries.

Typical local run:

1. `uv run python run.py` or `openswarm` starts the Python launcher.
2. `swarm.py` builds the Agency Swarm graph and applies local compatibility
   patches.
3. `Agency.tui(...)` starts a local FastAPI bridge.
4. `patches/patch_openswarm_model_control.py` expands that bridge to all
   registered swarms when the launched agency is an OpenSwarm registry agency.
5. The vendored TUI binary connects to that bridge and lets the user choose a
   swarm plus recipient agent.
6. User prompts stream through `/{agency}/get_response_stream`.
7. Agency Swarm routes the task to the selected swarm's orchestrator or
   specialist.

## Core Python Entry Points

| File | Purpose |
|---|---|
| `run.py` | Compatibility entry point for local runs. Delegates to `run_utils.py`. |
| `run_utils.py` | Launcher logic, setup checks, TUI binary handling, and runtime bootstrap. |
| `swarm.py` | Main agency graph: imports agents, creates them, and defines handoff/send-message flows. |
| `swarm_registry.py` | Registry of named swarms, factories, availability checks, and the Security Research Swarm graph. |
| `server.py` | FastAPI server entry point for API deployment on port `8080`. |
| `onboard.py` | Interactive setup and `--status` command for auth/service state. |
| `config.py` | Model resolution and model settings helpers shared by all agents. |
| `model_control.py` | Runtime model catalog, per-agent model switching, auth availability, and `.env` persistence. |
| `auth_registry.py` | Single source of truth for subscriptions, API keys, services, and status checks. |
| `subscription_models.py` | OpenAI Agents SDK model adapter for local Codex CLI and Claude Code subscription auth. |

## Swarms

OpenSwarm is now registry-driven. `swarm_registry.py` defines these swarms:

| Swarm ID | Display name | Purpose |
|---|---|---|
| `open-swarm` | OpenSwarm | General-purpose multi-agent workbench. |
| `security-research` | Security Research | Security research, threat intel, vulnerability analysis, labs, blogs, and visuals. |

`swarm.py:create_agency()` remains the compatibility factory for the original
OpenSwarm graph. New swarms should be added to `swarm_registry.py`, then given
their own model definitions in `model_control.py`.

## OpenSwarm Agent Graph

`swarm.py` creates one coordinator plus seven specialists:

| Agent | Folder | Model env var | Main responsibility |
|---|---|---|---|
| Orchestrator | `orchestrator/` | `ORCHESTRATOR_MODEL` | Plans and routes work. |
| General Agent | `virtual_assistant/` | `GENERAL_AGENT_MODEL` | General assistant tasks and integrations. |
| Deep Research Agent | `deep_research/` | `DEEP_RESEARCH_MODEL` | Web research and synthesis. |
| Data Analyst | `data_analyst_agent/` | `DATA_ANALYST_MODEL` | Data analysis, charts, notebooks, statistics. |
| Docs Agent | `docs_agent/` | `DOCS_AGENT_MODEL` | Documents, Markdown, PDF, DOCX. |
| Slides Agent | `slides_agent/` | `SLIDES_AGENT_MODEL` | HTML slides and PPTX generation/editing. |
| Image Agent | `image_generation_agent/` | `IMAGE_AGENT_MODEL` | Image generation/editing workflows. |
| Video Agent | `video_generation_agent/` | `VIDEO_AGENT_MODEL` | Video generation/editing workflows. |

Each agent folder has:

- `<agent>.py`: factory function that builds the Agency Swarm `Agent`.
- `instructions.md`: the system prompt for that agent.
- `tools/`: agent-specific tools.

Shared tools live in `shared_tools/`.

## Security Research Swarm

`swarm_registry.py:create_security_research_agency()` creates:

| Agent | Folder | Model env var | Main responsibility |
|---|---|---|---|
| Security Research Orchestrator | `security_research_orchestrator/` | `SECURITY_RESEARCH_ORCHESTRATOR_MODEL` | Coordinates security workstreams. |
| Security Research Lead | `security_research_lead/` | `SECURITY_RESEARCH_LEAD_MODEL` | Research quality, synthesis, evidence standards. |
| Threat Intelligence Analyst | `threat_intelligence_analyst/` | `THREAT_INTELLIGENCE_ANALYST_MODEL` | Campaigns, actors, TTPs, exploitation signals. |
| Vulnerability Researcher | `vulnerability_researcher/` | `VULNERABILITY_RESEARCHER_MODEL` | CVEs, exploitability, remediation, weakness classes. |
| OSINT Enrichment Specialist | `osint_enrichment_specialist/` | `OSINT_ENRICHMENT_SPECIALIST_MODEL` | Public-source collection and source tracking. |
| Security Lab Analyst | `security_lab_analyst/` | `SECURITY_LAB_ANALYST_MODEL` | Authorized lab analysis and reproducible notes. |
| Technical Blog Writer | `technical_blog_writer/` | `TECHNICAL_BLOG_WRITER_MODEL` | Security blog posts, reports, and documents. |
| Security Visual Designer | `security_visual_designer/` | `SECURITY_VISUAL_DESIGNER_MODEL` | Security visuals using the design profile. |

Security-specific tools live in `security_research_tools/`. Runtime research
memory defaults to `research_workspace/security/`; generated notes, resources,
progress, scratch, experiments, and outputs are ignored by Git, while templates,
design language, and reusable design assets are tracked.

## Communication Model

`swarm.py` builds two flow types:

- `SendMessage`: orchestrator-to-specialist delegation for background or
  scoped work.
- `Handoff`: control transfer between any two agents when the user should
  continue with a specialist.

The local patch in `patches/patch_agency_swarm_dual_comms.py` keeps these
communication types separate in the TUI so delegation does not look like a
handoff.

## Model Routing

Raw model IDs come from `.env`:

- `DEFAULT_MODEL`
- Per-agent env vars listed in `model_control.SWARM_AGENT_MODEL_DEFINITIONS`

Supported model ID patterns:

- `subscription/codex`: local Codex CLI subscription auth.
- `subscription/claude`: local Claude Code subscription auth.
- `subscription/<backend>/<model>`: subscription backend with a specific model
  hint.
- `gpt-5.2` or another slashless ID: direct OpenAI API model.
- `litellm/<provider>/<model>` or `<provider>/<model>`: LiteLLM-routed model.

Important files:

- `config.py` resolves raw strings into Agency Swarm model objects and builds
  provider-appropriate `ModelSettings`.
- `subscription_models.py` adapts Codex CLI and Claude Code into the OpenAI
  Agents SDK model interface.
- `model_control.py` exposes runtime model state and applies live switches per
  swarm.

When the TUI changes an agent model:

1. TUI posts to `POST /{agency}/openswarm/agent-model` for the selected swarm.
2. `patches/patch_openswarm_model_control.py` routes the request.
3. `model_control.set_agent_model(...)` updates the live `Agent`.
4. The selected model is persisted to `.env`.
5. Future runs load the same model at startup.

## Authentication And Service Status

`auth_registry.py` defines every provider and service:

- Subscriptions: Codex CLI, Claude Code.
- Model APIs: OpenAI, Anthropic, Google Gemini.
- Search/media services: SearchAPI, fal.ai, Pexels, Pixabay, Unsplash.
- Integrations: Composio.

`onboard.py --status` and the TUI use this registry to show redacted
availability. Secrets are never printed; status only reports whether credentials
or CLI logins are present.

## Web Research

Shared web research is exposed through `shared_tools/WebResearchSearch.py`.
The intended order is:

1. Subscription-backed search using Codex CLI and/or Claude Code where
   available.
2. Platform/API-backed fallback search.
3. SearchAPI and Scholar tools when configured and requested by the agent.

For research behavior, start with:

- `shared_tools/WebResearchSearch.py`
- `auth_registry.py`
- `deep_research/tools/`
- `virtual_assistant/tools/ScholarSearch.py`

## Slides And Media

The Slides Agent is the most tool-heavy specialist:

- `slides_agent/tools/InsertNewSlides.py`: planning and first-pass slide creation.
- `slides_agent/tools/ModifySlide.py`: slide HTML editing.
- `slides_agent/tools/BuildPptxFromHtmlSlides.py`: PPTX export path.
- `slides_agent/tools/ImageSearch.py`, `DownloadImage.py`, `GenerateImage.py`,
  `EnsureRasterImage.py`: image acquisition and generation.
- `slides_agent/tools/CheckSlide*.py`: rendering/overflow validation.

Image and video generation have separate agents, but the Slides Agent can call
image tools directly when building decks.

## TUI Fork

The vendored TUI lives under `packages/openswarm-tui`.

Key OpenSwarm integration points:

| File | Purpose |
|---|---|
| `packages/openswarm-tui/packages/opencode/src/agency-swarm/adapter.ts` | HTTP/SSE adapter for Agency Swarm bridge and OpenSwarm model-control APIs. |
| `packages/openswarm-tui/packages/opencode/src/cli/cmd/tui/context/agency-swarm-connection.tsx` | Bridge health and reconnect handling. |
| `packages/openswarm-tui/packages/opencode/src/cli/cmd/tui/context/openswarm-models.tsx` | OpenSwarm model state resource and live model update action. |
| `packages/openswarm-tui/packages/opencode/src/cli/cmd/tui/component/dialog-agent.tsx` | Swarm/agent picker and model management UI. |
| `packages/openswarm-tui/packages/opencode/src/cli/cmd/tui/component/prompt/index.tsx` | Prompt footer display for active agent/model. |
| `packages/openswarm-tui/FORK_CHANGELOG.md` | TUI fork-specific notes inherited from earlier TUI work. |

Build and test:

```bash
npm run test:tui
npm run build:tui
npm run test:tui:e2e
```

## Patches

Local patches live in `patches/` and are applied from `swarm.py`.

| Patch | Why it exists |
|---|---|
| `patch_utf8_file_reads.py` | Makes file reads more robust for UTF-8 content. |
| `patch_agency_swarm_dual_comms.py` | Keeps SendMessage and Handoff behavior distinct. |
| `patch_file_attachment_refs.py` | Improves file attachment references. |
| `patch_ipython_interpreter_composio.py` | Preserves Composio context in IPython tool execution. |
| `patch_openswarm_model_control.py` | Adds OpenSwarm model-control routes to the local TUI bridge. |

Before removing a patch, verify the upstream package now handles that behavior.

## Packaging And Deployment

Python package metadata:

- `pyproject.toml`
- `package.json`
- `bin/openswarm`

The published npm package includes the Python source and launcher. Python
dependencies are managed with `uv`; run Python commands through `uv run ...`.

TUI binaries are built from `packages/openswarm-tui` with:

```bash
npm run build:tui
```

The generated binary is intentionally ignored unless a release workflow uploads
it as an artifact.

## Where To Change Things

| Goal | Start here |
|---|---|
| Add or remove an agent | `swarm.py`, then the relevant agent folder. |
| Add or remove a swarm | `swarm_registry.py`, then `model_control.py`. |
| Rename or repurpose an agent | Agent folder, `<agent>.py`, `instructions.md`, and `swarm.py`. |
| Change agent default models | `.env`, `model_control.py`, and agent env vars. |
| Add a curated model option | `model_control.MODEL_OPTIONS` and `_MODEL_AUTH_IDS`. |
| Add a new auth/service key | `auth_registry.AUTH_DEFINITIONS`. |
| Change onboarding flow | `onboard.py`. |
| Change TUI model display | `openswarm-models.tsx`, `dialog-agent.tsx`, `prompt/index.tsx`. |
| Change server API behavior | `server.py`, `patch_openswarm_model_control.py`, Agency Swarm FastAPI integration. |
| Change research behavior | `shared_tools/WebResearchSearch.py` and `deep_research/`. |
| Change security research behavior | `security_research_tools/`, security agent folders, and `research_workspace/security/`. |
| Change slide generation | `slides_agent/tools/` and `slides_agent/instructions.md`. |
| Change shared context | `shared_instructions.md`. |

## Verification Checklist

Use focused checks while developing, then broader checks before committing:

```bash
uv run python -m py_compile config.py model_control.py swarm.py server.py
uv run pytest tests/test_model_control.py
npm run test:tui
npm run build:tui
npm run test:tui:e2e
```

Known local environment note: document/PDF tooling can require native Cairo and
GObject libraries through WeasyPrint. Missing native libraries can produce
warnings during agency construction even when non-document workflows still run.
