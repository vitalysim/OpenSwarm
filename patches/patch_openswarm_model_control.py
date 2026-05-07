"""Patch Agency Swarm's local TUI bridge with OpenSwarm model controls."""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel

from model_control import build_model_state, set_agent_model


class SetAgentModelRequest(BaseModel):
    agent: str
    model: str


def install_live_model_control_routes(app: Any, agency: Any, *, agency_id: str | None = None) -> None:
    """Install OpenSwarm model-control routes backed by a live Agency instance."""
    route_agency_id = agency_id or getattr(agency, "name", None) or "agency"
    _install_routes(
        app,
        route_agency_id=route_agency_id,
        agency_factory=lambda: agency,
        persist=True,
    )


def install_factory_model_control_routes(app: Any, agencies: dict[str, Callable[..., Any]]) -> None:
    """Install model-control routes backed by Agency factory functions."""
    for route_agency_id, agency_factory in agencies.items():
        _install_routes(
            app,
            route_agency_id=route_agency_id,
            agency_factory=lambda factory=agency_factory: factory(load_threads_callback=lambda: []),
            persist=True,
        )


def apply_openswarm_model_control_patch() -> None:
    """Patch the local Agent Swarm CLI server so the TUI can switch OpenSwarm models."""
    import agency_swarm.ui.demos.agentswarm_cli as cli  # noqa: PLC0415

    if getattr(cli, "_openswarm_model_control_patched", False):
        return

    def _start_server(agency: Any, capture=None):
        port = cli._port()
        app = cli.run_fastapi(
            agencies=cli.build_fastapi_agencies(agency),
            host=cli._HOST,
            port=port,
            server_url=f"http://{cli._HOST}:{port}",
            app_token_env="",
            return_app=True,
        )
        if app is None:
            raise RuntimeError("Failed to build the Agency Swarm FastAPI app for Agent Swarm CLI.")

        install_live_model_control_routes(app, agency, agency_id=cli._agency_id(agency))

        import threading  # noqa: PLC0415
        import uvicorn  # noqa: PLC0415

        config = uvicorn.Config(app=app, host=cli._HOST, port=port, log_level="warning", access_log=False)
        server = uvicorn.Server(config)
        error: list[BaseException] = []

        def target() -> None:
            try:
                with cli._contain_bridge_output(capture):
                    server.run()
            except BaseException as exc:  # pragma: no cover - surfaced by waiter below
                error.append(exc)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        cli._wait_for_server(port, server, thread, error)
        return cli._Server(port=port, server=server, thread=thread)

    cli._start_server = _start_server
    cli._openswarm_model_control_patched = True


def _install_routes(
    app: Any,
    *,
    route_agency_id: str,
    agency_factory: Callable[[], Any],
    persist: bool,
) -> None:
    installed = getattr(app.state, "openswarm_model_control_routes", set())
    if route_agency_id in installed:
        return

    prefix = f"/{route_agency_id}/openswarm"

    async def get_models(live: bool = True) -> dict[str, Any]:
        return build_model_state(agency_factory(), live=live)

    async def post_agent_model(request: SetAgentModelRequest) -> dict[str, Any]:
        return set_agent_model(
            agency_factory(),
            agent_name=request.agent,
            model_id=request.model,
            persist=persist,
        )

    app.add_api_route(f"{prefix}/models", get_models, methods=["GET"], tags=["openswarm"])
    app.add_api_route(f"{prefix}/agent-model", post_agent_model, methods=["POST"], tags=["openswarm"])
    installed = set(installed)
    installed.add(route_agency_id)
    app.state.openswarm_model_control_routes = installed
