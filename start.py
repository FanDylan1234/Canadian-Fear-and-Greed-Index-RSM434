"""Set up the project environment and run Dash: python start.py [--offline]."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        base = [sys.executable]
        if not (3, 10) <= sys.version_info[:2] < (3, 14):
            base = None
            if os.name == 'nt' and shutil.which('py'):
                for version in ('3.12', '3.13', '3.11', '3.10'):
                    candidate = ['py', '-' + version]
                    if subprocess.run(candidate + ['-c', 'pass'], capture_output=True).returncode == 0:
                        base = candidate
                        break
            if base is None:
                print('Install Python 3.12 from https://www.python.org/downloads/ then rerun python start.py.', flush=True)
                return 1
        subprocess.run(base + ['-m', 'venv', str(ROOT / '.venv')], check=True)
    print('Project Python: ' + str(python), flush=True)
    probe = subprocess.run([str(python), '-c', 'import dash, flask, pandas, numpy, plotly, tzdata'], capture_output=True)
    if probe.returncode:
        print('Installing dashboard dependencies...', flush=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.txt')], check=True)
    print('In VS Code: Python: Select Interpreter -> ' + str(python), flush=True)
    return subprocess.call([str(python), '-u', str(ROOT / 'app.py'), *sys.argv[1:]], cwd=ROOT)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        print('Setup failed. Resolve the installation error above and rerun python start.py.', flush=True)
        raise SystemExit(error.returncode)
