"""OpenSwarm timeout configuration helpers."""

from __future__ import annotations

import os


MODEL_TIMEOUT_ENV_VAR = "OPENSWARM_MODEL_TIMEOUT_SECONDS"
_DISABLED_VALUES = {"", "0", "none", "disabled", "false", "off", "no"}


def parse_model_timeout_seconds(raw: str | None) -> int | None:
    """Parse a model-call timeout value.

    None means OpenSwarm should not impose a hard model-call timeout.
    """
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in _DISABLED_VALUES:
        return None
    try:
        seconds = int(value)
    except ValueError:
        return None
    return seconds if seconds > 0 else None


def normalize_model_timeout_seconds(value: int | None) -> int | None:
    """Normalize programmatic timeout overrides."""
    return value if value and value > 0 else None


def get_model_timeout_seconds() -> int | None:
    """Return the configured OpenSwarm model-call timeout.

    By default, OpenSwarm does not impose a hard timeout on model calls. Users
    can set OPENSWARM_MODEL_TIMEOUT_SECONDS to a positive integer to opt into
    one.
    """
    return parse_model_timeout_seconds(os.getenv(MODEL_TIMEOUT_ENV_VAR))


def describe_model_timeout_setting(timeout_seconds: int | None) -> str:
    if timeout_seconds is None:
        return f"no OpenSwarm hard timeout ({MODEL_TIMEOUT_ENV_VAR} is unset/disabled)"
    return f"{timeout_seconds} seconds ({MODEL_TIMEOUT_ENV_VAR})"
