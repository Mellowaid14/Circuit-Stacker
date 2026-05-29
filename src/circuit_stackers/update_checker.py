from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .version import APP_VERSION, github_latest_release_url


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    download_url: str
    release_url: str
    release_notes: str


def update_check_configured() -> bool:
    return bool(github_latest_release_url())


def check_for_update(timeout_seconds: float = 5.0) -> UpdateInfo | None:
    url = github_latest_release_url()
    if not url:
        return None

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"Circuit-Stacker/{APP_VERSION}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None

    latest_version = str(payload.get("tag_name") or payload.get("name") or "").strip()
    if not latest_version:
        return None
    if not _version_is_newer(latest_version, APP_VERSION):
        return None

    release_url = str(payload.get("html_url") or "").strip()
    download_url = _installer_download_url(payload) or release_url
    if not download_url:
        return None

    return UpdateInfo(
        current_version=APP_VERSION,
        latest_version=latest_version,
        download_url=download_url,
        release_url=release_url or download_url,
        release_notes=str(payload.get("body") or "").strip(),
    )


def _installer_download_url(payload: dict[str, Any]) -> str:
    assets = payload.get("assets")
    if not isinstance(assets, list):
        return ""
    installer_assets: list[tuple[int, str]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "").strip()
        url = str(asset.get("browser_download_url") or "").strip()
        if not name or not url:
            continue
        lowered = name.casefold()
        score = 0
        if lowered.endswith(".exe"):
            score += 10
        if "setup" in lowered or "installer" in lowered:
            score += 5
        if "circuit" in lowered and "stacker" in lowered:
            score += 3
        if score:
            installer_assets.append((score, url))
    if not installer_assets:
        return ""
    installer_assets.sort(reverse=True)
    return installer_assets[0][1]


def _version_is_newer(candidate: str, current: str) -> bool:
    candidate_parts = _version_parts(candidate)
    current_parts = _version_parts(current)
    width = max(len(candidate_parts), len(current_parts), 3)
    candidate_parts.extend([0] * (width - len(candidate_parts)))
    current_parts.extend([0] * (width - len(current_parts)))
    return candidate_parts > current_parts


def _version_parts(value: str) -> list[int]:
    cleaned = str(value).strip().lstrip("vV")
    parts = [int(match) for match in re.findall(r"\d+", cleaned)]
    return parts or [0]
