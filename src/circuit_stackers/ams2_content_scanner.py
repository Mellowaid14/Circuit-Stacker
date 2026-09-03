"""Discover Automobilista 2 content without modifying the game installation.

AMS2 stores shipped vehicle content in packed ``Pakfiles`` archives.  Custom
liveries and custom AI drivers remain ordinary XML files, so this scanner
reports both sources and clearly separates package discovery from livery-ID
discovery.
"""

from __future__ import annotations

import re
import csv
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
from xml.etree import ElementTree as ET


@dataclass(frozen=True)
class Ams2Roots:
    configured: Path
    install: Path | None
    user_data: Path | None


@dataclass(frozen=True)
class PackedVehicle:
    package_name: str
    archive: Path
    header_name: str = ""


@dataclass(frozen=True)
class CustomLivery:
    name: str
    source: Path
    vehicle_folder: str
    livery_id: str = ""


@dataclass(frozen=True)
class CustomAiLivery:
    name: str
    source: Path
    roster: str


@dataclass(frozen=True)
class CarPackageMatch:
    car_id: str
    car_name: str
    csv_folder: str
    package_name: str = ""
    candidates: tuple[str, ...] = ()


def _is_install(path: Path) -> bool:
    return (path / "Pakfiles").is_dir() or (path / "Vehicles" / "Textures" / "CustomLiveries").is_dir()


def _is_user_data(path: Path) -> bool:
    return (path / "UserData").is_dir()


def _steam_library_roots() -> list[Path]:
    candidates = [
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
    ]
    roots: list[Path] = []
    for steam_root in candidates:
        vdf = steam_root / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            roots.append(steam_root)
            for raw_path in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="ignore")):
                roots.append(Path(raw_path.replace("\\\\", "\\")))
    return roots


def discover_roots(configured_path: str | Path) -> Ams2Roots:
    """Resolve the configured AMS2 data directory and its install directory."""
    configured = Path(configured_path).expanduser() if str(configured_path).strip() else Path()
    install = configured if _is_install(configured) else None
    user_data = configured if _is_user_data(configured) else None

    candidates: list[Path] = []
    if install is not None:
        candidates.append(install)
    for library in _steam_library_roots():
        candidates.append(library / "steamapps" / "common" / "Automobilista 2")
    if install is None:
        candidates.append(Path(r"C:\Program Files (x86)\Steam\steamapps\common\Automobilista 2"))
    for candidate in candidates:
        if _is_install(candidate):
            install = candidate
            break
    return Ams2Roots(configured=configured, install=install, user_data=user_data)


def _header_name(archive: Path) -> str:
    try:
        data = archive.read_bytes()[:256]
    except OSError:
        return ""
    # BFF package headers commonly contain the package name after the KAP
    # marker. This is metadata only; it is not a livery ID.
    match = re.search(rb"[A-Za-z0-9][A-Za-z0-9_ -]{3,100}(?:_Livery|_LD_Livery)", data)
    return match.group(0).decode("ascii", errors="ignore") if match else ""


def scan_packed_vehicles(install_root: Path | None) -> list[PackedVehicle]:
    if install_root is None:
        return []
    vehicle_dir = install_root / "Pakfiles" / "Vehicles"
    results: list[PackedVehicle] = []
    for archive in sorted(vehicle_dir.glob("*_Livery.bff")):
        package_name = archive.stem.removesuffix("_Livery")
        if package_name.endswith("_LD"):
            continue
        results.append(PackedVehicle(package_name, archive, _header_name(archive)))
    return results


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def compare_cars_csv_to_packages(install_root: Path | None, cars_csv: Path) -> list[CarPackageMatch]:
    """Compare the CSV's AMS2 livery folders with shipped BFF package names.

    Exact normalized matches are safe to use as an update source. Fuzzy
    candidates are reported for review because one package can represent
    several car variants and should not be changed automatically.
    """
    packages = scan_packed_vehicles(install_root)
    package_by_key = {_compact(item.package_name): item.package_name for item in packages}
    package_names = list(package_by_key.values())
    with cars_csv.open(newline="", encoding="utf-8-sig") as file_obj:
        rows = [row for row in csv.DictReader(file_obj) if str(row.get("Game", "")).casefold() == "ams2"]
    results: list[CarPackageMatch] = []
    for row in rows:
        folder = str(row.get("ams2_livery_folder", "")).strip()
        exact = package_by_key.get(_compact(folder)) if folder else None
        if exact:
            results.append(CarPackageMatch(str(row.get("id", "")).strip(), str(row.get("Car", "")).strip(), folder, exact))
            continue
        basis = _compact(folder or str(row.get("Car", "")))
        candidates = tuple(
            sorted(
                package_names,
                key=lambda name: SequenceMatcher(None, basis, _compact(name)).ratio(),
                reverse=True,
            )[:3]
        )
        results.append(CarPackageMatch(str(row.get("id", "")).strip(), str(row.get("Car", "")).strip(), folder, candidates=candidates))
    return results


def _xml_files(root: Path | None) -> list[Path]:
    return sorted(root.rglob("*.xml")) if root and root.is_dir() else []


def scan_custom_liveries(roots: Ams2Roots) -> list[CustomLivery]:
    results: list[CustomLivery] = []
    override_roots = []
    for root in (roots.install, roots.user_data):
        if root:
            override_roots.append(root / "Vehicles" / "Textures" / "CustomLiveries" / "Overrides")
    seen: set[tuple[str, str, str]] = set()
    for override_root in override_roots:
        for xml_path in _xml_files(override_root):
            if xml_path.name.casefold().endswith("_dist.xml"):
                continue
            try:
                tree = ET.parse(xml_path)
            except (ET.ParseError, OSError):
                continue
            vehicle_folder = xml_path.parent.relative_to(override_root).parts[0] if xml_path.parent != override_root else ""
            for node in tree.iter():
                if node.tag.split("}")[-1].casefold() != "livery_override":
                    continue
                name = str(node.attrib.get("NAME") or node.attrib.get("Name") or "").strip()
                livery_id = str(node.attrib.get("ID") or node.attrib.get("id") or "").strip()
                key = (name.casefold(), str(xml_path).casefold(), vehicle_folder.casefold())
                if name and key not in seen:
                    seen.add(key)
                    results.append(CustomLivery(name, xml_path, vehicle_folder, livery_id))
    return results


def scan_custom_ai_liveries(roots: Ams2Roots) -> list[CustomAiLivery]:
    results: list[CustomAiLivery] = []
    seen: set[tuple[str, str]] = set()
    for root in (roots.install, roots.user_data):
        for xml_path in _xml_files(root / "UserData" / "CustomAIDrivers" if root else None):
            try:
                tree = ET.parse(xml_path)
            except (ET.ParseError, OSError):
                continue
            for node in tree.iter():
                if node.tag.split("}")[-1].casefold() != "driver":
                    continue
                name = str(node.attrib.get("livery_name") or "").strip()
                key = (name.casefold(), str(xml_path).casefold())
                if name and key not in seen:
                    seen.add(key)
                    results.append(CustomAiLivery(name, xml_path, xml_path.stem))
    return results


def scan_ams2_content(configured_path: str | Path) -> dict[str, object]:
    roots = discover_roots(configured_path)
    packed = scan_packed_vehicles(roots.install)
    custom = scan_custom_liveries(roots)
    ai = scan_custom_ai_liveries(roots)
    cars_csv = Path(__file__).resolve().parent / "data" / "Cars.csv"
    package_matches = compare_cars_csv_to_packages(roots.install, cars_csv) if cars_csv.exists() else []
    return {
        "roots": asdict(roots),
        "packed_vehicles": [asdict(item) for item in packed],
        "custom_liveries": [asdict(item) for item in custom],
        "custom_ai_liveries": [asdict(item) for item in ai],
        "csv_package_matches": [asdict(item) for item in package_matches],
        "csv_exact_package_match_count": sum(bool(item.package_name) for item in package_matches),
        "default_livery_ids_available": False,
        "notes": ["Default liveries are packed in BFF archives; package discovery works, but IDs need a game-format parser or authoritative mapping."],
    }
