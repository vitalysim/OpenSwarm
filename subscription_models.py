"""Subprocess-backed model adapters for local subscription CLIs.

These adapters let Agency Swarm use Claude Code or Codex CLI subscription auth
as a model backend. The CLI is asked to return a strict JSON decision. The
adapter converts that decision into OpenAI Agents SDK output items so the normal
tool and handoff loop remains in charge.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import re
import subprocess
import time
import uuid
from typing import Any, Literal

from agents.items import ModelResponse
from agents.models.interface import Model, ModelTracing
from agents.usage import Usage
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseContentPartAddedEvent,
    ResponseContentPartDoneEvent,
    ResponseCreatedEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionToolCall,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseTextDeltaEvent,
    ResponseUsage,
)
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

from timeout_config import (
    MODEL_TIMEOUT_ENV_VAR,
    get_model_timeout_seconds,
    normalize_model_timeout_seconds,
)


SubscriptionBackend = Literal["codex", "claude"]


@dataclass(frozen=True)
class _CliResult:
    text: str
    usage: Usage
    raw: Any


class SubscriptionModel(Model):
    """OpenAI Agents SDK model wrapper around Codex or Claude Code CLI."""

    def __init__(self, backend: SubscriptionBackend, *, model: str | None = None, timeout_seconds: int | None = None):
        self.backend = backend
        self.model = model
        self.timeout_seconds = (
            normalize_model_timeout_seconds(timeout_seconds)
            if timeout_seconds is not None
            else get_model_timeout_seconds()
        )

    async def get_response(
        self,
        system_instructions,
        input,
        model_settings,
        tools,
        output_schema,
        handoffs,
        tracing,
        *,
        previous_response_id,
        conversation_id,
        prompt,
    ) -> ModelResponse:
        protocol_prompt = _build_protocol_prompt(
            system_instructions=system_instructions,
            input_items=input,
            tools=tools,
            handoffs=handoffs,
            output_schema=output_schema,
        )
        result = await asyncio.to_thread(self._run_cli, protocol_prompt)
        decision = _parse_decision(result.text)
        output = _decision_to_output(decision)
        return ModelResponse(output=output, usage=result.usage, response_id=None)

    def stream_response(
        self,
        system_instructions,
        input,
        model_settings,
        tools,
        output_schema,
        handoffs,
        tracing,
        *,
        previous_response_id=None,
        conversation_id=None,
        prompt=None,
    ):
        async def _buffered_stream():
            response_id = f"resp_{uuid.uuid4().hex}"
            sequence_number = 0
            yield ResponseCreatedEvent(
                response=_response_shell(response_id, self.model_name, status="in_progress"),
                type="response.created",
                sequence_number=sequence_number,
            )
            sequence_number += 1

            model_response = await self.get_response(
                system_instructions,
                input,
                model_settings,
                tools,
                output_schema,
                handoffs,
                tracing,
                previous_response_id=previous_response_id,
                conversation_id=conversation_id,
                prompt=prompt,
            )

            async for event in _stream_model_response(
                model_response=model_response,
                response_id=response_id,
                model_name=self.model_name,
                starting_sequence_number=sequence_number,
            ):
                yield event

        return _buffered_stream()

    @property
    def model_name(self) -> str:
        return f"subscription/{self.backend}" + (f"/{self.model}" if self.model else "")

    def _run_cli(self, prompt: str) -> _CliResult:
        if self.backend == "codex":
            return _run_codex(prompt, self.model, self.timeout_seconds)
        if self.backend == "claude":
            return _run_claude(prompt, self.model, self.timeout_seconds)
        raise ValueError(f"Unsupported subscription backend: {self.backend}")


def create_subscription_model(model_id: str) -> SubscriptionModel:
    parts = model_id.split("/", 2)
    if len(parts) < 2 or parts[0] != "subscription":
        raise ValueError(f"Not a subscription model id: {model_id}")
    backend = parts[1]
    if backend not in {"codex", "claude"}:
        raise ValueError(f"Unsupported subscription backend: {backend}")
    model = parts[2] if len(parts) == 3 else None
    return SubscriptionModel(backend=backend, model=model)  # type: ignore[arg-type]


def is_subscription_model_id(model_id: str | None) -> bool:
    return bool(model_id and model_id.startswith("subscription/"))


async def _stream_model_response(
    *,
    model_response: ModelResponse,
    response_id: str,
    model_name: str,
    starting_sequence_number: int,
):
    sequence_number = starting_sequence_number
    for output_index, item in enumerate(model_response.output):
        if isinstance(item, ResponseOutputMessage):
            async for event in _stream_message_item(item, output_index, sequence_number):
                yield event
                sequence_number += 1
        elif isinstance(item, ResponseFunctionToolCall):
            async for event in _stream_tool_call_item(item, output_index, sequence_number):
                yield event
                sequence_number += 1
        else:
            yield ResponseOutputItemAddedEvent(
                item=item,
                output_index=output_index,
                type="response.output_item.added",
                sequence_number=sequence_number,
            )
            sequence_number += 1
            yield ResponseOutputItemDoneEvent(
                item=item,
                output_index=output_index,
                type="response.output_item.done",
                sequence_number=sequence_number,
            )
            sequence_number += 1

    yield ResponseCompletedEvent(
        response=_response_shell(
            response_id,
            model_name,
            status="completed",
            output=model_response.output,
            usage=_response_usage(model_response.usage),
            completed_at=time.time(),
        ),
        type="response.completed",
        sequence_number=sequence_number,
    )


async def _stream_message_item(
    item: ResponseOutputMessage,
    output_index: int,
    sequence_number: int,
):
    in_progress = item.model_copy(update={"content": [], "status": "in_progress"})
    yield ResponseOutputItemAddedEvent(
        item=in_progress,
        output_index=output_index,
        type="response.output_item.added",
        sequence_number=sequence_number,
    )
    sequence_number += 1

    for content_index, part in enumerate(item.content):
        if not isinstance(part, ResponseOutputText):
            continue
        empty_part = part.model_copy(update={"text": ""})
        yield ResponseContentPartAddedEvent(
            content_index=content_index,
            item_id=item.id,
            output_index=output_index,
            part=empty_part,
            type="response.content_part.added",
            sequence_number=sequence_number,
        )
        sequence_number += 1
        text = part.text or ""
        if text:
            yield ResponseTextDeltaEvent(
                content_index=content_index,
                delta=text,
                item_id=item.id,
                output_index=output_index,
                type="response.output_text.delta",
                sequence_number=sequence_number,
                logprobs=[],
            )
            sequence_number += 1
        yield ResponseContentPartDoneEvent(
            content_index=content_index,
            item_id=item.id,
            output_index=output_index,
            part=part,
            type="response.content_part.done",
            sequence_number=sequence_number,
        )
        sequence_number += 1

    yield ResponseOutputItemDoneEvent(
        item=item,
        output_index=output_index,
        type="response.output_item.done",
        sequence_number=sequence_number,
    )


async def _stream_tool_call_item(
    item: ResponseFunctionToolCall,
    output_index: int,
    sequence_number: int,
):
    in_progress = item.model_copy(update={"arguments": "", "status": "in_progress"})
    yield ResponseOutputItemAddedEvent(
        item=in_progress,
        output_index=output_index,
        type="response.output_item.added",
        sequence_number=sequence_number,
    )
    sequence_number += 1
    if item.arguments:
        yield ResponseFunctionCallArgumentsDeltaEvent(
            delta=item.arguments,
            item_id=item.id or item.call_id,
            output_index=output_index,
            type="response.function_call_arguments.delta",
            sequence_number=sequence_number,
        )
        sequence_number += 1
    yield ResponseOutputItemDoneEvent(
        item=item,
        output_index=output_index,
        type="response.output_item.done",
        sequence_number=sequence_number,
    )


def _response_shell(
    response_id: str,
    model_name: str,
    *,
    status: Literal["completed", "in_progress"],
    output: list[Any] | None = None,
    usage: ResponseUsage | None = None,
    completed_at: float | None = None,
) -> Response:
    return Response(
        id=response_id,
        created_at=time.time(),
        model=model_name,
        object="response",
        output=output or [],
        parallel_tool_calls=True,
        tool_choice="auto",
        tools=[],
        status=status,
        completed_at=completed_at,
        usage=usage,
    )


def _response_usage(usage: Usage) -> ResponseUsage:
    return ResponseUsage(
        input_tokens=usage.input_tokens,
        input_tokens_details=InputTokensDetails(cached_tokens=usage.input_tokens_details.cached_tokens),
        output_tokens=usage.output_tokens,
        output_tokens_details=OutputTokensDetails(reasoning_tokens=usage.output_tokens_details.reasoning_tokens),
        total_tokens=usage.total_tokens,
    )


def _run_codex(prompt: str, model: str | None, timeout_seconds: int | None) -> _CliResult:
    cmd = [
        "codex",
        "exec",
        "--ephemeral",
        "--skip-git-repo-check",
        "--ignore-rules",
        "--sandbox",
        "read-only",
        "--disable",
        "shell_tool",
        "--disable",
        "image_generation",
        "--disable",
        "browser_use",
        "--disable",
        "computer_use",
        "--json",
    ]
    if model:
        cmd.extend(["--model", model])
    cmd.append("-")
    result = _run_command(cmd, prompt, timeout_seconds)
    text = ""
    usage = Usage(requests=1)
    events: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(event)
        if event.get("type") == "item.completed":
            item = event.get("item") or {}
            if item.get("type") == "agent_message":
                text = item.get("text") or text
        if event.get("type") == "turn.completed":
            raw_usage = event.get("usage") or {}
            usage = Usage(
                requests=1,
                input_tokens=int(raw_usage.get("input_tokens") or 0),
                output_tokens=int(raw_usage.get("output_tokens") or 0),
                total_tokens=int(raw_usage.get("input_tokens") or 0) + int(raw_usage.get("output_tokens") or 0),
            )
    if not text:
        raise RuntimeError("Codex CLI did not return an agent_message event.")
    return _CliResult(text=text, usage=usage, raw=events)


def _run_claude(prompt: str, model: str | None, timeout_seconds: int | None) -> _CliResult:
    cmd = [
        "claude",
        "-p",
        "--no-session-persistence",
        "--tools",
        "",
        "--output-format",
        "json",
        "--system-prompt",
        "Return only the JSON object requested by the OpenSwarm protocol.",
    ]
    if model:
        cmd.extend(["--model", model])
    result = _run_command(cmd, prompt, timeout_seconds)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Claude CLI returned non-JSON output: {result.stdout[:500]}") from exc
    if payload.get("is_error"):
        raise RuntimeError(payload.get("result") or payload.get("api_error_status") or "Claude CLI call failed.")
    text = payload.get("result") or ""
    raw_usage = payload.get("usage") or {}
    usage = Usage(
        requests=1,
        input_tokens=int(raw_usage.get("input_tokens") or 0),
        output_tokens=int(raw_usage.get("output_tokens") or 0),
        total_tokens=int(raw_usage.get("input_tokens") or 0) + int(raw_usage.get("output_tokens") or 0),
    )
    if not text:
        raise RuntimeError("Claude CLI did not return a result.")
    return _CliResult(text=text, usage=usage, raw=payload)


def _run_command(cmd: list[str], stdin: str, timeout_seconds: int | None) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            cmd,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"{cmd[0]} command not found. Run onboarding status for setup instructions.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"{cmd[0]} timed out after {timeout_seconds} seconds. Increase {MODEL_TIMEOUT_ENV_VAR} "
            f"or set it to 0/none to disable OpenSwarm model-call timeouts."
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"{cmd[0]} failed: {detail}")
    return result


def _build_protocol_prompt(
    *,
    system_instructions: str | None,
    input_items: Any,
    tools: list[Any],
    handoffs: list[Any],
    output_schema: Any,
) -> str:
    payload = {
        "system_instructions": system_instructions or "",
        "conversation": _jsonable(input_items),
        "tools": [_tool_spec(tool) for tool in tools if hasattr(tool, "on_invoke_tool")]
        + [_handoff_spec(handoff) for handoff in handoffs],
        "output_schema": _jsonable(output_schema),
    }
    return (
        "You are the model backend for an OpenSwarm Agency Swarm agent.\n"
        "OpenSwarm, not you, executes tools and handoffs. Your only job is to choose the next model output.\n"
        "Return exactly one JSON object and no markdown.\n\n"
        "Allowed response shapes:\n"
        '{"type":"final","content":"assistant response text"}\n'
        '{"type":"tool_calls","tool_calls":[{"name":"tool_name","arguments":{}}]}\n\n'
        "Rules:\n"
        "- Use tool_calls when a listed callable tool or handoff is needed.\n"
        "- Hosted provider tools that are not listed here are unavailable in subscription mode.\n"
        "- Use final only when you can answer or finish the task without another tool.\n"
        "- Tool arguments must satisfy the listed JSON schema.\n"
        "- Do not include code fences, comments, or explanatory text outside the JSON object.\n\n"
        f"OpenSwarm request payload:\n{json.dumps(payload, ensure_ascii=False, default=str)}"
    )


def _tool_spec(tool: Any) -> dict[str, Any]:
    return {
        "name": getattr(tool, "name", ""),
        "description": getattr(tool, "description", ""),
        "parameters": _jsonable(getattr(tool, "params_json_schema", {})),
    }


def _handoff_spec(handoff: Any) -> dict[str, Any]:
    return {
        "name": getattr(handoff, "tool_name", ""),
        "description": getattr(handoff, "tool_description", ""),
        "parameters": _jsonable(getattr(handoff, "input_json_schema", {})),
        "handoff_to": getattr(handoff, "agent_name", None),
    }


def _parse_decision(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        decision = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            return {"type": "final", "content": raw}
        decision = json.loads(match.group(0))
    if not isinstance(decision, dict):
        return {"type": "final", "content": str(decision)}
    return decision


def _decision_to_output(decision: dict[str, Any]) -> list[Any]:
    decision_type = decision.get("type")
    if decision_type == "tool_calls":
        calls = decision.get("tool_calls") or []
        output: list[Any] = []
        for index, call in enumerate(calls, start=1):
            if not isinstance(call, dict) or not call.get("name"):
                continue
            args = call.get("arguments") or {}
            output.append(
                ResponseFunctionToolCall(
                    arguments=json.dumps(args, ensure_ascii=False),
                    call_id=call.get("id") or f"call_{uuid.uuid4().hex}_{index}",
                    name=str(call["name"]),
                    type="function_call",
                    id=f"fc_{uuid.uuid4().hex}",
                    status="completed",
                )
            )
        if output:
            return output
    content = decision.get("content") if decision_type == "final" else json.dumps(decision, ensure_ascii=False)
    return [
        ResponseOutputMessage(
            id=f"msg_{uuid.uuid4().hex}",
            role="assistant",
            status="completed",
            type="message",
            content=[
                ResponseOutputText(
                    type="output_text",
                    text=str(content or ""),
                    annotations=[],
                )
            ],
        )
    ]


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(mode="json")
        except Exception:
            return value.model_dump()
    if hasattr(value, "__dict__"):
        return {str(k): _jsonable(v) for k, v in value.__dict__.items() if not k.startswith("_")}
    return str(value)
