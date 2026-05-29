# Circuit Stacker

Circuit Stacker is a racing career management app for players who want a deeper single-player career experience in iRacing and Automobilista 2.

Instead of just running one-off races, Circuit Stacker creates a living racing world around you. It generates drivers, teams, championships, schedules, standings, rivalries, team offers, promotions, retirements, and news stories. As you race, the rest of the world keeps moving too, with AI drivers and teams building their own careers over multiple seasons.

Players can start a career in either iRacing or AMS2, receive team and championship offers based on performance, and work their way up through more prestigious series. The app tracks results, MMR, wins, podiums, top 5s, rivalries, team history, and driver history. It also supports multiclass racing, custom championships, owned content filtering, and manual difficulty adjustments.

For iRacing, Circuit Stacker can export AI rosters and season files. For AMS2, it can export custom AI driver rosters with matching cars and liveries. It also includes live race sync features, so results and driver order can be pulled from the game more easily.

The goal of Circuit Stacker is to make offline racing feel like a real motorsport career. You are not just picking random races. You are joining teams, watching rivals develop, seeing championships evolve, and building a racing legacy inside a world that keeps growing around you.

## Features

- Career saves for iRacing and Automobilista 2
- Generated driver and team pools with long-term history
- Team offers based on performance, MMR, and championship prestige
- Multiclass championship support
- Custom championship creation and management
- iRacing AI roster and season exporting
- AMS2 custom AI roster exporting with car and livery matching
- Live race sync tools for entering results
- Driver rivalries, world news, messages, and team storylines
- Owned content filtering for cars, tracks, and DLC
- Windows installer/export workflow

## Quick Start

Players can start a career in either iRacing or AMS2, receive team and championship offers based on performance, and work their way up through more prestigious series. The app tracks results, MMR, wins, podiums, top 5s, rivalries, team history, and driver history. It also supports multiclass racing, custom championships, owned content filtering, and manual difficulty adjustments.

## Windows Installer Export

To build the Windows installer:

```powershell
.\build_installer.ps1
```

The installer will be created in the project output folder.

## Development Export

To build a shareable Windows app folder without the installer:

```powershell
py -m pip install -e .[build]
py -m PyInstaller --clean --noconfirm .\circuit_stackers.spec
```

Or run:

```powershell
.\build_windows.ps1
```

## Project Structure

- `src/circuit_stackers/app.py`: desktop app entry point
- `src/circuit_stackers/screens/`: UI screens for saves, championships, gameplay, results, teams, messages, and settings
- `src/circuit_stackers/game_logic.py`: season flow, race simulation, progression, and world updates
- `src/circuit_stackers/roster_exporter.py`: iRacing and AMS2 roster export logic
- `src/circuit_stackers/season_exporter.py`: iRacing season export logic
- `src/circuit_stackers/data/`: cars, tracks, championships, teams, liveries, and name data
- `tests/`: smoke tests for save and season logic
