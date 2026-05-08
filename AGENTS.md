# OpenSwarm — Customization Guide

This file gives coding agents (Cursor, Claude Code, Codex, etc.) everything they need to understand and customize this swarm. Read it before making any changes.

---

## What is OpenSwarm?

OpenSwarm is a multi-agent AI team you can fork and reshape into any kind of swarm you need — SEO, sales, research, finance, customer support, or anything else. Each agent is a specialist. They collaborate through a shared orchestrator.

---

## Folder Structure

```
swarm.py                  ← main config: imports all agents, defines how they connect
shared_instructions.md    ← context shared across every agent
run.py                    ← CLI entry point (terminal demo)
server.py                 ← API entry point (FastAPI server)

orchestrator/
  orchestrator.py         ← agent definition
  instructions.md         ← system prompt

data_analyst_agent/
  data_analyst_agent.py
  instructions.md
  tools/                  ← custom tools for this agent

docs_agent/
  docs_agent.py
  instructions.md
  tools/

slides_agent/
  slides_agent.py
  instructions.md
  tools/

image_generation_agent/
  image_generation_agent.py
  instructions.md
  tools/

video_generation_agent/
  video_generation_agent.py
  instructions.md
  tools/

deep_research/
  deep_research.py
  instructions.md
  tools/

virtual_assistant/
  virtual_assistant.py
  instructions.md
  tools/

shared_tools/             ← tools available to all agents (Composio integrations, etc.)
openswarm_skills/         ← provider-neutral project skills consumed by all models
model_failover.py         ← request-local fallback for quota/rate/usage model failures

packages/openswarm-tui/   ← vendored AgentSwarm/OpenCode TUI source controlled by this repo
```

---

## How Agents Connect (`swarm.py`)

`swarm.py` is the only file you need to edit when adding, removing, or rewiring agents. It:

1. Imports a `create_*` factory function from each agent folder
2. Instantiates all agents
3. Defines communication flows — who can talk to whom

The default pattern is **orchestrator-to-all**: the orchestrator can send messages to every specialist, and all agents can hand off to each other.

---

## Patched TUI Fork

OpenSwarm controls its own AgentSwarm/OpenCode TUI fork under `packages/openswarm-tui/`. This is not a read-only upstream dependency. We patch it for OpenSwarm-specific behavior such as swarm selection, per-agent model visibility, subscription-backed model routing, and project working-directory controls.

When changing TUI source:

- Edit the vendored source under `packages/openswarm-tui/packages/opencode/`.
- Run `npm run build:tui` from the repo root so the local `dist/.../bin/agentswarm` binary includes the change.
- Restart OpenSwarm after rebuilding; otherwise the running TUI may still use an older binary.
- Do not commit generated TUI binaries (`packages/openswarm-tui/**/dist/**` or root `openswarm-tui-*`) unless the user explicitly asks for release artifacts.
- Validate TUI behavior with targeted Bun tests and, for visible terminal behavior, the Agent Swarm TUI E2E tests.

The Python launcher prefers the freshly built local TUI binary when present. If the binary is older than key TUI source files, `run_utils.py` prints a warning to rebuild with `npm run build:tui`.

---

## How to Customize

To build your own swarm from this repo:

1. **Fork and rename** the repo (e.g., `seo-swarm`)
2. **Decide which agents to keep, rename, or replace**
   - Rename the folder and its files to match the new agent's purpose
   - Update `instructions.md` with the new system prompt
   - Update `swarm.py` to import and register the renamed agent
3. **Add or remove tools** inside each agent's `tools/` folder
4. **Update `shared_instructions.md`** with any context all agents should share
5. **Run** with `uv run python run.py`

### Example prompt to give your coding agent

> "Turn this into an SEO optimization swarm. The Research Agent becomes an SEO Keyword Planner, the Docs Agent becomes a Blog Post Writer, the Data Analyst becomes an SEO Analytics Agent (Google Search Console + GA4), and the General Agent handles technical SEO like schema markup and site audits. Keep the orchestrator and shared tools as-is."

The coding agent will read this file, understand the structure, and make the right changes automatically.

---

## Current Agents

| Agent | Purpose |
|---|---|
| `orchestrator` | Routes tasks to the right specialist |
| `virtual_assistant` | Email, calendar, Slack, file management |
| `deep_research` | Web research and synthesis |
| `data_analyst_agent` | Data analysis, visualization, statistical modeling |
| `docs_agent` | Document creation and editing |
| `slides_agent` | PowerPoint / HTML slide generation |
| `image_generation_agent` | AI image generation and editing |
| `video_generation_agent` | AI video generation and editing |

---

## Key Conventions

- Each agent folder has one `<name>.py` file and one `instructions.md`
- `instructions.md` is the agent's system prompt — edit it to change behavior
- Tools live in `tools/` and are auto-loaded by the agent definition
- `shared_tools/` contains Composio-powered integrations (Gmail, Slack, GitHub, etc.) available to all agents
- OpenSwarm skills live in `openswarm_skills/<skill-name>/SKILL.md` and are loaded through `ListOpenSwarmSkills` / `LoadOpenSwarmSkill`, not provider-native global skill folders.
- OpenSwarm skills v1 are instructions and read-only resources only; do not execute scripts from skill folders.
- Models are configured via `DEFAULT_MODEL` and optional per-agent model env vars in `.env` — never hardcoded
- OpenSwarm does not hard-timeout model calls by default. `OPENSWARM_MODEL_TIMEOUT_SECONDS` can opt into a positive timeout; blank/`0`/`none` disables the OpenSwarm-side model timeout.
- `model_failover.py` wraps configured models and retries only clear quota/rate/usage-limit failures using `OPENSWARM_MODEL_FAILOVER_ORDER`. Failover is temporary per request and must not persist fallback choices to `.env`.
- Use `uv` for Python environments and dependency installation:
  - `uv sync` creates/updates the repo-local `.venv`
  - `uv sync --group dev` includes test dependencies
  - `uv run python ...` runs commands inside that environment
  - Do not install project dependencies with global `pip`
- Local subscription model IDs are supported for reasoning agents:
  - `subscription/codex` uses the local Codex CLI login
  - `subscription/claude` uses the local Claude Code login
- Web research uses `WebResearchSearch`, which can use Codex/Claude Code subscription search first and OpenAI/SearchAPI as fallback (`WEB_SEARCH_MODE`, `WEB_SEARCH_PROVIDER_ORDER`, `WEB_SEARCH_DEEP_MIX`)
- Check model/API/service authentication with `uv run python onboard.py --status`
- The terminal UI fork lives in `packages/openswarm-tui`; after TUI source edits, rebuild with `npm run build:tui` before testing or launching.

Before proceeding with agent creation, please read the following instructions carefully:

- `.cursor/rules/agency-swarm-workflow.mdc` - your primary guide for creating agents and agencies

The following files can be read on demand, depending on the task at hand:

- `.cursor/commands/add-mcp.md` - how to add MCP servers to an agent
- `.cursor/commands/mcp-code-exec.md` - how to convert an MCP server into the Code Execution Pattern (progressive tool disclosure, 98% token reduction)
- `.cursor/commands/write-instructions.md` - how to write effective instructions for AI agents
- `.cursor/commands/create-prd.md` - how to create a PRD for an agent (use for complex multi agent systems)
