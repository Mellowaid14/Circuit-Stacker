# GitHub Update Releases

Circuit Stacker can check GitHub Releases at launch and show a download prompt when a newer release exists.

## One-Time Setup

1. Create a GitHub repository for the app.
2. Open `src/circuit_stackers/version.py`.
3. Set:

```python
GITHUB_OWNER = "YourGitHubUserName"
GITHUB_REPO = "YourRepositoryName"
```

4. Keep `APP_VERSION` matching the version you are shipping.

## Publishing A New Update

1. Update `APP_VERSION` in `src/circuit_stackers/version.py`.
2. Update `version` in `pyproject.toml`.
3. Update `MyAppVersion` in `CircuitStackerInstaller.iss`.
4. Build the installer:

```powershell
.\build_installer.ps1
```

5. On GitHub, create a new Release.
6. Use a tag that matches the app version, such as `v1.0.1`.
7. Upload the installer from the `output` folder, such as:

```text
CircuitStackerSetup-1.0.1.exe
```

8. Add release notes and publish the release.

## How The App Chooses The Download

The app reads GitHub's latest release API and looks for an uploaded asset whose filename:

- ends in `.exe`
- preferably contains `Setup` or `Installer`
- preferably contains `Circuit` and `Stacker`

If no installer asset is found, it opens the GitHub release page instead.

## User Saves

The installer replaces app files. User saves/settings remain in the user's selected data folder and are not part of the installed app folder.
