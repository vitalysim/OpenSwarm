"""Authentication provider and service registry for OpenSwarm.

The registry is the single source of truth for model backends, subscription
CLIs, and optional service API keys. It intentionally never prints secret
values; it only reports whether the required credentials are present.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import shutil
import subprocess
from typing import Literal


AuthCategory = Literal["subscription", "model_api", "service", "integration"]
AuthState = Literal["available", "configured", "missing", "error"]


@dataclass(frozen=True)
class AuthDefinition:
    id: str
    name: str
    category: AuthCategory
    capabilities: tuple[str, ...]
    env_keys: tuple[str, ...] = ()
    setup_url: str | None = None
    login_command: str | None = None
    status_command: tuple[str, ...] | None = None
    default_model: str | None = None
    description: str = ""


@dataclass(frozen=True)
class AuthStatus:
    id: str
    name: str
    category: AuthCategory
    state: AuthState
    detail: str
    capabilities: tuple[str, ...]
    env_keys: tuple[str, ...] = ()
    setup_hint: str | None = None
    default_model: str | None = None


AUTH_DEFINITIONS: tuple[AuthDefinition, ...] = (
    AuthDefinition(
        id="codex",
        name="Codex CLI",
        category="subscription",
        capabilities=("text", "tools"),
        status_command=("codex", "login", "status"),
        login_command="codex login",
        default_model="subscription/codex",
        description="Uses local Codex CLI ChatGPT subscription auth.",
    ),
    AuthDefinition(
        id="claude",
        name="Claude Code",
        category="subscription",
        capabilities=("text", "tools"),
        status_command=("claude", "auth", "status"),
        login_command="claude auth login",
        default_model="subscription/claude",
        description="Uses local Claude Code subscription auth.",
    ),
    AuthDefinition(
        id="openai_api",
        name="OpenAI API",
        category="model_api",
        capabilities=("text", "tools", "images", "video"),
        env_keys=("OPENAI_API_KEY",),
        setup_url="https://platform.openai.com/api-keys",
        default_model="gpt-5.2",
        description="Direct OpenAI API key for GPT models, Images, and Sora.",
    ),
    AuthDefinition(
        id="anthropic_api",
        name="Anthropic API",
        category="model_api",
        capabilities=("text", "tools"),
        env_keys=("ANTHROPIC_API_KEY",),
        setup_url="https://console.anthropic.com/settings/keys",
        default_model="litellm/anthropic/claude-sonnet-4-6",
        description="Direct Anthropic API key through LiteLLM.",
    ),
    AuthDefinition(
        id="google_api",
        name="Google Gemini API",
        category="model_api",
        capabilities=("text", "images", "video"),
        env_keys=("GOOGLE_API_KEY",),
        setup_url="https://aistudio.google.com/app/apikey",
        default_model="litellm/gemini/gemini-3-flash",
        description="Gemini model API, Gemini image models, and Veo video.",
    ),
    AuthDefinition(
        id="searchapi",
        name="SearchAPI",
        category="service",
        capabilities=("search", "scholar_search", "product_search"),
        env_keys=("SEARCH_API_KEY",),
        setup_url="https://www.searchapi.io",
        description="Web, Scholar, and product search tools.",
    ),
    AuthDefinition(
        id="fal",
        name="fal.ai",
        category="service",
        capabilities=("video", "background_removal"),
        env_keys=("FAL_KEY",),
        setup_url="https://fal.ai/dashboard/keys",
        description="Seedance video, video editing, and background removal.",
    ),
    AuthDefinition(
        id="pexels",
        name="Pexels",
        category="service",
        capabilities=("stock_images",),
        env_keys=("PEXELS_API_KEY",),
        setup_url="https://www.pexels.com/api",
        description="Stock photo search for the Slides Agent.",
    ),
    AuthDefinition(
        id="pixabay",
        name="Pixabay",
        category="service",
        capabilities=("stock_images",),
        env_keys=("PIXABAY_API_KEY",),
        setup_url="https://pixabay.com/api/docs",
        description="Stock image search for the Slides Agent.",
    ),
    AuthDefinition(
        id="unsplash",
        name="Unsplash",
        category="service",
        capabilities=("stock_images",),
        env_keys=("UNSPLASH_ACCESS_KEY",),
        setup_url="https://unsplash.com/developers",
        description="Stock image search for the Slides Agent.",
    ),
    AuthDefinition(
        id="composio",
        name="Composio",
        category="integration",
        capabilities=("integrations", "email", "calendar", "slack", "crm"),
        env_keys=("COMPOSIO_API_KEY", "COMPOSIO_USER_ID"),
        setup_url="https://composio.dev",
        description="External app integrations such as Gmail, Slack, HubSpot, and GitHub.",
    ),
)


CATEGORY_LABELS: dict[str, str] = {
    "subscription": "Model subscriptions",
    "model_api": "Model/API providers",
    "service": "Add-on services",
    "integration": "External integrations",
}


def get_definition(auth_id: str) -> AuthDefinition | None:
    return next((item for item in AUTH_DEFINITIONS if item.id == auth_id), None)


def list_definitions(category: AuthCategory | None = None) -> list[AuthDefinition]:
    if category is None:
        return list(AUTH_DEFINITIONS)
    return [item for item in AUTH_DEFINITIONS if item.category == category]


def check_auth_status(definition: AuthDefinition, *, live: bool = True) -> AuthStatus:
    if definition.status_command and live:
        return _check_command_status(definition)
    return _check_env_status(definition)


def get_auth_statuses(*, live: bool = True) -> list[AuthStatus]:
    return [check_auth_status(item, live=live) for item in AUTH_DEFINITIONS]


def build_status_summary(*, live: bool = True) -> str:
    lines: list[str] = ["Authentication status:"]
    statuses = get_auth_statuses(live=live)
    for category, label in CATEGORY_LABELS.items():
        lines.append(f"{label}:")
        for status in [item for item in statuses if item.category == category]:
            marker = _state_marker(status.state)
            detail = f" - {status.detail}" if status.detail else ""
            lines.append(f"  {marker} {status.name}{detail}")
    return "\n".join(lines)


def missing_setup_hints(*, live: bool = True) -> list[str]:
    hints: list[str] = []
    for status in get_auth_statuses(live=live):
        if status.state in {"missing", "error"} and status.setup_hint:
            hints.append(f"{status.name}: {status.setup_hint}")
    return hints


def env_key_status(keys: tuple[str, ...]) -> tuple[bool, list[str]]:
    missing = [key for key in keys if not os.getenv(key)]
    return not missing, missing


def _check_env_status(definition: AuthDefinition) -> AuthStatus:
    if not definition.env_keys:
        return AuthStatus(
            id=definition.id,
            name=definition.name,
            category=definition.category,
            state="missing",
            detail="no status check configured",
            capabilities=definition.capabilities,
            env_keys=definition.env_keys,
            setup_hint=definition.login_command or definition.setup_url,
            default_model=definition.default_model,
        )

    ok, missing = env_key_status(definition.env_keys)
    if ok:
        return AuthStatus(
            id=definition.id,
            name=definition.name,
            category=definition.category,
            state="configured",
            detail=f"configured via {', '.join(definition.env_keys)}",
            capabilities=definition.capabilities,
            env_keys=definition.env_keys,
            setup_hint=definition.setup_url,
            default_model=definition.default_model,
        )
    return AuthStatus(
        id=definition.id,
        name=definition.name,
        category=definition.category,
        state="missing",
        detail=f"missing {', '.join(missing)}",
        capabilities=definition.capabilities,
        env_keys=definition.env_keys,
        setup_hint=definition.setup_url,
        default_model=definition.default_model,
    )


def _check_command_status(definition: AuthDefinition) -> AuthStatus:
    assert definition.status_command is not None
    executable = definition.status_command[0]
    if not shutil.which(executable):
        return AuthStatus(
            id=definition.id,
            name=definition.name,
            category=definition.category,
            state="missing",
            detail=f"{executable} command not found",
            capabilities=definition.capabilities,
            env_keys=definition.env_keys,
            setup_hint=definition.login_command,
            default_model=definition.default_model,
        )

    try:
        result = subprocess.run(
            list(definition.status_command),
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        return AuthStatus(
            id=definition.id,
            name=definition.name,
            category=definition.category,
            state="error",
            detail=str(exc),
            capabilities=definition.capabilities,
            env_keys=definition.env_keys,
            setup_hint=definition.login_command,
            default_model=definition.default_model,
        )

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    combined = "\n".join(part for part in (stdout, stderr) if part)
    if definition.id == "codex":
        if result.returncode == 0 and "Logged in" in combined:
            return _available_command_status(definition, combined)
    elif definition.id == "claude":
        try:
            payload = json.loads(stdout)
            if result.returncode == 0 and payload.get("loggedIn"):
                auth_method = payload.get("authMethod") or "authenticated"
                subscription = payload.get("subscriptionType")
                detail = auth_method if not subscription else f"{auth_method}, {subscription}"
                return _available_command_status(definition, detail)
        except json.JSONDecodeError:
            pass

    detail = combined or f"{executable} status check failed"
    return AuthStatus(
        id=definition.id,
        name=definition.name,
        category=definition.category,
        state="missing" if result.returncode != 0 else "error",
        detail=_one_line(detail),
        capabilities=definition.capabilities,
        env_keys=definition.env_keys,
        setup_hint=definition.login_command,
        default_model=definition.default_model,
    )


def _available_command_status(definition: AuthDefinition, detail: str) -> AuthStatus:
    return AuthStatus(
        id=definition.id,
        name=definition.name,
        category=definition.category,
        state="available",
        detail=_one_line(detail),
        capabilities=definition.capabilities,
        env_keys=definition.env_keys,
        setup_hint=definition.login_command,
        default_model=definition.default_model,
    )


def _one_line(value: str, limit: int = 120) -> str:
    line = " ".join(value.split())
    return line if len(line) <= limit else f"{line[: limit - 3]}..."


def _state_marker(state: AuthState) -> str:
    return {
        "available": "[available]",
        "configured": "[configured]",
        "missing": "[missing]",
        "error": "[error]",
    }[state]
