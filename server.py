# FastAPI entry point - run with: uv run python server.py

import logging
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)

from agency_swarm.integrations.fastapi import run_fastapi
from patches.patch_openswarm_model_control import install_factory_model_control_routes
from swarm_registry import get_registered_agency_factories


if __name__ == "__main__":
    agencies = get_registered_agency_factories(available_only=True)
    if not agencies:
        raise RuntimeError("No registered swarms are available.")
    app = run_fastapi(
        agencies=agencies,
        port=8080,
        enable_logging=True,
        allowed_local_file_dirs=[
            "./uploads",
        ],
        return_app=True,
    )
    if app is None:
        raise RuntimeError("Failed to build the OpenSwarm FastAPI app.")
    install_factory_model_control_routes(app, agencies)

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
