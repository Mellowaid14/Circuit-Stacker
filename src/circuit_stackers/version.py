from __future__ import annotations

APP_VERSION = "1.6.2"

# Fill these in once the GitHub repository is created.
# Example:
# GITHUB_OWNER = "YourGitHubName"
# GITHUB_REPO = "Circuit-Stacker"
GITHUB_OWNER = "Mellowaid14"
GITHUB_REPO = "Circuit-Stacker"


def github_latest_release_url() -> str:
    if not GITHUB_OWNER or not GITHUB_REPO:
        return ""
    return f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
