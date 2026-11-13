"""Prepare one Python environment and run the dashboard or daily pipeline."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
ENVIRONMENT = ROOT / ".venv"
PYTHON = ENVIRONMENT / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def supported(command):
    """Check the interpreter itself, including an existing project environment."""
    try:
        return (
            subprocess.run(
                command
                + [
                    "-c",
                    "import sys; sys.exit(not ((3,10) <= sys.version_info[:2] < (3,14)))",
                ],
                capture_output=True,
            ).returncode
            == 0
        )
    except OSError:
        return False


def find_python():
    """Find supported Python even when VS Code selected a different version."""
    candidates = [[sys.executable]]
    if os.name == "nt":
        if shutil.which("py"):
            candidates.extend(
                [["py", "-" + version] for version in ("3.12", "3.13", "3.11", "3.10")]
            )
        candidates.append(
            [
                str(
                    Path(os.environ.get("ProgramData", "C:/ProgramData"))
                    / "anaconda3/python.exe"
                )
            ]
        )
        candidates.append([str(Path.home() / "anaconda3/python.exe")])
    if shutil.which("python"):
        candidates.append([shutil.which("python")])
    for command in candidates:
        if supported(command):
            return command
    raise RuntimeError("Install Python 3.12, then run this file again.")


def prepare_environment():
    """Install and validate the declared versions in the project environment."""
    uv = shutil.which("uv")
    if not PYTHON.exists():
        base = find_python()
        print(f"Creating .venv with {' '.join(base)}...", flush=True)
        subprocess.run(
            base + ["-m", "venv", "--without-pip", str(ENVIRONMENT)], check=True
        )
    if not supported([str(PYTHON)]):
        raise RuntimeError(
            "The existing .venv is unusable or unsupported. Rename .venv and run again to create a fresh environment."
        )
    print("Project Python: " + str(PYTHON), flush=True)
    # Version checks catch old Dash/Plotly installations that import successfully.
    probe = """
import importlib
from importlib.metadata import version
from packaging.requirements import Requirement
from pathlib import Path
for line in Path('requirements.txt').read_text().splitlines():
    if not line.strip() or line.startswith('#'):
        continue
    requirement = Requirement(line)
    assert version(requirement.name) in requirement.specifier, line
for module in ('dash', 'flask', 'pandas', 'numpy', 'plotly', 'tzdata'):
    importlib.import_module(module)
"""
    if subprocess.run(
        [str(PYTHON), "-c", probe], cwd=ROOT, capture_output=True
    ).returncode:
        requirements = str(ROOT / "requirements.txt")
        print(
            "Installing project packages. First setup may take a few minutes.",
            flush=True,
        )
        if uv:
            installed = subprocess.run(
                [
                    uv,
                    "pip",
                    "install",
                    "--python",
                    str(PYTHON),
                    "-r",
                    requirements,
                    "pip",
                    "--no-cache",
                ],
            ).returncode == 0
            if not installed:
                print("uv setup failed. Trying pip instead...", flush=True)
        if not uv or not installed:
            pip = [str(PYTHON), "-m", "pip"]
            if subprocess.run(pip + ["--version"], capture_output=True).returncode:
                print("Initializing pip in .venv...", flush=True)
                subprocess.run([str(PYTHON), "-m", "ensurepip"], check=True)
            subprocess.run(pip + ["install", "-r", requirements], check=True)
        subprocess.run([str(PYTHON), "-c", probe], cwd=ROOT, check=True)


def prepare_bloomberg():
    """Install the Desktop API from Bloomberg's official package repository."""
    probe = [str(PYTHON), "-c", "import blpapi"]
    if subprocess.run(probe, capture_output=True).returncode == 0:
        return
    print("Installing Bloomberg API into the project environment...", flush=True)
    pip = [str(PYTHON), "-m", "pip"]
    if subprocess.run(pip + ["--version"], capture_output=True).returncode:
        subprocess.run([str(PYTHON), "-m", "ensurepip"], check=True)
    subprocess.run(
        pip + ["install", "--upgrade", "--index-url",
               "https://blpapi.bloomberg.com/repository/releases/python/simple/",
               "blpapi"], check=True
    )
    subprocess.run(probe, check=True)


def run(module="app", arguments=None):
    """Launch a project entry point with packages installed in the same Python."""
    try:
        arguments = arguments or []
        if module == "app":
            options = argparse.ArgumentParser(add_help=False)
            options.add_argument("--port", type=int, default=8050)
            selected, _ = options.parse_known_args(arguments)
            if not 1 <= selected.port <= 65535:
                raise RuntimeError("Port must be between 1 and 65535.")
            print(
                f"\nDASHBOARD LINK: http://127.0.0.1:{selected.port}\n"
                "Setup is starting. Open this link once the terminal says Running on.\n"
                "Keep this terminal open while using the dashboard.\n",
                flush=True,
            )
        prepare_environment()
        needs_bloomberg = (
            (module == "app" and "--offline" not in arguments)
            or (module == "update_index" and "--refresh" in arguments)
            or module in ("run_all_checks", "repair_breadth")
        )
        if needs_bloomberg:
            prepare_bloomberg()
        return subprocess.call(
            [str(PYTHON), "-u", "-m", f"index_engine.{module}", *(arguments or [])],
            cwd=ROOT,
        )
    except KeyboardInterrupt:
        print(
            "\nStopped. Run the same command to resume setup or restart the app.",
            file=sys.stderr,
        )
        return 130
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print("Startup failed. " + str(error), file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Open the dashboard. Optional modes run without a browser.",
        epilog="Dashboard options: --offline, --port PORT. Pipeline option: --refresh.",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--update", dest="module", action="store_const",
                       const="update_index", help="Build and export the daily index")
    modes.add_argument("--check-data", dest="module", action="store_const",
                       const="run_all_checks", help="Diagnose source access")
    modes.add_argument("--repair-breadth", dest="module", action="store_const",
                       const="repair_breadth", help="Replace legacy breadth data")
    args, remaining = parser.parse_known_args()
    return run(args.module or "app", remaining)


if __name__ == "__main__":
    raise SystemExit(main())
