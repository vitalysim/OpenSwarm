"""Unified web research search across subscription CLIs and platform fallbacks."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import shutil
import subprocess
import threading
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from agency_swarm.tools import BaseTool
from dotenv import load_dotenv
from pydantic import Field


SearchMode = Literal["auto", "claude", "codex", "platform"]
SearchDepth = Literal["quick", "deep"]


class WebResearchSearch(BaseTool):
    """
    Search the web with subscription-backed Claude Code/Codex search and platform fallbacks.

    Use this for current facts, news, source discovery, company/product research,
    and general web research. In auto mode, quick searches use the configured
    subscription provider order, while deep searches can run Claude and Codex in
    parallel, merge results, and fall back to OpenAI hosted search or SearchAPI.
    """

    query: str = Field(..., description="Search query or research question.")
    mode: SearchMode = Field(
        default="auto",
        description="Search provider mode: auto, claude, codex, or platform.",
    )
    depth: SearchDepth = Field(
        default="quick",
        description="quick uses one preferred provider; deep can combine Claude and Codex.",
    )
    max_results: int = Field(default=8, ge=1, le=20, description="Maximum merged results to return.")
    fetch_top_k: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Number of top results the provider should fetch/summarize when supported.",
    )
    site_filters: list[str] | None = Field(
        default=None,
        description="Optional domains to constrain search, e.g. ['openai.com', 'anthropic.com'].",
    )

    class ToolConfig:
        strict = False

    def run(self) -> str:
        load_dotenv(override=True)
        mode = _effective_mode(self.mode)
        providers = _selected_providers(mode, self.depth)
        attempted: list[str] = []
        warnings: list[str] = []
        fallbacks_used: list[str] = []
        provider_payloads: list[dict[str, Any]] = []

        if providers:
            provider_payloads.extend(
                _run_subscription_providers(
                    providers=providers,
                    query=self.query,
                    depth=self.depth,
                    max_results=self.max_results,
                    fetch_top_k=self.fetch_top_k,
                    site_filters=self.site_filters or [],
                    attempted=attempted,
                    warnings=warnings,
                )
            )

        merged = _merge_results(provider_payloads, self.max_results)
        should_platform_fallback = (
            mode == "platform"
            or (
                mode == "auto"
                and _env_bool("WEB_SEARCH_PLATFORM_FALLBACK", True)
                and (not merged or (self.depth == "deep" and len(merged) < min(self.max_results, 5)))
            )
        )
        if should_platform_fallback:
            platform_payloads = _run_platform_fallbacks(
                query=self.query,
                depth=self.depth,
                max_results=self.max_results,
                fetch_top_k=self.fetch_top_k,
                site_filters=self.site_filters or [],
                attempted=attempted,
                warnings=warnings,
            )
            if platform_payloads:
                fallbacks_used.extend(payload["provider"] for payload in platform_payloads)
                provider_payloads.extend(platform_payloads)
                merged = _merge_results(provider_payloads, self.max_results)

        return json.dumps(
            {
                "query": self.query,
                "mode_requested": self.mode,
                "mode_used": mode,
                "depth": self.depth,
                "providers_attempted": attempted,
                "fallbacks_used": fallbacks_used,
                "results": merged,
                "warnings": warnings,
            },
            indent=2,
            ensure_ascii=False,
        )


def _effective_mode(mode: SearchMode) -> SearchMode:
    if mode != "auto":
        return mode
    configured = os.getenv("WEB_SEARCH_MODE", "auto").strip().lower()
    return configured if configured in {"auto", "claude", "codex", "platform"} else "auto"  # type: ignore[return-value]


def _selected_providers(mode: SearchMode, depth: SearchDepth) -> list[str]:
    if mode == "claude":
        return ["claude"]
    if mode == "codex":
        return ["codex"]
    if mode == "platform":
        return []
    ordered = _provider_order()
    if depth == "deep" and _env_bool("WEB_SEARCH_DEEP_MIX", True):
        return [provider for provider in ordered if provider in {"codex", "claude"}]
    return ordered[:1]


def _provider_order() -> list[str]:
    raw = os.getenv("WEB_SEARCH_PROVIDER_ORDER", "codex,claude")
    providers = [part.strip().lower() for part in raw.split(",") if part.strip()]
    valid = [provider for provider in providers if provider in {"codex", "claude"}]
    return valid or ["codex", "claude"]


def _run_subscription_providers(
    *,
    providers: list[str],
    query: str,
    depth: SearchDepth,
    max_results: int,
    fetch_top_k: int,
    site_filters: list[str],
    attempted: list[str],
    warnings: list[str],
) -> list[dict[str, Any]]:
    timeout = int(os.getenv("WEB_SEARCH_TIMEOUT_SECONDS", "60"))
    if len(providers) > 1:
        payloads: list[dict[str, Any]] = []
        attempted.extend(providers)
        with ThreadPoolExecutor(max_workers=len(providers)) as pool:
            future_map = {
                pool.submit(
                    _run_subscription_provider,
                    provider,
                    query,
                    depth,
                    max_results,
                    fetch_top_k,
                    site_filters,
                    timeout,
                ): provider
                for provider in providers
            }
            for future in as_completed(future_map):
                provider = future_map[future]
                try:
                    payloads.append(future.result())
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"{provider} search failed: {_one_line(str(exc))}")
        return payloads

    payloads = []
    for provider in providers:
        attempted.append(provider)
        try:
            payload = _run_subscription_provider(
                provider,
                query,
                depth,
                max_results,
                fetch_top_k,
                site_filters,
                timeout,
            )
            payloads.append(payload)
            if payload.get("results"):
                break
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{provider} search failed: {_one_line(str(exc))}")
    return payloads


def _run_subscription_provider(
    provider: str,
    query: str,
    depth: SearchDepth,
    max_results: int,
    fetch_top_k: int,
    site_filters: list[str],
    timeout: int,
) -> dict[str, Any]:
    if provider == "codex":
        return _run_codex_search(query, depth, max_results, fetch_top_k, site_filters, timeout)
    if provider == "claude":
        return _run_claude_search(query, depth, max_results, fetch_top_k, site_filters, timeout)
    raise ValueError(f"Unsupported subscription search provider: {provider}")


def _run_codex_search(
    query: str,
    depth: SearchDepth,
    max_results: int,
    fetch_top_k: int,
    site_filters: list[str],
    timeout: int,
) -> dict[str, Any]:
    if not shutil.which("codex"):
        raise RuntimeError("codex command not found. Run `codex login` after installing Codex CLI.")
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
        "computer_use",
        "--json",
        "-",
    ]
    result = _run_command(cmd, _build_prompt("codex", query, depth, max_results, fetch_top_k, site_filters), timeout)
    final_text = ""
    search_events: list[str] = []
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item") or {}
        if item.get("type") == "web_search":
            action = item.get("action") or {}
            if action.get("query"):
                search_events.append(str(action["query"]))
        if item.get("type") == "agent_message":
            final_text = item.get("text") or final_text
    if not final_text:
        raise RuntimeError("Codex search returned no final agent message.")
    payload = _parse_provider_json(final_text)
    payload["search_events"] = search_events
    return _normalize_provider_payload(payload, "codex", max_results)


def _run_claude_search(
    query: str,
    depth: SearchDepth,
    max_results: int,
    fetch_top_k: int,
    site_filters: list[str],
    timeout: int,
) -> dict[str, Any]:
    if not shutil.which("claude"):
        raise RuntimeError("claude command not found. Run `claude auth login` after installing Claude Code.")
    cmd = [
        "claude",
        "-p",
        "--tools",
        "WebSearch,WebFetch",
        "--permission-mode",
        "bypassPermissions",
        "--no-session-persistence",
        "--output-format",
        "json",
        "--system-prompt",
        "You are a search worker. Return only the JSON object requested by the prompt.",
    ]
    result = _run_command(cmd, _build_prompt("claude", query, depth, max_results, fetch_top_k, site_filters), timeout)
    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Claude returned non-JSON envelope: {result.stdout[:500]}") from exc
    if envelope.get("is_error"):
        raise RuntimeError(envelope.get("result") or "Claude search failed.")
    payload = _parse_provider_json(envelope.get("result") or "")
    return _normalize_provider_payload(payload, "claude", max_results)


def _run_platform_fallbacks(
    *,
    query: str,
    depth: SearchDepth,
    max_results: int,
    fetch_top_k: int,
    site_filters: list[str],
    attempted: list[str],
    warnings: list[str],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for provider, runner in (("openai_hosted", _run_openai_hosted_search), ("searchapi", _run_searchapi_search)):
        attempted.append(provider)
        try:
            payload = runner(query, depth, max_results, fetch_top_k, site_filters)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{provider} fallback failed: {_one_line(str(exc))}")
            continue
        payloads.append(payload)
        if payload.get("results"):
            break
    return payloads


def _run_openai_hosted_search(
    query: str,
    depth: SearchDepth,
    max_results: int,
    fetch_top_k: int,
    site_filters: list[str],
) -> dict[str, Any]:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")
    from agents import Agent, Runner, set_tracing_disabled  # noqa: PLC0415
    from agency_swarm.tools import WebSearchTool  # noqa: PLC0415

    set_tracing_disabled(True)
    context_size = "high" if depth == "deep" else "medium"
    agent = Agent(
        name="OpenAI Hosted Web Search",
        instructions="Use hosted web search and return only the requested JSON object.",
        model=os.getenv("WEB_SEARCH_OPENAI_MODEL", "gpt-5.2"),
        tools=[WebSearchTool(search_context_size=context_size)],
    )
    result = _run_awaitable(
        Runner.run(
            agent,
            _build_prompt("openai_hosted", query, depth, max_results, fetch_top_k, site_filters),
            max_turns=6,
        )
    )
    payload = _parse_provider_json(str(getattr(result, "final_output", "") or ""))
    return _normalize_provider_payload(payload, "openai_hosted", max_results)


def _run_searchapi_search(
    query: str,
    depth: SearchDepth,
    max_results: int,
    fetch_top_k: int,
    site_filters: list[str],
) -> dict[str, Any]:
    api_key = os.getenv("SEARCH_API_KEY")
    if not api_key:
        raise RuntimeError("SEARCH_API_KEY is not set.")
    import requests  # noqa: PLC0415

    search_query = _query_with_site_filters(query, site_filters)
    response = requests.get(
        "https://www.searchapi.io/api/v1/search",
        params={"engine": "google", "api_key": api_key, "q": search_query, "num": max_results},
        timeout=int(os.getenv("WEB_SEARCH_TIMEOUT_SECONDS", "60")),
    )
    if response.status_code != 200:
        raise RuntimeError(f"SearchAPI returned HTTP {response.status_code}: {response.text[:300]}")
    data = response.json()
    if data.get("error"):
        raise RuntimeError(str(data["error"]))
    results = []
    for item in data.get("organic_results", [])[:max_results]:
        results.append(
            {
                "title": item.get("title") or "",
                "url": item.get("link") or "",
                "snippet": item.get("snippet") or "",
                "fetched_summary": item.get("snippet") or "",
            }
        )
    return _normalize_provider_payload({"query": search_query, "results": results, "notes": "SearchAPI Google fallback."}, "searchapi", max_results)


def _build_prompt(
    provider: str,
    query: str,
    depth: SearchDepth,
    max_results: int,
    fetch_top_k: int,
    site_filters: list[str],
) -> str:
    filters = f"\nRestrict to these domains when relevant: {', '.join(site_filters)}." if site_filters else ""
    fetch_instruction = (
        f"Fetch or open the top {fetch_top_k} most relevant pages and summarize them when the provider supports it."
        if fetch_top_k
        else "Do not fetch pages after search; use search result snippets only."
    )
    return (
        f"Search query: {query}\n"
        f"Depth: {depth}. Provider: {provider}.{filters}\n"
        f"Return at most {max_results} results. {fetch_instruction}\n\n"
        "Return exactly one JSON object and no markdown, prose, citations block, or code fence.\n"
        "Shape:\n"
        "{\n"
        '  "query": "search query used",\n'
        '  "results": [\n'
        '    {"title": "result title", "url": "https://...", "snippet": "short snippet", "fetched_summary": "summary or empty string"}\n'
        "  ],\n"
        '  "notes": "brief note on search/fetch coverage or limitations"\n'
        "}\n"
    )


def _run_command(cmd: list[str], stdin: str, timeout: int) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        input=stdin,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(detail or f"{cmd[0]} exited with {result.returncode}")
    return result


def _run_awaitable(awaitable):
    box: dict[str, object] = {}
    err: dict[str, BaseException] = {}

    def _worker() -> None:
        try:
            box["result"] = asyncio.run(awaitable)
        except BaseException as exc:  # noqa: BLE001
            err["error"] = exc

    thread = threading.Thread(target=_worker, name="web-research-search-worker", daemon=True)
    thread.start()
    thread.join(timeout=int(os.getenv("WEB_SEARCH_TIMEOUT_SECONDS", "60")))
    if thread.is_alive():
        raise TimeoutError("OpenAI hosted web search timed out.")
    if "error" in err:
        raise err["error"]
    return box.get("result")


def _parse_provider_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise RuntimeError("provider returned empty output")
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise RuntimeError(f"provider did not return a JSON object: {raw[:300]}")


def _normalize_provider_payload(payload: dict[str, Any], provider: str, max_results: int) -> dict[str, Any]:
    normalized = []
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or item.get("link") or "").strip()
        if not title and not url:
            continue
        normalized.append(
            {
                "title": title or url,
                "url": url,
                "snippet": str(item.get("snippet") or "").strip(),
                "fetched_summary": str(item.get("fetched_summary") or item.get("summary") or "").strip(),
                "provider": provider,
                "confidence": _provider_confidence(provider),
            }
        )
        if len(normalized) >= max_results:
            break
    return {
        "provider": provider,
        "query": payload.get("query") or "",
        "results": normalized,
        "notes": payload.get("notes") or "",
    }


def _merge_results(payloads: list[dict[str, Any]], max_results: int) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for payload in payloads:
        for item in payload.get("results") or []:
            key = _result_key(item)
            if not key:
                continue
            if key not in by_key:
                merged = dict(item)
                merged["providers"] = [item.get("provider")]
                by_key[key] = merged
                order.append(key)
                continue
            existing = by_key[key]
            provider = item.get("provider")
            if provider and provider not in existing["providers"]:
                existing["providers"].append(provider)
                existing["provider"] = ",".join(existing["providers"])
                existing["confidence"] = min(0.99, float(existing.get("confidence") or 0.5) + 0.08)
            if len(str(item.get("snippet") or "")) > len(str(existing.get("snippet") or "")):
                existing["snippet"] = item.get("snippet") or ""
            if len(str(item.get("fetched_summary") or "")) > len(str(existing.get("fetched_summary") or "")):
                existing["fetched_summary"] = item.get("fetched_summary") or ""
    return [by_key[key] for key in order[:max_results]]


def _result_key(item: dict[str, Any]) -> str:
    url = str(item.get("url") or "").strip()
    if url:
        return _canonical_url(url)
    return re.sub(r"\s+", " ", str(item.get("title") or "").lower()).strip()


def _canonical_url(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return url.lower().rstrip("/")
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def _query_with_site_filters(query: str, site_filters: list[str]) -> str:
    if not site_filters:
        return query
    sites = " OR ".join(f"site:{site}" for site in site_filters)
    return f"({sites}) {query}"


def _provider_confidence(provider: str) -> float:
    return {
        "codex": 0.86,
        "claude": 0.86,
        "openai_hosted": 0.84,
        "searchapi": 0.72,
    }.get(provider, 0.65)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _one_line(value: str, limit: int = 240) -> str:
    line = " ".join(value.split())
    return line if len(line) <= limit else f"{line[: limit - 3]}..."
