"""Inventory installed iRacing car packages and compare them with app assets."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path

from .paths import resource_path


@dataclass(frozen=True)
class IracingCarPackage:
    folder_path: str
    relative_path: str
    version: str = ""
    image_folder: str = ""
    image_exists: bool = False
    csv_entry_exists: bool = False


def _compact(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def scan_iracing_car_packages(iracing_root: Path | None) -> list[IracingCarPackage]:
    """Find leaf car packages, excluding category/grouping directories."""
    cars_root = (iracing_root or Path()) / "cars"
    if not cars_root.is_dir():
        return []
    packages: list[IracingCarPackage] = []
    for directory in cars_root.rglob("*"):
        if not directory.is_dir() or any(child.is_dir() for child in directory.iterdir()):
            continue
        dat_files = list(directory.glob("*.dat"))
        if not dat_files:
            continue
        version_file = directory / "version.txt"
        try:
            version = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else ""
        except OSError:
            version = ""
        packages.append(
            IracingCarPackage(
                folder_path=str(directory),
                relative_path=str(directory.relative_to(cars_root)).replace("\\", "/"),
                version=version,
            )
        )
    return sorted(packages, key=lambda item: item.relative_path.casefold())


def compare_iracing_car_images(
    iracing_root: Path | None,
    assets_root: Path | None = None,
    cars_csv: Path | None = None,
) -> dict[str, object]:
    packages = scan_iracing_car_packages(iracing_root)
    assets_root = assets_root or resource_path("assets", "Cars", "Iracing")
    cars_csv = cars_csv or resource_path("data", "Cars.csv")
    csv_by_path: dict[str, dict[str, str]] = {}
    try:
        with cars_csv.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                if str(row.get("Game", "")).casefold() != "iracing":
                    continue
                path = str(row.get("FILEPATH", "")).strip().lstrip("\\/")
                if path:
                    csv_by_path[_compact(path)] = row
    except (OSError, csv.Error):
        pass

    enriched: list[IracingCarPackage] = []
    for package in packages:
        row = csv_by_path.get(_compact(package.relative_path), {})
        image_folder = str(row.get("image file", "")).strip()
        image_exists = bool(image_folder) and (assets_root / image_folder).is_dir()
        enriched.append(
            IracingCarPackage(
                **{**asdict(package), "image_folder": image_folder, "image_exists": image_exists, "csv_entry_exists": bool(row)}
            )
        )
    return {
        "cars_root": str((iracing_root or Path()) / "cars"),
        "installed_leaf_packages": [asdict(package) for package in enriched],
        "installed_count": len(enriched),
        "missing_csv_entries": [asdict(package) for package in enriched if not package.csv_entry_exists],
        "missing_images": [asdict(package) for package in enriched if not package.image_exists],
    }
