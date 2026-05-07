# FastAPI entry point - run with: uv run python server.py

import logging
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)

from swarm import create_agency
from agency_swarm.integrations.fastapi import run_fastapi
from patches.patch_openswarm_model_control import install_factory_model_control_routes


if __name__ == "__main__":
    agencies = {
        "open-swarm": create_agency,
    }
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
