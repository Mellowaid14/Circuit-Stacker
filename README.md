# Circuit Stackers

Circuit Stackers is a Python desktop app for running an iRacing-style career mode.
You can create a save, choose a championship, simulate races, and track standings
across a season.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
python -m pytest
python -m circuit_stackers
```

## Windows export

To build a shareable Windows app folder:

```powershell
py -m pip install -e .[build]
py -m PyInstaller --clean --noconfirm .\circuit_stackers.spec
```

Or run:

```powershell
.\build_windows.ps1
```

The exported app will be created in:

```text
dist\Circuit Stackers
```

Share that whole folder, not just the `.exe`, so the bundled files stay together.

## Current structure

- `src/circuit_stackers/app.py`: CustomTkinter app entry point
- `src/circuit_stackers/screens/`: UI screens for menu, saves, championships, and gameplay
- `src/circuit_stackers/game_logic.py`: season creation, race simulation, and persistence flow
- `src/circuit_stackers/data/`: championship and track data
- `tests/test_save_and_logic.py`: smoke tests for save and season logic
