"""Compatibility entry point for local OpenSwarm runs.

This keeps the documented `python run.py` workflow working while the reusable
launcher implementation lives in `run_utils.py`.
"""

from run_utils import _bootstrap, main


if __name__ == "__main__":
    _bootstrap()
    main()
