import os
import sys
import json
import subprocess
import shutil
import tempfile
from pathlib import Path

def _resolve_bin_name() -> str:
    """Return the platform+arch-specific TUI binary filename."""
    import platform
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
    if sys.platform == "win32":
        return f"openswarm-tui-windows-{arch}.exe"
    if sys.platform == "darwin":
        return f"openswarm-tui-darwin-{arch}"
    return f"openswarm-tui-linux-{arch}"


def _resolve_dist_dirname() -> str:
    """Return the local-build dist directory name produced by `npm run build:tui`."""
    import platform
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
    if sys.platform == "win32":
        return f"agentswarm-cli-windows-{arch}"
    if sys.platform == "darwin":
        return f"agentswarm-cli-darwin-{arch}"
    return f"agentswarm-cli-linux-{arch}"


def _resolve_local_tui_bin() -> Path | None:
    """Locate a usable local TUI binary, preferring a release-style drop at the repo root."""
    repo = Path(__file__).resolve().parent
    bin_filename = "agentswarm.exe" if sys.platform == "win32" else "agentswarm"
    candidates = [
        repo / _resolve_bin_name(),
        repo / "packages" / "openswarm-tui" / "packages" / "opencode"
            / "dist" / _resolve_dist_dirname() / "bin" / bin_filename,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _ensure_node_playwright_browsers(repo: Path) -> None:
    """Install Node Playwright browsers where the HTML-to-PPTX runner looks for them."""
    cli = repo / "node_modules" / "playwright" / "cli.js"
    if not cli.exists():
        return

    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(repo / ".playwright-browsers")
    subprocess.check_call(
        ["node", str(cli), "install", "chromium"],
        cwd=str(repo),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _uv_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("UV_LINK_MODE", "copy")
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def _uv_cmd() -> list[str]:
    uv = shutil.which("uv")
    if uv:
        return [uv]

    print("uv not found; installing uv first, please wait...\n")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "uv"])
    uv = shutil.which("uv")
    if uv:
        return [uv]

    user_base = subprocess.check_output(
        [sys.executable, "-m", "site", "--user-base"],
        text=True,
    ).strip()
    candidate = Path(user_base) / ("Scripts" if sys.platform == "win32" else "bin") / (
        "uv.exe" if sys.platform == "win32" else "uv"
    )
    if candidate.exists():
        return [str(candidate)]

    return [sys.executable, "-m", "uv"]


def _project_venv_python(repo: Path) -> Path:
    if sys.platform == "win32":
        return repo / ".venv" / "Scripts" / "python.exe"
    return repo / ".venv" / "bin" / "python"


def _in_project_venv(repo: Path) -> bool:
    try:
        return Path(sys.executable).resolve() == _project_venv_python(repo).resolve()
    except OSError:
        return False


def _sync_project_venv(repo: Path) -> None:
    subprocess.check_call(
        _uv_cmd() + ["sync", "--project", str(repo)],
        env=_uv_env(),
    )


# ── Bootstrap: create venv + install deps automatically on first run ─────────
# Only stdlib imports above. _bootstrap() is called explicitly — either from
# swarm.py (via `from run import _bootstrap; _bootstrap()`) or from the
# __main__ guard below — never at module level, so `from run import _bootstrap`
# is safe to call from outside the venv.
def _bootstrap() -> None:
    _repo = Path(__file__).resolve().parent
    _venv_python = _project_venv_python(_repo)

    if not _in_project_venv(_repo):
        if not _venv_python.exists():
            print("Creating .venv and installing Python dependencies with uv, please wait...\n")
            _sync_project_venv(_repo)
            print("\nDone.\n")

        os.execv(str(_venv_python), [str(_venv_python), *sys.argv])

    # Ensure deps are present.
    try:
        import dotenv        # noqa: F401
        import rich          # noqa: F401
        import questionary   # noqa: F401
        import agency_swarm  # noqa: F401
    except ImportError:
        print("Installing Python dependencies into .venv with uv, please wait...\n")
        _sync_project_venv(_repo)
        print("\nDone.\n")

    # Ensure the Playwright browser binary for the installed playwright version
    # is present. playwright install is idempotent — it exits quickly if the
    # right revision is already downloaded.
    try:
        subprocess.check_call(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

    # Install LibreOffice and Poppler if missing (used by Slides Agent).
    # Auto-installs when a known package manager is available; silently skips otherwise.
    _soffice = "soffice.com" if sys.platform == "win32" else "soffice"
    if not shutil.which(_soffice):
        if sys.platform == "darwin" and shutil.which("brew"):
            print("Installing LibreOffice (required for Slides Agent), please wait…\n")
            subprocess.check_call(["brew", "install", "--cask", "libreoffice"])
            print("\nDone.\n")
        elif sys.platform.startswith("linux") and shutil.which("apt-get"):
            print("Installing LibreOffice (required for Slides Agent), please wait…\n")
            subprocess.check_call(["sudo", "apt-get", "install", "-y", "libreoffice-impress"])
            print("\nDone.\n")
        elif sys.platform == "win32" and shutil.which("winget"):
            print("Installing LibreOffice (required for Slides Agent), please wait…\n")
            subprocess.check_call(["winget", "install", "--id", "TheDocumentFoundation.LibreOffice", "-e", "--silent"])
            print("\nDone.\n")
        else:
            print(
                "Warning: LibreOffice not found — Slides Agent thumbnail and export features "
                "will be unavailable.\n"
                "  Install it from: https://www.libreoffice.org/download/download-libreoffice/\n"
            )

    if not shutil.which("pdftoppm"):
        if sys.platform == "darwin" and shutil.which("brew"):
            print("Installing Poppler (required for Slides Agent), please wait…\n")
            subprocess.check_call(["brew", "install", "poppler"])
            print("\nDone.\n")
        elif sys.platform.startswith("linux") and shutil.which("apt-get"):
            print("Installing Poppler (required for Slides Agent), please wait…\n")
            subprocess.check_call(["sudo", "apt-get", "install", "-y", "poppler-utils"])
            print("\nDone.\n")
        elif sys.platform == "win32" and shutil.which("winget"):
            print("Installing Poppler (required for Slides Agent), please wait…\n")
            subprocess.check_call(["winget", "install", "--id", "oschwartz10612.Poppler", "-e", "--silent"])
            print("\nDone.\n")
        else:
            print(
                "Warning: Poppler (pdftoppm) not found — Slides Agent thumbnail and export "
                "features will be unavailable.\n"
                "  Install it from: https://poppler.freedesktop.org\n"
            )

    # Install Node.js dependencies if node_modules is missing or outdated.
    _npm = shutil.which("npm")
    if _npm and (_repo / "package.json").exists():
        _node_modules = _repo / "node_modules"
        _pkg_lock = _repo / "package-lock.json"
        _npm_marker = _node_modules / ".package-lock.json"
        _need_npm = (
            not _node_modules.exists()
            or not _npm_marker.exists()
            or (_pkg_lock.exists() and _pkg_lock.stat().st_mtime > _npm_marker.stat().st_mtime)
        )
        if _need_npm:
            print("Installing Node.js dependencies, please wait…\n")
            subprocess.check_call([_npm, "install"], cwd=str(_repo))
            print("\nDone.\n")
        try:
            _ensure_node_playwright_browsers(_repo)
        except Exception:
            pass

    # Download the OpenSwarm-controlled TUI binary from GitHub Releases if missing.
    _bin_name = _resolve_bin_name()
    _bin_path = _repo / _bin_name
    if not _bin_path.exists():
        import urllib.request
        _bin_url = os.getenv("OPENSWARM_TUI_URL", "").strip() or (
            f"https://github.com/vitalysim/OpenSwarm/releases/latest/download/{_bin_name}"
        )
        print("Downloading OpenSwarm TUI, please wait…\n")
        try:
            urllib.request.urlretrieve(_bin_url, str(_bin_path))
            if sys.platform != "win32":
                _bin_path.chmod(0o755)
            print("\nDone.\n")
        except Exception:
            print("Warning: Could not download OpenSwarm TUI. The terminal UI will use the default.\n")
# ─────────────────────────────────────────────────────────────────────────────


def build_integration_summary() -> str:
    from auth_registry import build_status_summary

    return build_status_summary(live=True)


def _configure_tui_backend_auth_env() -> None:
    from auth_registry import build_tui_auth_status_payload

    os.environ["OPENSWARM_AUTH_MODE"] = "backend"
    os.environ["OPENSWARM_AUTH_STATUS_JSON"] = json.dumps(
        build_tui_auth_status_payload(live=True),
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _configure_demo_console() -> None:
    """
    Terminal demo runs can stream stdout/stderr into a UI that expects structured output.
    Some third-party libs emit warnings that can corrupt that stream, so we suppress the
    known noisy ones here and apply the recommended Windows event-loop policy for pyzmq.
    """
    import warnings

    # By default, silence *all* console output for demo runs.
    # Opt out by setting OPENSWARM_DEMO_SILENCE_CONSOLE=0 / false / off.
    silence_env = os.getenv("OPENSWARM_DEMO_SILENCE_CONSOLE", "").strip().lower()
    silence_console = silence_env not in {"0", "false", "no", "off"}

    if silence_console:
        try:
            import logging
            devnull = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
            sys.stdout = devnull  # type: ignore[assignment]
            sys.stderr = devnull  # type: ignore[assignment]
            logging.disable(logging.CRITICAL)
        except Exception:
            pass
        return

    # Keep this opt-in so developers can still see warnings when needed.
    if os.getenv("OPENSWARM_DEMO_SHOW_WARNINGS", "").strip().lower() in {"1", "true", "yes", "on"}:
        return

    # pyzmq RuntimeWarning on Windows ProactorEventLoop (common with Python 3.8+ / 3.12)
    warnings.filterwarnings(
        "ignore",
        message=r".*Proactor event loop does not implement add_reader.*",
        category=RuntimeWarning,
    )

    # Pydantic v2 serializer warnings can be very noisy for streamed/typed objects.
    warnings.filterwarnings(
        "ignore",
        message=r"^Pydantic serializer warnings:.*",
        category=UserWarning,
    )

    # Prefer preventing the pyzmq warning entirely on Windows.
    if os.name == "nt":
        try:
            import asyncio
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()

    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    if not os.getenv("AGENTSWARM_BIN"):
        local_exe = _resolve_local_tui_bin()
        if local_exe is not None:
            os.environ["AGENTSWARM_BIN"] = str(local_exe)

    # Disable OpenAI Agents SDK tracing for terminal demo runs.
    try:
        from agents import set_tracing_disabled
        set_tracing_disabled(True)
    except Exception:
        pass

    from swarm import create_agency

    onboard_flag = Path(tempfile.gettempdir()) / "_openswarm_onboard.flag"
    os.environ["OPENSWARM_ONBOARD_FLAG"] = str(onboard_flag)
    onboard_flag.unlink(missing_ok=True)

    while True:
        import logging
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        logging.disable(logging.NOTSET)
        print("\nStarting OpenSwarm… this may take a few seconds.")
        _configure_demo_console()

        # Suppress OS-level stderr (fd 2) to prevent GLib/GIO UWP-app
        # warnings from appearing in the terminal during startup and TUI.
        _saved_stderr_fd = None
        try:
            _saved_stderr_fd = os.dup(2)
            _dn = os.open(os.devnull, os.O_WRONLY)
            os.dup2(_dn, 2)
            os.close(_dn)
        except OSError:
            pass

        print(build_integration_summary())
        print()
        _configure_tui_backend_auth_env()

        agency = create_agency()
        agency.tui(show_reasoning=True, reload=False)

        if _saved_stderr_fd is not None:
            try:
                os.dup2(_saved_stderr_fd, 2)
                os.close(_saved_stderr_fd)
            except OSError:
                pass

        if onboard_flag.exists():
            onboard_flag.unlink(missing_ok=True)
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
            logging.disable(logging.NOTSET)
            print("\nLaunching setup wizard…")
            from onboard import run_onboarding
            run_onboarding()
            load_dotenv(override=True)
        else:
            break


if __name__ == "__main__":
    _bootstrap()
    main()
