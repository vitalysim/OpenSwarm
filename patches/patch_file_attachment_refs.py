"""
Patch: inject attachment file references into the user message.
"""

import asyncio
from contextlib import contextmanager

from workspace_context import (
    extract_working_directory_from_client_config,
    reset_current_working_directory,
    set_current_working_directory,
)

_PATCH_APPLIED = False


def apply_file_attachment_reference_patch() -> None:
    global _PATCH_APPLIED
    if _PATCH_APPLIED:
        return
    _PATCH_APPLIED = True
    _patch_endpoint_handler_factories()


def _build_attachment_note(file_urls: dict[str, str]) -> str:
    lines = [
        "\n\n[SYSTEM NOTE] The user attached the following files.",
        "Use ONLY the URLs below as file references in your tools (e.g. as `input_image_ref`).",
        "Any /mnt/data/ paths you see are internal OpenAI server paths — they are NOT real local paths and must NOT be used or shown to the user:",
    ]
    for filename, ref in file_urls.items():
        lines.append(f"  - {filename}: {ref}")
    return "\n".join(lines)


def _patch_endpoint_handler_factories() -> None:
    from fastapi import Depends
    from fastapi import Request as FastAPIRequest
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers as eh

    _original_make_response = eh.make_response_endpoint
    _original_make_stream = eh.make_stream_endpoint
    _original_make_agui = eh.make_agui_chat_endpoint

    def patched_make_response_endpoint(request_model, agency_factory, verify_token, allowed_local_dirs=None):
        original_handler = _original_make_response(request_model, agency_factory, verify_token, allowed_local_dirs)

        async def handler(request: request_model, token: str = Depends(verify_token)):
            request, working_directory = _prepare_request(request)
            with _working_directory_scope(working_directory):
                return await original_handler(request, token)

        return handler

    def patched_make_stream_endpoint(request_model, agency_factory, verify_token, run_registry, allowed_local_dirs=None):
        original_handler = _original_make_stream(request_model, agency_factory, verify_token, run_registry, allowed_local_dirs)

        async def handler(http_request: FastAPIRequest, request: request_model, token: str = Depends(verify_token)):
            request, working_directory = _prepare_request(request)
            with _working_directory_scope(working_directory):
                response = await original_handler(http_request, request, token)
            body_iterator = getattr(response, "body_iterator", None)
            if body_iterator is not None:
                response.body_iterator = _with_workspace_context(
                    _with_sse_heartbeats(body_iterator),
                    working_directory,
                )
            return response

        return handler

    def patched_make_agui_endpoint(request_model, agency_factory, verify_token, allowed_local_dirs=None):
        original_handler = _original_make_agui(request_model, agency_factory, verify_token, allowed_local_dirs)

        async def handler(request: request_model, token: str = Depends(verify_token)):
            request, working_directory = _prepare_request(request)
            with _working_directory_scope(working_directory):
                return await original_handler(request, token)

        return handler

    eh.make_response_endpoint = patched_make_response_endpoint
    eh.make_stream_endpoint = patched_make_stream_endpoint
    eh.make_agui_chat_endpoint = patched_make_agui_endpoint


def _prepare_request(request):
    updates = {}
    working_directory, client_config = extract_working_directory_from_client_config(
        getattr(request, "client_config", None)
    )
    if client_config != getattr(request, "client_config", None):
        updates["client_config"] = client_config

    if getattr(request, "file_urls", None):
        note = _build_attachment_note(request.file_urls)
        existing = getattr(request, "additional_instructions", None) or ""
        updates["additional_instructions"] = (existing + "\n\n" + note).strip()

    if updates:
        request = request.model_copy(update=updates)
    return request, working_directory


@contextmanager
def _working_directory_scope(working_directory: str | None):
    token = set_current_working_directory(working_directory)
    try:
        yield
    finally:
        reset_current_working_directory(token)


async def _with_workspace_context(body_iterator, working_directory: str | None):
    with _working_directory_scope(working_directory):
        async for chunk in body_iterator:
            yield chunk


async def _with_sse_heartbeats(body_iterator, interval_seconds: float = 10.0):
    queue: asyncio.Queue = asyncio.Queue()
    sentinel = object()

    async def produce() -> None:
        try:
            async for chunk in body_iterator:
                await queue.put(chunk)
        except BaseException as exc:
            await queue.put(exc)
        finally:
            await queue.put(sentinel)

    producer = asyncio.create_task(produce())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=interval_seconds)
            except TimeoutError:
                yield b": openswarm heartbeat\n\n"
                continue
            if item is sentinel:
                break
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        if not producer.done():
            producer.cancel()
            try:
                await producer
            except asyncio.CancelledError:
                pass
