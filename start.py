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
    if not PYTHON.exists():
        subprocess.run(find_python() + ["-m", "venv", str(ENVIRONMENT)], check=True)
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
        subprocess.run([str(PYTHON), "-m", "ensurepip", "--upgrade"], check=True)
        subprocess.run(
            [str(PYTHON), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")],
            check=True,
        )
        subprocess.run([str(PYTHON), "-c", probe], cwd=ROOT, check=True)


def run(script="app.py", arguments=None):
    """Launch a project entry point with packages installed in the same Python."""
    try:
        prepare_environment()
        environment = os.environ.copy()
        environment["FG_PROJECT_PYTHON"] = str(PYTHON.resolve())
        return subprocess.call(
            [str(PYTHON), "-u", str(ROOT / script), *(arguments or [])],
            cwd=ROOT,
            env=environment,
        )
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print("Startup failed. " + str(error), file=sys.stderr)
        return 1


def bootstrap(script):
    """Route direct VS Code Run and terminal execution through setup once."""
    if os.environ.get("FG_PROJECT_PYTHON") != str(Path(sys.executable).resolve()):
        raise SystemExit(run(script, sys.argv[1:]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update", action="store_true", help="Build daily index outputs"
    )
    args, remaining = parser.parse_known_args()
    return run("update_index.py" if args.update else "app.py", remaining)


if __name__ == "__main__":
    raise SystemExit(main())
