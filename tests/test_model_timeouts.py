from __future__ import annotations

import asyncio
import importlib
import subprocess

import pytest

import subscription_models
from timeout_config import get_model_timeout_seconds, parse_model_timeout_seconds


@pytest.mark.parametrize("raw", [None, "", " ", "0", "none", "disabled", "false", "off", "no", "-1", "abc"])
def test_parse_model_timeout_disabled_values(raw):
    assert parse_model_timeout_seconds(raw) is None


@pytest.mark.parametrize(("raw", "expected"), [("1", 1), ("600", 600), (" 900 ", 900)])
def test_parse_model_timeout_positive_seconds(raw, expected):
    assert parse_model_timeout_seconds(raw) == expected


def test_get_model_timeout_default_is_disabled(monkeypatch):
    monkeypatch.delenv("OPENSWARM_MODEL_TIMEOUT_SECONDS", raising=False)

    assert get_model_timeout_seconds() is None


def test_subscription_model_uses_shared_timeout_env(monkeypatch):
    monkeypatch.setenv("OPENSWARM_MODEL_TIMEOUT_SECONDS", "600")

    model = subscription_models.SubscriptionModel("codex")

    assert model.timeout_seconds == 600


def test_subscription_model_default_has_no_hard_timeout(monkeypatch):
    monkeypatch.delenv("OPENSWARM_MODEL_TIMEOUT_SECONDS", raising=False)

    model = subscription_models.SubscriptionModel("claude")

    assert model.timeout_seconds is None


def test_subscription_run_command_passes_none_timeout(monkeypatch):
    seen: dict[str, object] = {}

    def fake_run(*args, **kwargs):
        seen["timeout"] = kwargs["timeout"]
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr(subscription_models.subprocess, "run", fake_run)

    subscription_models._run_command(["codex"], "prompt", None)

    assert seen["timeout"] is None


def test_subscription_timeout_error_mentions_env(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(subscription_models.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="OPENSWARM_MODEL_TIMEOUT_SECONDS"):
        subscription_models._run_command(["codex"], "prompt", 3)


def test_insert_slides_model_worker_default_has_no_hard_timeout(monkeypatch):
    insert_new_slides = importlib.import_module("slides_agent.tools.InsertNewSlides")

    async def immediate():
        return "ok"

    monkeypatch.setattr(insert_new_slides, "get_model_timeout_seconds", lambda: None)

    assert insert_new_slides._run_awaitable(immediate()) == "ok"


def test_insert_slides_model_worker_honors_explicit_timeout(monkeypatch):
    insert_new_slides = importlib.import_module("slides_agent.tools.InsertNewSlides")

    async def slow():
        await asyncio.sleep(0.05)
        return "late"

    monkeypatch.setattr(insert_new_slides, "get_model_timeout_seconds", lambda: 0.001)

    with pytest.raises(TimeoutError, match="OPENSWARM_MODEL_TIMEOUT_SECONDS"):
        insert_new_slides._run_awaitable(slow())
