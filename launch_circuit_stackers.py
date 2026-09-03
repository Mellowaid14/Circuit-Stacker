from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"

# Explorer uses the system .py file association, which may not be this
# project's virtual environment. Re-launch through the local environment so
# double-clicking this file uses the correct dependencies.
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "pythonw.exe"
if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    raise SystemExit(
        subprocess.call(
            [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]],
            cwd=str(PROJECT_ROOT),
        )
    )

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from circuit_stackers.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
