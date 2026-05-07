#!/usr/bin/env python3
"""OpenSwarm interactive setup wizard.

Run directly:   python onboard.py
Auto-launched:  python run.py  (when no provider key is found)
"""

import argparse
import getpass
import sys
from pathlib import Path

from dotenv import dotenv_values, set_key
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

try:
    import questionary
    from questionary import Choice, Style as QStyle
    import questionary.prompts.common as _qc_common

    # Swap filled circle → checkmark for selected state.
    _qc_common.INDICATOR_SELECTED = "✓"

    _HAS_QUESTIONARY = True
except ImportError:
    _HAS_QUESTIONARY = False

from auth_registry import AUTH_DEFINITIONS, CATEGORY_LABELS, get_auth_statuses, list_definitions

console = Console()

ENV_PATH = Path(__file__).parent / ".env"

# ── questionary theme ─────────────────────────────────────────────────────────
_QSTYLE = None
if _HAS_QUESTIONARY:
    _QSTYLE = QStyle([
        ("qmark",       "fg:#4fc3f7 bold"),
        ("question",    "bold"),
        ("answer",      "fg:#4fc3f7 bold"),
        ("pointer",     "fg:#4fc3f7 bold noreverse"),
        ("highlighted", "noreverse"),
        ("selected",    "fg:#4fc3f7 bold noreverse"),
        ("separator",   "fg:#555555 noreverse"),
        ("instruction", "fg:#555555 italic noreverse"),
        ("text",        "noreverse"),
    ])

# ── provider definitions ──────────────────────────────────────────────────────
PROVIDERS = [
    {
        "name": item.name,
        "env_key": item.env_keys[0],
        "default_model": item.default_model,
        "url": item.setup_url,
    }
    for item in list_definitions("model_api")
    if item.env_keys and item.default_model and item.setup_url
]

AGENT_MODEL_ENV_VARS = [
    ("Orchestrator", "ORCHESTRATOR_MODEL"),
    ("General Agent", "GENERAL_AGENT_MODEL"),
    ("Deep Research Agent", "DEEP_RESEARCH_MODEL"),
    ("Data Analyst", "DATA_ANALYST_MODEL"),
    ("Docs Agent", "DOCS_AGENT_MODEL"),
    ("Slides Agent", "SLIDES_AGENT_MODEL"),
    ("Image Agent", "IMAGE_AGENT_MODEL"),
    ("Video Agent", "VIDEO_AGENT_MODEL"),
]

SUBSCRIPTION_FIRST_MODELS = {
    "DEFAULT_MODEL": "subscription/codex",
    "ORCHESTRATOR_MODEL": "subscription/codex",
    "GENERAL_AGENT_MODEL": "subscription/codex",
    "DATA_ANALYST_MODEL": "subscription/codex",
    "DEEP_RESEARCH_MODEL": "subscription/claude",
    "DOCS_AGENT_MODEL": "subscription/claude",
    "SLIDES_AGENT_MODEL": "subscription/claude",
    "IMAGE_AGENT_MODEL": "subscription/claude",
    "VIDEO_AGENT_MODEL": "subscription/claude",
}

MODEL_OPTIONS = [
    ("Codex subscription", "subscription/codex"),
    ("Claude Code subscription", "subscription/claude"),
    ("OpenAI API", "gpt-5.2"),
    ("Anthropic API", "litellm/anthropic/claude-sonnet-4-6"),
    ("Google Gemini API", "litellm/gemini/gemini-3-flash"),
]

# ── ui helpers ────────────────────────────────────────────────────────────────

def _step(n: int, label: str) -> None:
    console.print()
    console.print(Rule(f"[bold]Step {n}  ·  {label}[/bold]", style="cyan"))
    console.print()


def _ask_select(message: str, choices: list) -> object:
    if _HAS_QUESTIONARY:
        return questionary.select(message, choices=choices, style=_QSTYLE).ask()
    # plain fallback
    titles = [c.title if isinstance(c, Choice) else c for c in choices]
    values = [c.value if isinstance(c, Choice) else c for c in choices]
    console.print(f"\n[bold]{message}[/bold]")
    for i, title in enumerate(titles, 1):
        console.print(f"  [cyan]{i}.[/cyan] {title}")
    while True:
        raw = input("Enter number: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(titles):
            return values[int(raw) - 1]
        console.print("[red]Invalid choice, try again.[/red]")


def _ask_checkbox(message: str, choices: list) -> list:
    if _HAS_QUESTIONARY:
        return questionary.checkbox(message, choices=choices, style=_QSTYLE, pointer="❯").ask() or []
    # plain fallback — comma-separated numbers
    titles = [c.title if isinstance(c, Choice) else c for c in choices]
    values = [c.value if isinstance(c, Choice) else c for c in choices]
    console.print(f"\n[bold]{message}[/bold]")
    console.print("[dim]  Enter comma-separated numbers, or press Enter to skip[/dim]")
    for i, title in enumerate(titles, 1):
        console.print(f"  [cyan]{i}.[/cyan] {title}")
    raw = input("Selection: ").strip()
    if not raw:
        return []
    result = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit() and 1 <= int(part) <= len(titles):
            result.append(values[int(part) - 1])
    return result


def _ask_secret(label: str, url: str) -> str:
    console.print(f"  [dim]Get yours at[/dim] [link={url}]{url}[/link]")
    if _HAS_QUESTIONARY:
        val = questionary.password(f"  {label}: ", style=_QSTYLE).ask()
        return (val or "").strip()
    return getpass.getpass(f"  {label}: ").strip()


def _ask_confirm(message: str, default: bool = True) -> bool:
    if _HAS_QUESTIONARY:
        return questionary.confirm(message, default=default, style=_QSTYLE).ask()
    prompt = f"{message} [{'Y/n' if default else 'y/N'}]: "
    raw = input(prompt).strip().lower()
    return default if not raw else raw in ("y", "yes")


def _write_env(updates: dict) -> None:
    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")
    for key, value in updates.items():
        set_key(str(ENV_PATH), key, value or "")


def _print_status_table(live: bool = True) -> None:
    statuses = get_auth_statuses(live=live)
    table = Table(title="Authentication Status", box=box.SIMPLE, padding=(0, 1))
    table.add_column("Category", style="dim", no_wrap=True)
    table.add_column("Provider")
    table.add_column("Status")
    table.add_column("Details")
    table.add_column("Capabilities")
    for status in statuses:
        table.add_row(
            CATEGORY_LABELS.get(status.category, status.category),
            status.name,
            _status_markup(status.state),
            status.detail,
            ", ".join(status.capabilities),
        )
    console.print(table)


def _status_markup(state: str) -> str:
    if state == "available":
        return "[green]available[/green]"
    if state == "configured":
        return "[cyan]configured[/cyan]"
    if state == "missing":
        return "[yellow]missing[/yellow]"
    return "[red]error[/red]"


def _model_choice(message: str, default_value: str | None = None) -> str:
    choices = []
    for title, value in MODEL_OPTIONS:
        suffix = " (current)" if value == default_value else ""
        choices.append(Choice(title=f"{title}  [{value}]{suffix}", value=value))
    return _ask_select(message, choices)


def _configure_custom_models(existing: dict) -> dict[str, str]:
    updates: dict[str, str] = {}
    current_default = existing.get("DEFAULT_MODEL", "subscription/codex")
    updates["DEFAULT_MODEL"] = _model_choice("Choose the default model backend:", current_default)
    for agent_name, env_key in AGENT_MODEL_ENV_VARS:
        current = existing.get(env_key, updates["DEFAULT_MODEL"])
        use_default = _ask_confirm(f"  Use DEFAULT_MODEL for {agent_name}?", default=True)
        if use_default:
            updates[env_key] = ""
            continue
        updates[env_key] = _model_choice(f"Choose model backend for {agent_name}:", current)
    return updates


def _configure_api_primary(existing: dict) -> dict[str, str]:
    updates: dict[str, str] = {}
    provider_choices = [Choice(title=p["name"], value=p) for p in PROVIDERS]
    provider = _ask_select("Choose your primary API provider:", provider_choices)
    _collect_key(provider["env_key"], f"{provider['name']} API key", provider["url"], existing, updates)
    updates["DEFAULT_MODEL"] = provider["default_model"]
    for _, env_key in AGENT_MODEL_ENV_VARS:
        updates[env_key] = ""
    return updates


def _configure_optional_services(existing: dict, updates: dict[str, str]) -> None:
    candidates = [item for item in AUTH_DEFINITIONS if item.env_keys]
    choices = [
        Choice(
            title=f"{item.name}  -  {item.description or ', '.join(item.capabilities)}",
            value=item.id,
        )
        for item in candidates
    ]
    selected_ids = _ask_checkbox("Select API keys or services to add/update:", choices)
    selected = [item for item in candidates if item.id in selected_ids]
    for item in selected:
        console.print(f"\n  [bold]{item.name}[/bold]")
        for env_key in item.env_keys:
            _collect_key(env_key, env_key, item.setup_url or "https://example.com", existing, updates)


def _collect_key(env_key: str, label: str, url: str, existing: dict, updates: dict[str, str]) -> None:
    if updates.get(env_key):
        console.print(f"  [dim]{env_key} is already configured in this setup.[/dim]")
        return
    existing_val = existing.get(env_key, "")
    if existing_val:
        console.print(f"  [dim]{env_key} is already configured.[/dim]")
        if not _ask_confirm("  Update it?", default=False):
            updates[env_key] = existing_val
            return
    val = _ask_secret(label, url)
    if val:
        updates[env_key] = val


# ── main wizard ───────────────────────────────────────────────────────────────

def run_onboarding() -> None:
    console.print()
    console.print(Panel.fit(
        "[bold cyan]OpenSwarm[/bold cyan]  [dim]—  open-source multi-agent AI team[/dim]\n"
        "[dim]Let's get you set up in a few steps.[/dim]",
        border_style="cyan",
        padding=(1, 4),
    ))

    existing = dotenv_values(str(ENV_PATH)) if ENV_PATH.exists() else {}
    updates: dict[str, str] = {}

    _step(1, "Current Authentication")
    _print_status_table(live=True)

    _step(2, "Model Routing")
    preset = _ask_select(
        "Choose a model routing preset:",
        [
            Choice(
                title="Subscriptions first  -  Codex for coordination/analysis, Claude for content-heavy agents",
                value="subscriptions",
            ),
            Choice(title="API keys only  -  OpenAI/Anthropic/Gemini API provider", value="api"),
            Choice(title="Custom  -  choose DEFAULT_MODEL and per-agent overrides", value="custom"),
        ],
    )
    if preset == "subscriptions":
        updates.update(SUBSCRIPTION_FIRST_MODELS)
        console.print("[green]Selected subscription-first routing.[/green]")
        console.print("[dim]Use `codex login` and `claude auth login` if either subscription status is missing.[/dim]")
    elif preset == "api":
        updates.update(_configure_api_primary(existing))
    else:
        updates.update(_configure_custom_models(existing))

    _step(3, "API Keys and Services  [dim](optional)[/dim]")
    _configure_optional_services(existing, updates)

    # ── write .env ────────────────────────────────────────────────────────────
    _write_env(updates)

    # ── summary ───────────────────────────────────────────────────────────────
    console.print()
    console.print(Rule("[bold green]Setup complete[/bold green]", style="green"))
    console.print()

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column(style="dim", no_wrap=True)
    table.add_column()
    table.add_row("DEFAULT_MODEL", f"[cyan]{updates.get('DEFAULT_MODEL', existing.get('DEFAULT_MODEL', '(unchanged)'))}[/cyan]")
    table.add_row(".env",     f"[cyan]{ENV_PATH}[/cyan]")
    saved = [k for k, v in updates.items() if v and not k.startswith("DEFAULT_")]
    if saved:
        table.add_row("Keys saved", f"[cyan]{', '.join(saved)}[/cyan]")
    console.print(table)

    console.print()
    console.print(Panel(
        "[bold]python swarm.py[/bold]  [dim]launch interactive terminal[/dim]\n"
        "[bold]python server.py[/bold]  [dim]start the API server[/dim]",
        border_style="green",
        padding=(0, 3),
    ))
    console.print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenSwarm setup and authentication status.")
    parser.add_argument("--status", action="store_true", help="Show authentication status and exit.")
    args = parser.parse_args()
    try:
        if args.status:
            _print_status_table(live=True)
        else:
            run_onboarding()
    except KeyboardInterrupt:
        console.print("\n\n[dim]Setup cancelled.[/dim]\n")
        sys.exit(0)
